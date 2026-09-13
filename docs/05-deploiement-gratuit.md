# Mettre DCUHAT en ligne gratuitement

Ce document décrit une mise en ligne à coût nul, de bout en bout, pour une
**démonstration à la Direction** ou une recette avec quelques agents. Sa
dernière partie dit franchement où sont les limites et à partir de quand il
faut passer à un hébergement payant.

Compter une à deux heures la première fois. Aucune carte bancaire n'est requise.

---

## 1. L'assemblage retenu

Deux comptes suffisent : **Supabase** pour les données, **Render** pour
l'application.

| Besoin | Service | Offre gratuite |
|---|---|---|
| Base PostgreSQL **avec PostGIS** | Supabase | 500 Mo |
| Fichiers déposés par les agents | Supabase Storage (compatible S3) | 1 Go, 50 Mo par fichier |
| API Django | Render — Web Service | 750 h/mois |
| Interface web | Cloudflare Pages *(recommandé)* ou Render Static Site | gratuit |

**Pourquoi Supabase pour la base.** La contrainte n'est pas la taille, c'est
**PostGIS** : beaucoup d'hébergeurs PostgreSQL gratuits ne l'autorisent pas.
Supabase l'active en un clic, et fournit en prime le stockage des fichiers —
d'où deux comptes au lieu de quatre.

**Pourquoi pas Vercel.** Techniquement, Vercel ferait très bien l'affaire. Mais
son offre gratuite (« Hobby ») est réservée aux projets **personnels et non
commerciaux** : une plateforme livrée à une direction communale n'entre pas dans
ce cadre. Cloudflare Pages n'impose pas cette restriction.

**Pourquoi Cloudflare Pages pour l'interface.** Render facture la bande
passante au-delà de 5 Go par mois, tous services confondus. Servir l'interface
depuis Cloudflare Pages, dont l'offre gratuite ne la facture pas, sort
l'essentiel du trafic de ce compteur. Render ne sert plus que des réponses JSON
de quelques kilo-octets.

**Ce qui n'est pas déployé.** Ni Redis, ni worker Celery : en gardant
`CELERY_TASK_ALWAYS_EAGER=1`, l'analyse géospatiale s'exécute pendant la
requête. C'est suffisant pour une démonstration ; c'est insuffisant en
production avec de gros levés.

---

## 2. Préparer le dépôt Git

Le code doit être accessible depuis GitHub.

```powershell
cd C:\Users\DNTCP\PycharmProjects\dcuhat
git init
git add .
git commit -m "DCUHAT - plateforme documentaire et geospatiale"
```

**Vérifiez qu'aucun secret ne part avec le commit** — le `.gitignore` exclut
déjà `.env`, mais un secret publié est un secret perdu :

```powershell
git status --short | Select-String ".env"
```

Cette commande ne doit rien afficher. Créez ensuite un dépôt **privé** sur
GitHub et poussez-y le projet.

---

## 3. Supabase — la base et les fichiers

### 3.1 Créer le projet

1. Compte sur <https://supabase.com>, puis **New project**.
2. Notez la **région** choisie : elle servira de `S3_REGION`.
3. Notez le **mot de passe de la base** : il n'est affiché qu'une fois.

### 3.2 Activer PostGIS

*Database → Extensions*, chercher **postgis**, activer. Puis vérifier dans
*SQL Editor* :

```sql
SELECT PostGIS_Version();
```

La réponse doit ressembler à `3.3 USE_GEOS=1 USE_PROJ=1 USE_STATS=1`. Sans
cette extension, les migrations échoueront dès la première table géospatiale.

### 3.3 Créer le bucket de fichiers

*Storage → New bucket*, nommé `dcuhat`, laissé **privé**.

> Le laisser privé n'est pas un détail de confort. La plateforme sert chaque
> document par une URL signée à durée limitée, **après** avoir vérifié les
> droits de l'agent. Un bucket public rendrait tous les documents accessibles à
> qui devine leur adresse, et contournerait entièrement le contrôle d'accès.

### 3.4 Relever les identifiants S3

*Storage → S3 Connection* : générer une paire **Access Key / Secret Key**, et
relever l'URL du point d'accès, de la forme :

```
https://<ref-du-projet>.storage.supabase.co/storage/v1/s3
```

### 3.5 Relever la chaîne de connexion

*Database → Connect*, onglet **Session pooler**. Copier la chaîne complète.

> **Prenez le « Session pooler », surtout pas la connexion directe.**
> La connexion directe de Supabase n'est joignable qu'en **IPv6**, dont Render
> ne dispose pas : le service ne démarrerait jamais, avec un message d'erreur
> peu parlant. Le pooler de session est en IPv4 sur tous les plans ; son nom
> d'utilisateur a la forme `postgres.<ref-du-projet>` et son port est 5432.
>
> Évitez aussi le « Transaction pooler » (port 6543) : il ne conserve pas la
> session entre deux requêtes, ce qui interdit les curseurs côté serveur. La
> plateforme s'y adapte si vous le configurez, mais le pooler de session est
> plus simple et sans compromis.

