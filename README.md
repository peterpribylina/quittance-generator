# quittance-generator

Produit les documents locatifs au format PDF et les envoie par email aux
locataires : quittances de loyer, attestations de domicile et d'hébergement,
reçus de dépôt de garantie. Suit aussi les loyers encaissés, les attestations
d'assurance reçues et les dépôts de garantie, et relance ce qui manque.

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
| `lease_start` | il faut passer `--depuis` (domicile) ou `--recu-le` (caution) |
| `lease_end` | le locataire est réputé en place : aucune vacance calculée |
| `preavis` | vaut `true` : le mois de départ est dû en entier |
| `room` | la chambre n'est pas située (« R+2 », « RDC jardin ») |
| `share` | pas de quote-part pour répartir les charges annuelles |

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

L'email accompagnant la quittance est **bilingue et mis en forme** : montant
réglé en évidence, détail loyer et charges, et un rappel de conserver le
document — il sert de justificatif de domicile pour la CAF ou un dossier de
garant.

### Quotes-parts de surface

Chaque locataire porte la situation de sa chambre (`room`) et sa part de la
surface totale de **sa maison** (`share`), sur laquelle se répartiront les
charges annuelles :

```yaml
  Matilde:
    room: R+2
    share: 22.39
```

Les quotes-parts d'une même maison doivent totaliser **100 %**, à 0,05 point
près pour absorber les arrondis. Anzin et Valenciennes comptent chacune pour
100 %, pas 100 % à elles deux : les charges d'un immeuble se répartissent entre
ses occupants.

Une maison où aucun locataire n'a de quote-part reste valide — la répartition
n'y est simplement pas en place. En revanche une maison **partiellement**
renseignée est refusée : répartir sur une base incomplète donnerait des
montants faux sans que rien ne le signale.

```bash
quittances locataires
```

```
CLE       NOM                           MAISON   CHAMBRE          PART  LOYER
Matilde   Matilde Aranibar Campero      anzin    R+2           22,39 %  340,00 € + 70,00 € de charges
Henri     Henri Fournet                 vals     R+2           25,98 %  390,00 € + 80,00 € de charges
```

### Factures d'électricité

Les factures TotalEnergies se déposent dans `<maison>/Charges/<année>/` et se
lisent automatiquement :

```bash
quittances factures --maison anzin
```

```
  totalenergies_anzin_202609.pdf  29/07/2026 - 28/09/2026  69,46 € TTC
     Abonnement     fixe        19,99 € HT  29/08 - 28/09
     Consommation   variable    27,44 € HT  29/07 - 28/08
     CTA            fixe         2,45 € HT  29/08 - 28/09
     Accise         variable     8,00 € HT  29/07 - 28/08
```

**L'abonnement est facturé d'avance, la consommation à terme échu** : les deux
périodes sont décalées d'un mois, et un mois calendaire est donc couvert par
deux factures. Chaque poste est proratisé sur sa propre période, puis majoré de
la TVA au taux de la facture.

Les montants extraits sont **confrontés aux totaux imprimés**. Une facture dont
les postes ne reconstituent pas le total TTC est rejetée : une extraction
silencieusement fausse alimenterait une répartition de charges.

Un mois n'est **complet** que si les deux factures qui l'encadrent sont
présentes. Les mois partiels sont signalés et jamais inscrits — ils
sous-évalueraient les charges. `--ecrire` inscrit les mois complets dans
`charges.yaml`.

La catégorie `fixe` (abonnement, CTA) reste due par un locataire absent ; la
catégorie `variable` (consommation, accise) ne l'est pas.

### Charges d'une maison

Les charges se déclarent à deux endroits, selon qu'elles bougent ou non.

Les **fixes** vivent dans `config.yaml`, sous la maison :

```yaml
  anzin:
    charges_folder: C:/Users/.../Coloc_Anzin/Charges
    monthly_charges:
      eau: 80.00
      internet: 51.00
```

Les **variables** se relèvent facture par facture dans `charges.yaml`, à côté
de `config.yaml` :

```yaml
anzin:
  2026-01:
    electricite: 348.30
```

