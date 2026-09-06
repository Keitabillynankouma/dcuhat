# Déployer DCUHAT gratuitement

Ce document décrit une mise en ligne à coût nul, valable pour une **démonstration
à la Direction** ou une recette. Sa dernière section explique pourquoi ce n'est
pas une solution de production, et ce que coûterait la vraie.

---

## 1. Ce qu'il faut héberger, et où

La plateforme a quatre besoins, dont trois ont une offre gratuite crédible.

| Besoin | Service retenu | Offre gratuite | Pourquoi celui-là |
|---|---|---|---|
| Base PostgreSQL **avec PostGIS** | **Neon** | 3 Gio par branche | La contrainte est PostGIS, pas la taille : beaucoup d'offres gratuites ne l'autorisent pas. Neon le prend en charge. |
| API Django **avec GDAL** | **Koyeb** ou **Render** | 512 Mo RAM | Deux chemins possibles : image Docker, ou environnement Python natif (voir § 5 bis). |
| Fichiers déposés | **Cloudflare R2** | 10 Go, sortie réseau gratuite | Compatible S3, donc directement utilisable par la plateforme. Les 10 Go sont la vraie limite du dispositif. |
| Interface web | **Cloudflare Pages** ou **Netlify** | illimité en pratique | Ce ne sont que des fichiers statiques. |

Redis et le worker Celery ne sont pas déployés : en gardant
`CELERY_TASK_ALWAYS_EAGER=1`, l'extraction géospatiale s'exécute dans la requête.
Suffisant pour une démonstration, inacceptable en production avec de gros levés.

**Alternative à Koyeb : Render.** Offre gratuite plus généreuse en heures (750 h/mois)
mais l'instance s'endort après 15 minutes au lieu d'une heure, et sa base PostgreSQL
gratuite **expire au bout de 30 jours** — raison pour laquelle la base est chez Neon
dans tous les cas.

---

## 1 bis. La variante **Render + Supabase**

C'est l'assemblage le plus simple : **deux comptes au lieu de quatre**, Supabase
fournissant à la fois la base PostGIS et le stockage des fichiers.

| Besoin | Service | Gratuit |
|---|---|---|
| Base PostgreSQL + PostGIS | **Supabase** | 500 Mo |
| Stockage des fichiers | **Supabase Storage** (compatible S3) | 1 Go, 50 Mo par fichier |
| API Django | **Render** (Python natif ou Docker) | 750 h/mois |
| Interface web | **Render Static Site** | inclus |

### Côté Supabase

1. Créer un projet, en notant la **région** (elle servira de `S3_REGION`).
2. *Database → Extensions* : activer **postgis**. Vérifier ensuite dans
   *SQL Editor* :

```sql
SELECT PostGIS_Version();
```

3. *Storage* : créer un bucket **privé** nommé `dcuhat`. Le laisser privé n'est
   pas un détail : la plateforme sert les fichiers par URL signée à durée
   limitée, après avoir vérifié les droits de l'agent. Un bucket public
   contournerait tout le contrôle d'accès.
4. *Storage → S3 Connection* : générer une paire **Access Key / Secret**, et
   relever l'URL du point d'accès, de la forme
   `https://<ref>.storage.supabase.co/storage/v1/s3`.
5. *Database → Connect* : copier la chaîne du **Session pooler**.

> **Prenez bien le « Session pooler », pas la connexion directe.** La connexion
> directe de Supabase n'est joignable qu'en IPv6, dont Render ne dispose pas :
> le service ne démarrerait pas. Le pooler de session est en IPv4 sur tous les
> plans, avec un nom d'utilisateur de la forme `postgres.<ref>` et le port 5432.
>
> Évitez le « Transaction pooler » (port 6543) : il ne conserve pas la session
> entre deux requêtes, ce qui interdit les curseurs côté serveur. La plateforme
> s'y adapte si vous le configurez, mais le pooler de session est plus simple et
> sans compromis.

### Côté Render

Un **Web Service** pour l'API (voir § 5 pour Docker, § 5 bis pour Python natif),
avec ces variables :

