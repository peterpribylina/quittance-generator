"""Modeles metier : une quittance de loyer, une attestation d'hebergement.

Ces objets ne connaissent ni le PDF ni l'email : ils portent les donnees, les
calculs et les chemins de sortie.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import groupby
from decimal import Decimal
from pathlib import Path

from .config import Tenant
from .formatting import (
    elision,
    format_amount,
    format_date,
    month_name,
    month_year,
)


class DocumentError(Exception):
    """Donnees insuffisantes ou incoherentes pour produire un document."""


# Reformulation de la clause du bail : « Il est payable d'avance le 1er de
# chaque mois au BAILLEUR ». Rappelee dans les relances pour situer l'echeance.
ECHEANCE = (
    "Pour rappel, le bail prévoit que le loyer est payable d'avance, "
    "le 1er de chaque mois."
)


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
        preposition = elision(self.period_label)
        texte = (
            f"Bonjour {prenom},\n\n"
            f"ci-joint la quittance de loyer pour le mois "
            f"{preposition}{self.period_label}.\n\n"
            f"Bien a toi,\n{landlord_first_name}"
        )
        html = (
            f"Bonjour {prenom},<br/><br/>"
            f"ci-joint la quittance de loyer pour le mois "
            f"{preposition}<b>{self.period_label}</b>.<br/><br/>"
            f"Bien à toi,<br/>{landlord_first_name}"
        )
        return texte, html


@dataclass(frozen=True)
class Relance:
    """Rappel amiable pour un ou plusieurs mois echus sans quittance.

    Ne porte aucun document : la relance est un simple email. Le montant est
    facultatif, un locataire sans loyer configure etant relance sans chiffre
    plutot que pas du tout.
    """

    tenant: Tenant
    months: tuple[date, ...]
    monthly_amount: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.months:
            raise DocumentError(
                f"Aucun mois en retard pour {self.tenant.full_name} : "
                "rien a relancer."
            )

    @property
    def total(self) -> Decimal | None:
        if self.monthly_amount is None:
            return None
        return (self.monthly_amount * len(self.months)).quantize(Decimal("0.01"))

    @property
    def months_label(self) -> str:
        """« juillet, août et septembre 2026 » : l'annee n'est ecrite qu'une
        fois par groupe, pas apres chaque mois."""
        groupes = []
        for annee, mois in groupby(self.months, key=lambda m: m.year):
            noms = [month_name(m.month) for m in mois]
            if len(noms) == 1:
                groupes.append(f"{noms[0]} {annee}")
            else:
                groupes.append(f"{', '.join(noms[:-1])} et {noms[-1]} {annee}")
        return ", ".join(groupes)

    @property
    def email_subject(self) -> str:
        if len(self.months) == 1:
            libelle = month_year(self.months[0])
            return f"Rappel : loyer {elision(libelle)}{libelle}"
        return f"Rappel : {len(self.months)} loyers en attente"

    def email_body(self, landlord_first_name: str) -> tuple[str, str]:
        prenom = self.tenant.first_name
        # L'elision porte sur le premier mois cite : « aux mois d'aout et... ».
        pluriel = "aux mois " if len(self.months) > 1 else "au mois "
        article = pluriel + elision(self.months_label)
        montant_txt = (
            f" Le montant total dû est de {format_amount(self.total)}."
            if self.total is not None
            else ""
        )
        texte = (
            f"Bonjour {prenom},\n\n"
            f"sauf erreur de ma part, je n'ai pas encore reçu le loyer "
            f"correspondant {article}{self.months_label}."
            f"{montant_txt}\n\n"
            f"{ECHEANCE}\n\n"
            "Si le règlement est déjà parti, merci de ne pas tenir compte de ce "
            "message. Dans le cas contraire, peux-tu me dire où en est le "
            "versement ?\n\n"
            f"Bien à toi,\n{landlord_first_name}"
        )
        montant_html = (
            f" Le montant total dû est de <b>{format_amount(self.total)}</b>."
            if self.total is not None
            else ""
        )
        html = (
            f"Bonjour {prenom},<br/><br/>"
            f"sauf erreur de ma part, je n'ai pas encore reçu le loyer "
            f"correspondant {article}<b>{self.months_label}</b>."
            f"{montant_html}<br/><br/>"
            f"{ECHEANCE}<br/><br/>"
            "Si le règlement est déjà parti, merci de ne pas tenir compte de ce "
            "message. Dans le cas contraire, peux-tu me dire où en est le "
            f"versement ?<br/><br/>"
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
