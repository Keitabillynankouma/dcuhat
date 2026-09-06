import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useAuth } from "../etat/auth";
import { useReseau } from "../etat/reseau";
import type { Notification } from "../types";

const LIENS = [
  { vers: "/dossiers", libelle: "Dossiers", icone: "📁" },
  { vers: "/carte", libelle: "Carte", icone: "🗺️" },
  { vers: "/recherche", libelle: "Recherche", icone: "🔍" },
  { vers: "/corbeille", libelle: "Corbeille", icone: "🗑️" },
  { vers: "/conflits", libelle: "Conflits", icone: "⚠️" },
  { vers: "/journal", libelle: "Journal", icone: "📋" },
];

//: Réservé aux administrateurs de la plateforme.
const LIENS_ADMIN = [
  { vers: "/administration", libelle: "Administration", icone: "⚙️" },
];

export default function MiseEnPage({ children }: { children: ReactNode }) {
  const { utilisateur, deconnecter } = useAuth();
  const { enLigne, synchronisation, message, enAttente, lancerSynchronisation } = useReseau();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [panneauOuvert, setPanneauOuvert] = useState(false);
  const [menuMobile, setMenuMobile] = useState(false);
  const naviguer = useNavigate();

  useEffect(() => {
    if (!enLigne) return;
    api
      .get<{ results: Notification[] }>("/notifications/?non_lues=1")
      .then((donnees) => setNotifications(donnees.results ?? []))
      .catch(() => undefined);
  }, [enLigne]);

  return (
    <div className="application">
      <header className="entete">
        <button
          className="bouton-menu"
          onClick={() => setMenuMobile((ouvert) => !ouvert)}
          aria-label="Afficher le menu"
        >
          ☰
        </button>
        <div className="marque">
          <span className="marque-sigle">DCUHAT</span>
          <span className="marque-detail">
            Direction Communale de l'Urbanisme, de l'Habitat et de l'Aménagement du
            Territoire — Lambayin
          </span>
        </div>

        <div className="entete-actions">
          <span
            className={`pastille-reseau ${enLigne ? "en-ligne" : "hors-ligne"}`}
            title={enLigne ? "Connecté" : "Hors ligne — le travail est conservé localement"}
          >
            {enLigne ? "En ligne" : "Hors ligne"}
          </span>

          <button
            className="bouton-sync"
            onClick={() => void lancerSynchronisation()}
            disabled={synchronisation || !enLigne}
            title="Synchroniser maintenant"
          >
            {synchronisation ? "Synchronisation…" : "Synchroniser"}
            {enAttente > 0 && <span className="badge">{enAttente}</span>}
          </button>

          <button
            className="bouton-icone"
            onClick={() => setPanneauOuvert((ouvert) => !ouvert)}
            aria-label="Notifications"
          >
            🔔{notifications.length > 0 && <span className="badge">{notifications.length}</span>}
          </button>

          <NavLink to="/mon-compte" className="agent" title="Mon compte">
            <span className="agent-nom">{utilisateur?.nom_complet || utilisateur?.email}</span>
            <span className="agent-role">{utilisateur?.service_nom ?? utilisateur?.role}</span>
          </NavLink>

          <button
            className="bouton-secondaire"
            onClick={async () => {
              await deconnecter();
              naviguer("/connexion");
            }}
          >
            Quitter
          </button>
        </div>
      </header>

      {message && <div className="bandeau-message">{message}</div>}

      {utilisateur?.must_change_password && (
        <div className="bandeau-alerte">
          Votre mot de passe est provisoire.{" "}
          <NavLink to="/mon-compte">Changez-le dès maintenant</NavLink> — il protège
          aussi les documents enregistrés hors ligne sur cet appareil.
        </div>
      )}

      <div className="corps">
        <nav className={`navigation ${menuMobile ? "ouverte" : ""}`}>
          {[...LIENS, ...(utilisateur?.role === "ADMIN" ? LIENS_ADMIN : [])].map((lien) => (
            <NavLink
              key={lien.vers}
              to={lien.vers}
              className={({ isActive }) => `lien-nav ${isActive ? "actif" : ""}`}
              onClick={() => setMenuMobile(false)}
            >
              <span aria-hidden>{lien.icone}</span>
              {lien.libelle}
            </NavLink>
          ))}
        </nav>

        <main className="contenu">{children}</main>

        {panneauOuvert && (
          <aside className="panneau-notifications">
            <h2>Notifications</h2>
            {notifications.length === 0 && <p className="vide">Aucune notification.</p>}
            {notifications.map((notification) => (
              <article key={notification.id} className="notification">
                <h3>{notification.title}</h3>
                <p>{notification.body}</p>
              </article>
            ))}
          </aside>
        )}
      </div>
    </div>
  );
}
