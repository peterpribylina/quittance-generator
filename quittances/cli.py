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

from .ajustements import Ajustement, Ajustements
from .config import Config, ConfigError, Tenant
from .documents import (
    Attestation,
    AttestationDomicile,
    DepotGarantie,
    DocumentError,
    Quittance,
    Relance,
    RelanceAssurance,
    fichiers_assurance,
    fichiers_depot_garantie,
    quittance_path,
)
from .formatting import format_amount, iter_months, month_year, parse_amount
from .mailer import MailError, MailSettings, build_message, send
from .pdf import (
    render_attestation,
    render_depot_garantie,
    render_attestation_domicile,
    render_quittance,
)

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
    tenant: Tenant, args: argparse.Namespace,
    ajustement: Ajustement | None = None,
) -> tuple[Decimal, Decimal]:
    """Montants du mois, par ordre de priorite decroissant :

    ligne de commande, puis ajustement du mois, puis loyer du bail.
    """
    loyer = args.loyer
    if loyer is None and ajustement is not None:
        loyer = ajustement.rent
    if loyer is None:
        loyer = tenant.rent

    charges = args.charges
    if charges is None and ajustement is not None:
        charges = ajustement.charges_effectives
    if charges is None:
        charges = tenant.charges

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
    attachment: Path | None = None,
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
    """(emise, en retard, a venir), en ASCII si la sortie encode mal.

    Le terminal Windows accepte l'Unicode, mais une redirection retombe en
    cp1252 : sans ce repli, `quittances suivi > fichier.txt` planterait.
    """
    encodage = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "✓·".encode(encodage)
    except (UnicodeEncodeError, LookupError):
        return "X", ".", " "
    return "✓", "·", " "


def printable(texte: str) -> str:
    """Rend un texte affichable quel que soit l'encodage de la sortie.

    Les corps d'email contiennent des emojis, absents de cp1252 : sans ce
    filtre, `quittances relance | more` plantait en UnicodeEncodeError.
    """
    encodage = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        texte.encode(encodage)
    except (UnicodeEncodeError, LookupError):
        return texte.encode(encodage, errors="replace").decode(encodage)
    return texte


MOIS_PAR_DEFAUT = 12  # une annee de bail


def periode_suivi(args: argparse.Namespace) -> tuple[list[date], date, date]:
    """Mois couverts, du premier au dernier.

    Sans `--jusqu-a`, la fenetre vaut une annee de bail a partir de `--depuis`.
    """
    debut = (
        parse_period(args.depuis)
        if args.depuis
        else date.today().replace(month=1, day=1)
    )
    if args.jusqu_a:
        fin = parse_period(args.jusqu_a)
        if debut > fin:
            raise CliError(f"Periode vide : {debut:%m/%Y} est posterieur a {fin:%m/%Y}.")
        return iter_months(debut, fin), debut, fin
    mois = [
        date(debut.year + (debut.month - 1 + i) // 12,
             (debut.month - 1 + i) % 12 + 1, 1)
        for i in range(MOIS_PAR_DEFAUT)
    ]
    return mois, debut, mois[-1]


def terme_du_mois(
    tenant: Tenant, periode: date, ajustements: Ajustements
) -> Decimal | None:
    """Loyer + charges reellement dus ce mois-la, ajustements compris.

    Sans loyer configure, renvoie None : le suivi affiche « - » plutot que de
    sommer un montant invente.
    """
    ajustement = ajustements.pour(tenant, periode)
    loyer = (ajustement.rent if ajustement else None) or tenant.rent
    if loyer is None:
        return None
    charges = ajustement.charges_effectives if ajustement else None
    if charges is None:
        charges = tenant.charges or Decimal("0.00")
    return loyer + charges


def etats_locataire(
    tenant: Tenant, mois: Sequence[date], racine: Path | None
) -> list[str]:
    """« emise », « retard » ou « avenir » pour chaque mois.

    Partage par `suivi` et `relance` : les deux doivent s'accorder sur ce qui
    constitue un retard, sans quoi on relancerait un mois non echu.
    """
    courant = date.today().replace(day=1)
    etats = []
    for m in mois:
        if quittance_path(tenant, m, racine).is_file():
            etats.append("emise")
        elif m <= courant:
            etats.append("retard")
        else:
            etats.append("avenir")
    return etats


