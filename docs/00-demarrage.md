# Démarrer avec DCUHAT

Ce document couvre les trente premières minutes : lancer la plateforme, créer les comptes,
déposer le premier document. Il suppose que vous partez de l'archive `dcuhat.zip`.

---

## 1. Préparer le poste

Un seul prérequis : **Docker Desktop** (Windows, macOS ou Linux). Il embarque PostgreSQL,
PostGIS, MinIO, Redis, Python et Node — rien d'autre n'est à installer.

Vérifiez qu'il tourne :

```powershell
docker --version
docker compose version
```

Si les deux commandes répondent, vous êtes prêt. Sinon, installez Docker Desktop et
**redémarrez la session Windows** avant de continuer.

> Si vous ne pouvez pas installer Docker, la section 6 donne la procédure manuelle. Elle
> demande d'installer PostgreSQL 16, PostGIS et GDAL à la main : réservez-la au cas où
> Docker est réellement impossible.

---

## 2. Décompresser et configurer

```powershell
cd C:\Users\DNTCP\PycharmProjects
Expand-Archive dcuhat.zip -DestinationPath .
cd dcuhat
copy .env.example .env
```

Ouvrez `.env` et remplacez au minimum ces quatre valeurs :

```ini
DJANGO_SECRET_KEY=<une longue chaîne aléatoire>
POSTGRES_PASSWORD=<un mot de passe long>
S3_SECRET_KEY=<un autre mot de passe long>
DJANGO_DEBUG=1          # 1 en développement, 0 en production
```

Pour générer une clé :

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Laissez les autres valeurs telles quelles : elles sont déjà réglées pour un poste de
développement (`POSTGRES_HOST=db`, `CORS_ALLOWED_ORIGINS=http://localhost:5173`).

---

## 3. Lancer la plateforme

```powershell
docker compose up -d --build
```

Le premier lancement télécharge les images et compile l'interface : comptez cinq à dix
minutes. Ensuite, quelques secondes.

Vérifiez que tout tourne :

```powershell
docker compose ps
```

Les services `db`, `minio`, `redis`, `api`, `worker`, `beat` et `web` doivent être à l'état
*running*. Si `api` redémarre en boucle :

```powershell
docker compose logs api
```

La cause la plus fréquente est une valeur oubliée dans `.env`.

---

## 4. Initialiser la Direction

```powershell
docker compose exec api python manage.py initialiser_dcuhat --admin-email=votre.adresse@exemple.org
```

La commande crée :

- les **six services** de la Direction (Urbanisme, Habitat, Aménagement, Cadastre,
  Affaires domaniales, Archives) ;
- leur **arborescence métier** : permis de construire, certificats d'urbanisme,
  lotissements, levés topographiques, plans cadastraux, titres fonciers, arrêtés… ;
- le **compte administrateur**.

Si vous n'avez pas passé `--admin-password`, un mot de passe est généré et affiché **une
seule fois**. Notez-le immédiatement.

---

## 5. Les trois adresses à connaître

| Adresse | À quoi elle sert |
|---|---|
| http://localhost:5173 | **L'application** — ce que voient les agents |
| http://localhost:8000/admin/ | L'administration : comptes, services, quotas |
| http://localhost:8000/api/docs/ | La documentation interactive de l'API |

### Créer les agents

Deux façons, au choix.

**Depuis l'administration** — http://localhost:8000/admin/ → *Utilisateurs* → *Ajouter*.
Renseignez l'adresse, le nom, le rôle et le service. Le mot de passe saisi est provisoire :
l'agent devra le changer à sa première connexion.

**En ligne de commande**, plus rapide pour créer une équipe :

```powershell
docker compose exec api python manage.py creer_agent --email=f.bah@lambayin.gov --prenom=Fatou --nom=Bah --role=CHEF_SERVICE --service=CADASTRE
docker compose exec api python manage.py creer_agent --email=i.sow@lambayin.gov --prenom=Ibrahima --nom=Sow --role=AGENT --service=URBANISME
```

Rôles disponibles : `ADMIN`, `DIRECTEUR`, `CHEF_SERVICE`, `AGENT`, `LECTEUR`, `INVITE`.
Codes de service : `URBANISME`, `HABITAT`, `AMENAGEMENT`, `CADASTRE`, `DOMANIAL`, `ARCHIVES`.

### Premier tour de l'application

1. Ouvrez http://localhost:5173 et connectez-vous avec le compte administrateur.
2. L'accueil affiche les espaces des services. Ouvrez **Cadastre → Levés topographiques**.
3. Glissez-y un fichier — un PDF, ou mieux, un GeoJSON ou un Shapefile zippé.
4. Cliquez sur le fichier : sa fiche montre l'historique des versions, les champs du
   dossier et, s'il est géoréférencé, son emprise sur la carte.
5. Redéposez le même fichier modifié : une **version 2** apparaît, la version 1 reste.
6. Ouvrez l'onglet **Carte** : le fichier géoréférencé y figure.
7. Coupez le réseau (mode avion), naviguez : les dossiers déjà consultés restent
   accessibles. Rétablissez le réseau : la synchronisation repart seule.

---

## 6. Sans Docker (procédure manuelle)

À réserver au cas où Docker est impossible.

**Prérequis** : PostgreSQL 16 avec l'extension PostGIS 3.4, GDAL (`gdal-bin`), Python 3.12,
Node 20 ou plus. Sous Windows, PostGIS et GDAL s'installent via *Stack Builder*, livré avec
l'installateur PostgreSQL ; ajoutez le dossier `bin` de GDAL au `PATH`.

```powershell
# Base de données
psql -U postgres -c "CREATE DATABASE dcuhat;"
psql -U postgres -d dcuhat -c "CREATE EXTENSION postgis;"

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py initialiser_dcuhat --admin-email=votre.adresse@exemple.org
python manage.py runserver

# Interface, dans un second terminal
cd frontend
npm install
npm run dev
```

Dans `.env`, mettez alors `POSTGRES_HOST=127.0.0.1`, `OBJECT_STORAGE_BACKEND=local` et
`CELERY_TASK_ALWAYS_EAGER=1` (les traitements géospatiaux s'exécutent alors directement,
sans Redis ni worker).

---

## 7. Commandes du quotidien

```powershell
docker compose logs -f api        # suivre les journaux
docker compose restart api        # redémarrer après modification de .env
docker compose down               # arrêter (les données sont conservées)
docker compose down -v            # arrêter ET tout effacer — irréversible
cd backend; python manage.py test tests   # 75 tests
```

---

## 8. Si quelque chose coince

| Symptôme | Cause la plus fréquente |
|---|---|
| `api` redémarre en boucle | Valeur manquante dans `.env` — voyez `docker compose logs api` |
| Page blanche sur :5173 | L'interface est encore en compilation ; attendez, puis rechargez |
| « Network Error » dans l'application | `CORS_ALLOWED_ORIGINS` ne contient pas `http://localhost:5173` |
| Connexion refusée à l'administration | Le rôle du compte n'est pas `ADMIN` |
| Un fichier géo n'apparaît pas sur la carte | Sa projection est indéterminée : ouvrez sa fiche et déclarez-la |
| Port 8000 ou 5173 déjà utilisé | Un autre programme l'occupe ; changez le port dans `docker-compose.yml` |

Pour aller plus loin : `docs/02-guide-utilisateur.md` pour les agents,
`docs/03-deploiement-maintenance.md` pour la mise en production.
