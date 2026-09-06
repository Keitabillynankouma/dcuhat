import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/**
 * Planche à dessin.
 *
 * Le croquis est enregistré en **SVG** : c'est du texte, donc versionnable,
 * comparable, léger, et lisible par n'importe quel logiciel. La liste des
 * formes est conservée dans une balise `<metadata>` du fichier, ce qui permet
 * de rouvrir un croquis et de continuer à le modifier trait par trait —
 * un SVG venu d'ailleurs reste affiché en fond, sans être perdu.
 *
 * Les événements sont des *pointer events* : la souris au bureau et le doigt
 * ou le stylet sur une tablette de terrain suivent le même chemin.
 */

const LARGEUR = 1123;
const HAUTEUR = 794;
const BALISE_FORMES = "dcuhat-formes";

export type Outil = "trait" | "ligne" | "fleche" | "rectangle" | "ellipse" | "texte" | "gomme";

interface FormeBase {
  id: string;
  couleur: string;
  epaisseur: number;
}
interface Trait extends FormeBase {
  type: "trait";
  points: [number, number][];
}
interface Segment extends FormeBase {
  type: "ligne" | "fleche";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}
interface Boite extends FormeBase {
  type: "rectangle" | "ellipse";
  x: number;
  y: number;
  largeur: number;
  hauteur: number;
}
interface Texte extends FormeBase {
  type: "texte";
  x: number;
  y: number;
  contenu: string;
}
export type Forme = Trait | Segment | Boite | Texte;

export const COULEURS = [
  { valeur: "#1f2328", nom: "Noir" },
  { valeur: "#b42318", nom: "Rouge" },
  { valeur: "#0f5132", nom: "Vert" },
  { valeur: "#1d4ed8", nom: "Bleu" },
  { valeur: "#b45309", nom: "Orange" },
];
export const EPAISSEURS = [2, 4, 8, 14];

/* ------------------------------------------------------------------ */
/* Sérialisation                                                       */
/* ------------------------------------------------------------------ */
function echapper(texte: string): string {
  return texte
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function pointeDeFleche(forme: Segment): string {
  const angle = Math.atan2(forme.y2 - forme.y1, forme.x2 - forme.x1);
  const taille = 6 + forme.epaisseur * 2.2;
  const gauche = angle - Math.PI / 7;
  const droite = angle + Math.PI / 7;
  return [
    `M${forme.x2} ${forme.y2}`,
    `L${forme.x2 - taille * Math.cos(gauche)} ${forme.y2 - taille * Math.sin(gauche)}`,
    `M${forme.x2} ${forme.y2}`,
    `L${forme.x2 - taille * Math.cos(droite)} ${forme.y2 - taille * Math.sin(droite)}`,
  ].join(" ");
}

function formeEnSvg(forme: Forme): string {
  const trait = `stroke="${forme.couleur}" stroke-width="${forme.epaisseur}" fill="none" stroke-linecap="round" stroke-linejoin="round"`;
  switch (forme.type) {
    case "trait": {
      const d = forme.points
        .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x} ${y}`)
        .join(" ");
      return `<path d="${d}" ${trait}/>`;
    }
    case "ligne":
      return `<path d="M${forme.x1} ${forme.y1} L${forme.x2} ${forme.y2}" ${trait}/>`;
    case "fleche":
      return (
        `<path d="M${forme.x1} ${forme.y1} L${forme.x2} ${forme.y2}" ${trait}/>` +
        `<path d="${pointeDeFleche(forme)}" ${trait}/>`
      );
    case "rectangle":
      return `<rect x="${forme.x}" y="${forme.y}" width="${forme.largeur}" height="${forme.hauteur}" ${trait}/>`;
    case "ellipse":
      return `<ellipse cx="${forme.x + forme.largeur / 2}" cy="${
        forme.y + forme.hauteur / 2
      }" rx="${Math.abs(forme.largeur / 2)}" ry="${Math.abs(forme.hauteur / 2)}" ${trait}/>`;
    case "texte":
      return `<text x="${forme.x}" y="${forme.y}" fill="${forme.couleur}" font-size="${
        forme.epaisseur * 5 + 10
      }" font-family="Segoe UI, system-ui, sans-serif">${echapper(forme.contenu)}</text>`;
  }
}

export function construireSvg(formes: Forme[], fond: string | null): string {
  const image = fond
    ? `  <image href="${fond}" x="0" y="0" width="${LARGEUR}" height="${HAUTEUR}" preserveAspectRatio="xMidYMid meet"/>\n`
    : "";
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${LARGEUR} ${HAUTEUR}" ` +
    `width="${LARGEUR}" height="${HAUTEUR}">\n` +
    `  <metadata id="${BALISE_FORMES}">${echapper(JSON.stringify({ formes, fond }))}</metadata>\n` +
    `  <rect width="${LARGEUR}" height="${HAUTEUR}" fill="#ffffff"/>\n` +
    image +
    formes.map((forme) => `  ${formeEnSvg(forme)}`).join("\n") +
    "\n</svg>\n"
  );
}

