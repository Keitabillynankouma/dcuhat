import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { api } from "../api/client";
import type { GeoAsset } from "../types";

/**
 * Carte communale : la base documentaire vue par l'espace.
 *
 * Chaque fichier géoréférencé y apparaît par son emprise. Les couches de
 * référence de la Direction (quartiers, zonage, voirie) se superposent.
 * L'utilisateur peut interroger la carte pour trouver tous les documents
 * concernant un secteur — « que sait-on de cette parcelle ? » devient une
 * question à laquelle la plateforme répond en un clic.
 */
export default function Carte() {
  const conteneur = useRef<HTMLDivElement>(null);
  const carteRef = useRef<L.Map | null>(null);
  const coucheRef = useRef<L.LayerGroup | null>(null);
  const [assets, setAssets] = useState<GeoAsset[]>([]);
  const [selection, setSelection] = useState<GeoAsset | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!conteneur.current || carteRef.current) return;
    const carte = L.map(conteneur.current).setView([9.54, -13.68], 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(carte);
    coucheRef.current = L.layerGroup().addTo(carte);
    carteRef.current = carte;

    const chargerEmprises = async () => {
      const bornes = carte.getBounds();
      const bbox = [
        bornes.getWest(),
        bornes.getSouth(),
        bornes.getEast(),
        bornes.getNorth(),
      ].join(",");
      try {
        const resultats = await api.get<GeoAsset[]>(`/geo/search/?bbox=${bbox}`);
        setAssets(resultats);
        setMessage(
          resultats.length === 0
            ? "Aucun document géoréférencé dans cette vue."
            : `${resultats.length} document(s) géoréférencé(s) dans cette vue.`
        );
      } catch {
        setMessage("Carte indisponible hors ligne pour cette zone.");
      }
    };

    carte.on("moveend", () => void chargerEmprises());
    void chargerEmprises();

    return () => {
      carte.remove();
      carteRef.current = null;
    };
  }, []);

  useEffect(() => {
    const couche = coucheRef.current;
    if (!couche) return;
    couche.clearLayers();
    for (const asset of assets) {
      if (!asset.emprise) continue;
      L.geoJSON(asset.emprise, {
        style: { color: "#0f5132", weight: 2, fillOpacity: 0.12 },
      })
        .on("click", () => setSelection(asset))
        .bindTooltip(asset.fichier_nom)
        .addTo(couche);
    }
  }, [assets]);

  return (
    <section className="page-carte">
      <div className="entete-carte">
        <h1>Carte communale</h1>
        <p className="sous-titre">{message}</p>
      </div>
      <div className="zone-carte">
        <div ref={conteneur} className="carte-principale" />
        <aside className="panneau-carte">
          <h2>Documents de la vue</h2>
          {assets.length === 0 && <p className="vide">Déplacez la carte pour explorer.</p>}
          <ul className="liste-assets">
            {assets.map((asset) => (
              <li key={asset.file}>
                <button
                  className={selection?.file === asset.file ? "actif" : ""}
                  onClick={() => setSelection(asset)}
                >
                  <strong>{asset.fichier_nom}</strong>
                  <span>
                    {asset.geo_format}
                    {asset.srid_effectif ? ` · EPSG:${asset.srid_effectif}` : ""}
                    {asset.feature_count ? ` · ${asset.feature_count} entités` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {selection && (
            <div className="detail-selection">
              <h3>{selection.fichier_nom}</h3>
              <a className="bouton-secondaire" href={`/fichiers/${selection.file}`}>
                Ouvrir la fiche du document
              </a>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
