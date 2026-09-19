from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from quittances.ajustements import Ajustement, Ajustements
from quittances.config import Config, ConfigError

NBSP = " "


def ecrire(tmp_path: Path, contenu: dict) -> Path:
    fichier = tmp_path / "ajustements.yaml"
    fichier.write_text(
        yaml.safe_dump(contenu, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return fichier


def test_journal_absent_est_vide(tmp_path: Path) -> None:
    """Ne rien ajuster est le cas normal : pas de fichier, pas d'erreur."""
    journal = Ajustements.load(base_dir=tmp_path)
    assert journal.entrees == {}
    assert journal.tous() == []


def test_charge_un_ajustement(config: Config, tmp_path: Path) -> None:
    fichier = ecrire(tmp_path, {"Jin": {"2026-09": {"charges": 20.0, "motif": "test"}}})
    journal = Ajustements.load(fichier, config.tenants)
    ajustement = journal.pour(config.tenant("Jin"), date(2026, 9, 1))
    assert ajustement is not None
    assert ajustement.charges == Decimal("20.00")
    assert ajustement.motif == "test"


def test_retrouve_le_mois_quel_que_soit_le_jour(
    config: Config, tmp_path: Path
) -> None:
    fichier = ecrire(tmp_path, {"Jin": {"2026-09": {"charges": 20.0}}})
    journal = Ajustements.load(fichier, config.tenants)
    assert journal.pour(config.tenant("Jin"), date(2026, 9, 28)) is not None


def test_mois_sans_ajustement(config: Config, tmp_path: Path) -> None:
    fichier = ecrire(tmp_path, {"Jin": {"2026-09": {"charges": 20.0}}})
    journal = Ajustements.load(fichier, config.tenants)
    assert journal.pour(config.tenant("Jin"), date(2026, 10, 1)) is None


def test_absent_met_les_charges_a_zero(config: Config, tmp_path: Path) -> None:
    """L'ete, le locataire ne consomme rien : c'est la regle par defaut."""
    fichier = ecrire(tmp_path, {"Jin": {"2026-08": {"absent": True}}})
    journal = Ajustements.load(fichier, config.tenants)
    ajustement = journal.pour(config.tenant("Jin"), date(2026, 8, 1))
    assert ajustement.charges_effectives == Decimal("0.00")
    assert ajustement.rent is None          # le loyer reste du


def test_absent_avec_charges_explicites(config: Config, tmp_path: Path) -> None:
    """Une absence peut laisser un abonnement a la charge du locataire."""
    fichier = ecrire(
        tmp_path, {"Jin": {"2026-08": {"absent": True, "charges": 15.0}}}
    )
    journal = Ajustements.load(fichier, config.tenants)
    ajustement = journal.pour(config.tenant("Jin"), date(2026, 8, 1))
    assert ajustement.charges_effectives == Decimal("15.00")


def test_locataire_inconnu_refuse(config: Config, tmp_path: Path) -> None:
    """Une faute de frappe facturerait le mois au tarif du bail, sans rien dire."""
    fichier = ecrire(tmp_path, {"Jinn": {"2026-09": {"charges": 20.0}}})
    with pytest.raises(ConfigError) as exc:
        Ajustements.load(fichier, config.tenants)
    assert "Jinn" in str(exc.value)
    assert "Jin" in str(exc.value)


def test_periode_invalide(config: Config, tmp_path: Path) -> None:
    fichier = ecrire(tmp_path, {"Jin": {"septembre": {"charges": 20.0}}})
    with pytest.raises(ConfigError, match="AAAA-MM"):
        Ajustements.load(fichier, config.tenants)


def test_champ_inconnu_refuse(config: Config, tmp_path: Path) -> None:
    """« charge » au lieu de « charges » serait ignore en silence."""
    fichier = ecrire(tmp_path, {"Jin": {"2026-09": {"charge": 20.0}}})
    with pytest.raises(ConfigError, match="charge"):
        Ajustements.load(fichier, config.tenants)


def test_montant_negatif_refuse(config: Config, tmp_path: Path) -> None:
    fichier = ecrire(tmp_path, {"Jin": {"2026-09": {"charges": -5}}})
    with pytest.raises(ConfigError, match="négatif"):
        Ajustements.load(fichier, config.tenants)


def test_entree_vide_acceptee(config: Config, tmp_path: Path) -> None:
    """Un mois note sans valeur ne change rien, mais reste dans le journal."""
    fichier = ecrire(tmp_path, {"Jin": {"2026-09": None}})
    journal = Ajustements.load(fichier, config.tenants)
    ajustement = journal.pour(config.tenant("Jin"), date(2026, 9, 1))
    assert ajustement.resume() == "aucun changement"


def test_resume_lisible(config: Config, tmp_path: Path) -> None:
    fichier = ecrire(
        tmp_path, {"Jin": {"2026-08": {"absent": True, "rent": 100}}}
    )
    journal = Ajustements.load(fichier, config.tenants)
    resume = journal.pour(config.tenant("Jin"), date(2026, 8, 1)).resume()
    assert resume == f"absent, loyer 100,00{NBSP}€, charges 0,00{NBSP}€"


def test_du_locataire_du_plus_recent_au_plus_ancien(
    config: Config, tmp_path: Path
) -> None:
    fichier = ecrire(
        tmp_path,
        {
            "Jin": {"2026-07": {"absent": True}, "2026-09": {"charges": 20.0}},
            "Matilde": {"2026-08": {"absent": True}},
        },
    )
    journal = Ajustements.load(fichier, config.tenants)
    periodes = [a.period for a in journal.du_locataire(config.tenant("Jin"))]
    assert periodes == [date(2026, 9, 1), date(2026, 7, 1)]


def test_yaml_invalide(config: Config, tmp_path: Path) -> None:
    fichier = tmp_path / "ajustements.yaml"
    fichier.write_text("Jin: [\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML invalide"):
        Ajustements.load(fichier, config.tenants)


def test_periode_normalisee_au_premier_du_mois(
    config: Config, tmp_path: Path
) -> None:
    fichier = ecrire(tmp_path, {"Jin": {"2026-09": {"charges": 20.0}}})
    journal = Ajustements.load(fichier, config.tenants)
    assert journal.tous()[0].period == date(2026, 9, 1)


def test_ajustement_isole_construit_a_la_main() -> None:
    """Le modele se construit sans fichier, pour les tests et l'usage direct."""
    ajustement = Ajustement(
        tenant_key="Jin", period=date(2026, 9, 1), charges=Decimal("20")
    )
    assert ajustement.period_label == "septembre 2026"
    assert not ajustement.absent