Un poste inscrit dans le journal **remplace** sa référence pour ce mois — utile
quand une facture d'eau s'écarte du montant habituel. Un poste sans référence,
comme l'électricité, s'ajoute simplement.

#### Décomposer l'eau

L'eau se lit comme l'électricité : une part fixe qui court même logement vide,
une part qui suit la consommation. Les factures SUEZ annuelles donnent :

| Maison | Période | Conso | Abonnement | Tarif courant |
|---|---|---|---|---|
| Valenciennes | sept. 2024 → sept. 2025 | 158 m³ | 57,50 €/an | 7,0771 €/m³ |
| Anzin | juil. 2025 → juil. 2026 | 128 m³ | 57,55 €/an | 6,8017 €/m³ |

Le montant d'un mois suit **les m³ relevés sur ce mois**, jamais un douzième de
l'année : un locataire qui part avant l'été ne doit pas porter les mois creux,
ni échapper aux mois pleins. À Valenciennes, 0,5487 m³/jour du 24/09 au 06/04
contre 0,3000 du 07/04 au 23/09 — 1,83 fois plus l'hiver, là où une moyenne
plate se tromperait de 40 % à chaque semestre :

```yaml
vals:
  2026-12: {eau_abonnement: 5.13, eau_consommation: 126.40, internet: 51.00}
  2027-07: {eau_abonnement: 5.13, eau_consommation: 69.11, internet: 51.00}
```

Les deux postes portent le préfixe `eau_` : sans lui, `abonnement` et
`consommation` désigneraient l'électricité. Ils se regroupent en une seule
colonne **Eau** sur la régularisation — le locataire lit un poste, le bailleur
en voit deux.

**Saisonnalité et tarif sont deux choses.** La saisonnalité vient des m³/jour
de chaque fenêtre de relevé ; le tarif retenu est celui de la fenêtre **la plus
récente**, appliqué à toute l'année. Les deux fenêtres d'une facture encadrent
souvent une révision : à Anzin, GESAV reprend l'assainissement au 01/01/2026 et
le renchérit de 10,9 %, si bien que garder le prix de la fenêtre d'été aurait
facturé l'été 2027 au tarif de 2025.

Les montants inscrits portent en plus une **majoration de 5 %**, prévision de
hausse pour l'année de bail. Elle ne vise que l'eau : internet est un abonnement
ferme, l'électricité se relève sur facture.

Deux pièges relevés sur les factures réelles. SUEZ **arrondit la TVA ligne à
ligne** et non sur le total par taux — l'écart atteint 2 centimes, assez pour
faire échouer un contrôle. Et l'abonnement assainissement d'Anzin disparaît au
01/01/2026, GESAV reprenant le service à la facturation au m³ : le reconduire
surestimerait la part fixe de moitié.

La référence de `config.yaml` porte la **même décomposition**, faute de quoi
l'eau serait comptée deux fois : un poste du journal ne remplace une référence
que sous une clé identique.

```yaml
  vals:
    monthly_charges:
      eau_abonnement: 5.03
      eau_consommation: 97.84
      internet: 51.00
```

Les factures se déposent dans `<maison>/Charges/<année>/`, chemin déclaré par
`charges_folder`.

```bash
quittances charges --maison vals --depuis 2026-01 --jusqu-a 2026-02
```

```
vals - 14 avenue de Condé, 59300 Valenciennes
  MOIS           eau  electricite   internet       TOTAL
  2026-01    ~100,00       588,87     ~51,00    739,87 €
  2026-02    ~100,00            -     ~51,00    151,00 €
  Total                                         890,87 €
  ~ montant de reference, non releve sur facture

  Repartition au prorata de la surface :
    Henri F.       25,98 %    231,45 €
```

Le `~` distingue un montant **présumé** d'un montant **relevé** : sans lui, une
référence non vérifiée se confondrait avec une facture réelle.

Une ligne **Bailleur** apparaît quand une part n'a pu être imputée — chambre
vacante, locataire entré en cours de période ou déjà parti (`lease_end`). C'est
la mesure du coût d'une vacance :

```
    Eliot F.        20,43 %     73,14 €
    Bailleur        vacance     78,01 €
```

C'est un **rapport, pas une régularisation** : il montre ce que coûte la maison
et ce que chacun supporterait au prorata de sa surface. Il ne compare rien aux
provisions déjà encaissées.

