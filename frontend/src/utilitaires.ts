import type { Kind } from "./types";

export function formaterTaille(octets: number): string {
  if (!octets) return "—";
  const unites = ["o", "Ko", "Mo", "Go", "To"];
  let valeur = octets;
  let index = 0;
  while (valeur >= 1024 && index < unites.length - 1) {
    valeur /= 1024;
    index += 1;
  }
  return `${valeur.toFixed(index === 0 ? 0 : 1).replace(".", ",")} ${unites[index]}`;
}

export function formaterDate(iso: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const ICONES: Record<Kind, string> = {
  DOCUMENT: "📄",
  CROQUIS: "✏️",
  IMAGE: "🖼️",
  TABLEUR: "📊",
  VECTEUR: "🗺️",
  RASTER: "🛰️",
  CAO: "📐",
  ARCHIVE: "🗜️",
  AUTRE: "📎",
};

export function iconeType(kind: Kind): string {
  return ICONES[kind] ?? ICONES.AUTRE;
}

export const LIBELLES_TYPE: Record<Kind, string> = {
  DOCUMENT: "Document",
  CROQUIS: "Croquis",
  IMAGE: "Image",
  TABLEUR: "Tableur",
  VECTEUR: "Données vectorielles",
  RASTER: "Image satellite / raster",
  CAO: "Plan CAO",
  ARCHIVE: "Archive",
  AUTRE: "Autre",
};

export const LIBELLES_NIVEAU: Record<string, string> = {
  READ: "Consultation",
  COMMENT: "Commentaire",
  WRITE: "Modification",
  MANAGE: "Gestion",
};

export function peutEcrire(niveau: string | null): boolean {
  return niveau === "WRITE" || niveau === "MANAGE";
}

export function peutGerer(niveau: string | null): boolean {
  return niveau === "MANAGE";
}

export const LIBELLES_ROLE: Record<string, string> = {
  ADMIN: "Administrateur",
  DIRECTEUR: "Directeur",
  CHEF_SERVICE: "Chef de service",
  AGENT: "Agent",
  LECTEUR: "Lecteur",
  INVITE: "Invité",
};

/** Ce que chaque rôle permet, en une phrase — affiché à la création d'un compte. */
export const EXPLICATIONS_ROLE: Record<string, string> = {
  ADMIN: "Tous les droits, y compris la gestion des comptes et des quotas.",
  DIRECTEUR: "Lecture de tous les espaces de la Direction, sans droit de modification.",
  CHEF_SERVICE: "Tous droits sur l'espace de son service et sur ses membres.",
  AGENT: "Dépose et modifie des documents dans les dossiers de son service.",
  LECTEUR: "Consulte et télécharge, sans rien modifier.",
  INVITE: "Accès limité et temporaire à un dossier partagé.",
};

export function pourcentage(partie: number, total: number): number {
  if (!total) return 0;
  return Math.min(100, Math.round((partie / total) * 100));
}