def cmd_suivi(config: Config, args: argparse.Namespace) -> int:
    """Tableau locataires x mois de l'annee de bail, coche ou une quittance existe.

    L'application ne consulte aucun compte bancaire : le seul signal disponible
    est l'existence du PDF, emis lorsque le loyer est arrive. C'est donc un
    suivi des quittances emises, pas un releve de paiements.

    Les mois posterieurs au mois courant sont affiches mais comptes a part : un
    loyer de mars n'est pas un impaye en septembre.
    """
    ajustements = args.ajustements
    mois, debut, fin = periode_suivi(args)
    racine = Path(args.dossier) if args.dossier else None
    emise, manquante, future = markers()

    # Un etat des lieux porte par defaut sur tout le monde.
    tenants = (
        select_tenants(config, args)
        if (args.locataire or args.maison or args.tous)
        else list(config.tenants.values())
    )

    lignes = []
    for tenant in tenants:
        etats = etats_locataire(tenant, mois, racine)
        compte = {etat: etats.count(etat) for etat in ("emise", "retard", "avenir")}
        # Chaque mois a son propre terme : un ete sans charges ne se compte pas
        # comme un mois plein.
        termes = [terme_du_mois(tenant, m, ajustements) for m in mois]
        montants = (
            {
                etat: sum(
                    (terme for terme, e in zip(termes, etats) if e == etat),
                    Decimal("0.00"),
                )
                for etat in ("emise", "retard", "avenir")
            }
            if all(terme is not None for terme in termes)
            else None
        )
        lignes.append((tenant, etats, compte, montants))

    if args.manquants:
        lignes = [ligne for ligne in lignes if ligne[2]["retard"]]

    print(f"Quittances emises de {month_year(debut)} a {month_year(fin)}")
    print("Une quittance n'est emise qu'une fois le loyer encaisse.\n")

    if not lignes:
        print("Aucun locataire a afficher.")
        return 0

    symboles = {"emise": emise, "retard": manquante, "avenir": future}
    largeur_nom = max(len(ligne[0].short_name) for ligne in lignes)
    entete = " ".join(f"{m:%m}" for m in mois)
    print(f"{'LOCATAIRE'.ljust(largeur_nom)}  {'MAISON'.ljust(7)}  {entete}   RETARD")

    for tenant, etats, compte, montants in lignes:
        cases = " ".join(f"{symboles[e]} " for e in etats)
        retard = f"{compte['retard']}" if compte["retard"] else "-"
        montant = (
            f"  {format_amount(montants['retard'])}"
            if montants is not None and compte["retard"]
            else ""
        )
        print(
            f"{tenant.short_name.ljust(largeur_nom)}  "
            f"{tenant.property.key.ljust(7)}  {cases}  {retard.rjust(6)}{montant}"
        )

    totaux = {
        etat: sum(ligne[2][etat] for ligne in lignes)
        for etat in ("emise", "retard", "avenir")
    }
    euros = {
        etat: sum(
            (ligne[3][etat] for ligne in lignes if ligne[3] is not None), Decimal("0")
        )
        for etat in ("emise", "retard", "avenir")
    }
    attendu = euros["emise"] + euros["retard"] + euros["avenir"]

    print(f"\nAnnee {month_year(debut)} - {month_year(fin)} : "
          f"{len(lignes)} locataires, {len(mois)} mois")
    for libelle, montant, detail in (
        ("Attendu", attendu, f"{len(lignes) * len(mois)} termes"),
        ("Acquitté", euros["emise"], f"{totaux['emise']} quittances émises"),
        ("En retard", euros["retard"], f"{totaux['retard']} mois échus impayés"),
        ("À venir", euros["avenir"], f"{totaux['avenir']} mois non échus"),
    ):
        print(
            f"  {libelle.ljust(10)} {format_amount(montant).rjust(12)}   {detail}".rstrip()
        )
    if any(ligne[3] is None for ligne in lignes):
        print("Montant indisponible pour les locataires sans « rent » configure.")
    return 0


def _journal_plus_recent(
    pdf: Path, ajustement: Ajustement | None, ajustements: Ajustements
) -> bool:
    """Le PDF existant date-t-il d'avant la derniere retouche du journal ?

    Modifier un montant dans `ajustements.yaml` ne reecrit aucun document :
    sans cet avertissement, on relance la commande, on lit « PDF deja present »
    et on envoie l'ancien montant sans s'en apercevoir.

    Restreint aux mois effectivement ajustes, pour ne pas crier a chaque fois
    que le journal bouge pour un autre locataire.
    """
    if ajustement is None or ajustements.source is None:
        return False
    try:
        return ajustements.source.stat().st_mtime > pdf.stat().st_mtime
    except OSError:
        return False


