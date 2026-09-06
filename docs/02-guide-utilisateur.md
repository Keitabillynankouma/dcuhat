# Guide de l'agent — Plateforme DCUHAT

Direction Communale de l'Urbanisme, de l'Habitat et de l'Aménagement du Territoire de Lambayin

Ce guide s'adresse aux agents de la Direction. Il ne suppose aucune connaissance technique.

---

## 1. Se connecter

Ouvrez l'adresse de la plateforme dans votre navigateur, saisissez votre adresse e-mail
professionnelle et votre mot de passe.

À la première connexion, la plateforme vous demande de changer le mot de passe fourni par
l'administrateur. Choisissez-en un d'au moins douze caractères, que vous n'utilisez nulle
part ailleurs.

**Ce mot de passe protège aussi les documents enregistrés sur votre appareil pour le
travail hors ligne.** Si vous le perdez, l'administrateur peut vous en donner un nouveau,
mais les documents déjà enregistrés hors ligne sur cet appareil devront être retéléchargés.

### Installer l'application sur votre appareil

Sur un ordinateur, votre navigateur affiche une icône d'installation dans la barre
d'adresse. Sur un téléphone ou une tablette : menu du navigateur → « Ajouter à l'écran
d'accueil ». L'application s'ouvre alors comme une application ordinaire et fonctionne
même sans réseau.

---

## 2. Se repérer

L'écran d'accueil présente **les espaces des services** : Urbanisme, Habitat, Aménagement,
Cadastre, Affaires domaniales, Archives. Vous ne voyez que ceux auxquels vous avez accès.

Le menu de gauche donne accès à :

| Entrée | À quoi elle sert |
|---|---|
| **Dossiers** | l'arborescence des documents |
| **Carte** | les documents géoréférencés, situés sur la commune |
| **Recherche** | retrouver un document par mot-clé, type, date ou numéro de parcelle |
| **Corbeille** | récupérer un élément supprimé par erreur |
| **Conflits** | arbitrer les modifications concurrentes après une sortie terrain |
| **Journal** | l'historique des actions |

En haut à droite, une pastille indique **En ligne** ou **Hors ligne**, et le bouton
**Synchroniser** affiche le nombre de modifications en attente d'envoi.

---

## 3. Déposer et organiser des documents

**Déposer un fichier** : ouvrez le dossier de destination, puis glissez-y le fichier, ou
utilisez le bouton *Téléverser*. Vous pouvez déposer plusieurs fichiers à la fois.

Un fichier volumineux (un levé, une orthophoto) est envoyé par morceaux. Si la connexion
coupe en cours d'envoi, seul le morceau interrompu est renvoyé — l'envoi ne recommence
jamais depuis le début.

**Créer un dossier** : bouton *Nouveau dossier*. L'arborescence n'a pas de limite de
profondeur, mais restez simple : deux à quatre niveaux suffisent presque toujours.

**Renommer, déplacer, supprimer** : les actions sont disponibles sur chaque ligne. Une
suppression envoie l'élément à la corbeille, d'où il reste récupérable.

### Remplir les champs du dossier

Sur la fiche d'un document, la section *Champs du dossier* propose les rubriques de la
Direction : référence, numéro de parcelle, section cadastrale, quartier, demandeur, dates,
type d'acte, statut de l'instruction.

Prenez le temps de les remplir : c'est ce qui permettra, dans six mois, de retrouver
« tous les dossiers du quartier Centre déposés en 2026 » en une seule recherche, sans
ouvrir un seul document.

---

## 4. Les versions : rien n'est jamais écrasé

Quand vous redéposez un fichier portant le même nom, l'ancien n'est **pas** remplacé : une
nouvelle version est créée et l'ancienne reste consultable.

Sur la fiche du document, l'onglet *Historique des versions* montre qui a modifié quoi et
quand. Un chef de service peut rétablir une version antérieure : cela crée une nouvelle
version identique à l'ancienne, sans rien effacer.

Indiquez le motif de la modification lors du dépôt (« correction d'altimétrie », « plan
validé en commission ») : c'est ce qui rend l'historique lisible pour vos collègues.

---

## 5. Les documents géoréférencés

Les formats reconnus : Shapefile (`.shp`, ou l'ensemble compressé en `.zip`), GeoJSON,
GeoTIFF, KML/KMZ, GPX, DXF, DWG, GeoPackage.

Après le dépôt, la plateforme lit automatiquement le système de projection, l'emprise, le
nombre d'entités et la table attributaire. Le document apparaît alors sur la **Carte**.

> **Un Shapefile n'est jamais un seul fichier.** Il en compte de trois à huit (`.shp`,
> `.dbf`, `.shx`, `.prj`…). Déposez-les ensemble, ou compressez-les dans un `.zip` : un
> `.shp` seul est inutilisable.

