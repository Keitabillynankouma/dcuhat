import { useEffect, useState, type FormEvent } from "react";

import { api, ErreurAPI } from "../api/client";
import { useAuth } from "../etat/auth";
import { base, placeOccupee, viderCacheLocal } from "../hors-ligne/base";
import type { Utilisateur } from "../types";
import { LIBELLES_ROLE, formaterTaille } from "../utilitaires";

export default function MonCompte() {
  const { utilisateur, deconnecter } = useAuth();
  const [onglet, setOnglet] = useState<"profil" | "securite" | "appareil">("profil");

  if (!utilisateur) return null;

  return (
    <section>
      <h1>Mon compte</h1>
      <p className="sous-titre">
        {utilisateur.nom_complet || utilisateur.email} —{" "}
        {LIBELLES_ROLE[utilisateur.role] ?? utilisateur.role}
        {utilisateur.service_nom ? `, ${utilisateur.service_nom}` : ""}
      </p>

      {utilisateur.must_change_password && (
        <p className="alerte">
          Votre mot de passe est provisoire. Changez-le dès maintenant : il protège
          aussi les documents enregistrés sur cet appareil pour un usage hors ligne.
        </p>
      )}

      <div className="onglets">
        <button
          className={onglet === "profil" ? "actif" : ""}
          onClick={() => setOnglet("profil")}
        >
          Profil
        </button>
        <button
          className={onglet === "securite" ? "actif" : ""}
          onClick={() => setOnglet("securite")}
        >
          Mot de passe et sécurité
        </button>
        <button
          className={onglet === "appareil" ? "actif" : ""}
          onClick={() => setOnglet("appareil")}
        >
          Cet appareil
        </button>
      </div>

      {onglet === "profil" && <Profil utilisateur={utilisateur} />}
      {onglet === "securite" && <Securite utilisateur={utilisateur} />}
      {onglet === "appareil" && <Appareil surPurge={() => deconnecter(true)} />}
    </section>
  );
}

/* ------------------------------------------------------------------ */
function Profil({ utilisateur }: { utilisateur: Utilisateur }) {
  const [champs, setChamps] = useState({
    first_name: utilisateur.first_name,
    last_name: utilisateur.last_name,
    fonction: utilisateur.fonction ?? "",
    phone: (utilisateur as { phone?: string }).phone ?? "",
  });
  const [message, setMessage] = useState("");

  async function enregistrer(evenement: FormEvent) {
    evenement.preventDefault();
    try {
      await api.patch("/auth/me/", champs);
      setMessage("Profil enregistré.");
    } catch (probleme) {
      setMessage((probleme as Error).message);
    }
  }

  return (
    <form className="formulaire-recherche" onSubmit={enregistrer}>
      <div className="ligne-formulaire">
        <label>
          Prénom
          <input
            value={champs.first_name}
            onChange={(e) => setChamps({ ...champs, first_name: e.target.value })}
          />
        </label>
        <label>
          Nom
          <input
            value={champs.last_name}
            onChange={(e) => setChamps({ ...champs, last_name: e.target.value })}
          />
        </label>
        <label className="champ-large">
          Fonction
          <input
            value={champs.fonction}
            onChange={(e) => setChamps({ ...champs, fonction: e.target.value })}
          />
        </label>
        <label>
          Téléphone
          <input
            value={champs.phone}
            onChange={(e) => setChamps({ ...champs, phone: e.target.value })}
          />
        </label>
      </div>
      <div className="ligne-formulaire">
        <button type="submit" className="bouton-principal">
          Enregistrer
        </button>
      </div>
      <p className="aide">
        Votre adresse e-mail, votre rôle et votre service ne sont modifiables que par
        un administrateur : ils déterminent vos droits.
      </p>
      {message && <p className="alerte">{message}</p>}
    </form>
  );
}