### Régularisation de charges

Confronte les charges réelles aux provisions versées, sur une période :

```bash
quittances regul --maison vals --depuis 2026-09 --jusqu-a 2026-09
```

```
  LOCATAIRE       PART        RÉEL  PROVISIONS       SOLDE
  Mathias V.   17,61 %     30,11 €     70,00 €    -39,89 €
  Henri F.     25,98 %     44,42 €     80,00 €    -35,58 €
  Bailleur     vacance     62,70 €
  Cout de la maison : Eau 100,00 €  Internet 51,00 €  Électricité 19,99 €
```

**Un solde négatif est un trop-perçu** : la somme est due au locataire. Le PDF
reprend la grille de la quittance, avec une colonne par poste — coût de la
maison, quote-part, part du locataire — pour que la répartition soit
vérifiable.

La ligne **Bailleur** n'apparaît que s'il reste une part réellement non
imputée. Un écart d'arrondi est absorbé par le dernier occupant : l'afficher
comme une vacance d'un centime serait un contresens.

Les provisions retenues sont celles réellement facturées sur les quittances —
celles du bail, corrigées des ajustements du mois.

Le document affiche une colonne **JOURS** à côté de la quote-part : sans elle,
une part proratisée est irréconciliable avec le coût de la maison. Le calcul se
lit de bout en bout — 100,00 € × 18,81 % × 19/30 = 11,91 €.

**Le mois de départ est dû en entier** dès lors que le préavis a été respecté,
ce qui est le cas par défaut. Un départ sans préavis se prorate au nombre de
jours, et la part non couverte remonte sur la ligne Bailleur :

```yaml
  MathiasP:
    lease_end: 2026-09-19
    preavis: false        # sans preavis : septembre est proratisé 19/30
```

#### Suppléments propres à un locataire

Une recharge de voiture électrique, un radiateur de plus : la consommation est
causée par une personne, pas par des mètres carrés. La répartir à la surface la
ferait porter par les autres.

```yaml
  MathiasP:
    charges_dediees:
      - groupe: Électricité
        montant: 20.00
        motif: Recharge du véhicule électrique
```

Le montant est **mensuel**, prélevé sur le coût du groupe **avant** répartition ;
le reste se partage aux quotes-parts inchangées. Tenir les 100 % ne demande donc
aucun calcul : ils restent 100 %, appliqués à un montant diminué.

C'est le point qui fait préférer ce mécanisme à une seconde grille de
pourcentages. Une part d'électricité relevée à 27,92 % suivrait la facture : un
hiver froid doublerait le supplément d'un véhicule qui n'aurait rien consommé de
plus. Un montant fixe ne bouge pas avec le chauffage.

Le supplément se proratise aux jours occupés — partir le 15 ne fait pas recharger
sa voiture jusqu'au 30 — et il est plafonné au coût du groupe pour le mois : on
ne peut pas imputer plus que la facture. Sur le document, il a sa propre ligne
avec son motif, sans quote-part ni jours, puisqu'il n'est pas réparti :

```
  Électricité         2 275,20 €   25,98 %   365/365     591,10 €
  Chauffage supplémentaire (un radiateur et demi)        120,00 €
  Imputé directement, non réparti entre les locataires.
```

La colonne MAISON porte alors le montant **partagé**, déduction faite : c'est lui
qui se réconcilie avec la quote-part.

#### Gestes et retenues

Tout ne se calcule pas. Un geste commercial, une retenue pour dégradations : ces
montants se portent à la main sous le locataire, dans `config.yaml`.

```yaml
  MathiasP:
    lignes_manuelles:
      - date: 2026-09-30
        libelle: Geste commercial pour le départ anticipé
        montant: 50.00
      - date: 2026-09-30
        libelle: Retenue pour remise en état du mur de la chambre
        montant: -120.00
```

**Le signe se lit en faveur du locataire** : positif, la somme lui revient ;
négatif, elle lui est retenue. C'est le sens dans lequel on raisonne en
saisissant la ligne — « je lui rends 50 », « je lui retiens 120 ».

