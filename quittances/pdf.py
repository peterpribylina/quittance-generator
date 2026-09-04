"""Rendu PDF via ReportLab.

Mise en page editoriale : pas de cadre, hierarchie portee par la typographie et
le blanc, montant regle en element dominant. Elle remplace la grille heritee de
pdfkit, dont le cadre occupait un tiers de page sans porter d'information et
dont le filigrane debordait hors de la page.

ReportLab place l'origine en bas a gauche ; les constantes ci-dessous sont
exprimees depuis le haut de la page, plus naturelles a lire pour une mise en
page, et converties par `_y()`.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph

from .config import Config
from .documents import Attestation, Quittance
from .formatting import elision

PAGE_WIDTH, PAGE_HEIGHT = A4

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

# Palette : ardoise pour les titres, rouge du logo en accent, verts et gris
# reserves aux statuts et aux etiquettes.
NOIR = HexColor("#1A1A1A")
ARDOISE = HexColor("#2F3437")
ACCENT = HexColor("#BE1E2F")
GRIS = HexColor("#575656")
GRIS_MOYEN = HexColor("#8A8A8A")
GRIS_CLAIR = HexColor("#D4D4D6")
VERT = HexColor("#2E7D5B")

MARGE = 56.0
DROITE = PAGE_WIDTH - MARGE
COLONNE_2 = MARGE + 300.0
LARGEUR_COLONNE_1 = 265.0

# Boite de la signature. L'image conserve ses proportions a l'interieur.
SIGNATURE_LARGEUR = 240.0
SIGNATURE_HAUTEUR = 124.0

MENTION_LEGALE = (
    "Le paiement de la présente n'emporte pas présomption de paiement des termes "
    "antérieurs. Cette quittance ou ce reçu annule tous les reçus qui auraient pu "
    "être donnés pour acompte versé sur le présent terme. En cas de congé "
    "précédemment donné, cette quittance ou ce reçu représenterait l'indemnité "
    "d'occupation et ne saurait être considéré comme un titre d'occupation. "
    "Sous réserve d'encaissement."
)


def _y(depuis_le_haut: float, hauteur: float = 0.0) -> float:
    """Convertit une ordonnee mesuree depuis le haut en ordonnee ReportLab."""
    return PAGE_HEIGHT - depuis_le_haut - hauteur


def _ascent(police: str, taille: float) -> float:
    return pdfmetrics.getAscent(police) / 1000.0 * taille


def _text(canvas, contenu, x, haut, police=FONT, taille=9.0, couleur=NOIR,
          interlettrage=0.0) -> None:
    """Ecrit une ligne dont le haut des capitales est a `haut`.

    L'interlettrage n'existe que sur l'objet texte, pas sur le canvas.
    """
    canvas.saveState()
    objet = canvas.beginText(x, _y(haut) - _ascent(police, taille))
    objet.setFont(police, taille)
    objet.setFillColor(couleur)
    if interlettrage:
        objet.setCharSpace(interlettrage)
    objet.textOut(contenu)
    canvas.drawText(objet)
    canvas.restoreState()


def _text_right(canvas, contenu, x_droite, haut, police=FONT, taille=9.0,
                couleur=NOIR) -> None:
    canvas.saveState()
    canvas.setFont(police, taille)
    canvas.setFillColor(couleur)
    canvas.drawRightString(x_droite, _y(haut) - _ascent(police, taille), contenu)
    canvas.restoreState()


def _label(canvas, contenu, x, haut, couleur=GRIS_MOYEN, taille=6.5) -> None:
    """Etiquette en capitales espacees, au-dessus de la donnee qu'elle nomme."""
    _text(canvas, contenu.upper(), x, haut, FONT_BOLD, taille, couleur,
          interlettrage=1.1)


def _style(nom: str, **surcharges) -> ParagraphStyle:
    base = dict(fontName=FONT, fontSize=9.0, leading=13.0, textColor=NOIR)
    base.update(surcharges)
    return ParagraphStyle(nom, **base)


CORPS = _style("corps", fontSize=9.5, leading=15.5, alignment=TA_JUSTIFY)
MENTION = _style("mention", fontSize=6.4, leading=9.0, textColor=GRIS_MOYEN,
                 alignment=TA_JUSTIFY)


