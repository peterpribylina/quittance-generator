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
    code = run(config_file, "quittance", "--tous", "--bien", "anzin", "--periode",
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


def test_commande_obligatoire() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


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
