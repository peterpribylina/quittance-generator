from __future__ import annotations

from pathlib import Path

import pytest

from quittances import cli


def run(config_file: Path, *args: str) -> int:
    return cli.main(["--config", str(config_file), *args])


def test_liste_des_locataires(config_file: Path, capsys) -> None:
    assert run(config_file, "locataires") == 0
    sortie = capsys.readouterr().out
    assert "Jingyi Luo" in sortie
    assert "Matilde Aranibar Campero" in sortie


def test_generation_simple(config_file: Path, tmp_path: Path) -> None:
    sortie = tmp_path / "out"
    code = run(
        config_file, "quittance", "--locataire", "Jin", "--periode", "2025-09",
        "--dossier", str(sortie),
    )
    assert code == 0
    attendu = sortie / "Jingyi_Luo" / "Quittances" / "Quittance_de_loyer_Jingyi_LUO_2025-09.pdf"
    assert attendu.is_file()


def test_montants_repris_de_la_configuration(
    config_file: Path, tmp_path: Path, capsys
) -> None:
    run(config_file, "quittance", "--locataire", "Jin", "--periode", "2025-09",
        "--dossier", str(tmp_path))
    assert "450,50" in capsys.readouterr().out


def test_loyer_en_ligne_de_commande_prioritaire(
    config_file: Path, tmp_path: Path, capsys
) -> None:
    run(config_file, "quittance", "--locataire", "Jin", "--periode", "2025-09",
        "--loyer", "500", "--charges", "0", "--dossier", str(tmp_path))
    assert "500,00" in capsys.readouterr().out


def test_loyer_manquant_signale(config_file: Path, tmp_path: Path, capsys) -> None:
    code = run(config_file, "quittance", "--locataire", "Xin", "--periode", "2025-09",
               "--dossier", str(tmp_path))
    assert code == 1
    assert "Loyer inconnu" in capsys.readouterr().err


def test_pdf_existant_non_ecrase_sans_forcer(
    config_file: Path, tmp_path: Path, capsys
) -> None:
    args = ("quittance", "--locataire", "Jin", "--periode", "2025-09",
            "--dossier", str(tmp_path))
    run(config_file, *args)
    cible = next(tmp_path.rglob("*.pdf"))
    horodatage = cible.stat().st_mtime_ns

    run(config_file, *args)
    assert "deja present" in capsys.readouterr().out
    assert cible.stat().st_mtime_ns == horodatage


def test_forcer_regenere(config_file: Path, tmp_path: Path, capsys) -> None:
    args = ("quittance", "--locataire", "Jin", "--periode", "2025-09",
            "--dossier", str(tmp_path))
    run(config_file, *args)
    run(config_file, *args, "--forcer")
    assert "deja present" not in capsys.readouterr().out


def test_aucun_email_sans_option_envoyer(
    config_file: Path, tmp_path: Path, capsys, monkeypatch
) -> None:
    """Garde-fou : l'ancienne version envoyait un email a chaque execution."""
    def refuser(*args, **kwargs):
        raise AssertionError("Aucun envoi ne doit avoir lieu sans --envoyer")

    monkeypatch.setattr(cli, "send", refuser)
    assert run(config_file, "quittance", "--locataire", "Jin", "--periode", "2025-09",
               "--dossier", str(tmp_path)) == 0
    assert "Email non envoye" in capsys.readouterr().out


