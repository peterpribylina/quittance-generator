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
from datetime import date, datetime
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
    if debut is None or fin is None:
        # Sans periode, l'ecart ne peut venir que de l'arrondi : le dernier
        # occupant l'absorbe plutot que d'inventer une part bailleur.
        if parts and reliquat:
            dernier, montant = parts[-1]
            parts[-1] = (dernier, montant + reliquat)
            reliquat = Decimal("0.00")
    return parts, reliquat
