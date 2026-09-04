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

Enfin, une génération à blanc dans un dossier jetable, qui n'envoie rien :

```bash
quittances --locataire Alice --dossier .\essai
```

Pour éprouver aussi la chaîne d'envoi sans écrire à un locataire, ajouter
temporairement dans `config.yaml` une entrée pointant sur sa propre adresse,
puis la retirer.

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

Après installation, la commande s'appelle `quittances`. La sous-commande
`quittance` est implicite, la période vaut le mois courant, et `--maison`
sous-entend « tous les locataires de cette maison ». L'envoi mensuel tient donc
en une ligne :

```bash
quittances --maison anzin --envoyer
```

Un seul locataire, pour un mois précis :

```bash
quittances --locataire Jin --periode 2026-09
```

Toutes les maisons d'un coup :

```bash
quittances --tous --envoyer
```

Voir qui est à jour, mois par mois :

```bash
quittances suivi --depuis 2026-09
```

```
LOCATAIRE    MAISON   09 10 11 12 01 02 03 04 05 06 07 08   RETARD
Alice R.     anzin    ✓                                         -
Elsa M.      anzin    ·                                         1  420,00 €

Annee septembre 2026 - août 2027 : 10 locataires, 12 mois
  Attendu     49 920,00 €   120 termes
  Acquitté     2 070,00 €   5 quittances émises
  En retard    2 090,00 €   5 mois échus impayés
  À venir     45 760,00 €   110 mois non échus
```

Sans `--jusqu-a`, la période couvre **douze mois** à partir de `--depuis`,
c'est-à-dire l'année de bail. « Attendu » est donc le total annuel, fixe, et
c'est « Acquitté » qui progresse mois après mois.

Les mois postérieurs au mois courant sont affichés mais comptés à part : un
loyer de mars n'est pas un impayé en septembre. Seule la ligne « En retard »
mesure ce qui est réellement dû, et c'est elle qui doit guider les relances.

`suivi` lit l'existence des quittances sur le disque : une quittance n'étant
émise qu'une fois le loyer encaissé, sa présence vaut paiement. L'application ne
consulte aucun compte bancaire. Ajouter `--manquants` pour ne lister que les
retards, `--jusqu-a` pour borner, `--maison` ou `--locataire` pour restreindre.

Relancer ceux qui ont un mois échu sans quittance :

```bash
quittances relance --depuis 2026-09
```

Sans `--envoyer`, la commande affiche les messages sans rien expédier — une
relance part à ton nom, elle se relit avant. Seuls les mois **échus** déclenchent
un rappel : un loyer de mars n'est jamais réclamé en septembre.

Le message est **bilingue** (français puis anglais). Il liste les mois concernés
et le total dû, rappelle l'échéance du bail, et suggère un virement programmé —
la plupart des retards venant d'un oubli.

Lister les locataires configurés :

```bash
quittances locataires
```

Une attestation d'hébergement :

```bash
quittances attestation --locataire Jin --depuis 2026-09-01
```

Sans installation, tout fonctionne aussi via `python -m quittances`.

### Options

| Option | Effet |
|---|---|
| `--locataire CLE` | locataire ciblé, répétable |
| `--tous` | tous les locataires, toutes maisons confondues |
| `--maison CLE` | tous les locataires de cette maison |

| `--periode AAAA-MM` | mois de la quittance, défaut : mois courant |
| `--date-paiement DATE` | défaut : 1er jour de la période |
| `--loyer` / `--charges` | remplacent les montants de `config.yaml` |
| `--date DATE` | date d'émission, défaut : aujourd'hui |
| `--depuis DATE` | début d'hébergement (attestation) |
| `--dossier CHEMIN` | racine de sortie, défaut : dossier du bien |
| `--forcer` | régénère un PDF déjà présent |
| `--envoyer` | envoie l'email (sinon, génération seule) |
| `--config CHEMIN` | autre `config.yaml` |

`--locataire`, `--maison` et `--tous` s'excluent mutuellement. La maison d'un
locataire nommé est déduite de sa fiche : deux locataires de maisons
différentes peuvent donc être traités dans la même commande.

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
