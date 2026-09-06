# DCUHAT — Spécifications techniques détaillées

**Plateforme collaborative de gestion documentaire et géospatiale**
Direction Communale de l'Urbanisme, de l'Habitat et de l'Aménagement du Territoire de Lambayin

| | |
|---|---|
| Version du document | 1.0 |
| Date | 31 août 2026 |
| Statut | Référence de développement |
| Périmètre V1 | Complet — documentaire + géospatial + hors ligne |

---

## 1. Vision produit

DCUHAT est l'espace documentaire unique de la Direction. Tout document produit ou reçu par
la Direction — plan de lotissement, levé topographique, permis de construire, arrêté,
photo de terrain, tableau de suivi — y est déposé, classé, retrouvable, versionné et
partagé selon des droits explicites, que l'agent soit au bureau ou sur le terrain sans réseau.

Trois promesses structurent toutes les décisions techniques du document :

1. **Rien ne se perd.** Tout fichier est versionné, la suppression est réversible, chaque
   action est journalisée et attribuée à un agent nommé.
2. **La carte est une vue de la base documentaire.** Un fichier géoréférencé n'est pas un
   fichier « à part » : il apparaît à la fois dans l'arborescence et sur la carte communale.
3. **Le terrain fonctionne sans réseau.** L'application est utilisable hors ligne par
   conception, pas en dégradé.

---

## 2. Acteurs et rôles

### 2.1 Rôles applicatifs (RBAC)

| Rôle | Portée | Droits |
|---|---|---|
| `ADMIN` | Plateforme entière | Tout : gestion des comptes, des services, des quotas, purge de la corbeille, consultation intégrale du journal d'activité |
| `DIRECTEUR` | Plateforme entière (lecture) + validation | Lecture de tout l'espace de la Direction, validation/publication de documents, export global, pas de gestion de comptes |
| `CHEF_SERVICE` | Son service | Tous droits sur l'arborescence de son service, gestion des membres du service, partage externe |
| `AGENT` | Dossiers qui lui sont partagés | Créer, téléverser, modifier, commenter dans les dossiers où il a le droit d'écriture |
| `LECTEUR` | Dossiers qui lui sont partagés | Consulter, prévisualiser, télécharger |
| `INVITE` | Lien de partage | Accès limité dans le temps à un dossier ou un fichier précis, sans compte permanent |

Le rôle est un **socle global** ; il est affiné par des **permissions par dossier**
(§ 4.4). La règle d'évaluation est décrite au § 6.3.

### 2.2 Services de la Direction (groupes livrés par défaut)

- Service de l'Urbanisme et de la Planification
- Service de l'Habitat et du Logement
- Service de l'Aménagement du Territoire
- Service du Cadastre et de la Topographie
- Service des Affaires Domaniales
- Secrétariat / Archives

Ces services sont modifiables par l'administrateur ; ils ne sont pas codés en dur.

---

## 3. Architecture système

### 3.1 Vue d'ensemble

```
                    ┌──────────────────────────────────────────┐
   Navigateur       │  Frontend React (PWA)                    │
   poste / mobile   │  • UI explorateur + carte Leaflet        │
                    │  • Service Worker (cache applicatif)     │
                    │  • IndexedDB chiffré (fichiers + queue)  │
                    └───────────────┬──────────────────────────┘
                                    │ HTTPS / JSON + JWT
                    ┌───────────────▼──────────────────────────┐
                    │  Nginx (TLS, fichiers statiques, proxy)  │
                    └───────────────┬──────────────────────────┘
                                    │
                    ┌───────────────▼──────────────────────────┐
                    │  Django REST Framework (Gunicorn)        │
                    │  accounts │ storage │ geo │ sharing      │
                    │  sync     │ audit   │ search             │
                    └──┬───────────┬───────────┬───────────────┘
                       │           │           │
          ┌────────────▼──┐  ┌─────▼──────┐  ┌─▼─────────────┐
          │ PostgreSQL 16 │  │  MinIO/S3  │  │ Redis         │
          │  + PostGIS    │  │  (blobs)   │  │ cache + broker│
          └───────────────┘  └────────────┘  └───┬───────────┘
                                                 │
                                          ┌──────▼────────┐
                                          │ Celery workers│
                                          │ • extraction  │
                                          │   métadonnées │
                                          │ • vignettes   │
                                          │ • conversions │
                                          │ • antivirus   │
                                          └───────────────┘
```

