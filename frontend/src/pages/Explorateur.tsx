import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ErreurAPI, HorsLigne } from "../api/client";
import { televerser, type ProgressionTeleversement } from "../api/televersement";
import { base } from "../hors-ligne/base";
import { empiler, enBase64, nouvelIdentifiant } from "../hors-ligne/file";
import { useAuth } from "../etat/auth";
import { useReseau } from "../etat/reseau";
import type {
  ContenuDossier,
  Dossier,
  Fichier,
  PageResultats,
  ServiceComplet,
} from "../types";
import { formaterDate, formaterTaille, iconeType, peutEcrire } from "../utilitaires";

export default function Explorateur() {
  const { dossierId } = useParams();
  const { enLigne, rafraichirCompteur } = useReseau();
  const { utilisateur } = useAuth();
  const naviguer = useNavigate();

  const [contenu, setContenu] = useState<ContenuDossier | null>(null);
  const [racines, setRacines] = useState<Dossier[]>([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [progression, setProgression] = useState<ProgressionTeleversement | null>(null);
  const [survol, setSurvol] = useState(false);
  const [services, setServices] = useState<ServiceComplet[]>([]);
  const [nouvelEspace, setNouvelEspace] = useState<{ nom: string; service: string } | null>(
    null
  );
  const champFichier = useRef<HTMLInputElement>(null);
  const estAdmin = utilisateur?.role === "ADMIN";

  const charger = useCallback(async () => {
    setChargement(true);
    setErreur("");
    try {
      if (!dossierId) {
        const donnees = await api.get<{ results: Dossier[] }>("/folders/");
        setRacines(donnees.results ?? []);
        setContenu(null);
      } else {
        const donnees = await api.get<ContenuDossier>(`/folders/${dossierId}/children/`);
        setContenu(donnees);
        // Le contenu consulté alimente le cache local : ce qu'un agent regarde
        // au bureau est ce dont il aura besoin sur le terrain.
        await base.dossiers.bulkPut([donnees.dossier, ...donnees.dossiers]);
        await base.fichiers.bulkPut(donnees.fichiers);
      }
    } catch (probleme) {
      if (probleme instanceof HorsLigne && dossierId) {
        const dossier = await base.dossiers.get(dossierId);
        const sousDossiers = await base.dossiers.where("parent").equals(dossierId).toArray();
        const fichiers = await base.fichiers.where("folder").equals(dossierId).toArray();
        if (dossier) {
          setContenu({ dossier, fil_ariane: [], dossiers: sousDossiers, fichiers });
          setErreur("Hors ligne — affichage du dernier état synchronisé.");
        } else {
          setErreur("Ce dossier n'est pas disponible hors ligne.");
        }
      } else {
        setErreur((probleme as Error).message);
      }
    } finally {
      setChargement(false);
    }
  }, [dossierId]);

  useEffect(() => {
    void charger();
  }, [charger]);

  useEffect(() => {
    if (!estAdmin || dossierId) return;
    api
      .get<PageResultats<ServiceComplet>>("/auth/services/")
      .then((donnees) => setServices(donnees.results))
      .catch(() => undefined);
  }, [estAdmin, dossierId]);

  async function creerEspace() {
    if (!nouvelEspace?.nom.trim()) return;
    try {
      await api.post("/folders/", {
        name: nouvelEspace.nom.trim(),
        service: nouvelEspace.service || null,
      });
      setNouvelEspace(null);
      await charger();
    } catch (probleme) {
      setErreur(
        probleme instanceof ErreurAPI
          ? String(probleme.detail)
          : (probleme as Error).message
      );
    }
  }

  const niveau = contenu?.dossier.niveau ?? null;
  const modifiable = peutEcrire(niveau);

  async function creerDossier() {
    const nom = window.prompt("Nom du nouveau dossier");
    if (!nom || !dossierId) return;
    try {
      await api.post("/folders/", { name: nom, parent: dossierId });
      await charger();
    } catch (probleme) {
      if (probleme instanceof HorsLigne) {
        // Hors ligne : l'identifiant est généré ici et sera accepté tel quel
        // par le serveur à la synchronisation.
        const identifiant = nouvelIdentifiant();
        await empiler("CREATE_FOLDER", "FOLDER", identifiant, {
          name: nom,
          parent: dossierId,
        });
        await rafraichirCompteur();
        setErreur("Dossier créé localement — il sera envoyé au retour du réseau.");
      } else if (probleme instanceof ErreurAPI && probleme.code === "NAME_CONFLICT") {
        setErreur("Un dossier porte déjà ce nom ici.");
      } else {
        setErreur((probleme as Error).message);
      }
    }
  }

  async function creerDocument(croquis: boolean) {
    const nom = window.prompt(
      croquis ? "Nom du croquis" : "Nom du document (.md, .txt, .csv, .geojson…)",
      croquis ? "Croquis de terrain" : "Note.md"
    );
    if (!nom || !dossierId) return;
    try {
      const fichier = await api.post<Fichier>("/files/nouveau/", {
        nom,
        dossier: dossierId,
        croquis,
      });
      naviguer(`/fichiers/${fichier.id}/editer`);
    } catch (probleme) {
      setErreur(
        probleme instanceof ErreurAPI ? String(probleme.detail) : (probleme as Error).message
      );
    }
  }

  async function deposer(fichiers: FileList | null) {
    if (!fichiers || !dossierId) return;
    for (const fichier of Array.from(fichiers)) {
      try {
        await televerser(fichier, dossierId, { surProgression: setProgression });
      } catch (probleme) {
        if (probleme instanceof HorsLigne) {
          await empiler("UPLOAD_VERSION", "FILE", nouvelIdentifiant(), {
            name: fichier.name,
            folder: dossierId,
            contenu_base64: await enBase64(fichier),
            commentaire: "Déposé hors ligne",
          });
          await rafraichirCompteur();
          setErreur(
            `« ${fichier.name} » est conservé sur cet appareil et sera envoyé au retour du réseau.`
          );
        } else {
          setErreur(`${fichier.name} : ${(probleme as Error).message}`);
        }
      }
    }
    setProgression(null);
    await charger();
  }

  async function renommerEspace(espace: Dossier) {
    const nom = window.prompt("Nouveau nom de l'espace", espace.name);
    if (!nom || nom === espace.name) return;
    try {
      await api.patch(`/folders/${espace.id}/`, { name: nom });
      await charger();
    } catch (probleme) {
      setErreur(
        probleme instanceof ErreurAPI ? String(probleme.detail) : (probleme as Error).message
      );
    }
  }

  async function supprimer(element: Dossier | Fichier) {
    const estEspace = element.type === "dossier" && element.parent === null;
    const question = estEspace
      ? `Envoyer l'espace « ${element.name} » à la corbeille ? Tout son contenu part avec lui. Il restera récupérable depuis la corbeille.`
      : `Envoyer « ${element.name} » à la corbeille ?`;
    if (!window.confirm(question)) return;
    const chemin = element.type === "dossier" ? "folders" : "files";
    try {
      await api.delete(`/${chemin}/${element.id}/`);
    } catch (probleme) {
      if (probleme instanceof HorsLigne) {
        await empiler(
          "DELETE",
          element.type === "dossier" ? "FOLDER" : "FILE",
          element.id
        );
        await rafraichirCompteur();
      } else {
        setErreur((probleme as Error).message);
        return;
      }
    }
    await charger();
  }

  if (chargement) return <p className="chargement">Chargement…</p>;

  if (!dossierId) {
    return (
      <section>
        <div className="barre-actions">
          <div>
            <h1>Espaces de la Direction</h1>
            <p className="sous-titre">
              Chaque service dispose de son espace. Ouvrez celui sur lequel vous
              travaillez.
            </p>
          </div>
          {estAdmin && (
            <button
              className="bouton-principal"
              onClick={() =>
                setNouvelEspace(nouvelEspace ? null : { nom: "", service: "" })
              }
            >
              {nouvelEspace ? "Annuler" : "Nouvel espace"}
            </button>
          )}
        </div>

        {erreur && <p className="alerte">{erreur}</p>}

        {nouvelEspace && (
          <form
            className="formulaire-recherche"
            onSubmit={(evenement) => {
              evenement.preventDefault();
              void creerEspace();
            }}
          >
            <div className="ligne-formulaire">
              <label className="champ-large">
                Nom de l'espace
                <input
                  autoFocus
                  value={nouvelEspace.nom}
                  onChange={(evenement) =>
                    setNouvelEspace({ ...nouvelEspace, nom: evenement.target.value })
                  }
                  placeholder="Service des Espaces Verts"
                />
              </label>
              <label>
                Service rattaché
                <select
                  value={nouvelEspace.service}
                  onChange={(evenement) =>
                    setNouvelEspace({ ...nouvelEspace, service: evenement.target.value })
                  }
                >
                  <option value="">Aucun</option>
                  {services.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.name}
                    </option>
                  ))}
                </select>
              </label>
              <button type="submit" className="bouton-principal">
                Créer l'espace
              </button>
            </div>
            <p className="aide">
              Un espace rattaché à un service en devient la racine : ses agents y
              obtiennent automatiquement leurs droits.
            </p>
          </form>
        )}

        <div className="grille-services">
          {racines.map((racine) => (
            <div key={racine.id} className="carte-service">
              <Link to={`/dossiers/${racine.id}`} className="carte-lien">
                <span className="carte-icone" aria-hidden>📁</span>
                <span className="carte-titre">{racine.name}</span>
                <span className="carte-detail">
                  {racine.file_count} fichier(s) · {formaterTaille(racine.size_bytes)}
                </span>
              </Link>
              {estAdmin && (
                <div className="carte-actions">
                  <button className="lien" onClick={() => void renommerEspace(racine)}>
                    Renommer
                  </button>
                  <button className="lien-danger" onClick={() => void supprimer(racine)}>
                    Supprimer
                  </button>
                </div>
              )}
            </div>
          ))}
          {racines.length === 0 && (
            <p className="vide">
              Aucun espace ne vous est encore ouvert. Contactez l'administrateur de la
              plateforme.
            </p>
          )}
        </div>
      </section>
    );
  }

  return (
    <section
      className={`explorateur ${survol ? "survol" : ""}`}
      onDragOver={(evenement) => {
        evenement.preventDefault();
        if (modifiable) setSurvol(true);
      }}
      onDragLeave={() => setSurvol(false)}
      onDrop={(evenement) => {
        evenement.preventDefault();
        setSurvol(false);
        if (modifiable) void deposer(evenement.dataTransfer.files);
      }}
    >
      <nav className="fil-ariane">
        <Link to="/dossiers">Espaces</Link>
        {contenu?.fil_ariane.map((etape) => (
          <span key={etape.id}>
            <span className="separateur">/</span>
            <Link to={`/dossiers/${etape.id}`}>{etape.name}</Link>
          </span>
        ))}
      </nav>

      <div className="barre-actions">
        <h1>{contenu?.dossier.name}</h1>
        <div className="actions">
          {modifiable && (
            <>
              <button className="bouton-secondaire" onClick={creerDossier}>
                Nouveau dossier
              </button>
              <button className="bouton-secondaire" onClick={() => void creerDocument(false)}>
                Nouveau document
              </button>
              <button className="bouton-secondaire" onClick={() => void creerDocument(true)}>
                Nouveau croquis
              </button>
              <button
                className="bouton-principal"
                onClick={() => champFichier.current?.click()}
              >
                Téléverser
              </button>
              <input
                ref={champFichier}
                type="file"
                multiple
                hidden
                onChange={(evenement) => void deposer(evenement.target.files)}
              />
            </>
          )}
          <a
            className="bouton-secondaire"
            href={`${api.base}/folders/${dossierId}/download/`}
            onClick={(evenement) => {
              if (!enLigne) {
                evenement.preventDefault();
                setErreur("Le téléchargement d'une archive nécessite une connexion.");
              }
            }}
          >
            Télécharger (.zip)
          </a>
        </div>
      </div>

      {erreur && <p className="alerte">{erreur}</p>}

      {progression && (
        <div className="progression">
          <div className="progression-barre" style={{ width: `${progression.pourcentage}%` }} />
          <span>
            Envoi {progression.envoyes}/{progression.total} fragments ({progression.pourcentage} %)
          </span>
        </div>
      )}

      <table className="tableau">
        <thead>
          <tr>
            <th>Nom</th>
            <th>Type</th>
            <th>Taille</th>
            <th>Modifié le</th>
            <th>Auteur</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {contenu?.dossiers.map((sousDossier) => (
            <tr key={sousDossier.id}>
              <td>
                <Link to={`/dossiers/${sousDossier.id}`} className="lien-element">
                  <span aria-hidden>📁</span> {sousDossier.name}
                </Link>
              </td>
              <td>Dossier</td>
              <td>{formaterTaille(sousDossier.size_bytes)}</td>
              <td>{formaterDate(sousDossier.updated_at)}</td>
              <td>—</td>
              <td className="cellule-actions">
                {peutEcrire(sousDossier.niveau) && (
                  <button className="lien-danger" onClick={() => void supprimer(sousDossier)}>
                    Supprimer
                  </button>
                )}
              </td>
            </tr>
          ))}

          {contenu?.fichiers.map((fichier) => (
            <tr key={fichier.id}>
              <td>
                <Link to={`/fichiers/${fichier.id}`} className="lien-element">
                  <span aria-hidden>{iconeType(fichier.kind)}</span> {fichier.name}
                  {fichier.version_courante > 1 && (
                    <span className="etiquette">v{fichier.version_courante}</span>
                  )}
                </Link>
              </td>
              <td>{fichier.est_geospatial ? "Donnée géospatiale" : fichier.kind}</td>
              <td>{formaterTaille(fichier.size_bytes)}</td>
              <td>{formaterDate(fichier.updated_at)}</td>
              <td>{fichier.owner_nom}</td>
              <td className="cellule-actions">
                {peutEcrire(fichier.niveau) && (
                  <button className="lien-danger" onClick={() => void supprimer(fichier)}>
                    Supprimer
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {contenu?.dossiers.length === 0 && contenu?.fichiers.length === 0 && (
        <p className="vide">
          Ce dossier est vide. {modifiable && "Glissez-y des fichiers pour commencer."}
        </p>
      )}

      <p className="aide-bas">
        Astuce : ouvrez un fichier pour consulter son historique de versions, ses
        métadonnées et, s'il est géoréférencé, son emprise sur la carte communale.
      </p>
    </section>
  );
}
