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
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph

from .config import Config
from .documents import (
    Attestation,
    AttestationDomicile,
    DepotGarantie,
    Quittance,
    Regularisation,
)
from decimal import Decimal

from .formatting import elision, format_amount, format_date

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

# Palette du graphique de regularisation. Les quatre creneaux catégoriels du
# guide dataviz, passes au validateur sur fond clair : bande de clarte, plancher
# de chroma, ecart CVD (pire paire ΔE 9,1) et plancher en vision normale (22,9)
# tous PASS. Le contraste de l'aqua et du jaune reste sous 3:1, ce qui exige un
# releve chiffre : le tableau qui suit le graphique le fournit.
#
# La teinte suit l'**intitule**, jamais le rang : un mois sans electricite ne
# doit pas repeindre les tranches des autres mois.
COULEUR_TRANCHE = {
    "Eau": HexColor("#2A78D6"),
    "Internet": HexColor("#EB6834"),
    "Électricité": HexColor("#1BAF7A"),
    "Supplément": HexColor("#EDA100"),
}
# La provision n'est pas une categorie mais un repere : elle reste neutre.
COULEUR_PROVISION = HexColor("#8A8A8A")

MARGE = 56.0
DROITE = PAGE_WIDTH - MARGE
COLONNE_2 = MARGE + 300.0
LARGEUR_COLONNE_1 = 265.0

# Boite de la signature. L'image conserve ses proportions a l'interieur.
SIGNATURE_LARGEUR = 240.0
SIGNATURE_HAUTEUR = 124.0

# Hauteur du bloc « Fait a ... / Signature », depuis sa regle de tete : 68 pt
# de libelles puis l'image. Sert a savoir s'il tient encore sur la page.
HAUTEUR_CLOTURE = 68.0 + SIGNATURE_HAUTEUR

# Derniere ordonnee utilisable, marge basse egale a la marge haute.
BAS_UTILE = PAGE_HEIGHT - MARGE

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
# Le fer a gauche evite les lezardes que la justification creuse dans une
# adresse coupee en fin de ligne.
CORPS_GAUCHE = _style("corps_gauche", fontSize=9.5, leading=15.5, alignment=TA_LEFT)
MENTION = _style("mention", fontSize=6.4, leading=9.0, textColor=GRIS_MOYEN,
                 alignment=TA_JUSTIFY)


def _wrap(canvas, contenu: str, police: str, taille: float,
          largeur: float) -> list[str]:
    """Coupe `contenu` en lignes tenant dans `largeur`.

    Les libelles des lignes manuelles sont libres : « Retenue pour remise en
    etat du mur de la chambre ». Tronquer priverait le locataire de
    l'explication, et deborder ecrirait par-dessus le montant.
    """
    lignes: list[str] = []
    courante = ""
    for mot in contenu.split():
        essai = f"{courante} {mot}".strip()
        if courante and canvas.stringWidth(essai, police, taille) > largeur:
            lignes.append(courante)
            courante = mot
        else:
            courante = essai
    if courante:
        lignes.append(courante)
    return lignes or [""]


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


def _barre(canvas, x: float, bas: float, largeur: float, hauteur: float,
           couleur, arrondi: bool) -> None:
    """Barre pleine, coins hauts arrondis, pied carre sur la ligne de base.

    Seule la tranche du sommet est arrondie : une pile dont chaque segment le
    serait ressemblerait a des gelules empilees, pas a une barre.
    """
    if hauteur <= 0:
        return
    rayon = min(3.0, largeur / 2.0, hauteur) if arrondi else 0.0
    k = rayon * 0.5523
    haut = bas + hauteur
    chemin = canvas.beginPath()
    chemin.moveTo(x, bas)
    chemin.lineTo(x, haut - rayon)
    if rayon:
        chemin.curveTo(x, haut - rayon + k, x + rayon - k, haut, x + rayon, haut)
        chemin.lineTo(x + largeur - rayon, haut)
        chemin.curveTo(x + largeur - rayon + k, haut, x + largeur,
                       haut - rayon + k, x + largeur, haut - rayon)
    else:
        chemin.lineTo(x + largeur, haut)
    chemin.lineTo(x + largeur, bas)
    chemin.close()
    canvas.saveState()
    canvas.setFillColor(couleur)
    canvas.drawPath(chemin, stroke=0, fill=1)
    canvas.restoreState()


def _pastille(canvas, x: float, haut: float, couleur) -> float:
    """Petit carre de legende. Renvoie la largeur occupee."""
    canvas.saveState()
    canvas.setFillColor(couleur)
    canvas.rect(x, _y(haut + 6.0), 6.0, 6.0, stroke=0, fill=1)
    canvas.restoreState()
    return 6.0


