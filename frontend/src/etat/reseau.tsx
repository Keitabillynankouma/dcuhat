import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { nombreEnAttente } from "../hors-ligne/file";
import { synchroniser } from "../hors-ligne/synchronisation";

interface ContexteReseau {
  enLigne: boolean;
  synchronisation: boolean;
  message: string;
  enAttente: number;
  lancerSynchronisation: () => Promise<void>;
  rafraichirCompteur: () => Promise<void>;
}

const Contexte = createContext<ContexteReseau | null>(null);

export function FournisseurReseau({ children }: { children: ReactNode }) {
  const [enLigne, setEnLigne] = useState(navigator.onLine);
  const [synchronisation, setSynchronisation] = useState(false);
  const [message, setMessage] = useState("");
  const [enAttente, setEnAttente] = useState(0);

  const rafraichirCompteur = useCallback(async () => {
    setEnAttente(await nombreEnAttente());
  }, []);

  const lancerSynchronisation = useCallback(async () => {
    if (!navigator.onLine) {
      setMessage("Hors ligne — les modifications sont conservées localement.");
      return;
    }
    setSynchronisation(true);
    try {
      const etat = await synchroniser(setMessage);
      setMessage(etat.message);
    } catch (erreur) {
      setMessage(`Échec de la synchronisation : ${(erreur as Error).message}`);
    } finally {
      setSynchronisation(false);
      await rafraichirCompteur();
    }
  }, [rafraichirCompteur]);

  useEffect(() => {
    const retourReseau = () => {
      setEnLigne(true);
      // Le retour du réseau déclenche la synchronisation : l'agent n'a rien
      // à faire, c'est le comportement attendu après une sortie terrain.
      void lancerSynchronisation();
    };
    const perteReseau = () => {
      setEnLigne(false);
      setMessage("Hors ligne — vous pouvez continuer à travailler.");
    };
    window.addEventListener("online", retourReseau);
    window.addEventListener("offline", perteReseau);
    void rafraichirCompteur();
    return () => {
      window.removeEventListener("online", retourReseau);
      window.removeEventListener("offline", perteReseau);
    };
  }, [lancerSynchronisation, rafraichirCompteur]);

  const valeur = useMemo(
    () => ({
      enLigne,
      synchronisation,
      message,
      enAttente,
      lancerSynchronisation,
      rafraichirCompteur,
    }),
    [enLigne, synchronisation, message, enAttente, lancerSynchronisation, rafraichirCompteur]
  );

  return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

export function useReseau(): ContexteReseau {
  const contexte = useContext(Contexte);
  if (!contexte) throw new Error("useReseau doit être utilisé dans FournisseurReseau.");
  return contexte;
}
