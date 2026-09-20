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
python -m pytest                    # 284 tests
python -m pytest tests/test_pdf.py::test_quittance_produit_un_pdf_a4   # un seul test
quittances locataires               # verifie que config.yaml se charge
```

Il n'y a ni linter ni formateur configurés.

## Architecture

Quatre couches, du bas vers le haut :

| Couche | Modules | Dépendances |
|---|---|---|
| Données | `config.py`, `ajustements.py`, `charges.py`, `factures.py`, `formatting.py` | aucune |
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

## Factures d'electricite

`factures.py` lit les PDF TotalEnergies. L'**abonnement est facture d'avance**
(29/08 - 28/09), la **consommation a terme echu** (29/07 - 28/08) : les periodes
sont decalees d'un mois, et un mois calendaire depend de deux factures. Chaque
poste porte donc sa propre periode et se proratise dessus.

L'extraction est **confrontee aux totaux imprimes** : si les postes ne
reconstituent pas le TTC a 2 centimes pres, `lire_facture` echoue. Un poste
manque fausserait une repartition sans que rien ne le signale.

Les postes sont classes `FIXE` (abonnement, CTA — dus meme absent) ou `VARIABLE`
(consommation, accise). La CTA est rattachee a l'abonnement et l'accise a la
consommation, bien qu'elles figurent sous un meme total sur la facture.

`mois_complets` refuse d'inscrire un mois que les factures ne couvrent pas de
bout en bout pour les deux categories.

Une periode se lit sur **toute sa section** (`_periode_de_section`), pas sur sa
premiere ligne. Les factures d'avant mars 2026 detaillent la consommation en
tranches quand un tarif change en cours de mois — « du 29/01 au 31/01 » puis
« du 01/02 au 28/02 » — et ne retenir que la premiere amputait le mois, faisant
passer des mois complets pour incomplets. Les intitules de `SECTIONS` servent
de butoir : une periode lue au-dela appartient deja au poste suivant.

La section des taxes s'intitule « Taxes locales et contributions » avant mars
2026 et « Contributions et taxes » depuis ; `_trouver_un` accepte les deux. Sept
factures de 2025 echouaient sur ce seul libelle.

## Regularisation de charges

`charges.regularisations` confronte le reel aux provisions, mois par mois. Le
**solde negatif est un trop-percu** du au locataire : c'est le sens des
regularisations deja etablies a la main, ne pas l'inverser.

Les provisions retenues sont celles **reellement facturees** sur les quittances
(bail corrige des ajustements), et non le montant du bail : sans cela un mois
d'ete a charges reduites creerait une dette fictive.

Les postes sont regroupes par `charges.groupe` : « eau » et « internet » gardent
leur nom, tout le reste — abonnement, consommation, CTA, accise — devient
« Electricite ». Le locataire lit une colonne, pas six lignes de facture.

`Tenant.fin_due` etend `lease_end` a la fin de son mois quand `preavis` vaut
vrai — le cas par defaut : un preavis respecte rend le mois de depart
entierement du. Un depart sans preavis se prorate, et la part non couverte
remonte sur la ligne Bailleur.

Le document porte une colonne **JOURS** (`jours_dus` / `jours_periode`). Sans
elle, une part proratisee est irreconciliable avec le cout de la maison : le
locataire voit 11,91 € la ou sa quote-part de 18,81 % sur 100 € donnerait
18,81 €. Le facteur manquant doit etre imprime.

`Tenant.lignes_manuelles` porte ce qui ne se calcule pas : geste commercial,
retenue pour degradations. **Le signe se lit en faveur du locataire** — positif,
la somme lui revient — alors que `solde` compte ce qu'il doit. Le retournement
a lieu dans `Regularisation.total_lignes` et **nulle part ailleurs** : le
dupliquer dans le PDF ou l'email les ferait diverger, et une inversion passee
inapercue transformerait un cadeau en dette.

Le `libelle` est obligatoire et le montant nul refuse : `LigneManuelle` echoue
au chargement plutot que d'imprimer une somme sans explication. La `date`
rattache la ligne a **une** regularisation (`lignes_manuelles_entre`), sinon un
geste de 2026 reviendrait sur celle de 2027 ; `cmd_regul` signale celles qui
tombent hors periode. Les montants s'affichent toujours signes
(`format_amount_signe`) : « Degradations 120,00 € » ne dirait pas si la somme
est retenue ou rendue.

La regularisation ne porte **pas** `MENTION_LEGALE`. Ce texte parle de « cette
quittance ou ce recu » et de termes de loyer : il ne s'applique pas a une
regularisation de charges, et le pied de page revient au document. Seule la
quittance le porte desormais.

Elle est le **seul document dont la hauteur varie**. Son bloc de cloture mesure
`HAUTEUR_CLOTURE` (192 pt) et s'ecrivait par-dessus la mention legale des la
version a trois postes ; il bascule desormais en page suivante quand il
depasserait `BAS_UTILE`. Les libelles manuels sont replies par `_wrap` plutot
que tronques.

`Tenant.charges_dediees` impute a une seule personne ce qu'elle cause seule :
la recharge d'un vehicule electrique, un radiateur de plus. **Le montant est
preleve sur le cout du groupe avant repartition**, et le reste se partage aux
quotes-parts inchangees. C'est ce qui dispense d'une seconde grille de
pourcentages : tenir les 100 % ne demande aucun calcul, puisque 100 % restent
100 % d'un montant diminue.

Une seconde grille aurait **suivi la facture** : a 27,92 % d'electricite, un
hiver froid aurait double le supplement d'un vehicule qui n'aurait rien
consomme de plus. Le montant fixe ne bouge pas avec le chauffage.

Le montant declare est **mensuel** et se prorate aux jours occupes. Il est
**plafonne au cout du groupe pour le mois** : imputer 30 € de supplements sur
un mois ou le journal ne porte que l'abonnement (23,99 €) rendrait la part
partagee negative. Le plafond se voit — les supplements sont rabattus au
prorata — et disparait des que la consommation du mois est relevee.

`totaux_maison` porte le montant **partage**, deduction faite. Sans cela, la
ligne « Electricite » du document ne vaudrait plus maison x quote-part x jours,
et le locataire ne pourrait plus la verifier. Les supplements ont leurs propres
lignes, avec leur motif : ni quote-part ni jours a afficher, puisqu'ils ne sont
pas repartis.

`repartition` distingue **arrondi et vacance** : quand les quotes-parts occupees
couvrent la periode a 99,95 % ou plus, l'ecart residuel est un arrondi et le
dernier occupant l'absorbe. Afficher un centime en ligne « Bailleur » ferait
croire a une chambre vide.

## Charges d'une maison

Deux natures de charges, deux emplacements : les **fixes** dans `config.yaml`
(`Property.monthly_charges` — eau, internet), les **variables** relevees facture
par facture dans `charges.yaml` (electricite). Un poste du journal **remplace**
sa reference pour ce mois ; un poste sans reference s'ajoute.

L'eau de Valenciennes est **decomposee comme l'electricite**, en part fixe
(`eau_abonnement`, l'abonnement SUEZ, du meme logement vide) et part variable
(`eau_consommation`). Les deux portent le prefixe `eau_` parce que
`abonnement` et `consommation` sans prefixe designent deja l'electricite, et
`charges.GROUPES` les ramene tous deux a « Eau » : le locataire lit une
colonne, le bailleur en voit deux.

La reference de `config.yaml` porte la **meme decomposition** que le journal.
C'est une contrainte, pas un choix : `du_mois` ne remplace une reference que par
une cle identique. Laisser `eau: 100` en reference avec `eau_abonnement` au
journal ferait compter l'eau **deux fois**.

Les deux maisons sont decomposees, chacune depuis sa facture SUEZ annuelle.
Le montant d'un mois suit **les m3 releves sur ce mois**, jamais un douzieme de
l'annee : un locataire qui part avant l'ete ne doit pas porter les mois creux,
ni echapper aux mois pleins. A Valenciennes, 0,5487 m3/jour du 24/09 au 06/04
contre 0,3000 du 07/04 au 23/09 — 1,83 fois plus l'hiver. Une moyenne plate se
tromperait de 40 % a chaque semestre.

**Saisonnalite et tarif sont deux grandeurs distinctes**, et les melanger fut
l'erreur du premier jet. La saisonnalite vient des m3/jour de chaque fenetre de
relevi ; le tarif retenu est celui de la fenetre **la plus recente**, applique a
toute l'annee. Les deux fenetres d'une facture encadrent souvent une revision :
a Anzin, GESAV reprend l'assainissement au 01/01/2026 et le rencherit de 10,9 %,
si bien que garder le prix de la fenetre d'ete aurait facture l'ete 2027 au
tarif de 2025 — 33,76 € de moins sur l'annee.

**SUEZ arrondit la TVA ligne a ligne**, pas sur le total par taux. Sommer les HT
par taux avant d'appliquer la TVA donne 2 centimes d'ecart sur Anzin — assez
pour faire echouer un controle contre les totaux imprimes.

L'abonnement assainissement SUEZ d'Anzin (28,31 € TTC au 2e semestre 2025) est
**exclu du forfait** : GESAV reprend le service au 01/01/2026 et facture au m3
sans part fixe. Le reconduire surestimerait la part fixe de moitie.

Les montants inscrits portent une **majoration de 5 %**, prevision de hausse
pour 2026-2027 decidee par le bailleur. Elle ne s'applique qu'a l'eau : internet
est un abonnement ferme et l'electricite se releve sur facture.

L'eau et l'internet sont portes au journal sur toute l'annee de bail pour etre
ajustables mois par mois. Consequence
assumee : un poste present dans le journal est tenu pour **releve** et perd son
`~`. Retirer la ligne le rend a la reference, et au marqueur.

Le rapport marque d'un `~` les montants **presumes**. Confondre une reference
non verifiee avec une facture reelle fausserait une regularisation sans que rien
ne le signale.

`repartition` renvoie `(parts, reliquat)`. Le **reliquat** est ce qui n'a pu
etre impute — chambre vacante, locataire entre en cours de periode ou parti
(`lease_end`) — et s'affiche sur une ligne **Bailleur** : c'est la mesure du
cout d'une vacance, et elle doit se voir.

Sans periode, l'ecart d'arrondi est absorbe par le dernier occupant, pour que
la somme des parts fasse **exactement** le total : un centime perdu par ligne
finirait par se voir sur un exercice. Un test le verifie sur plusieurs totaux.

`quittances charges` est un **rapport, pas une regularisation** : il ne compare
rien aux provisions encaissees et n'applique aucun prorata temporis. Ces regles
ne sont pas encore arretees.

`Property.monthly_charges` etant un dictionnaire, `Property` et `Tenant` ne sont
plus hachables : indexer par `tenant.key`, pas par l'objet.

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
