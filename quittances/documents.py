"""Modeles metier : une quittance de loyer, une attestation d'hebergement.

Ces objets ne connaissent ni le PDF ni l'email : ils portent les donnees, les
calculs et les chemins de sortie.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape
from datetime import date
import unicodedata
from itertools import groupby
from decimal import Decimal
from pathlib import Path

from . import emails
from .config import Tenant
from .formatting import (
    elision,
    format_amount,
    format_amount_en,
    format_date,
    format_date_en,
    montant_en_lettres,
    format_date_long,
    month_name,
    month_name_en,
    month_year,
    month_year_en,
)


class DocumentError(Exception):
    """Donnees insuffisantes ou incoherentes pour produire un document."""


# Reformulation de la clause du bail : « Il est payable d'avance le 1er de
# chaque mois au BAILLEUR ». Rappelee dans les relances pour situer l'echeance.
ECHEANCE = (
    "📅 Pour rappel, le bail prévoit que le loyer est payable d'avance, "
    "le 1er de chaque mois."
)
ECHEANCE_EN = (
    "📅 As a reminder, the lease provides that rent is payable in advance, "
    "on the 1st of each month."
)

# Une quittance sert de justificatif de domicile et de ressources : le locataire
# a interet a la garder, il la redemande souvent des mois plus tard.
CONSERVATION = (
    "📎 La quittance est en pièce jointe. Garde-la : elle sert de justificatif "
    "de domicile, et te sera demandée pour la CAF, un dossier de garant ou une "
    "déclaration d'impôts."
)
CONSERVATION_EN = (
    "📎 The receipt is attached. Keep it: it serves as proof of address, and "
    "you will be asked for it by the CAF, a guarantor application or a tax "
    "return."
)

# L'assurance des risques locatifs est une obligation legale du locataire
# (loi du 6 juillet 1989), dont l'attestation se fournit chaque annee.
OBLIGATION_ASSURANCE = (
    "📅 Le bail impose une assurance couvrant les risques locatifs, et "
    "l'attestation doit m'être remise chaque année."
)
OBLIGATION_ASSURANCE_EN = (
    "📅 The lease requires insurance covering tenant risks, and the "
    "certificate must be provided to me every year."
)
ASTUCE_ASSURANCE = (
    "💡 Astuce : ton assureur peut te l'envoyer en quelques minutes depuis ton "
    "espace client ou par téléphone."
)
ASTUCE_ASSURANCE_EN = (
    "💡 Tip: your insurer can usually send it within minutes from your online "
    "account or over the phone."
)

# Sort du depot de garantie, rappele au locataire au moment de l'encaissement :
# c'est la question qu'il pose invariablement a la sortie.
RESTITUTION_DEPOT = (
    "🔒 Ce dépôt est conservé pendant toute la durée de la location, puis "
    "restitué dans le mois qui suit l'état des lieux de sortie, déduction "
    "faite des éventuels impayés, excédents de consommation ou frais de "
    "remise en état."
)
CONSERVATION_DEPOT = (
    "📎 Garde ce reçu : c'est ta preuve du versement, et il te servira au "
    "moment de la restitution."
)

CONSERVATION_DOMICILE = (
    "📎 Le document est en pièce jointe, signé. Il est daté du jour : si on te "
    "le demande dans plusieurs mois, redemande-le-moi plutôt que de renvoyer "
    "celui-ci, beaucoup d'organismes exigent un justificatif récent."
)

# Suggestion pratique : la plupart des retards viennent d'un oubli, pas d'une
# difficulte de paiement.
ASTUCE = (
    "💡 Astuce : un virement programmé le 1er depuis ta banque évite d'y penser "
    "chaque mois."
)
ASTUCE_EN = (
    "💡 Tip: a standing order set for the 1st from your bank saves you having "
    "to think about it every month."
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
    # Motif de l'ajustement du mois, quand les montants s'ecartent du bail. Le
    # locataire doit comprendre pourquoi sa quittance change : la CLI y place
    # le texte du journal.
    note: str | None = None

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
    def period_label_en(self) -> str:
        """« September 2025 »."""
        return month_year_en(self.period)

    @property
    def email_subject(self) -> str:
        """Bilingue : la moitie des locataires ne lisent pas le francais."""
        return (
            f"Quittance de loyer - {self.period_label} / "
            f"Rent receipt: {self.period_label_en}"
        )

    def email_body(self, landlord_first_name: str) -> tuple[str, str]:
        """Renvoie (texte brut, HTML)."""
        prenom = self.tenant.first_name
        preposition = elision(self.period_label)
        detail = (
            f"{self.rent_label} de loyer + {self.charges_label} de charges"
            if self.charges
            else "loyer sans charges"
        )
        detail_en = (
            f"{format_amount_en(self.rent)} rent + "
            f"{format_amount_en(self.charges)} charges"
            if self.charges
            else "rent, no charges"
        )
        # La note est saisie a la main : elle vaut pour les deux langues, telle
        # quelle, et son balisage doit etre echappe.
        note_txt = f"{self.note}\n\n" if self.note else ""
        encart_note = (
            [emails.encart("ℹ️", escape(self.note))] if self.note else []
        )

        texte = (
            f"Bonjour {prenom},\n\n"
            f"ci-joint ta quittance de loyer pour le mois "
            f"{preposition}{self.period_label}, d'un montant de "
            f"{self.total_label} ({detail}), reçu le "
            f"{self.payment_date_label}.\n\n"
            f"{note_txt}"
            f"{CONSERVATION}\n\n"
            f"Bien à toi,\n{landlord_first_name}\n\n"
            f"{'-' * 40}\n\n"
            f"Hi {prenom},\n\n"
            f"please find attached your rent receipt for "
            f"{self.period_label_en}, for {format_amount_en(self.total)} "
            f"({detail_en}), received on "
            f"{format_date_en(self.payment_date)}.\n\n"
            f"{note_txt}"
            f"{CONSERVATION_EN}\n\n"
            f"Best,\n{landlord_first_name}"
        )

        conservation_fr = CONSERVATION.removeprefix("📎 ")
        conservation_en = CONSERVATION_EN.removeprefix("📎 ")
        html = emails.document([
            emails.entete("Quittance de loyer", self.period_label.capitalize()),
            emails.montant(
                "Montant réglé", self.total_label, detail, ton="succes"
            ),
            emails.paragraphe(
                f"Bonjour {prenom},<br/><br/>"
                f"ci-joint ta quittance de loyer pour le mois "
                f"{preposition}<b>{self.period_label}</b>, reçu le "
                f"<b>{self.payment_date_label}</b>."
            ),
            *encart_note,
            emails.encart("📎", conservation_fr),
            emails.signature(f"Bien à toi,<br/>{landlord_first_name}"),
            emails.separateur(),
            emails.langue("English"),
            emails.paragraphe(
                f"Hi {prenom},<br/><br/>"
                f"please find attached your rent receipt for "
                f"<b>{self.period_label_en}</b>, received on "
                f"<b>{format_date_en(self.payment_date)}</b>."
            ),
            *encart_note,
            emails.encart("📎", conservation_en),
            emails.signature(f"Best,<br/>{landlord_first_name}"),
        ])
        return texte, html


MOT_CLE_ASSURANCE = "assurance"


def docs_dir(tenant: Tenant, root: Path | None = None) -> Path:
    """<dossier du bien>/<Prenom_Nom>/Docs."""
    base = Path(root) if root is not None else tenant.property.folder
    return base / tenant.slug / "Docs"


def _sans_accent(texte: str) -> str:
    """« Reçu_dépôt » -> « recu_depot », pour comparer des noms de fichiers.

    Les documents deposes a la main ecrivent tantot « depot », tantot
    « dépôt » ; la recherche doit ignorer la difference.
    """
    decompose = unicodedata.normalize("NFD", texte.casefold())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def fichiers_docs(
    tenant: Tenant,
    *mots_cles: str,
    exclure: tuple[str, ...] = (),
    root: Path | None = None,
) -> list[Path]:
    """Fichiers de « Docs » dont le nom contient tous les mots-cles.

    Du plus recent au plus ancien. Accents et casse sont ignores, et
    l'extension n'entre pas en compte : les locataires deposent aussi bien un
    PDF qu'une photo.
    """
    dossier = docs_dir(tenant, root)
    if not dossier.is_dir():
        return []
    cherches = [_sans_accent(mot) for mot in mots_cles]
    ecartes = [_sans_accent(mot) for mot in exclure]
    trouves = []
    for fichier in dossier.iterdir():
        if not fichier.is_file():
            continue
        nom = _sans_accent(fichier.name)
        if all(mot in nom for mot in cherches) and not any(
            mot in nom for mot in ecartes
        ):
            trouves.append(fichier)
    return sorted(trouves, key=lambda f: f.stat().st_mtime, reverse=True)


def fichiers_assurance(tenant: Tenant, root: Path | None = None) -> list[Path]:
    """Attestations d'assurance deposees dans « Docs »."""
    return fichiers_docs(tenant, MOT_CLE_ASSURANCE, root=root)