def _paragraph(canvas, markup, x, haut, largeur, style=CORPS) -> float:
    """Dessine un paragraphe dont le haut est a `haut`. Renvoie sa hauteur."""
    para = Paragraph(markup, style)
    _, hauteur = para.wrapOn(canvas, largeur, PAGE_HEIGHT)
    para.drawOn(canvas, x, _y(haut, hauteur))
    return hauteur


def _bold(valeur: object) -> str:
    """Echappe une valeur et la met en gras dans le balisage Paragraph."""
    return f"<b>{escape(str(valeur))}</b>"


def _rule(canvas, haut, x1=MARGE, x2=DROITE, couleur=GRIS_CLAIR,
          epaisseur=0.5) -> None:
    canvas.saveState()
    canvas.setStrokeColor(couleur)
    canvas.setLineWidth(epaisseur)
    canvas.line(x1, _y(haut), x2, _y(haut))
    canvas.restoreState()


def _draw_header(canvas, config: Config) -> None:
    """Bloc bailleur a gauche, logo a droite."""
    landlord = config.landlord
    taille_logo = 38.0
    canvas.drawImage(
        str(config.assets.logo), DROITE - taille_logo, _y(52.0, taille_logo),
        width=taille_logo, height=taille_logo, mask="auto",
        preserveAspectRatio=True, anchor="nw",
    )
    _label(canvas, "Bailleur", MARGE, 52.0)
    _text(canvas, landlord.display_name, MARGE, 66.0, FONT_BOLD, 9.5)
    for index, ligne in enumerate(landlord.address_lines):
        _text(canvas, ligne, MARGE, 80.0 + index * 12.0, FONT, 8.5, GRIS)


def _draw_title(canvas, titre: str, sous_titre: str) -> None:
    _text(canvas, titre, MARGE, 150.0, FONT_BOLD, 27.0, ARDOISE)
    _text(canvas, sous_titre, MARGE, 186.0, FONT, 14.0, ACCENT)
    _rule(canvas, 222.0)


FILIGRANE_TAILLE = 160.0
FILIGRANE_OPACITE = 0.10


def _draw_watermark(canvas, config: Config, bas: float = 720.0) -> None:
    """Filigrane en bas a droite, dans la zone laissee libre par la signature.

    Sans effet si aucune image n'est configuree.
    """
    if config.assets.watermark is None:
        return
    canvas.saveState()
    # Alpha non-couvrant : s'applique aussi aux images (operateur `ca`).
    canvas.setFillAlpha(FILIGRANE_OPACITE)
    canvas.drawImage(
        str(config.assets.watermark),
        DROITE - FILIGRANE_TAILLE, _y(bas),
        width=FILIGRANE_TAILLE, height=FILIGRANE_TAILLE, mask="auto",
        preserveAspectRatio=True, anchor="sw",
    )
    canvas.restoreState()


def _draw_signature(canvas, config: Config, haut: float) -> None:
    canvas.drawImage(
        str(config.assets.signature), MARGE, _y(haut, SIGNATURE_HAUTEUR),
        width=SIGNATURE_LARGEUR, height=SIGNATURE_HAUTEUR, mask="auto",
        preserveAspectRatio=True, anchor="nw",
    )


def _draw_closing(canvas, config: Config, date_emission: str,
                  haut: float = 498.0) -> None:
    """Lieu, date d'emission et signature, en bas du document."""
    _rule(canvas, haut)
    _text(canvas, f"Fait à {config.landlord.city} le {date_emission}",
          MARGE, haut + 24.0, FONT, 9.0, GRIS)
    _label(canvas, "Signature du bailleur", MARGE, haut + 50.0)
    _draw_signature(canvas, config, haut + 68.0)