### 3.2 Choix techniques et justification

| Couche | Technologie | Pourquoi |
|---|---|---|
| API | Django 5 + DRF | Écosystème mature, admin intégré pour la Direction, GeoDjango natif |
| Base | PostgreSQL 16 + PostGIS 3.4 | Seule base relationnelle avec indexation spatiale de niveau production ; requêtes « documents dans ce quartier » |
| Objets | MinIO (S3-compatible) | Fichiers volumineux hors base, compatible S3 si migration cloud ultérieure, déployable sur serveur communal |
| Tâches | Celery + Redis | Extraction de métadonnées et conversions géospatiales sont trop lentes pour le cycle requête/réponse |
| Front | React 18 + Vite + TypeScript | Écosystème PWA/offline mature, TypeScript pour la fiabilité du modèle partagé |
| Carte | Leaflet + proj4 | Léger, fonctionne hors ligne avec tuiles mises en cache, pas de dépendance à une clé API payante |
| Hors ligne | Service Worker + IndexedDB (Dexie) + WebCrypto | Standard navigateur, pas d'installation, chiffrement local AES-GCM |
| Auth | JWT (access 15 min / refresh 7 j) + TOTP 2FA | Le JWT court survit aux coupures réseau ; le refresh permet la reconnexion silencieuse |
| Conteneurs | Docker Compose | Déploiement identique en local, sur serveur communal ou sur VPS |

### 3.3 Applications Django

| App | Responsabilité |
|---|---|
| `accounts` | Utilisateurs, services, rôles, 2FA, sessions, politique de mots de passe |
| `storage` | Dossiers, fichiers, versions, métadonnées, tags, corbeille, quotas |
| `geo` | Détection et extraction géospatiales, emprises, conversions, couches carto |
| `sharing` | Permissions par dossier/fichier, liens publics, invitations |
| `sync` | Delta de synchronisation, file d'opérations client, résolution de conflits |
| `audit` | Journal d'activité immuable, export |
| `search` | Recherche plein texte + filtres + recherche spatiale |
| `notifications` | Événements, notifications in-app et e-mail |

---

## 4. Modèle de données

Notation : `PK` clé primaire, `FK` clé étrangère, `U` unique, `I` indexé.
Toutes les tables portent `created_at`, `updated_at`.
Les identifiants exposés à l'API sont des **UUID v4** (jamais les `id` séquentiels) pour
éviter l'énumération et permettre la génération d'identifiants côté client hors ligne.

### 4.1 `accounts`

**`user`** (hérite de `AbstractBaseUser`)

| Champ | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `email` | citext | U, identifiant de connexion |
| `matricule` | varchar(32) | U, nullable — matricule agent communal |
| `first_name`, `last_name` | varchar(100) | |
| `role` | varchar(20) | ADMIN / DIRECTEUR / CHEF_SERVICE / AGENT / LECTEUR / INVITE |
| `service` | FK → `service` | nullable |
| `phone` | varchar(20) | nullable, pour notifications SMS ultérieures |
| `is_active` | bool | désactivation sans suppression (traçabilité conservée) |
| `totp_secret` | varchar(64) | nullable, chiffré au repos |
| `totp_enabled` | bool | |
| `storage_quota_bytes` | bigint | 0 = quota du service |
| `last_login_at`, `last_seen_at` | timestamptz | |
| `must_change_password` | bool | vrai à la création par l'admin |

**`service`** — `id`, `name` U, `code` U (ex. `CADASTRE`), `description`, `quota_bytes`, `root_folder` FK → `folder`.

**`device`** — appareils enregistrés pour la synchronisation : `id`, `user` FK, `label`
(« Tablette terrain 02 »), `platform`, `last_sync_at`, `sync_cursor`, `is_revoked`.

### 4.2 `storage` — arborescence

**`folder`**

| Champ | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `name` | varchar(255) | U avec (`parent`, `is_deleted=false`) |
| `parent` | FK → `folder` | null = racine |
| `path` | text | I — chemin matérialisé `/urbanisme/lotissements/2026/`, maintenu par trigger |
| `depth` | int | I |
| `owner` | FK → `user` | |
| `service` | FK → `service` | I — cloisonnement principal |
| `color`, `icon` | varchar | confort d'affichage |
| `is_deleted`, `deleted_at`, `deleted_by` | | corbeille |
| `size_bytes`, `file_count` | bigint | dénormalisés, recalculés en tâche de fond |

