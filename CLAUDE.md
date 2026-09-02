# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Ce que fait le projet

Génère les quittances de loyer et attestations d'hébergement en PDF pour les
locataires de trois biens (colocations d'Anzin et Valenciennes, appartement de
Lille), et les envoie par email. Usage personnel du bailleur, en local, sur
Windows.

## Commandes

```bash
python -m pip install -e ".[dev]"   # installe le paquet et les outils de test
python -m pytest                    # 89 tests
python -m pytest tests/test_pdf.py::test_quittance_produit_un_pdf_a4   # un seul test
python -m quittances locataires     # verifie que config.yaml se charge
```

Il n'y a ni linter ni formateur configurés.

## Architecture

Quatre couches, du bas vers le haut :

| Couche | Modules | Dépendances |
|---|---|---|
| Données | `config.py`, `formatting.py` | aucune |
| Métier | `documents.py` | config, formatting |
| Effets | `pdf.py`, `mailer.py` | config, documents |
| Orchestration | `cli.py` | tout |

**`documents.py` ne connaît ni le PDF ni l'email.** `Quittance` et
`Attestation` portent les calculs, les libellés et les chemins de sortie ; c'est
ce qui permet de tester montants, noms de fichiers et corps de mail sans rien
générer. Ne pas y introduire d'appel à ReportLab ou smtplib.

**`config.yaml` est l'unique source des données métier** (bailleur, biens,
locataires). Aucune donnée nominative ne doit revenir dans les sources — c'était
le défaut de l'ancien `helper.js`, remplacé lors du portage Node → Python.

## Invariants à ne pas casser

**L'email ne part jamais sans `--envoyer`.** L'ancienne version envoyait à chaque
exécution, y compris quand le PDF n'avait pas été régénéré. Un envoi groupé
(`--tous --envoyer`) demande confirmation interactive.
`tests/test_cli.py::test_aucun_email_sans_option_envoyer` garde ce comportement.

**Les montants sont des `Decimal`, jamais des flottants.** L'ancien JS calculait
`320.00 + 80.00` puis `.toString()` et affichait `400 €` à côté de `320.00 €`.
`format_amount` produit la typographie française avec espaces insécables
(U+00A0) : les tests comparent avec la constante `NBSP`, ecrite sous forme
d'echappement `"\u00a0"` pour qu'aucun espace ordinaire ne s'y glisse.

**Les mois français sont codés en dur** dans `formatting.MOIS`.
`locale.setlocale(LC_TIME, "fr_FR")` n'est pas fiable sous Windows.

**Rien n'est deviné à partir d'un prénom.** `title` est facultatif ; absent, la
civilité est omise du document (« Reçu de : MORÓN Elsa ») et l'attestation écrit
« né(e) ». Ne pas ajouter d'inférence de genre.

**Les noms composés restent entiers.** `last_name` peut contenir des espaces
(« Aranibar Campero », « Dos Santos »). L'ancien `fullName.split(" ")[1]`
tronquait ces noms — ne pas réintroduire de découpage sur l'espace.

## Rendu PDF

La mise en page est éditoriale : pas de cadre, hiérarchie portée par la
typographie et le blanc, montant réglé en élément dominant. `assets.watermark` est facultatif et **volontairement absent de `config.yaml`** :
le rendu sans filigrane a été préféré. Le code reste en place — renseigner la
clé le fait réapparaître en bas à droite à 10 % d'opacité.

Les constantes de `pdf.py` sont exprimées **depuis le haut de la page**, hérité
de la mise en page pdfkit d'origine ; `_y()` convertit vers l'origine
bas-gauche de ReportLab. Tout le texte passe par des `Paragraph` (retour à la
ligne automatique et gras en ligne via `<b>`), positionnés par `_paragraph()`
qui prend une ordonnée haute. Les valeurs injectées dans le balisage doivent
passer par `escape()` ou `_bold()`, sinon une esperluette dans une adresse casse
le rendu.

Les documents sont en A4. Les tests vérifient le contenu via `pypdf` en
aplatissant les espaces (`" ".join(texte.split())`), car ReportLab coupe les
lignes à des endroits variables.

## Tests

Les tests de `test_mailer.py` doivent neutraliser `load_dotenv` : `find_dotenv()`
remonte depuis `quittances/mailer.py`, pas depuis le répertoire courant, donc un
`monkeypatch.chdir` ne suffit pas à isoler du vrai `.env` du dépôt. La fixture
autouse `environnement_propre` s'en charge.

Les fixtures de `conftest.py` construisent une config de test pointant sur les
vraies images de `img/`.

Le locataire `Peter` de `config.yaml` n'est pas un locataire : c'est une entree
de test qui envoie sur l'adresse du bailleur, utilisee pour valider la chaine
complete avant de viser de vrais destinataires. `--tous` l'inclut.

## Pièges

`src/` n'est **pas** le code du paquet : c'est `src/data_2025.py`, des relevés
bancaires bruts consommés par `parse_releve_de_comptes.py`, un script comptable
indépendant du générateur de quittances. Le paquet est `quittances/`.

`config.yaml` est versionné et contient noms, emails et adresses des locataires ;
`src/data_2025.py` contient les relevés bancaires. **Le dépôt doit rester
privé.** `.env` et `credentials.json` sont exclus par `.gitignore`.

`credentials.json` est une clé de compte de service Google, vestige du code
Drive supprimé lors du portage. Elle ne sert plus à rien et ne peut pas servir à
l'envoi SMTP.

Le shell du projet est PowerShell : `printf`, `head`, `touch` et les chaînages
`&&` n'y existent pas. Les sorties accentuées de la CLI s'affichent correctement
dans le terminal, mais deviennent illisibles quand elles passent par un tube
(encodage cp1252) — ce n'est pas un bug du code.
