"""Lecture des factures d'electricite.

Le module n'avait aucun test, et une troncature de periode y a survecu
longtemps : la consommation detaillee en plusieurs tranches n'etait lue que sur
la premiere, ce qui amputait le mois et faisait passer des mois complets pour
incomplets. Les fonctions pures se testent sans PDF, c'est ce qui est fait ici.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from quittances.factures import (
    FIXE,
    VARIABLE,
    Facture,
    Poste,
    _periode_de_section,
    categories,
    mois_complets,
    prorata_mensuel,
)


# --- Periodes d'une section --------------------------------------------


def test_periode_couvre_toutes_les_sous_periodes() -> None:
    """Un tarif qui change en cours de mois scinde la consommation.

    Ne retenir que « du 29/01 au 31/01 » amputait le mois de fevrier entier.
    """
    detail = [
        "Consommation d'électricité (HT) ... 227,40 €",
        "Période du 29/01/25 au 31/01/25 Relevé Enedis Estimé",
        "Heures Pleines 23512 23641 129 129 0,2119 27,34 €",
        "Période du 01/02/25 au 28/02/25 Estimé Relevé Enedis",
        "Heures Creuses 6195 6426 231 231 0,1076 24,86 €",
        "Offres promotionnelles et réductions (HT) -1,67 €",
    ]
    assert _periode_de_section(detail, 0) == (date(2025, 1, 29), date(2025, 2, 28))


def test_la_section_suivante_arrete_la_lecture() -> None:
    """Une periode lue trop loin appartient deja au poste suivant."""
    detail = [
        "Abonnement d'électricité (HT) Prix par mois 16,70 €",
        "Offre Charge'Heures du 01/03/2025 au 28/03/2025 18,49 16,70 €",
        "Consommation d'électricité (HT) ... 227,40 €",
        "Période du 29/01/25 au 28/02/25 Relevé Enedis",
    ]
    assert _periode_de_section(detail, 0) == (date(2025, 3, 1), date(2025, 3, 28))


def test_section_sans_periode() -> None:
    assert _periode_de_section(["Abonnement d'électricité 16,70 €"], 0) is None


def test_annee_sur_deux_chiffres_acceptee() -> None:
    """Les anciennes factures ecrivent « 29/01/25 », les recentes « 2025 »."""
    court = ["Consommation", "du 29/01/25 au 28/02/25"]
    long = ["Consommation", "du 29/01/2025 au 28/02/2025"]
    assert _periode_de_section(court, 0) == _periode_de_section(long, 0)


# --- Prorata mensuel ---------------------------------------------------


def facture(*postes: Poste, tva: Decimal = Decimal("0.00")) -> Facture:
    ht = sum((p.montant_ht for p in postes), Decimal("0.00"))
    return Facture(
        fichier=None, postes=postes, total_ht=ht, tva=tva, total_ttc=ht + tva
    )


def test_prorata_repartit_sur_les_mois_couverts() -> None:
    poste = Poste("Abonnement", FIXE, Decimal("31.00"), date(2026, 1, 20), date(2026, 2, 19))
    rendu = prorata_mensuel(facture(poste))
    assert set(rendu) == {date(2026, 1, 1), date(2026, 2, 1)}
    assert rendu[date(2026, 1, 1)]["Abonnement"] == Decimal("12.00")   # 12 jours
    assert rendu[date(2026, 2, 1)]["Abonnement"] == Decimal("19.00")   # 19 jours


def test_le_dernier_mois_absorbe_l_arrondi() -> None:
    """La somme rendue doit valoir exactement le poste, au centime."""
    poste = Poste("Consommation", VARIABLE, Decimal("100.00"),
                  date(2026, 1, 15), date(2026, 3, 14))
    rendu = prorata_mensuel(facture(poste))
    total = sum((mois["Consommation"] for mois in rendu.values()), Decimal("0.00"))
    assert total == Decimal("100.00")


def test_la_tva_est_repercutee() -> None:
    poste = Poste("Abonnement", FIXE, Decimal("100.00"), date(2026, 1, 1), date(2026, 1, 31))
    rendu = prorata_mensuel(facture(poste, tva=Decimal("20.00")))
    assert rendu[date(2026, 1, 1)]["Abonnement"] == Decimal("120.00")


def test_categories_distingue_fixe_et_variable() -> None:
    """Un locataire absent supporte l'abonnement, pas la consommation."""
    fac = facture(
        Poste("Abonnement", FIXE, Decimal("20.00"), date(2026, 1, 1), date(2026, 1, 31)),
        Poste("Consommation", VARIABLE, Decimal("40.00"), date(2025, 12, 1), date(2025, 12, 31)),
    )
    assert categories(fac) == {"Abonnement": FIXE, "Consommation": VARIABLE}


# --- Mois complets -----------------------------------------------------


def test_un_mois_exige_les_deux_categories() -> None:
    """L'abonnement et la consommation sont decales : il faut deux factures."""
    seule = facture(
        Poste("Abonnement", FIXE, Decimal("20.00"), date(2026, 1, 1), date(2026, 1, 31)),
        Poste("Consommation", VARIABLE, Decimal("40.00"), date(2025, 12, 1), date(2025, 12, 31)),
    )
    assert mois_complets([seule])[date(2026, 1, 1)] is False


def test_deux_factures_completent_le_mois() -> None:
    janvier_abo = facture(
        Poste("Abonnement", FIXE, Decimal("20.00"), date(2026, 1, 1), date(2026, 1, 31)),
        Poste("Consommation", VARIABLE, Decimal("40.00"), date(2025, 12, 1), date(2025, 12, 31)),
    )
    janvier_conso = facture(
        Poste("Abonnement", FIXE, Decimal("20.00"), date(2026, 2, 1), date(2026, 2, 28)),
        Poste("Consommation", VARIABLE, Decimal("40.00"), date(2026, 1, 1), date(2026, 1, 31)),
    )
    complets = mois_complets([janvier_abo, janvier_conso])
    assert complets[date(2026, 1, 1)] is True
    assert complets[date(2026, 2, 1)] is False     # consommation pas encore relevee


def test_un_mois_a_demi_couvert_reste_incomplet() -> None:
    """Sans ce controle, un mois tronque serait inscrit sous-evalue."""
    partielle = facture(
        Poste("Abonnement", FIXE, Decimal("10.00"), date(2026, 1, 1), date(2026, 1, 15)),
        Poste("Consommation", VARIABLE, Decimal("20.00"), date(2026, 1, 1), date(2026, 1, 31)),
    )
    assert mois_complets([partielle])[date(2026, 1, 1)] is False
