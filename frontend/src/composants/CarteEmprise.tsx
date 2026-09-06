import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import type { Polygon } from "geojson";

/**
 * Aperçu cartographique de l'emprise d'un fichier.
 *
 * Le fond OpenStreetMap est mis en cache par le Service Worker : une fois la
 * zone communale consultée au bureau, la carte reste lisible sur le terrain
 * sans réseau.
 */
export default function CarteEmprise({
  emprise,
  titre,
}: {
  emprise: Polygon;
  titre: string;
}) {
  const conteneur = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!conteneur.current) return;
    const carte = L.map(conteneur.current, { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(carte);

    const couche = L.geoJSON(emprise, {
      style: { color: "#0f5132", weight: 2, fillOpacity: 0.15 },
    })
      .bindPopup(titre)
      .addTo(carte);

    carte.fitBounds(couche.getBounds(), { padding: [24, 24], maxZoom: 17 });
    return () => {
      carte.remove();
    };
  }, [emprise, titre]);

  return <div ref={conteneur} className="carte-apercu" />;
}
