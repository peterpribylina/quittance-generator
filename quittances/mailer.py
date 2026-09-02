"""Envoi des documents par email (SMTP).

Aucun identifiant n'est code en dur : tout vient de l'environnement ou d'un
fichier `.env` local, jamais versionne.
"""

from __future__ import annotations

import mimetypes
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv


class MailError(Exception):
    """Configuration SMTP absente ou envoi impossible."""


@dataclass(frozen=True)
class MailSettings:
    host: str
    port: int
    user: str
    password: str
    from_name: str

    @property
    def from_header(self) -> str:
        """Citation du nom affiche selon la RFC 5322 (uniquement si necessaire)."""
        return formataddr((self.from_name, self.user))

    @classmethod
    def from_env(cls, from_name: str) -> "MailSettings":
        """Lit `.env` puis l'environnement. Leve MailError si incomplet."""
        load_dotenv(override=False)
        user = os.environ.get("SMTP_USER") or os.environ.get("GMAIL_USER")
        password = os.environ.get("SMTP_PASSWORD") or os.environ.get(
            "GMAIL_APP_PASSWORD"
        )
        manquants = [
            nom
            for nom, valeur in (("SMTP_USER", user), ("SMTP_PASSWORD", password))
            if not valeur
        ]
        if manquants:
            raise MailError(
                f"Variables d'environnement manquantes : {', '.join(manquants)}. "
                "Renseignez-les dans un fichier .env (voir .env.example)."
            )
        port_brut = os.environ.get("SMTP_PORT", "465")
        try:
            port = int(port_brut)
        except ValueError as exc:
            raise MailError(f"SMTP_PORT invalide : {port_brut!r}") from exc
        return cls(
            host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            port=port,
            user=str(user),
            password=str(password),
            from_name=os.environ.get("SMTP_FROM_NAME", from_name),
        )


def build_message(
    settings: MailSettings,
    recipients: Sequence[str],
    subject: str,
    text_body: str,
    html_body: str,
    attachment: Path | None = None,
) -> EmailMessage:
    """Construit le message ; separe de l'envoi pour rester testable."""
    if not recipients:
        raise MailError("Aucun destinataire.")

    message = EmailMessage()
    message["From"] = settings.from_header
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    if attachment is not None:
        attachment = Path(attachment)
        if not attachment.is_file():
            raise MailError(f"Piece jointe introuvable : {attachment}")
        type_mime, _ = mimetypes.guess_type(attachment.name)
        maintype, _, subtype = (type_mime or "application/octet-stream").partition("/")
        message.add_attachment(
            attachment.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=attachment.name,
        )
    return message


def send(settings: MailSettings, message: EmailMessage) -> None:
    """Envoie le message. Port 465 : SSL implicite ; sinon STARTTLS."""
    try:
        if settings.port == 465:
            with smtplib.SMTP_SSL(settings.host, settings.port, timeout=30) as serveur:
                serveur.login(settings.user, settings.password)
                serveur.send_message(message)
        else:
            with smtplib.SMTP(settings.host, settings.port, timeout=30) as serveur:
                serveur.starttls()
                serveur.login(settings.user, settings.password)
                serveur.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(
            "Authentification SMTP refusee. Pour Gmail, utilisez un mot de passe "
            "d'application (https://myaccount.google.com/apppasswords), pas le mot "
            f"de passe du compte. Detail : {exc}"
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"Envoi impossible : {exc}") from exc