def cmd_quittance(config: Config, args: argparse.Namespace) -> int:
    ajustements = args.ajustements
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
        ajustement = ajustements.pour(tenant, periode)
        # Un locataire mal configure ne doit pas interrompre le lot.
        try:
            loyer, charges = resolve_amounts(tenant, args, ajustement)
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
            # Le locataire voit un montant inhabituel : l'email en donne la
            # raison, sinon il ecrit pour demander.
            note=ajustement.motif if ajustement else None,
        )
        chemin = quittance.output_path(racine)
        print(f"{tenant.full_name} - {quittance.total_label} - {chemin}")
        if ajustement is not None:
            print(printable(f"  Ajustement : {ajustement.resume()}"))
            if ajustement.motif:
                print(printable(f"  Motif : {ajustement.motif}"))

        if chemin.exists() and not args.forcer:
            print("  PDF deja present (utilisez --forcer pour regenerer)")
            if _journal_plus_recent(chemin, ajustement, ajustements):
                print(
                    "  ATTENTION : le journal a ete modifie apres ce PDF, qui "
                    "peut porter d'anciens montants. Relancez avec --forcer.",
                    file=sys.stderr,
                )
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


def cmd_relance(config: Config, args: argparse.Namespace) -> int:
    """Rappel amiable aux locataires dont un mois echu n'a pas de quittance.

    Sans `--envoyer`, affiche les messages sans rien expedier : une relance
    part au nom du bailleur, elle se relit avant d'etre envoyee.
    """
    mois, debut, fin = periode_suivi(args)
    racine = Path(args.dossier) if args.dossier else None
    tenants = (
        select_tenants(config, args)
        if (args.locataire or args.maison or args.tous)
        else list(config.tenants.values())
    )

    relances = []
    for tenant in tenants:
        etats = etats_locataire(tenant, mois, racine)
        retards = tuple(m for m, etat in zip(mois, etats) if etat == "retard")
        if not retards:
            continue
        terme = (
            tenant.rent + (tenant.charges or Decimal("0"))
            if tenant.rent is not None
            else None
        )
        relances.append(Relance(tenant=tenant, months=retards, monthly_amount=terme))

    print(f"Retards sur {month_year(debut)} - {month_year(fin)}\n")
    if not relances:
        print("Aucun retard : personne a relancer.")
        return 0

    if args.envoyer and len(relances) > 1:
        noms = ", ".join(r.tenant.full_name for r in relances)
        if not _confirm(f"Relancer {len(relances)} locataires ({noms}) ?"):
            raise CliError("Envoi annule.")

    erreurs = 0
    for relance in relances:
        destinataires = ", ".join(relance.tenant.emails) or "(aucune adresse)"
        total = f" - {format_amount(relance.total)}" if relance.total else ""
        print(f"{relance.tenant.full_name} <{destinataires}>{total}")
        print(printable(f"  Objet : {relance.email_subject}"))
        if not args.envoyer:
            texte, _ = relance.email_body(config.landlord.first_name)
            for ligne in texte.splitlines():
                print(printable(f"  | {ligne}") if ligne else "  |")
            print("  Email non envoye (ajoutez --envoyer)\n")
            continue
        try:
            _deliver(
                config,
                relance.tenant,
                relance.email_subject,
                relance.email_body(config.landlord.first_name),
                attachment=None,
            )
        except MailError as exc:
            erreurs += 1
            print(f"  ECHEC de l'envoi : {exc}", file=sys.stderr)
        print()
    return 1 if erreurs else 0


