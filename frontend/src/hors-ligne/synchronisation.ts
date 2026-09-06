/**
 * Moteur de synchronisation côté client.
 *
 * Ordre imposé : on **envoie d'abord** la file locale, puis on récupère le
 * delta. L'inverse écraserait le travail de terrain par l'état serveur avant
 * même de l'avoir transmis.
 */

import { api, HorsLigne } from "../api/client";
import { chiffrer, dechiffrer } from "./chiffrement";
import { base, ecrireReglage, lireReglage } from "./base";
import { marquer, operationsEnAttente, purgerAppliquees } from "./file";
import type { Dossier, Fichier } from "../types";

export interface EtatSynchronisation {
  enCours: boolean;
  derniereSync: string | null;
  operationsEnAttente: number;
  conflits: number;
  message: string;
}

interface ResultatOperation {
  id: string;
  status: "APPLIED" | "CONFLICT" | "REJECTED" | "PENDING";
  error?: string;
  resolution?: string;
}

interface Changement {
  seq: number;
  entity_type: "FOLDER" | "FILE";
  entity_id: string;
  change_type: string;
  folder_path: string;
  payload: Record<string, unknown>;
}

const CLE_CURSEUR = "curseur_sync";
const CLE_APPAREIL = "appareil_id";
const CLE_DERNIERE = "derniere_sync";

export async function identifiantAppareil(): Promise<string | null> {
  return lireReglage<string | null>(CLE_APPAREIL, null);
}

export async function enregistrerAppareil(libelle: string): Promise<string> {
  const existant = await identifiantAppareil();
  if (existant) return existant;
  const appareil = await api.post<{ id: string }>("/auth/devices/", {
    label: libelle,
    platform: navigator.platform || "web",
  });
  await ecrireReglage(CLE_APPAREIL, appareil.id);
  return appareil.id;
}

async function envoyerFile(appareil: string): Promise<{ conflits: number; rejets: number }> {
  const enAttente = await operationsEnAttente();
  if (enAttente.length === 0) return { conflits: 0, rejets: 0 };

  const reponse = await api.post<{ resultats: ResultatOperation[] }>("/sync/operations/", {
    device: appareil,
    operations: enAttente.map((operation) => ({
      id: operation.id,
      op_type: operation.op_type,
      target_type: operation.target_type,
      target_id: operation.target_id,
      payload: operation.payload,
      client_seq: operation.client_seq,
      base_version: operation.base_version,
      client_timestamp: operation.client_timestamp,
    })),
  });

  let conflits = 0;
  let rejets = 0;
  for (const resultat of reponse.resultats) {
    if (resultat.status === "APPLIED") {
      await marquer(resultat.id, "appliquee");
    } else if (resultat.status === "CONFLICT") {
      conflits += 1;
      await marquer(resultat.id, "conflit", resultat.resolution);
    } else {
      rejets += 1;
      await marquer(resultat.id, "rejetee", resultat.error);
    }
  }
  await purgerAppliquees();
  return { conflits, rejets };
}

async function appliquerDelta(appareil: string): Promise<number> {
  let curseur = await lireReglage<number>(CLE_CURSEUR, 0);
  let recus = 0;
  // On boucle : un appareil resté trois semaines au bureau rattrape en
  // plusieurs lots, sans jamais charger la base entière.
  for (let tour = 0; tour < 50; tour += 1) {
    const reponse = await api.get<{
      cursor: number;
      reste: boolean;
      changements: Changement[];
    }>(`/sync/delta/?cursor=${curseur}&device=${appareil}`);

    for (const changement of reponse.changements) {
      if (changement.change_type === "DELETED") {
        if (changement.entity_type === "FOLDER") await base.dossiers.delete(changement.entity_id);
        else {
          await base.fichiers.delete(changement.entity_id);
          await base.contenus.delete(changement.entity_id);
        }
      }
      recus += 1;
    }
    curseur = reponse.cursor;
    await ecrireReglage(CLE_CURSEUR, curseur);
    if (!reponse.reste) break;
  }
  return recus;
}

/** Recharge l'arborescence complète dans le cache local. */
export async function rafraichirArborescence(): Promise<void> {
  const dossiers = await api.get<Dossier[]>("/folders/tree/");
  await base.dossiers.bulkPut(dossiers);
}

export async function synchroniser(
  surEtat?: (message: string) => void
): Promise<EtatSynchronisation> {
  const appareil = await identifiantAppareil();
  if (!appareil) {
    return {
      enCours: false,
      derniereSync: await lireReglage<string | null>(CLE_DERNIERE, null),
      operationsEnAttente: await base.operations.where("etat").equals("en_attente").count(),
      conflits: 0,
      message: "Appareil non enregistré.",
    };
  }

  try {
    surEtat?.("Envoi des modifications hors ligne…");
    const { conflits, rejets } = await envoyerFile(appareil);

    surEtat?.("Réception des changements…");
    const recus = await appliquerDelta(appareil);

    surEtat?.("Mise à jour de l'arborescence…");
    await rafraichirArborescence();

    const maintenant = new Date().toISOString();
    await ecrireReglage(CLE_DERNIERE, maintenant);

    const parties = [`${recus} changement(s) reçu(s)`];
    if (conflits) parties.push(`${conflits} conflit(s) à arbitrer`);
    if (rejets) parties.push(`${rejets} opération(s) refusée(s)`);

    return {
      enCours: false,
      derniereSync: maintenant,
      operationsEnAttente: await base.operations.where("etat").equals("en_attente").count(),
      conflits,
      message: parties.join(" — "),
    };
  } catch (erreur) {
    if (erreur instanceof HorsLigne) {
      return {
        enCours: false,
        derniereSync: await lireReglage<string | null>(CLE_DERNIERE, null),
        operationsEnAttente: await base.operations.where("etat").equals("en_attente").count(),
        conflits: 0,
        message: "Hors ligne — la synchronisation reprendra au retour du réseau.",
      };
    }
    throw erreur;
  }
}

/** Marque un fichier pour une consultation hors ligne (contenu chiffré). */
export async function rendreDisponibleHorsLigne(fichier: Fichier): Promise<void> {
  const reponse = await fetch(`${api.base}/files/${fichier.id}/download/`, {
    headers: { Authorization: `Bearer ${localStorage.getItem("dcuhat.acces") ?? ""}` },
  });
  const typeContenu = reponse.headers.get("Content-Type") ?? "";
  let donnees: ArrayBuffer;
  if (typeContenu.includes("application/json")) {
    // Stockage objet : l'API renvoie une URL pré-signée.
    const { url } = (await reponse.json()) as { url: string };
    donnees = await (await fetch(url)).arrayBuffer();
  } else {
    donnees = await reponse.arrayBuffer();
  }

  await base.contenus.put({
    fichier_id: fichier.id,
    version: fichier.version_courante,
    checksum: "",
    taille: donnees.byteLength,
    mime: fichier.mime_type,
    blob_chiffre: await chiffrer(donnees),
    enregistre_le: new Date().toISOString(),
  });
  await base.fichiers.put(fichier);
}

export async function retirerDuCache(fichierId: string): Promise<void> {
  await base.contenus.delete(fichierId);
}

export async function lireContenuLocal(fichierId: string): Promise<Blob | null> {
  const contenu = await base.contenus.get(fichierId);
  if (!contenu) return null;
  const clair = await dechiffrer(contenu.blob_chiffre);
  return new Blob([clair], { type: contenu.mime });
}
