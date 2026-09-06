import type { Polygon, Point } from "geojson";

export type Role = "ADMIN" | "DIRECTEUR" | "CHEF_SERVICE" | "AGENT" | "LECTEUR" | "INVITE";
export type Niveau = "READ" | "COMMENT" | "WRITE" | "MANAGE" | null;

export interface Utilisateur {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  nom_complet: string;
  role: Role;
  service: string | null;
  service_nom?: string;
  fonction: string;
  must_change_password: boolean;
  totp_enabled: boolean;
  is_active?: boolean;
  created_at?: string;
  last_seen_at?: string | null;
}

export interface Dossier {
  id: string;
  name: string;
  parent: string | null;
  path: string;
  depth: number;
  service: string | null;
  service_nom?: string;
  description: string;
  size_bytes: number;
  file_count: number;
  is_deleted: boolean;
  deleted_at?: string | null;
  updated_at: string;
  niveau: Niveau;
  type: "dossier";
}

export type Kind =
  | "DOCUMENT" | "CROQUIS" | "IMAGE" | "TABLEUR" | "VECTEUR"
  | "RASTER" | "CAO" | "ARCHIVE" | "AUTRE";

export interface Fichier {
  id: string;
  name: string;
  folder: string;
  chemin: string;
  owner_nom: string;
  mime_type: string;
  kind: Kind;
  size_bytes: number;
  description: string;
  tags: { id: string; name: string; color: string }[];
  version_courante: number;
  est_geospatial: boolean;
  is_locked: boolean;
  is_deleted: boolean;
  deleted_at?: string | null;
  updated_at: string;
  niveau: Niveau;
  type: "fichier";
}

export interface FilAriane {
  id: string;
  name: string;
  path: string;
}

export interface ContenuDossier {
  dossier: Dossier;
  fil_ariane: FilAriane[];
  dossiers: Dossier[];
  fichiers: Fichier[];
}

export interface GeoAsset {
  file: string;
  fichier_nom: string;
  geo_format: string;
  srid_source: number | null;
  srid_declared: number | null;
  srid_effectif: number | null;
  emprise: Polygon | null;
  centre: Point | null;
  geometry_type: string;
  feature_count: number | null;
  extraction_status: "PENDING" | "OK" | "PARTIAL" | "FAILED";
  extraction_error: string;
}

export interface Version {
  id: string;
  version_number: number;
  size_bytes: number;
  checksum_sha256: string;
  auteur: string;
  comment: string;
  origin: string;
  is_conflict_copy: boolean;
  created_at: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  target_type: string;
  target_id: string;
  is_read: boolean;
  created_at: string;
}

export interface EntreeJournal {
  id: string;
  acteur_nom: string;
  action: string;
  action_libelle: string;
  target_path: string;
  ip_address: string | null;
  created_at: string;
}

export type TypeOperation =
  | "CREATE_FOLDER" | "RENAME" | "MOVE" | "UPLOAD_VERSION" | "DELETE" | "RESTORE" | "SET_METADATA";

export interface OperationLocale {
  id: string;
  op_type: TypeOperation;
  target_type: "FOLDER" | "FILE";
  target_id: string;
  payload: Record<string, unknown>;
  client_seq: number;
  base_version: number | null;
  client_timestamp: string;
  etat: "en_attente" | "envoyee" | "appliquee" | "conflit" | "rejetee";
  message?: string;
}

export interface ServiceComplet {
  id: string;
  name: string;
  code: string;
  description: string;
  quota_bytes: number;
  quota_effectif: number;
  usage_octets: number;
  nombre_agents: number;
  root_folder: string | null;
  is_active: boolean;
}

export interface Statistiques {
  agents: {
    total: number;
    actifs: number;
    par_role: { role: Role; nombre: number }[];
  };
  services: number;
  dossiers: number;
  fichiers: {
    total: number;
    geospatiaux: number;
    corbeille: number;
    par_type: { kind: Kind; nombre: number }[];
  };
  stockage_octets: number;
  activite_7_jours: number;
  conflits_ouverts: number;
}

export interface PageResultats<T> {
  next: string | null;
  previous: string | null;
  results: T[];
}
