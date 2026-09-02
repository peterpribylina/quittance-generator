"""Chargement et validation de la configuration (bailleur, biens, locataires).

Toutes les donnees metier vivent dans `config.yaml` : plus rien n'est code en
dur dans les sources, contrairement a l'ancien `helper.js`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import yaml

from .formatting import parse_amount

DEFAULT_CONFIG_PATH = Path("config.yaml")
CONFIG_ENV_VAR = "QUITTANCES_CONFIG"


class ConfigError(Exception):
    """Configuration absente, mal formee ou incomplete."""


def _require(mapping: Mapping[str, Any], key: str, context: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise ConfigError(f"Champ obligatoire manquant : « {key} » dans {context}.")
    return mapping[key]


def _optional_amount(mapping: Mapping[str, Any], key: str, context: str) -> Decimal | None:
    if mapping.get(key) in (None, ""):
        return None
    try:
        return parse_amount(mapping[key])
    except ValueError as exc:
        raise ConfigError(f"{context} : {exc}") from exc


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

    @classmethod
    def from_dict(cls, key: str, data: Mapping[str, Any]) -> "Property":
        ctx = f"properties.{key}"
        return cls(
            key=key,
            address=str(_require(data, "address", ctx)),
            folder=Path(str(_require(data, "folder", ctx))),
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
    def slug(self) -> str:
        """Nom de dossier : « Jingyi_Luo »."""
        return self.full_name.replace(" ", "_")

    @property
    def address(self) -> str:
        return self.property.address

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
        )


@dataclass(frozen=True)
class Assets:
    logo: Path
    watermark: Path
    signature: Path

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], base_dir: Path) -> "Assets":
        ctx = "assets"
        return cls(
            logo=base_dir / str(_require(data, "logo", ctx)),
            watermark=base_dir / str(_require(data, "watermark", ctx)),
            signature=base_dir / str(_require(data, "signature", ctx)),
        )

    def missing(self) -> list[Path]:
        return [p for p in (self.logo, self.watermark, self.signature) if not p.is_file()]


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
        return cls(
            landlord=landlord,
            assets=assets,
            properties=properties,
            tenants=tenants,
            source=source,
        )