def cmd_ajustements(config: Config, args: argparse.Namespace) -> int:
    """Journal des ecarts au bail, du plus recent au plus ancien."""
    ajustements = args.ajustements
    if args.locataire or args.maison or args.tous:
        cibles = {t.key for t in select_tenants(config, args)}
        entrees = [a for a in ajustements.tous() if a.tenant_key in cibles]
    else:
        entrees = ajustements.tous()

    source = ajustements.source or "ajustements.yaml"
    print(f"Ajustements mensuels - {source}\n")
    if not entrees:
        print("Aucun ajustement enregistre : tout le monde est au tarif du bail.")
        return 0

    largeur_nom = max(
        len(config.tenant(a.tenant_key).short_name) for a in entrees
    )
    for ajustement in entrees:
        tenant = config.tenant(ajustement.tenant_key)
        terme = terme_du_mois(tenant, ajustement.period, ajustements)
        total = f"  ({format_amount(terme)} au total)" if terme is not None else ""
        print(
            printable(
                f"{ajustement.period:%Y-%m}  "
                f"{tenant.short_name.ljust(largeur_nom)}  "
                f"{ajustement.resume()}{total}"
            )
        )
        if ajustement.motif:
            print(printable(f"{' ' * 10}{ajustement.motif}"))
    print(f"\n{len(entrees)} ajustement{'s' if len(entrees) > 1 else ''}")
    return 0


def cmd_caution(config: Config, args: argparse.Namespace) -> int:
    """Recu de depot de garantie : production, envoi, et suivi avec --suivi.

    Le depot vaut deux mois de loyer hors charges. Le recu sort dans « Docs »,
    comme l'attestation de domicile : ce n'est pas une piece mensuelle.
    """
    racine = Path(args.dossier) if args.dossier else None
    tenants = (
        select_tenants(config, args)
        if (args.locataire or args.maison or args.tous)
        else list(config.tenants.values())
    )

    if args.suivi:
        return _suivi_caution(tenants, racine)

    if not (args.locataire or args.maison or args.tous):
        raise CliError(
            "Precisez --locataire NOM, --maison CLE ou --tous "
            "(ou --suivi pour l'etat des lieux)."
        )

    emise_le = parse_date(args.date) if args.date else date.today()
    erreurs = 0
    for tenant in tenants:
        recu_le = parse_date(args.recu_le) if args.recu_le else tenant.lease_start
        if recu_le is None:
            erreurs += 1
            print(
                f"{tenant.full_name} : date de versement inconnue. Passez "
                f"--recu-le, ou renseignez « lease_start » dans config.yaml "
                f"(tenants.{tenant.key}).",
                file=sys.stderr,
            )
            continue
        try:
            montant = args.montant or DepotGarantie.montant_attendu(tenant)
            depot = DepotGarantie(
                tenant=tenant, amount=montant, received_on=recu_le,
                issued_on=emise_le,
                first_month=tenant.lease_start or recu_le,
            )
        except DocumentError as exc:
            erreurs += 1
            print(f"{tenant.full_name} : {exc}", file=sys.stderr)
            continue

        chemin = depot.output_path(racine)
        print(f"{tenant.full_name} - {depot.amount_label} - {chemin}")

        if chemin.exists() and not args.forcer:
            print("  PDF deja present (utilisez --forcer pour regenerer)")
        else:
            render_depot_garantie(depot, config, chemin)
            print("  PDF genere")

        if args.envoyer:
            try:
                _deliver(
                    config, tenant, depot.email_subject,
                    depot.email_body(config.landlord.first_name), chemin,
                )
            except MailError as exc:
                erreurs += 1
                print(f"  ECHEC de l'envoi : {exc}", file=sys.stderr)
        else:
            print("  Email non envoye (ajoutez --envoyer)")
    return 1 if erreurs else 0


def _suivi_caution(tenants: list[Tenant], racine: Path | None) -> int:
    """Qui a un recu de depot dans « Docs », qui n'en a pas."""
    recu, manquant, _ = markers()
    lignes = [(t, fichiers_depot_garantie(t, racine)) for t in tenants]
    if not lignes:
        print("Aucun locataire a afficher.")
        return 0

    print("Recus de depot de garantie presents dans « Docs »\n")
    largeur = max(len(ligne[0].short_name) for ligne in lignes)
    print(f"{'LOCATAIRE'.ljust(largeur)}  {'MAISON'.ljust(7)}  REÇU   ATTENDU   FICHIER")
    absents = 0
    for tenant, fichiers in lignes:
        try:
            attendu = format_amount(DepotGarantie.montant_attendu(tenant))
        except DocumentError:
            attendu = "-"
        if fichiers:
            detail = fichiers[0].name
        else:
            detail = "-"
            absents += 1
        print(
            f"{tenant.short_name.ljust(largeur)}  "
            f"{tenant.property.key.ljust(7)}  "
            f"{(recu if fichiers else manquant).center(5)}  "
            f"{attendu.rjust(9)}   {detail}"
        )
    presents = len(lignes) - absents
    print(
        f"\n{presents} reçu{'s' if presents > 1 else ''}, "
        f"{absents} manquant{'s' if absents > 1 else ''}"
    )
    return 0


