"""Interface en ligne de commande.

    quittances --maison anzin --envoyer      mois courant, toute la maison
    quittances --locataire Jin --periode 2026-09
    quittances locataires
    quittances attestation --locataire Jin --depuis 2026-09-01

« quittance » est la commande par defaut : elle peut etre omise.

L'envoi d'email n'a jamais lieu sans `--envoyer` : l'ancienne version envoyait
systematiquement, y compris quand le PDF n'avait pas ete regenere.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .config import Config, ConfigError, Tenant
from .documents import Attestation, DocumentError, Quittance, quittance_path
from .formatting import format_amount, iter_months, month_year, parse_amount
from .mailer import MailError, MailSettings, build_message, send
from .pdf import render_attestation, render_quittance

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


class CliError(Exception):
    """Erreur d'usage, rapportee sans trace d'exception."""


def parse_date(value: str) -> date:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise CliError(
        f"Date invalide : {value!r}. Formats acceptes : AAAA-MM-JJ ou JJ/MM/AAAA."
    )


def parse_period(value: str | None) -> date:
    """« 2025-09 » -> premier jour du mois. Sans valeur : le mois courant."""
    if value is None:
        return date.today().replace(day=1)
    try:
        return datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise CliError(f"Periode invalide : {value!r}. Format attendu : AAAA-MM.") from exc


def _amount(value: str) -> Decimal:
    try:
        return parse_amount(value)
    except ValueError as exc:
        raise CliError(str(exc)) from exc


def select_tenants(config: Config, args: argparse.Namespace) -> list[Tenant]:
    """--locataire cible des personnes, --maison une adresse, --tous tout le monde.

    `--maison` sans `--locataire` vaut « tous les locataires de cette maison » : il n'y
    a pas d'autre lecture raisonnable, autant ne pas exiger `--tous` en plus.
    """
    actifs = [
        nom
        for nom, actif in (
            ("--locataire", bool(args.locataire)),
            ("--maison", bool(args.maison)),
            ("--tous", bool(args.tous)),
        )
        if actif
    ]
    if len(actifs) > 1:
        # Sans ce garde-fou, --maison l'emportait en silence et le lot partait
        # a toute la maison au lieu du locataire nomme.
        raise CliError(
            f"Selecteurs incompatibles : {' et '.join(actifs)}. Choisissez-en un "
            "seul ; la maison d'un locataire nomme est deduite de sa fiche."
        )

    if args.maison or args.tous:
        tenants = list(config.tenants.values())
        if args.maison:
            if args.maison not in config.properties:
                connus = ", ".join(sorted(config.properties))
                raise CliError(f"Maison « {args.maison} » inconnue. Maisons : {connus}.")
            tenants = [t for t in tenants if t.property.key == args.maison]
            if not tenants:
                raise CliError(f"Aucun locataire dans la maison « {args.maison} ».")
        return tenants
    if not args.locataire:
        raise CliError("Precisez --locataire NOM, --maison CLE ou --tous.")
    return [config.tenant(nom) for nom in args.locataire]


def resolve_amounts(
    tenant: Tenant, args: argparse.Namespace
) -> tuple[Decimal, Decimal]:
    """Priorite a la ligne de commande, puis a la configuration du locataire."""
    loyer = args.loyer if args.loyer is not None else tenant.rent
    charges = args.charges if args.charges is not None else tenant.charges
    if loyer is None:
        raise CliError(
            f"Loyer inconnu pour {tenant.full_name} : renseignez « rent » dans "
            f"config.yaml (tenants.{tenant.key}) ou passez --loyer."
        )
    if charges is None:
        charges = Decimal("0.00")
    return loyer, charges


def _confirm(question: str) -> bool:
    if not sys.stdin.isatty():
        return False
    reponse = input(f"{question} [o/N] ").strip().lower()
    return reponse in {"o", "oui", "y", "yes"}


def _deliver(
    config: Config,
    tenant: Tenant,
    subject: str,
    bodies: tuple[str, str],
    attachment: Path,
) -> None:
    if not tenant.emails:
        raise MailError(
            f"Aucune adresse email pour {tenant.full_name} : renseignez « email » "
            f"dans config.yaml (tenants.{tenant.key})."
        )
    settings = MailSettings.from_env(from_name=config.landlord.legal_name)
    texte, html = bodies
    message = build_message(
        settings, tenant.emails, subject, texte, html, attachment=attachment
    )
    send(settings, message)
    print(f"  Email envoye a {', '.join(tenant.emails)}")


def cmd_tenants(config: Config, args: argparse.Namespace) -> int:
    largeur = max((len(cle) for cle in config.tenants), default=4)
    print(f"{'CLE'.ljust(largeur)}  {'NOM'.ljust(28)}  {'MAISON'.ljust(8)}  LOYER")
    for cle, tenant in sorted(config.tenants.items()):
        loyer = format_amount(tenant.rent) if tenant.rent is not None else "-"
        charges = (
            f" + {format_amount(tenant.charges)} de charges"
            if tenant.charges
            else ""
        )
        print(
            f"{cle.ljust(largeur)}  {tenant.full_name.ljust(28)}  "
            f"{tenant.property.key.ljust(8)}  {loyer}{charges}"
        )
    return 0


def markers() -> tuple[str, str]:
    """(emise, manquante), en ASCII si la sortie ne sait pas encoder mieux.

    Le terminal Windows accepte l'Unicode, mais une redirection retombe en
    cp1252 : sans ce repli, `quittances suivi > fichier.txt` planterait.
    """
    encodage = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "✓·".encode(encodage)
    except (UnicodeEncodeError, LookupError):
        return "X", "."
    return "✓", "·"


def cmd_suivi(config: Config, args: argparse.Namespace) -> int:
    """Tableau locataires x mois, coche la ou une quittance existe.

    L'application ne consulte aucun compte bancaire : le seul signal disponible
    est l'existence du PDF, emis lorsque le loyer est arrive. C'est donc un
    suivi des quittances emises, pas un releve de paiements.
    """
    debut = parse_period(args.depuis) if args.depuis else date.today().replace(month=1, day=1)
    fin = parse_period(args.jusqu_a) if args.jusqu_a else date.today().replace(day=1)
    if debut > fin:
        raise CliError(
            f"Periode vide : {debut:%m/%Y} est posterieur a {fin:%m/%Y}."
        )
    mois = iter_months(debut, fin)
    racine = Path(args.dossier) if args.dossier else None
    emise, manquante = markers()

    # Un etat des lieux porte par defaut sur tout le monde.
    tenants = (
        select_tenants(config, args)
        if (args.locataire or args.maison or args.tous)
        else list(config.tenants.values())
    )

    lignes = []
    for tenant in tenants:
        presence = [
            quittance_path(tenant, m, racine).is_file() for m in mois
        ]
        manquants = [m for m, presente in zip(mois, presence) if not presente]
        terme = (
            tenant.rent + (tenant.charges or Decimal("0"))
            if tenant.rent is not None
            else None
        )
        du = terme * len(manquants) if terme is not None and manquants else None
        acquitte = terme * sum(presence) if terme is not None else None
        lignes.append((tenant, presence, manquants, du, acquitte))

    if args.manquants:
        lignes = [ligne for ligne in lignes if ligne[2]]

    titre = f"Quittances emises de {month_year(debut)} a {month_year(fin)}"
    print(titre)
    print("Une quittance n'est emise qu'une fois le loyer encaisse.\n")

    if not lignes:
        print("Aucun locataire a afficher.")
        return 0

    largeur_nom = max(len(ligne[0].full_name) for ligne in lignes)
    entete_mois = " ".join(f"{m:%m}" for m in mois)
    print(f"{'LOCATAIRE'.ljust(largeur_nom)}  {'MAISON'.ljust(7)}  {entete_mois}   MANQUE")

    for tenant, presence, manquants, du, _ in lignes:
        cases = " ".join(f"{emise if p else manquante} " for p in presence)
        reste = f"{len(manquants)}" if manquants else "-"
        montant = f"  {format_amount(du)}" if du is not None else ""
        print(
            f"{tenant.full_name.ljust(largeur_nom)}  "
            f"{tenant.property.key.ljust(7)}  {cases}  {reste.rjust(5)}{montant}"
        )

    total_emises = sum(sum(ligne[1]) for ligne in lignes)
    total_manquants = sum(len(ligne[2]) for ligne in lignes)
    total_du = sum((l[3] for l in lignes if l[3] is not None), Decimal("0"))
    total_acquitte = sum((l[4] for l in lignes if l[4] is not None), Decimal("0"))

    # Cumul sur toute la periode affichee : il grandit d'un terme par mois
    # ecoule, ce qui donne le total attendu depuis le mois de depart.
    total_attendu = total_acquitte + total_du
    termes = total_emises + total_manquants

    print(
        f"\nDepuis {month_year(debut)} - {len(lignes)} locataires, "
        f"{termes} termes"
    )
    colonnes = (
        ("Attendu", total_attendu, ""),
        ("Acquitté", total_acquitte, f"{total_emises} quittances émises"),
        ("Restant", total_du, f"{total_manquants} manquantes"),
    )
    for libelle, montant, detail in colonnes:
        print(f"  {libelle.ljust(9)} {format_amount(montant).rjust(12)}   {detail}".rstrip())
    if any(ligne[3] is None and ligne[2] for ligne in lignes):
        print("Montant indisponible pour les locataires sans « rent » configure.")
    return 0


def cmd_quittance(config: Config, args: argparse.Namespace) -> int:
    periode = parse_period(args.periode)
    date_paiement = parse_date(args.date_paiement) if args.date_paiement else periode
    emise_le = parse_date(args.date) if args.date else date.today()
    tenants = select_tenants(config, args)
    racine = Path(args.dossier) if args.dossier else None

    # La periode est implicite par defaut : on l'affiche pour qu'une erreur de
    # mois se voie immediatement, avant tout envoi.
    print(f"Quittances de {periode.strftime('%m/%Y')} ({len(tenants)} locataires)\n")

    if args.envoyer and len(tenants) > 1:
        noms = ", ".join(t.full_name for t in tenants)
        if not _confirm(f"Envoyer la quittance a {len(tenants)} locataires ({noms}) ?"):
            raise CliError("Envoi annule.")

    erreurs = 0
    for tenant in tenants:
        # Un locataire mal configure ne doit pas interrompre le lot.
        try:
            loyer, charges = resolve_amounts(tenant, args)
        except CliError as exc:
            erreurs += 1
            print(f"{tenant.full_name} : {exc}", file=sys.stderr)
            continue
        quittance = Quittance(
            tenant=tenant,
            period=periode,
            payment_date=date_paiement,
            rent=loyer,
            charges=charges,
            issued_on=emise_le,
        )
        chemin = quittance.output_path(racine)
        print(f"{tenant.full_name} - {quittance.total_label} - {chemin}")

        if chemin.exists() and not args.forcer:
            print("  PDF deja present (utilisez --forcer pour regenerer)")
        else:
            render_quittance(quittance, config, chemin)
            print("  PDF genere")

        if args.envoyer:
            try:
                _deliver(
                    config,
                    tenant,
                    quittance.email_subject,
                    quittance.email_body(config.landlord.first_name),
                    chemin,
                )
            except MailError as exc:
                erreurs += 1
                print(f"  ECHEC de l'envoi : {exc}", file=sys.stderr)
        else:
            print("  Email non envoye (ajoutez --envoyer)")
    return 1 if erreurs else 0


def cmd_attestation(config: Config, args: argparse.Namespace) -> int:
    depuis = parse_date(args.depuis)
    emise_le = parse_date(args.date) if args.date else date.today()
    tenants = select_tenants(config, args)
    racine = Path(args.dossier) if args.dossier else None

    erreurs = 0
    for tenant in tenants:
        try:
            attestation = Attestation(
                tenant=tenant, hosted_since=depuis, issued_on=emise_le
            )
        except DocumentError as exc:
            erreurs += 1
            print(f"{tenant.full_name} : {exc}", file=sys.stderr)
            continue

        chemin = attestation.output_path(racine)
        print(f"{tenant.full_name} - {chemin}")

        if chemin.exists() and not args.forcer:
            print("  PDF deja present (utilisez --forcer pour regenerer)")
        else:
            render_attestation(attestation, config, chemin)
            print("  PDF genere")

        if args.envoyer:
            try:
                _deliver(
                    config,
                    tenant,
                    attestation.email_subject,
                    attestation.email_body(config.landlord.first_name),
                    chemin,
                )
            except MailError as exc:
                erreurs += 1
                print(f"  ECHEC de l'envoi : {exc}", file=sys.stderr)
        else:
            print("  Email non envoye (ajoutez --envoyer)")
    return 1 if erreurs else 0


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--locataire", action="append", metavar="CLE",
                        help="cle du locataire (repetable)")
    parser.add_argument("--tous", action="store_true",
                        help="tous les locataires")
    parser.add_argument("--maison", metavar="CLE",
                        help="tous les locataires de cette maison")
    parser.add_argument("--dossier", metavar="CHEMIN",
                        help="racine de sortie (defaut : dossier du bien)")
    parser.add_argument("--forcer", action="store_true",
                        help="regenere meme si le PDF existe")
    parser.add_argument("--envoyer", action="store_true",
                        help="envoie le document par email")
    parser.add_argument("--date", metavar="DATE",
                        help="date d'emission (defaut : aujourd'hui)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quittances",
        description="Generation des quittances de loyer et attestations d'hebergement.",
    )
    parser.add_argument("--config", metavar="CHEMIN", help="chemin de config.yaml")
    sous = parser.add_subparsers(dest="commande", required=True)

    p_list = sous.add_parser("locataires", help="liste les locataires configures")
    p_list.set_defaults(handler=cmd_tenants)

    p_quittance = sous.add_parser("quittance", help="genere une quittance de loyer")
    _add_common_arguments(p_quittance)
    p_quittance.add_argument("--periode", metavar="AAAA-MM",
                             help="defaut : mois courant")
    p_quittance.add_argument("--date-paiement", metavar="DATE",
                             help="defaut : premier jour de la periode")
    p_quittance.add_argument("--loyer", type=_amount, metavar="MONTANT")
    p_quittance.add_argument("--charges", type=_amount, metavar="MONTANT")
    p_quittance.set_defaults(handler=cmd_quittance)

    p_suivi = sous.add_parser(
        "suivi", help="qui a une quittance emise, mois par mois")
    p_suivi.add_argument("--locataire", action="append", metavar="CLE")
    p_suivi.add_argument("--tous", action="store_true")
    p_suivi.add_argument("--maison", metavar="CLE")
    p_suivi.add_argument("--depuis", metavar="AAAA-MM",
                         help="defaut : janvier de l'annee en cours")
    p_suivi.add_argument("--jusqu-a", metavar="AAAA-MM", dest="jusqu_a",
                         help="defaut : mois courant")
    p_suivi.add_argument("--manquants", action="store_true",
                         help="n'affiche que les locataires en retard")
    p_suivi.add_argument("--dossier", metavar="CHEMIN")
    p_suivi.set_defaults(handler=cmd_suivi)

    p_attestation = sous.add_parser("attestation", help="genere une attestation")
    _add_common_arguments(p_attestation)
    p_attestation.add_argument("--depuis", required=True, metavar="DATE",
                               help="date de debut d'hebergement")
    p_attestation.set_defaults(handler=cmd_attestation)

    return parser


COMMANDES = ("quittance", "attestation", "locataires", "suivi")


def inject_default_command(argv: Sequence[str]) -> list[str]:
    """Insere « quittance » quand aucune commande n'est donnee.

    C'est l'usage courant. Il faut sauter les options globales, y compris la
    valeur de `--config`, pour ne pas la prendre pour un nom de commande.
    """
    argv = list(argv)
    index = 0
    while index < len(argv):
        jeton = argv[index]
        if jeton in ("-h", "--help"):
            return argv
        if jeton == "--config":
            index += 2  # l'option et sa valeur
            continue
        if jeton.startswith("--config="):
            index += 1
            continue
        # La commande, si elle est donnee, suit immediatement les options
        # globales. Tout autre jeton signifie qu'elle est absente : une option
        # de sous-commande (--maison) comme sa valeur (anzin) arrivent ici.
        break
    if index < len(argv) and argv[index] in COMMANDES:
        return argv
    return argv[:index] + ["quittance"] + argv[index:]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(inject_default_command(
        sys.argv[1:] if argv is None else argv
    ))
    try:
        config = Config.load(args.config)
        manquants = config.assets.missing()
        if manquants:
            raise CliError(
                "Images introuvables : " + ", ".join(str(p) for p in manquants)
            )
        return int(args.handler(config, args))
    except (CliError, ConfigError, DocumentError, MailError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
