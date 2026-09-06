import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { EntreeJournal } from "../types";
import { formaterDate } from "../utilitaires";

export default function Journal() {
  const [entrees, setEntrees] = useState<EntreeJournal[]>([]);
  const [action, setAction] = useState("");
  const [texte, setTexte] = useState("");
  const [message, setMessage] = useState("");

  const charger = useCallback(async () => {
    const parametres = new URLSearchParams();
    if (action) parametres.set("action", action);
    if (texte) parametres.set("q", texte);
    try {
      const donnees = await api.get<{ results: EntreeJournal[] }>(
        `/activity/?${parametres.toString()}`
      );
      setEntrees(donnees.results ?? []);
    } catch (probleme) {
      setMessage(`Journal indisponible : ${(probleme as Error).message}`);
    }
  }, [action, texte]);

  useEffect(() => {
    void charger();
  }, [charger]);

  return (
    <section>
      <h1>Journal d'activité</h1>
      <p className="sous-titre">
        Chaque action est enregistrée et attribuée à un agent nommé. Le journal ne peut
        être ni modifié ni effacé depuis l'application.
      </p>

      <div className="ligne-formulaire">
        <label>
          Action
          <select value={action} onChange={(evenement) => setAction(evenement.target.value)}>
            <option value="">Toutes</option>
            <option value="FILE_UPLOAD">Téléversement</option>
            <option value="FILE_DOWNLOAD">Téléchargement</option>
            <option value="FILE_DELETE">Suppression de fichier</option>
            <option value="PERMISSION_GRANT">Attribution de droit</option>
            <option value="SHARE_LINK_CREATE">Création de lien</option>
            <option value="SYNC_CONFLICT">Conflit de synchronisation</option>
            <option value="LOGIN_FAILED">Échec de connexion</option>
          </select>
        </label>
        <label className="champ-large">
          Chemin contenant
          <input
            value={texte}
            onChange={(evenement) => setTexte(evenement.target.value)}
            placeholder="/cadastre/leves"
          />
        </label>
        <a className="bouton-secondaire" href={`${api.base}/activity/export/`}>
          Exporter en CSV
        </a>
      </div>

      {message && <p className="alerte">{message}</p>}

      <table className="tableau">
        <thead>
          <tr>
            <th>Date</th>
            <th>Agent</th>
            <th>Action</th>
            <th>Élément</th>
            <th>Adresse IP</th>
          </tr>
        </thead>
        <tbody>
          {entrees.map((entree) => (
            <tr key={entree.id}>
              <td>{formaterDate(entree.created_at)}</td>
              <td>{entree.acteur_nom}</td>
              <td>{entree.action_libelle}</td>
              <td className="chemin">{entree.target_path || "—"}</td>
              <td>{entree.ip_address ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {entrees.length === 0 && <p className="vide">Aucune entrée pour ces critères.</p>}
    </section>
  );
}
