"""Montants portes a la main sur une regularisation.

Le point sensible est le **signe**. En configuration il se lit en faveur du
locataire — un geste commercial est positif — alors que le solde compte ce que
le locataire doit. Une inversion passee inapercue transformerait un cadeau en
dette, d'ou le nombre de tests qui verifient le sens plutot que la valeur.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from quittances.config import Config, ConfigError, LigneManuelle
from quittances.documents import Regularisation

# Espace insecable, cf. formatting.format_amount. Ecrit sous forme
# d'echappement : un espace ordinaire glisse dans l'attendu
# rendrait le test faussement vert.
NBSP = "\u00a0"

pypdf = pytest.importorskip("pypdf")

from quittances.pdf import render_regularisation  # noqa: E402


REEL = {"Eau": Decimal("11.91"), "Internet": Decimal("6.08")}
TOTAUX = {"Eau": Decimal("100.00"), "Internet": Decimal("51.00")}


def regul(config: Config, *lignes: LigneManuelle) -> Regularisation:
    return Regularisation(
        tenant=config.tenant("Jin"),
        debut=date(2026, 9, 1),
        fin=date(2026, 9, 30),
        reel=REEL,
        totaux_maison=TOTAUX,
        provisions=Decimal("60.50"),
        issued_on=date(2026, 9, 19),
        jours_dus=19,
        jours_periode=30,
        lignes=lignes,
    )


def texte_pdf(chemin: Path) -> str:
    """Texte de toutes les pages, espaces aplatis.

    `str.split()` coupe aussi sur l'espace insecable : les montants ressortent
    donc avec un espace ordinaire, et c'est ainsi qu'il faut les attendre ici.
    La typographie fine est verifiee sur `format_amount`, pas sur le PDF.
    """
    reader = pypdf.PdfReader(str(chemin))
    pages = (page.extract_text() or "" for page in reader.pages)
    return " ".join(" ".join(pages).split())


# --- Lecture de la configuration ---------------------------------------


def avec_lignes(raw_config: dict, *lignes: dict) -> dict:
    raw_config["tenants"]["Jin"]["lignes_manuelles"] = list(lignes)
    return raw_config


def test_lignes_manuelles_lues(raw_config: dict, tmp_path: Path) -> None:
    config = Config.from_dict(
        avec_lignes(
            raw_config,
            {"date": "2026-09-30", "libelle": "Geste commercial", "montant": 50},
            {"date": "30/09/2026", "libelle": "Dégradations", "montant": "-120,00"},
        ),
        base_dir=tmp_path,
    )
    geste, degats = config.tenant("Jin").lignes_manuelles
    assert geste.montant == Decimal("50")
    assert degats.montant == Decimal("-120.00")
    assert degats.date == date(2026, 9, 30)


def test_le_signe_est_toujours_porte(raw_config: dict, tmp_path: Path) -> None:
    """« Dégradations 120,00 € » ne dirait pas si la somme est retenue."""
    config = Config.from_dict(
        avec_lignes(
            raw_config,
            {"date": "2026-09-30", "libelle": "Geste", "montant": 50},
            {"date": "2026-09-30", "libelle": "Dégâts", "montant": -120},
        ),
        base_dir=tmp_path,
    )
    geste, degats = config.tenant("Jin").lignes_manuelles
    assert geste.montant_label == f"+50,00{NBSP}€"
    assert degats.montant_label == f"-120,00{NBSP}€"


def test_libelle_obligatoire(raw_config: dict, tmp_path: Path) -> None:
    """Un montant sans explication sur le document genere une question."""
    with pytest.raises(ConfigError, match="libelle"):
        Config.from_dict(
            avec_lignes(raw_config, {"date": "2026-09-30", "montant": 50}),
            base_dir=tmp_path,
        )


def test_libelle_vide_refuse(raw_config: dict, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="libelle"):
        Config.from_dict(
            avec_lignes(
                raw_config,
                {"date": "2026-09-30", "libelle": "   ", "montant": 50},
            ),
            base_dir=tmp_path,
        )


def test_date_obligatoire(raw_config: dict, tmp_path: Path) -> None:
    """Sans date, la ligne ne se rattache a aucune regularisation."""
    with pytest.raises(ConfigError, match="date"):
        Config.from_dict(
            avec_lignes(raw_config, {"libelle": "Geste", "montant": 50}),
            base_dir=tmp_path,
        )


def test_montant_obligatoire(raw_config: dict, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="montant"):
        Config.from_dict(
            avec_lignes(raw_config, {"date": "2026-09-30", "libelle": "Geste"}),
            base_dir=tmp_path,
        )


def test_montant_nul_refuse(raw_config: dict, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="nul"):
        Config.from_dict(
            avec_lignes(
                raw_config,
                {"date": "2026-09-30", "libelle": "Geste", "montant": 0},
            ),
            base_dir=tmp_path,
        )


def test_champ_mal_orthographie_refuse(raw_config: dict, tmp_path: Path) -> None:
    """« motif » au lieu de « libelle » laisserait la ligne sans explication."""
    with pytest.raises(ConfigError, match="motif"):
        Config.from_dict(
            avec_lignes(
                raw_config,
                {"date": "2026-09-30", "motif": "Geste", "montant": 50},
            ),
            base_dir=tmp_path,
        )


def test_mapping_au_lieu_d_une_liste_refuse(raw_config: dict, tmp_path: Path) -> None:
    raw_config["tenants"]["Jin"]["lignes_manuelles"] = {
        "2026-09-30": {"libelle": "Geste", "montant": 50}
    }
    with pytest.raises(ConfigError, match="liste"):
        Config.from_dict(raw_config, base_dir=tmp_path)


def test_selection_par_periode(raw_config: dict, tmp_path: Path) -> None:
    """Plusieurs regularisations coexistent : chacune ne reprend que les siennes."""
    config = Config.from_dict(
        avec_lignes(
            raw_config,
            {"date": "2026-09-30", "libelle": "Geste 2026", "montant": 50},
            {"date": "2027-08-31", "libelle": "Geste 2027", "montant": 30},
        ),
        base_dir=tmp_path,
    )
    tenant = config.tenant("Jin")
    retenues = tenant.lignes_manuelles_entre(date(2026, 9, 1), date(2027, 8, 30))
    assert [l.libelle for l in retenues] == ["Geste 2026"]
    assert tenant.lignes_manuelles_entre(date(2027, 1, 1), date(2027, 12, 31)) == (
        tenant.lignes_manuelles[1],
    )


def test_bornes_incluses(raw_config: dict, tmp_path: Path) -> None:
    config = Config.from_dict(
        avec_lignes(
            raw_config,
            {"date": "2026-09-01", "libelle": "Premier jour", "montant": 10},
            {"date": "2026-09-30", "libelle": "Dernier jour", "montant": 10},
        ),
        base_dir=tmp_path,
    )
    retenues = config.tenant("Jin").lignes_manuelles_entre(
        date(2026, 9, 1), date(2026, 9, 30)
    )
    assert len(retenues) == 2


def test_aucune_ligne_par_defaut(config: Config) -> None:
    assert config.tenant("Jin").lignes_manuelles == ()


# --- Sens du signe dans le document ------------------------------------


def test_sans_ligne_le_solde_est_inchange(config: Config) -> None:
    nu = regul(config)
    assert nu.total_lignes == Decimal("0.00")
    assert nu.solde == Decimal("17.99") - Decimal("60.50")


def test_geste_commercial_augmente_la_restitution(config: Config) -> None:
    """Positif en configuration = en faveur du locataire."""
    nu = regul(config)
    avec = regul(config, LigneManuelle(date(2026, 9, 30), "Geste", Decimal("50")))
    assert avec.solde == nu.solde - Decimal("50.00")
    assert avec.montant_du == nu.montant_du + Decimal("50.00")
    assert avec.libelle_solde == "Montant à restituer"


def test_degradations_alourdissent_la_dette(config: Config) -> None:
    """Negatif en configuration = retenu au locataire."""
    nu = regul(config)
    avec = regul(config, LigneManuelle(date(2026, 9, 30), "Dégâts", Decimal("-120")))
    assert avec.solde == nu.solde + Decimal("120.00")
    assert avec.solde > 0
    assert avec.libelle_solde == "Reste à payer"


def test_lignes_qui_se_compensent(config: Config) -> None:
    nu = regul(config)
    avec = regul(
        config,
        LigneManuelle(date(2026, 9, 30), "Geste", Decimal("80")),
        LigneManuelle(date(2026, 9, 30), "Dégâts", Decimal("-80")),
    )
    assert avec.total_lignes == Decimal("0.00")
    assert avec.solde == nu.solde


def test_le_total_reel_ignore_les_lignes(config: Config) -> None:
    """Les lignes manuelles ne sont pas des charges : le tableau reste juste."""
    avec = regul(config, LigneManuelle(date(2026, 9, 30), "Geste", Decimal("50")))
    assert avec.total_reel == Decimal("17.99")


# --- Restitution dans l'email ------------------------------------------


def test_lignes_reprises_dans_l_email(config: Config) -> None:
    avec = regul(
        config,
        LigneManuelle(date(2026, 9, 30), "Geste commercial", Decimal("50")),
        LigneManuelle(date(2026, 9, 30), "Dégradations", Decimal("-120")),
    )
    texte, html = avec.email_body("Peter")
    for corps in (texte, html):
        assert "Geste commercial" in corps
        assert "Dégradations" in corps
        assert f"+50,00{NBSP}€" in corps
        assert f"-120,00{NBSP}€" in corps
        assert "positif est en ta faveur" in corps


def test_email_muet_sans_ligne(config: Config) -> None:
    texte, html = regul(config).email_body("Peter")
    assert "portée à la main" not in texte
    assert "en ta faveur" not in html


# --- Restitution dans le PDF -------------------------------------------


def test_pdf_porte_libelle_et_signe(config: Config, tmp_path: Path) -> None:
    avec = regul(
        config,
        LigneManuelle(date(2026, 9, 30), "Geste commercial", Decimal("50")),
        LigneManuelle(date(2026, 9, 30), "Dégradations", Decimal("-120")),
    )
    texte = texte_pdf(render_regularisation(avec, config, tmp_path / "r.pdf"))
    assert "Geste commercial" in texte
    assert "Dégradations" in texte
    assert "+50,00 €" in texte
    assert "-120,00 €" in texte
    assert "Un montant positif est en votre faveur." in texte


def test_pdf_libelle_long_n_est_pas_tronque(config: Config, tmp_path: Path) -> None:
    """Tronquer priverait le locataire de l'explication qu'il doit lire."""
    libelle = (
        "Retenue pour la remise en état du mur de la chambre et le "
        "remplacement de la poignée de la porte-fenêtre du salon"
    )
    avec = regul(config, LigneManuelle(date(2026, 9, 30), libelle, Decimal("-120")))
    texte = texte_pdf(render_regularisation(avec, config, tmp_path / "r.pdf"))
    assert libelle in texte


def test_la_cloture_passe_a_la_page_suivante(
    config: Config, tmp_path: Path
) -> None:
    """Le bloc signature bascule plutot que de deborder sous le bord.

    Il mesure 192 pt : un document long le poussait hors de la page.
    """
    beaucoup = tuple(
        LigneManuelle(date(2026, 9, 30), f"Ligne {i}", Decimal("10"))
        for i in range(8)
    )
    chemin = render_regularisation(regul(config, *beaucoup), config, tmp_path / "r.pdf")
    reader = pypdf.PdfReader(str(chemin))
    assert len(reader.pages) == 2
    # Le bloc de cloture est bien sur la seconde page, pas ecrase sur la
    # premiere. Le libelle de signature est capitalise par `_label`.
    seconde = " ".join(reader.pages[1].extract_text().split())
    assert "Fait à" in seconde
    premiere = " ".join(reader.pages[0].extract_text().split())
    assert "Fait à" not in premiere


def test_regularisation_courte_tient_sur_une_page(
    config: Config, tmp_path: Path
) -> None:
    chemin = render_regularisation(regul(config), config, tmp_path / "r.pdf")
    assert len(pypdf.PdfReader(str(chemin)).pages) == 1


# --- Email bilingue ----------------------------------------------------


def test_email_porte_les_deux_langues(config: Config) -> None:
    """Le decompte reste francais, l'envoi qui l'accompagne ne l'est pas."""
    texte, html = regul(config).email_body("Peter")
    for corps in (texte, html):
        assert "Bonjour Jingyi" in corps
        assert "Hi Jingyi" in corps
        assert "Bien à toi" in corps
        assert "Best," in corps


