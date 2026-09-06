import { useState, type FormEvent } from "react";

import { ErreurAPI } from "../api/client";
import { useAuth } from "../etat/auth";

export default function Connexion() {
  const { connecter, totpRequis } = useAuth();
  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [totp, setTotp] = useState("");
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);

  async function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    setErreur("");
    setEnvoi(true);
    try {
      await connecter(email, motDePasse, totp);
    } catch (probleme) {
      if (probleme instanceof ErreurAPI) {
        const messages: Record<string, string> = {
          TOTP_REQUIRED: "Saisissez le code de votre application d'authentification.",
          TOTP_INVALID: "Code de vérification incorrect.",
          INVALID_CREDENTIALS: "Adresse e-mail ou mot de passe incorrect.",
          ACCOUNT_LOCKED:
            "Compte temporairement verrouillé après plusieurs tentatives. Réessayez dans quelques minutes.",
        };
        setErreur(messages[probleme.code] ?? String(probleme.detail));
      } else {
        setErreur(
          "Impossible de joindre le serveur. Vérifiez votre connexion ; les données déjà synchronisées restent accessibles."
        );
      }
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="page-connexion">
      <form className="carte-connexion" onSubmit={soumettre}>
        <div className="connexion-entete">
          <h1>DCUHAT</h1>
          <p>
            Direction Communale de l'Urbanisme, de l'Habitat et de l'Aménagement du
            Territoire de Lambayin
          </p>
        </div>

        <label>
          Adresse e-mail
          <input
            type="email"
            value={email}
            onChange={(evenement) => setEmail(evenement.target.value)}
            autoComplete="username"
            required
            autoFocus
          />
        </label>

        <label>
          Mot de passe
          <input
            type="password"
            value={motDePasse}
            onChange={(evenement) => setMotDePasse(evenement.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {totpRequis && (
          <label>
            Code de vérification
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={6}
              value={totp}
              onChange={(evenement) => setTotp(evenement.target.value)}
              placeholder="123456"
              autoFocus
            />
          </label>
        )}

        {erreur && <p className="erreur">{erreur}</p>}

        <button type="submit" className="bouton-principal" disabled={envoi}>
          {envoi ? "Connexion…" : "Se connecter"}
        </button>

        <p className="note-connexion">
          Votre mot de passe protège aussi les documents enregistrés sur cet appareil
          pour un usage hors ligne : ils restent illisibles sans lui.
        </p>
      </form>
    </div>
  );
}
