"""Lecture des factures d'electricite TotalEnergies.

Une facture couvre deux periodes distinctes, decalees d'un mois :

* l'**abonnement** est facture d'avance — du 29/08 au 28/09 ;
* la **consommation** est relevee a terme echu — du 29/07 au 28/08.

Un mois calendaire est donc couvert par deux factures, et chaque poste doit
etre proratise sur sa propre periode. C'est la raison d'etre de ce module.

Les montants extraits sont **confrontes aux totaux imprimes** sur la facture.
Une extraction fausse doit echouer bruyamment : elle alimente une repartition
de charges, et un poste manque passerait autrement inapercu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Categories : un locataire absent supporte les charges fixes (l'abonnement
# reste du, le compteur reste ouvert) mais pas la consommation.
FIXE = "fixe"
VARIABLE = "variable"


class FactureError(Exception):
    """Facture illisible, ou dont les postes ne reconstituent pas le total."""


@dataclass(frozen=True)
class Poste:
    libelle: str
    categorie: str
    montant_ht: Decimal
    debut: date
    fin: date

    @property
    def jours(self) -> int:
        """Bornes incluses : du 29/07 au 28/08 fait 31 jours."""
        return (self.fin - self.debut).days + 1


@dataclass(frozen=True)
class Facture:
    fichier: Path
    postes: tuple[Poste, ...]
    total_ht: Decimal
    tva: Decimal
    total_ttc: Decimal

    @property
    def taux_tva(self) -> Decimal:
        if not self.total_ht:
            return Decimal("0")
        return self.tva / self.total_ht

    @property
    def periode(self) -> tuple[date, date]:
        return (
            min(p.debut for p in self.postes),
            max(p.fin for p in self.postes),
        )


def _montant(texte: str) -> Decimal:
    """« 1 234,56 € » -> Decimal('1234.56'), signe compris."""
    nettoye = (
        texte.replace(" ", "").replace(" ", "").replace(" ", "")
        .replace("€", "").replace(",", ".")
    )
    return Decimal(nettoye)


def _date(texte: str) -> date:
    """Accepte « 29/08/2026 » comme « 29/08/26 »."""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texte, fmt).date()
        except ValueError:
            continue
    raise FactureError(f"Date illisible : {texte!r}")


# Un montant en fin de ligne : « ... 19,99 € » ou « ... -1,67 € ».
_FIN_MONTANT = re.compile(r"(-?[\d    ]+,\d{2})\s*€\s*$")
_PERIODE = re.compile(r"du (\d{2}/\d{2}/\d{2,4}) au (\d{2}/\d{2}/\d{2,4})")


def _montant_de_ligne(ligne: str) -> Decimal | None:
    trouve = _FIN_MONTANT.search(ligne)
    return _montant(trouve.group(1)) if trouve else None


def _periode_de_ligne(ligne: str) -> tuple[date, date] | None:
    trouve = _PERIODE.search(ligne)
    if not trouve:
        return None
    return _date(trouve.group(1)), _date(trouve.group(2))


# Intitules qui ouvrent une section du detail. Servent de butoir : une periode
# lue au-dela appartient deja au poste suivant.
SECTIONS = (
    "Abonnement d'électricité",
    "Consommation d'électricité",
    "Offres promotionnelles",
    "Services, prestations",
    "Taxes locales",
    "Contributions et taxes",
    "TVA (",
    "TOTAL TTC",
)


def _periode_de_section(detail: list[str], depart: int) -> tuple[date, date] | None:
    """Periode couverte par une section, sous-periodes comprises.

    Les factures d'avant mars 2026 detaillent la consommation en plusieurs
    tranches — « du 29/01/25 au 31/01/25 » puis « du 01/02/25 au 28/02/25 »
    quand un tarif change en cours de mois. Ne retenir que la premiere
    amputait la periode de consommation et faussait le prorata mensuel.
    """
    bornes: list[tuple[date, date]] = []
    for ligne in detail[depart + 1:]:
        if any(ligne.startswith(section) for section in SECTIONS):
            break
        trouve = _periode_de_ligne(ligne)
        if trouve:
            bornes.append(trouve)
    if not bornes:
        return None
    return min(d for d, _ in bornes), max(f for _, f in bornes)


def lire_facture(chemin: Path) -> Facture:
    """Extrait les postes d'une facture d'electricite TotalEnergies."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependance optionnelle
        raise FactureError(
            "La lecture des factures demande pypdf : "
            'python -m pip install -e ".[dev]"'
        ) from exc

    chemin = Path(chemin)
    texte = "\n".join(page.extract_text() or "" for page in PdfReader(str(chemin)).pages)
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]

    debut_detail = next(
        (i for i, l in enumerate(lignes) if "Détail de ma facture" in l), None
    )
    if debut_detail is None:
        raise FactureError(
            f"{chemin.name} : section « Détail de ma facture » introuvable. "
            "Cette facture n'est pas au format TotalEnergies attendu."
        )
    detail = lignes[debut_detail:]

    def _trouver(motif: str) -> tuple[int, str]:
        for i, ligne in enumerate(detail):
            if ligne.startswith(motif):
                return i, ligne
        raise FactureError(f"{chemin.name} : ligne « {motif} » introuvable.")

    def _trouver_un(motifs: tuple[str, ...]) -> tuple[int, str]:
        """Premier intitule present parmi plusieurs variantes de mise en page."""
        for i, ligne in enumerate(detail):
            if any(ligne.startswith(motif) for motif in motifs):
                return i, ligne
        attendus = " » ou « ".join(motifs)
        raise FactureError(f"{chemin.name} : ligne « {attendus} » introuvable.")

    postes: list[Poste] = []

    # Abonnement : son montant est sur l'intitule, sa periode sur la suivante.
    i, ligne = _trouver("Abonnement d'électricité")
    montant_abo = _montant_de_ligne(ligne)
    periode_abo = _periode_de_section(detail, i)
    if montant_abo is None or periode_abo is None:
        raise FactureError(f"{chemin.name} : abonnement illisible.")
    postes.append(Poste("Abonnement", FIXE, montant_abo, *periode_abo))

    # Consommation : periode relevee, decalee d'un mois par rapport a l'abonnement.
    i, ligne = _trouver("Consommation d'électricité")
    montant_conso = _montant_de_ligne(ligne)
    periode_conso = _periode_de_section(detail, i)
    if montant_conso is None or periode_conso is None:
        raise FactureError(f"{chemin.name} : consommation illisible.")
    postes.append(Poste("Consommation", VARIABLE, montant_conso, *periode_conso))

    # Postes facultatifs, rattaches a la periode de consommation faute de
    # periode propre lisible.
    for motif, libelle, categorie in (
        ("Offres promotionnelles", "Réductions", FIXE),
        ("Services, prestations", "Services", FIXE),
    ):
        ligne = next((l for l in detail if l.startswith(motif)), None)
        if ligne is None:
            continue
        montant = _montant_de_ligne(ligne)
        if montant is None:
            continue
        postes.append(Poste(libelle, categorie, montant, *periode_conso))

    # Taxes : l'accise suit la consommation, la CTA suit l'abonnement. Les
    # separer evite de faire payer de l'accise a un locataire absent.
    cta = next((l for l in detail if "Contribution Tarifaire d'Acheminement" in l), None)
    montant_cta = _montant_de_ligne(cta) if cta else None
    # « Taxes locales et contributions » avant mars 2026, « Contributions et
    # taxes » depuis. Le meme total, sous deux intitules.
    i, ligne = _trouver_un(("Contributions et taxes", "Taxes locales"))
    total_taxes = _montant_de_ligne(ligne)
    if total_taxes is None:
        # L'intitule tient sur deux lignes : le montant est sur la suivante.
        total_taxes = next(
            (m for m in (_montant_de_ligne(l) for l in detail[i + 1: i + 4]) if m),
            None,
        )
    if total_taxes is None:
        raise FactureError(f"{chemin.name} : contributions et taxes illisibles.")
    if montant_cta is not None:
        postes.append(Poste("CTA", FIXE, montant_cta, *periode_abo))
        postes.append(
            Poste("Accise", VARIABLE, total_taxes - montant_cta, *periode_conso)
        )
    else:
        postes.append(Poste("Taxes", VARIABLE, total_taxes, *periode_conso))

    _, ligne = _trouver("TVA (")
    tva = _montant_de_ligne(ligne)
    _, ligne = _trouver("TOTAL TTC")
    total_ttc = _montant_de_ligne(ligne)
    if tva is None or total_ttc is None:
        raise FactureError(f"{chemin.name} : TVA ou total TTC illisible.")

    total_ht = sum((p.montant_ht for p in postes), Decimal("0.00"))
    # Controle : les postes extraits doivent reconstituer le total imprime.
    if abs(total_ht + tva - total_ttc) > Decimal("0.02"):
        raise FactureError(
            f"{chemin.name} : les postes extraits totalisent "
            f"{total_ht + tva} € au lieu des {total_ttc} € imprimes. "
            "Le format de la facture a probablement change."
        )
    return Facture(
        fichier=chemin,
        postes=tuple(postes),
        total_ht=total_ht,
        tva=tva,
        total_ttc=total_ttc,
    )


