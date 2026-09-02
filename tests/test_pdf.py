from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from quittances.config import Config
from quittances.documents import Attestation, Quittance
from quittances.pdf import render_attestation, render_quittance

pypdf = pytest.importorskip("pypdf")

A4_POINTS = (595, 842)


def extract_text(path: Path) -> str:
    reader = pypdf.PdfReader(str(path))
    assert len(reader.pages) == 1
    # Le retour a la ligne du PDF ne doit pas faire echouer les recherches.
    return " ".join(reader.pages[0].extract_text().split())


@pytest.fixture
def quittance(config: Config) -> Quittance:
    return Quittance(
        tenant=config.tenant("Jin"),
        period=date(2025, 9, 1),
        payment_date=date(2025, 9, 1),
        rent=Decimal("390.00"),
        charges=Decimal("60.50"),
        issued_on=date(2025, 9, 2),
    )


def test_quittance_produit_un_pdf_a4(
    config: Config, quittance: Quittance, tmp_path: Path
) -> None:
    chemin = render_quittance(quittance, config, tmp_path / "q.pdf")
    assert chemin.is_file()
    page = pypdf.PdfReader(str(chemin)).pages[0]
    taille = (round(float(page.mediabox.width)), round(float(page.mediabox.height)))
    assert taille == A4_POINTS


def test_quittance_cree_les_dossiers_parents(
    config: Config, quittance: Quittance, tmp_path: Path
) -> None:
    """L'ancien `fs.createWriteStream` plantait si le dossier n'existait pas."""
    chemin = tmp_path / "a" / "b" / "c" / "q.pdf"
    assert render_quittance(quittance, config, chemin).is_file()


def test_quittance_contient_les_mentions_obligatoires(
    config: Config, quittance: Quittance, tmp_path: Path
) -> None:
    texte = extract_text(render_quittance(quittance, config, tmp_path / "q.pdf"))
    for attendu in (
        "Quittance de loyer",
        "Loyer septembre 2025",
        "M. LUO Jingyi",
        "01/09/2025",
        "3 impasse Lecomte, 59410 Anzin",
        "en paiement du terme du mois septembre 2025",
        "Fait à Marcq en Baroeul le 02/09/2025",
        "M. PRIBYLINA Peter",
        "Sous réserve d'encaissement.",
    ):
        assert attendu in texte, f"« {attendu} » absent du PDF"


def test_quittance_affiche_les_montants_en_francais(
    config: Config, quittance: Quittance, tmp_path: Path
) -> None:
    texte = extract_text(render_quittance(quittance, config, tmp_path / "q.pdf"))
    assert "390,00" in texte
    assert "60,50" in texte
    assert texte.count("450,50") == 3  # somme recue, total du terme, paiement
    assert "0,00" in texte  # solde a payer


def test_quittance_nom_compose_entierement_affiche(
    config: Config, tmp_path: Path
) -> None:
    quittance = Quittance(
        tenant=config.tenant("Matilde"),
        period=date(2025, 9, 1),
        payment_date=date(2025, 9, 1),
        rent=Decimal("400"),
        charges=Decimal("0"),
        issued_on=date(2025, 9, 2),
    )
    texte = extract_text(render_quittance(quittance, config, tmp_path / "q.pdf"))
    assert "ARANIBAR CAMPERO" in texte


def test_attestation_produit_un_pdf(config: Config, tmp_path: Path) -> None:
    """L'ancienne version plantait sur `generateFooter` inexistant."""
    attestation = Attestation(
        tenant=config.tenant("Matilde"),
        hosted_since=date(2025, 9, 1),
        issued_on=date(2025, 9, 2),
    )
    texte = extract_text(render_attestation(attestation, config, tmp_path / "a.pdf"))
    assert "ATTESTATION D'HÉBERGEMENT" in texte
    assert "Je soussigné Peter PRIBYLINA" in texte
    assert "Mlle. ARANIBAR CAMPERO Matilde" in texte
    assert "La Paz, BOLIVIE" in texte
    assert "depuis le 01/09/2025" in texte
    assert "undefined" not in texte


def test_attestation_accorde_le_participe(config: Config, tmp_path: Path) -> None:
    attestation = Attestation(
        tenant=config.tenant("Matilde"),
        hosted_since=date(2025, 9, 1),
        issued_on=date(2025, 9, 2),
    )
    texte = extract_text(render_attestation(attestation, config, tmp_path / "a.pdf"))
    assert "née le 3 mars 2001" in texte


def test_caracteres_speciaux_echappes(
    config: Config, raw_config: dict, tmp_path: Path
) -> None:
    """Une esperluette dans une adresse ne doit pas casser le balisage."""
    raw_config["properties"]["anzin"]["address"] = "3 rue Dupont & Fils, 59410 Anzin"
    config_modifiee = Config.from_dict(
        raw_config, base_dir=Path(__file__).resolve().parent.parent
    )
    quittance = Quittance(
        tenant=config_modifiee.tenant("Jin"),
        period=date(2025, 9, 1),
        payment_date=date(2025, 9, 1),
        rent=Decimal("390"),
        charges=Decimal("0"),
        issued_on=date(2025, 9, 2),
    )
    texte = extract_text(render_quittance(quittance, config_modifiee, tmp_path / "q.pdf"))
    assert "Dupont & Fils" in texte
