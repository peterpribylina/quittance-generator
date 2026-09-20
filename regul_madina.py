"""Regularisation de Madina pour son annee a Anzin (2025-09 -> 2026-06).

Script jetable : sa fiche `config.yaml` decrit sa location actuelle a
Valenciennes, la CLI ne peut donc pas produire ce document. La location
d'Anzin est close, on ne l'inscrit pas dans la configuration pour autant.

    python regul_madina.py              # apercu, rien n'est envoye
    python regul_madina.py --envoyer    # ecrit le PDF et envoie l'email

L'envoi demande explicitement --envoyer, comme partout ailleurs.
"""

from __future__ import annotations

import dataclasses
import sys
from datetime import date
from decimal import Decimal as D, ROUND_HALF_UP

from quittances.cli import _deliver, printable
from quittances.config import Config
from quittances.documents import Regularisation
from quittances.pdf import render_regularisation

# Cout de la maison sur la periode, releve sur les factures :
#   electricite  TotalEnergies 09/2025 - 06/2026, tous mois complets
#   eau          SUEZ n° 1107630321 du 20/07/2026, au prorata des jours
#   internet     51 € par mois
MAISON = {
    "Eau": D("793.55"),
    "Internet": D("510.00"),
    "Électricité": D("1929.79"),
}
DEBUT, FIN = date(2025, 9, 1), date(2026, 6, 30)
PART = D("22.76")          # chambre R+1 jardin
PROVISIONS = D("70.00") * 10       # 70 € sur chacune de ses dix quittances


def q(x: D) -> D:
    return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def main() -> int:
    envoyer = "--envoyer" in sys.argv
    config = Config.load("config.yaml")

    # Sa fiche telle qu'elle etait a Anzin, le temps du rendu.
    madina = dataclasses.replace(
        config.tenant("Madina"),
        property=config.properties["anzin"],
        room="R+1 jardin",
        share=PART,
        lease_start=DEBUT,
        lease_end=FIN,
        charges=D("70.00"),
        rent=D("340.00"),
        charges_dediees=(),
    )
    regul = Regularisation(
        tenant=madina,
        debut=DEBUT,
        fin=FIN,
        reel={nom: q(total * PART / 100) for nom, total in MAISON.items()},
        totaux_maison=MAISON,
        provisions=PROVISIONS,
        issued_on=date.today(),
        jours_dus=madina.jours_occupes(DEBUT, FIN),
        jours_periode=(FIN - DEBUT).days + 1,
        # La note rejoint le paragraphe d'introduction, qui porte deja
        # l'adresse : elle n'ajoute que ce qu'il ne dit pas.
        note=(
            f"Il s'agit de la chambre {madina.room}, occupée du "
            f"{DEBUT:%d/%m/%Y} au {FIN:%d/%m/%Y}, et les montants sont "
            f"relevés sur les factures de la période."
        ),
    )

    print(printable(
        f"{madina.full_name} — {regul.periode_label}\n"
        f"  Charges reelles {regul.total_reel} € contre {regul.provisions} € "
        f"de provisions -> {regul.libelle_solde} {regul.montant_du} €\n"
        f"  Soit {regul.comparaison}"
    ))

    chemin = regul.output_path()
    try:
        render_regularisation(regul, config, chemin)
        print(f"  PDF ecrit : {chemin}")
    except PermissionError:
        print(f"  PDF VERROUILLE (ferme-le dans ton lecteur) : {chemin}")
        return 1

    print(printable(f"\n  Objet : {regul.email_subject}"))
    print(printable(f"  Destinataires : {', '.join(madina.emails) or '(aucun)'}"))
    if not envoyer:
        print("\n  Email non envoye (ajoute --envoyer)")
        return 0
    _deliver(
        config, madina, regul.email_subject,
        regul.email_body(config.landlord.first_name), chemin,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