def _draw_comparatif(canvas, regul, haut: float) -> float:
    """Barres mensuelles : provision versee contre cout reel, empile par poste.

    Le locataire ne voit plus le budget de la maison, mais il doit comprendre
    d'ou vient son solde. Mois par mois, la provision qu'il a versee fait face
    a ce que le mois lui a reellement coute, decompose comme le tableau qui
    suit — meme intitules, memes montants.

    Renvoie la hauteur consommee.
    """
    if not regul.mensuel:
        return 0.0

    HAUTEUR = 52.0
    # Tete reservee a l'etiquette du pic. Elle doit loger le texte *entier* :
    # `_text` positionne le haut des capitales, et la ligne descend ensuite.
    TETE = 12.0
    depart = haut
    tranches = regul.tranches
    plafond = regul.plafond_mensuel
    if plafond <= 0:
        return 0.0

    # Pas de cartouche de legende : **le tableau en tient lieu**. Chaque ligne
    # y porte sa pastille, son intitule et son montant — identite jamais reduite
    # a la couleur, et plus complete qu'une legende, qui n'aurait rien dit des
    # sommes. Un cartouche aurait repete les memes mots douze lignes plus haut.

    base = _y(haut + HAUTEUR)
    echelle = (HAUTEUR - TETE) / float(plafond)

    # Une seule ligne de base, et pas de reglette haute : elle aurait porte la
    # meme valeur que l'etiquette du pic, deux fois la meme chose. Les etiquettes
    # directes passent avant la grille, et la grille avant un second axe.
    _rule(canvas, haut + HAUTEUR, MARGE, DROITE, GRIS_CLAIR, 0.5)

    bande = (DROITE - MARGE) / len(regul.mensuel)
    largeur = min(13.0, (bande - 12.0) / 2.0)
    pic = regul.pic_mensuel
    for index, (mois, lignes, provision) in enumerate(regul.mensuel):
        centre = MARGE + bande * (index + 0.5)
        gauche = centre - largeur - 1.0          # 2 pt de blanc entre les deux

        _barre(canvas, gauche, base, largeur,
               float(provision) * echelle, COULEUR_PROVISION, True)

        empile = 0.0
        visibles = [(n, lignes[n]) for n in tranches if lignes.get(n)]
        for rang, (nom, montant) in enumerate(visibles):
            hauteur = float(montant) * echelle
            # 2 pt de fond entre deux tranches, plutot qu'un contour.
            creux = 2.0 if rang < len(visibles) - 1 else 0.0
            _barre(canvas, centre + 1.0, base + empile, largeur,
                   max(hauteur - creux, 0.0), COULEUR_TRANCHE.get(nom, GRIS),
                   rang == len(visibles) - 1)
            empile += hauteur

        _text(
            canvas, regul.mois_label[index],
            centre - canvas.stringWidth(regul.mois_label[index], FONT, 6.0) / 2.0,
            haut + HAUTEUR + 12.0, FONT, 6.0, GRIS_MOYEN,
        )
        # Un montant par barre serait illisible : seul l'extreme est etiquete.
        if pic and index == pic[0]:
            etiquette = format_amount(pic[1])
            _text(
                canvas, etiquette,
                centre + 1.0 + largeur / 2.0
                - canvas.stringWidth(etiquette, FONT_BOLD, 6.5) / 2.0,
                # 10 pt : la hauteur de la ligne, plus trois de blanc. A
                # quatre, le texte retombait sur le sommet de la barre.
                haut + HAUTEUR - empile - 10.0, FONT_BOLD, 6.5, GRIS,
            )
    # Hauteur reellement consommee, etiquettes de mois comprises : un forfait
    # laissait l'en-tete du tableau s'ecrire sur « sept. ».
    return haut + HAUTEUR + 28.0 - depart


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