---

## 4. Render — l'API

### 4.1 Créer le service

**New → Web Service**, connecté au dépôt GitHub. Deux façons de construire,
au choix.

**Environnement Python** (le plus simple, recommandé) :

- Language : **Python 3**
- Root Directory : `backend`
- Build Command :

```
pip install -r requirements-sans-docker.txt && python manage.py collectstatic --noinput
```

- Start Command :

```
python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 300
```

Le fichier `requirements-sans-docker.txt` ajoute `rasterio` et `shapely`, dont
les paquets PyPI embarquent GDAL, GEOS et PROJ. La plateforme les détecte seule
— aucun chemin à configurer.

**Environnement Docker** (si les conversions de formats sont nécessaires) :

- Language : **Docker**
- Dockerfile Path : `backend/Dockerfile`
- Docker Build Context Directory : `backend`

La différence tient en une ligne : sans Docker, l'utilitaire `ogr2ogr` est
absent, donc **la conversion entre formats géospatiaux ne fonctionne pas**.
Tout le reste — dépôt, versions, carte, emprises, recherche spatiale, édition,
croquis, hors ligne — est identique.

### 4.2 Les variables d'environnement

```ini
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<50 caractères aléatoires, différents de ceux du poste local>
ALLOWED_HOSTS=<votre-service>.onrender.com
CORS_ALLOWED_ORIGINS=https://<votre-interface>.pages.dev

# Une seule ligne : celle du Session pooler, collée telle quelle.
DATABASE_URL=postgresql://postgres.<ref>:<mot de passe>@aws-0-<région>.pooler.supabase.com:5432/postgres
POSTGRES_SSLMODE=require
# Supabase installe PostGIS dans un schéma `extensions`. À ajouter seulement si
# les migrations échouent sur « type geometry does not exist ».
# POSTGRES_SEARCH_PATH=public,extensions

OBJECT_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<ref>.storage.supabase.co/storage/v1/s3
S3_ACCESS_KEY=<Access Key Supabase>
S3_SECRET_KEY=<Secret Key Supabase>
S3_BUCKET=dcuhat
S3_REGION=<région du projet, par exemple eu-central-1>

CELERY_TASK_ALWAYS_EAGER=1
USE_REDIS_CACHE=0
GUNICORN_WORKERS=1
MAX_UPLOAD_SIZE_MB=45
```

Trois de ces valeurs méritent une explication.

`DATABASE_URL` **remplace à elle seule** les cinq variables `POSTGRES_*` : la
plateforme la décompose. Recopier cinq champs à la main est une source
d'erreurs de trop.

`GUNICORN_WORKERS=1` n'est pas de la prudence excessive : chaque worker charge
sa propre copie de GDAL et de Django, et deux ne tiennent pas dans 512 Mo.

`MAX_UPLOAD_SIZE_MB=45` évite un échec en fin de téléversement : Supabase
refuse les fichiers de plus de **50 Mo** sur l'offre gratuite. Mieux vaut un
refus immédiat et clair de la plateforme qu'une erreur du stockage après trois
minutes d'attente.

### 4.3 Générer la clé secrète

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Ne réutilisez jamais celle de votre poste : elle signe les jetons de connexion.

---

## 5. Cloudflare Pages — l'interface

**Workers & Pages → Create → Pages → Connect to Git**, sur le même dépôt.

- Framework preset : **Vite**
- Root directory : `frontend`
- Build command : `npm run build`
- Build output directory : `dist`
- Variable d'environnement :

```ini
VITE_API_URL=https://<votre-service>.onrender.com/api/v1
```

Une fois l'adresse `*.pages.dev` connue, revenez dans Render corriger
`CORS_ALLOWED_ORIGINS` pour qu'elle corresponde **exactement**, protocole
compris, puis redéployez l'API.

> Le proxy de développement ne joue que pour `npm run dev`. En ligne,
> l'interface appelle directement l'API sur un autre domaine : c'est
> `CORS_ALLOWED_ORIGINS` qui autorise cet appel, et rien d'autre. Une valeur
> approximative se traduit par une page de connexion qui « ne joint pas le
> serveur », sans autre explication.

**Variante Render Static Site**, si vous préférez tout garder au même endroit :
Root Directory `frontend`, Build Command `npm ci && npm run build`, Publish
Directory `dist`, et surtout une règle **Rewrite** de `/*` vers `/index.html` —
sans elle, recharger une page interne comme `/administration` renvoie une 404.

---

## 6. Créer les comptes

