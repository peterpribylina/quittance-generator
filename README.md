# quittance-generator

Génère les quittances de loyer et les attestations d'hébergement au format PDF,
et les envoie par email aux locataires.

## Installation

### 1. Prérequis

Python 3.10 ou plus récent, et git. Vérifier :

```bash
python --version
```

Si la commande ouvre le Microsoft Store ou reste sans réponse, installer Python
depuis [python.org](https://www.python.org/downloads/) en cochant
« Add python.exe to PATH » pendant l'installation.

### 2. Récupérer le code

```bash
git clone https://github.com/peterpribylina/quittance-generator.git
```

```bash
cd quittance-generator
```

### 3. Environnement virtuel (recommandé)

Isole les dépendances du reste de la machine.

```bash
python -m venv .venv
```

```bash
.\.venv\Scripts\Activate.ps1
```

Si PowerShell refuse le script d'activation (`l'exécution de scripts est
désactivée`), l'autoriser une fois pour l'utilisateur courant :

```bash
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

L'invite affiche alors `(.venv)`. À refaire à chaque nouveau terminal ; sans
environnement virtuel, sauter cette étape et passer à la suivante.

### 4. Installer l'application et ses dépendances

```bash
python -m pip install -e ".[dev]"
```

Installe ReportLab, PyYAML, python-dotenv, ainsi que pytest et pypdf pour les
tests. `-e` installe en mode éditable : les modifications du code sont prises en
compte sans réinstaller.

### 5. Configurer

`config.yaml` est versionné : un clone du dépôt le contient déjà, avec les
locataires réels. Il n'y a rien à copier — le remplacer par le modèle
effacerait ces données. Pour repartir de zéro sur une autre installation :

```bash
Copy-Item config.example.yaml config.yaml
```

`.env` en revanche n'est jamais versionné et doit être créé :

```bash
Copy-Item .env.example .env
```

Éditer ensuite :

```bash
notepad config.yaml
```

`config.yaml` décrit le bailleur, les biens et les locataires — c'est la seule
source des données métier. `.env` contient les identifiants d'envoi. Les deux
restent locaux ; `.env` est exclu du dépôt.

Gmail exige un [mot de passe d'application](https://myaccount.google.com/apppasswords) ;
le mot de passe du compte est refusé. Le générer, puis le coller dans `.env`
après `SMTP_PASSWORD=`.

### 6. Vérifier

```bash
python -m quittances locataires
```

La liste des locataires confirme que `config.yaml` est lu correctement. Puis la
suite de tests :

```bash
python -m pytest
```

Enfin, un essai complet sur sa propre adresse avant de viser un vrai locataire :

```bash
python -m quittances quittance --locataire Peter --periode 2026-09 --loyer 1 --charges 0 --envoyer
```

### Champs d'un locataire

`first_name`, `last_name` et `property` sont obligatoires. Le reste est
facultatif :

| Champ | Effet s'il est absent |
|---|---|
| `title` | la civilité est omise du document, plutôt que devinée d'après le prénom |
| `email` | le PDF est produit, mais `--envoyer` refuse ce locataire |
| `rent` / `charges` | il faut passer `--loyer` et `--charges` |
| `birth_date` / `birth_place` | l'attestation d'hébergement est refusée |

## Utilisation

Lister les locataires configurés :

```bash
python -m quittances locataires
```

Générer une quittance (loyer et charges repris de `config.yaml` s'ils y sont) :

```bash
python -m quittances quittance --locataire Jin --periode 2025-09
```

Générer **et** envoyer par email :

```bash
python -m quittances quittance --locataire Jin --periode 2025-09 --envoyer
```

Tout un bien en une fois :

```bash
python -m quittances quittance --tous --bien anzin --periode 2025-09 --envoyer
```

Une attestation d'hébergement :

```bash
python -m quittances attestation --locataire Jin --depuis 2025-09-01
```

### Options

| Option | Effet |
|---|---|
| `--locataire CLE` | locataire ciblé, répétable |
| `--tous` | tous les locataires |
| `--bien CLE` | restreint `--tous` à un bien |
| `--periode AAAA-MM` | mois de la quittance (obligatoire) |
| `--date-paiement DATE` | défaut : 1er jour de la période |
| `--loyer` / `--charges` | remplacent les montants de `config.yaml` |
| `--date DATE` | date d'émission, défaut : aujourd'hui |
| `--depuis DATE` | début d'hébergement (attestation) |
| `--dossier CHEMIN` | racine de sortie, défaut : dossier du bien |
| `--forcer` | régénère un PDF déjà présent |
| `--envoyer` | envoie l'email (sinon, génération seule) |
| `--config CHEMIN` | autre `config.yaml` |

Les dates s'écrivent `AAAA-MM-JJ` ou `JJ/MM/AAAA`.

**L'email n'est jamais envoyé sans `--envoyer`.** Un envoi groupé (`--tous
--envoyer`) demande confirmation.

## Sortie

```
<dossier du bien>/<Prenom_Nom>/Quittances/Quittance_de_loyer_<Prenom>_<NOM>_<AAAA-MM>.pdf
<dossier du bien>/<Prenom_Nom>/Docs/Attestation_hebergement_<Prenom>_<NOM>_<AAAA>.pdf
```

Les dossiers manquants sont créés automatiquement.

## Développement

```bash
python -m pytest
```

| Module | Rôle |
|---|---|
| `quittances/config.py` | lecture et validation de `config.yaml` |
| `quittances/documents.py` | modèles métier, calculs, chemins de sortie |
| `quittances/pdf.py` | rendu PDF (ReportLab) |
| `quittances/mailer.py` | construction et envoi SMTP |
| `quittances/cli.py` | interface en ligne de commande |
| `quittances/formatting.py` | dates, mois et montants en français |

Les modèles ne connaissent ni le PDF ni l'email, ce qui permet de tester les
calculs et les libellés sans rien générer.

## Historique

Version 2.1 : refonte de la mise en page. Le cadre et la grille hérités de
pdfkit disparaissent au profit d'une hiérarchie typographique — le montant réglé
et la période, les deux informations que cherche le locataire, arrivent avant le
détail comptable. Signature agrandie, filigrane retiré (réactivable via `assets.watermark`).


Version 2.0 : portage de Node.js/pdfkit vers Python/ReportLab. Corrections
apportées au passage :

- l'attestation d'hébergement plantait (`generateFooter` inexistant) et
  affichait `undefined` faute de date et lieu de naissance en configuration ;
- le total était calculé en flottant puis converti en chaîne : `320.00 + 80.00`
  s'affichait `400 €` à côté de `320.00 €` ; il est désormais en `Decimal` et
  formaté à la française (`400,00 €`) ;
- les noms composés étaient tronqués (« Matilde Aranibar Campero » perdait
  « Campero ») ;
- l'écriture du PDF échouait si le dossier du locataire n'existait pas ;
- l'email partait à chaque exécution, même sans régénération du document ;
- le mot de passe Gmail était en dur dans les sources ;
- le filigrane débordait de 300 pt hors de la page ;
- les documents sont produits en A4 et non plus en Letter US.

Le script comptable `parse_releve_de_comptes.py` (analyse des relevés
bancaires) est indépendant et n'a pas été modifié.
