from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from quittances.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent

RAW_CONFIG = {
    "landlord": {
        "title": "M.",
        "first_name": "Peter",
        "last_name": "Pribylina",
        "address_lines": ["21 rue Hélène Boucher", "59700 Marcq en Baroeul"],
        "city": "Marcq en Baroeul",
        "email": "bailleur@example.com",
        "birth_date": "15 août 1978",
        "birth_place": "Banska Bystrica, SLOVAQUIE",
    },
    "assets": {
        "logo": "img/logo-coloc.png",
        "watermark": "img/logo-coloc-watermark.png",
        "signature": "img/signature.png",
    },
    "properties": {
        "anzin": {
            "address": "3 impasse Lecomte, 59410 Anzin",
            "folder": "/tmp/anzin",
        },
        "vals": {
            "address": "14 avenue de Condé, 59300 Valenciennes",
            "folder": "/tmp/vals",
        },
    },
    "tenants": {
        "Jin": {
            "title": "M",
            "first_name": "Jingyi",
            "last_name": "Luo",
            "email": "jin@example.com",
            "property": "anzin",
            "rent": 390.00,
            "charges": "60,50",
        },
        "Matilde": {
            "title": "Mlle",
            "first_name": "Matilde",
            "last_name": "Aranibar Campero",
            "email": "matilde@example.com, tuteur@example.com",
            "property": "anzin",
            "birth_date": "3 mars 2001",
            "birth_place": "La Paz, BOLIVIE",
        },
        "Xin": {
            "title": "Mlle",
            "first_name": "XinXuan",
            "last_name": "Li",
            "email": "xin@example.com",
            "property": "vals",
        },
    },
}


@pytest.fixture
def raw_config() -> dict:
    """Copie modifiable de la configuration de reference."""
    import copy

    return copy.deepcopy(RAW_CONFIG)


@pytest.fixture
def config(raw_config: dict) -> Config:
    """Config pointant sur les vraies images du depot."""
    return Config.from_dict(raw_config, base_dir=REPO_ROOT)


@pytest.fixture
def config_file(tmp_path: Path, raw_config: dict) -> Path:
    """config.yaml ecrit sur disque, images referencees en absolu."""
    for cle, chemin in raw_config["assets"].items():
        raw_config["assets"][cle] = str((REPO_ROOT / chemin).resolve())
    fichier = tmp_path / "config.yaml"
    fichier.write_text(
        yaml.safe_dump(raw_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return fichier