def _mois_couverts(debut: date, fin: date) -> list[date]:
    mois, courant = [], debut.replace(day=1)
    while courant <= fin:
        mois.append(courant)
        courant = (courant.replace(day=28) + timedelta(days=4)).replace(day=1)
    return mois


def _fin_de_mois(mois: date) -> date:
    return (mois.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def prorata_mensuel(facture: Facture) -> dict[date, dict[str, Decimal]]:
    """Repartit les postes TTC sur les mois calendaires qu'ils recouvrent.

    Chaque poste est reparti au prorata du nombre de jours tombant dans chaque
    mois, puis majore de la TVA au taux de la facture. Le dernier mois absorbe
    l'ecart d'arrondi, pour que la somme rendue egale exactement le montant du
    poste.
    """
    resultat: dict[date, dict[str, Decimal]] = {}
    taux = Decimal("1") + facture.taux_tva

    for poste in facture.postes:
        ttc = (poste.montant_ht * taux).quantize(Decimal("0.01"))
        mois = _mois_couverts(poste.debut, poste.fin)
        repartis: list[tuple[date, Decimal]] = []
        cumul = Decimal("0.00")
        for index, m in enumerate(mois):
            debut = max(poste.debut, m)
            fin = min(poste.fin, _fin_de_mois(m))
            jours = (fin - debut).days + 1
            if index == len(mois) - 1:
                part = ttc - cumul
            else:
                part = (ttc * jours / poste.jours).quantize(Decimal("0.01"))
                cumul += part
            repartis.append((m, part))
        for m, part in repartis:
            resultat.setdefault(m, {})
            resultat[m][poste.libelle] = resultat[m].get(
                poste.libelle, Decimal("0.00")
            ) + part
    return dict(sorted(resultat.items()))


def categories(facture: Facture) -> dict[str, str]:
    """Libelle -> categorie, pour distinguer fixe et variable en aval."""
    return {p.libelle: p.categorie for p in facture.postes}


def mois_complets(factures: list[Facture]) -> dict[date, bool]:
    """Un mois est complet quand chaque categorie le couvre de bout en bout.

    L'abonnement et la consommation etant decales, un mois n'est entierement
    documente que si les deux factures qui l'encadrent sont presentes. Sans ce
    controle, un mois a demi couvert serait inscrit sous-evalue.
    """
    couverture: dict[date, dict[str, set[date]]] = {}
    for facture in factures:
        for poste in facture.postes:
            jour = poste.debut
            while jour <= poste.fin:
                mois = jour.replace(day=1)
                couverture.setdefault(mois, {FIXE: set(), VARIABLE: set()})
                couverture[mois][poste.categorie].add(jour)
                jour += timedelta(days=1)

    complets: dict[date, bool] = {}
    for mois, par_categorie in couverture.items():
        attendus = (_fin_de_mois(mois) - mois).days + 1
        complets[mois] = all(
            len(jours) == attendus for jours in par_categorie.values()
        )
    return dict(sorted(complets.items()))