def test_envoi_utilise_les_destinataires_du_locataire(
    config_file: Path, tmp_path: Path, monkeypatch
) -> None:
    envoyes = []
    monkeypatch.setenv("SMTP_USER", "bailleur@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr(cli, "send", lambda settings, message: envoyes.append(message))

    code = run(config_file, "quittance", "--locataire", "Matilde", "--periode",
               "2025-09", "--loyer", "400", "--dossier", str(tmp_path), "--envoyer")

    assert code == 0
    assert len(envoyes) == 1
    message = envoyes[0]
    assert message["To"] == "matilde@example.com, tuteur@example.com"
    assert "septembre 2025" in message["Subject"]
    pieces = [p.get_filename() for p in message.iter_attachments()]
    assert pieces == ["Quittance_de_loyer_Matilde_ARANIBAR_CAMPERO_2025-09.pdf"]


def test_echec_d_envoi_renvoie_un_code_erreur(
    config_file: Path, tmp_path: Path, monkeypatch, capsys
) -> None:
    from quittances.mailer import MailError

    monkeypatch.setenv("SMTP_USER", "bailleur@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")

    def echouer(settings, message):
        raise MailError("serveur injoignable")

    monkeypatch.setattr(cli, "send", echouer)
    code = run(config_file, "quittance", "--locataire", "Jin", "--periode", "2025-09",
               "--dossier", str(tmp_path), "--envoyer")
    assert code == 1
    assert "serveur injoignable" in capsys.readouterr().err


def test_generation_pour_tous_les_locataires_d_un_bien(
    config_file: Path, tmp_path: Path
) -> None:
    code = run(config_file, "quittance", "--maison", "anzin", "--periode",
               "2025-09", "--loyer", "400", "--dossier", str(tmp_path))
    assert code == 0
    assert len(list(tmp_path.rglob("*.pdf"))) == 2


def test_periode_invalide(config_file: Path, capsys) -> None:
    assert run(config_file, "quittance", "--locataire", "Jin", "--periode", "sept") == 1
    assert "Periode invalide" in capsys.readouterr().err


def test_date_invalide(config_file: Path, capsys) -> None:
    code = run(config_file, "quittance", "--locataire", "Jin", "--periode", "2025-09",
               "--date-paiement", "32/13/2025")
    assert code == 1
    assert "Date invalide" in capsys.readouterr().err


def test_locataire_inconnu(config_file: Path, capsys) -> None:
    assert run(config_file, "quittance", "--locataire", "Victor",
               "--periode", "2025-09") == 1
    assert "inconnu" in capsys.readouterr().err


def test_locataire_obligatoire(config_file: Path, capsys) -> None:
    assert run(config_file, "quittance", "--periode", "2025-09") == 1
    assert "--locataire" in capsys.readouterr().err


def test_attestation_sans_date_de_naissance(
    config_file: Path, tmp_path: Path, capsys
) -> None:
    code = run(config_file, "attestation", "--locataire", "Jin", "--depuis",
               "2025-09-01", "--dossier", str(tmp_path))
    assert code == 1
    assert "birth_date" in capsys.readouterr().err


def test_attestation_generee(config_file: Path, tmp_path: Path) -> None:
    code = run(config_file, "attestation", "--locataire", "Matilde", "--depuis",
               "01/09/2025", "--dossier", str(tmp_path))
    assert code == 0
    assert list(tmp_path.rglob("Docs/*.pdf"))


def test_config_absente(tmp_path: Path, capsys) -> None:
    assert cli.main(["--config", str(tmp_path / "rien.yaml"), "locataires"]) == 1
    assert "introuvable" in capsys.readouterr().err


def test_sans_argument_demande_une_cible(config_file: Path, capsys) -> None:
    """« quittance » etant implicite, l'absence d'argument n'est plus une
    erreur d'argparse mais un defaut de cible, signale clairement."""
    assert run(config_file) == 1
    erreur = capsys.readouterr().err
    assert "--locataire" in erreur
    assert "--maison" in erreur


def test_envoi_refuse_sans_email(
    config_file: Path, tmp_path: Path, monkeypatch, capsys
) -> None:
    """Un locataire sans email ne doit pas faire echouer silencieusement l'envoi."""
    import yaml

    brut = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    del brut["tenants"]["Jin"]["email"]
    config_file.write_text(
        yaml.safe_dump(brut, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setenv("SMTP_USER", "bailleur@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr(
        cli, "send", lambda *a, **k: pytest.fail("aucun envoi ne doit avoir lieu")
    )

    code = run(config_file, "quittance", "--locataire", "Jin", "--periode", "2025-09",
               "--dossier", str(tmp_path), "--envoyer")

    assert code == 1
    erreur = capsys.readouterr().err
    assert "Aucune adresse email" in erreur
    assert "tenants.Jin" in erreur
    assert next(tmp_path.rglob("*.pdf")).is_file()  # le PDF est bien produit


def test_lot_poursuit_malgre_un_locataire_sans_loyer(
    config_file: Path, tmp_path: Path, capsys
) -> None:
    """Seul Jin a un loyer configure.

    Matilde et Xin doivent tous deux etre signales : l'ancien comportement
    s'arretait sur le premier locataire en defaut.
    """
    code = run(config_file, "quittance", "--tous", "--periode", "2025-09",
               "--dossier", str(tmp_path))
    assert code == 1
    erreur = capsys.readouterr().err
    assert "Matilde Aranibar Campero" in erreur
    assert "XinXuan Li" in erreur
    assert erreur.count("Loyer inconnu") == 2
    assert [p.name for p in tmp_path.rglob("*.pdf")] == [
        "Quittance_de_loyer_Jingyi_LUO_2025-09.pdf"
    ]


class TestCommandeParDefaut:
    """« quittance » est implicite : c'est l'usage courant."""

    def test_commande_omise(self) -> None:
        assert cli.inject_default_command(["--maison", "anzin"]) == [
            "quittance", "--maison", "anzin"
        ]

    def test_commande_explicite_inchangee(self) -> None:
        argv = ["attestation", "--locataire", "Jin", "--depuis", "2025-09-01"]
        assert cli.inject_default_command(argv) == argv

    def test_locataires_inchangee(self) -> None:
        assert cli.inject_default_command(["locataires"]) == ["locataires"]

    def test_option_globale_avant_la_commande(self) -> None:
        assert cli.inject_default_command(["--config", "a.yaml", "locataires"]) == [
            "--config", "a.yaml", "locataires"
        ]

    def test_valeur_de_config_non_prise_pour_une_commande(self) -> None:
        """« --config quittance » ne doit pas passer pour la commande."""
        assert cli.inject_default_command(["--config", "quittance", "--tous"]) == [
            "--config", "quittance", "quittance", "--tous"
        ]

    def test_config_avec_signe_egal(self) -> None:
        assert cli.inject_default_command(["--config=a.yaml", "--tous"]) == [
            "--config=a.yaml", "quittance", "--tous"
        ]

    def test_sans_argument(self) -> None:
        assert cli.inject_default_command([]) == ["quittance"]

    def test_aide_preservee(self) -> None:
        assert cli.inject_default_command(["--help"]) == ["--help"]


def test_periode_par_defaut_mois_courant(
    config_file: Path, tmp_path: Path, capsys
) -> None:
    from datetime import date

    assert run(config_file, "--locataire", "Jin", "--dossier", str(tmp_path)) == 0
    attendu = date.today().strftime("%Y-%m")
    assert list(tmp_path.rglob(f"*{attendu}.pdf"))
    assert date.today().strftime("%m/%Y") in capsys.readouterr().out


class TestSelecteursExclusifs:
    """Combiner les selecteurs faisait silencieusement gagner --maison."""

    def test_locataire_et_maison_refuses(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        code = run(config_file, "--locataire", "Jin", "--maison", "vals",
                   "--dossier", str(tmp_path))
        assert code == 1
        erreur = capsys.readouterr().err
        assert "--locataire" in erreur and "--maison" in erreur
        assert not list(tmp_path.rglob("*.pdf"))  # rien n'est genere

    def test_locataire_et_tous_refuses(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        code = run(config_file, "--locataire", "Jin", "--tous",
                   "--dossier", str(tmp_path))
        assert code == 1
        assert "incompatibles" in capsys.readouterr().err

    def test_maison_seule_reste_valide(
        self, config_file: Path, tmp_path: Path
    ) -> None:
        assert run(config_file, "--maison", "anzin", "--periode", "2025-09",
                   "--loyer", "400", "--dossier", str(tmp_path)) == 0
        assert len(list(tmp_path.rglob("*.pdf"))) == 2

    def test_maison_deduite_du_locataire(
        self, config_file: Path, tmp_path: Path
    ) -> None:
        """Deux locataires de maisons differentes, en une commande, sans --maison."""
        code = run(config_file, "--locataire", "Jin", "--locataire", "Xin",
                   "--periode", "2025-09", "--loyer", "400", "--dossier", str(tmp_path))
        assert code == 0
        dossiers = {p.parent.parent.name for p in tmp_path.rglob("*.pdf")}
        assert dossiers == {"Jingyi_Luo", "XinXuan_Li"}


class TestSuivi:
    """Le suivi lit l'existence des PDF : c'est le seul signal disponible."""

    def _genere(self, config_file: Path, racine: Path, locataire: str,
                periode: str) -> None:
        assert run(config_file, "--locataire", locataire, "--periode", periode,
                   "--loyer", "400", "--dossier", str(racine)) == 0

    def test_colonnes_et_marqueurs(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        self._genere(config_file, tmp_path, "Jin", "2025-02")
        capsys.readouterr()

        assert run(config_file, "suivi", "--depuis", "2025-01", "--jusqu-a",
                   "2025-03", "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        assert "01 02 03" in sortie
        ligne = next(l for l in sortie.splitlines() if "Jingyi L." in l)
        # Le nom abrege contient un point : ne lire les marqueurs qu'apres la
        # colonne maison.
        _, _, cellules = ligne.partition("anzin")
        marques = [c for c in cellules if c in "✓·X."]
        assert marques == ["·", "✓", "·"] or marques == [".", "X", "."]

    def test_sans_selecteur_couvre_tout_le_monde(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        assert run(config_file, "suivi", "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        for nom in ("Jingyi L.", "Matilde A.", "XinXuan L."):
            assert nom in sortie

    def test_filtre_par_maison(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        assert run(config_file, "suivi", "--maison", "vals",
                   "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        assert "XinXuan L." in sortie
        assert "Jingyi L." not in sortie

    def test_manquants_masque_les_locataires_a_jour(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        self._genere(config_file, tmp_path, "Jin", "2025-01")
        capsys.readouterr()

        assert run(config_file, "suivi", "--depuis", "2025-01", "--jusqu-a",
                   "2025-01", "--manquants", "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        assert "Jingyi L." not in sortie
        assert "XinXuan L." in sortie

    def test_montant_du_cumule_les_mois(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        """Jin est a 390 + 60,50 : trois mois manquants font 1 351,50."""
        assert run(config_file, "suivi", "--locataire", "Jin", "--depuis",
                   "2025-01", "--jusqu-a", "2025-03", "--dossier", str(tmp_path)) == 0
        assert "1\u00a0351,50" in capsys.readouterr().out

    def test_montant_absent_sans_loyer_configure(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        assert run(config_file, "suivi", "--locataire", "Xin",
                   "--dossier", str(tmp_path)) == 0
        assert "rent" in capsys.readouterr().out

    def test_periode_inversee_refusee(
        self, config_file: Path, capsys
    ) -> None:
        code = run(config_file, "suivi", "--depuis", "2026-09", "--jusqu-a", "2026-01")
        assert code == 1
        assert "Periode vide" in capsys.readouterr().err

    def test_marqueurs_ascii_si_encodage_pauvre(self, monkeypatch) -> None:
        """Une redirection en cp1252 ne doit pas faire planter la commande."""
        class SortiePauvre:
            encoding = "cp1252"

        monkeypatch.setattr(cli.sys, "stdout", SortiePauvre())
        assert cli.markers() == ("X", ".", " ")

    def test_totaux_de_l_annee(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        """Jin est a 450,50 par mois. Sur trois mois tous echus, une quittance
        emise donne 1 351,50 attendus, 450,50 acquittes, 901,00 en retard."""
        self._genere(config_file, tmp_path, "Jin", "2025-01")
        capsys.readouterr()

        assert run(config_file, "suivi", "--locataire", "Jin", "--depuis",
                   "2025-01", "--jusqu-a", "2025-03", "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        for libelle, montant in (
            ("Attendu", "1 351,50"),
            ("Acquitté", "450,50"),
            ("En retard", "901,00"),
            ("À venir", "0,00"),
        ):
            ligne = next(l for l in sortie.splitlines() if l.strip().startswith(libelle))
            assert montant in ligne, f"{libelle} : {ligne!r}"

    def test_annee_de_bail_par_defaut(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        """Sans --jusqu-a, la periode couvre douze mois depuis --depuis."""
        assert run(config_file, "suivi", "--locataire", "Jin", "--depuis",
                   "2025-09", "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        assert "septembre 2025 - août 2026" in sortie
        assert "12 mois" in sortie
        assert "09 10 11 12 01 02 03 04 05 06 07 08" in sortie

    def test_mois_non_echus_ne_sont_pas_des_retards(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        """Un loyer de mars n'est pas un impaye en septembre."""
        from datetime import date

        depart = date.today().replace(day=1)
        assert run(config_file, "suivi", "--locataire", "Jin", "--depuis",
                   depart.strftime("%Y-%m"), "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        retard = next(l for l in sortie.splitlines() if l.strip().startswith("En retard"))
        avenir = next(l for l in sortie.splitlines() if l.strip().startswith("À venir"))
        assert "1 mois échus" in retard      # le mois courant seul
        assert "11 mois non échus" in avenir

    def test_attendu_est_la_somme_des_trois(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        assert run(config_file, "suivi", "--locataire", "Jin", "--depuis",
                   "2025-09", "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        montants = {}
        for libelle in ("Attendu", "Acquitté", "En retard", "À venir"):
            ligne = next(l for l in sortie.splitlines() if l.strip().startswith(libelle))
            # str.split() couperait aussi sur l'espace insecable du montant.
            montants[libelle] = ligne.split("€")[0].replace(libelle, "").strip()
        # 12 mois a 450,50 = 5 406,00
        assert montants["Attendu"] == "5 406,00"
        assert montants["Acquitté"] == "0,00"


class TestRelance:
    """Une relance part au nom du bailleur : rien sans --envoyer."""

    def test_apercu_sans_envoi(
        self, config_file: Path, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            cli, "send", lambda *a, **k: pytest.fail("aucun envoi sans --envoyer")
        )
        assert run(config_file, "relance", "--locataire", "Jin", "--depuis",
                   "2025-01", "--jusqu-a", "2025-02", "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        assert "Rappel : 2 loyers en attente" in sortie
        assert "janvier et février 2025" in sortie
        assert "Email non envoye" in sortie

    def test_locataire_a_jour_non_relance(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        assert run(config_file, "--locataire", "Jin", "--periode", "2025-01",
                   "--dossier", str(tmp_path)) == 0
        capsys.readouterr()

        assert run(config_file, "relance", "--locataire", "Jin", "--depuis",
                   "2025-01", "--jusqu-a", "2025-01", "--dossier", str(tmp_path)) == 0
        assert "personne a relancer" in capsys.readouterr().out

    def test_mois_non_echus_jamais_relances(
        self, config_file: Path, tmp_path: Path, capsys
    ) -> None:
        """Sur une annee de bail, seuls les mois echus declenchent un rappel."""
        from datetime import date

        depart = date.today().replace(day=1)
        assert run(config_file, "relance", "--locataire", "Jin", "--depuis",
                   depart.strftime("%Y-%m"), "--dossier", str(tmp_path)) == 0
        sortie = capsys.readouterr().out
        assert "Rappel : loyer de" in sortie          # un seul mois
        assert "loyers en attente" not in sortie

    def test_envoi_reel(
        self, config_file: Path, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        envoyes = []
        monkeypatch.setenv("SMTP_USER", "bailleur@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")
        monkeypatch.setattr(cli, "send", lambda s, m: envoyes.append(m))

        assert run(config_file, "relance", "--locataire", "Jin", "--depuis",
                   "2025-01", "--jusqu-a", "2025-01", "--dossier", str(tmp_path),
                   "--envoyer") == 0
        assert len(envoyes) == 1
        message = envoyes[0]
        assert message["To"] == "jin@example.com"
        assert "Rappel" in message["Subject"]
        assert list(message.iter_attachments()) == []  # pas de piece jointe

    def test_sans_email_configure(
        self, config_file: Path, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        import yaml

        brut = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        del brut["tenants"]["Jin"]["email"]
        config_file.write_text(
            yaml.safe_dump(brut, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        monkeypatch.setenv("SMTP_USER", "bailleur@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")
        monkeypatch.setattr(cli, "send", lambda *a, **k: pytest.fail("envoi interdit"))

        code = run(config_file, "relance", "--locataire", "Jin", "--depuis",
                   "2025-01", "--jusqu-a", "2025-01", "--dossier", str(tmp_path),
                   "--envoyer")
        assert code == 1
        assert "Aucune adresse email" in capsys.readouterr().err