Depuis Render, onglet **Shell** du service (ou en ajoutant temporairement la
commande au *Start Command*) :

```
python manage.py initialiser_dcuhat --admin-email=votre.adresse@exemple.org
```

La commande crée les six services de la Direction, leur arborescence métier, et
le compte administrateur. **Le mot de passe s'affiche une seule fois** :
notez-le immédiatement.

Les agents se créent ensuite depuis l'interface, onglet **Administration →
Agents**, qui génère pour chacun un mot de passe provisoire à transmettre.

---

## 7. Recette avant de montrer la plateforme

- [ ] La page de connexion s'affiche
- [ ] La connexion aboutit — une ligne `POST /api/v1/auth/login/ 200` dans les journaux Render
- [ ] `python manage.py verifier_geo` depuis le Shell : GDAL, GEOS et PostGIS répondent
- [ ] Création d'un espace, puis d'un dossier
- [ ] Dépôt d'un PDF, puis rechargement de la page : le fichier est toujours là
- [ ] **Redémarrage du service, puis nouveau rechargement : le fichier est toujours là** — c'est ce test, et lui seul, qui prouve que le stockage Supabase est bien utilisé et non le disque éphémère du conteneur
- [ ] Dépôt d'un GeoJSON : l'emprise apparaît sur la carte
- [ ] Création d'un croquis, quelques traits, enregistrement d'une version
- [ ] Rechargement d'une page interne (`/administration`) : elle s'affiche, pas une 404
- [ ] Mode avion : les dossiers déjà consultés restent accessibles

---

## 8. Ce que « gratuit » coûte réellement

Ces limites ne sont pas des désagréments de confort : elles décident de ce que
la plateforme peut porter.

| Limite | Conséquence concrète |
|---|---|
| **L'API s'endort après 15 minutes sans trafic** | Le premier agent de la matinée attend 30 à 60 secondes. Les suivants non. |
| **Le projet Supabase se met en pause après une semaine sans activité** | Une plateforme muette le lundi matin fait mauvais effet devant la Direction. Prévoyez une visite hebdomadaire, ou un appel automatique par un service de surveillance gratuit. |
| **512 Mo de mémoire** | Le téléversement fragmenté réassemble le fichier en mémoire : au-delà d'une centaine de mégaoctets, le conteneur est tué. **Un levé topographique de 300 Mo ne passera pas.** |
| **50 Mo par fichier, 1 Go au total** | Quelques milliers de documents bureautiques, ou quelques dizaines d'orthophotos. Les versions comptent double. |
| **500 Mo de base** | Largement suffisant : la base ne contient que les métadonnées, pas les fichiers. |
| **5 Go de bande passante Render par mois** | Peu contraignant : les téléchargements passent par une URL signée directement chez Supabase, sans traverser Render. Seule l'archive `.zip` d'un dossier transite par l'API — à éviter sur les gros dossiers. |
| **500 minutes de compilation par mois** | Chaque envoi sur le dépôt reconstruit le service : deux à quatre minutes. De quoi tenir, pas de quoi pousser cinquante fois par jour. |
| **Aucune sauvegarde automatique** | À faire soi-même : `pg_dump` régulier depuis un poste, et copie du bucket. Une sauvegarde jamais restaurée n'est pas une sauvegarde. |
| **Données hébergées hors du pays** | La limite la plus sérieuse. Des plans de lotissement, des titres fonciers et des dossiers nominatifs de demandeurs relèvent d'une décision de la Direction, pas d'un choix technique fait en configurant un service gratuit. |

**Conclusion honnête.** Cette configuration est excellente pour montrer la
plateforme, faire tester les agents et emporter la décision. Elle n'est pas un
cadre acceptable pour les archives réelles de la commune.

---

## 9. Si un de ces services est inaccessible

Selon l'endroit d'où vous travaillez, certains hébergeurs refusent les
inscriptions ou sont injoignables. Plutôt que d'en essayer dix, changez
d'approche : **un VPS à quelques euros par mois** règle tout d'un coup.

```bash
git clone <votre dépôt> /opt/dcuhat && cd /opt/dcuhat
cp .env.example .env      # renseigner les mots de passe
docker compose up -d --build
docker compose exec api python manage.py initialiser_dcuhat --admin-email=...
```

Vous retrouvez alors la pile complète : PostGIS, MinIO, Redis, le worker
Celery, un disque persistant, aucune mise en veille, aucun plafond artificiel
sur la taille des fichiers, et les sauvegardes sous votre contrôle
(`deploy/sauvegarde.sh`). C'est de toute façon ce que recommande
`docs/03-deploiement-maintenance.md` pour un vrai pilote.

Un hébergeur situé en Guinée ou dans la sous-région ajoute un argument qui pèse
davantage que le prix : la souveraineté des données de la commune.
