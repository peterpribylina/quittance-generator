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


UNITES = (
    "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit",
    "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
)
DIZAINES = {
    20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante",
    60: "soixante", 80: "quatre-vingt",
}


def _moins_de_cent(n: int) -> str:
    if n < 17:
        return UNITES[n]
    if n < 20:
        return f"dix-{UNITES[n - 10]}"
    # 70 et 90 se disent « soixante-dix » et « quatre-vingt-dix » : la dizaine
    # de base est celle du dessous, l'unite va jusqu'a 19.
    base = 60 if 70 <= n < 80 else 80 if n >= 80 else n // 10 * 10
    reste = n - base
    if reste == 0:
        return DIZAINES[base]
    if reste == 1 and base in (20, 30, 40, 50, 60):
        return f"{DIZAINES[base]} et un"
    if reste == 11 and base == 60:
        return "soixante et onze"
    return f"{DIZAINES[base]}-{_moins_de_cent(reste)}"


def _moins_de_mille(n: int) -> str:
    centaines, reste = divmod(n, 100)
    if centaines == 0:
        return _moins_de_cent(reste)
    # « cent » prend un s quand il est multiplie et termine le nombre.
    tete = "cent" if centaines == 1 else f"{UNITES[centaines]} cent"
    if reste == 0:
        return tete + ("s" if centaines > 1 else "")
    return f"{tete} {_moins_de_cent(reste)}"


def nombre_en_lettres(n: int) -> str:
    """« 680 » -> « six cent quatre-vingts ».

    Orthographe francaise standard : « quatre-vingts » et « deux cents »
    prennent un s seulement en fin de nombre, « mille » est invariable.
    """
    if n < 0:
        raise ValueError(f"Nombre negatif : {n}")
    if n >= 1_000_000:
        raise ValueError(f"Nombre trop grand : {n}")
    if n < 1000:
        mots = _moins_de_mille(n)
    else:
        milliers, reste = divmod(n, 1000)
        tete = "mille" if milliers == 1 else f"{_moins_de_mille(milliers)} mille"
        mots = tete if reste == 0 else f"{tete} {_moins_de_mille(reste)}"
    # « quatre-vingt » s'accorde en fin de nombre, jamais au milieu.
    if mots.endswith("quatre-vingt"):
        mots += "s"
    return mots


def montant_en_lettres(value: Decimal) -> str:
    """« 680,00 » -> « six cent quatre-vingts euros »."""
    quantized = value.quantize(Decimal("0.01"))
    euros, centimes = divmod(int(quantized * 100), 100)
    libelle = f"{nombre_en_lettres(euros)} euro{'s' if euros > 1 else ''}"
    if centimes:
        libelle += (
            f" et {nombre_en_lettres(centimes)} "
            f"centime{'s' if centimes > 1 else ''}"
        )
    return libelle


def format_date_long(value: date) -> str:
    """« 1er septembre 2026 », « 31 août 2026 ».

    Forme attendue dans les attestations. Seul le premier du mois porte
    l'ordinal, les autres jours s'ecrivent en chiffres nus.
    """
    jour = "1er" if value.day == 1 else str(value.day)
    return f"{jour} {month_name(value.month)} {value.year}"


def format_date_en(value: date) -> str:
    """« 3 September 2026 ».

    Le format numerique francais est ambigu pour un lecteur anglophone :
    03/09/2026 se lit « 9 mars » aux Etats-Unis. Le mois est donc ecrit.
    """
    return f"{value.day} {month_name_en(value.month)} {value.year}"


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


def format_amount_signe(value: Decimal) -> str:
    """« +50,00 € » ou « -120,00 € » : le signe est toujours porte.

    `format_amount` omet le plus, ce qui convient a un loyer, jamais negatif.
    Une ligne de regularisation manuelle va dans les deux sens : sans le signe,
    « Degradations 120,00 € » ne dit pas si la somme est retenue ou rendue.
    """
    rendu = format_amount(value)
    return rendu if rendu.startswith("-") else f"+{rendu}"


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
