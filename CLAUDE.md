# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Ce que fait le projet

Produit les documents locatifs en PDF pour les locataires de trois biens
(colocations d'Anzin et Valenciennes, appartement de Lille) et les envoie par
email : quittances de loyer, attestations de domicile et d'hebergement, recus de
depot de garantie. Suit aussi les loyers encaisses, les attestations d'assurance
et les depots recus, et relance ce qui manque. Usage personnel du bailleur, en
local, sur Windows.

## Commandes

```bash
python -m pip install -e ".[dev]"   # installe le paquet et les outils de test
python -m pytest                    # 242 tests
python -m pytest tests/test_pdf.py::test_quittance_produit_un_pdf_a4   # un seul test
quittances locataires               # verifie que config.yaml se charge
```

Il n'y a ni linter ni formateur configurés.

## Architecture

Quatre couches, du bas vers le haut :

| Couche | Modules | Dépendances |
|---|---|---|
| Données | `config.py`, `ajustements.py`, `formatting.py` | aucune |
| Métier | `documents.py` | config, formatting |
| Effets | `pdf.py`, `emails.py`, `mailer.py` | config, documents |
| Orchestration | `cli.py` | tout |

**`documents.py` ne connaît ni le PDF ni l'email.** `Quittance` et
`Attestation` portent les calculs, les libellés et les chemins de sortie ; c'est
ce qui permet de tester montants, noms de fichiers et corps de mail sans rien
générer. Ne pas y introduire d'appel à ReportLab ou smtplib.

**`config.yaml` est l'unique source des données métier** (bailleur, biens,
locataires). Aucune donnée nominative ne doit revenir dans les sources — c'était
le défaut de l'ancien `helper.js`, remplacé lors du portage Node → Python.

## Invariants à ne pas casser

`--locataire`, `--maison` et `--tous` sont trois sélecteurs **mutuellement
exclusifs**, et `select_tenants` refuse toute combinaison. `--maison` ne
paramètre pas le document : l'adresse et le dossier de sortie viennent toujours
de la fiche du locataire. Avant ce garde-fou, `--locataire X --maison Y`
ignorait X en silence et générait pour toute la maison Y.

`quittance` est la sous-commande par défaut, injectée par
`inject_default_command` avant argparse. Elle doit sauter les options globales
(`--config` et sa valeur, `--config=x`) sans prendre la valeur d'une option de
sous-commande pour un nom de commande — c'est le piège que couvre
`TestCommandeParDefaut`.


**L'email ne part jamais sans `--envoyer`.** L'ancienne version envoyait à chaque
exécution, y compris quand le PDF n'avait pas été régénéré. Un envoi groupé
(`--tous --envoyer`) demande confirmation interactive.
`tests/test_cli.py::test_aucun_email_sans_option_envoyer` garde ce comportement.

**Les montants sont des `Decimal`, jamais des flottants.** L'ancien JS calculait
`320.00 + 80.00` puis `.toString()` et affichait `400 €` à côté de `320.00 €`.
`format_amount` produit la typographie française avec espaces insécables
(U+00A0) : les tests comparent avec la constante `NBSP`, ecrite sous forme
d'echappement `"\u00a0"` pour qu'aucun espace ordinaire ne s'y glisse.

**L'élision est obligatoire devant avril, août et octobre.** `formatting.elision`
renvoie « de » ou « d'» et s'applique aux corps d'email comme au PDF : sans elle,
les documents d'août affichaient « le mois de août ». Elle rend la préposition
seule, pour qu'on puisse intercaler du balisage (« le mois d'<b>août 2026</b> »).

**Les mois français sont codés en dur** dans `formatting.MOIS`.
`locale.setlocale(LC_TIME, "fr_FR")` n'est pas fiable sous Windows.

**Rien n'est deviné à partir d'un prénom.** `title` est facultatif ; absent, la
civilité est omise du document (« Reçu de : MORÓN Elsa ») et l'attestation écrit
« né(e) ». Ne pas ajouter d'inférence de genre.

