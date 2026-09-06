/**
 * Cache local (IndexedDB).
 *
 * Trois niveaux, conformément à la spécification §8.1 :
 *  - `dossiers` / `fichiers` : les métadonnées du périmètre synchronisé ;
 *  - `contenus` : les blobs chiffrés des fichiers marqués « disponible hors
 *    ligne » — jamais l'intégralité de la base, qui ne tiendrait pas ;
 *  - `operations` : la file des actions produites sans réseau.
 */

import Dexie, { type Table } from "dexie";

import type { Dossier, Fichier, OperationLocale } from "../types";

export interface ContenuLocal {
  fichier_id: string;
  version: number;
  checksum: string;
  taille: number;
  mime: string;
  blob_chiffre: ArrayBuffer;
  enregistre_le: string;
}

export interface Reglage {
  cle: string;
  valeur: unknown;
}

class BaseDCUHAT extends Dexie {
  dossiers!: Table<Dossier, string>;
  fichiers!: Table<Fichier, string>;
  contenus!: Table<ContenuLocal, string>;
  operations!: Table<OperationLocale, string>;
  reglages!: Table<Reglage, string>;

  constructor() {
    super("dcuhat");
    this.version(1).stores({
      dossiers: "id, parent, path, service",
      fichiers: "id, folder, name, kind, updated_at",
      contenus: "fichier_id, checksum",
      operations: "id, client_seq, etat",
      reglages: "cle",
    });
  }
}

export const base = new BaseDCUHAT();

export async function lireReglage<T>(cle: string, defaut: T): Promise<T> {
  const entree = await base.reglages.get(cle);
  return entree ? (entree.valeur as T) : defaut;
}

export async function ecrireReglage(cle: string, valeur: unknown): Promise<void> {
  await base.reglages.put({ cle, valeur });
}

export async function prochainSeq(): Promise<number> {
  const dernier = await base.operations.orderBy("client_seq").last();
  return (dernier?.client_seq ?? 0) + 1;
}

export async function viderCacheLocal(): Promise<void> {
  await Promise.all([
    base.dossiers.clear(),
    base.fichiers.clear(),
    base.contenus.clear(),
    base.operations.clear(),
    base.reglages.clear(),
  ]);
}

/** Place occupée par les contenus mis à disposition hors ligne. */
export async function placeOccupee(): Promise<number> {
  let total = 0;
  await base.contenus.each((contenu) => {
    total += contenu.taille;
  });
  return total;
}
