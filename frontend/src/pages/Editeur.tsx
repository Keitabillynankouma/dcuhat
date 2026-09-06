import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, ErreurAPI, HorsLigne } from "../api/client";
import Croquis from "../composants/Croquis";
import { base } from "../hors-ligne/base";
import { libelleEtat, useSauvegardeAuto } from "../hooks/useSauvegardeAuto";

interface Contenu {
  editable: boolean;
  modifiable: boolean;
  nom: string;
  kind: string;
  version: number;
  contenu: string;
  brouillon: { contenu: string; base_version: number; enregistre_le: string } | null;
}

export default function Editeur() {
  const { fichierId } = useParams();

  const [donnees, setDonnees] = useState<Contenu | null>(null);
  const [texte, setTexte] = useState("");
  const [message, setMessage] = useState("");
  const [erreur, setErreur] = useState("");
  const [brouillonRepris, setBrouillonRepris] = useState(false);
  const texteRef = useRef("");

  const { etat, enregistreLe, signalerModification, enregistrerMaintenant, publier } =
    useSauvegardeAuto({
      fichierId: fichierId!,
      surVersionPubliee: (version) =>
        setMessage(`Version ${version} enregistrée automatiquement.`),
    });

  useEffect(() => {
    if (!fichierId) return;
    api
      .get<Contenu>(`/files/${fichierId}/contenu/`)
      .then(async (reponse) => {
        setDonnees(reponse);
        // Un brouillon local (laissé hors ligne) prime sur celui du serveur :
        // c'est le plus récent travail de cet agent sur cet appareil.
        const local = await base.reglages.get(`brouillon:${fichierId}`);
        const depuisLocal = (local?.valeur as { contenu?: string } | undefined)?.contenu;
        const initial = depuisLocal ?? reponse.brouillon?.contenu ?? reponse.contenu;
        setTexte(initial);
        texteRef.current = initial;
        setBrouillonRepris(Boolean(depuisLocal ?? reponse.brouillon));
      })
      .catch((probleme) => {
        if (probleme instanceof ErreurAPI) setErreur(String(probleme.detail));
        else if (probleme instanceof HorsLigne)
          setErreur("Ce document n'est pas modifiable hors ligne s'il n'a pas été ouvert avant.");
        else setErreur((probleme as Error).message);
      });
  }, [fichierId]);

  const modifier = useCallback(
    (valeur: string) => {
      setTexte(valeur);
      texteRef.current = valeur;
      signalerModification(valeur);
    },
    [signalerModification]
  );

  async function enregistrerVersion() {
    const commentaire = window.prompt(
      "Motif de la modification (facultatif, mais il rend l'historique lisible)",
      ""
    );
    if (commentaire === null) return;
    try {
      const version = await publier(texteRef.current, commentaire);
      setMessage(
        version
          ? `Version ${version} enregistrée. L'état précédent reste consultable dans l'historique.`
          : "Hors ligne — la version partira à la reconnexion."
      );
      await base.reglages.delete(`brouillon:${fichierId}`);
      setBrouillonRepris(false);
    } catch (probleme) {
      setErreur((probleme as Error).message);
    }
  }

  async function abandonner() {
    if (
      !window.confirm(
        "Abandonner les modifications non publiées et revenir à la dernière version enregistrée ?"
      )
    )
      return;
    await api.delete(`/files/${fichierId}/brouillon/`).catch(() => undefined);
    await base.reglages.delete(`brouillon:${fichierId}`);
    const rechargé = await api.get<Contenu>(`/files/${fichierId}/contenu/`);
    setTexte(rechargé.contenu);
    texteRef.current = rechargé.contenu;
    setBrouillonRepris(false);
    setMessage("Modifications abandonnées.");
  }

  if (erreur) {
    return (
      <section>
        <p className="alerte">{erreur}</p>
        <Link to={`/fichiers/${fichierId}`} className="bouton-secondaire">
          Retour à la fiche du document
        </Link>
      </section>
    );
  }

  if (!donnees) return <p className="chargement">Ouverture du document…</p>;

  const estCroquis = donnees.kind === "CROQUIS" || donnees.nom.toLowerCase().endsWith(".svg");

  return (
    <section className="page-editeur">
      <div className="barre-actions">
        <div>
          <h1>{donnees.nom}</h1>
          <p className="sous-titre">
            Version {donnees.version} ·{" "}
            <span className={`etat-sauvegarde etat-${etat}`}>
              {libelleEtat(etat, enregistreLe)}
            </span>
          </p>
        </div>
        <div className="actions">
          <Link to={`/fichiers/${fichierId}`} className="bouton-secondaire">
            Fiche du document
          </Link>
          {donnees.modifiable && (
            <>
              <button className="bouton-secondaire" onClick={() => void abandonner()}>
                Abandonner
              </button>
              <button className="bouton-principal" onClick={() => void enregistrerVersion()}>
                Enregistrer une version
              </button>
            </>
          )}
        </div>
      </div>

      {!donnees.modifiable && (
        <p className="alerte">
          Vous consultez ce document en lecture seule : vous n'avez pas le droit de
          modification sur ce dossier.
        </p>
      )}

      {brouillonRepris && (
        <p className="alerte">
          Un travail en cours a été retrouvé et rouvert. Il n'apparaîtra dans
          l'historique qu'une fois la version enregistrée.
        </p>
      )}

      {message && <p className="bandeau-succes">{message}</p>}

      {estCroquis ? (
        <Croquis
          svgInitial={texte}
          modifiable={donnees.modifiable}
          surChangement={modifier}
        />
      ) : (
        <textarea
          className="editeur-texte"
          value={texte}
          readOnly={!donnees.modifiable}
          spellCheck={false}
          onChange={(evenement) => modifier(evenement.target.value)}
          onBlur={() => void enregistrerMaintenant()}
        />
      )}

      <p className="aide-bas">
        La sauvegarde automatique conserve votre travail en continu sans encombrer
        l'historique. Une version n'est créée que lorsque vous le demandez — ou
        d'elle-même après un long moment de travail, pour qu'une coupure ne vous coûte
        jamais plus que quelques minutes.
      </p>
    </section>
  );
}