def render_quittance(quittance: Quittance, config: Config, path: Path) -> Path:
    """Ecrit la quittance en PDF a `path` (dossiers parents crees si besoin)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    canvas = pdfcanvas.Canvas(str(path), pagesize=A4)
    canvas.setTitle(f"Quittance de loyer - {quittance.period_label}")
    canvas.setAuthor(config.landlord.legal_name)

    _draw_watermark(canvas, config)
    _draw_header(canvas, config)
    _draw_title(canvas, "Quittance de loyer", quittance.period_label.capitalize())

    # Le locataire cherche d'abord combien, et pour quand : ces deux donnees
    # passent avant le detail comptable.
    _label(canvas, "Montant réglé", MARGE, 246.0)
    _text(canvas, quittance.total_label, MARGE, 260.0, FONT_BOLD, 30.0, NOIR)
    _label(canvas, "Payé le", DROITE - 120.0, 246.0)
    _text(canvas, quittance.payment_date_label, DROITE - 120.0, 262.0, FONT, 13.0,
          GRIS)

    _rule(canvas, 322.0)

    tenant = quittance.tenant
    _paragraph(
        canvas,
        f"Reçu de {_bold(tenant.display_name)} la somme de "
        f"{_bold(quittance.total_label)}, pour loyer et accessoires des locaux "
        f"situés au {_bold(tenant.address)}, en paiement du terme du mois "
        f"{elision(quittance.period_label)}{_bold(quittance.period_label)}.",
        MARGE, 348.0, LARGEUR_COLONNE_1,
    )

    _label(canvas, "Détail du terme", COLONNE_2, 348.0)
    haut = 372.0
    for libelle, valeur in (
        ("Loyer nu", quittance.rent_label),
        ("Provisions de charges", quittance.charges_label),
    ):
        _text(canvas, libelle, COLONNE_2, haut, FONT, 9.0, GRIS)
        _text_right(canvas, valeur, DROITE, haut, FONT, 9.0)
        haut += 20.0

    _rule(canvas, haut + 2.0, COLONNE_2, DROITE)
    haut += 12.0
    _text(canvas, "Total du terme", COLONNE_2, haut, FONT_BOLD, 9.5)
    _text_right(canvas, quittance.total_label, DROITE, haut, FONT_BOLD, 9.5)
    haut += 20.0
    _text(canvas, "Solde à payer", COLONNE_2, haut, FONT, 9.0, GRIS)
    _text_right(canvas, "0,00 €", DROITE, haut, FONT, 9.0, VERT)

    _draw_closing(canvas, config, quittance.issued_on_label)

    _rule(canvas, 742.0)
    _paragraph(canvas, MENTION_LEGALE, MARGE, 754.0, DROITE - MARGE, MENTION)

    canvas.showPage()
    canvas.save()
    return path


def render_attestation(attestation: Attestation, config: Config, path: Path) -> Path:
    """Ecrit l'attestation d'hebergement en PDF a `path`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    landlord = config.landlord
    tenant = attestation.tenant

    canvas = pdfcanvas.Canvas(str(path), pagesize=A4)
    canvas.setTitle("Attestation d'hébergement")
    canvas.setAuthor(landlord.legal_name)

    _draw_watermark(canvas, config)
    _draw_header(canvas, config)
    _draw_title(canvas, "Attestation d'hébergement", str(attestation.issued_on.year))

    naissance_bailleur = ""
    if landlord.birth_date and landlord.birth_place:
        naissance_bailleur = (
            f", né le {escape(str(landlord.birth_date))} "
            f"à {escape(str(landlord.birth_place))}"
        )

    # Sans civilite configuree, on n'accorde pas au hasard.
    if not tenant.title:
        accord = "né(e)"
    elif tenant.title.lower().startswith(("mlle", "mme")):
        accord = "née"
    else:
        accord = "né"

    corps = (
        f"Je soussigné {_bold(landlord.legal_name)}{naissance_bailleur}, "
        f"déclare sur l'honneur héberger à mon domicile :",
        f"{_bold(tenant.display_name)}, {accord} le "
        f"{escape(str(tenant.birth_date))} à {escape(str(tenant.birth_place))},",
        f"depuis le {_bold(attestation.hosted_since_label)}, à l'adresse suivante : "
        f"{_bold(tenant.address)}.",
        "Cette attestation est établie pour servir et valoir ce que de droit.",
    )

    haut = 260.0
    for markup in corps:
        haut += _paragraph(canvas, markup, MARGE, haut, DROITE - MARGE) + 20.0

    _draw_closing(canvas, config, attestation.issued_on_label, haut=max(haut + 20.0, 460.0))

    canvas.showPage()
    canvas.save()
    return path