Le **chemin matérialisé** (`path`) est retenu plutôt qu'une table de fermeture : il rend
les requêtes « tout le sous-arbre » triviales (`WHERE path LIKE '/urbanisme/%'`), ce qui
compte pour le calcul de permissions héritées et pour le delta de synchronisation.

**`file`**

| Champ | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `name` | varchar(255) | U avec (`folder`, `is_deleted=false`) |
| `folder` | FK → `folder` | I |
| `owner` | FK → `user` | |
| `service` | FK → `service` | I |
| `current_version` | FK → `file_version` | |
| `mime_type` | varchar(150) | |
| `kind` | varchar(20) | I — `DOCUMENT`, `IMAGE`, `TABLEUR`, `VECTEUR`, `RASTER`, `CAO`, `AUTRE` |
| `size_bytes` | bigint | version courante |
| `description` | text | |
| `tags` | M2M → `tag` | |
| `is_deleted`, `deleted_at`, `deleted_by` | | corbeille |
| `is_locked`, `locked_by`, `locked_at` | | verrou d'édition optionnel |
| `search_vector` | tsvector | I GIN — nom + description + tags + texte extrait |

**`file_version`**

`id`, `file` FK, `version_number` int (U avec `file`), `storage_key` (clé objet S3/MinIO),
`size_bytes`, `checksum_sha256` (U partiel — déduplication), `mime_type`,
`uploaded_by` FK, `uploaded_at`, `comment` (motif de la modification),
`origin` (`WEB`, `SYNC_OFFLINE`, `IMPORT`), `client_id` (UUID généré hors ligne).

Le contenu binaire **n'est jamais supprimé** par une suppression logique ; seule la purge
administrative de la corbeille libère les objets.

**`tag`** — `id`, `name` U par service, `service` FK, `color`.

**`file_metadata`** — paires clé/valeur libres : `file` FK, `key`, `value`, `value_type`,
`source` (`AUTO` extraite, `MANUEL` saisie). Index sur (`key`, `value`).

Champs métier attendus par la Direction, pré-déclarés comme clés normalisées :
`reference_dossier`, `numero_parcelle`, `section_cadastrale`, `quartier`, `demandeur`,
`date_depot`, `date_decision`, `type_acte`, `statut_instruction`.

### 4.3 `geo`

**`geo_asset`** — un fichier reconnu comme géospatial

| Champ | Type | Notes |
|---|---|---|
| `file` | O2O → `file` | PK |
| `geo_format` | varchar(20) | SHP, GEOTIFF, DXF, DWG, KML, KMZ, GEOJSON, GPX |
| `srid_source` | int | code EPSG détecté (ex. 32628 pour UTM 28N) |
| `srid_declared` | int | corrigé manuellement si détection impossible |
| `extent` | `geometry(Polygon, 4326)` | I GIST — emprise en WGS84 |
| `centroid` | `geometry(Point, 4326)` | I GIST |
| `geometry_type` | varchar(20) | POINT / LINESTRING / POLYGON / RASTER / MIXED |
| `feature_count` | int | entités vectorielles |
| `raster_width`, `raster_height`, `pixel_size_x`, `pixel_size_y` | | rasters |
| `attributes_schema` | jsonb | colonnes de la table attributaire |
| `preview_key` | varchar | vignette PNG dans le stockage objet |
| `simplified_geojson` | jsonb | géométrie allégée pour l'affichage carte rapide |
| `extraction_status` | varchar(20) | PENDING / OK / PARTIAL / FAILED |
| `extraction_error` | text | |