def fichiers_depot_garantie(tenant: Tenant, root: Path | None = None) -> list[Path]:
    """Recus de depot de garantie presents dans « Docs ».

    « restitution » est ecarte : un recu de restitution solde le depot a la
    sortie du locataire, c'est l'inverse du recu d'encaissement.
    """
    return fichiers_docs(
        tenant, "depot", "garantie", exclure=("restitution",), root=root
    )


@dataclass(frozen=True)
class DepotGarantie:
    """Recu confirmant l'encaissement du depot de garantie.

    Le montant vaut deux mois de loyer **hors charges** : le depot ne couvre
    pas les provisions, qui se regularisent separement.

    Reste **en francais uniquement**, comme l'attestation de domicile : c'est
    une piece qui peut etre produite en justice.
    """

    tenant: Tenant
    amount: Decimal
    received_on: date
    issued_on: date
    # Mois d'entree : la clause de reservation le nomme explicitement.
    first_month: date

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise DocumentError("Le depot de garantie doit etre positif.")

    @staticmethod
    def montant_attendu(tenant: Tenant) -> Decimal:
        """Deux mois de loyer hors charges."""
        if tenant.rent is None:
            raise DocumentError(
                f"Loyer inconnu pour {tenant.full_name} : renseignez « rent » "
                f"dans config.yaml (tenants.{tenant.key}) ou passez --montant."
            )
        return (tenant.rent * 2).quantize(Decimal("0.01"))

    @property
    def amount_label(self) -> str:
        return format_amount(self.amount)

    @property
    def amount_words(self) -> str:
        """« six cent quatre-vingts euros », comme l'exige un recu."""
        return montant_en_lettres(self.amount)

    @property
    def received_on_label(self) -> str:
        return format_date(self.received_on)

    @property
    def issued_on_label(self) -> str:
        return format_date(self.issued_on)

    @property
    def first_month_label(self) -> str:
        return month_name(self.first_month.month)

    @property
    def filename(self) -> str:
        """Un seul recu par locataire : pas de date dans le nom."""
        return (
            f"Recu_depot_de_garantie_{self.tenant.first_name}_"
            f"{self.tenant.last_name.upper().replace(' ', '_')}.pdf"
        )

    def output_path(self, root: Path | None = None) -> Path:
        """<dossier du bien>/<Prenom_Nom>/Docs/<fichier>."""
        return docs_dir(self.tenant, root) / self.filename

    @property
    def email_subject(self) -> str:
        return "Reçu de dépôt de garantie"

    def email_body(self, landlord_first_name: str) -> tuple[str, str]:
        prenom = self.tenant.first_name
        texte = (
            f"Bonjour {prenom},\n\n"
            f"tu trouveras ci-joint le reçu du dépôt de garantie de "
            f"{self.amount_label} que tu m'as versé le "
            f"{self.received_on_label}, soit deux mois de loyer hors "
            f"charges.\n\n"
            f"{RESTITUTION_DEPOT}\n\n"
            f"{CONSERVATION_DEPOT}\n\n"
            f"Bien à toi,\n{landlord_first_name}"
        )
        html = emails.document([
            emails.entete("Reçu de dépôt de garantie", self.tenant.full_name),
            emails.montant(
                "Dépôt de garantie reçu",
                self.amount_label,
                f"deux mois de loyer hors charges, versés le "
                f"{self.received_on_label}",
                ton="succes",
            ),
            emails.paragraphe(
                f"Bonjour {prenom},<br/><br/>"
                f"tu trouveras ci-joint le reçu du dépôt de garantie que tu "
                f"m'as versé le <b>{self.received_on_label}</b>."
            ),
            emails.encart("🔒", RESTITUTION_DEPOT.removeprefix("🔒 ")),
            emails.encart("📎", CONSERVATION_DEPOT.removeprefix("📎 ")),
            emails.signature(f"Bien à toi,<br/>{landlord_first_name}"),
        ])
        return texte, html