**Si la plateforme signale « projection introuvable »**, c'est que le fichier ne contient
pas cette information (souvent parce que le `.prj` manque). Cliquez sur *Déclarer la
projection* et indiquez le code : `4326` pour des données GPS, `32628` ou `32629` pour un
levé UTM local. Demandez au service du Cadastre en cas de doute.

La plateforme ne devine jamais : une emprise fausse sur la carte communale ferait plus de
dégâts qu'une emprise absente.

**Convertir un format** : sur la fiche du document, choisissez le format de sortie. La
conversion produit un nouveau fichier déposé à côté de l'original, qui reste intact.

---

## 6. Travailler sur le terrain, sans réseau

### Avant de partir

Ouvrez les documents dont vous aurez besoin et cliquez sur **Rendre disponible hors ligne**.
Ils sont enregistrés chiffrés sur votre appareil : sans votre mot de passe, ils restent
illisibles, y compris pour qui trouverait la tablette.

Ouvrez également la **Carte** sur la zone de votre sortie : le fond de plan est mis en
cache et restera lisible sans réseau.

### Sur le terrain

Travaillez normalement. Vous pouvez consulter les documents enregistrés, créer des
dossiers, déposer des photos et des levés, remplir les champs du dossier. La pastille
indique *Hors ligne* et vos actions s'accumulent dans une file d'attente.

Ce que vous ne pouvez pas faire hors ligne : consulter un document que vous n'avez pas
enregistré avant de partir, télécharger une archive, ou modifier des droits.

### Au retour

Dès que le réseau revient, la synchronisation démarre seule. Vos modifications partent
d'abord, puis les changements des collègues arrivent.

Si un document a été modifié à la fois au bureau et par vous sur le terrain, la plateforme
**conserve les deux versions** et vous en informe. Rendez-vous dans **Conflits** pour
choisir : votre version de terrain, celle du bureau, ou les deux. Rien n'est perdu tant
que vous n'avez pas tranché.

---

## 7. Rechercher

La recherche porte simultanément sur le nom, la description, les étiquettes, les champs du
dossier et **le contenu** des documents bureautiques (PDF, Word, texte).

Quelques exemples utiles :

| Ce que vous cherchez | Comment |
|---|---|
| Tous les permis d'un quartier | mots-clés `permis` + champ *Quartier* = `Centre` |
| Une parcelle précise | champ *Numéro de parcelle* = `LB-2026-014` |
| Les levés de l'année | type = *Données vectorielles* + dates |
| Tout ce qui concerne un secteur | onglet **Carte**, déplacez-vous sur la zone |

---

## 8. Partager

**Avec un collègue ou un service** : sur un dossier ou un fichier, ajoutez une permission
et choisissez le niveau — *Consultation*, *Commentaire*, *Modification*, *Gestion*. Une
permission posée sur un dossier s'applique à tout son contenu.

**Avec une personne extérieure** (un demandeur, un bureau d'études) : créez un **lien de
partage**. Vous pouvez le protéger par un mot de passe, lui donner une date d'expiration
et limiter le nombre de téléchargements. Un lien reste révocable à tout moment.

Chaque accès par lien est enregistré dans le journal.

---

## 9. Bonnes pratiques

- **Nommez lisiblement.** `PC-2026-014-Diallo-plan-masse.pdf` vaut mieux que `scan001.pdf`.
- **Un dossier par affaire**, pas un dossier par mois : on cherche par affaire, pas par date de classement.
- **Remplissez les champs du dossier** au moment du dépôt, pas « plus tard ».
- **Préparez vos sorties terrain** la veille, tant que vous avez du réseau.
- **Ne partagez pas votre compte.** Le journal attribue chaque action à un agent nommé ; un compte partagé rend cette traçabilité inutile.
- **Signalez un conflit que vous ne savez pas arbitrer** à votre chef de service plutôt que de choisir au hasard.

---

## 10. En cas de problème

| Situation | Que faire |
|---|---|
| « Compte temporairement verrouillé » | Cinq échecs de connexion ; attendez quelques minutes ou contactez l'administrateur. |
| « Le quota du service est atteint » | Purgez la corbeille de votre service, ou demandez une extension à l'administrateur. |
| Un document a disparu | Regardez d'abord dans la **Corbeille** : une suppression y reste récupérable. |
| Le document n'apparaît pas sur la carte | Sa projection est probablement indéterminée : ouvrez sa fiche et déclarez-la. |
| La synchronisation ne part pas | Vérifiez la pastille réseau ; le bouton *Synchroniser* force une tentative. |
| Un fichier est « verrouillé » | Un collègue le modifie ; il apparaît sur la fiche du document. |