def cmd_assurance(config: Config, args: argparse.Namespace) -> int:
    """Qui a depose son attestation d'assurance dans « Docs », qui ne l'a pas.

    Aucune date d'echeance n'est suivie : le critere est la seule presence d'un
    fichier contenant « assurance ». Avec --relancer, ceux qui n'en ont pas
    recoivent un rappel.
    """
    racine = Path(args.dossier) if args.dossier else None
    tenants = (
        select_tenants(config, args)
        if (args.locataire or args.maison or args.tous)
        else list(config.tenants.values())
    )
    recue, manquante, _ = markers()

    lignes = [(tenant, fichiers_assurance(tenant, racine)) for tenant in tenants]
    absents = [tenant for tenant, fichiers in lignes if not fichiers]

    if args.relancer:
        return _relancer_assurance(config, absents, args)

    print("Attestations d'assurance deposees dans « Docs »\n")
    if not lignes:
        print("Aucun locataire a afficher.")
        return 0

    largeur = max(len(ligne[0].short_name) for ligne in lignes)
    print(f"{'LOCATAIRE'.ljust(largeur)}  {'MAISON'.ljust(7)}  REÇUE  FICHIER")
    for tenant, fichiers in lignes:
        if fichiers:
            recent = fichiers[0]
            depose = date.fromtimestamp(recent.stat().st_mtime)
            detail = f"{recent.name}  ({depose:%d/%m/%Y})"
            if len(fichiers) > 1:
                detail += f"  +{len(fichiers) - 1}"
        else:
            detail = "-"
        print(
            f"{tenant.short_name.ljust(largeur)}  "
            f"{tenant.property.key.ljust(7)}  "
            f"{(recue if fichiers else manquante).center(5)}  {detail}"
        )

    print(
        f"\n{len(lignes) - len(absents)} reçues, {len(absents)} manquantes"
        + (" (--relancer pour les rappeler)" if absents else "")
    )
    return 0


def _relancer_assurance(
    config: Config, absents: list[Tenant], args: argparse.Namespace
) -> int:
    if not absents:
        print("Toutes les attestations sont deposees : personne a relancer.")
        return 0

    if args.envoyer and len(absents) > 1:
        noms = ", ".join(t.full_name for t in absents)
        if not _confirm(f"Relancer {len(absents)} locataires ({noms}) ?"):
            raise CliError("Envoi annule.")

    erreurs = 0
    for tenant in absents:
        relance = RelanceAssurance(tenant=tenant)
        destinataires = ", ".join(tenant.emails) or "(aucune adresse)"
        print(f"{tenant.full_name} <{destinataires}>")
        print(printable(f"  Objet : {relance.email_subject}"))
        if not args.envoyer:
            texte, _ = relance.email_body(config.landlord.first_name)
            for ligne in texte.splitlines():
                print(printable(f"  | {ligne}") if ligne else "  |")
            print("  Email non envoye (ajoutez --envoyer)\n")
            continue
        try:
            _deliver(
                config, tenant, relance.email_subject,
                relance.email_body(config.landlord.first_name),
            )
        except MailError as exc:
            erreurs += 1
            print(f"  ECHEC de l'envoi : {exc}", file=sys.stderr)
        print()
    return 1 if erreurs else 0


