import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, ErreurAPI } from "../api/client";
import { useAuth } from "../etat/auth";
import type {
  PageResultats,
  Role,
  ServiceComplet,
  Statistiques,
  Utilisateur,
} from "../types";
import {
  EXPLICATIONS_ROLE,
  LIBELLES_ROLE,
  formaterDate,
  formaterTaille,
  pourcentage,
} from "../utilitaires";

const ROLES: Role[] = ["ADMIN", "DIRECTEUR", "CHEF_SERVICE", "AGENT", "LECTEUR", "INVITE"];

type Onglet = "tableau" | "agents" | "services";

export default function Administration() {
  const { utilisateur } = useAuth();
  const [onglet, setOnglet] = useState<Onglet>("tableau");

  if (utilisateur?.role !== "ADMIN") {
    return (
      <section>
        <h1>Administration</h1>
        <p className="alerte">
          Cette section est réservée aux administrateurs de la plateforme.
        </p>
      </section>
    );
  }

  return (
    <section>
      <h1>Administration</h1>
      <p className="sous-titre">
        Comptes, rôles, services et quotas de la Direction.
      </p>

      <div className="onglets">
        <button
          className={onglet === "tableau" ? "actif" : ""}
          onClick={() => setOnglet("tableau")}
        >
          Tableau de bord
        </button>
        <button
          className={onglet === "agents" ? "actif" : ""}
          onClick={() => setOnglet("agents")}
        >
          Agents
        </button>
        <button
          className={onglet === "services" ? "actif" : ""}
          onClick={() => setOnglet("services")}
        >
          Services
        </button>
      </div>

      {onglet === "tableau" && <TableauDeBord />}
      {onglet === "agents" && <GestionAgents />}
      {onglet === "services" && <GestionServices />}

      <footer className="pied-administration">
        <p>
          Les opérations courantes se font ici. Pour les cas rares — corriger une
          donnée à la main, inspecter une table, purger un enregistrement —
          l'administration technique de Django reste accessible :{" "}
          <a href="/admin/" target="_blank" rel="noopener noreferrer">
            ouvrir l'administration Django
          </a>
          . Elle donne un accès direct à la base : n'y touchez qu'en sachant ce que
          vous faites, et jamais pour ce que cette page sait déjà faire.
        </p>
      </footer>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Tableau de bord                                                     */
/* ------------------------------------------------------------------ */
function TableauDeBord() {
  const [stats, setStats] = useState<Statistiques | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api
      .get<Statistiques>("/auth/statistiques/")
      .then(setStats)
      .catch((probleme) => setMessage((probleme as Error).message));
  }, []);

  if (message) return <p className="alerte">{message}</p>;
  if (!stats) return <p className="chargement">Chargement des chiffres…</p>;

  return (
    <>
      <div className="grille-chiffres">
        <Chiffre valeur={stats.agents.actifs} libelle="Agents actifs"
          detail={`${stats.agents.total} comptes au total`} />
        <Chiffre valeur={stats.services} libelle="Services" />
        <Chiffre valeur={stats.dossiers} libelle="Dossiers" />
        <Chiffre valeur={stats.fichiers.total} libelle="Fichiers"
          detail={`dont ${stats.fichiers.geospatiaux} géoréférencés`} />
        <Chiffre valeur={formaterTaille(stats.stockage_octets)} libelle="Stockage occupé"
          detail="toutes versions comprises" />
        <Chiffre valeur={stats.activite_7_jours} libelle="Actions sur 7 jours" />
      </div>

      {stats.conflits_ouverts > 0 && (
        <p className="alerte">
          {stats.conflits_ouverts} conflit(s) de synchronisation attendent un arbitrage.
        </p>
      )}
      {stats.fichiers.corbeille > 0 && (
        <p className="aide">
          {stats.fichiers.corbeille} fichier(s) en corbeille occupent encore de l'espace
          tant qu'ils ne sont pas purgés.
        </p>
      )}

      <h2>Répartition des comptes</h2>
      <table className="tableau">
        <thead>
          <tr>
            <th>Rôle</th>
            <th>Comptes</th>
            <th>Ce que le rôle permet</th>
          </tr>
        </thead>
        <tbody>
          {stats.agents.par_role.map((ligne) => (
            <tr key={ligne.role}>
              <td>{LIBELLES_ROLE[ligne.role] ?? ligne.role}</td>
              <td>{ligne.nombre}</td>
              <td className="chemin">{EXPLICATIONS_ROLE[ligne.role]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Chiffre({
  valeur,
  libelle,
  detail,
}: {
  valeur: number | string;
  libelle: string;
  detail?: string;
}) {
  return (
    <div className="carte-chiffre">
      <span className="chiffre-valeur">{valeur}</span>
      <span className="chiffre-libelle">{libelle}</span>
      {detail && <span className="chiffre-detail">{detail}</span>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Agents                                                              */
/* ------------------------------------------------------------------ */
function GestionAgents() {
  const { utilisateur: courant } = useAuth();
  const [agents, setAgents] = useState<Utilisateur[]>([]);
  const [services, setServices] = useState<ServiceComplet[]>([]);
  const [recherche, setRecherche] = useState("");
  const [filtreRole, setFiltreRole] = useState("");
  const [message, setMessage] = useState("");
  const [motDePasse, setMotDePasse] = useState<{ agent: string; valeur: string } | null>(null);
  const [formulaireOuvert, setFormulaireOuvert] = useState(false);

  const charger = useCallback(async () => {
    const parametres = new URLSearchParams();
    if (recherche) parametres.set("q", recherche);
    if (filtreRole) parametres.set("role", filtreRole);
    try {
      const donnees = await api.get<PageResultats<Utilisateur>>(
        `/auth/users/?${parametres.toString()}`
      );
      setAgents(donnees.results);
    } catch (probleme) {
      setMessage((probleme as Error).message);
    }
  }, [recherche, filtreRole]);

  useEffect(() => {
    void charger();
    api
      .get<PageResultats<ServiceComplet>>("/auth/services/")
      .then((donnees) => setServices(donnees.results))
      .catch(() => undefined);
  }, [charger]);

  async function changerRole(agent: Utilisateur, role: string) {
    try {
      await api.post(`/auth/users/${agent.id}/role/`, { role });
      setMessage(`${agent.nom_complet || agent.email} est désormais ${LIBELLES_ROLE[role]}.`);
      await charger();
    } catch (probleme) {
      setMessage(
        probleme instanceof ErreurAPI ? String(probleme.detail) : (probleme as Error).message
      );
    }
  }

  async function changerService(agent: Utilisateur, service: string) {
    await api.patch(`/auth/users/${agent.id}/`, { service: service || null });
    await charger();
  }

  async function basculerActivation(agent: Utilisateur) {
    try {
      if (agent.is_active) {
        if (
          !window.confirm(
            `Désactiver le compte de ${agent.nom_complet || agent.email} ? Il ne pourra plus se connecter, mais tout son historique est conservé.`
          )
        )
          return;
        await api.delete(`/auth/users/${agent.id}/`);
      } else {
        await api.post(`/auth/users/${agent.id}/activer/`);
      }
      await charger();
    } catch (probleme) {
      setMessage(
        probleme instanceof ErreurAPI ? String(probleme.detail) : (probleme as Error).message
      );
    }
  }

  async function reinitialiser(agent: Utilisateur) {
    if (
      !window.confirm(
        `Générer un nouveau mot de passe provisoire pour ${agent.nom_complet || agent.email} ? L'ancien cessera immédiatement de fonctionner.`
      )
    )
      return;
    const reponse = await api.post<{ mot_de_passe_provisoire: string }>(
      `/auth/users/${agent.id}/reinitialiser-mot-de-passe/`
    );
    setMotDePasse({
      agent: agent.nom_complet || agent.email,
      valeur: reponse.mot_de_passe_provisoire,
    });
    await charger();
  }

  return (
    <>
      <div className="barre-actions">
        <div className="ligne-formulaire">
          <label className="champ-large">
            Rechercher
            <input
              value={recherche}
              onChange={(evenement) => setRecherche(evenement.target.value)}
              placeholder="nom, e-mail, matricule…"
            />
          </label>
          <label>
            Rôle
            <select
              value={filtreRole}
              onChange={(evenement) => setFiltreRole(evenement.target.value)}
            >
              <option value="">Tous</option>
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {LIBELLES_ROLE[role]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button
          className="bouton-principal"
          onClick={() => setFormulaireOuvert((ouvert) => !ouvert)}
        >
          {formulaireOuvert ? "Fermer" : "Nouvel agent"}
        </button>
      </div>

      {formulaireOuvert && (
        <FormulaireAgent
          services={services}
          surCreation={async (nom, provisoire) => {
            setMotDePasse(provisoire ? { agent: nom, valeur: provisoire } : null);
            setFormulaireOuvert(false);
            await charger();
          }}
        />
      )}

      {motDePasse && (
        <div className="bloc-mot-de-passe">
          <h3>Mot de passe provisoire de {motDePasse.agent}</h3>
          <code>{motDePasse.valeur}</code>
          <p>
            Il n'est affiché qu'une seule fois. Transmettez-le à l'agent : il devra le
            changer à sa première connexion.
          </p>
          <button className="bouton-secondaire" onClick={() => setMotDePasse(null)}>
            J'ai noté
          </button>
        </div>
      )}

      {message && <p className="alerte">{message}</p>}

      <table className="tableau">
        <thead>
          <tr>
            <th>Agent</th>
            <th>Rôle</th>
            <th>Service</th>
            <th>Statut</th>
            <th>Créé le</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {agents.map((agent) => (
            <tr key={agent.id} className={agent.is_active ? "" : "ligne-inactive"}>
              <td>
                <strong>{agent.nom_complet || "—"}</strong>
                <br />
                <span className="chemin">{agent.email}</span>
              </td>
              <td>
                <select
                  value={agent.role}
                  disabled={agent.id === courant?.id}
                  onChange={(evenement) => void changerRole(agent, evenement.target.value)}
                  title={EXPLICATIONS_ROLE[agent.role]}
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {LIBELLES_ROLE[role]}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <select
                  value={agent.service ?? ""}
                  onChange={(evenement) => void changerService(agent, evenement.target.value)}
                >
                  <option value="">Aucun</option>
                  {services.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.name}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                {agent.is_active ? (
                  <span className="etiquette">actif</span>
                ) : (
                  <span className="etiquette alerte">désactivé</span>
                )}
                {agent.must_change_password && (
                  <span className="etiquette">mot de passe à changer</span>
                )}
              </td>
              <td>{formaterDate(agent.created_at ?? "")}</td>
              <td className="cellule-actions">
                <button className="lien" onClick={() => void reinitialiser(agent)}>
                  Mot de passe
                </button>
                {agent.id !== courant?.id && (
                  <button
                    className={agent.is_active ? "lien-danger" : "lien"}
                    onClick={() => void basculerActivation(agent)}
                  >
                    {agent.is_active ? "Désactiver" : "Réactiver"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {agents.length === 0 && <p className="vide">Aucun agent ne correspond.</p>}

      <p className="aide-bas">
        Un compte n'est jamais supprimé, seulement désactivé : le journal d'activité
        attribue chaque action à un agent nommé, et supprimer le compte rendrait
        l'historique illisible.
      </p>
    </>
  );
}

function FormulaireAgent({
  services,
  surCreation,
}: {
  services: ServiceComplet[];
  surCreation: (nom: string, motDePasseProvisoire: string) => Promise<void>;
}) {
  const [champs, setChamps] = useState({
    email: "",
    first_name: "",
    last_name: "",
    matricule: "",
    fonction: "",
    phone: "",
    role: "AGENT" as Role,
    service: "",
    password: "",
  });
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);

  function modifier(champ: keyof typeof champs, valeur: string) {
    setChamps((actuel) => ({ ...actuel, [champ]: valeur }));
  }

  async function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    setErreur("");
    setEnvoi(true);
    try {
      const reponse = await api.post<{
        mot_de_passe_provisoire: string;
        first_name: string;
        last_name: string;
        email: string;
      }>("/auth/users/", {
        ...champs,
        service: champs.service || null,
        matricule: champs.matricule || null,
        password: champs.password || undefined,
      });
      await surCreation(
        `${reponse.first_name} ${reponse.last_name}`.trim() || reponse.email,
        reponse.mot_de_passe_provisoire
      );
    } catch (probleme) {
      if (probleme instanceof ErreurAPI) {
        const detail = probleme.detail;
        setErreur(
          typeof detail === "string"
            ? detail
            : Object.entries(detail as Record<string, string[]>)
                .map(([champ, messages]) => `${champ} : ${messages.join(" ")}`)
                .join(" — ")
        );
      } else {
        setErreur((probleme as Error).message);
      }
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form className="formulaire-recherche" onSubmit={soumettre}>
      <h2>Nouvel agent</h2>
      <div className="ligne-formulaire">
        <label className="champ-large">
          Adresse e-mail
          <input
            type="email"
            required
            value={champs.email}
            onChange={(evenement) => modifier("email", evenement.target.value)}
            placeholder="prenom.nom@lambayin.gov"
          />
        </label>
        <label>
          Prénom
          <input
            value={champs.first_name}
            onChange={(evenement) => modifier("first_name", evenement.target.value)}
          />
        </label>
        <label>
          Nom
          <input
            value={champs.last_name}
            onChange={(evenement) => modifier("last_name", evenement.target.value)}
          />
        </label>
      </div>

      <div className="ligne-formulaire">
        <label>
          Rôle
          <select
            value={champs.role}
            onChange={(evenement) => modifier("role", evenement.target.value)}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {LIBELLES_ROLE[role]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Service
          <select
            value={champs.service}
            onChange={(evenement) => modifier("service", evenement.target.value)}
          >
            <option value="">Aucun</option>
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {service.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Matricule
          <input
            value={champs.matricule}
            onChange={(evenement) => modifier("matricule", evenement.target.value)}
          />
        </label>
        <label className="champ-large">
          Fonction
          <input
            value={champs.fonction}
            onChange={(evenement) => modifier("fonction", evenement.target.value)}
            placeholder="Technicien topographe"
          />
        </label>
      </div>

      <p className="aide">{EXPLICATIONS_ROLE[champs.role]}</p>

      <div className="ligne-formulaire">
        <label className="champ-large">
          Mot de passe provisoire (facultatif)
          <input
            type="text"
            value={champs.password}
            onChange={(evenement) => modifier("password", evenement.target.value)}
            placeholder="laissez vide pour en générer un automatiquement"
          />
        </label>
        <button type="submit" className="bouton-principal" disabled={envoi}>
          {envoi ? "Création…" : "Créer le compte"}
        </button>
      </div>

      {erreur && <p className="erreur">{erreur}</p>}
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Services                                                            */
/* ------------------------------------------------------------------ */
function GestionServices() {
  const [services, setServices] = useState<ServiceComplet[]>([]);
  const [nom, setNom] = useState("");
  const [code, setCode] = useState("");
  const [quotaGo, setQuotaGo] = useState("50");
  const [message, setMessage] = useState("");

  const charger = useCallback(async () => {
    const donnees = await api.get<PageResultats<ServiceComplet>>("/auth/services/");
    setServices(donnees.results);
  }, []);

  useEffect(() => {
    void charger();
  }, [charger]);

  async function creer(evenement: FormEvent) {
    evenement.preventDefault();
    setMessage("");
    try {
      await api.post("/auth/services/", {
        name: nom,
        code: code.toUpperCase().replace(/[^A-Z0-9_]/g, "_"),
        quota_bytes: Number(quotaGo) * 1024 ** 3,
      });
      setNom("");
      setCode("");
      await charger();
    } catch (probleme) {
      setMessage(
        probleme instanceof ErreurAPI ? JSON.stringify(probleme.detail) : (probleme as Error).message
      );
    }
  }

  async function modifierQuota(service: ServiceComplet) {
    const saisie = window.prompt(
      `Quota du ${service.name}, en Go`,
      String(Math.round(service.quota_effectif / 1024 ** 3))
    );
    if (!saisie) return;
    await api.patch(`/auth/services/${service.id}/`, {
      quota_bytes: Number(saisie) * 1024 ** 3,
    });
    await charger();
  }

  return (
    <>
      <form className="formulaire-recherche" onSubmit={creer}>
        <h2>Nouveau service</h2>
        <div className="ligne-formulaire">
          <label className="champ-large">
            Nom
            <input
              required
              value={nom}
              onChange={(evenement) => setNom(evenement.target.value)}
              placeholder="Service des Espaces Verts"
            />
          </label>
          <label>
            Code
            <input
              required
              value={code}
              onChange={(evenement) => setCode(evenement.target.value)}
              placeholder="ESPACES_VERTS"
            />
          </label>
          <label>
            Quota (Go)
            <input
              type="number"
              min={1}
              value={quotaGo}
              onChange={(evenement) => setQuotaGo(evenement.target.value)}
            />
          </label>
          <button type="submit" className="bouton-principal">
            Créer
          </button>
        </div>
        {message && <p className="erreur">{message}</p>}
      </form>

      <table className="tableau">
        <thead>
          <tr>
            <th>Service</th>
            <th>Code</th>
            <th>Agents</th>
            <th>Espace utilisé</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {services.map((service) => {
            const taux = pourcentage(service.usage_octets, service.quota_effectif);
            return (
              <tr key={service.id}>
                <td>
                  <strong>{service.name}</strong>
                  {!service.is_active && <span className="etiquette alerte">inactif</span>}
                </td>
                <td className="chemin">{service.code}</td>
                <td>{service.nombre_agents}</td>
                <td>
                  <div className="jauge" title={`${taux} % du quota`}>
                    <div
                      className={`jauge-remplissage ${taux > 85 ? "critique" : ""}`}
                      style={{ width: `${taux}%` }}
                    />
                  </div>
                  <span className="chemin">
                    {formaterTaille(service.usage_octets)} sur{" "}
                    {formaterTaille(service.quota_effectif)} ({taux} %)
                  </span>
                </td>
                <td className="cellule-actions">
                  <button className="lien" onClick={() => void modifierQuota(service)}>
                    Modifier le quota
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <p className="aide-bas">
        L'espace utilisé compte <strong>toutes</strong> les versions conservées, pas
        seulement les fichiers courants : c'est ce qui occupe réellement le disque.
        Purger la corbeille est le premier geste quand un service approche de son quota.
      </p>
    </>
  );
}