**Les noms composés restent entiers.** `last_name` peut contenir des espaces
(« Aranibar Campero », « Dos Santos »). L'ancien `fullName.split(" ")[1]`
tronquait ces noms — ne pas réintroduire de découpage sur l'espace.

## Quotes-parts de surface

`Tenant.share` est un pourcentage de la surface de **sa maison**, pas du parc :
Anzin et Valenciennes totalisent 100 % chacune. Les charges d'un immeuble se
repartissent entre ses occupants.

`_verifier_quotes_parts` refuse une maison **partiellement** renseignee, et une
somme qui s'ecarte de 100 % de plus que `TOLERANCE_QUOTE_PART` (0,05 point, pour
absorber l'arrondi de surfaces reelles). Une maison sans aucune quote-part reste
valide : la repartition n'y est pas encore en place.

`Tenant.room` (« R+2 », « RDC jardin ») situe la chambre, sans autre effet que
l'affichage pour l'instant.

## Ajustements mensuels

`ajustements.yaml` porte les ecarts au bail, mois par mois. Il est
**centralise et versionne**, et non disperse dans les dossiers des locataires :
un ajustement est une decision, pas un document, et `git blame` doit pouvoir
repondre a « pourquoi 20 € en septembre ? ».

Il se resout **a cote du `config.yaml` retenu** (`base_dir=config.source.parent`),
jamais depuis le repertoire courant. Sans cela `--config autre.yaml` melangerait
les journaux, et les tests liraient celui du depot — meme piege que le `.env` de
`test_mailer`.

Ordre de priorite des montants, applique par `resolve_amounts` : ligne de
commande, puis ajustement du mois, puis bail. `terme_du_mois` applique le meme
ordre pour que le suivi somme les montants reels.

`absent: true` met les **charges a zero**, jamais le loyer : la chambre reste
reservee. Une valeur `charges` explicite l'emporte, une absence pouvant laisser
un abonnement a la charge du locataire.

Les montants du journal sont **ceux a facturer**, jamais des remises a
soustraire : `charges: 70.00` produit 70 € de charges.

Editer le journal **ne reecrit aucun PDF**. `_journal_plus_recent` compare la
date du fichier a celle de la quittance existante et avertit, faute de quoi on
relance la commande, on lit « PDF deja present » et on envoie l'ancien montant.
L'avertissement se limite aux mois effectivement ajustes.

Un locataire inconnu ou un champ mal orthographie fait **echouer le
chargement**. Ignorer silencieusement « charge » au lieu de « charges »
facturerait le mois au tarif du bail sans que rien ne le signale.

Le `motif` remonte jusqu'a l'email du locataire (`Quittance.note`) : un montant
inhabituel sans explication genere une question.

## Suivi des paiements

`quittances suivi` n'a **aucune source de paiement** : il teste l'existence du
PDF attendu (`documents.quittance_path`) pour chaque locataire et chaque mois.
Le raccourci « quittance présente = loyer encaissé » tient parce que le bailleur
n'émet une quittance qu'une fois payé — le libellé de la commande le dit, ne pas
le présenter comme un relevé bancaire. Les relevés de `src/data_2025.py`
s'arrêtent fin 2025 et ne sont pas branchés.

Les corps HTML des quittances et des relances sont assembles par `emails.py`,
module de presentation sans donnee metier. `emails.montant` prend un `ton` :
« succes » (vert) pour une quittance qui confirme, « attention » (rouge) pour
une relance qui alerte. Les contraintes du format y dictent le code : **styles en
ligne** (les clients suppriment `<style>`), **tableaux** et non flex ou grid
(Outlook), aucune police ni image distante, largeur bornee a 560 px. La version
texte reste la retombee et doit rester lisible seule.

Quittances et relances sont **bilingues** : la moitie des locataires ne lisent
pas le francais. Les dates anglaises passent par `format_date_en`, qui ecrit le
mois en toutes lettres — « 03/09/2026 » se lirait « 9 mars » outre-Atlantique. Les libelles anglais ont leurs propres conventions
(`month_year_en`, `format_amount_en` qui ecrit « €450.50 » et non
« 450,50 € »). Les emojis du corps imposent `cli.printable` a l'affichage,
sinon l'apercu plante en cp1252 comme le faisaient les coches du suivi.

