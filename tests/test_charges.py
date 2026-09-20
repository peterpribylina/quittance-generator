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


def test_reliquat_bailleur_si_depart_sans_preavis(
    raw_config: dict, tmp_path: Path
) -> None:
    """Sans preavis, le mois se prorate et le reste retombe sur le bailleur."""
    raw_config["tenants"]["Jin"]["share"] = 50.0
    raw_config["tenants"]["Jin"]["lease_start"] = "2026-01-01"
    raw_config["tenants"]["Matilde"]["share"] = 50.0
    raw_config["tenants"]["Matilde"]["lease_start"] = "2026-01-01"
    raw_config["tenants"]["Matilde"]["lease_end"] = "2026-01-15"
    raw_config["tenants"]["Matilde"]["preavis"] = False
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


def test_arrondi_absorbe_et_non_presente_comme_vacance(
    raw_config: dict, tmp_path: Path
) -> None:
    """Tous presents : l'ecart residuel est un arrondi, pas une chambre vide."""
    raw_config["tenants"]["Jin"]["share"] = 33.33
    raw_config["tenants"]["Jin"]["lease_start"] = "2025-09-01"
    raw_config["tenants"]["Matilde"]["share"] = 66.67
    raw_config["tenants"]["Matilde"]["lease_start"] = "2025-09-01"
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    bien = config.properties["anzin"]
    occupants = [t for t in config.tenants.values() if t.property.key == "anzin"]

    parts, reliquat = repartition(
        bien, Decimal("100.01"), occupants, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert reliquat == Decimal("0.00")
    assert sum(m for _, m in parts) == Decimal("100.01")


def test_preavis_rend_le_mois_de_depart_entierement_du(
    raw_config: dict, tmp_path: Path
) -> None:
    """Partir le 15 avec preavis ne dispense pas du mois : rien au bailleur."""
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
    assert montants["Matilde"] == Decimal("500.00")
    assert reliquat == Decimal("0.00")


def test_preavis_ne_deborde_pas_sur_le_mois_suivant(
    raw_config: dict, tmp_path: Path
) -> None:
    """Le mois de depart est du, pas le suivant."""
    raw_config["tenants"]["Jin"]["share"] = 50.0
    raw_config["tenants"]["Jin"]["lease_start"] = "2026-01-01"
    raw_config["tenants"]["Matilde"]["share"] = 50.0
    raw_config["tenants"]["Matilde"]["lease_start"] = "2026-01-01"
    raw_config["tenants"]["Matilde"]["lease_end"] = "2026-01-15"
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    matilde = config.tenant("Matilde")
    assert matilde.fin_due == date(2026, 1, 31)
    assert matilde.jours_occupes(date(2026, 2, 1), date(2026, 2, 28)) == 0


def test_les_postes_d_eau_forment_un_seul_groupe() -> None:
    """Le locataire lit « Eau », pas l'abonnement et la consommation separes."""
    from quittances.charges import groupe

    assert groupe("eau") == "Eau"
    assert groupe("eau_abonnement") == "Eau"
    assert groupe("eau_consommation") == "Eau"


def test_abonnement_sans_prefixe_reste_electrique() -> None:
    """« abonnement » vient des factures TotalEnergies : le prefixe tranche."""
    from quittances.charges import groupe

    assert groupe("abonnement") == "Électricité"
    assert groupe("consommation") == "Électricité"


def test_reference_decomposee_et_journal_ne_se_cumulent_pas(
    raw_config: dict, tmp_path: Path
) -> None:
    """Un poste du journal remplace sa reference, meme decomposee.

    La reference est passee de « eau » a « eau_abonnement »/« eau_consommation » :
    si le journal avait garde l'ancienne cle, l'eau aurait ete comptee deux fois.
    """
    raw_config["properties"]["anzin"]["monthly_charges"] = {
        "eau_abonnement": 4.79, "eau_consommation": 92.27, "internet": 51.0
    }
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    fichier = ecrire(
        tmp_path,
        {"anzin": {"2026-10": {"eau_abonnement": 4.88, "eau_consommation": 118.65}}},
    )
    journal = Charges.load(fichier, config.properties)
    du_mois = journal.du_mois(config.properties["anzin"], date(2026, 10, 1))
    assert du_mois.total == Decimal("174.53")     # 4,88 + 118,65 + 51
    assert du_mois.est_releve("eau_consommation")
    assert not du_mois.est_releve("internet")


def config_dediee(
    raw_config: dict, tmp_path: Path, postes: dict | None = None, **charges
) -> Config:
    """Deux locataires a 50 %, avec les charges dediees demandees."""
    for cle in ("Jin", "Matilde"):
        raw_config["tenants"][cle]["share"] = 50.0
        raw_config["tenants"][cle]["lease_start"] = "2025-09-01"
    for cle, lignes in charges.items():
        raw_config["tenants"][cle]["charges_dediees"] = lignes
    raw_config["properties"]["anzin"]["monthly_charges"] = postes or {
        "electricite": 200.0
    }
    return Config.from_dict(raw_config, base_dir=tmp_path)


def regul_anzin(config: Config, journal: Charges, mois=None):
    from quittances.charges import regularisations

    bien = config.properties["anzin"]
    occupants = [t for t in config.tenants.values() if t.property.key == "anzin"]
    return regularisations(
        bien, occupants, mois or [date(2026, 1, 1)], journal, None
    )


def test_charge_dediee_sort_de_la_repartition(
    raw_config: dict, tmp_path: Path
) -> None:
    """Le supplement est impute a lui seul ; le reste se partage a 50/50.

    C'est ce qui dispense de toucher aux quotes-parts : 100 % restent 100 %,
    appliques a un montant diminue.
    """
    config = config_dediee(
        raw_config, tmp_path,
        Jin=[{"groupe": "Électricité", "montant": 20.0, "motif": "Voiture"}],
    )
    lignes, totaux, reliquat = regul_anzin(config, Charges.vide())
    parts = {l.tenant.key: l for l in lignes}
    # 200 € - 20 € dedies = 180 € partages, 90 € chacun.
    assert totaux["Électricité"] == Decimal("180.00")
    assert parts["Jin"].reel["Électricité"] == Decimal("90.00")
    assert parts["Matilde"].reel["Électricité"] == Decimal("90.00")
    assert parts["Jin"].dediees == {"Voiture": Decimal("20.00")}
    assert parts["Matilde"].dediees == {}
    assert parts["Jin"].total_reel == Decimal("110.00")
    assert parts["Matilde"].total_reel == Decimal("90.00")
    assert reliquat == Decimal("0.00")


def test_la_maison_reste_soldee(raw_config: dict, tmp_path: Path) -> None:
    """Rien ne se cree ni ne se perd : les parts et le reliquat font le total."""
    config = config_dediee(
        raw_config, tmp_path,
        Jin=[{"groupe": "Électricité", "montant": 20.0, "motif": "Voiture"}],
        Matilde=[{"groupe": "Électricité", "montant": 10.0, "motif": "Radiateur"}],
    )
    lignes, totaux, reliquat = regul_anzin(config, Charges.vide())
    supporte = sum((l.total_reel for l in lignes), Decimal("0.00"))
    assert supporte + reliquat == Decimal("200.00")


def test_le_supplement_ne_depasse_pas_la_facture(
    raw_config: dict, tmp_path: Path
) -> None:
    """On ne peut pas imputer plus que le mois ne coute.

    Le cas se presente quand le journal ne porte qu'une part du groupe :
    l'abonnement seul, la consommation pas encore relevee.
    """
    config = config_dediee(
        raw_config, tmp_path,
        Jin=[{"groupe": "Électricité", "montant": 40.0, "motif": "Voiture"}],
        Matilde=[{"groupe": "Électricité", "montant": 20.0, "motif": "Radiateur"}],
    )
    fichier = ecrire(tmp_path, {"anzin": {"2026-01": {"electricite": 30.00}}})
    journal = Charges.load(fichier, config.properties)
    lignes, totaux, reliquat = regul_anzin(config, journal)
    parts = {l.tenant.key: l for l in lignes}
    # 60 € dus pour 30 € factures : rabattus au prorata, deux tiers / un tiers.
    assert parts["Jin"].dediees == {"Voiture": Decimal("20.00")}
    assert parts["Matilde"].dediees == {"Radiateur": Decimal("10.00")}
    assert totaux["Électricité"] == Decimal("0.00")
    assert sum((l.total_reel for l in lignes), Decimal("0.00")) == Decimal("30.00")


def test_le_supplement_suit_les_jours_occupes(
    raw_config: dict, tmp_path: Path
) -> None:
    """Partir le 15 ne fait pas recharger sa voiture jusqu'au 31."""
    config = config_dediee(
        raw_config, tmp_path,
        Jin=[{"groupe": "Électricité", "montant": 31.0, "motif": "Voiture"}],
    )
    raw = raw_config["tenants"]["Jin"]
    raw["lease_end"] = "2026-01-15"
    raw["preavis"] = False
    config = Config.from_dict(raw_config, base_dir=tmp_path)
    lignes, _, _ = regul_anzin(config, Charges.vide())
    parts = {l.tenant.key: l for l in lignes}
    assert parts["Jin"].dediees == {"Voiture": Decimal("15.00")}   # 15 j / 31


def test_le_supplement_ne_vise_que_son_groupe(
    raw_config: dict, tmp_path: Path
) -> None:
    """Une voiture ne consomme pas d'eau : l'eau reste a la surface."""
    config = config_dediee(
        raw_config, tmp_path,
        postes={"electricite": 200.0, "eau": 100.0},
        Jin=[{"groupe": "Électricité", "montant": 20.0, "motif": "Voiture"}],
    )
    _, totaux, _ = regul_anzin(config, Charges.vide())
    assert totaux["Eau"] == Decimal("100.00")        # intacte
    assert totaux["Électricité"] == Decimal("180.00")


def test_groupe_inconnu_refuse(raw_config: dict, tmp_path: Path) -> None:
    """« electricte » ne doit pas se deviner en « Electricite »."""
    with pytest.raises(ConfigError, match="inconnu"):
        config_dediee(
            raw_config, tmp_path,
            Jin=[{"groupe": "chauffage", "montant": 20.0, "motif": "Voiture"}],
        )


def test_accents_et_casse_ignores(raw_config: dict, tmp_path: Path) -> None:
    config = config_dediee(
        raw_config, tmp_path,
        Jin=[{"groupe": "ELECTRICITE", "montant": 20.0, "motif": "Voiture"}],
    )
    assert config.tenant("Jin").charges_dediees[0].groupe == "Électricité"


def test_motif_obligatoire(raw_config: dict, tmp_path: Path) -> None:
    """Un supplement non explique sur le document genere une question."""
    with pytest.raises(ConfigError, match="motif"):
        config_dediee(
            raw_config, tmp_path,
            Jin=[{"groupe": "Électricité", "montant": 20.0}],
        )


def test_montant_negatif_refuse(raw_config: dict, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="positif"):
        config_dediee(
            raw_config, tmp_path,
            Jin=[{"groupe": "Électricité", "montant": -20.0, "motif": "Voiture"}],
        )