def cmd_domicile(config: Config, args: argparse.Namespace) -> int:
    """Attestation de domicile : justificatif remis au locataire pour un tiers.

    Le document part dans « Docs » et non « Quittances » : ce n'est pas une
    piece comptable mensuelle mais un justificatif ponctuel.
    """
    emise_le = parse_date(args.date) if args.date else date.today()
    tenants = select_tenants(config, args)
    racine = Path(args.dossier) if args.dossier else None

    erreurs = 0
    for tenant in tenants:
        debut = (
            parse_date(args.depuis) if args.depuis else tenant.lease_start
        )
        if debut is None:
            erreurs += 1
            print(
                f"{tenant.full_name} : date d'entrée dans les lieux inconnue. "
                f"Renseignez « lease_start » dans config.yaml "
                f"(tenants.{tenant.key}) ou passez --depuis.",
                file=sys.stderr,
            )
            continue

        attestation = AttestationDomicile(
            tenant=tenant, lease_start=debut, issued_on=emise_le,
            motif=args.motif,
        )
        chemin = attestation.output_path(racine)
        print(f"{tenant.full_name} - {chemin}")

        if chemin.exists() and not args.forcer:
            print("  PDF deja present (utilisez --forcer pour regenerer)")
        else:
            render_attestation_domicile(attestation, config, chemin)
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
    parser.add_argument("--ajustements", metavar="CHEMIN", dest="ajustements_path",
                        help="chemin d'ajustements.yaml")
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

    p_relance = sous.add_parser(
        "relance", help="rappelle les locataires dont un mois echu est impaye")
    p_relance.add_argument("--locataire", action="append", metavar="CLE")
    p_relance.add_argument("--tous", action="store_true")
    p_relance.add_argument("--maison", metavar="CLE")
    p_relance.add_argument("--depuis", metavar="AAAA-MM",
                           help="defaut : janvier de l'annee en cours")
    p_relance.add_argument("--jusqu-a", metavar="AAAA-MM", dest="jusqu_a")
    p_relance.add_argument("--dossier", metavar="CHEMIN")
    p_relance.add_argument("--envoyer", action="store_true",
                           help="envoie les rappels (sinon, simple apercu)")
    p_relance.set_defaults(handler=cmd_relance)

    p_ajustements = sous.add_parser(
        "ajustements", help="journal des ecarts au bail, mois par mois")
    p_ajustements.add_argument("--locataire", action="append", metavar="CLE")
    p_ajustements.add_argument("--tous", action="store_true")
    p_ajustements.add_argument("--maison", metavar="CLE")
    p_ajustements.set_defaults(handler=cmd_ajustements)

    p_caution = sous.add_parser(
        "caution", help="recu de depot de garantie, et son suivi")
    _add_common_arguments(p_caution)
    p_caution.add_argument("--suivi", action="store_true",
                           help="affiche qui a un recu, sans rien produire")
    p_caution.add_argument("--recu-le", metavar="DATE", dest="recu_le",
                           help="date du versement ; defaut : « lease_start »")
    p_caution.add_argument("--montant", type=_amount, metavar="MONTANT",
                           help="defaut : deux mois de loyer hors charges")
    p_caution.set_defaults(handler=cmd_caution)

    p_assurance = sous.add_parser(
        "assurance", help="qui a depose son attestation d'assurance")
    p_assurance.add_argument("--locataire", action="append", metavar="CLE")
    p_assurance.add_argument("--tous", action="store_true")
    p_assurance.add_argument("--maison", metavar="CLE")
    p_assurance.add_argument("--dossier", metavar="CHEMIN")
    p_assurance.add_argument("--relancer", action="store_true",
                             help="rappelle ceux qui n'ont rien depose")
    p_assurance.add_argument("--envoyer", action="store_true",
                             help="envoie les rappels (avec --relancer)")
    p_assurance.set_defaults(handler=cmd_assurance)

    p_domicile = sous.add_parser(
        "domicile", help="genere une attestation de domicile")
    _add_common_arguments(p_domicile)
    p_domicile.add_argument("--depuis", metavar="DATE",
                            help="entree dans les lieux ; defaut : "
                                 "« lease_start » du locataire")
    p_domicile.add_argument("--motif", metavar="TEXTE",
                            help="usage prevu, ex. « une demande de carte de "
                                 "transport auprès du réseau Transvilles »")
    p_domicile.set_defaults(handler=cmd_domicile)

    p_attestation = sous.add_parser("attestation", help="genere une attestation")
    _add_common_arguments(p_attestation)
    p_attestation.add_argument("--depuis", required=True, metavar="DATE",
                               help="date de debut d'hebergement")
    p_attestation.set_defaults(handler=cmd_attestation)

    return parser


COMMANDES = (
    "quittance", "attestation", "domicile", "locataires", "suivi", "relance",
    "assurance", "caution", "ajustements",
)


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
        args.ajustements = Ajustements.load(
            getattr(args, "ajustements_path", None),
            config.tenants,
            base_dir=config.source.parent,
        )
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