def test_objet_bilingue(config: Config) -> None:
    objet = regul(config).email_subject
    assert "Régularisation de charges" in objet
    assert "Service charge statement" in objet


def test_conventions_anglaises(config: Config) -> None:
    """« €450.50 » et non « 450,50 € », mois en toutes lettres."""
    r = regul(config)
    texte, _ = r.email_body("Peter")
    assert "€60.50" in texte                      # provisions
    assert "1 September 2026" in r.periode_label_en
    assert "01/09/2026" in r.periode_label        # le francais garde sa forme


def test_le_cout_mensuel_est_dit_dans_les_deux_langues(config: Config) -> None:
    """La comparaison au mois est ce qui parle au locataire."""
    r = regul(config)
    texte, html = r.email_body("Peter")
    assert r.comparaison in texte
    assert "per month against" in texte
    assert "per month against" in html


def test_les_motifs_ne_sont_pas_traduits(config: Config) -> None:
    """Libelles et motifs sont saisis a la main : ils valent tels quels."""
    avec = regul(
        config, LigneManuelle(date(2026, 9, 30), "Geste commercial", Decimal("50"))
    )
    texte, html = avec.email_body("Peter")
    assert texte.count("Geste commercial") == 2   # une fois par langue
    # Le HTML capitalise la mention, le texte non : on compare sans la casse.
    for corps in (texte, html):
        assert "positive amount is in your favour" in corps.lower()