def render_regularisation(
    regul: Regularisation, config: Config, path: Path
) -> Path:
    """Ecrit la regularisation de charges en PDF a `path`.

    Grille editoriale de la quittance, avec un tableau a trois colonnes : le
    cout de la maison, la quote-part du locataire, et ce qui lui revient. Voir
    le cout total a cote de sa part rend la repartition verifiable.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tenant = regul.tenant
    canvas = pdfcanvas.Canvas(str(path), pagesize=A4)
    canvas.setTitle(f"Régularisation de charges - {tenant.full_name}")
    canvas.setAuthor(config.landlord.legal_name)

    _draw_watermark(canvas, config)
    _draw_header(canvas, config)
    _draw_title(canvas, "Régularisation de charges", tenant.full_name)

    _label(canvas, regul.libelle_solde, MARGE, 246.0)
    couleur = VERT if regul.solde <= 0 else ACCENT
    _text(canvas, format_amount(regul.montant_du), MARGE, 260.0,
          FONT_BOLD, 30.0, couleur)
    _label(canvas, "Période", DROITE - 150.0, 246.0)
    _text(canvas, regul.periode_label, DROITE - 150.0, 262.0, FONT, 12.0, GRIS)

    _rule(canvas, 306.0)

    prorata = (
        f", et de {regul.jours_dus} jours d'occupation sur "
        f"{regul.jours_periode}"
        if regul.prorata_applique
        else ""
    )
    reserve = (
        " Les suppléments qui vous sont propres sont imputés à part."
        if regul.dediees
        else ""
    )
    # La note rejoint le paragraphe d'introduction au lieu de former un bloc
    # sous les totaux. Elle y disait l'adresse une seconde fois, et se lisait
    # comme un ajout apres coup alors qu'elle situe le decompte : le lecteur
    # doit l'avoir avant les chiffres, pas apres.
    contexte = f" {escape(regul.note)}" if regul.note else ""
    hauteur_intro = _paragraph(
        canvas,
        f"Charges réelles du logement situé au {_bold(tenant.address)}, "
        f"réparties sur chaque poste au prorata de la surface occupée "
        f"({escape(tenant.share_label)}){prorata}.{contexte} Le graphique "
        f"compare, mois par mois, la provision versée au coût réellement "
        f"supporté.{reserve}",
        MARGE, 322.0, DROITE - MARGE, CORPS_GAUCHE,
    )

    # Tableau : cout de la maison, cout mensuel, part du locataire.
    #
    # La quote-part et les jours ne sont plus en colonnes : ils valaient la
    # meme chose sur chaque ligne, et trois colonnes identiques n'apprennent
    # rien. La phrase d'introduction les porte une fois. Le cout mensuel les
    # remplace, seule grandeur directement comparable a la provision appelee
    # chaque mois sur la quittance.
    col_mois, col_du = DROITE - 110.0, DROITE
    largeur_libelle = (DROITE - 82.0) - MARGE
    # Le tableau suit le paragraphe au lieu de partir d'une ordonnee fixe : le
    # texte gagne ou perd une ligne selon le locataire — prorata, supplements,
    # adresse longue — et l'en-tete venait s'ecrire dessus.
    haut = max(348.0, 322.0 + hauteur_intro + 10.0)

    haut += _draw_comparatif(canvas, regul, haut)

    # Plus de colonne MAISON : le cout total du logement disait aux uns ce que
    # paient les autres. La quote-part suffit a verifier sa propre part, et le
    # detail par nature de charges reste — un decompte le doit.
    _label(canvas, "Poste", MARGE, haut)
    _text_right(canvas, "PAR MOIS", col_mois, haut, FONT_BOLD, 6.5, GRIS_MOYEN)
    _text_right(canvas, "VOTRE PART", col_du, haut, FONT_BOLD, 6.5, GRIS_MOYEN)
    haut += 13.0
    _rule(canvas, haut)
    haut += 10.0

    for poste in regul.postes:
        # Pastille : elle relie la ligne a sa tranche du graphique. L'identite
        # reste portee par l'intitule, jamais par la couleur seule.
        if regul.mensuel and poste in COULEUR_TRANCHE:
            _pastille(canvas, MARGE, haut - 1.0, COULEUR_TRANCHE[poste])
        _text(canvas, poste, MARGE + 12.0, haut, FONT, 9.5)
        montant = regul.reel.get(poste, Decimal("0"))
        _text_right(
            canvas, format_amount(regul.par_mois(montant)),
            col_mois, haut, FONT, 9.5, GRIS,
        )
        _text_right(canvas, format_amount(montant), col_du, haut, FONT, 9.5)
        haut += 15.0

    # Supplements imputes a une seule personne. Ils n'ont ni quote-part ni
    # jours a montrer : les melanger aux postes partages rendrait la colonne
    # PART incoherente, puisqu'ils ne sont justement pas partages.
    if regul.dediees:
        for motif, montant in regul.dediees:
            if regul.mensuel:
                _pastille(canvas, MARGE, haut - 1.0, COULEUR_TRANCHE["Supplément"])
            replis = _wrap(canvas, motif, FONT, 9.5, largeur_libelle)
            _text_right(
                canvas, format_amount(regul.par_mois(montant)),
                col_mois, haut, FONT, 9.5, GRIS,
            )
            _text_right(canvas, format_amount(montant), col_du, haut, FONT, 9.5)
            for repli in replis:
                _text(canvas, repli, MARGE + 12.0, haut, FONT, 9.5)
                haut += 13.0
            haut += 5.0
        _text(
            canvas, "Imputé directement, non réparti entre les locataires.",
            MARGE, haut - 2.0, FONT, 7.5, GRIS_MOYEN,
        )
        haut += 12.0

    _rule(canvas, haut - 4.0)
    haut += 6.0
    for libelle, montant, gras, serie in (
        ("Total des charges réelles", regul.total_reel, True, False),
        ("Provisions versées", regul.provisions, False, True),
    ):
        police = FONT_BOLD if gras else FONT
        # Les provisions sont une serie du graphique, au meme titre que les
        # postes : elles portent donc leur pastille et s'alignent sur eux. Les
        # deux lignes calculees restent en retrait, sans pastille.
        decalage = 0.0
        if serie and regul.mensuel:
            _pastille(canvas, MARGE, haut - 1.0, COULEUR_PROVISION)
            decalage = 12.0
        _text(canvas, libelle, MARGE + decalage, haut, police, 9.5)
        _text_right(
            canvas, format_amount(regul.par_mois(montant)),
            col_mois, haut, police, 9.5, GRIS,
        )
        _text_right(canvas, format_amount(montant), col_du, haut, police, 9.5)
        haut += 15.0

    # Lignes portees a la main. Le libelle dit pourquoi, le signe dit dans quel
    # sens : « Degradations 120,00 € » ne dirait pas si la somme est retenue ou
    # rendue. Les deux sont indispensables, d'ou la mention qui les suit.
    if regul.lignes:
        for ligne in regul.lignes:
            replis = _wrap(canvas, ligne.libelle, FONT, 9.5, largeur_libelle)
            _text_right(
                canvas, ligne.montant_label, col_du, haut, FONT, 9.5,
                VERT if ligne.montant > 0 else ACCENT,
            )
            for repli in replis:
                _text(canvas, repli, MARGE, haut, FONT, 9.5)
                haut += 13.0
            haut += 5.0
        _text(
            canvas, "Un montant positif est en votre faveur.",
            MARGE, haut - 2.0, FONT, 7.5, GRIS_MOYEN,
        )
        haut += 12.0

    _rule(canvas, haut - 4.0)
    haut += 6.0
    _text(canvas, regul.libelle_solde, MARGE, haut, FONT_BOLD, 10.5)
    _text_right(
        canvas, format_amount(regul.par_mois(regul.montant_du)), col_mois, haut,
        FONT_BOLD, 10.5, GRIS,
    )
    _text_right(
        canvas, format_amount(regul.montant_du), col_du, haut,
        FONT_BOLD, 10.5, couleur,
    )
    haut += 14.0


    # Pas de MENTION_LEGALE ici : elle parle de « cette quittance ou ce recu »
    # et de termes de loyer, ce qu'une regularisation de charges n'est pas. Le
    # pied de page lui revient, ce qui laisse de la place aux lignes manuelles.
    #
    # La regularisation est le seul document dont la hauteur varie : le nombre
    # de postes et de lignes manuelles depend du locataire. Quand le bloc de
    # cloture ne tient plus dans la page, il passe a la suivante plutot que de
    # deborder sous le bord.
    if haut + 4.0 + HAUTEUR_CLOTURE > BAS_UTILE:
        canvas.showPage()
        _draw_watermark(canvas, config)
        _draw_header(canvas, config)
        haut = 160.0

    _draw_closing(canvas, config, format_date(regul.issued_on), haut=haut + 2.0)

    canvas.showPage()
    canvas.save()
    return path


def render_depot_garantie(
    depot: DepotGarantie, config: Config, path: Path
) -> Path:
    """Ecrit le recu de depot de garantie en PDF a `path`.

    Reprend la grille editoriale de la quittance : meme en-tete, meme titre,
    meme encart de montant. Le locataire recoit les deux documents a quelques
    jours d'intervalle, ils doivent se ressembler.

    Le corps est ferre a gauche, comme l'attestation de domicile : justifie, il
    se lezardait sur les adresses longues.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    landlord = config.landlord
    tenant = depot.tenant

    canvas = pdfcanvas.Canvas(str(path), pagesize=A4)
    canvas.setTitle(f"Reçu de dépôt de garantie - {tenant.full_name}")
    canvas.setAuthor(landlord.legal_name)

    _draw_watermark(canvas, config)
    _draw_header(canvas, config)
    _draw_title(canvas, "Reçu de dépôt de garantie", tenant.full_name)

    _label(canvas, "Montant reçu", MARGE, 246.0)
    _text(canvas, depot.amount_label, MARGE, 260.0, FONT_BOLD, 30.0, NOIR)
    _label(canvas, "Versé le", DROITE - 120.0, 246.0)
    _text(canvas, depot.received_on_label, DROITE - 120.0, 262.0, FONT, 13.0, GRIS)

    _rule(canvas, 322.0)

    corps = (
        f"Je soussigné {_bold(landlord.legal_name)}, bailleur, déclare avoir "
        f"reçu de {_bold(tenant.full_name)}, qui occupe "
        f"{escape(tenant.dwelling)} au {_bold(tenant.address)}, la somme de "
        f"{_bold(depot.amount_words)} ({_bold(depot.amount_label)}) au titre "
        f"du dépôt de garantie, versée le "
        f"{_bold(depot.received_on_label)}.",
        "Ce dépôt correspond à deux mois de loyer hors charges.",
        "Il est conservé pendant toute la durée de la location, puis restitué "
        "dans le mois qui suit l'état des lieux de sortie. Il pourra être "
        "réduit du montant des loyers impayés, des excédents de consommation "
        "et de charges, ainsi que des frais de remise en état, conformément à "
        "la législation en vigueur.",
        f"En cas de non-paiement du loyer du mois de "
        f"{escape(depot.first_month_label)} et d'absence du locataire au cours "
        f"de ce même mois, ce dépôt sera considéré comme des frais de "
        f"réservation et restera acquis au bailleur.",
    )
    haut = 348.0
    for markup in corps:
        haut += _paragraph(
            canvas, markup, MARGE, haut, DROITE - MARGE, CORPS_GAUCHE
        ) + 16.0

    _draw_closing(canvas, config, depot.issued_on_label, haut=haut + 14.0)

    canvas.showPage()
    canvas.save()
    return path


