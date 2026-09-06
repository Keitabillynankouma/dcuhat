/**
 * Client HTTP de l'API DCUHAT.
 *
 * Deux responsabilités particulières :
 *  - renouveler silencieusement le jeton d'accès (15 minutes) sans jamais
 *    interrompre le travail de l'agent ;
 *  - distinguer une erreur métier d'une absence de réseau, car la première
 *    doit être montrée et la seconde doit basculer l'application en mode hors
 *    ligne plutôt qu'afficher une erreur.
 */

const BASE = import.meta.env.VITE_API_URL ?? "/api/v1";

export class ErreurAPI extends Error {
  constructor(
    public code: string,
    public detail: unknown,
    public statut: number
  ) {
    super(typeof detail === "string" ? detail : code);
  }
}

export class HorsLigne extends Error {
  constructor() {
    super("Aucune connexion : l'action a été mise en file d'attente.");
  }
}

let jetonAcces: string | null = null;
let jetonRefresh: string | null = null;
let renouvellementEnCours: Promise<boolean> | null = null;

export function definirJetons(acces: string | null, refresh: string | null): void {
  jetonAcces = acces;
  jetonRefresh = refresh;
  if (acces) localStorage.setItem("dcuhat.acces", acces);
  else localStorage.removeItem("dcuhat.acces");
  if (refresh) localStorage.setItem("dcuhat.refresh", refresh);
  else localStorage.removeItem("dcuhat.refresh");
}

export function restaurerJetons(): void {
  jetonAcces = localStorage.getItem("dcuhat.acces");
  jetonRefresh = localStorage.getItem("dcuhat.refresh");
}

export function estConnecte(): boolean {
  return Boolean(jetonAcces);
}

async function renouveler(): Promise<boolean> {
  if (!jetonRefresh) return false;
  if (renouvellementEnCours) return renouvellementEnCours;
  renouvellementEnCours = (async () => {
    try {
      const reponse = await fetch(`${BASE}/auth/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: jetonRefresh }),
      });
      if (!reponse.ok) return false;
      const donnees = await reponse.json();
      definirJetons(donnees.access, donnees.refresh ?? jetonRefresh);
      return true;
    } catch {
      return false;
    } finally {
      renouvellementEnCours = null;
    }
  })();
  return renouvellementEnCours;
}

interface Options {
  methode?: string;
  corps?: unknown;
  brut?: BodyInit;
  entetes?: Record<string, string>;
  signal?: AbortSignal;
}

export async function appeler<T = unknown>(chemin: string, options: Options = {}): Promise<T> {
  const executer = async (): Promise<Response> => {
    const entetes: Record<string, string> = { ...(options.entetes ?? {}) };
    if (jetonAcces) entetes.Authorization = `Bearer ${jetonAcces}`;
    let corps: BodyInit | undefined = options.brut;
    if (options.corps !== undefined && !options.brut) {
      if (options.corps instanceof FormData) {
        corps = options.corps;
      } else {
        entetes["Content-Type"] = "application/json";
        corps = JSON.stringify(options.corps);
      }
    }
    return fetch(`${BASE}${chemin}`, {
      method: options.methode ?? "GET",
      headers: entetes,
      body: corps,
      signal: options.signal,
    });
  };

  let reponse: Response;
  try {
    reponse = await executer();
  } catch {
    throw new HorsLigne();
  }

  if (reponse.status === 401 && jetonRefresh) {
    if (await renouveler()) {
      reponse = await executer();
    }
  }

  if (reponse.status === 204) return undefined as T;

  const typeContenu = reponse.headers.get("Content-Type") ?? "";
  const charge = typeContenu.includes("application/json")
    ? await reponse.json().catch(() => null)
    : await reponse.text();

  if (!reponse.ok) {
    const code = (charge as { code?: string })?.code ?? `HTTP_${reponse.status}`;
    const detail = (charge as { detail?: unknown })?.detail ?? charge;
    if (code === "HORS_LIGNE") throw new HorsLigne();
    throw new ErreurAPI(code, detail, reponse.status);
  }
  return charge as T;
}

/** Indique si la réponse provient du cache du Service Worker. */
export async function appelerAvecFraicheur<T>(
  chemin: string
): Promise<{ donnees: T; horsLigne: boolean }> {
  const entetes: Record<string, string> = {};
  if (jetonAcces) entetes.Authorization = `Bearer ${jetonAcces}`;
  try {
    const reponse = await fetch(`${BASE}${chemin}`, { headers: entetes });
    const donnees = (await reponse.json()) as T;
    return { donnees, horsLigne: reponse.headers.get("X-DCUHAT-Hors-Ligne") === "1" };
  } catch {
    throw new HorsLigne();
  }
}

export const api = {
  base: BASE,
  get: <T>(chemin: string) => appeler<T>(chemin),
  post: <T>(chemin: string, corps?: unknown) =>
    appeler<T>(chemin, { methode: "POST", corps }),
  patch: <T>(chemin: string, corps?: unknown) =>
    appeler<T>(chemin, { methode: "PATCH", corps }),
  put: <T>(chemin: string, corps?: unknown) =>
    appeler<T>(chemin, { methode: "PUT", corps }),
  delete: <T>(chemin: string) => appeler<T>(chemin, { methode: "DELETE" }),
};