```ini
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<50 caractères aléatoires>
ALLOWED_HOSTS=<votre-service>.onrender.com
CORS_ALLOWED_ORIGINS=https://<votre-interface>.onrender.com

# Une seule ligne : celle du Session pooler, collée telle quelle.
DATABASE_URL=postgresql://postgres.<ref>:<mot de passe>@aws-0-<region>.pooler.supabase.com:5432/postgres
POSTGRES_SSLMODE=require

OBJECT_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<ref>.storage.supabase.co/storage/v1/s3
S3_ACCESS_KEY=<Access Key Supabase>
S3_SECRET_KEY=<Secret Supabase>
S3_BUCKET=dcuhat
S3_REGION=<région du projet, ex. eu-central-1>

CELERY_TASK_ALWAYS_EAGER=1
USE_REDIS_CACHE=0
GUNICORN_WORKERS=1
MAX_UPLOAD_SIZE_MB=45
```

`DATABASE_URL` remplace à elle seule les cinq variables `POSTGRES_*` : la
plateforme la décompose. Recopier cinq champs à la main est une source d'erreurs
de trop.

`MAX_UPLOAD_SIZE_MB=45` n'est pas arbitraire : Supabase refuse les fichiers de
plus de **50 Mo** sur l'offre gratuite. Mieux vaut un refus clair de la
plateforme qu'une erreur du stockage à la fin d'un long téléversement.

Puis un **Static Site** pour l'interface :

- Root Directory : `frontend`
- Build Command : `npm ci && npm run build`
- Publish Directory : `dist`
- Variable : `VITE_API_URL=https://<votre-service>.onrender.com/api/v1`
- Redirect/Rewrite : source `/*`, destination `/index.html`, type **Rewrite** —
  sans cette règle, recharger une page interne renvoie une erreur 404.

### Le vrai compteur : la bande passante Render

Le site statique est **gratuit à déployer** — mais, comme le service web, il
consomme la bande passante de l'espace de travail, et l'offre Hobby n'inclut
que **5 Go par mois** (au-delà : 0,15 $/Go), plus 500 minutes de compilation.
C'est la limite qui compte réellement, bien avant les 750 heures d'instance.

Bonne nouvelle : l'architecture de la plateforme la ménage presque
entièrement. Quand le stockage objet sait produire une URL signée — c'est le
cas de Supabase, de R2 et de MinIO — **le téléchargement d'un document ne passe
pas par Render** : l'API renvoie une URL à durée limitée et le navigateur va
chercher le fichier directement chez le fournisseur de stockage. Render ne sert
donc que l'interface (environ 350 Ko compressés au premier chargement, puis le
cache du navigateur et le Service Worker) et les réponses JSON de l'API.

Concrètement, 5 Go par mois tiennent largement pour une direction de quelques
dizaines d'agents. Deux réserves tout de même :

- **Le téléchargement d'un dossier en archive `.zip` traverse l'API**, lui.
  C'est le seul geste qui peut consommer vite ; à éviter sur les gros dossiers
  tant qu'on est en offre gratuite.
- **500 minutes de compilation par mois** : chaque envoi sur le dépôt
  reconstruit le service et le site, soit deux à quatre minutes à chaque fois.
  De quoi tenir, mais pas de quoi pousser cinquante fois par jour.

Deux noms de domaine personnalisés sont inclus, certificats TLS compris.

> **Alternative gratuite pour l'interface.** Héberger le site statique sur
> **Cloudflare Pages** plutôt que sur Render sort complètement l'interface du
> compteur : son offre gratuite ne facture pas la bande passante. Render ne sert
> alors que l'API. C'est le réglage à retenir si la démonstration doit durer.

### Les deux autres pièges de cet assemblage

**Le projet Supabase se met en pause après une semaine sans activité**, sur
l'offre gratuite. Il se réveille depuis le tableau de bord, mais une plateforme
qui ne répond pas le lundi matin donne une mauvaise impression à la Direction.
Si la démonstration doit durer, prévoyez une visite hebdomadaire — ou un appel
automatique à `/api/v1/auth/login/` depuis un service de surveillance gratuit.

**500 Mo de base et 1 Go de fichiers**, c'est deux à trois fois moins que
l'assemblage Neon + R2 décrit plus haut. Pour une démonstration c'est
confortable ; pour un pilote avec plusieurs services qui déposent réellement,
cela se remplit en quelques semaines.

---

## 2. Préparer le dépôt

Le code doit être accessible depuis un dépôt Git.

```powershell
cd C:\Users\DNTCP\PycharmProjects\dcuhat
git init
git add .
git commit -m "DCUHAT — plateforme documentaire et geospatiale"
```

