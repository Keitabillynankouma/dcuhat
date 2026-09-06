import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { CHAMPS_METIER } from "../champs";
import type { Dossier, Fichier } from "../types";
import { LIBELLES_TYPE, formaterDate, formaterTaille, iconeType } from "../utilitaires";

interface Resultats {
  total_fichiers: number;
  total_dossiers: number;
  fichiers: Fichier[];
  dossiers: Dossier[];
}

export default function Recherche() {
  const [texte, setTexte] = useState("");
  const [kind, setKind] = useState("");
  const [dateDebut, setDateDebut] = useState("");
  const [dateFin, setDateFin] = useState("");
  const [champMetier, setChampMetier] = useState<string>(CHAMPS_METIER[1].cle);
  const [valeurMetier, setValeurMetier] = useState("");
  const [resultats, setResultats] = useState<Resultats | null>(null);
  const [recherche, setRecherche] = useState(false);
  const [message, setMessage] = useState("");

  async function lancer(evenement: FormEvent) {
    evenement.preventDefault();
    setRecherche(true);
    setMessage("");
    const parametres = new URLSearchParams();
    if (texte) parametres.set("q", texte);
    if (kind) parametres.set("kind", kind);
    if (dateDebut) parametres.set("date_from", dateDebut);
    if (dateFin) parametres.set("date_to", dateFin);
    if (valeurMetier) parametres.set(`meta_${champMetier}`, valeurMetier);
    try {
      setResultats(await api.get<Resultats>(`/search/?${parametres.toString()}`));
    } catch (probleme) {
      setMessage(`Recherche impossible : ${(probleme as Error).message}`);
    } finally {
      setRecherche(false);
    }
  }

  return (
    <section>
      <h1>Recherche</h1>
      <p className="sous-titre">
        La recherche porte sur le nom, la description, les étiquettes, les champs du
        dossier et le contenu des documents bureautiques.
      </p>

      <form className="formulaire-recherche" onSubmit={lancer}>
        <div className="ligne-formulaire">
          <label className="champ-large">
            Mots-clés
            <input
              value={texte}
              onChange={(evenement) => setTexte(evenement.target.value)}
              placeholder="permis de construire, quartier Centre, LB-2026…"
              autoFocus
            />
          </label>
          <label>
            Type
            <select value={kind} onChange={(evenement) => setKind(evenement.target.value)}>
              <option value="">Tous</option>
              {Object.entries(LIBELLES_TYPE).map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>
                  {libelle}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="ligne-formulaire">
          <label>
            Déposé après le
            <input
              type="date"
              value={dateDebut}
              onChange={(evenement) => setDateDebut(evenement.target.value)}
            />
          </label>
          <label>
            Déposé avant le
            <input
              type="date"
              value={dateFin}
              onChange={(evenement) => setDateFin(evenement.target.value)}
            />
          </label>
          <label>
            Champ du dossier
            <select
              value={champMetier}
              onChange={(evenement) => setChampMetier(evenement.target.value)}
            >
              {CHAMPS_METIER.map((champ) => (
                <option key={champ.cle} value={champ.cle}>
                  {champ.libelle}
                </option>
              ))}
            </select>
          </label>
          <label>
            Valeur
            <input
              value={valeurMetier}
              onChange={(evenement) => setValeurMetier(evenement.target.value)}
              placeholder="LB-2026-014"
            />
          </label>
          <button type="submit" className="bouton-principal" disabled={recherche}>
            {recherche ? "Recherche…" : "Rechercher"}
          </button>
        </div>
      </form>

      {message && <p className="alerte">{message}</p>}

      {resultats && (
        <>
          <p className="resume-resultats">
            {resultats.total_fichiers} fichier(s) et {resultats.total_dossiers} dossier(s)
            correspondent.
          </p>

          {resultats.dossiers.length > 0 && (
            <div className="grille-services">
              {resultats.dossiers.map((dossier) => (
                <Link key={dossier.id} to={`/dossiers/${dossier.id}`} className="carte-service">
                  <span className="carte-icone" aria-hidden>📁</span>
                  <span className="carte-titre">{dossier.name}</span>
                  <span className="carte-detail">{dossier.path}</span>
                </Link>
              ))}
            </div>
          )}

          <table className="tableau">
            <thead>
              <tr>
                <th>Nom</th>
                <th>Emplacement</th>
                <th>Type</th>
                <th>Taille</th>
                <th>Modifié le</th>
              </tr>
            </thead>
            <tbody>
              {resultats.fichiers.map((fichier) => (
                <tr key={fichier.id}>
                  <td>
                    <Link to={`/fichiers/${fichier.id}`} className="lien-element">
                      <span aria-hidden>{iconeType(fichier.kind)}</span> {fichier.name}
                    </Link>
                  </td>
                  <td className="chemin">{fichier.chemin}</td>
                  <td>{LIBELLES_TYPE[fichier.kind]}</td>
                  <td>{formaterTaille(fichier.size_bytes)}</td>
                  <td>{formaterDate(fichier.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {resultats.fichiers.length === 0 && (
            <p className="vide">Aucun fichier ne correspond à ces critères.</p>
          )}
        </>
      )}
    </section>
  );
}
