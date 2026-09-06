import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { base } from "../hors-ligne/base";
import type { OperationLocale } from "../types";
import { formaterDate } from "../utilitaires";

interface ConflitServeur {
  id: string;
  op_type: string;
  target_type: string;
  target_id: string;
  conflict_resolution: string;
  client_timestamp: string;
  error: string;
  result: { file?: string; version?: number };
}

const LIBELLES_RESOLUTION: Record<string, string> = {
  BOTH_KEPT: "Les deux versions ont été conservées",
  SERVER_WINS: "La version du serveur a été conservée",
  CLIENT_WINS: "Votre version hors ligne a été conservée",
  MANUAL: "À arbitrer",
};

export default function Conflits() {
  const [conflits, setConflits] = useState<ConflitServeur[]>([]);
  const [rejets, setRejets] = useState<OperationLocale[]>([]);
  const [message, setMessage] = useState("");

  const charger = useCallback(async () => {
    try {
      setConflits(await api.get<ConflitServeur[]>("/sync/conflicts/"));
    } catch {
      setMessage("Liste des conflits indisponible hors ligne.");
    }
    setRejets(await base.operations.where("etat").equals("rejetee").toArray());
  }, []);

  useEffect(() => {
    void charger();
  }, [charger]);

  async function resoudre(identifiant: string, resolution: string) {
    await api.post(`/sync/conflicts/${identifiant}/resolve/`, { resolution });
    setMessage("Conflit arbitré.");
    await charger();
  }

  return (
    <section>
      <h1>Conflits de synchronisation</h1>
      <p className="sous-titre">
        Lorsqu'un document a été modifié à la fois au bureau et sur le terrain, la
        plateforme conserve les deux versions et vous laisse trancher. Aucun travail
        n'est jamais écrasé automatiquement.
      </p>
      {message && <p className="alerte">{message}</p>}

      <h2>À arbitrer</h2>
      {conflits.length === 0 && <p className="vide">Aucun conflit en attente.</p>}
      {conflits.map((conflit) => (
        <article key={conflit.id} className="carte-conflit">
          <header>
            <h3>
              {conflit.op_type === "UPLOAD_VERSION"
                ? "Modification concurrente d'un fichier"
                : conflit.op_type}
            </h3>
            <span className="etiquette">
              {LIBELLES_RESOLUTION[conflit.conflict_resolution] ?? conflit.conflict_resolution}
            </span>
          </header>
          <p>Modification effectuée hors ligne le {formaterDate(conflit.client_timestamp)}.</p>
          {conflit.result?.file && (
            <p>
              <Link to={`/fichiers/${conflit.result.file}`}>
                Comparer les versions du fichier
              </Link>
            </p>
          )}
          <div className="actions">
            <button
              className="bouton-principal"
              onClick={() => void resoudre(conflit.id, "CLIENT_WINS")}
            >
              Retenir ma version de terrain
            </button>
            <button
              className="bouton-secondaire"
              onClick={() => void resoudre(conflit.id, "SERVER_WINS")}
            >
              Retenir la version du bureau
            </button>
            <button
              className="bouton-secondaire"
              onClick={() => void resoudre(conflit.id, "BOTH_KEPT")}
            >
              Garder les deux
            </button>
          </div>
        </article>
      ))}

      <h2>Opérations refusées</h2>
      <p className="aide">
        Ces actions n'ont pas pu être appliquées, le plus souvent parce qu'un droit a
        changé entre-temps. Le contenu concerné reste sur cet appareil.
      </p>
      {rejets.length === 0 && <p className="vide">Aucune opération refusée.</p>}
      <ul className="liste-rejets">
        {rejets.map((operation) => (
          <li key={operation.id}>
            <strong>{operation.op_type}</strong> — {operation.message}
            <span className="date">{formaterDate(operation.client_timestamp)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