@dataclass(frozen=True)
class RelanceAssurance:
    """Rappel demandant l'attestation d'assurance des risques locatifs.

    Bilingue : cette demande s'adresse au locataire, pas a une administration,
    et la moitie d'entre eux ne lisent pas le francais.
    """

    tenant: Tenant

    @property
    def email_subject(self) -> str:
        return (
            "Attestation d'assurance habitation / Home insurance certificate"
        )

    def email_body(self, landlord_first_name: str) -> tuple[str, str]:
        prenom = self.tenant.first_name
        # Pas d'elision ici : « pour une chambre », et non « pour d'une
        # chambre ». Elle ne vaut qu'apres « locataire ».
        logement = self.tenant.dwelling

        texte = (
            f"Bonjour {prenom},\n\n"
            f"je n'ai pas encore reçu ton attestation d'assurance habitation "
            f"(attestation de risques locatifs) pour {logement} au "
            f"{self.tenant.address}.\n\n"
            f"{OBLIGATION_ASSURANCE}\n\n"
            f"{ASTUCE_ASSURANCE}\n\n"
            "Peux-tu me la transmettre en réponse à ce message ? Un PDF ou une "
            "photo lisible suffit.\n\n"
            f"Bien à toi,\n{landlord_first_name}\n\n"
            f"{'-' * 40}\n\n"
            f"Hi {prenom},\n\n"
            f"I haven't received your home insurance certificate "
            f"(\"attestation de risques locatifs\") yet, for the property at "
            f"{self.tenant.address}.\n\n"
            f"{OBLIGATION_ASSURANCE_EN}\n\n"
            f"{ASTUCE_ASSURANCE_EN}\n\n"
            "Could you send it back in reply to this message? A PDF or a clear "
            "photo is enough.\n\n"
            f"Best,\n{landlord_first_name}"
        )

        html = emails.document([
            emails.entete("Document manquant", "Attestation de risques locatifs"),
            emails.paragraphe(
                f"Bonjour {prenom},<br/><br/>"
                f"je n'ai pas encore reçu ton attestation d'assurance "
                f"habitation (attestation de risques locatifs) pour "
                f"{logement} au <b>{self.tenant.address}</b>."
            ),
            emails.encart("📅", OBLIGATION_ASSURANCE.removeprefix("📅 ")),
            emails.encart("💡", ASTUCE_ASSURANCE.removeprefix("💡 ")),
            emails.paragraphe(
                "Peux-tu me la transmettre en réponse à ce message ? Un PDF ou "
                "une photo lisible suffit."
            ),
            emails.signature(f"Bien à toi,<br/>{landlord_first_name}"),
            emails.separateur(),
            emails.langue("English"),
            emails.paragraphe(
                f"Hi {prenom},<br/><br/>"
                f"I haven't received your home insurance certificate "
                f"(&laquo;&nbsp;attestation de risques locatifs&nbsp;&raquo;) "
                f"yet, for the property at <b>{self.tenant.address}</b>."
            ),
            emails.encart("📅", OBLIGATION_ASSURANCE_EN.removeprefix("📅 ")),
            emails.encart("💡", ASTUCE_ASSURANCE_EN.removeprefix("💡 ")),
            emails.paragraphe(
                "Could you send it back in reply to this message? A PDF or a "
                "clear photo is enough."
            ),
            emails.signature(f"Best,<br/>{landlord_first_name}"),
        ])
        return texte, html


