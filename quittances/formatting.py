"""Formatage francais (montants, dates, mois) sans dependre de la locale systeme.

`locale.setlocale(LC_TIME, "fr_FR")` n'est pas fiable sous Windows : les noms de
mois sont donc codes en dur.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

MOIS = (
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
)

MOIS_ACCENTUES = {
    "fevrier": "février",
    "aout": "août",
    "decembre": "décembre",
}


def month_name(month: int) -> str:
    """Nom francais du mois (1-12), accentue."""
    if not 1 <= month <= 12:
        raise ValueError(f"Mois invalide : {month}")
    nom = MOIS[month - 1]
    return MOIS_ACCENTUES.get(nom, nom)


def month_year(value: date) -> str:
    """« septembre 2025 »."""
    return f"{month_name(value.month)} {value.year}"


MOIS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def month_name_en(month: int) -> str:
    if not 1 <= month <= 12:
        raise ValueError(f"Mois invalide : {month}")
    return MOIS_EN[month - 1]


def month_year_en(value: date) -> str:
    """« September 2026 »."""
    return f"{month_name_en(value.month)} {value.year}"


def format_amount_en(value: Decimal) -> str:
    """« €1,234.50 » : conventions anglaises, pour la version traduite."""
    quantized = value.quantize(Decimal("0.01"))
    signe = "-" if quantized < 0 else ""
    return f"{signe}€{abs(quantized):,.2f}"


VOYELLES = "aàâeéèêiîoôuû"


def elision(libelle: str) -> str:
    """« de » ou « d'» selon l'initiale du libelle qui suit.

    Trois mois commencent par une voyelle : avril, aout et octobre. Sans
    elision, les documents affichaient « le mois de aout ».

    Renvoie la preposition seule, et non la chaine complete, pour que l'appelant
    puisse intercaler du balisage : « le mois d'<b>aout 2026</b> ».
    """
    return "d'" if libelle[:1].lower() in VOYELLES else "de "


def iter_months(debut: date, fin: date) -> list[date]:
    """Premiers jours de chaque mois de `debut` a `fin` inclus."""
    mois = []
    annee, numero = debut.year, debut.month
    while (annee, numero) <= (fin.year, fin.month):
        mois.append(date(annee, numero, 1))
        numero += 1
        if numero == 13:
            annee, numero = annee + 1, 1
    return mois


def format_date(value: date) -> str:
    """« 01/09/2025 »."""
    return value.strftime("%d/%m/%Y")


def format_amount(value: Decimal) -> str:
    """« 1 234,50 € » : separateur de milliers insecable, virgule decimale."""
    quantized = value.quantize(Decimal("0.01"))
    entier, _, decimales = f"{abs(quantized):.2f}".partition(".")
    groupes = []
    while len(entier) > 3:
        groupes.insert(0, entier[-3:])
        entier = entier[:-3]
    groupes.insert(0, entier)
    signe = "-" if quantized < 0 else ""
    # U+00A0 : espace insecable, comme le veut la typographie francaise.
    return f"{signe}{' '.join(groupes)},{decimales} €"


def parse_amount(value: object) -> Decimal:
    """Accepte 390, 390.0, "390.00" ou "390,00" et renvoie un Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool est un int en Python : on l'ecarte.
        raise ValueError(f"Montant invalide : {value!r}")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        nettoye = value.strip().replace(" ", "").replace(" ", "").replace(",", ".")
        nettoye = nettoye.removesuffix("€").strip()
        try:
            return Decimal(nettoye)
        except InvalidOperation as exc:
            raise ValueError(f"Montant invalide : {value!r}") from exc
    raise ValueError(f"Montant invalide : {value!r}")
