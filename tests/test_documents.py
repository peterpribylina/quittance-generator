from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from quittances.config import Config
from quittances.documents import Attestation, DocumentError, Quittance, Relance

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


def build_relance(config: Config, mois: list[date], montant="450.50") -> Relance:
    return Relance(
        tenant=config.tenant("Jin"),
        months=tuple(mois),
        monthly_amount=Decimal(montant) if montant else None,
    )


def test_relance_un_seul_mois(config: Config) -> None:
    relance = build_relance(config, [date(2026, 9, 1)])
    assert relance.months_label == "septembre 2026"
    assert relance.email_subject == "Rappel : loyer de septembre 2026"
    texte, _ = relance.email_body("Peter")
    assert "au mois de septembre 2026" in texte
    assert "aux mois" not in texte


def test_relance_annee_ecrite_une_seule_fois(config: Config) -> None:
    relance = build_relance(
        config, [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]
    )
    assert relance.months_label == "juillet, août et septembre 2026"
    texte, _ = relance.email_body("Peter")
    assert "aux mois de juillet, août et septembre 2026" in texte


def test_relance_a_cheval_sur_deux_annees(config: Config) -> None:
    relance = build_relance(
        config, [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)]
    )
    assert relance.months_label == "novembre et décembre 2026, janvier 2027"


def test_relance_total_cumule(config: Config) -> None:
    relance = build_relance(config, [date(2026, 8, 1), date(2026, 9, 1)])
    assert relance.total == Decimal("901.00")
    texte, html = relance.email_body("Peter")
    assert f"901,00{NBSP}€" in texte
    assert f"<b>901,00{NBSP}€</b>" in html
    assert relance.email_subject == "Rappel : 2 loyers en attente"


def test_relance_sans_montant_connu(config: Config) -> None:
    """Un locataire sans loyer configure est relance sans chiffre."""
    relance = build_relance(config, [date(2026, 9, 1)], montant=None)
    assert relance.total is None
    texte, _ = relance.email_body("Peter")
    assert "montant total" not in texte
    assert "septembre 2026" in texte


def test_relance_sans_mois_refusee(config: Config) -> None:
    with pytest.raises(DocumentError, match="rien a relancer"):
        Relance(tenant=config.tenant("Jin"), months=())