@dataclass(frozen=True)
class AttestationDomicile:
    """Attestation de domicile : le bailleur atteste qu'untel est son locataire.

    A ne pas confondre avec `Attestation`, qui certifie un hebergement a titre
    gratuit chez le bailleur. Ici le locataire paie un loyer, et le document lui
    sert de justificatif de domicile aupres d'un tiers.

    Reste **en francais uniquement** : il s'adresse a une administration
    francaise, pas au locataire.
    """

    tenant: Tenant
    lease_start: date
    issued_on: date
    motif: str | None = None

    @property
    def lease_start_label(self) -> str:
        return format_date_long(self.lease_start)

    @property
    def issued_on_label(self) -> str:
        return format_date_long(self.issued_on)

    @property
    def objet(self) -> str:
        """Clause d'usage, completee du motif quand il est precise."""
        base = (
            "La présente attestation est délivrée à la demande de l'intéressé(e), "
            "pour servir et valoir ce que de droit"
        )
        if not self.motif:
            return f"{base}."
        return f"{base}, notamment dans le cadre {elision(self.motif)}{self.motif}."

    @property
    def filename(self) -> str:
        """Date complete dans le nom : une meme annee peut en compter plusieurs,
        delivrees pour des motifs differents."""
        return (
            f"Attestation_domicile_{self.tenant.first_name}_"
            f"{self.tenant.last_name.upper().replace(' ', '_')}_"
            f"{self.issued_on:%Y-%m-%d}.pdf"
        )

    def output_path(self, root: Path | None = None) -> Path:
        """<dossier du bien>/<Prenom_Nom>/Docs/<fichier>."""
        return docs_dir(self.tenant, root) / self.filename

    @property
    def email_subject(self) -> str:
        return "Attestation de domicile"

    def email_body(self, landlord_first_name: str) -> tuple[str, str]:
        prenom = self.tenant.first_name
        # « locataire d'une chambre », « locataire d'un logement ».
        logement = f"{elision(self.tenant.dwelling)}{self.tenant.dwelling}"
        texte = (
            f"Bonjour {prenom},\n\n"
            f"tu trouveras ci-joint ton attestation de domicile, signée, "
            f"attestant que tu es locataire {logement} au "
            f"{self.tenant.address} depuis le {self.lease_start_label}.\n\n"
            f"{CONSERVATION_DOMICILE}\n\n"
            f"Bien à toi,\n{landlord_first_name}"
        )
        note = CONSERVATION_DOMICILE.removeprefix("📎 ")
        html = emails.document([
            emails.entete("Attestation de domicile", self.tenant.full_name),
            emails.paragraphe(
                f"Bonjour {prenom},<br/><br/>"
                f"tu trouveras ci-joint ton attestation de domicile, signée, "
                f"attestant que tu es locataire {logement} au "
                f"<b>{self.tenant.address}</b> depuis le "
                f"<b>{self.lease_start_label}</b>."
            ),
            emails.encart("📎", note),
            emails.signature(f"Bien à toi,<br/>{landlord_first_name}"),
        ])
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
    def months_label_en(self) -> str:
        """« August and September 2026 », pendant anglais de months_label."""
        groupes = []
        for annee, mois in groupby(self.months, key=lambda m: m.year):
            noms = [month_name_en(m.month) for m in mois]
            if len(noms) == 1:
                groupes.append(f"{noms[0]} {annee}")
            else:
                groupes.append(f"{', '.join(noms[:-1])} and {noms[-1]} {annee}")
        return ", ".join(groupes)

    @property
    def email_subject(self) -> str:
        """Bilingue : la moitie des locataires ne lisent pas le francais."""
        if len(self.months) == 1:
            libelle = month_year(self.months[0])
            return (
                f"Rappel : loyer {elision(libelle)}{libelle} / "
                f"Rent reminder: {month_year_en(self.months[0])}"
            )
        return (
            f"Rappel : {len(self.months)} loyers en attente / "
            f"Rent reminder: {len(self.months)} months outstanding"
        )

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
        montant_en = (
            f" The total amount due is {format_amount_en(self.total)}."
            if self.total is not None
            else ""
        )
        pluriel_en = "months of" if len(self.months) > 1 else "month of"

        texte = (
            f"Bonjour {prenom},\n\n"
            f"sauf erreur de ma part, je n'ai pas encore reçu le loyer "
            f"correspondant {article}{self.months_label}."
            f"{montant_txt}\n\n"
            f"{ECHEANCE}\n\n"
            f"{ASTUCE}\n\n"
            "Si le règlement est déjà parti, merci de ne pas tenir compte de ce "
            "message. Dans le cas contraire, peux-tu me dire où en est le "
            "versement ?\n\n"
            f"Bien à toi,\n{landlord_first_name}\n\n"
            f"{'-' * 40}\n\n"
            f"Hi {prenom},\n\n"
            f"unless I'm mistaken, I haven't received the rent for the "
            f"{pluriel_en} {self.months_label_en} yet."
            f"{montant_en}\n\n"
            f"{ECHEANCE_EN}\n\n"
            f"{ASTUCE_EN}\n\n"
            "If the payment has already been sent, please disregard this "
            "message. Otherwise, could you let me know where it stands?\n\n"
            f"Best,\n{landlord_first_name}"
        )

        # Les emojis servent de puces dans les encarts : on les retire du texte
        # avant de le reinjecter dans le HTML, qui les place lui-meme.
        echeance_fr = ECHEANCE.removeprefix("📅 ")
        echeance_en = ECHEANCE_EN.removeprefix("📅 ")
        astuce_fr = ASTUCE.removeprefix("💡 ")
        astuce_en = ASTUCE_EN.removeprefix("💡 ")

        montant_html = (
            f"Le montant total dû est de <b>{format_amount(self.total)}</b>."
            if self.total is not None
            else ""
        )
        blocs = [
            emails.entete("Rappel de loyer", self.months_label.capitalize()),
        ]
        if self.total is not None:
            blocs.append(
                emails.montant(
                    "Montant dû",
                    format_amount(self.total),
                    f"{len(self.months)} mois" if len(self.months) > 1 else "",
                )
            )
        blocs += [
            emails.paragraphe(
                f"Bonjour {prenom},<br/><br/>"
                f"sauf erreur de ma part, je n'ai pas encore reçu le loyer "
                f"correspondant {article}<b>{self.months_label}</b>."
            ),
            emails.encart("📅", echeance_fr),
            emails.encart("💡", astuce_fr),
            emails.paragraphe(
                "Si le règlement est déjà parti, merci de ne pas tenir compte de "
                "ce message. Dans le cas contraire, peux-tu me dire où en est le "
                "versement ?"
            ),
            emails.signature(f"Bien à toi,<br/>{landlord_first_name}"),
            emails.separateur(),
            emails.langue("English"),
            emails.paragraphe(
                f"Hi {prenom},<br/><br/>"
                f"unless I'm mistaken, I haven't received the rent for the "
                f"{pluriel_en} <b>{self.months_label_en}</b> yet."
                + (
                    f" The total amount due is "
                    f"<b>{format_amount_en(self.total)}</b>."
                    if self.total is not None
                    else ""
                )
            ),
            emails.encart("📅", echeance_en),
            emails.encart("💡", astuce_en),
            emails.paragraphe(
                "If the payment has already been sent, please disregard this "
                "message. Otherwise, could you let me know where it stands?"
            ),
            emails.signature(f"Best,<br/>{landlord_first_name}"),
        ]
        html = emails.document(blocs)
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
        return docs_dir(self.tenant, root) / self.filename

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
