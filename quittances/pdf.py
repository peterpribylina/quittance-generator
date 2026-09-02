"""Rendu PDF via ReportLab.

La mise en page reprend celle de l'ancienne version pdfkit (cadre, deux
colonnes, filigrane, signature) avec deux differences assumees :

* page A4 au lieu de Letter US (format attendu pour un document francais) ;
* filigrane contenu dans le cadre. L'ancienne version le posait en (410, 410)
  avec `fit: [500, 500]`, soit 300 pt hors de la page.

ReportLab place l'origine en bas a gauche ; les constantes ci-dessous sont
exprimees depuis le haut de la page, comme dans le code d'origine, et
converties par `_y()`.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import black, grey
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph

from .config import Config
from .documents import Attestation, Quittance

PAGE_WIDTH, PAGE_HEIGHT = A4

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

FRAME_LEFT = 50.0
FRAME_RIGHT = 545.0
FRAME_TOP = 200.0
FRAME_HEADER_RULE = 255.0
FRAME_BOTTOM = 660.0

CONTENT_LEFT = 60.0
COLUMN_2_LEFT = 310.0
DIVIDER_X = 300.0

COLUMN_1_WIDTH = DIVIDER_X - 15.0 - CONTENT_LEFT
COLUMN_2_WIDTH = FRAME_RIGHT - 10.0 - COLUMN_2_LEFT

BODY = ParagraphStyle("body", fontName=FONT, fontSize=10, leading=13, textColor=black)
TITLE = ParagraphStyle("title", parent=BODY, fontName=FONT_BOLD, alignment=TA_CENTER)
FOOTER = ParagraphStyle(
    "footer", fontName=FONT, fontSize=8, leading=10, textColor=grey, alignment=TA_CENTER
)


def _y(top_offset: float, height: float = 0.0) -> float:
    """Convertit une ordonnee mesuree depuis le haut en ordonnee ReportLab."""
    return PAGE_HEIGHT - top_offset - height


def _paragraph(
    canvas: pdfcanvas.Canvas,
    markup: str,
    x: float,
    top: float,
    width: float,
    style: ParagraphStyle = BODY,
) -> float:
    """Dessine un paragraphe dont le haut est a `top`. Renvoie sa hauteur."""
    para = Paragraph(markup, style)
    _, height = para.wrapOn(canvas, width, PAGE_HEIGHT)
    para.drawOn(canvas, x, _y(top, height))
    return height


def _bold(value: object) -> str:
    """Echappe une valeur et la met en gras dans le balisage Paragraph."""
    return f"<b>{escape(str(value))}</b>"


def _draw_landlord_header(canvas: pdfcanvas.Canvas, config: Config) -> None:
    landlord = config.landlord
    _paragraph(canvas, "Bailleur", CONTENT_LEFT, 50.0, 250.0)
    _paragraph(canvas, escape(landlord.display_name), CONTENT_LEFT, 80.0, 250.0)
    for index, line in enumerate(landlord.address_lines):
        _paragraph(canvas, escape(line), CONTENT_LEFT, 95.0 + index * 15.0, 250.0)

    logo_size = 50.0
    canvas.drawImage(
        str(config.assets.logo),
        FRAME_RIGHT - logo_size,
        _y(50.0, logo_size),
        width=logo_size,
        height=logo_size,
        mask="auto",
    )


WATERMARK_ALPHA = 0.14


def _draw_watermark(canvas: pdfcanvas.Canvas, config: Config) -> None:
    """Filigrane en bas a droite, attenue et contenu dans le cadre."""
    size = 150.0
    canvas.saveState()
    # Alpha non-couvrant : s'applique aussi aux images (operateur `ca`).
    canvas.setFillAlpha(WATERMARK_ALPHA)
    canvas.drawImage(
        str(config.assets.watermark),
        FRAME_RIGHT - size - 10.0,
        _y(FRAME_BOTTOM - 10.0, 0.0),
        width=size,
        height=size,
        mask="auto",
        preserveAspectRatio=True,
        anchor="sw",
    )
    canvas.restoreState()


def _draw_signature(canvas: pdfcanvas.Canvas, config: Config, top: float) -> None:
    width = 140.0
    height = 95.0
    canvas.drawImage(
        str(config.assets.signature),
        CONTENT_LEFT + 10.0,
        _y(top, height),
        width=width,
        height=height,
        mask="auto",
        preserveAspectRatio=True,
        anchor="nw",
    )


def _draw_frame(canvas: pdfcanvas.Canvas) -> None:
    canvas.setLineWidth(1)
    canvas.setStrokeColor(black)
    canvas.rect(
        FRAME_LEFT,
        _y(FRAME_BOTTOM),
        FRAME_RIGHT - FRAME_LEFT,
        FRAME_BOTTOM - FRAME_TOP,
        stroke=1,
        fill=0,
    )
    canvas.line(FRAME_LEFT, _y(FRAME_HEADER_RULE), FRAME_RIGHT, _y(FRAME_HEADER_RULE))
    canvas.line(DIVIDER_X, _y(FRAME_HEADER_RULE), DIVIDER_X, _y(FRAME_BOTTOM))


LEGAL_NOTICE = (
    "Le paiement de la présente n'emporte pas présomption de paiement des termes "
    "antérieurs. Cette quittance ou ce reçu annule tous les reçus qui auraient pu "
    "être donnés pour acompte versé sur le présent terme. En cas de congé "
    "précédemment donné, cette quittance ou ce reçu représenterait l'indemnité "
    "d'occupation et ne saurait être considéré comme un titre d'occupation. "
    "Sous réserve d'encaissement."
)


def render_quittance(quittance: Quittance, config: Config, path: Path) -> Path:
    """Ecrit la quittance en PDF a `path` (dossiers parents crees si besoin)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    canvas = pdfcanvas.Canvas(str(path), pagesize=A4)
    canvas.setTitle(f"Quittance de loyer - {quittance.period_label}")
    canvas.setAuthor(config.landlord.legal_name)

    _draw_landlord_header(canvas, config)
    _draw_frame(canvas)
    _draw_watermark(canvas, config)

    frame_width = FRAME_RIGHT - FRAME_LEFT
    _paragraph(canvas, "Quittance de loyer", FRAME_LEFT, 210.0, frame_width, TITLE)
    _paragraph(
        canvas,
        f"Loyer {escape(quittance.period_label)}",
        FRAME_LEFT,
        227.0,
        frame_width,
        TITLE,
    )

    tenant = quittance.tenant
    left_column = (
        (270.0, f"Reçu de : {escape(tenant.display_name)}"),
        (305.0, f"la somme de {_bold(quittance.total_label)}"),
        (330.0, f"le {_bold(quittance.payment_date_label)}"),
        (
            360.0,
            "pour loyer et accessoires des locaux situés au : "
            f"{_bold(tenant.address)}",
        ),
        (
            415.0,
            f"en paiement du terme du mois {_bold(quittance.period_label)}",
        ),
        (
            470.0,
            f"Fait à {escape(config.landlord.city)} le "
            f"{_bold(quittance.issued_on_label)}",
        ),
        (500.0, "Signature du bailleur"),
    )
    for top, markup in left_column:
        _paragraph(canvas, markup, CONTENT_LEFT, top, COLUMN_1_WIDTH)

    _draw_signature(canvas, config, top=520.0)

    right_column = (
        (270.0, "<b>Détail :</b>"),
        (305.0, f"- Loyer nu : {_bold(quittance.rent_label)}"),
        (330.0, f"- Provisions de charges : {_bold(quittance.charges_label)}"),
        (390.0, f"Montant total du terme : {_bold(quittance.total_label)}"),
        (420.0, f"- Paiement locataire : {_bold(quittance.total_label)}"),
        (450.0, f"- Solde à payer : {_bold('0,00 €')}"),
    )
    for top, markup in right_column:
        _paragraph(canvas, markup, COLUMN_2_LEFT, top, COLUMN_2_WIDTH)

    _paragraph(canvas, LEGAL_NOTICE, FRAME_LEFT, 700.0, frame_width, FOOTER)

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

    _draw_landlord_header(canvas, config)
    _draw_watermark(canvas, config)

    frame_width = FRAME_RIGHT - FRAME_LEFT
    _paragraph(
        canvas, "ATTESTATION D'HÉBERGEMENT", FRAME_LEFT, 210.0, frame_width, TITLE
    )

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

    top = 270.0
    for markup in corps:
        hauteur = _paragraph(canvas, markup, CONTENT_LEFT, top, frame_width - 20.0)
        top += hauteur + 18.0

    _paragraph(
        canvas,
        f"Fait à {escape(landlord.city)} le {_bold(attestation.issued_on_label)}",
        CONTENT_LEFT,
        top + 30.0,
        frame_width - 20.0,
    )
    _paragraph(canvas, "Signature du bailleur", CONTENT_LEFT, top + 60.0, 250.0)
    _draw_signature(canvas, config, top=top + 80.0)

    canvas.showPage()
    canvas.save()
    return path
