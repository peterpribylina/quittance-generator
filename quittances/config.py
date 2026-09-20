"""Chargement et validation de la configuration (bailleur, biens, locataires).

Toutes les donnees metier vivent dans `config.yaml` : plus rien n'est code en
dur dans les sources, contrairement a l'ancien `helper.js`.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import yaml

from .formatting import format_amount_signe, parse_amount

DEFAULT_CONFIG_PATH = Path("config.yaml")
CONFIG_ENV_VAR = "QUITTANCES_CONFIG"


class ConfigError(Exception):
    """Configuration absente, mal formee ou incomplete."""


def _require(mapping: Mapping[str, Any], key: str, context: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise ConfigError(f"Champ obligatoire manquant : « {key} » dans {context}.")
    return mapping[key]


def _optional_date(mapping: Mapping[str, Any], key: str, context: str) -> date | None:
    """YAML rend deja un `date` pour 2026-09-01 ; une chaine reste toleree."""
    valeur = mapping.get(key)
    if valeur in (None, ""):
        return None
    if isinstance(valeur, date):
        return valeur
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valeur), fmt).date()
        except ValueError:
            continue
    raise ConfigError(
        f"{context} : date invalide pour « {key} » ({valeur!r}). "
        "Formats acceptes : AAAA-MM-JJ ou JJ/MM/AAAA."
    )


def _optional_amount(mapping: Mapping[str, Any], key: str, context: str) -> Decimal | None:
    if mapping.get(key) in (None, ""):
        return None
    try:
        return parse_amount(mapping[key])
    except ValueError as exc:
        raise ConfigError(f"{context} : {exc}") from exc


def _sans_accents(texte: str) -> str:
    """Compare des intitules saisis a la main sans buter sur les accents."""
    decompose = unicodedata.normalize("NFD", texte.strip().casefold())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def _montant_positif(valeur: Any, contexte: str) -> Decimal:
    try:
        montant = parse_amount(valeur)
    except ValueError as exc:
        raise ConfigError(f"{contexte} : {exc}") from exc
    if montant < 0:
        raise ConfigError(f"{contexte} : un montant negatif n'a pas de sens.")
    return montant


def _liste(data: Mapping[str, Any], cle: str, ctx: str) -> list[Any]:
    """Valide la forme d'un champ-liste avant de le detailler.

    Un mapping au lieu d'une liste est l'erreur naturelle quand on ecrit du
    YAML a la main : elle doit se dire, pas se traduire en « champ inconnu ».
    """
    brut = data.get(cle)
    if brut in (None, ""):
        return []
    if not isinstance(brut, list):
        raise ConfigError(
            f"{ctx}.{cle} : une liste est attendue. Chaque entree est un bloc "
            "prefixe d'un tiret."
        )
    return brut


@dataclass(frozen=True)
class Landlord:
    title: str
    first_name: str
    last_name: str
    address_lines: tuple[str, ...]
    city: str
    email: str
    birth_date: str | None = None
    birth_place: str | None = None

    @property
    def display_name(self) -> str:
        """« M. PRIBYLINA Peter » : usage administratif francais."""
        return f"{self.title} {self.last_name.upper()} {self.first_name}"

    @property
    def legal_name(self) -> str:
        """« Peter PRIBYLINA » : usage courant, prenom en premier."""
        return f"{self.first_name} {self.last_name.upper()}"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Landlord":
        ctx = "landlord"
        lines = _require(data, "address_lines", ctx)
        if isinstance(lines, str):
            lines = [lines]
        return cls(
            title=str(_require(data, "title", ctx)),
            first_name=str(_require(data, "first_name", ctx)),
            last_name=str(_require(data, "last_name", ctx)),
            address_lines=tuple(str(line) for line in lines),
            city=str(_require(data, "city", ctx)),
            email=str(_require(data, "email", ctx)),
            birth_date=data.get("birth_date") or None,
            birth_place=data.get("birth_place") or None,
        )


@dataclass(frozen=True)
class Property:
    key: str
    address: str
    folder: Path
    # Ce qui est loue, tel qu'il s'ecrit dans une attestation de domicile :
    # « une chambre » en colocation, « un logement » pour un bien entier.
    dwelling: str = "une chambre"
    # Ou sont deposees les factures de la maison (eau, internet, electricite).
    charges_folder: Path | None = None
    # Charges mensuelles de reference, par poste. L'electricite n'y figure pas :
    # elle varie trop, et se releve facture par facture dans charges.yaml.
    #
    # Ce dictionnaire rend `Property` — et donc `Tenant` — non hachable :
    # indexer par `tenant.key` plutot que par l'objet.
    monthly_charges: dict[str, Decimal] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, key: str, data: Mapping[str, Any]) -> "Property":
        ctx = f"properties.{key}"
        return cls(
            key=key,
            address=str(_require(data, "address", ctx)),
            folder=Path(str(_require(data, "folder", ctx))),
            dwelling=str(data.get("dwelling") or "une chambre"),
            charges_folder=(
                Path(str(data["charges_folder"]))
                if data.get("charges_folder")
                else None
            ),
            monthly_charges={
                str(poste): _montant_positif(valeur, f"{ctx}.monthly_charges.{poste}")
                for poste, valeur in (data.get("monthly_charges") or {}).items()
            },
        )

    @property
    def monthly_charges_total(self) -> Decimal:
        """Somme des charges fixes mensuelles, hors electricite."""
        return sum(self.monthly_charges.values(), Decimal("0.00"))


@dataclass(frozen=True)
class LigneManuelle:
    """Montant porte a la main sur une regularisation : geste, degradations.

    **Le signe se lit en faveur du locataire** : un geste commercial est
    positif, une retenue pour degradations negative. C'est le sens dans lequel
    le bailleur raisonne quand il saisit la ligne — « je lui rends 50 », « je
    lui retiens 120 ». Le solde d'une regularisation compte l'inverse, ce que
    le locataire doit ; l'inversion est faite une seule fois, dans
    `Regularisation.total_lignes`, et nulle part ailleurs.

    La `date` rattache la ligne a une regularisation : seules celles qui
    tombent dans la periode sont reprises. Un bailleur en emet au moins une par
    an, et une de sortie ; sans cette date, un geste de 2026 reviendrait sur la
    regularisation de 2027.
    """

    date: date
    libelle: str
    montant: Decimal

    @property
    def montant_label(self) -> str:
        """« +50,00 € », signe toujours visible.

        Sans le signe, « Degradations 120,00 € » ne dit pas si la somme est
        retenue ou rendue : c'est la seule information qui manque au lecteur.
        """
        return format_amount_signe(self.montant)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], contexte: str) -> "LigneManuelle":
        if not isinstance(data, Mapping):
            raise ConfigError(f"{contexte} : un mapping est attendu (date, libelle, montant).")
        inconnus = set(data) - {"date", "libelle", "montant"}
        if inconnus:
            raise ConfigError(
                f"{contexte} : champ(s) inconnu(s) {', '.join(sorted(inconnus))}. "
                "Attendus : date, libelle, montant."
            )
        quand = _optional_date(data, "date", contexte)
        if quand is None:
            raise ConfigError(
                f"{contexte} : « date » est obligatoire. Elle rattache la ligne "
                "a une regularisation."
            )
        libelle = str(data.get("libelle") or "").strip()
        if not libelle:
            raise ConfigError(
                f"{contexte} : « libelle » est obligatoire. Un montant sans "
                "explication sur le document genere une question."
            )
        montant = _optional_amount(data, "montant", contexte)
        if montant is None:
            raise ConfigError(f"{contexte} : « montant » est obligatoire.")
        if montant == 0:
            raise ConfigError(f"{contexte} : un montant nul n'a rien a regulariser.")
        return cls(date=quand, libelle=libelle, montant=montant)


# Groupes de charges sur lesquels une charge dediee peut porter. Ecrits ici et
# non deduits de `charges.groupe`, qui rabat tout intitule inconnu sur
# « Electricite » : une faute de frappe doit echouer, pas se deviner.
GROUPES_CHARGES = ("Eau", "Internet", "Électricité")


def _groupe_declare(valeur: Any, contexte: str) -> str:
    """« electricite », « Électricité », « ELECTRICITE » -> « Électricité »."""
    cherche = _sans_accents(str(valeur))
    for connu in GROUPES_CHARGES:
        if _sans_accents(connu) == cherche:
            return connu
    attendus = ", ".join(GROUPES_CHARGES)
    raise ConfigError(
        f"{contexte} : groupe « {valeur} » inconnu. Groupes : {attendus}."
    )


@dataclass(frozen=True)
class ChargeDediee:
    """Part d'une charge imputee a un seul locataire, avant toute repartition.

    Un vehicule electrique recharge sur place, un radiateur de plus : la
    consommation est causee par une personne, pas par des metres carres. La
    repartir a la surface la ferait porter par les autres.

    Le montant est **mensuel**, et se prorate aux jours d'occupation : partir
    le 15 ne fait pas recharger sa voiture jusqu'au 30.

    Tenir les 100 % ne demande alors aucun calcul : la somme dediee est
    prelevee sur le cout du groupe, et le **reste** se repartit aux
    quotes-parts inchangees. Une seconde grille de pourcentages aurait suivi la
    facture — un hiver froid aurait double le supplement d'un vehicule qui
    n'aurait rien consomme de plus.
    """

    groupe: str
    montant: Decimal
    motif: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], contexte: str) -> "ChargeDediee":
        if not isinstance(data, Mapping):
            raise ConfigError(
                f"{contexte} : un mapping est attendu (groupe, montant, motif)."
            )
        inconnus = set(data) - {"groupe", "montant", "motif"}
        if inconnus:
            raise ConfigError(
                f"{contexte} : champ(s) inconnu(s) {', '.join(sorted(inconnus))}. "
                "Attendus : groupe, montant, motif."
            )
        motif = str(data.get("motif") or "").strip()
        if not motif:
            raise ConfigError(
                f"{contexte} : « motif » est obligatoire. Un supplement non "
                "explique sur le document du locataire genere une question."
            )
        montant = _optional_amount(data, "montant", contexte)
        if montant is None:
            raise ConfigError(f"{contexte} : « montant » est obligatoire.")
        if montant <= 0:
            raise ConfigError(
                f"{contexte} : le montant doit etre positif. Une charge dediee "
                "s'ajoute a la part d'un locataire, elle ne la diminue pas."
            )
        return cls(
            groupe=_groupe_declare(_require(data, "groupe", contexte), contexte),
            montant=montant,
            motif=motif,
        )


@dataclass(frozen=True)
class Tenant:
    key: str
    first_name: str
    last_name: str
    property: Property
    # Facultative : un titre absent vaut mieux qu'un titre devine a partir du
    # prenom. Il est alors simplement omis des documents.
    title: str | None = None
    # Facultatifs : la generation des PDF n'en a pas besoin, seul l'envoi si.
    emails: tuple[str, ...] = ()
    rent: Decimal | None = None
    charges: Decimal | None = None
    birth_date: str | None = None
    birth_place: str | None = None
    # Entree dans les lieux, pour l'attestation de domicile.
    lease_start: date | None = None
    # Sortie des lieux. Absente tant que le locataire est en place ; une fois
    # renseignee, les charges cessent de lui etre imputees au-dela.
    lease_end: date | None = None
    # Preavis respecte : le mois de depart est alors du en entier. Un depart
    # sans preavis se prorate au nombre de jours.
    preavis: bool = True
    # Situation de la chambre : « R+2 », « RDC jardin »...
    room: str | None = None
    # Quote-part de surface, en pourcentage du total de la maison. Sert a
    # repartir les charges annuelles.
    share: Decimal | None = None
    # Montants portes a la main sur une regularisation, positifs en faveur du
    # locataire. Voir `LigneManuelle`.
    lignes_manuelles: tuple[LigneManuelle, ...] = ()
    # Parts de charges imputees a lui seul avant repartition. Voir
    # `ChargeDediee`.
    charges_dediees: tuple[ChargeDediee, ...] = ()

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        """« M. LUO Jingyi », ou « LUO Jingyi » sans civilite configuree.

        Le nom complet est conserve, y compris compose.
        """
        nom = f"{self.last_name.upper()} {self.first_name}"
        return f"{self.title}. {nom}" if self.title else nom

    @property
    def short_name(self) -> str:
        """« Jingyi L. » : forme abregee pour les tableaux.

        Reserve a l'affichage. Les documents portent toujours le nom complet.
        """
        return f"{self.first_name} {self.last_name[0].upper()}."

    @property
    def slug(self) -> str:
        """Nom de dossier : « Jingyi_Luo »."""
        return self.full_name.replace(" ", "_")

    @property
    def address(self) -> str:
        return self.property.address

    @property
    def dwelling(self) -> str:
        return self.property.dwelling

    @property
    def fin_due(self) -> date | None:
        """Derniere date due, preavis compris.

        Avec preavis, le mois de depart est du en entier : partir le 19 ne
        dispense pas de septembre. Sans preavis, la sortie fait foi.
        """
        if self.lease_end is None:
            return None
        if not self.preavis:
            return self.lease_end
        suivant = (self.lease_end.replace(day=28) + timedelta(days=4)).replace(day=1)
        return suivant - timedelta(days=1)

    def jours_occupes(self, debut: date, fin: date) -> int:
        """Jours dus dans la periode, bornes incluses.

        Un bail qui commence apres le debut, ou dont l'obligation s'acheve
        avant la fin, reduit d'autant la part de charges imputable.
        """
        entree = max(debut, self.lease_start) if self.lease_start else debut
        due = self.fin_due
        sortie = min(fin, due) if due else fin
        return max(0, (sortie - entree).days + 1)

    def lignes_manuelles_entre(
        self, debut: date, fin: date
    ) -> tuple["LigneManuelle", ...]:
        """Lignes manuelles dont la date tombe dans la periode, bornes incluses.

        Chaque regularisation ne reprend que les siennes : c'est ce qui permet
        d'en emettre plusieurs sans rejouer les gestes des annees passees.
        """
        return tuple(
            ligne for ligne in self.lignes_manuelles if debut <= ligne.date <= fin
        )

    def charges_dediees_periode(
        self, groupe: str, debut: date, fin: date
    ) -> list[tuple[str, Decimal]]:
        """(motif, montant) pour ce groupe sur la periode, au prorata des jours.

        Le montant declare est mensuel. Partir le 15 ne fait pas recharger sa
        voiture jusqu'au 30 : la somme suit les jours reellement occupes. Le
        motif accompagne le montant jusqu'au document — un supplement sans
        explication genere une question.
        """
        jours = (fin - debut).days + 1
        if jours <= 0:
            return []
        part = Decimal(self.jours_occupes(debut, fin)) / Decimal(jours)
        rendu = []
        for charge in self.charges_dediees:
            if charge.groupe != groupe:
                continue
            montant = (charge.montant * part).quantize(Decimal("0.01"))
            if montant:
                rendu.append((charge.motif, montant))
        return rendu

    @property
    def share_label(self) -> str:
        """« 22,39 % », espace insecable avant le signe."""
        if self.share is None:
            return "-"
        return f"{self.share:.2f}".replace(".", ",") + "\u00a0%"

    @classmethod
    def from_dict(
        cls, key: str, data: Mapping[str, Any], properties: Mapping[str, Property]
    ) -> "Tenant":
        ctx = f"tenants.{key}"
        property_key = str(_require(data, "property", ctx))
        if property_key not in properties:
            connus = ", ".join(sorted(properties)) or "(aucun)"
            raise ConfigError(
                f"{ctx} : bien « {property_key} » inconnu. Biens declares : {connus}."
            )
        emails = data.get("email") or ()
        if isinstance(emails, str):
            # L'ancienne config tolerait "a@x.fr, b@y.fr" dans un seul champ.
            emails = [part.strip() for part in emails.split(",") if part.strip()]
        titre = data.get("title") or None
        return cls(
            key=key,
            title=str(titre) if titre else None,
            first_name=str(_require(data, "first_name", ctx)),
            last_name=str(_require(data, "last_name", ctx)),
            emails=tuple(str(email) for email in emails),
            property=properties[property_key],
            rent=_optional_amount(data, "rent", ctx),
            charges=_optional_amount(data, "charges", ctx),
            birth_date=data.get("birth_date") or None,
            birth_place=data.get("birth_place") or None,
            lease_start=_optional_date(data, "lease_start", ctx),
            lease_end=_optional_date(data, "lease_end", ctx),
            preavis=bool(data.get("preavis", True)),
            room=str(data["room"]) if data.get("room") else None,
            share=_optional_amount(data, "share", ctx),
            lignes_manuelles=tuple(
                LigneManuelle.from_dict(ligne, f"{ctx}.lignes_manuelles[{i}]")
                for i, ligne in enumerate(_liste(data, "lignes_manuelles", ctx))
            ),
            charges_dediees=tuple(
                ChargeDediee.from_dict(ligne, f"{ctx}.charges_dediees[{i}]")
                for i, ligne in enumerate(_liste(data, "charges_dediees", ctx))
            ),
        )


# Tolerance sur la somme des quotes-parts : des surfaces reelles arrondies au
# centieme tombent rarement sur 100,00 % pile.
TOLERANCE_QUOTE_PART = Decimal("0.05")


def _verifier_quotes_parts(tenants: Mapping[str, "Tenant"]) -> None:
    """Par maison, les quotes-parts renseignees doivent totaliser 100 %.

    Une maison sans aucune quote-part est acceptee : la repartition des charges
    n'y est simplement pas encore mise en place. En revanche une maison
    partiellement renseignee est refusee — repartir des charges sur une base
    incomplete donnerait des montants faux sans que rien ne le signale.
    """
    par_maison: dict[str, list["Tenant"]] = {}
    for tenant in tenants.values():
        par_maison.setdefault(tenant.property.key, []).append(tenant)

    for maison, occupants in sorted(par_maison.items()):
        avec = [t for t in occupants if t.share is not None]
        if not avec:
            continue
        sans = [t.key for t in occupants if t.share is None]
        if sans:
            raise ConfigError(
                f"Quotes-parts incompletes pour la maison « {maison} » : "
                f"{', '.join(sorted(sans))} n'en ont pas. Renseignez « share » "
                "pour tous les locataires de la maison, ou pour aucun."
            )
        total = sum((t.share for t in avec), Decimal("0"))
        if abs(total - Decimal("100")) > TOLERANCE_QUOTE_PART:
            raise ConfigError(
                f"Les quotes-parts de la maison « {maison} » totalisent "
                f"{total} % au lieu de 100 %."
            )


@dataclass(frozen=True)
class Assets:
    logo: Path
    signature: Path
    # Plus utilise par la mise en page actuelle ; conserve pour les
    # configurations existantes et une eventuelle reprise.
    watermark: Path | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], base_dir: Path) -> "Assets":
        ctx = "assets"
        filigrane = data.get("watermark")
        return cls(
            logo=base_dir / str(_require(data, "logo", ctx)),
            signature=base_dir / str(_require(data, "signature", ctx)),
            watermark=base_dir / str(filigrane) if filigrane else None,
        )

    def missing(self) -> list[Path]:
        candidats = [self.logo, self.signature, self.watermark]
        return [p for p in candidats if p is not None and not p.is_file()]


@dataclass(frozen=True)
class Config:
    landlord: Landlord
    assets: Assets
    properties: dict[str, Property]
    tenants: dict[str, Tenant]
    source: Path

    def tenant(self, key: str) -> Tenant:
        """Recherche insensible a la casse ; leve une erreur listant les cles connues."""
        for candidate, tenant in self.tenants.items():
            if candidate.lower() == key.lower():
                return tenant
        connus = ", ".join(sorted(self.tenants)) or "(aucun)"
        raise ConfigError(f"Locataire « {key} » inconnu. Locataires declares : {connus}.")

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> "Config":
        resolved = Path(path or os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG_PATH)
        if not resolved.is_file():
            raise ConfigError(
                f"Fichier de configuration introuvable : {resolved}. "
                "Copiez config.example.yaml vers config.yaml pour demarrer."
            )
        try:
            raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML invalide dans {resolved} : {exc}") from exc
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{resolved} doit contenir un mapping YAML a la racine.")
        return cls.from_dict(raw, base_dir=resolved.parent, source=resolved)

    @classmethod
    def from_dict(
        cls, raw: Mapping[str, Any], base_dir: Path, source: Path = DEFAULT_CONFIG_PATH
    ) -> "Config":
        landlord = Landlord.from_dict(_require(raw, "landlord", "la racine"))
        assets = Assets.from_dict(_require(raw, "assets", "la racine"), base_dir)

        properties_raw = _require(raw, "properties", "la racine")
        properties = {
            key: Property.from_dict(key, value) for key, value in properties_raw.items()
        }

        tenants_raw = _require(raw, "tenants", "la racine")
        tenants = {
            key: Tenant.from_dict(key, value, properties)
            for key, value in tenants_raw.items()
        }
        _verifier_quotes_parts(tenants)
        return cls(
            landlord=landlord,
            assets=assets,
            properties=properties,
            tenants=tenants,
            source=source,
        )