`suivi` et `relance` partagent `etats_locataire` : les deux doivent s'accorder
sur ce qui constitue un retard, sinon on relancerait un mois non echu. Ne pas
dupliquer cette logique.

Le suivi couvre **douze mois depuis `--depuis`** (l'annee de bail), pas
seulement les mois ecoules. Les mois posterieurs au mois courant sont donc
affiches vides et comptes dans « A venir », jamais dans « En retard » : sans
cette distinction, septembre afficherait onze mois d'impayes fictifs.

Les marqueurs `✓`/`·` passent par `cli.markers()`, qui retombe sur `X`/`.`
quand `sys.stdout` ne sait pas les encoder : une redirection Windows repasse en
cp1252 et ferait planter la commande.

## Depot de garantie

`DepotGarantie.montant_attendu` vaut **deux mois de loyer hors charges** : les
provisions ne sont pas couvertes par le depot, elles se regularisent a part.

Le recu ecrit la somme en toutes lettres (`formatting.montant_en_lettres`), ce
qu'attend un recu : « six cent quatre-vingts euros (680,00 € ) ». L'orthographe
des nombres suit la regle francaise — « quatre-vingts » et « deux cents »
prennent un s en fin de nombre seulement, « mille » est invariable.

Son PDF reprend la **grille editoriale de la quittance**, pas la lettre de
l'attestation de domicile : le locataire recoit les deux a quelques jours
d'intervalle. Il reste **en francais uniquement**, et sort dans `Docs`.

`fichiers_docs` normalise les accents avant de comparer : les recus produits a
la main s'ecrivent tantot `Recu_depot_de_garantie_X.pdf`, tantot
`Reçu dépôt de garantie - X.pdf`. Les **restitutions** sont exclues — elles
soldent le depot a la sortie, c'est l'operation inverse.

## Suivi des assurances

`quittances assurance` ne suit **aucune echeance** : il liste les fichiers de
`Docs` dont le nom contient « assurance » (`documents.fichiers_assurance`),
sans regarder leur contenu ni leur date de validite. Le critere est volontairement
large — les locataires deposent aussi bien un PDF qu'une photo `.jpeg`.

`--relancer` cible exactement ceux qui n'ont aucun fichier. Le message
`RelanceAssurance` est bilingue et **ne joint rien** : il reclame un document,
il n'en transmet pas.

`Property.dwelling` s'ecrit **sans** elision apres « pour » (« pour une
chambre ») et **avec** apres « locataire » (« locataire d'une chambre »). Le
bloc anglais dit « the property », neutre, la ou « the room » serait faux pour
Lille.

## Attestation de domicile

`AttestationDomicile` n'est pas `Attestation` : la premiere certifie qu'un
**locataire** occupe un logement contre loyer, la seconde qu'une personne est
**hebergee a titre gratuit** chez le bailleur. Ne pas les fusionner.

Elle sort dans `Docs` et non `Quittances`, reste **en francais uniquement** (le
destinataire final est une administration francaise), et son nom de fichier
porte la date complete : un locataire peut en demander plusieurs dans l'annee
pour des motifs differents.

Son PDF suit une **mise en page de lettre** — bloc bailleur, lieu et date a
droite, titre centre, corps ferre a gauche, signature — et non la grille
editoriale des quittances : le lecteur est un tiers qui attend une forme
conventionnelle. Le fer a gauche (`CORPS_GAUCHE`) est volontaire : justifie, le
corps se lezardait des qu'une adresse se coupait en fin de ligne.

`Property.dwelling` prend `elision` **apres « locataire »** (« locataire d'une
chambre ») mais pas apres « pour » — la regle complete est dans la section
Suivi des assurances.

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

## Pièges

Le dossier de destination d'un locataire est déduit de `first_name`/`last_name`
(`Tenant.slug`), accents compris : un dossier `Elsa_Moron` sur le disque et un
`Morón` en configuration produisent deux dossiers distincts. Renommer le dossier
plutôt que de retirer l'accent du nom, qui s'imprime sur les documents.


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
