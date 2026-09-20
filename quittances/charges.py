"""Charges reelles d'une maison, mois par mois.

Deux natures de charges cohabitent :

* les **fixes**, declarees une fois dans `config.yaml` sous `monthly_charges` —
  l'eau et l'internet, dont le montant mensuel ne bouge pas d'un exercice ;
* les **variables**, relevees facture par facture dans `charges.yaml` —
  l'electricite, qui double en hiver.

Un poste releve dans le journal **remplace** son homologue fixe pour ce mois :
c'est ce qui permet d'inscrire une facture d'eau reelle quand elle s'ecarte de
la reference.

Le journal vit a cote de `config.yaml`, comme `ajustements.yaml`, et pour les
memes raisons : versionne, il garde la trace des montants retenus.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import yaml

from .config import ConfigError, Property
from .formatting import parse_amount

DEFAULT_CHARGES_PATH = Path("charges.yaml")
CHARGES_ENV_VAR = "QUITTANCES_CHARGES"


def _periode(cle: str, contexte: str) -> date:
    try:
        return datetime.strptime(str(cle), "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise ConfigError(
            f"{contexte} : période invalide « {cle} ». Format attendu : AAAA-MM."
        ) from exc


@dataclass(frozen=True)
class ChargesDuMois:
    """Postes retenus pour une maison et un mois, fixes et releves confondus."""

    property_key: str
    period: date
    postes: dict[str, Decimal] = field(default_factory=dict)
    # Postes qui viennent du journal et non de la reference : le rapport
    # distingue un montant releve d'un montant presume.
    releves: frozenset[str] = frozenset()

    @property
    def total(self) -> Decimal:
        return sum(self.postes.values(), Decimal("0.00"))

    def est_releve(self, poste: str) -> bool:
        return poste in self.releves


@dataclass(frozen=True)
class Charges:
    """Journal des charges relevees, indexe par maison et par mois."""

    entrees: dict[tuple[str, date], dict[str, Decimal]]
    source: Path | None = None

    def du_mois(self, bien: Property, period: date) -> ChargesDuMois:
        """Charges retenues : les fixes, corrigees des postes releves."""
        periode = period.replace(day=1)
        releves = self.entrees.get((bien.key, periode), {})
        postes = dict(bien.monthly_charges)
        postes.update(releves)
        return ChargesDuMois(
            property_key=bien.key,
            period=periode,
            postes=postes,
            releves=frozenset(releves),
        )

    def postes_connus(self) -> list[str]:
        noms = {poste for releves in self.entrees.values() for poste in releves}
        return sorted(noms)

    @classmethod
    def vide(cls) -> "Charges":
        return cls(entrees={})

    @classmethod
    def load(
        cls,
        path: str | os.PathLike[str] | None = None,
        properties: Mapping[str, Property] | None = None,
        base_dir: Path | None = None,
    ) -> "Charges":
        """Charge le journal. Son absence est normale : rien n'a encore ete releve.

        Comme pour les ajustements, le fichier se cherche **a cote du
        `config.yaml` retenu** et non dans le repertoire courant.
        """
        choisi = path or os.environ.get(CHARGES_ENV_VAR)
        if choisi:
            resolved = Path(choisi)
        else:
            racine = Path(base_dir) if base_dir is not None else Path()
            resolved = racine / DEFAULT_CHARGES_PATH
        if not resolved.is_file():
            return cls.vide()
        try:
            brut = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML invalide dans {resolved} : {exc}") from exc
        if not isinstance(brut, Mapping):
            raise ConfigError(f"{resolved} doit contenir un mapping YAML.")

        entrees: dict[tuple[str, date], dict[str, Decimal]] = {}
        for cle_bien, mois in brut.items():
            if properties is not None and cle_bien not in properties:
                connus = ", ".join(sorted(properties)) or "(aucune)"
                raise ConfigError(
                    f"{resolved} : maison « {cle_bien} » inconnue. "
                    f"Maisons déclarées : {connus}."
                )
            if not isinstance(mois, Mapping):
                raise ConfigError(
                    f"charges.{cle_bien} : un mapping de mois est attendu."
                )
            for cle_periode, postes in mois.items():
                contexte = f"charges.{cle_bien}.{cle_periode}"
                periode = _periode(cle_periode, contexte)
                if not isinstance(postes, Mapping):
                    raise ConfigError(f"{contexte} : un mapping de postes est attendu.")
                entrees[(cle_bien, periode)] = {
                    str(poste): _montant(valeur, f"{contexte}.{poste}")
                    for poste, valeur in postes.items()
                }
        return cls(entrees=entrees, source=resolved)


def _montant(valeur: Any, contexte: str) -> Decimal:
    try:
        montant = parse_amount(valeur)
    except ValueError as exc:
        raise ConfigError(f"{contexte} : {exc}") from exc
    if montant < 0:
        raise ConfigError(f"{contexte} : une charge négative n'a pas de sens.")
    return montant


def repartition(
    bien: Property,
    total: Decimal,
    occupants: list,
    debut: date | None = None,
    fin: date | None = None,
) -> tuple[list[tuple[Any, Decimal]], Decimal]:
    """Repartit un total au prorata des quotes-parts et de l'occupation.

    Renvoie `(parts, reliquat)`. Le **reliquat** est ce qui n'a pu etre impute
    a personne : chambre vacante, locataire entre en cours de periode ou deja
    parti. Il reste a la charge du bailleur, et doit se voir — c'est lui qui
    mesure le cout d'une vacance.

    Sans periode, tout le monde est repute present toute la periode : la
    repartition se fait alors sur les seules quotes-parts.
    """
    avec_part = [t for t in occupants if t.share is not None]
    if not avec_part:
        return [], total

    parts: list[tuple[Any, Decimal]] = []
    cumul = Decimal("0.00")
    for tenant in avec_part:
        montant = total * tenant.share / Decimal("100")
        if debut is not None and fin is not None:
            jours_periode = (fin - debut).days + 1
            if jours_periode <= 0:
                montant = Decimal("0")
            else:
                montant = montant * tenant.jours_occupes(debut, fin) / jours_periode
        montant = montant.quantize(Decimal("0.01"))
        parts.append((tenant, montant))
        cumul += montant

    reliquat = (total - cumul).quantize(Decimal("0.01"))

    # Distinguer l'arrondi de la vacance : quand les quotes-parts occupees
    # couvrent la totalite de la periode, l'ecart residuel n'est qu'un arrondi
    # et le dernier occupant l'absorbe. L'afficher comme une vacance de un
    # centime serait un contresens.
    couverture = Decimal("0")
    for tenant in avec_part:
        if debut is None or fin is None:
            couverture += tenant.share
        else:
            jours_periode = (fin - debut).days + 1
            if jours_periode > 0:
                couverture += (
                    tenant.share * tenant.jours_occupes(debut, fin) / jours_periode
                )
    if parts and reliquat and couverture >= Decimal("99.95"):
        dernier, montant = parts[-1]
        parts[-1] = (dernier, montant + reliquat)
        reliquat = Decimal("0.00")
    return parts, reliquat


# Regroupement des postes pour la presentation : une facture arrive en
# plusieurs lignes, elle se lit en une colonne.
#
# L'eau se decompose comme l'electricite, en une part fixe (l'abonnement, du
# meme logement vide) et une part variable (consommation, assainissement,
# redevances). Les deux postes sont distincts du cote electricite — sans le
# prefixe « eau_ », `abonnement` designerait les deux.
# Intitule de la tranche qui porte les supplements dedies, au graphique comme
# au tableau : ils ne sont pas repartis, ils ne se fondent donc pas dans leur
# groupe.
SUPPLEMENT = "Supplément"

GROUPES = {
    "eau": "Eau",
    "eau_abonnement": "Eau",
    "eau_consommation": "Eau",
    "internet": "Internet",
}


def groupe(poste: str) -> str:
    """« abonnement », « cta », « accise »... -> « Electricite »."""
    return GROUPES.get(poste.strip().lower(), "Électricité")


@dataclass(frozen=True)
class LigneRegularisation:
    """Ce qu'un locataire doit et ce qu'il a verse, sur une periode."""

    tenant: Any
    reel: dict[str, Decimal]          # par groupe de postes, apres deduction
    provisions: Decimal
    # Supplements imputes a lui seul : motif -> montant sur la periode.
    dediees: dict[str, Decimal] = field(default_factory=dict)
    # (mois, {ligne: montant}, provisions) pour le graphique. Les cles sont
    # celles du tableau — groupes de postes, plus « Supplement » — pour que la
    # barre empilee et le decompte disent la meme chose.
    mensuel: tuple[tuple[date, dict[str, Decimal], Decimal], ...] = ()

    @property
    def total_dediees(self) -> Decimal:
        return sum(self.dediees.values(), Decimal("0.00"))

    @property
    def total_reel(self) -> Decimal:
        return sum(self.reel.values(), Decimal("0.00")) + self.total_dediees

    @property
    def solde(self) -> Decimal:
        """Negatif : le locataire a trop verse, il lui est du."""
        return (self.total_reel - self.provisions).quantize(Decimal("0.01"))


def regularisations(
    bien: Property,
    occupants: list,
    mois: list[date],
    journal: "Charges",
    ajustements,
) -> tuple[list[LigneRegularisation], dict[str, Decimal], Decimal]:
    """Charges reelles imputees a chacun, face aux provisions encaissees.

    Renvoie `(lignes, totaux_par_groupe, reliquat_bailleur)`. Le reliquat est
    la part des charges qu'aucun locataire ne supporte : chambre vacante ou
    periode hors bail.

    Les provisions retenues sont celles reellement facturees sur les
    quittances — celles du bail, corrigees des ajustements du mois.
    """
    from .factures import FIXE  # evite un import circulaire au chargement

    reels: dict[Any, dict[str, Decimal]] = {t.key: {} for t in occupants}
    dediees: dict[Any, dict[str, Decimal]] = {t.key: {} for t in occupants}
    # Cumul par mois, pour le graphique : ce que le locataire a supporte face a
    # ce qu'il a verse.
    par_mois: dict[Any, dict[date, dict[str, Decimal]]] = {
        t.key: {m: {} for m in mois} for t in occupants
    }
    prov_mois: dict[Any, dict[date, Decimal]] = {
        t.key: {m: Decimal("0.00") for m in mois} for t in occupants
    }
    provisions: dict[Any, Decimal] = {t.key: Decimal("0.00") for t in occupants}
    totaux: dict[str, Decimal] = {}
    reliquat = Decimal("0.00")

    for m in mois:
        du_mois = journal.du_mois(bien, m)
        fin_mois = (m.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

        # Agreger par groupe avant de repartir : une charge dediee vise un
        # groupe, pas une ligne de facture. L'electricite arrive en quatre
        # postes, le supplement d'un vehicule est un seul montant.
        par_groupe: dict[str, Decimal] = {}
        for poste, montant in du_mois.postes.items():
            nom = groupe(poste)
            par_groupe[nom] = par_groupe.get(nom, Decimal("0.00")) + montant

        for nom, montant in par_groupe.items():
            detail = {
                t.key: t.charges_dediees_periode(nom, m, fin_mois) for t in occupants
            }
            total_dedie = sum(
                (v for lignes in detail.values() for _, v in lignes), Decimal("0.00")
            )
            # On ne peut pas imputer plus que la facture du mois. Le cas se
            # presente quand le journal ne porte qu'une part du groupe : en
            # septembre, l'abonnement d'electricite seul, la consommation pas
            # encore relevee. Les supplements sont alors rabattus au prorata.
            if total_dedie > montant:
                facteur = montant / total_dedie if total_dedie else Decimal("0")
                detail = {
                    cle: [(motif, (v * facteur).quantize(Decimal("0.01")))
                          for motif, v in lignes]
                    for cle, lignes in detail.items()
                }
                total_dedie = sum(
                    (v for lignes in detail.values() for _, v in lignes),
                    Decimal("0.00"),
                )
            for cle, lignes in detail.items():
                for motif, valeur in lignes:
                    dediees[cle][motif] = dediees[cle].get(
                        motif, Decimal("0.00")
                    ) + valeur
                    # Le supplement n'est pas reparti : il forme sa propre
                    # tranche, comme sa propre ligne au tableau.
                    par_mois[cle][m][SUPPLEMENT] = par_mois[cle][m].get(
                        SUPPLEMENT, Decimal("0.00")
                    ) + valeur

            # La colonne « maison » du document porte le montant **partage**,
            # deduction faite : c'est lui qui se reconcilie avec la quote-part.
            partage = montant - total_dedie
            totaux[nom] = totaux.get(nom, Decimal("0.00")) + partage
            parts, reste = repartition(bien, partage, occupants, m, fin_mois)
            reliquat += reste
            for tenant, part in parts:
                reels[tenant.key][nom] = reels[tenant.key].get(
                    nom, Decimal("0.00")
                ) + part
                par_mois[tenant.key][m][nom] = par_mois[tenant.key][m].get(
                    nom, Decimal("0.00")
                ) + part

        for tenant in occupants:
            ajustement = ajustements.pour(tenant, m) if ajustements else None
            charges = ajustement.charges_effectives if ajustement else None
            if charges is None:
                charges = tenant.charges or Decimal("0.00")
            # Un locataire hors bail ne s'est vu facturer aucune provision.
            if tenant.jours_occupes(m, fin_mois) > 0:
                provisions[tenant.key] += charges
                prov_mois[tenant.key][m] += charges

    lignes = [
        LigneRegularisation(
            tenant=tenant,
            reel={k: v.quantize(Decimal("0.01")) for k, v in reels[tenant.key].items()},
            provisions=provisions[tenant.key],
            dediees={
                k: v.quantize(Decimal("0.01"))
                for k, v in dediees[tenant.key].items()
            },
            mensuel=tuple(
                (
                    m,
                    {k: v.quantize(Decimal("0.01")) for k, v in lignes.items()},
                    prov_mois[tenant.key][m].quantize(Decimal("0.01")),
                )
                for m, lignes in sorted(par_mois[tenant.key].items())
            ),
        )
        for tenant in occupants
    ]
    return lignes, totaux, reliquat.quantize(Decimal("0.01"))