**`geo_layer`** — couche de référence communale (limites de quartiers, réseau viaire,
zonage du plan d'urbanisme) : `id`, `name`, `service` FK, `source_file` FK nullable,
`style` jsonb, `z_index`, `is_public`, `min_zoom`, `max_zoom`.

**`conversion_job`** — `id`, `file` FK, `source_format`, `target_format`, `status`,
`result_file` FK nullable, `requested_by`, `error`.

### 4.4 `sharing`

**`permission`** — permission explicite sur un nœud

| Champ | Type |
|---|---|
| `id` | UUID |
| `folder` / `file` | FK, exactement un des deux non nul |
| `grantee_user` / `grantee_service` | FK, exactement un des deux non nul |
| `level` | `READ` / `COMMENT` / `WRITE` / `MANAGE` |
| `inherit` | bool — s'applique au sous-arbre |
| `granted_by` | FK → user |
| `expires_at` | timestamptz nullable |

**`share_link`** — `id`, `token` U (32 octets), `folder`/`file`, `level` (READ/WRITE),
`password_hash` nullable, `expires_at`, `max_downloads`, `download_count`,
`created_by`, `is_revoked`.

### 4.5 `sync`

**`sync_operation`** — opération produite hors ligne et rejouée au retour du réseau

| Champ | Type | Notes |
|---|---|---|
| `id` | UUID | généré par le client |
| `device` | FK → `device` | |
| `user` | FK → `user` | |
| `op_type` | varchar(30) | CREATE_FOLDER, RENAME, MOVE, UPLOAD_VERSION, DELETE, RESTORE, SET_METADATA |
| `target_type`, `target_id` | | UUID du nœud visé (généré côté client si créé hors ligne) |
| `payload` | jsonb | |
| `client_seq` | bigint | ordre local sur l'appareil |
| `base_version` | int | version connue du client — détection de conflit |
| `client_timestamp` | timestamptz | |
| `status` | varchar(20) | PENDING / APPLIED / CONFLICT / REJECTED |
| `conflict_resolution` | varchar(20) | SERVER_WINS / CLIENT_WINS / BOTH_KEPT / MANUAL |
| `applied_at`, `error` | | |

**`change_log`** — journal ordonné servant le delta descendant :
`seq` bigserial PK, `entity_type`, `entity_id`, `change_type`, `service` FK,
`folder_path` (pour filtrer par sous-arbre), `payload` jsonb, `created_at`.

Le client conserve `sync_cursor = dernier seq reçu` ; le delta est
`SELECT * FROM change_log WHERE seq > :cursor AND <visible par l'utilisateur> ORDER BY seq`.

### 4.6 `audit`

**`activity_log`** — `id`, `actor` FK (nullable si système), `action` (varchar indexé),
`target_type`, `target_id`, `target_path` (chemin figé au moment de l'action),
`ip_address` (inet), `user_agent`, `device` FK nullable, `metadata` jsonb, `created_at` I.

Table en **écriture seule** : aucune API de modification ou suppression n'est exposée ;
révocation du droit `DELETE`/`UPDATE` au rôle SQL applicatif. Partitionnée par mois.

Actions journalisées : `LOGIN`, `LOGIN_FAILED`, `LOGOUT`, `FILE_UPLOAD`,
`FILE_DOWNLOAD`, `FILE_VIEW`, `FILE_RENAME`, `FILE_MOVE`, `FILE_DELETE`,
`FILE_RESTORE`, `VERSION_RESTORE`, `FOLDER_*`, `PERMISSION_GRANT`,
`PERMISSION_REVOKE`, `SHARE_LINK_CREATE`, `SHARE_LINK_ACCESS`, `SYNC_CONFLICT`,
`USER_CREATE`, `USER_DISABLE`, `ROLE_CHANGE`, `TRASH_PURGE`.

### 4.7 `notifications`

`notification` — `id`, `recipient` FK, `type`, `title`, `body`, `target_type`,
`target_id`, `is_read`, `read_at`, `created_at`.
`notification_preference` — par utilisateur et par type : in-app, e-mail, aucun.

---

## 5. Spécification de l'API REST

Base : `/api/v1/`. Format JSON. Authentification `Authorization: Bearer <access_token>`.
Pagination par curseur (`?cursor=`, 50 éléments par défaut) — stable pendant la
synchronisation, contrairement à la pagination par offset.

### 5.1 Authentification

| Méthode | Chemin | Description |
|---|---|---|
| POST | `auth/login/` | email + mot de passe → `access`, `refresh`, ou `totp_required` |
| POST | `auth/login/totp/` | code TOTP + jeton intermédiaire |
| POST | `auth/refresh/` | rotation du refresh token |
| POST | `auth/logout/` | révocation du refresh |
| GET/PATCH | `auth/me/` | profil courant |
| POST | `auth/password/change/` | |
| POST | `auth/totp/setup/`, `auth/totp/confirm/`, `auth/totp/disable/` | |
| GET/POST/DELETE | `auth/devices/` | appareils synchronisés |

### 5.2 Arborescence

| Méthode | Chemin | Description |
|---|---|---|
| GET | `folders/` | racines visibles ; `?parent=<uuid>` pour un niveau |
| GET | `folders/{id}/` | détail + fil d'Ariane + permissions effectives |
| GET | `folders/{id}/children/` | dossiers et fichiers, triables, filtrables |
| POST | `folders/` | `{name, parent, service}` |
| PATCH | `folders/{id}/` | renommer, changer couleur |
| POST | `folders/{id}/move/` | `{target_parent}` |
| POST | `folders/{id}/copy/` | copie récursive (asynchrone au-delà de 100 fichiers) |
| DELETE | `folders/{id}/` | → corbeille |
| GET | `folders/{id}/download/` | archive ZIP en flux |
| GET | `folders/tree/` | arbre complet allégé, pour le cache hors ligne |

### 5.3 Fichiers

| Méthode | Chemin | Description |
|---|---|---|
| GET | `files/{id}/` | métadonnées complètes |
| POST | `files/upload/init/` | ouvre un téléversement fragmenté → `upload_id`, taille de fragment |
| PUT | `files/upload/{upload_id}/part/{n}/` | fragment (5 Mo par défaut) |
| POST | `files/upload/{upload_id}/complete/` | assemble, vérifie le SHA-256, crée la version |
| POST | `files/upload/simple/` | multipart direct, fichiers < 10 Mo |
| PATCH | `files/{id}/` | renommer, description, tags |
| POST | `files/{id}/move/` | |
| DELETE | `files/{id}/` | → corbeille |
| GET | `files/{id}/download/` | redirection 302 vers URL pré-signée, TTL 5 min |
| GET | `files/{id}/preview/` | vignette ou rendu PDF/image |
| GET | `files/{id}/versions/` | historique |
| POST | `files/{id}/versions/{n}/restore/` | crée une nouvelle version à partir d'une ancienne |
| GET/POST | `files/{id}/comments/` | |
| GET/PUT | `files/{id}/metadata/` | champs métier |
| POST | `files/{id}/lock/`, `unlock/` | verrou d'édition |

Le téléversement fragmenté est obligatoire au-delà de 10 Mo : sur une liaison instable,
seul le fragment perdu est réémis. Chaque fragment est acquitté et l'assemblage est
idempotent — un même `upload_id` rejoué ne crée pas de doublon.

### 5.4 Géospatial

| Méthode | Chemin | Description |
|---|---|---|
| GET | `geo/assets/` | fichiers géoréférencés ; filtres `?bbox=`, `?format=`, `?srid=` |
| GET | `geo/assets/{file_id}/` | métadonnées géospatiales |
| GET | `geo/assets/{file_id}/geojson/` | géométrie simplifiée pour la carte |
| PATCH | `geo/assets/{file_id}/` | corriger le SRID déclaré |
| POST | `geo/assets/{file_id}/convert/` | `{target_format, target_srid}` → tâche |
| GET | `geo/conversions/{job_id}/` | état de la conversion |
| GET | `geo/layers/` | couches de référence communales |
| GET | `geo/search/?bbox=` ou `?point=&radius=` | **tous** les fichiers dont l'emprise intersecte |

### 5.5 Partage, recherche, corbeille, journal

| Méthode | Chemin | Description |
|---|---|---|
| GET/POST/DELETE | `permissions/` | `?folder=` ou `?file=` |
| GET/POST | `share-links/` | création de lien public |
| POST | `share-links/{token}/access/` | accès invité (mot de passe éventuel) |
| GET | `search/?q=&kind=&tag=&service=&date_from=&date_to=&bbox=` | recherche unifiée |
| GET | `search/suggest/?q=` | autocomplétion |
| GET | `trash/` | corbeille de l'utilisateur / du service |
| POST | `trash/{id}/restore/` | |
| DELETE | `trash/{id}/` | purge définitive (ADMIN) |
| GET | `activity/` | journal filtrable, export CSV |
| GET | `notifications/`, POST `notifications/{id}/read/` | |

### 5.6 Synchronisation

| Méthode | Chemin | Description |
|---|---|---|
| GET | `sync/delta/?cursor=<seq>&scope=<folder_id>` | changements descendants + nouveau curseur |
| POST | `sync/operations/` | lot d'opérations produites hors ligne |
| GET | `sync/operations/{id}/` | état d'une opération |
| GET | `sync/conflicts/` | conflits à arbitrer |
| POST | `sync/conflicts/{id}/resolve/` | `{resolution}` |
| GET | `sync/manifest/?scope=` | liste `{id, version, checksum, size}` pour vérifier le cache local |

### 5.7 Codes d'erreur métier

| Code | Signification |
|---|---|
| `PERMISSION_DENIED` | droit insuffisant sur le nœud |
| `QUOTA_EXCEEDED` | quota du service atteint |
| `NAME_CONFLICT` | nom déjà utilisé dans le dossier |
| `VERSION_CONFLICT` | `base_version` obsolète — conflit de synchronisation |
| `FILE_LOCKED` | fichier verrouillé par un autre agent |
| `UNSUPPORTED_FORMAT` | conversion géospatiale impossible |
| `CHECKSUM_MISMATCH` | téléversement corrompu, à réémettre |
| `SHARE_LINK_EXPIRED` | lien public expiré ou révoqué |

---

## 6. Règles métier

### 6.1 Cycle de vie d'un fichier

```
téléversement → analyse asynchrone → disponible
     │                │
     │                ├─ calcul SHA-256, déduplication
     │                ├─ détection du type et du format
     │                ├─ extraction texte (PDF, DOCX, XLSX) → index plein texte
     │                ├─ si géospatial → emprise, SRID, vignette, GeoJSON simplifié
     │                └─ génération de vignette (image, PDF, carte)
     │
modification → nouvelle version (l'ancienne reste)
     │
suppression → corbeille (30 j par défaut) → purge admin → objets libérés
```

### 6.2 Versionnement

- Toute écriture sur un fichier existant crée une version, jamais un écrasement.
- La déduplication par SHA-256 évite de stocker deux fois un contenu identique : si le
  checksum existe déjà, la version pointe vers le même objet.
- Rétention par défaut : 20 versions ou 2 ans, la plus généreuse des deux ; configurable
  par service. La version courante n'est jamais purgée.

### 6.3 Évaluation des permissions

Ordre d'évaluation, premier verdict trouvé :

1. `ADMIN` → `MANAGE`.
2. Permission explicite **sur le nœud lui-même** (fichier ou dossier).
3. Permission héritée du plus proche ancêtre portant `inherit = true` — le niveau le plus
   élevé l'emporte entre une permission utilisateur et une permission de service.
4. Appartenance au service propriétaire du nœud : `CHEF_SERVICE` → `MANAGE`,
   `AGENT` → `WRITE`, `LECTEUR` → `READ`.
5. `DIRECTEUR` → `READ` sur tout.
6. Sinon : refus, et le nœud est **invisible** (404, jamais 403 — on ne révèle pas
   l'existence d'un dossier non autorisé).

Le résultat est mis en cache Redis par (`user`, `folder.path`) et invalidé à toute
modification de permission ou déplacement de nœud.

### 6.4 Quotas

Quota par service, hérité par les agents. Le calcul porte sur la somme des tailles de
**toutes** les versions non purgées. Un téléversement qui dépasserait le quota est refusé
à l'étape `upload/init/`, avant tout transfert — essentiel sur liaison lente.

---

## 7. Support géospatial

### 7.1 Formats et traitement

| Format | Extensions | Lecture | Emprise | Aperçu | Conversion |
|---|---|---|---|---|---|
| Shapefile | `.shp` + `.dbf`/`.shx`/`.prj` (ou `.zip`) | GDAL/OGR | oui | oui | → GeoJSON, KML, GPKG |
| GeoJSON | `.geojson`, `.json` | natif | oui | oui | → SHP, KML, GPKG |
| GeoTIFF | `.tif`, `.tiff` | GDAL | oui | vignette | → COG, PNG géoréférencé |
| KML/KMZ | `.kml`, `.kmz` | GDAL | oui | oui | → GeoJSON, SHP |
| GPX | `.gpx` | GDAL | oui | oui | → GeoJSON, SHP |
| DXF | `.dxf` | GDAL + ezdxf | oui si géoréférencé | oui | → GeoJSON, SHP |
| DWG | `.dwg` | ODA File Converter → DXF | idem | idem | → DXF puis vecteur |
| GeoPackage | `.gpkg` | GDAL | oui | oui | → SHP, GeoJSON |

**Cas du Shapefile.** Un Shapefile est un jeu de 3 à 8 fichiers. La plateforme le traite
comme une **entité unique** : le téléversement d'un `.zip` contenant un `.shp` crée un
seul enregistrement `file` de type `VECTEUR`, et le dépôt des fichiers séparés dans un
même dossier déclenche leur regroupement automatique. Un `.shp` orphelin (sans `.dbf`)
est marqué `extraction_status = PARTIAL` avec un avertissement explicite.

### 7.2 Systèmes de projection

Le SRID est détecté dans l'ordre : fichier `.prj` → en-tête du format → métadonnées
GDAL → à défaut, demande explicite à l'agent au moment du dépôt. **Aucune projection
n'est devinée silencieusement** : une emprise fausse sur une carte communale est pire
qu'une emprise absente.

Projections attendues dans le contexte de la Direction :

- `EPSG:4326` — WGS84 géographique (GPS, données d'échange)
- `EPSG:32628` / `EPSG:32629` — UTM zones 28N / 29N, WGS84 (levés locaux)
- Systèmes nationaux, ajoutés par l'administrateur dans la table `spatial_ref_sys` de PostGIS

L'emprise est **toujours** reprojetée en 4326 pour le stockage, ce qui rend comparables des
fichiers déposés dans des projections différentes.

### 7.3 Carte

Fond de plan OpenStreetMap en ligne, **avec cache local des tuiles** pour la zone
communale afin que la carte reste utilisable hors ligne. Superposition : couches de
référence (`geo_layer`) + emprises des fichiers du dossier courant + géométries
simplifiées à la demande. Au-delà de 5 000 entités, la couche est servie en tuiles
vectorielles générées par PostGIS (`ST_AsMVT`).

---

## 8. Fonctionnement hors ligne

### 8.1 Principe

L'application est une **PWA** installable. Trois niveaux de cache :

1. **Coquille applicative** — HTML/JS/CSS, précachés par le Service Worker, stratégie
   *stale-while-revalidate*.
2. **Métadonnées** — arborescence, permissions, métadonnées des fichiers du périmètre
   choisi, dans IndexedDB. Rafraîchies par delta.
3. **Contenus** — fichiers explicitement marqués « disponible hors ligne » par l'agent,
   ou dossiers entiers marqués avant une sortie terrain. Stockés chiffrés.

### 8.2 Chiffrement local

Clé AES-256-GCM dérivée par PBKDF2 (310 000 itérations) du mot de passe de l'agent,
conservée en mémoire pendant la session et jamais persistée. Les blobs IndexedDB sont
chiffrés individuellement. À la révocation d'un appareil, le client purge son stockage à
la première reconnexion ; les données déjà présentes restent illisibles sans le mot de passe.

### 8.3 File d'opérations

Toute action hors ligne est écrite dans une file locale ordonnée (`client_seq`) **avant**
d'être appliquée à l'état local optimiste. Les identifiants des nœuds créés hors ligne
sont des UUID générés côté client : ils sont acceptés tels quels par le serveur, ce qui
évite toute réécriture d'identifiants à la synchronisation.

Le retour du réseau déclenche : envoi de la file → réception du delta → réconciliation.

### 8.4 Résolution des conflits

| Situation | Règle |
|---|---|
| Même fichier modifié par deux agents | Les deux versions sont conservées. La version serveur reste courante ; la version hors ligne est ajoutée à l'historique et signalée par une notification à son auteur. Aucune perte, jamais. |
| Fichier supprimé côté serveur, modifié hors ligne | Le fichier est restauré avec la version hors ligne et marqué « conflit », à arbitrer par le chef de service. |
| Renommage concurrent | Horodatage serveur le plus récent l'emporte ; l'autre nom est conservé dans le journal. |
| Déplacement vers un dossier supprimé | L'opération est rejetée, l'élément est placé dans un dossier « Éléments non classés » de l'agent. |
| Création avec un nom déjà pris | Suffixe automatique ` (2)`, sans échec. |
| Permission perdue entre-temps | Opération rejetée, contenu local conservé et signalé à l'agent. |

Le principe directeur : **une synchronisation ne détruit jamais un travail de terrain.**
En cas de doute, on garde les deux et on demande.

### 8.5 Limites assumées

Le hors ligne couvre le périmètre marqué par l'agent, pas la totalité de la base : un
serveur communal de plusieurs centaines de Go ne tient pas sur une tablette. L'interface
affiche explicitement ce qui est disponible hors ligne et la place occupée.

---

## 9. Sécurité

| Domaine | Mesure |
|---|---|
| Transport | HTTPS obligatoire, TLS 1.2+, HSTS, redirection 80 → 443 |
| Repos | Chiffrement du volume PostgreSQL et du bucket MinIO (SSE-S3) |
| Local | AES-256-GCM sur IndexedDB (§ 8.2) |
| Mots de passe | Argon2id, minimum 12 caractères, contrôle contre les listes de mots de passe compromis, expiration 180 j pour ADMIN et CHEF_SERVICE |
| 2FA | TOTP obligatoire pour ADMIN et DIRECTEUR, optionnel pour les autres |
| Sessions | Access 15 min, refresh 7 j avec rotation et détection de réutilisation |
| Anti-force brute | 5 échecs → verrouillage progressif ; limitation de débit par IP et par compte |
| Téléversement | Vérification du type réel (magic bytes) et non de l'extension, analyse antivirus ClamAV, taille max 2 Go |
| Accès aux objets | URL pré-signées à TTL court, jamais d'accès direct au bucket |
| Injections | ORM exclusivement, aucune concaténation SQL ; échappement systématique côté React |
| CSRF/CORS | Origines déclarées explicitement ; JWT en en-tête, pas en cookie |
| En-têtes | CSP stricte, `X-Content-Type-Options`, `Referrer-Policy: same-origin` |
| Sauvegardes | `pg_dump` quotidien chiffré + réplication du bucket ; test de restauration mensuel obligatoire |
| Traçabilité | Journal immuable (§ 4.6), conservation 5 ans |

---

## 10. Performance

| Exigence | Cible | Moyen |
|---|---|---|
| Chargement d'une page | < 2 s | Découpage du bundle, précache SW, pagination par curseur |
| Listing d'un dossier de 1 000 éléments | < 500 ms | Index composite (`folder`, `is_deleted`, `name`), dénormalisation des compteurs |
| Téléversement de 500 Mo | Reprise après coupure | Fragments de 5 Mo, reprise au fragment |
| Affichage carte, 10 000 entités | < 1,5 s | Géométries simplifiées + tuiles vectorielles MVT |
| Recherche plein texte | < 300 ms | `tsvector` GIN, dictionnaire français |
| Recherche spatiale | < 300 ms | Index GIST sur `extent` |
| Synchronisation d'un delta | < 5 s pour 500 changements | Curseur `seq`, lots de 200 |

---

## 11. Environnements et déploiement

| Environnement | Usage | Composition |
|---|---|---|
| Développement | Poste de Billy | Docker Compose complet, données de démonstration |
| Recette | Validation par la Direction | Même image, base anonymisée |
| Production | Serveur communal ou VPS | Compose + Nginx + TLS + sauvegardes planifiées |

Variables d'environnement essentielles : `DJANGO_SECRET_KEY`, `DATABASE_URL`,
`S3_ENDPOINT`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`/`S3_BUCKET`, `REDIS_URL`,
`ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `TRASH_RETENTION_DAYS`,
`MAX_UPLOAD_SIZE_MB`, `DEFAULT_SERVICE_QUOTA_GB`.

---

## 12. Livrables et suite

Ce document couvre le livrable n° 1 du cahier des charges (spécifications techniques
détaillées : schéma de base de données, architecture système, spécification d'API).
Les livrables suivants s'y adossent : maquettes, application web, module hors ligne,
documentation, plan de déploiement.

### Points restant à trancher avec la Direction

1. Nombre d'agents au lancement et volumétrie initiale des archives à reprendre.
2. Hébergement : serveur à la mairie (autonomie, contrainte d'électricité et de sauvegarde)
   ou VPS (disponibilité, dépendance à la liaison internet).
3. Reprise de l'existant : y a-t-il des archives papier à numériser, ou un fonds numérique
   déjà constitué à importer ?
4. Systèmes de projection officiellement utilisés par le service du Cadastre.
5. Nécessité d'une application mobile native en plus de la PWA.
