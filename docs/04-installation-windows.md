# Installation native sous Windows (sans Docker)

À utiliser lorsque Docker Desktop ne démarre pas, ou lorsqu'on préfère un environnement de
développement direct : `runserver` recharge à chaque sauvegarde, sans reconstruire d'image.

Compter environ trente minutes la première fois. Les trois quarts des difficultés viennent
de GDAL — la section 3 les traite une par une.

---

## 1. PostgreSQL 16 et PostGIS

1. Télécharger l'installateur EDB : <https://www.enterprisedb.com/downloads/postgres-postgresql-downloads> — version **16**.
2. Pendant l'installation : noter le mot de passe du compte `postgres`, laisser le port `5432`.
3. À la fin, **laisser cochée** la case *Launch Stack Builder*.
4. Dans Stack Builder : sélectionner l'instance PostgreSQL 16, puis
   **Spatial Extensions → PostGIS 3.4 Bundle**. Installer.

Vérification, dans un terminal :

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "SELECT version();"
```

Création de la base :

```powershell
$env:PGPASSWORD = "<mot de passe postgres>"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE dcuhat;"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d dcuhat -c "CREATE EXTENSION postgis;"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d dcuhat -c "SELECT PostGIS_Version();"
```

La dernière commande doit répondre quelque chose comme `3.4 USE_GEOS=1 USE_PROJ=1`.

---

## 2. Python 3.12 et Node

- Python 3.12 : <https://www.python.org/downloads/windows/> — **cocher « Add python.exe to PATH »**.
- Node 20 ou plus : <https://nodejs.org/> (version LTS).

```powershell
python --version
node --version
```

---

## 3. GDAL — la partie délicate

GeoDjango a besoin des bibliothèques **GDAL**, **GEOS** et **PROJ**. Le bundle PostGIS en
installe une copie, mais elle n'est pas toujours visible depuis Python. La voie fiable est
**OSGeo4W**, l'installateur officiel du projet OSGeo.

1. Télécharger `osgeo4w-setup.exe` : <https://trac.osgeo.org/osgeo4w/>
2. Choisir **Express Install**, puis cocher **GDAL**. Laisser le répertoire par défaut
   `C:\OSGeo4W`.

### Déclarer les chemins à Windows

Ouvrir *Paramètres → Système → Informations système → Paramètres système avancés →
Variables d'environnement*, et ajouter dans **Variables système** :

| Variable | Valeur |
|---|---|
| `OSGEO4W_ROOT` | `C:\OSGeo4W` |
| `PROJ_LIB` | `C:\OSGeo4W\share\proj` |
| `GDAL_DATA` | `C:\OSGeo4W\share\gdal` |

Puis, dans la variable `Path`, ajouter **en première position** :

```
C:\OSGeo4W\bin
```

La position compte : si un autre logiciel (QGIS, PostGIS, ArcGIS) a déjà déposé une version
différente de `gdal*.dll` plus haut dans le `Path`, Python chargera la mauvaise et tombera
sur une erreur illisible.

**Fermer et rouvrir le terminal** — les variables d'environnement ne sont pas rechargées
dans une session déjà ouverte.

```powershell
ogrinfo --version
```

Doit répondre `GDAL 3.x.x, released ...`.

### Trouver le nom exact des DLL

Le nom du fichier change à chaque version majeure de GDAL (`gdal309.dll`, `gdal310.dll`…) :

```powershell
Get-ChildItem C:\OSGeo4W\bin\gdal*.dll
Get-ChildItem C:\OSGeo4W\bin\geos_c.dll
```

Notez les deux chemins complets : ils vont dans le `.env` à l'étape suivante. Le projet lit
`GDAL_LIBRARY_PATH` et `GEOS_LIBRARY_PATH` depuis l'environnement, précisément pour éviter
d'avoir à deviner.

---

## 4. Configurer le projet

Dans `C:\Users\<vous>\PycharmProjects\dcuhat\.env` :

```ini
DJANGO_DEBUG=1
DJANGO_SECRET_KEY=<votre clé>
ALLOWED_HOSTS=localhost,127.0.0.1

# Base locale, et non le conteneur « db »
POSTGRES_DB=dcuhat
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<mot de passe postgres>
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432

