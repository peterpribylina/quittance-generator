from __future__ import annotations

from pathlib import Path

import pytest

from quittances.mailer import MailError, MailSettings, build_message


@pytest.fixture
def settings() -> MailSettings:
    return MailSettings(
        host="smtp.example.com",
        port=465,
        user="bailleur@example.com",
        password="secret",
        from_name="Peter PRIBYLINA",
    )


@pytest.fixture(autouse=True)
def environnement_propre(monkeypatch) -> None:
    """Isole les tests du vrai .env du depot.

    `load_dotenv()` remonte depuis le fichier appelant (quittances/mailer.py),
    pas depuis le repertoire courant : un `chdir` ne suffit donc pas a l'eviter.
    """
    monkeypatch.setattr("quittances.mailer.load_dotenv", lambda *a, **k: None)
    for nom in (
        "SMTP_USER", "SMTP_PASSWORD", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM_NAME",
        "GMAIL_USER", "GMAIL_APP_PASSWORD",
    ):
        monkeypatch.delenv(nom, raising=False)


def test_identifiants_lus_dans_l_environnement(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_USER", "a@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "motdepasse")
    settings = MailSettings.from_env(from_name="Bailleur")
    assert settings.user == "a@example.com"
    assert settings.host == "smtp.gmail.com"
    assert settings.port == 465


def test_variables_gmail_acceptees(monkeypatch) -> None:
    monkeypatch.setenv("GMAIL_USER", "a@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd")
    assert MailSettings.from_env(from_name="Bailleur").user == "a@gmail.com"


def test_identifiants_manquants() -> None:
    with pytest.raises(MailError) as exc:
        MailSettings.from_env(from_name="Bailleur")
    assert "SMTP_USER" in str(exc.value)


def test_port_invalide(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_USER", "a@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    monkeypatch.setenv("SMTP_PORT", "quatre-cent")
    with pytest.raises(MailError, match="SMTP_PORT"):
        MailSettings.from_env(from_name="Bailleur")


def test_message_multipart_avec_piece_jointe(
    settings: MailSettings, tmp_path: Path
) -> None:
    piece = tmp_path / "quittance.pdf"
    piece.write_bytes(b"%PDF-1.4 factice")

    message = build_message(
        settings, ["a@example.com", "b@example.com"], "Sujet", "texte",
        "<b>html</b>", attachment=piece,
    )

    assert message["From"] == "Peter PRIBYLINA <bailleur@example.com>"
    assert message["To"] == "a@example.com, b@example.com"
    assert message["Subject"] == "Sujet"
    pieces = list(message.iter_attachments())
    assert len(pieces) == 1
    assert pieces[0].get_filename() == "quittance.pdf"
    assert pieces[0].get_content_type() == "application/pdf"


def test_message_sans_destinataire(settings: MailSettings) -> None:
    with pytest.raises(MailError, match="destinataire"):
        build_message(settings, [], "Sujet", "texte", "html")


def test_piece_jointe_introuvable(settings: MailSettings, tmp_path: Path) -> None:
    with pytest.raises(MailError, match="introuvable"):
        build_message(
            settings, ["a@example.com"], "Sujet", "texte", "html",
            attachment=tmp_path / "absent.pdf",
        )