Vérifiez que `.env` **n'est pas** dans le commit — il est déjà exclu par le
`.gitignore`, mais un secret publié est un secret perdu :

```powershell
git status --short | Select-String ".env"
```

Cette commande ne doit rien afficher. Poussez ensuite vers un dépôt GitHub privé.

---

## 3. La base de données (Neon)

1. Créer un compte sur <https://neon.com>, puis un projet en **PostgreSQL 16**.
2. Ouvrir la console SQL du projet et activer l'extension :

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT PostGIS_Version();
```

3. Relever la chaîne de connexion. Elle donne les cinq variables dont la
   plateforme a besoin : hôte, base, utilisateur, mot de passe, port.

> Neon met la base en veille après quelques minutes d'inactivité. La première
> requête après une pause prend une à deux secondes : c'est normal, et cela
> s'ajoute au réveil de l'API.

---

## 4. Le stockage des fichiers (Cloudflare R2)

C'est l'étape à ne pas sauter. Les hébergements gratuits ont un disque
**éphémère** : tout fichier écrit sur le disque du conteneur disparaît au
redémarrage. En mode `local`, la plateforme perdrait les documents déposés.

1. Créer un compte Cloudflare, ouvrir **R2** et créer un bucket `dcuhat`.
2. Créer un jeton d'API R2 avec les droits *Object Read & Write*.
3. Relever l'identifiant, la clé secrète et l'URL de point d'accès, de la forme
   `https://<compte>.r2.cloudflarestorage.com`.

---

## 5. L'API (Koyeb)

1. Créer un compte sur <https://koyeb.com>, puis un service à partir du dépôt GitHub.
2. Type de build : **Dockerfile**, chemin `backend/Dockerfile`, contexte `backend`.
3. Port d'écoute : **8000** (le conteneur respecte aussi la variable `PORT`).
4. Renseigner les variables d'environnement :

```ini
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<50 caractères aléatoires, différents du poste local>
ALLOWED_HOSTS=<votre-service>.koyeb.app
CORS_ALLOWED_ORIGINS=https://<votre-interface>.pages.dev

POSTGRES_DB=<base Neon>
POSTGRES_USER=<utilisateur Neon>
POSTGRES_PASSWORD=<mot de passe Neon>
POSTGRES_HOST=<hôte Neon>
POSTGRES_PORT=5432

OBJECT_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<compte>.r2.cloudflarestorage.com
S3_ACCESS_KEY=<clé R2>
S3_SECRET_KEY=<secret R2>
S3_BUCKET=dcuhat
S3_REGION=auto

CELERY_TASK_ALWAYS_EAGER=1
USE_REDIS_CACHE=0
GUNICORN_WORKERS=1
MAX_UPLOAD_SIZE_MB=100
```

`GUNICORN_WORKERS=1` n'est pas un détail : chaque worker charge sa propre copie de
GDAL et de Django, et deux workers ne tiennent pas dans 512 Mo.

Le conteneur applique les migrations et collecte les fichiers statiques à chaque
démarrage. Créez ensuite les services et le compte administrateur depuis la console
Koyeb :

```
python manage.py initialiser_dcuhat --admin-email=votre.adresse@exemple.org
```

---

## 5 bis. Déployer **sans Docker**

Docker n'est pas obligatoire. La seule chose qu'il apportait, c'est GDAL — et il
existe une autre façon de l'obtenir : les roues PyPI de **rasterio** et
**shapely** embarquent GDAL, GEOS, PROJ et leurs dépendances directement dans
`site-packages`. Aucun paquet système à installer, donc aucun besoin d'accès
root.

La plateforme les détecte toute seule : `apps/common/geolibs.py` cherche, dans
l'ordre, la variable d'environnement, le bundle PostGIS sous Windows, la
bibliothèque système, puis les roues PyPI. Il n'y a aucun chemin à configurer.

### Sur Render, en mode Python natif

Créez un **Web Service**, connectez le dépôt, choisissez l'environnement
**Python 3**, et renseignez :

- **Root Directory** : `backend`
- **Build Command** :

```
pip install -r requirements-sans-docker.txt && python manage.py collectstatic --noinput
```

- **Start Command** :

```
python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 300
```

Les variables d'environnement sont les mêmes qu'au § 5.

### Vérifier que GDAL est bien vu

Une commande répond à la question, sur n'importe quelle machine :

```
python manage.py verifier_geo
```

