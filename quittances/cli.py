"""Interface en ligne de commande.

    python -m quittances locataires
    python -m quittances quittance --locataire Jin --periode 2025-09
    python -m quittances quittance --tous --bien anzin --periode 2025-09 --envoyer
    python -m quittances attestation --locataire Jin --depuis 2025-09-01

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
from .documents import Attestation, DocumentError, Quittance
from .formatting import format_amount, parse_amount
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


def parse_period(value: str) -> date:
    """« 2025-09 » -> premier jour du mois."""
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
    if args.tous:
        tenants = list(config.tenants.values())
        if args.bien:
            tenants = [t for t in tenants if t.property.key == args.bien]
            if not tenants:
                connus = ", ".join(sorted(config.properties))
                raise CliError(
                    f"Aucun locataire pour le bien « {args.bien} ». Biens : {connus}."
                )
        return tenants
    if not args.locataire:
        raise CliError("Precisez --locataire NOM (ou --tous).")
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
    print(f"{'CLE'.ljust(largeur)}  {'NOM'.ljust(28)}  {'BIEN'.ljust(8)}  LOYER")
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


def cmd_quittance(config: Config, args: argparse.Namespace) -> int:
    periode = parse_period(args.periode)
    date_paiement = parse_date(args.date_paiement) if args.date_paiement else periode
    emise_le = parse_date(args.date) if args.date else date.today()
    tenants = select_tenants(config, args)
    racine = Path(args.dossier) if args.dossier else None

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
    parser.add_argument("--bien", metavar="CLE",
                        help="restreint --tous a un bien")
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
    p_quittance.add_argument("--periode", required=True, metavar="AAAA-MM")
    p_quittance.add_argument("--date-paiement", metavar="DATE",
                             help="defaut : premier jour de la periode")
    p_quittance.add_argument("--loyer", type=_amount, metavar="MONTANT")
    p_quittance.add_argument("--charges", type=_amount, metavar="MONTANT")
    p_quittance.set_defaults(handler=cmd_quittance)

    p_attestation = sous.add_parser("attestation", help="genere une attestation")
    _add_common_arguments(p_attestation)
    p_attestation.add_argument("--depuis", required=True, metavar="DATE",
                               help="date de debut d'hebergement")
    p_attestation.set_defaults(handler=cmd_attestation)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