export function lireSvg(svg: string): { formes: Forme[]; fond: string | null } {
  try {
    const document = new DOMParser().parseFromString(svg, "image/svg+xml");
    const metadonnees = document.getElementById(BALISE_FORMES);
    if (metadonnees?.textContent) {
      const donnees = JSON.parse(metadonnees.textContent);
      return { formes: donnees.formes ?? [], fond: donnees.fond ?? null };
    }
  } catch {
    // SVG produit ailleurs : on l'affichera en fond plutôt que de le perdre.
  }
  return { formes: [], fond: null };
}

/* ------------------------------------------------------------------ */
/* Composant                                                           */
/* ------------------------------------------------------------------ */
export default function Croquis({
  svgInitial,
  modifiable,
  surChangement,
}: {
  svgInitial: string;
  modifiable: boolean;
  surChangement: (svg: string) => void;
}) {
  const initial = useMemo(() => lireSvg(svgInitial), [svgInitial]);
  const [formes, setFormes] = useState<Forme[]>(initial.formes);
  const [fond, setFond] = useState<string | null>(initial.fond);
  const [annulees, setAnnulees] = useState<Forme[]>([]);
  const [outil, setOutil] = useState<Outil>("trait");
  const [couleur, setCouleur] = useState(COULEURS[0].valeur);
  const [epaisseur, setEpaisseur] = useState(4);
  const [enCours, setEnCours] = useState<Forme | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const champFond = useRef<HTMLInputElement>(null);

  // Le SVG complet remonte à chaque changement : c'est lui qui est enregistré.
  useEffect(() => {
    surChangement(construireSvg(formes, fond));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formes, fond]);

  const coordonnees = useCallback((evenement: React.PointerEvent): [number, number] => {
    const cadre = svgRef.current!.getBoundingClientRect();
    return [
      ((evenement.clientX - cadre.left) / cadre.width) * LARGEUR,
      ((evenement.clientY - cadre.top) / cadre.height) * HAUTEUR,
    ];
  }, []);

  function commencer(evenement: React.PointerEvent) {
    if (!modifiable) return;
    const [x, y] = coordonnees(evenement);
    (evenement.target as Element).setPointerCapture?.(evenement.pointerId);

    if (outil === "gomme") {
      // On retire la forme la plus récente dont le tracé passe près du clic.
      const index = [...formes]
        .reverse()
        .findIndex((forme) => distanceApprochee(forme, x, y) < 12 + forme.epaisseur);
      if (index >= 0) {
        const reel = formes.length - 1 - index;
        setFormes(formes.filter((_, position) => position !== reel));
      }
      return;
    }

    if (outil === "texte") {
      const contenu = window.prompt("Texte à placer");
      if (contenu) {
        setFormes([
          ...formes,
          { id: crypto.randomUUID(), type: "texte", x, y, contenu, couleur, epaisseur },
        ]);
      }
      return;
    }

    const commun = { id: crypto.randomUUID(), couleur, epaisseur };
    if (outil === "trait") {
      setEnCours({ ...commun, type: "trait", points: [[x, y]] });
    } else if (outil === "ligne" || outil === "fleche") {
      setEnCours({ ...commun, type: outil, x1: x, y1: y, x2: x, y2: y });
    } else {
      setEnCours({ ...commun, type: outil, x, y, largeur: 0, hauteur: 0 });
    }
  }

  function deplacer(evenement: React.PointerEvent) {
    if (!enCours) return;
    const [x, y] = coordonnees(evenement);
    if (enCours.type === "trait") {
      setEnCours({ ...enCours, points: [...enCours.points, [x, y]] });
    } else if (enCours.type === "ligne" || enCours.type === "fleche") {
      setEnCours({ ...enCours, x2: x, y2: y });
    } else if (enCours.type === "rectangle" || enCours.type === "ellipse") {
      setEnCours({ ...enCours, largeur: x - enCours.x, hauteur: y - enCours.y });
    }
  }

  function terminer() {
    if (!enCours) return;
    const negligeable =
      enCours.type === "trait"
        ? enCours.points.length < 2
        : enCours.type === "ligne" || enCours.type === "fleche"
          ? Math.hypot(enCours.x2 - enCours.x1, enCours.y2 - enCours.y1) < 3
          : Math.abs((enCours as Boite).largeur) < 3;
    if (!negligeable) {
      setFormes([...formes, enCours]);
      setAnnulees([]);
    }
    setEnCours(null);
  }

  function annuler() {
    if (formes.length === 0) return;
    setAnnulees([...annulees, formes[formes.length - 1]]);
    setFormes(formes.slice(0, -1));
  }

  function refaire() {
    if (annulees.length === 0) return;
    setFormes([...formes, annulees[annulees.length - 1]]);
    setAnnulees(annulees.slice(0, -1));
  }

  async function chargerFond(fichier: File | undefined) {
    if (!fichier) return;
    if (fichier.size > 3 * 1024 * 1024) {
      window.alert(
        "Image trop lourde (maximum 3 Mo). Le fond est intégré au croquis pour qu'il reste lisible partout ; au-delà, le fichier deviendrait ingérable."
      );
      return;
    }
    const lecteur = new FileReader();
    lecteur.onload = () => setFond(String(lecteur.result));
    lecteur.readAsDataURL(fichier);
  }

  const apercu = enCours ? [...formes, enCours] : formes;

  return (
    <div className="croquis">
      {modifiable && (
        <div className="croquis-barre">
          <div className="croquis-groupe">
            {(
              [
                ["trait", "✏️", "Tracé libre"],
                ["ligne", "／", "Ligne"],
                ["fleche", "➜", "Flèche"],
                ["rectangle", "▭", "Rectangle"],
                ["ellipse", "◯", "Ellipse"],
                ["texte", "T", "Texte"],
                ["gomme", "🧽", "Gomme"],
              ] as [Outil, string, string][]
            ).map(([valeur, icone, titre]) => (
              <button
                key={valeur}
                title={titre}
                className={outil === valeur ? "actif" : ""}
                onClick={() => setOutil(valeur)}
              >
                {icone}
              </button>
            ))}
          </div>

          <div className="croquis-groupe">
            {COULEURS.map((entree) => (
              <button
                key={entree.valeur}
                title={entree.nom}
                className={`pastille ${couleur === entree.valeur ? "actif" : ""}`}
                style={{ background: entree.valeur }}
                onClick={() => setCouleur(entree.valeur)}
              />
            ))}
          </div>

          <div className="croquis-groupe">
            {EPAISSEURS.map((valeur) => (
              <button
                key={valeur}
                title={`Épaisseur ${valeur}`}
                className={epaisseur === valeur ? "actif" : ""}
                onClick={() => setEpaisseur(valeur)}
              >
                <span
                  className="apercu-epaisseur"
                  style={{ height: Math.min(valeur, 10), background: couleur }}
                />
              </button>
            ))}
          </div>

          <div className="croquis-groupe">
            <button onClick={annuler} title="Annuler" disabled={formes.length === 0}>
              ↶
            </button>
            <button onClick={refaire} title="Refaire" disabled={annulees.length === 0}>
              ↷
            </button>
            <button onClick={() => champFond.current?.click()} title="Image de fond">
              🖼️
            </button>
            {fond && (
              <button onClick={() => setFond(null)} title="Retirer le fond">
                ✖
              </button>
            )}
            <input
              ref={champFond}
              type="file"
              accept="image/*"
              hidden
              onChange={(evenement) => void chargerFond(evenement.target.files?.[0])}
            />
            <button
              className="lien-danger"
              onClick={() => {
                if (window.confirm("Effacer tout le croquis ?")) {
                  setAnnulees([...annulees, ...formes].slice(-50));
                  setFormes([]);
                }
              }}
            >
              Tout effacer
            </button>
          </div>
        </div>
      )}

      <svg
        ref={svgRef}
        className="croquis-toile"
        viewBox={`0 0 ${LARGEUR} ${HAUTEUR}`}
        onPointerDown={commencer}
        onPointerMove={deplacer}
        onPointerUp={terminer}
        onPointerLeave={terminer}
        style={{ cursor: modifiable ? "crosshair" : "default" }}
      >
        <rect width={LARGEUR} height={HAUTEUR} fill="#ffffff" />
        {fond && (
          <image
            href={fond}
            x={0}
            y={0}
            width={LARGEUR}
            height={HAUTEUR}
            preserveAspectRatio="xMidYMid meet"
          />
        )}
        <g
          dangerouslySetInnerHTML={{
            __html: apercu.map(formeEnSvg).join(""),
          }}
        />
      </svg>
    </div>
  );
}

/** Distance approchée entre un point et une forme, pour la gomme. */
function distanceApprochee(forme: Forme, x: number, y: number): number {
  switch (forme.type) {
    case "trait":
      return Math.min(...forme.points.map(([px, py]) => Math.hypot(px - x, py - y)));
    case "ligne":
    case "fleche": {
      const dx = forme.x2 - forme.x1;
      const dy = forme.y2 - forme.y1;
      const longueur = Math.hypot(dx, dy) || 1;
      const t = Math.max(
        0,
        Math.min(1, ((x - forme.x1) * dx + (y - forme.y1) * dy) / (longueur * longueur))
      );
      return Math.hypot(forme.x1 + t * dx - x, forme.y1 + t * dy - y);
    }
    case "rectangle":
    case "ellipse": {
      const cx = forme.x + forme.largeur / 2;
      const cy = forme.y + forme.hauteur / 2;
      return Math.max(
        0,
        Math.hypot(cx - x, cy - y) - Math.hypot(forme.largeur, forme.hauteur) / 2
      );
    }
    case "texte":
      return Math.hypot(forme.x - x, forme.y - y);
  }
}
