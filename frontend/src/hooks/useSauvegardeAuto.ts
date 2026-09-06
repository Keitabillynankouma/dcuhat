import { useCallback, useEffect, useRef, useState } from "react";

import { api, HorsLigne } from "../api/client";
import { base } from "../hors-ligne/base";
import { empiler, enBase64 } from "../hors-ligne/file";

export type EtatSauvegarde =
  | "au-repos"
  | "modifie"
  | "enregistrement"
  | "enregistre"
  | "hors-ligne"
  | "erreur";

interface Options {
  fichierId: string;
  /** Délai d'inactivité avant l'envoi, en millisecondes. */
  delai?: number;
  surVersionPubliee?: (version: number) => void;
}

/**
 * Sauvegarde automatique du contenu d'un document.
 *
 * Le contenu part après un court silence de frappe, pas à chaque touche : on
 * évite d'inonder le serveur sans jamais laisser dormir le travail de l'agent.
 * Le serveur écrit dans un brouillon — aucune version n'est créée — et publie
 * de lui-même une version de sécurité à intervalle régulier.
 *
 * Hors ligne, le contenu est conservé sur l'appareil et mis en file : il
 * repartira à la reconnexion, comme n'importe quelle modification de terrain.
 */
export function useSauvegardeAuto({ fichierId, delai = 1500, surVersionPubliee }: Options) {
  const [etat, setEtat] = useState<EtatSauvegarde>("au-repos");
  const [enregistreLe, setEnregistreLe] = useState<Date | null>(null);
  const minuterie = useRef<number | null>(null);
  const dernierEnvoi = useRef<string | null>(null);
  const enAttente = useRef<string | null>(null);

  const envoyer = useCallback(
    async (contenu: string) => {
      if (contenu === dernierEnvoi.current) return;
      setEtat("enregistrement");
      try {
        const reponse = await api.put<{
          enregistre_le: string;
          version_publiee: number | null;
        }>(`/files/${fichierId}/brouillon/`, { contenu });
        dernierEnvoi.current = contenu;
        setEnregistreLe(new Date(reponse.enregistre_le));
        setEtat("enregistre");
        if (reponse.version_publiee) surVersionPubliee?.(reponse.version_publiee);
      } catch (probleme) {
        if (probleme instanceof HorsLigne) {
          // Le travail reste sur l'appareil et repartira à la reconnexion.
          await base.reglages.put({
            cle: `brouillon:${fichierId}`,
            valeur: { contenu, date: new Date().toISOString() },
          });
          setEtat("hors-ligne");
        } else {
          setEtat("erreur");
        }
      }
    },
    [fichierId, surVersionPubliee]
  );

  const signalerModification = useCallback(
    (contenu: string) => {
      enAttente.current = contenu;
      setEtat("modifie");
      if (minuterie.current) window.clearTimeout(minuterie.current);
      minuterie.current = window.setTimeout(() => void envoyer(contenu), delai);
    },
    [delai, envoyer]
  );

  /** Force l'envoi immédiat (avant de quitter la page, ou sur demande). */
  const enregistrerMaintenant = useCallback(async () => {
    if (minuterie.current) window.clearTimeout(minuterie.current);
    if (enAttente.current !== null) await envoyer(enAttente.current);
  }, [envoyer]);

  /** Publie une version à partir du contenu courant. */
  const publier = useCallback(
    async (contenu: string, commentaire: string) => {
      if (minuterie.current) window.clearTimeout(minuterie.current);
      setEtat("enregistrement");
      try {
        const reponse = await api.post<{ version: number }>(
          `/files/${fichierId}/brouillon/publier/`,
          { contenu, commentaire }
        );
        dernierEnvoi.current = contenu;
        setEnregistreLe(new Date());
        setEtat("enregistre");
        return reponse.version;
      } catch (probleme) {
        if (probleme instanceof HorsLigne) {
          await empiler("UPLOAD_VERSION", "FILE", fichierId, {
            contenu_base64: await enBase64(new Blob([contenu])),
            commentaire: commentaire || "Modifié hors ligne",
          });
          setEtat("hors-ligne");
          return null;
        }
        setEtat("erreur");
        throw probleme;
      }
    },
    [fichierId]
  );

  // Un onglet fermé ne doit pas emporter la dernière phrase saisie.
  useEffect(() => {
    const avantFermeture = (evenement: BeforeUnloadEvent) => {
      if (etat === "modifie" || etat === "enregistrement") {
        evenement.preventDefault();
        evenement.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", avantFermeture);
    return () => {
      window.removeEventListener("beforeunload", avantFermeture);
      if (minuterie.current) window.clearTimeout(minuterie.current);
    };
  }, [etat]);

  return { etat, enregistreLe, signalerModification, enregistrerMaintenant, publier };
}

export function libelleEtat(etat: EtatSauvegarde, date: Date | null): string {
  switch (etat) {
    case "modifie":
      return "Modifications non enregistrées…";
    case "enregistrement":
      return "Enregistrement…";
    case "enregistre":
      return date
        ? `Enregistré à ${date.toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}`
        : "Enregistré";
    case "hors-ligne":
      return "Hors ligne — conservé sur cet appareil";
    case "erreur":
      return "Échec de l'enregistrement";
    default:
      return "Aucune modification";
  }
}