/* ------------------------------------------------------------------ */
function Securite({ utilisateur }: { utilisateur: Utilisateur }) {
  const [ancien, setAncien] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);

  const [totp, setTotp] = useState<{ uri: string; qrcode_png_base64: string } | null>(null);
  const [codeTotp, setCodeTotp] = useState("");
  const [actif, setActif] = useState(utilisateur.totp_enabled);

  async function changer(evenement: FormEvent) {
    evenement.preventDefault();
    setErreur("");
    setMessage("");
    if (nouveau !== confirmation) {
      setErreur("Les deux saisies du nouveau mot de passe ne correspondent pas.");
      return;
    }
    if (nouveau.length < 12) {
      setErreur("Le mot de passe doit compter au moins douze caractères.");
      return;
    }
    setEnvoi(true);
    try {
      await api.post("/auth/password/change/", { ancien, nouveau });
      setMessage(
        "Mot de passe modifié. Reconnectez-vous pour que le chiffrement de vos documents hors ligne utilise le nouveau."
      );
      setAncien("");
      setNouveau("");
      setConfirmation("");
    } catch (probleme) {
      if (probleme instanceof ErreurAPI) {
        const detail = probleme.detail;
        setErreur(
          typeof detail === "string"
            ? detail
            : Object.values(detail as Record<string, string[]>)
                .flat()
                .join(" ")
        );
      } else {
        setErreur((probleme as Error).message);
      }
    } finally {
      setEnvoi(false);
    }
  }

  async function preparerTotp() {
    setTotp(await api.post("/auth/totp/"));
  }

  async function confirmerTotp() {
    try {
      await api.put("/auth/totp/", { code: codeTotp });
      setActif(true);
      setTotp(null);
      setMessage("Double authentification activée.");
    } catch (probleme) {
      setErreur(
        probleme instanceof ErreurAPI ? String(probleme.detail) : (probleme as Error).message
      );
    }
  }

  async function desactiverTotp() {
    if (!window.confirm("Désactiver la double authentification ?")) return;
    await api.delete("/auth/totp/");
    setActif(false);
    setMessage("Double authentification désactivée.");
  }

  return (
    <>
      <form className="formulaire-recherche" onSubmit={changer}>
        <h2>Changer mon mot de passe</h2>
        <div className="ligne-formulaire">
          <label className="champ-large">
            Mot de passe actuel
            <input
              type="password"
              autoComplete="current-password"
              required
              value={ancien}
              onChange={(e) => setAncien(e.target.value)}
            />
          </label>
        </div>
        <div className="ligne-formulaire">
          <label className="champ-large">
            Nouveau mot de passe
            <input
              type="password"
              autoComplete="new-password"
              required
              value={nouveau}
              onChange={(e) => setNouveau(e.target.value)}
            />
          </label>
          <label className="champ-large">
            Confirmation
            <input
              type="password"
              autoComplete="new-password"
              required
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
          </label>
          <button type="submit" className="bouton-principal" disabled={envoi}>
            {envoi ? "Modification…" : "Changer"}
          </button>
        </div>
        <p className="aide">
          Douze caractères au minimum, différent de vos autres mots de passe. Il sert
          aussi de clé au chiffrement des documents enregistrés hors ligne sur vos
          appareils.
        </p>
        {erreur && <p className="erreur">{erreur}</p>}
        {message && <p className="alerte">{message}</p>}
      </form>

      <div className="formulaire-recherche">
        <h2>Double authentification</h2>
        {actif ? (
          <>
            <p className="aide">
              Elle est active : un code à six chiffres vous est demandé à chaque
              connexion.
            </p>
            <button className="bouton-secondaire" onClick={() => void desactiverTotp()}>
              Désactiver
            </button>
          </>
        ) : totp ? (
          <>
            <p className="aide">
              Scannez ce code avec votre application d'authentification, puis saisissez
              le code affiché pour confirmer.
            </p>
            {totp.qrcode_png_base64 && (
              <img
                className="qrcode"
                alt="Code à scanner"
                src={`data:image/png;base64,${totp.qrcode_png_base64}`}
              />
            )}
            <div className="ligne-formulaire">
              <label>
                Code à six chiffres
                <input
                  inputMode="numeric"
                  maxLength={6}
                  value={codeTotp}
                  onChange={(e) => setCodeTotp(e.target.value)}
                />
              </label>
              <button className="bouton-principal" onClick={() => void confirmerTotp()}>
                Confirmer
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="aide">
              Recommandée pour les comptes d'administration et de direction : même si
              votre mot de passe fuite, le compte reste protégé.
            </p>
            <button className="bouton-secondaire" onClick={() => void preparerTotp()}>
              Activer
            </button>
          </>
        )}
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
function Appareil({ surPurge }: { surPurge: () => Promise<void> }) {
  const [place, setPlace] = useState(0);
  const [documents, setDocuments] = useState(0);
  const [enAttente, setEnAttente] = useState(0);

  useEffect(() => {
    void (async () => {
      setPlace(await placeOccupee());
      setDocuments(await base.contenus.count());
      setEnAttente(await base.operations.where("etat").equals("en_attente").count());
    })();
  }, []);

  return (
    <div className="formulaire-recherche">
      <h2>Données enregistrées sur cet appareil</h2>
      <dl className="dl-en-ligne">
        <dt>Documents hors ligne</dt>
        <dd>{documents}</dd>
        <dt>Place occupée</dt>
        <dd>{formaterTaille(place)}</dd>
        <dt>Modifications en attente</dt>
        <dd>{enAttente}</dd>
      </dl>
      <p className="aide">
        Ces documents sont chiffrés avec votre mot de passe : sans lui, ils restent
        illisibles, y compris pour qui trouverait l'appareil.
      </p>
      {enAttente > 0 && (
        <p className="alerte">
          {enAttente} modification(s) n'ont pas encore été envoyées au serveur. Vider le
          cache maintenant les perdrait définitivement — synchronisez d'abord.
        </p>
      )}
      <button
        className="lien-danger"
        onClick={async () => {
          if (
            !window.confirm(
              "Effacer toutes les données enregistrées sur cet appareil et se déconnecter ?"
            )
          )
            return;
          await viderCacheLocal();
          await surPurge();
        }}
      >
        Effacer les données de cet appareil
      </button>
    </div>
  );
}
