"""Modeles metier : une quittance de loyer, une attestation d'hebergement.

Ces objets ne connaissent ni le PDF ni l'email : ils portent les donnees, les
calculs et les chemins de sortie.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from .config import Tenant
from .formatting import format_amount, format_date, month_year


class DocumentError(Exception):
    """Donnees insuffisantes ou incoherentes pour produire un document."""


def quittance_filename(tenant: Tenant, period: date) -> str:
    """Nom du fichier attendu pour un locataire et un mois donnes."""
    return (
        f"Quittance_de_loyer_{tenant.first_name}_"
        f"{tenant.last_name.upper().replace(' ', '_')}_"
        f"{period.strftime('%Y-%m')}.pdf"
    )


def quittance_path(tenant: Tenant, period: date, root: Path | None = None) -> Path:
    """Chemin attendu, calculable sans construire de quittance complete.

    Le suivi des paiements s'en sert pour tester l'existence d'un document sans
    connaitre les montants.
    """
    base = Path(root) if root is not None else tenant.property.folder
    return base / tenant.slug / "Quittances" / quittance_filename(tenant, period)


@dataclass(frozen=True)
class Quittance:
    tenant: Tenant
    period: date
    payment_date: date
    rent: Decimal
    charges: Decimal
    issued_on: date

    def __post_init__(self) -> None:
        if self.rent < 0 or self.charges < 0:
            raise DocumentError("Le loyer et les charges ne peuvent pas etre negatifs.")

    @property
    def total(self) -> Decimal:
        """Somme exacte : Decimal, pas de flottant (l'ancien JS affichait « 400 »)."""
        return (self.rent + self.charges).quantize(Decimal("0.01"))

    @property
    def period_key(self) -> str:
        """« 2025-09 », utilise dans le nom de fichier."""
        return self.period.strftime("%Y-%m")

    @property
    def period_label(self) -> str:
        """« septembre 2025 », utilise dans le corps du document."""
        return month_year(self.period)

    @property
    def rent_label(self) -> str:
        return format_amount(self.rent)

    @property
    def charges_label(self) -> str:
        return format_amount(self.charges)

    @property
    def total_label(self) -> str:
        return format_amount(self.total)

    @property
    def payment_date_label(self) -> str:
        return format_date(self.payment_date)

    @property
    def issued_on_label(self) -> str:
        return format_date(self.issued_on)

    @property
    def filename(self) -> str:
        return quittance_filename(self.tenant, self.period)

    def output_path(self, root: Path | None = None) -> Path:
        """<dossier du bien>/<Prenom_Nom>/Quittances/<fichier>."""
        return quittance_path(self.tenant, self.period, root)

    @property
    def email_subject(self) -> str:
        return f"Quittance de loyer - {self.period_label}"

    def email_body(self, landlord_first_name: str) -> tuple[str, str]:
        """Renvoie (texte brut, HTML)."""
        prenom = self.tenant.first_name
        texte = (
            f"Bonjour {prenom},\n\n"
            f"ci-joint la quittance de loyer pour le mois de {self.period_label}.\n\n"
            f"Bien a toi,\n{landlord_first_name}"
        )
        html = (
            f"Bonjour {prenom},<br/><br/>"
            f"ci-joint la quittance de loyer pour le mois de "
            f"<b>{self.period_label}</b>.<br/><br/>"
            f"Bien à toi,<br/>{landlord_first_name}"
        )
        return texte, html


@dataclass(frozen=True)
class Attestation:
    """Attestation d'hebergement.

    L'ancienne version JS plantait (`generateFooter` inexistant) et affichait
    « undefined » : la date et le lieu de naissance de l'heberge n'existaient
    dans aucune configuration. Ils sont desormais obligatoires et valides ici.
    """

    tenant: Tenant
    hosted_since: date
    issued_on: date

    def __post_init__(self) -> None:
        manquants = [
            libelle
            for libelle, valeur in (
                ("birth_date", self.tenant.birth_date),
                ("birth_place", self.tenant.birth_place),
            )
            if not valeur
        ]
        if manquants:
            champs = " et ".join(f"« {champ} »" for champ in manquants)
            raise DocumentError(
                f"Attestation impossible pour {self.tenant.full_name} : "
                f"{champs} absent(s) de la configuration "
                f"(section tenants.{self.tenant.key} de config.yaml)."
            )

    @property
    def hosted_since_label(self) -> str:
        return format_date(self.hosted_since)

    @property
    def issued_on_label(self) -> str:
        return format_date(self.issued_on)

    @property
    def filename(self) -> str:
        return (
            f"Attestation_hebergement_{self.tenant.first_name}_"
            f"{self.tenant.last_name.upper().replace(' ', '_')}_"
            f"{self.issued_on.year}.pdf"
        )

    def output_path(self, root: Path | None = None) -> Path:
        """<dossier du bien>/<Prenom_Nom>/Docs/<fichier>."""
        base = Path(root) if root is not None else self.tenant.property.folder
        return base / self.tenant.slug / "Docs" / self.filename

    @property
    def email_subject(self) -> str:
        return f"Attestation d'hébergement - {self.issued_on.year}"

    def email_body(self, landlord_first_name: str) -> tuple[str, str]:
        prenom = self.tenant.first_name
        texte = (
            f"Bonjour {prenom},\n\n"
            f"ci-joint ton attestation d'hebergement.\n\n"
            f"Bien a toi,\n{landlord_first_name}"
        )
        html = (
            f"Bonjour {prenom},<br/><br/>"
            f"ci-joint ton attestation d'hébergement.<br/><br/>"
            f"Bien à toi,<br/>{landlord_first_name}"
        )
        return texte, html
