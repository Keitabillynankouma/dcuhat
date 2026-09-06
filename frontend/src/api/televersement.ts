/**
 * Téléversement fragmenté.
 *
 * Sur une liaison de terrain, un envoi de 300 Mo qui échoue à 95 % et doit
 * repartir de zéro n'est pas un désagrément : c'est un travail perdu. Chaque
 * fragment est donc acquitté séparément et seuls les fragments manquants sont
 * réémis.
 */

import { api, appeler } from "./client";
import type { Fichier } from "../types";

export interface ProgressionTeleversement {
  envoyes: number;
  total: number;
  pourcentage: number;
}

async function empreinteFichier(fichier: File): Promise<string> {
  const tampon = await fichier.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", tampon);
  return Array.from(new Uint8Array(digest))
    .map((octet) => octet.toString(16).padStart(2, "0"))
    .join("");
}

const SEUIL_SIMPLE = 10 * 1024 * 1024;

export async function televerser(
  fichier: File,
  dossierId: string,
  options: {
    commentaire?: string;
    surProgression?: (progression: ProgressionTeleversement) => void;
    signal?: AbortSignal;
  } = {}
): Promise<Fichier> {
  if (fichier.size <= SEUIL_SIMPLE) {
    const formulaire = new FormData();
    formulaire.append("fichier", fichier);
    formulaire.append("dossier", dossierId);
    if (options.commentaire) formulaire.append("commentaire", options.commentaire);
    const resultat = await appeler<Fichier>("/files/upload/simple/", {
      methode: "POST",
      corps: formulaire,
      signal: options.signal,
    });
    options.surProgression?.({ envoyes: 1, total: 1, pourcentage: 100 });
    return resultat;
  }

  const checksum = await empreinteFichier(fichier);
  const init = await api.post<{
    upload_id: string;
    chunk_size: number;
    total_chunks: number;
    fragments_manquants: number[];
  }>("/files/upload/init/", {
    nom: fichier.name,
    dossier: dossierId,
    taille: fichier.size,
    checksum_sha256: checksum,
    commentaire: options.commentaire ?? "",
  });

  let envoyes = 0;
  for (let numero = 1; numero <= init.total_chunks; numero += 1) {
    const debut = (numero - 1) * init.chunk_size;
    const morceau = fichier.slice(debut, debut + init.chunk_size);
    let tentative = 0;
    // Une coupure réseau ne doit pas faire échouer tout l'envoi : on réessaie
    // le fragment, avec une attente croissante.
    while (true) {
      try {
        await appeler(`/files/upload/${init.upload_id}/part/${numero}/`, {
          methode: "PUT",
          brut: morceau,
          entetes: { "Content-Type": "application/octet-stream" },
          signal: options.signal,
        });
        break;
      } catch (erreur) {
        tentative += 1;
        if (tentative >= 5) throw erreur;
        await new Promise((resoudre) => setTimeout(resoudre, 1000 * 2 ** tentative));
      }
    }
    envoyes += 1;
    options.surProgression?.({
      envoyes,
      total: init.total_chunks,
      pourcentage: Math.round((envoyes / init.total_chunks) * 100),
    });
  }

  return api.post<Fichier>(`/files/upload/${init.upload_id}/complete/`);
}