Le `libelle` est **obligatoire**, et s'imprime en clair à côté du montant : un
montant sans explication génère une question. La `date` rattache la ligne à une
régularisation, et une seule — c'est ce qui permet d'en émettre plusieurs, une
par an et une de sortie, sans rejouer les gestes des années passées. Une ligne
datée hors de la période demandée est signalée au terminal plutôt que perdue.

Le document les reprend sous les provisions, signe et couleur compris, et le
solde en tient compte :

```
  Total des charges réelles                     20,85 €
  Provisions versées                            90,00 €
  Geste commercial pour le départ anticipé     +50,00 €
  Retenue pour remise en état du mur          -120,00 €
  Un montant positif est en votre faveur.
  Reste à payer                                  0,85 €
```

La régularisation ne porte **pas** la mention légale du pied de quittance :
celle-ci parle de « cette quittance ou ce reçu » et de termes de loyer, ce
qu'une régularisation de charges n'est pas. La place ainsi rendue accueille les
lignes manuelles. Au-delà de deux, le bloc signature passe à la page suivante —
il mesure 192 pt et déborderait sous le bord.

### Ajustements mensuels

Un bail fixe un loyer, mais la réalité mensuelle varie : un locataire parti tout
l'été ne consomme rien, un autre n'a pas encore branché sa voiture électrique.
`ajustements.yaml`, à côté de `config.yaml`, porte ces écarts :

```yaml
MathiasP:
  2026-09:
    charges: 20.00
    motif: Véhicule électrique pas encore rechargé sur place ce mois-ci.
  2026-07:
    absent: true
    motif: Retour au Portugal pour l'été.
```

| Champ | Effet |
|---|---|
| `rent` | remplace le loyer du bail pour ce mois |
| `charges` | remplace les provisions pour ce mois |
| `absent` | locataire absent : charges à zéro, sauf valeur explicite |
| `motif` | la raison, reprise dans l'email au locataire |

Les montants sont **ceux à facturer**, pas des remises : `charges: 70.00`
produit une quittance à 70 € de charges, quel que soit le montant du bail.

**Le loyer reste dû en cas d'absence** : la chambre demeure réservée. Seules les
charges tombent.

Modifier le journal **ne réécrit aucun PDF déjà produit**. La commande le
signale quand le journal est plus récent que la quittance existante :

```
  PDF deja present (utilisez --forcer pour regenerer)
  ATTENTION : le journal a ete modifie apres ce PDF, qui peut porter
  d'anciens montants. Relancez avec --forcer.
```

Les montants suivent cet ordre de priorité : `--loyer`/`--charges` en ligne de
commande, puis l'ajustement du mois, puis le bail. Le suivi somme les montants
réels, si bien qu'un été sans charges ne compte pas comme un mois plein.

Consulter le journal :

```bash
quittances ajustements
```

```
2026-09  Mathias P.  charges 20,00 €  (360,00 € au total)
          Véhicule électrique pas encore rechargé sur place ce mois-ci.
```

Le journal est versionné : `git blame` dira dans un an pourquoi ce mois-là
était à 20 €.

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

Le message est **bilingue** (français puis anglais) et mis en forme : montant dû
en évidence, échéance du bail et suggestion de virement programmé en encarts. La
version texte accompagne toujours la version HTML, pour les clients qui ne
l'affichent pas.

Produire le reçu de dépôt de garantie, deux mois de loyer hors charges :

```bash
quittances caution --locataire Madina --recu-le 28/08/2026
```

Le montant se déduit du loyer configuré, `--montant` le remplace. Le PDF reprend
la mise en page de la quittance, écrit la somme en toutes lettres comme l'exige
un reçu, et va dans **`Docs`**. Il reste **en français uniquement** : c'est une
pièce qui peut être produite en justice.

Voir qui a déjà un reçu :

```bash
quittances caution --suivi
```

```
LOCATAIRE    MAISON   REÇU   ATTENDU   FICHIER
Alice R.     anzin      ✓     640,00 €   Reçu dépôt de garantie - Alice ROLLAND.pdf
Madina T.    vals       ·     680,00 €   -

9 reçus, 1 manquant
```

