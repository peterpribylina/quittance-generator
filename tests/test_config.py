from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from quittances.config import Config, ConfigError


def test_chargement_depuis_fichier(config_file: Path) -> None:
    config = Config.load(config_file)
    assert set(config.tenants) == {"Jin", "Matilde", "Xin"}
    assert config.landlord.display_name == "M. PRIBYLINA Peter"
    assert config.landlord.legal_name == "Peter PRIBYLINA"


def test_fichier_absent(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="introuvable"):
        Config.load(tmp_path / "absent.yaml")


def test_recherche_locataire_insensible_a_la_casse(config: Config) -> None:
    assert config.tenant("jin").key == "Jin"
    assert config.tenant("JIN").key == "Jin"


def test_locataire_inconnu_liste_les_cles(config: Config) -> None:
    with pytest.raises(ConfigError) as exc:
        config.tenant("Victor")
    message = str(exc.value)
    assert "Victor" in message
    assert "Jin" in message


def test_nom_compose_conserve_integralement(config: Config) -> None:
    """L'ancien `fullName.split(" ")[1]` perdait « Campero »."""
    matilde = config.tenant("Matilde")
    assert matilde.last_name == "Aranibar Campero"
    assert matilde.display_name == "Mlle. ARANIBAR CAMPERO Matilde"
    assert matilde.slug == "Matilde_Aranibar_Campero"


def test_emails_multiples_separes_par_virgule(config: Config) -> None:
    assert config.tenant("Matilde").emails == (
        "matilde@example.com",
        "tuteur@example.com",
    )


def test_montants_convertis_en_decimal(config: Config) -> None:
    jin = config.tenant("Jin")
    assert jin.rent == Decimal("390.00")
    assert jin.charges == Decimal("60.50")


def test_montants_facultatifs(config: Config) -> None:
    assert config.tenant("Xin").rent is None
    assert config.tenant("Xin").charges is None


def test_locataire_rattache_a_son_bien(config: Config) -> None:
    assert config.tenant("Jin").address == "3 impasse Lecomte, 59410 Anzin"


def test_bien_inconnu(raw_config: dict, tmp_path: Path) -> None:
    raw_config["tenants"]["Jin"]["property"] = "roubaix"
    with pytest.raises(ConfigError, match="roubaix"):
        Config.from_dict(raw_config, base_dir=tmp_path)


@pytest.mark.parametrize("champ", ["first_name", "last_name", "property"])
def test_champ_obligatoire_manquant(
    raw_config: dict, tmp_path: Path, champ: str
) -> None:
    del raw_config["tenants"]["Jin"][champ]
    with pytest.raises(ConfigError, match=champ):
        Config.from_dict(raw_config, base_dir=tmp_path)


def test_montant_invalide_en_configuration(raw_config: dict, tmp_path: Path) -> None:
    raw_config["tenants"]["Jin"]["rent"] = "beaucoup"
    with pytest.raises(ConfigError, match="Montant invalide"):
        Config.from_dict(raw_config, base_dir=tmp_path)


def test_images_presentes(config: Config) -> None:
    assert config.assets.missing() == []


def test_images_absentes_signalees(raw_config: dict, tmp_path: Path) -> None:
    raw_config["assets"]["logo"] = "img/inexistant.png"
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    assert len(config.assets.missing()) == 3


def test_civilite_facultative(raw_config: dict, tmp_path: Path) -> None:
    """Sans titre configure, la civilite est omise plutot que devinee."""
    del raw_config["tenants"]["Jin"]["title"]
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    tenant = config.tenant("Jin")
    assert tenant.title is None
    assert tenant.display_name == "LUO Jingyi"


def test_email_facultatif(raw_config: dict, tmp_path: Path) -> None:
    del raw_config["tenants"]["Jin"]["email"]
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    assert config.tenant("Jin").emails == ()


def test_nom_abrege(config: Config) -> None:
    assert config.tenant("Jin").short_name == "Jingyi L."


def test_nom_abrege_avec_nom_compose(config: Config) -> None:
    """Un nom compose est abrege sur sa premiere lettre, pas sur chaque mot."""
    assert config.tenant("Matilde").short_name == "Matilde A."


def test_nom_complet_intact(config: Config) -> None:
    """L'abreviation est un choix d'affichage : les documents gardent le nom."""
    assert config.tenant("Matilde").full_name == "Matilde Aranibar Campero"
