"""Ajustements mensuels : ce qui s'ecarte du bail, mois par mois.

Un bail fixe un loyer et des provisions de charges, mais la realite mensuelle
varie : un locataire parti tout l'ete ne consomme rien, un autre n'a pas encore
branche sa voiture electrique. Ce module porte ce journal.

Il est **centralise** dans `ajustements.yaml`, a cote de `config.yaml`, et non
disperse dans les dossiers des locataires :

* versionne, il garde la trace de la decision et de sa date — `git blame`
  repond a « pourquoi 20 € en septembre ? » ;
* le suivi somme dix locataires en une lecture ;
* les dossiers `Docs` contiennent ce qu'on remet au locataire, pas les notes de
  gestion du bailleur.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import yaml

from .config import ConfigError, Tenant
from .formatting import format_amount, month_year, parse_amount

DEFAULT_AJUSTEMENTS_PATH = Path("ajustements.yaml")
AJUSTEMENTS_ENV_VAR = "QUITTANCES_AJUSTEMENTS"


def _periode(cle: str, contexte: str) -> date:
    try:
        return datetime.strptime(str(cle), "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise ConfigError(
            f"{contexte} : période invalide « {cle} ». Format attendu : AAAA-MM."
        ) from exc


def _montant(data: Mapping[str, Any], cle: str, contexte: str) -> Decimal | None:
    if data.get(cle) is None:
        return None
    try:
        montant = parse_amount(data[cle])
    except ValueError as exc:
        raise ConfigError(f"{contexte} : {exc}") from exc
    if montant < 0:
        raise ConfigError(f"{contexte} : « {cle} » ne peut pas être négatif.")
    return montant


@dataclass(frozen=True)
class Ajustement:
    """Ce qui change pour un locataire et un mois donnes."""

    tenant_key: str
    period: date
    rent: Decimal | None = None
    charges: Decimal | None = None
    absent: bool = False
    motif: str | None = None

    @property
    def period_label(self) -> str:
        return month_year(self.period)

    @property
    def charges_effectives(self) -> Decimal | None:
        """Un locataire absent ne consomme rien : charges a zero par defaut.

        Une valeur explicite l'emporte — une absence peut laisser un abonnement
        a la charge du locataire.
        """
        if self.charges is not None:
            return self.charges
        if self.absent:
            return Decimal("0.00")
        return None

    def resume(self) -> str:
        """Ligne lisible pour la sortie console."""
        parties = []
        if self.absent:
            parties.append("absent")
        if self.rent is not None:
            parties.append(f"loyer {format_amount(self.rent)}")
        effectives = self.charges_effectives
        if effectives is not None:
            parties.append(f"charges {format_amount(effectives)}")
        return ", ".join(parties) or "aucun changement"

    @classmethod
    def from_dict(
        cls, tenant_key: str, cle_periode: str, data: Mapping[str, Any] | None
    ) -> "Ajustement":
        contexte = f"ajustements.{tenant_key}.{cle_periode}"
        data = data or {}
        if not isinstance(data, Mapping):
            raise ConfigError(f"{contexte} : un mapping est attendu.")
        inconnus = set(data) - {"rent", "charges", "absent", "motif"}
        if inconnus:
            raise ConfigError(
                f"{contexte} : champs inconnus {sorted(inconnus)}. "
                "Attendus : rent, charges, absent, motif."
            )
        return cls(
            tenant_key=tenant_key,
            period=_periode(cle_periode, contexte),
            rent=_montant(data, "rent", contexte),
            charges=_montant(data, "charges", contexte),
            absent=bool(data.get("absent", False)),
            motif=str(data["motif"]) if data.get("motif") else None,
        )


@dataclass(frozen=True)
class Ajustements:
    """Journal complet, indexe par locataire et par mois."""

    entrees: dict[tuple[str, date], Ajustement]
    source: Path | None = None

    def pour(self, tenant: Tenant, period: date) -> Ajustement | None:
        return self.entrees.get((tenant.key, period.replace(day=1)))

    def du_locataire(self, tenant: Tenant) -> list[Ajustement]:
        """Du plus recent au plus ancien."""
        trouves = [a for (cle, _), a in self.entrees.items() if cle == tenant.key]
        return sorted(trouves, key=lambda a: a.period, reverse=True)

    def tous(self) -> list[Ajustement]:
        return sorted(
            self.entrees.values(), key=lambda a: (a.period, a.tenant_key), reverse=True
        )

    @classmethod
    def vide(cls) -> "Ajustements":
        return cls(entrees={})

    @classmethod
    def load(
        cls,
        path: str | os.PathLike[str] | None = None,
        tenants: Mapping[str, Tenant] | None = None,
        base_dir: Path | None = None,
    ) -> "Ajustements":
        """Charge le journal. Son absence est normale : il n'y a rien a ajuster.

        `base_dir` est le dossier du `config.yaml` retenu : le journal vit a
        cote de la configuration qu'il complete, et non dans le repertoire
        courant. Sans cela, `--config autre.yaml` melangerait les journaux, et
        les tests liraient celui du depot.

        `tenants` sert a refuser une cle inconnue : une faute de frappe dans
        `ajustements.yaml` passerait sinon inapercue, et le mois serait facture
        au tarif du bail sans que rien ne le signale.
        """
        choisi = path or os.environ.get(AJUSTEMENTS_ENV_VAR)
        if choisi:
            resolved = Path(choisi)
        else:
            racine = Path(base_dir) if base_dir is not None else Path()
            resolved = racine / DEFAULT_AJUSTEMENTS_PATH
        if not resolved.is_file():
            return cls.vide()
        try:
            brut = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML invalide dans {resolved} : {exc}") from exc
        if not isinstance(brut, Mapping):
            raise ConfigError(f"{resolved} doit contenir un mapping YAML.")

        entrees: dict[tuple[str, date], Ajustement] = {}
        for tenant_key, mois in brut.items():
            if tenants is not None and tenant_key not in tenants:
                connus = ", ".join(sorted(tenants)) or "(aucun)"
                raise ConfigError(
                    f"{resolved} : locataire « {tenant_key} » inconnu. "
                    f"Locataires déclarés : {connus}."
                )
            if not isinstance(mois, Mapping):
                raise ConfigError(
                    f"ajustements.{tenant_key} : un mapping de mois est attendu."
                )
            for cle_periode, data in mois.items():
                ajustement = Ajustement.from_dict(tenant_key, cle_periode, data)
                entrees[(tenant_key, ajustement.period)] = ajustement
        return cls(entrees=entrees, source=resolved)