La détection ignore accents et casse, et retrouve donc les reçus déjà produits à
la main sous d'autres conventions de nommage. Les reçus de **restitution** sont
écartés : ils soldent le dépôt à la sortie, c'est l'inverse.

Voir qui a déposé son attestation d'assurance :

```bash
quittances assurance
```

```
LOCATAIRE    MAISON   REÇUE  FICHIER
Alice R.     anzin      ·    -
Baptiste D.  anzin      ✓    assurance_2026-27.pdf  (03/09/2026)
Mathias P.   vals       ✓    assurance_2026-27.jpeg  (05/09/2026)

5 reçues, 5 manquantes (--relancer pour les rappeler)
```

Le critère est le nom du fichier : **tout fichier de `Docs` contenant
« assurance »** compte, quelle que soit son extension — les locataires envoient
aussi bien un PDF qu'une photo. Aucune échéance n'est suivie, seulement la
présence du document.

Relancer ceux qui n'ont rien déposé :

```bash
quittances assurance --relancer
```

Le message demande l'attestation de risques locatifs, rappelle que le bail
l'impose chaque année, et suggère de la demander à son assureur. Il est
**bilingue et mis en forme**, et ne joint aucun document — il en réclame un.
Comme ailleurs, rien ne part sans `--envoyer`.

Lister les locataires configurés :

```bash
quittances locataires
```

Une attestation de domicile, à remettre à un tiers (transporteur, banque,
préfecture) :

```bash
quittances domicile --locataire Elsa --motif "une demande de carte de transport auprès du réseau Transvilles"
```

Le PDF est signé et rangé dans **`Docs`**, pas dans `Quittances` : c'est un
justificatif ponctuel, pas une pièce comptable mensuelle. Il est daté du jour et
son nom porte la date complète, plusieurs attestations pouvant être délivrées la
même année pour des motifs différents. Ce document et son email restent
**en français uniquement** — ils s'adressent à une administration française.

La date d'entrée dans les lieux vient de `lease_start` dans `config.yaml`, ou de
`--depuis`. Sans `--motif`, la clause d'usage s'arrête à « pour servir et valoir
ce que de droit ».

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
| `--depuis DATE` | début d'hébergement, d'occupation, ou mois de départ d'un suivi |
| `--jusqu-a AAAA-MM` | borne un suivi, défaut : douze mois |
| `--manquants` | `suivi` : n'affiche que les retards |
| `--motif TEXTE` | usage prévu de l'attestation de domicile |
| `--recu-le DATE` | `caution` : date du versement, défaut : `lease_start` |
| `--montant MONTANT` | `caution` : remplace les deux mois de loyer |
| `--suivi` | `caution` : affiche l'état des lieux sans rien produire |
| `--relancer` | `assurance` : rappelle ceux qui n'ont rien déposé |
| `--dossier CHEMIN` | racine de sortie, défaut : dossier du bien |
| `--forcer` | régénère un PDF déjà présent |
| `--envoyer` | envoie l'email (sinon, génération seule) |
| `--config CHEMIN` | autre `config.yaml` |
| `--ajustements CHEMIN` | autre `ajustements.yaml` |
| `--charges-releve CHEMIN` | autre `charges.yaml` |

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
| `quittances/ajustements.py` | journal des écarts mensuels au bail |
| `quittances/charges.py` | charges d'une maison et leur répartition |
| `quittances/factures.py` | lecture des factures d'électricité |
| `quittances/documents.py` | modèles métier, calculs, chemins de sortie |
| `quittances/pdf.py` | rendu PDF (ReportLab) |
| `quittances/emails.py` | mise en forme HTML des emails |
| `quittances/mailer.py` | construction et envoi SMTP |
| `quittances/cli.py` | interface en ligne de commande |
| `quittances/formatting.py` | dates, mois et montants en français |

Les modèles ne connaissent ni le PDF ni l'email, ce qui permet de tester les
calculs et les libellés sans rien générer.

## Historique

Version 2.2 : trois documents et deux suivis s'ajoutent — attestation de
domicile, reçu de dépôt de garantie, suivi des attestations d'assurance avec
relance. Les emails de quittance et de relance deviennent des cartes mises en
forme, et bilingues français/anglais ; les documents destinés à une
administration française ou opposables en justice restent monolingues.

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
