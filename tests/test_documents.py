from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from quittances.config import Config
from quittances.documents import Attestation, DocumentError, Quittance

NBSP = "\u00a0"  # espace insecable, cf. formatting.format_amount


def build_quittance(config: Config, **overrides) -> Quittance:
    params = {
        "tenant": config.tenant("Jin"),
        "period": date(2025, 9, 1),
        "payment_date": date(2025, 9, 1),
        "rent": Decimal("390.00"),
        "charges": Decimal("60.50"),
        "issued_on": date(2025, 9, 2),
    }
    params.update(overrides)
    return Quittance(**params)


def test_total_exact_en_decimal(config: Config) -> None:
    """L'ancien JS affichait « 400 » pour 320.00 + 80.00."""
    quittance = build_quittance(
        config, rent=Decimal("320.00"), charges=Decimal("80.00")
    )
    assert quittance.total == Decimal("400.00")
    assert quittance.total_label == f"400,00{NBSP}€"


def test_total_sans_erreur_de_flottant(config: Config) -> None:
    quittance = build_quittance(config, rent=Decimal("0.1"), charges=Decimal("0.2"))
    assert quittance.total == Decimal("0.30")


def test_libelles(config: Config) -> None:
    quittance = build_quittance(config)
    assert quittance.period_key == "2025-09"
    assert quittance.period_label == "septembre 2025"
    assert quittance.payment_date_label == "01/09/2025"
    assert quittance.issued_on_label == "02/09/2025"
    assert quittance.rent_label == f"390,00{NBSP}€"


def test_nom_de_fichier(config: Config) -> None:
    assert (
        build_quittance(config).filename
        == "Quittance_de_loyer_Jingyi_LUO_2025-09.pdf"
    )


def test_nom_de_fichier_avec_nom_compose(config: Config) -> None:
    quittance = build_quittance(config, tenant=config.tenant("Matilde"))
    assert (
        quittance.filename
        == "Quittance_de_loyer_Matilde_ARANIBAR_CAMPERO_2025-09.pdf"
    )


def test_chemin_de_sortie(config: Config, tmp_path: Path) -> None:
    chemin = build_quittance(config).output_path(tmp_path)
    assert chemin.parent == tmp_path / "Jingyi_Luo" / "Quittances"


def test_chemin_par_defaut_depuis_le_bien(config: Config) -> None:
    chemin = build_quittance(config).output_path()
    assert "Jingyi_Luo" in chemin.parts
    assert chemin.parts[-2] == "Quittances"


def test_montants_negatifs_refuses(config: Config) -> None:
    with pytest.raises(DocumentError, match="negatifs"):
        build_quittance(config, rent=Decimal("-1"))


def test_corps_de_mail(config: Config) -> None:
    texte, html = build_quittance(config).email_body("Peter")
    assert "Jingyi" in texte
    assert "septembre 2025" in texte
    assert "<b>septembre 2025</b>" in html


def test_attestation_exige_la_naissance(config: Config) -> None:
    """L'ancienne version imprimait « undefined » a la place."""
    with pytest.raises(DocumentError) as exc:
        Attestation(
            tenant=config.tenant("Jin"),
            hosted_since=date(2025, 9, 1),
            issued_on=date(2025, 9, 2),
        )
    assert "birth_date" in str(exc.value)
    assert "birth_place" in str(exc.value)


def test_attestation_valide(config: Config, tmp_path: Path) -> None:
    attestation = Attestation(
        tenant=config.tenant("Matilde"),
        hosted_since=date(2025, 9, 1),
        issued_on=date(2025, 9, 2),
    )
    assert attestation.hosted_since_label == "01/09/2025"
    assert attestation.filename.endswith("_2025.pdf")
    assert attestation.output_path(tmp_path).parts[-2] == "Docs"
