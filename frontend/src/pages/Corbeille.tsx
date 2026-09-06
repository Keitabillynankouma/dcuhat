import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import { useAuth } from "../etat/auth";
import type { Dossier, Fichier } from "../types";
import { formaterDate, formaterTaille } from "../utilitaires";

export default function Corbeille() {
  const { utilisateur } = useAuth();
  const [dossiers, setDossiers] = useState<Dossier[]>([]);
  const [fichiers, setFichiers] = useState<Fichier[]>([]);
  const [message, setMessage] = useState("");

  const charger = useCallback(async () => {
    try {
      const donnees = await api.get<{ dossiers: Dossier[]; fichiers: Fichier[] }>("/trash/");
      setDossiers(donnees.dossiers);
      setFichiers(donnees.fichiers);
    } catch (probleme) {
      setMessage(`Corbeille indisponible : ${(probleme as Error).message}`);
    }
  }, []);

  useEffect(() => {
    void charger();
  }, [charger]);

  async function restaurer(identifiant: string, nom: string) {
    await api.post(`/trash/${identifiant}/`);
    setMessage(`« ${nom} » a été restauré à son emplacement d'origine.`);
    await charger();
  }

  async function purger(identifiant: string, nom: string) {
    if (
      !window.confirm(
        `Supprimer définitivement « ${nom} » ? Cette action est irréversible et libère l'espace occupé par toutes ses versions.`
      )
    )
      return;
    await api.delete(`/trash/${identifiant}/`);
    setMessage(`« ${nom} » a été supprimé définitivement.`);
    await charger();
  }

  const estAdmin = utilisateur?.role === "ADMIN";

  return (
    <section>
      <h1>Corbeille</h1>
      <p className="sous-titre">
        Les éléments supprimés sont conservés puis purgés automatiquement. Tant qu'ils
        sont ici, rien n'est perdu.
      </p>
      {message && <p className="alerte">{message}</p>}

      <table className="tableau">
        <thead>
          <tr>
            <th>Nom</th>
            <th>Type</th>
            <th>Taille</th>
            <th>Supprimé le</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {dossiers.map((dossier) => (
            <tr key={dossier.id}>
              <td>📁 {dossier.name}</td>
              <td>Dossier</td>
              <td>{formaterTaille(dossier.size_bytes)}</td>
              <td>{formaterDate(dossier.deleted_at ?? "")}</td>
              <td className="cellule-actions">
                <button className="lien" onClick={() => void restaurer(dossier.id, dossier.name)}>
                  Restaurer
                </button>
                {estAdmin && (
                  <button
                    className="lien-danger"
                    onClick={() => void purger(dossier.id, dossier.name)}
                  >
                    Purger
                  </button>
                )}
              </td>
            </tr>
          ))}
          {fichiers.map((fichier) => (
            <tr key={fichier.id}>
              <td>📄 {fichier.name}</td>
              <td>Fichier</td>
              <td>{formaterTaille(fichier.size_bytes)}</td>
              <td>{formaterDate(fichier.deleted_at ?? "")}</td>
              <td className="cellule-actions">
                <button className="lien" onClick={() => void restaurer(fichier.id, fichier.name)}>
                  Restaurer
                </button>
                {estAdmin && (
                  <button
                    className="lien-danger"
                    onClick={() => void purger(fichier.id, fichier.name)}
                  >
                    Purger
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {dossiers.length === 0 && fichiers.length === 0 && (
        <p className="vide">La corbeille est vide.</p>
      )}
    </section>
  );
}