Elle indique quelle bibliothèque a été retenue, d'où elle vient, quelle version
se charge réellement, et si PostGIS répond. C'est le premier réflexe quand la
plateforme refuse de démarrer sur un nouvel hébergement.

### Ce que coûte l'absence de Docker

| | Docker | Python natif |
|---|---|---|
| GDAL | paquet système, version maîtrisée | roues PyPI, ~100 Mo de dépendances |
| `ogr2ogr` (conversions de formats) | présent | **absent** — la conversion entre formats géospatiaux ne fonctionnera pas |
| Reproductibilité | identique partout | dépend de la version de Python de l'hébergeur |
| Démarrage | image prête | installation à chaque déploiement, plus lent |

La perte d'`ogr2ogr` est la seule vraie fonctionnalité en moins : tout le reste
— dépôt, versions, carte, emprises, recherche spatiale, hors ligne — fonctionne
à l'identique. Si les conversions comptent pour le service du Cadastre, c'est un
argument pour Docker ; sinon, le mode natif est plus simple.

---

## 6. L'interface (Cloudflare Pages)

1. Nouveau projet Pages connecté au même dépôt.
2. Réglages de build :
   - Répertoire racine : `frontend`
   - Commande : `npm run build`
   - Répertoire de sortie : `dist`
3. Variable d'environnement de build :

```ini
VITE_API_URL=https://<votre-service>.koyeb.app/api/v1
```

Le proxy de développement ne s'applique qu'à `npm run dev` : en ligne, l'interface
appelle directement l'API. C'est pourquoi `CORS_ALLOWED_ORIGINS` doit contenir
**exactement** l'adresse de Pages, protocole compris.

---

## 7. Recette après mise en ligne

- [ ] La page de connexion s'affiche
- [ ] La connexion aboutit (une ligne `POST /api/v1/auth/login/ 200` dans les journaux)
- [ ] Création d'un espace, puis d'un dossier
- [ ] Dépôt d'un PDF, puis rechargement de la page : le fichier est toujours là
- [ ] **Redémarrage du service, puis nouveau rechargement** : le fichier est toujours là — c'est le test qui valide R2
- [ ] Dépôt d'un GeoJSON : l'emprise apparaît sur la carte
- [ ] Mode avion : les dossiers déjà consultés restent accessibles
- [ ] `python manage.py verifier_geo` depuis la console de l'hébergeur : GDAL, GEOS et PostGIS répondent
- [ ] Recharger une page interne (par exemple `/administration`) : elle s'affiche au lieu d'une erreur 404

---

## 8. Ce que « gratuit » coûte réellement

Ces limites ne sont pas des détails de confort : elles décident de ce que la
plateforme peut porter.

| Limite | Conséquence concrète |
|---|---|
| L'API s'endort après une heure sans trafic | Le premier agent du matin attend 30 à 60 secondes. Les suivants non. |
| 512 Mo de mémoire | Le téléversement fragmenté réassemble le fichier en mémoire : au-delà d'environ 100 Mo, le conteneur est tué. D'où `MAX_UPLOAD_SIZE_MB=100`. **Un levé topographique de 300 Mo ne passera pas.** |
| 10 Go de stockage | Quelques milliers de documents bureautiques, ou quelques dizaines d'orthophotos. Les versions comptent double. |
| Pas de sauvegarde automatique | À faire soi-même : `pg_dump` régulier depuis un poste, et copie du bucket. Une sauvegarde jamais restaurée n'est pas une sauvegarde. |
| Aucun engagement de disponibilité | Le service peut disparaître ou changer ses conditions du jour au lendemain. |
| Données hébergées hors du pays | C'est la limite la plus sérieuse. Des plans de lotissement, des titres fonciers et des dossiers nominatifs de demandeurs sont des données publiques sensibles ; leur hébergement relève d'une décision de la Direction, pas d'un choix technique. |

**Conclusion honnête.** Cette configuration est excellente pour montrer la
plateforme à la Direction, faire tester les agents et emporter la décision. Elle
n'est pas un cadre acceptable pour les archives réelles de la commune.

Pour la production, deux voies, chiffrées dans `docs/03-deploiement-maintenance.md` :
un VPS à quelques euros par mois (Docker Compose complet, sauvegardes maîtrisées),
ou un serveur à la mairie (souveraineté totale, mais onduleur et sauvegarde hors
site indispensables). Dans les deux cas, on retrouve le worker Celery, un disque
persistant et des téléversements sans limite artificielle.
