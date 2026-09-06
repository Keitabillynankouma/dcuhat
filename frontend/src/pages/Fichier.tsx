import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, HorsLigne } from "../api/client";
import { base } from "../hors-ligne/base";
import {
  lireContenuLocal,
  rendreDisponibleHorsLigne,
  retirerDuCache,
} from "../hors-ligne/synchronisation";
import type { Fichier as TypeFichier, GeoAsset, Version } from "../types";
import { CHAMPS_METIER } from "../champs";
import { formaterDate, formaterTaille, iconeType, peutEcrire, peutGerer } from "../utilitaires";
import CarteEmprise from "../composants/CarteEmprise";

interface DetailFichier extends TypeFichier {
  versions: Version[];
  metadata: { id: string; key: string; value: string; source: string }[];
}

export default function Fichier() {
  const { fichierId } = useParams();
  const [fichier, setFichier] = useState<DetailFichier | null>(null);
  const [geo, setGeo] = useState<GeoAsset | null>(null);
  const [message, setMessage] = useState("");
  const [horsLigneDisponible, setHorsLigneDisponible] = useState(false);
  const [metadonnees, setMetadonnees] = useState<Record<string, string>>({});

  const charger = useCallback(async () => {
    if (!fichierId) return;
    try {
      const donnees = await api.get<DetailFichier>(`/files/${fichierId}/`);
      setFichier(donnees);
      setMetadonnees(
        Object.fromEntries(donnees.metadata.map((entree) => [entree.key, entree.value]))
      );
      if (donnees.est_geospatial) {
        api
          .get<GeoAsset>(`/geo/assets/${fichierId}/`)
          .then(setGeo)
          .catch(() => setGeo(null));
      }
    } catch (probleme) {
      if (probleme instanceof HorsLigne) {
        const local = await base.fichiers.get(fichierId);
        if (local) {
          setFichier({ ...local, versions: [], metadata: [] });
          setMessage("Hors ligne — informations issues du dernier état synchronisé.");
        } else {
          setMessage("Ce fichier n'est pas disponible hors ligne.");
        }
      } else {
        setMessage((probleme as Error).message);
      }
    }
    setHorsLigneDisponible(Boolean(await base.contenus.get(fichierId)));
  }, [fichierId]);

  useEffect(() => {
    void charger();
  }, [charger]);

  if (!fichier) return <p className="chargement">{message || "Chargement…"}</p>;

  const modifiable = peutEcrire(fichier.niveau);
  const estModifiable =
    modifiable &&
    [".txt", ".md", ".csv", ".json", ".geojson", ".svg", ".gpx", ".kml", ".prj", ".log"].some(
      (extension) => fichier.name.toLowerCase().endsWith(extension)
    );

  async function basculerHorsLigne() {
    if (!fichier) return;
    if (horsLigneDisponible) {
      await retirerDuCache(fichier.id);
      setHorsLigneDisponible(false);
      setMessage("Le fichier a été retiré de cet appareil.");
      return;
    }
    try {
      await rendreDisponibleHorsLigne(fichier);
      setHorsLigneDisponible(true);
      setMessage("Fichier chiffré et enregistré sur cet appareil pour un usage hors ligne.");
    } catch (probleme) {
      setMessage(`Impossible d'enregistrer le fichier : ${(probleme as Error).message}`);
    }
  }

  async function ouvrirLocalement() {
    if (!fichier) return;
    const blob = await lireContenuLocal(fichier.id);
    if (!blob) {
      setMessage("Aucune copie locale de ce fichier.");
      return;
    }
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  async function enregistrerMetadonnees() {
    if (!fichier) return;
    await api.put(`/files/${fichier.id}/metadata/`, metadonnees);
    setMessage("Métadonnées enregistrées.");
    await charger();
  }

  async function restaurerVersion(numero: number) {
    if (!fichier) return;
    if (!window.confirm(`Rétablir la version ${numero} comme version courante ?`)) return;
    await api.post(`/files/${fichier.id}/versions/${numero}/restore/`);
    setMessage(`La version ${numero} a été rétablie ; l'historique est conservé.`);
    await charger();
  }

  async function declarerSrid() {
    if (!fichier) return;
    const saisie = window.prompt(
      "Code EPSG du système de projection (exemples : 4326 pour le GPS, 32628 pour UTM 28N)"
    );
    if (!saisie) return;
    await api.patch(`/geo/assets/${fichier.id}/srid/`, { srid: Number(saisie) });
    setMessage("Projection déclarée : le fichier apparaîtra sur la carte.");
    await charger();
  }

  return (
    <section className="page-fichier">
      <nav className="fil-ariane">
        <Link to={`/dossiers/${fichier.folder}`}>← Retour au dossier</Link>
      </nav>

      <header className="entete-fichier">
        <h1>
          <span aria-hidden>{iconeType(fichier.kind)}</span> {fichier.name}
        </h1>
        <div className="actions">
          {estModifiable && (
            <Link className="bouton-principal" to={`/fichiers/${fichier.id}/editer`}>
              {fichier.kind === "CROQUIS" ? "Dessiner" : "Modifier le contenu"}
            </Link>
          )}
          <a className="bouton-secondaire" href={`${api.base}/files/${fichier.id}/download/`}>
            Télécharger
          </a>
          <button className="bouton-secondaire" onClick={() => void basculerHorsLigne()}>
            {horsLigneDisponible ? "Retirer de cet appareil" : "Rendre disponible hors ligne"}
          </button>
          {horsLigneDisponible && (
            <button className="bouton-secondaire" onClick={() => void ouvrirLocalement()}>
              Ouvrir la copie locale
            </button>
          )}
        </div>
      </header>

      {message && <p className="alerte">{message}</p>}

      <div className="grille-fichier">
        <article className="bloc">
          <h2>Informations</h2>
          <dl>
            <dt>Emplacement</dt>
            <dd>{fichier.chemin}</dd>
            <dt>Taille</dt>
            <dd>{formaterTaille(fichier.size_bytes)}</dd>
            <dt>Type</dt>
            <dd>{fichier.mime_type || fichier.kind}</dd>
            <dt>Déposé par</dt>
            <dd>{fichier.owner_nom}</dd>
            <dt>Dernière modification</dt>
            <dd>{formaterDate(fichier.updated_at)}</dd>
            <dt>Version courante</dt>
            <dd>{fichier.version_courante}</dd>
          </dl>
        </article>

        <article className="bloc">
          <h2>Champs du dossier</h2>
          <p className="aide">
            Ces champs alimentent la recherche : une parcelle renseignée ici se retrouve
            en une seule requête.
          </p>
          {CHAMPS_METIER.map((champ) => (
            <label key={champ.cle} className="champ-metier">
              {champ.libelle}
              <input
                value={metadonnees[champ.cle] ?? ""}
                disabled={!modifiable}
                onChange={(evenement) =>
                  setMetadonnees((actuel) => ({
                    ...actuel,
                    [champ.cle]: evenement.target.value,
                  }))
                }
              />
            </label>
          ))}
          {modifiable && (
            <button className="bouton-principal" onClick={() => void enregistrerMetadonnees()}>
              Enregistrer
            </button>
          )}
        </article>

        {fichier.est_geospatial && (
          <article className="bloc bloc-large">
            <h2>Données géospatiales</h2>
            {geo ? (
              <>
                <dl className="dl-en-ligne">
                  <dt>Format</dt>
                  <dd>{geo.geo_format}</dd>
                  <dt>Projection</dt>
                  <dd>{geo.srid_effectif ? `EPSG:${geo.srid_effectif}` : "non déterminée"}</dd>
                  <dt>Géométrie</dt>
                  <dd>{geo.geometry_type || "—"}</dd>
                  <dt>Entités</dt>
                  <dd>{geo.feature_count ?? "—"}</dd>
                </dl>
                {geo.extraction_status === "PARTIAL" && (
                  <div className="alerte">
                    <p>{geo.extraction_error}</p>
                    {modifiable && (
                      <button className="bouton-secondaire" onClick={() => void declarerSrid()}>
                        Déclarer la projection
                      </button>
                    )}
                  </div>
                )}
                {geo.emprise && <CarteEmprise emprise={geo.emprise} titre={fichier.name} />}
              </>
            ) : (
              <p className="vide">Analyse géospatiale en cours ou indisponible hors ligne.</p>
            )}
          </article>
        )}

        <article className="bloc bloc-large">
          <h2>Historique des versions</h2>
          <p className="aide">
            Une modification n'écrase jamais la précédente : chaque état reste
            restaurable.
          </p>
          <table className="tableau">
            <thead>
              <tr>
                <th>Version</th>
                <th>Date</th>
                <th>Auteur</th>
                <th>Taille</th>
                <th>Motif</th>
                <th>Origine</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {fichier.versions.map((version) => (
                <tr key={version.id} className={version.is_conflict_copy ? "ligne-conflit" : ""}>
                  <td>
                    v{version.version_number}
                    {version.version_number === fichier.version_courante && (
                      <span className="etiquette">courante</span>
                    )}
                    {version.is_conflict_copy && <span className="etiquette alerte">conflit</span>}
                  </td>
                  <td>{formaterDate(version.created_at)}</td>
                  <td>{version.auteur}</td>
                  <td>{formaterTaille(version.size_bytes)}</td>
                  <td>{version.comment || "—"}</td>
                  <td>{version.origin === "SYNC_OFFLINE" ? "Terrain (hors ligne)" : "Bureau"}</td>
                  <td>
                    {peutGerer(fichier.niveau) &&
                      version.version_number !== fichier.version_courante && (
                        <button
                          className="lien"
                          onClick={() => void restaurerVersion(version.version_number)}
                        >
                          Rétablir
                        </button>
                      )}
                  </td>
                </tr>
              ))}
              {fichier.versions.length === 0 && (
                <tr>
                  <td colSpan={7} className="vide">
                    Historique indisponible hors ligne.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </article>
      </div>
    </section>
  );
}
