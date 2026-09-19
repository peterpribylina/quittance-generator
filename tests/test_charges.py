from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from quittances.charges import Charges, repartition
from quittances.config import Config, ConfigError


def ecrire(tmp_path: Path, contenu: dict) -> Path:
    fichier = tmp_path / "charges.yaml"
    fichier.write_text(
        yaml.safe_dump(contenu, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return fichier


@pytest.fixture
def config_avec_charges(raw_config: dict, tmp_path: Path) -> Config:
    raw_config["properties"]["anzin"]["monthly_charges"] = {
        "eau": 80.0, "internet": 51.0
    }
    raw_config["tenants"]["Jin"]["share"] = 60.0
    raw_config["tenants"]["Matilde"]["share"] = 40.0
    return Config.from_dict(raw_config, base_dir=tmp_path)


def test_charges_fixes_sans_journal(config_avec_charges: Config, tmp_path: Path) -> None:
    """Sans releve, les charges valent la reference du bail."""
    journal = Charges.load(base_dir=tmp_path)
    du_mois = journal.du_mois(config_avec_charges.properties["anzin"], date(2026, 1, 1))
    assert du_mois.total == Decimal("131.00")
    assert not du_mois.est_releve("eau")


def test_poste_releve_s_ajoute(config_avec_charges: Config, tmp_path: Path) -> None:
    """L'electricite n'a pas de reference : elle s'ajoute au total."""
    fichier = ecrire(tmp_path, {"anzin": {"2026-01": {"electricite": 348.30}}})
    journal = Charges.load(fichier, config_avec_charges.properties)
    du_mois = journal.du_mois(config_avec_charges.properties["anzin"], date(2026, 1, 1))
    assert du_mois.total == Decimal("479.30")
    assert du_mois.est_releve("electricite")
    assert not du_mois.est_releve("eau")


def test_poste_releve_remplace_la_reference(
    config_avec_charges: Config, tmp_path: Path
) -> None:
    """Une facture d'eau reelle l'emporte sur le montant presume."""
    fichier = ecrire(tmp_path, {"anzin": {"2026-01": {"eau": 96.40}}})
    journal = Charges.load(fichier, config_avec_charges.properties)
    du_mois = journal.du_mois(config_avec_charges.properties["anzin"], date(2026, 1, 1))
    assert du_mois.postes["eau"] == Decimal("96.40")
    assert du_mois.total == Decimal("147.40")     # 96,40 + 51
    assert du_mois.est_releve("eau")


def test_mois_sans_releve(config_avec_charges: Config, tmp_path: Path) -> None:
    fichier = ecrire(tmp_path, {"anzin": {"2026-01": {"electricite": 348.30}}})
    journal = Charges.load(fichier, config_avec_charges.properties)
    du_mois = journal.du_mois(config_avec_charges.properties["anzin"], date(2026, 2, 1))
    assert du_mois.total == Decimal("131.00")
    assert "electricite" not in du_mois.postes


def test_maison_inconnue_refusee(config_avec_charges: Config, tmp_path: Path) -> None:
    fichier = ecrire(tmp_path, {"roubaix": {"2026-01": {"electricite": 10}}})
    with pytest.raises(ConfigError, match="roubaix"):
        Charges.load(fichier, config_avec_charges.properties)


def test_charge_negative_refusee(config_avec_charges: Config, tmp_path: Path) -> None:
    fichier = ecrire(tmp_path, {"anzin": {"2026-01": {"electricite": -10}}})
    with pytest.raises(ConfigError, match="négative"):
        Charges.load(fichier, config_avec_charges.properties)


def test_periode_invalide(config_avec_charges: Config, tmp_path: Path) -> None:
    fichier = ecrire(tmp_path, {"anzin": {"janvier": {"electricite": 10}}})
    with pytest.raises(ConfigError, match="AAAA-MM"):
        Charges.load(fichier, config_avec_charges.properties)


def test_journal_absent_est_vide(tmp_path: Path) -> None:
    assert Charges.load(base_dir=tmp_path).entrees == {}


def test_repartition_au_prorata(config_avec_charges: Config) -> None:
    bien = config_avec_charges.properties["anzin"]
    occupants = [
        t for t in config_avec_charges.tenants.values() if t.property.key == "anzin"
    ]
    # Tenant n'est plus hachable depuis que Property porte un dictionnaire :
    # on indexe par cle, pas par objet.
    parts, reliquat = repartition(bien, Decimal("1000.00"), occupants)
    montants = {t.key: m for t, m in parts}
    assert reliquat == Decimal("0.00")
    assert montants["Jin"] == Decimal("600.00")
    assert montants["Matilde"] == Decimal("400.00")


def test_repartition_somme_exactement_le_total(
    config_avec_charges: Config
) -> None:
    """Un centime perdu par ligne finirait par se voir sur un exercice."""
    bien = config_avec_charges.properties["anzin"]
    occupants = [
        t for t in config_avec_charges.tenants.values() if t.property.key == "anzin"
    ]
    for total in ("100.01", "333.33", "1234.57", "0.01"):
        parts, reliquat = repartition(bien, Decimal(total), occupants)
        assert sum(m for _, m in parts) + reliquat == Decimal(total), total


def test_repartition_sans_quote_part(config: Config) -> None:
    bien = config.properties["anzin"]
    occupants = [t for t in config.tenants.values() if t.property.key == "anzin"]
    parts, reliquat = repartition(bien, Decimal("100"), occupants)
    assert parts == []
    assert reliquat == Decimal("100")     # tout reste au bailleur


def test_total_des_charges_fixes(config_avec_charges: Config) -> None:
    assert (
        config_avec_charges.properties["anzin"].monthly_charges_total
        == Decimal("131.00")
    )


def test_charge_fixe_negative_refusee(raw_config: dict, tmp_path: Path) -> None:
    raw_config["properties"]["anzin"]["monthly_charges"] = {"eau": -5}
    with pytest.raises(ConfigError, match="negatif"):
        Config.from_dict(raw_config, base_dir=tmp_path)


def test_reliquat_bailleur_si_chambre_vacante(
    raw_config: dict, tmp_path: Path
) -> None:
    """Un locataire parti en cours de periode laisse sa part au bailleur."""
    raw_config["tenants"]["Jin"]["share"] = 50.0
    raw_config["tenants"]["Jin"]["lease_start"] = "2026-01-01"
    raw_config["tenants"]["Matilde"]["share"] = 50.0
    raw_config["tenants"]["Matilde"]["lease_start"] = "2026-01-01"
    raw_config["tenants"]["Matilde"]["lease_end"] = "2026-01-15"
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    bien = config.properties["anzin"]
    occupants = [t for t in config.tenants.values() if t.property.key == "anzin"]

    parts, reliquat = repartition(
        bien, Decimal("1000.00"), occupants, date(2026, 1, 1), date(2026, 1, 31)
    )
    montants = {t.key: m for t, m in parts}
    assert montants["Jin"] == Decimal("500.00")          # present tout le mois
    assert montants["Matilde"] == Decimal("241.94")      # 15 jours sur 31
    assert reliquat == Decimal("258.06")                 # chambre vacante
    assert sum(montants.values()) + reliquat == Decimal("1000.00")


def test_pas_de_reliquat_si_tous_presents(raw_config: dict, tmp_path: Path) -> None:
    raw_config["tenants"]["Jin"]["share"] = 50.0
    raw_config["tenants"]["Jin"]["lease_start"] = "2025-09-01"
    raw_config["tenants"]["Matilde"]["share"] = 50.0
    raw_config["tenants"]["Matilde"]["lease_start"] = "2025-09-01"
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    bien = config.properties["anzin"]
    occupants = [t for t in config.tenants.values() if t.property.key == "anzin"]

    _, reliquat = repartition(
        bien, Decimal("1000.00"), occupants, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert reliquat == Decimal("0.00")


def test_locataire_pas_encore_entre(raw_config: dict, tmp_path: Path) -> None:
    raw_config["tenants"]["Jin"]["share"] = 50.0
    raw_config["tenants"]["Jin"]["lease_start"] = "2026-02-01"
    raw_config["tenants"]["Matilde"]["share"] = 50.0
    raw_config["tenants"]["Matilde"]["lease_start"] = "2025-09-01"
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    bien = config.properties["anzin"]
    occupants = [t for t in config.tenants.values() if t.property.key == "anzin"]

    parts, reliquat = repartition(
        bien, Decimal("1000.00"), occupants, date(2026, 1, 1), date(2026, 1, 31)
    )
    montants = {t.key: m for t, m in parts}
    assert montants["Jin"] == Decimal("0.00")
    assert reliquat == Decimal("500.00")