def render_attestation_domicile(
    attestation: AttestationDomicile, config: Config, path: Path
) -> Path:
    """Ecrit l'attestation de domicile en PDF a `path`.

    Mise en page de lettre administrative, et non la grille editoriale des
    quittances : ce document est lu par un tiers (transporteur, banque,
    prefecture) qui attend une forme conventionnelle.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    landlord = config.landlord
    tenant = attestation.tenant

    canvas = pdfcanvas.Canvas(str(path), pagesize=A4)
    canvas.setTitle("Attestation de domicile")
    canvas.setAuthor(landlord.legal_name)

    _draw_header(canvas, config)

    # Lieu et date en vis-a-vis du bloc bailleur, comme dans une lettre.
    _text_right(
        canvas,
        f"{landlord.city}, le {attestation.issued_on_label}",
        DROITE, 118.0, FONT, 9.5, NOIR,
    )

    _paragraph(
        canvas, "ATTESTATION DE DOMICILE", MARGE, 190.0, DROITE - MARGE,
        _style("titre", fontName=FONT_BOLD, fontSize=14, leading=18,
               alignment=TA_CENTER, textColor=ARDOISE),
    )
    _rule(canvas, 220.0)

    adresse_bailleur = ", ".join(landlord.address_lines)
    corps = (
        f"Je soussigné {_bold(landlord.legal_name)}, propriétaire-bailleur, "
        f"demeurant {escape(adresse_bailleur)},",
        f"atteste que {_bold(tenant.full_name)} est locataire "
        f"{elision(tenant.dwelling)}{escape(tenant.dwelling)} à compter du "
        f"{_bold(attestation.lease_start_label)}, à l'adresse suivante : "
        f"{_bold(tenant.address)}.",
        escape(attestation.objet),
    )
    haut = 252.0
    for markup in corps:
        haut += _paragraph(
            canvas, markup, MARGE, haut, DROITE - MARGE, CORPS_GAUCHE
        ) + 20.0

    _text(
        canvas,
        f"Fait à {config.landlord.city}, le {attestation.issued_on_label}.",
        MARGE, haut + 24.0, FONT, 9.5, NOIR,
    )
    _label(canvas, "Signature du bailleur", MARGE, haut + 54.0)
    _draw_signature(canvas, config, haut + 70.0)
    _text(
        canvas, landlord.legal_name,
        MARGE, haut + 70.0 + SIGNATURE_HAUTEUR + 4.0, FONT, 9.5, NOIR,
    )

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