# Ni MinIO ni Redis : les fichiers vont sur le disque, les tâches s'exécutent
# directement dans le processus web.
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_ROOT=C:/Users/<vous>/PycharmProjects/dcuhat/var/objets
CELERY_TASK_ALWAYS_EAGER=1
USE_REDIS_CACHE=0

CORS_ALLOWED_ORIGINS=http://localhost:5173

# Chemins relevés à l'étape 3 — adapter le numéro de version
GDAL_LIBRARY_PATH=C:/OSGeo4W/bin/gdal310.dll
GEOS_LIBRARY_PATH=C:/OSGeo4W/bin/geos_c.dll
```

> Utilisez des barres obliques `/` et non `\` dans les chemins du `.env` : la barre inverse
> y est interprétée comme un caractère d'échappement.

---

## 5. Backend

```powershell
cd C:\Users\<vous>\PycharmProjects\dcuhat\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell refuse d'exécuter le script d'activation :

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Vérifier que Django voit bien GDAL **avant** de migrer :

```powershell
python manage.py verifier_geo
```

Cette commande cherche seule les bibliothèques dans le bundle PostGIS et dans
OSGeo4W, affiche celle qui sera retenue, et teste le chargement réel. Si elle
répond correctement, les variables `GDAL_LIBRARY_PATH` et `GEOS_LIBRARY_PATH`
du `.env` sont facultatives.

Puis :

```powershell
python manage.py migrate
python manage.py initialiser_dcuhat --admin-email=votre.adresse@exemple.org
python manage.py test tests      # 75 tests, pour valider l'installation
python manage.py runserver
```

L'API répond sur <http://127.0.0.1:8000/api/v1/>, l'administration sur
<http://127.0.0.1:8000/admin/>.

---

## 6. Interface

Dans un **second** terminal, en laissant `runserver` tourner :

```powershell
cd C:\Users\<vous>\PycharmProjects\dcuhat\frontend
npm install
npm run dev
```

L'application est sur <http://localhost:5173>.

Vite lit `VITE_API_URL`. Créez `frontend\.env.local` :

```ini
VITE_API_URL=http://127.0.0.1:8000/api/v1
```

---

## 7. Ce qui change par rapport à Docker

| | Docker | Installation native |
|---|---|---|
| Stockage des fichiers | MinIO (S3) | Disque, dans `var/objets` |
| Tâches d'analyse | Worker Celery séparé | Exécutées dans la requête (`ALWAYS_EAGER`) |
| Cache | Redis | Mémoire du processus |
| Rechargement du code | Reconstruction d'image | Immédiat |

Conséquence pratique : le dépôt d'un gros fichier géospatial est **plus lent**, puisque
l'extraction de l'emprise se fait pendant la requête au lieu d'être déportée. C'est sans
importance en développement, mais la production doit repasser par Docker — ou faire tourner
un worker Celery séparé.

---

## 8. Erreurs fréquentes

| Message | Cause et remède |
|---|---|
| `Could not find the GDAL library` | `GDAL_LIBRARY_PATH` absent ou nom de DLL faux. Relister `C:\OSGeo4W\bin\gdal*.dll`. |
| `OSError: [WinError 126] Le module spécifié est introuvable` | La DLL est trouvée mais ses dépendances non : `C:\OSGeo4W\bin` n'est pas dans le `Path`, ou pas en première position. |
| `django.contrib.gis.gdal.error.SRSException` | `PROJ_LIB` n'est pas défini, ou pointe ailleurs que `C:\OSGeo4W\share\proj`. |
| `psycopg.OperationalError: connection refused` | Le service PostgreSQL n'est pas démarré : `services.msc` → *postgresql-x64-16*. |
| `type "geometry" does not exist` | L'extension PostGIS n'a pas été créée dans **cette** base : rejouer `CREATE EXTENSION postgis;` sur `dcuhat`. |
| `ogr2ogr` introuvable au moment d'une conversion | `C:\OSGeo4W\bin` absent du `Path` du terminal qui lance `runserver`. Fermer et rouvrir le terminal. |
| Les variables du `.env` semblent ignorées | Le `.env` doit être à la racine du projet (à côté de `docker-compose.yml`), pas dans `backend\`. |
