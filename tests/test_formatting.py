from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from quittances.formatting import (
    format_amount,
    format_date,
    month_name,
    month_year,
    parse_amount,
)

NBSP = "\u00a0"  # espace insecable, cf. formatting.format_amount


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (Decimal("400"), f"400,00{NBSP}€"),
        (Decimal("390.5"), f"390,50{NBSP}€"),
        (Decimal("1234.5"), f"1{NBSP}234,50{NBSP}€"),
        (Decimal("1234567.89"), f"1{NBSP}234{NBSP}567,89{NBSP}€"),
        (Decimal("0"), f"0,00{NBSP}€"),
        (Decimal("-12.3"), f"-12,30{NBSP}€"),
    ],
)
def test_format_amount(valeur: Decimal, attendu: str) -> None:
    assert format_amount(valeur) == attendu


def test_format_amount_arrondit_au_centime() -> None:
    assert format_amount(Decimal("10.005")) == f"10,00{NBSP}€"
    assert format_amount(Decimal("10.006")) == f"10,01{NBSP}€"


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("390.00", Decimal("390.00")),
        ("390,00", Decimal("390.00")),
        ("1 234,50", Decimal("1234.50")),
        ("450,50 €", Decimal("450.50")),
        (390, Decimal("390")),
        (390.5, Decimal("390.5")),
        (Decimal("1.23"), Decimal("1.23")),
    ],
)
def test_parse_amount(brut: object, attendu: Decimal) -> None:
    assert parse_amount(brut) == attendu


@pytest.mark.parametrize("brut", ["", "abc", "12,34,56", None, True])
def test_parse_amount_rejette_les_valeurs_invalides(brut: object) -> None:
    with pytest.raises(ValueError):
        parse_amount(brut)


def test_month_name_accentue() -> None:
    assert month_name(2) == "février"
    assert month_name(8) == "août"
    assert month_name(9) == "septembre"


def test_month_name_hors_bornes() -> None:
    with pytest.raises(ValueError):
        month_name(13)


def test_month_year_ne_depend_pas_de_la_locale() -> None:
    assert month_year(date(2025, 9, 15)) == "septembre 2025"


def test_format_date() -> None:
    assert format_date(date(2025, 9, 1)) == "01/09/2025"
