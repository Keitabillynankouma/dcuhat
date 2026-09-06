import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, definirJetons, ErreurAPI, restaurerJetons } from "../api/client";
import { fermerSession, ouvrirSession } from "../hors-ligne/chiffrement";
import { viderCacheLocal } from "../hors-ligne/base";
import { enregistrerAppareil } from "../hors-ligne/synchronisation";
import type { Utilisateur } from "../types";

interface ContexteAuth {
  utilisateur: Utilisateur | null;
  chargement: boolean;
  connecter: (email: string, motDePasse: string, totp?: string) => Promise<void>;
  deconnecter: (viderCache?: boolean) => Promise<void>;
  totpRequis: boolean;
}

const Contexte = createContext<ContexteAuth | null>(null);

export function FournisseurAuth({ children }: { children: ReactNode }) {
  const [utilisateur, setUtilisateur] = useState<Utilisateur | null>(null);
  const [chargement, setChargement] = useState(true);
  const [totpRequis, setTotpRequis] = useState(false);

  useEffect(() => {
    restaurerJetons();
    api
      .get<Utilisateur>("/auth/me/")
      .then(setUtilisateur)
      .catch(() => setUtilisateur(null))
      .finally(() => setChargement(false));
  }, []);

  const connecter = useCallback(async (email: string, motDePasse: string, totp?: string) => {
    try {
      const reponse = await api.post<{
        access: string;
        refresh: string;
        utilisateur: Utilisateur;
      }>("/auth/login/", { email, password: motDePasse, totp: totp ?? "" });
      definirJetons(reponse.access, reponse.refresh);
      setUtilisateur(reponse.utilisateur);
      setTotpRequis(false);
      // La clé de chiffrement du cache local est dérivée du mot de passe et
      // reste en mémoire : elle n'est jamais écrite sur le disque.
      await ouvrirSession(motDePasse, reponse.utilisateur.id);
      await enregistrerAppareil(
        `${navigator.platform || "Navigateur"} — ${new Date().toLocaleDateString("fr-FR")}`
      ).catch(() => undefined);
    } catch (erreur) {
      if (erreur instanceof ErreurAPI && erreur.code === "TOTP_REQUIRED") {
        setTotpRequis(true);
      }
      throw erreur;
    }
  }, []);

  const deconnecter = useCallback(async (viderCache = false) => {
    await api.post("/auth/logout/").catch(() => undefined);
    definirJetons(null, null);
    fermerSession();
    if (viderCache) await viderCacheLocal();
    setUtilisateur(null);
  }, []);

  const valeur = useMemo(
    () => ({ utilisateur, chargement, connecter, deconnecter, totpRequis }),
    [utilisateur, chargement, connecter, deconnecter, totpRequis]
  );

  return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

export function useAuth(): ContexteAuth {
  const contexte = useContext(Contexte);
  if (!contexte) throw new Error("useAuth doit être utilisé dans FournisseurAuth.");
  return contexte;
}
