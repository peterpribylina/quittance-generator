"""Mise en forme HTML des emails.

Presentation pure : aucune donnee metier, aucun envoi. `documents.py` compose
les textes, ce module les habille.

Contraintes propres a l'email, qui expliquent le style du code :

* tout est en **styles en ligne** — la plupart des clients suppriment les
  balises `<style>` ;
* la structure repose sur des `<table>` et non des `div` en flex ou grid, seul
  moyen d'obtenir le meme rendu sur Outlook ;
* aucune police distante : une pile systeme, qui degrade proprement ;
* largeur bornee a 560 px, lisible sur telephone comme sur ecran.
"""

from __future__ import annotations

POLICE = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
    "Helvetica,Arial,sans-serif"
)

ENCRE = "#1A1A1A"
TEXTE = "#2F3437"
DISCRET = "#8A8A8E"
TRAIT = "#E5E5E7"
FOND = "#F4F4F5"
ACCENT = "#BE1E2F"
ACCENT_PALE = "#FAF6F6"


def _cellule(contenu: str, padding: str) -> str:
    return f'<tr><td style="padding:{padding};">{contenu}</td></tr>'


def surtitre(texte: str) -> str:
    """Etiquette en petites capitales espacees, au-dessus du titre."""
    return (
        f'<div style="font-size:11px;letter-spacing:1.4px;text-transform:uppercase;'
        f'color:{DISCRET};font-weight:600;">{texte}</div>'
    )


def entete(etiquette: str, titre: str) -> str:
    return _cellule(
        surtitre(etiquette)
        + f'<div style="font-size:23px;font-weight:700;color:{ENCRE};'
        f'margin-top:6px;line-height:1.25;">{titre}</div>',
        "30px 32px 4px",
    )


def montant(etiquette: str, valeur: str, detail: str = "") -> str:
    """Encart accentue : le chiffre est ce que le locataire cherche d'abord."""
    ligne_detail = (
        f'<div style="font-size:13px;color:{DISCRET};margin-top:4px;">{detail}</div>'
        if detail
        else ""
    )
    encart = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="100%" style="background:{ACCENT_PALE};border-left:3px solid {ACCENT};'
        f'border-radius:0 8px 8px 0;">'
        f'<tr><td style="padding:16px 18px;">'
        + surtitre(etiquette)
        + f'<div style="font-size:27px;font-weight:700;color:{ENCRE};'
        f'margin-top:4px;letter-spacing:-0.5px;">{valeur}</div>'
        + ligne_detail
        + "</td></tr></table>"
    )
    return _cellule(encart, "18px 32px 0")


def paragraphe(html: str) -> str:
    return _cellule(
        f'<div style="font-size:15px;line-height:1.65;color:{TEXTE};">{html}</div>',
        "18px 32px 0",
    )


def encart(emoji: str, html: str) -> str:
    """Note laterale : echeance, astuce. L'emoji tient lieu de puce."""
    return _cellule(
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="100%" style="background:{FOND};border-radius:8px;">'
        f'<tr>'
        f'<td style="padding:14px 8px 14px 16px;font-size:17px;vertical-align:top;'
        f'width:34px;">{emoji}</td>'
        f'<td style="padding:14px 16px 14px 0;font-size:14px;line-height:1.55;'
        f'color:{TEXTE};">{html}</td>'
        f"</tr></table>",
        "14px 32px 0",
    )


def signature(nom: str) -> str:
    return _cellule(
        f'<div style="font-size:15px;line-height:1.65;color:{TEXTE};">{nom}</div>',
        "18px 32px 4px",
    )


def langue(nom: str) -> str:
    """Repere de section, pour qu'un lecteur trouve sa langue sans lire tout."""
    return _cellule(surtitre(nom), "22px 32px 0")


def separateur() -> str:
    return _cellule(
        f'<div style="border-top:1px solid {TRAIT};"></div>', "26px 32px 0"
    )


def document(blocs: list[str]) -> str:
    """Assemble les blocs dans la carte centrale."""
    return (
        f'<div style="margin:0;padding:24px 12px;background:{FOND};'
        f'font-family:{POLICE};">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="100%" style="max-width:560px;margin:0 auto;background:#FFFFFF;'
        f'border:1px solid {TRAIT};border-radius:14px;">'
        + "".join(blocs)
        + '<tr><td style="height:30px;"></td></tr>'
        "</table></div>"
    )
