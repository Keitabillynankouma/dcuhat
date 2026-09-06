/**
 * File d'opérations hors ligne.
 *
 * Toute action est écrite dans la file **avant** d'être appliquée à l'état
 * local : si l'onglet est fermé au mauvais moment, l'intention de l'agent est
 * déjà enregistrée. Les identifiants des éléments créés hors ligne sont des
 * UUID générés ici et acceptés tels quels par le serveur — aucune réécriture
 * d'identifiant n'est nécessaire à la synchronisation.
 */

import { base, prochainSeq } from "./base";
import type { OperationLocale, TypeOperation } from "../types";

export function nouvelIdentifiant(): string {
  return crypto.randomUUID();
}

export async function empiler(
  op_type: TypeOperation,
  target_type: "FOLDER" | "FILE",
  target_id: string,
  payload: Record<string, unknown> = {},
  base_version: number | null = null
): Promise<OperationLocale> {
  const operation: OperationLocale = {
    id: nouvelIdentifiant(),
    op_type,
    target_type,
    target_id,
    payload,
    client_seq: await prochainSeq(),
    base_version,
    client_timestamp: new Date().toISOString(),
    etat: "en_attente",
  };
  await base.operations.add(operation);
  return operation;
}

export async function operationsEnAttente(): Promise<OperationLocale[]> {
  return base.operations.where("etat").equals("en_attente").sortBy("client_seq");
}

export async function nombreEnAttente(): Promise<number> {
  return base.operations.where("etat").equals("en_attente").count();
}

export async function marquer(
  id: string,
  etat: OperationLocale["etat"],
  message?: string
): Promise<void> {
  await base.operations.update(id, { etat, message });
}

export async function purgerAppliquees(): Promise<void> {
  await base.operations.where("etat").equals("appliquee").delete();
}

/** Convertit un blob en base64 pour le transport JSON des opérations. */
export async function enBase64(donnees: Blob | ArrayBuffer): Promise<string> {
  const tampon = donnees instanceof Blob ? await donnees.arrayBuffer() : donnees;
  const octets = new Uint8Array(tampon);
  let binaire = "";
  const PAS = 0x8000;
  for (let index = 0; index < octets.length; index += PAS) {
    binaire += String.fromCharCode(...octets.subarray(index, index + PAS));
  }
  return btoa(binaire);
}
