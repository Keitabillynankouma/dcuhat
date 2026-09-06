# DCUHAT — Plateforme documentaire et géospatiale

**Direction Communale de l'Urbanisme, de l'Habitat et de l'Aménagement du Territoire de Lambayin**

Espace documentaire partagé de la Direction : tout document produit ou reçu — plan de
lotissement, levé topographique, permis de construire, arrêté, photo de terrain — y est
déposé, classé, retrouvable, versionné et partagé selon des droits explicites, que
l'agent soit au bureau ou sur le terrain sans réseau.

---

## Ce que la plateforme garantit

1. **Rien ne se perd.** Chaque modification crée une version, la suppression passe par une
   corbeille, et chaque action est journalisée et attribuée à un agent nommé.
2. **La carte est une vue de la base documentaire.** Un fichier géoréférencé apparaît à la
   fois dans l'arborescence et sur la carte communale ; « que sait-on de cette parcelle ? »
   devient une requête.
3. **Le terrain fonctionne sans réseau.** L'application est utilisable hors ligne par
   conception, et une synchronisation ne détruit jamais un travail de terrain : en cas de
   conflit, les deux versions sont conservées.

---

## Démarrage rapide

```bash
cp .env.example .env          # puis renseignez les mots de passe
docker compose up -d --build
docker compose exec api python manage.py initialiser_dcuhat \
    --admin-email=votre.adresse@exemple.org
```

Puis créez les agents :

```bash
docker compose exec api python manage.py creer_agent \
    --email=f.bah@lambayin.gov --prenom=Fatou --nom=Bah \
    --role=CHEF_SERVICE --service=CADASTRE
```

L'interface est sur http://localhost:5173, l'API sur http://localhost:8000/api/v1/,
la documentation interactive de l'API sur http://localhost:8000/api/docs/ et
l'administration sur http://localhost:8000/admin/.

La commande `initialiser_dcuhat` crée les six services de la Direction, leur arborescence
métier (permis de construire, levés topographiques, titres fonciers…) et le compte
administrateur. Si aucun mot de passe n'est fourni, il est généré et affiché une seule fois.

### Développement sans Docker

```bash
# Backend — nécessite PostgreSQL 16 + PostGIS 3.4 et GDAL
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py initialiser_dcuhat
python manage.py runserver

# Interface
cd frontend
npm install
npm run dev
```

---

## Architecture

| Couche | Technologie | Rôle |
|---|---|---|
| API | Django 5 + Django REST Framework | Métier, droits, journal |
| Base | PostgreSQL 16 + PostGIS 3.4 | Données et index spatial |
| Objets | MinIO (S3-compatible) ou disque local | Contenus binaires |
| Tâches | Celery + Redis | Extraction, vignettes, conversions |
| Interface | React 18 + TypeScript + Vite (PWA) | Explorateur, carte, hors ligne |
| Carte | Leaflet + OpenStreetMap | Emprises et couches communales |

```
backend/
  config/          configuration Django, Celery, routes
  apps/accounts/   utilisateurs, services, rôles, 2FA, appareils
  apps/storage/    dossiers, fichiers, versions, métadonnées, corbeille
  apps/geo/        extraction géospatiale, emprises, conversions, couches
  apps/sharing/    permissions par nœud, liens de partage
  apps/sync/       delta, file d'opérations, résolution de conflits
  apps/audit/      journal d'activité immuable
  apps/search/     recherche plein texte, métier et spatiale
  tests/           75 tests couvrant droits, versions, sync, géo, API
frontend/
  src/api/         client HTTP, téléversement fragmenté
  src/hors-ligne/  IndexedDB, chiffrement local, file d'opérations, sync
  src/pages/       explorateur, fiche fichier, carte, recherche, conflits…
docs/              spécifications, guide utilisateur, déploiement
deploy/            Nginx, sauvegardes
```

---

## Points de conception qui méritent d'être connus

**Le chemin matérialisé.** Chaque dossier porte son chemin complet (`/cadastre/leves/2026/`).
Les deux requêtes les plus fréquentes de la plateforme — « tout le sous-arbre » pour les
droits hérités et « les changements sous ce dossier » pour la synchronisation — deviennent
un simple `LIKE`. Un renommage réécrit le sous-arbre en une passe.

**Les identifiants générés par le client.** Un dossier créé hors ligne reçoit son UUID sur
la tablette, et le serveur l'accepte tel quel. Aucune réécriture d'identifiant à la
synchronisation, donc aucune des erreurs de réconciliation qui vont avec.

**Le téléversement fragmenté.** Au-delà de 10 Mo, l'envoi est découpé en fragments de 5 Mo
acquittés séparément. Sur une liaison qui coupe, seul le fragment perdu est réémis — un
levé de 300 Mo ne repart jamais de zéro. Le quota est vérifié à l'ouverture du
téléversement, avant tout transfert.

**Aucune projection devinée.** Quand le système de projection d'un fichier est introuvable,
la plateforme le signale et demande à l'agent de le déclarer, plutôt que de supposer. Une
emprise fausse sur une carte communale est plus dangereuse qu'une emprise absente.

**Le conflit ne détruit rien.** Un fichier modifié au bureau et sur le terrain donne deux
versions conservées, une notification à l'agent, et un arbitrage explicite. Le serveur ne
choisit jamais silencieusement.

**404 plutôt que 403.** Un dossier auquel l'agent n'a pas droit est invisible : répondre
« interdit » révélerait déjà son existence.

---

## Tests

```bash
make tests                        # ou : cd backend && python manage.py test tests
cd frontend && npm run verifier   # vérification des types
```

75 tests couvrent le moteur de permissions (héritage, expiration, cloisonnement des
services), le versionnement et la déduplication, les quotas, le téléversement fragmenté et
son idempotence, les six règles de résolution de conflits, l'extraction géospatiale et la
recherche spatiale, la recherche plein texte et métier, le partage par lien et le journal
d'activité.

---

## Documentation

- `docs/00-demarrage.md` — les trente premières minutes : lancer, créer les comptes, déposer le premier document
- `docs/01-specifications-techniques.md` — modèle de données, architecture, API, règles métier
- `docs/02-guide-utilisateur.md` — prise en main pour les agents de la Direction
- `docs/03-deploiement-maintenance.md` — mise en production, sauvegardes, exploitation
- `docs/04-installation-windows.md` — installation native sous Windows, sans Docker
- `docs/05-deploiement-gratuit.md` — mise en ligne à coût nul, pour démonstration et recette

---

## Reste à trancher avec la Direction

1. Nombre d'agents au lancement et volumétrie des archives à reprendre.
2. Hébergement : serveur à la mairie (autonomie, contrainte d'électricité) ou VPS
   (disponibilité, dépendance à la liaison internet).
3. Reprise de l'existant : archives papier à numériser, ou fonds numérique à importer ?
4. Systèmes de projection officiellement utilisés par le service du Cadastre.
5. Nécessité d'une application mobile native en plus de la PWA.
