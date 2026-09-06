/**
 * Chiffrement du cache local.
 *
 * Les fichiers rendus disponibles hors ligne sont stockés chiffrés dans
 * IndexedDB : une tablette de terrain se perd, et les dossiers d'urbanisme
 * d'une commune ne doivent pas être lisibles par celui qui la ramasse.
 *
 * La clé est dérivée du mot de passe de l'agent par PBKDF2 et n'est jamais
 * persistée : elle vit en mémoire le temps de la session. Sans le mot de passe,
 * le contenu du cache reste illisible.
 */

const ITERATIONS = 310_000;
const ALGORITHME = "AES-GCM";

let cleSession: CryptoKey | null = null;

export async function deriverCle(motDePasse: string, sel: string): Promise<CryptoKey> {
  const encodeur = new TextEncoder();
  const materiel = await crypto.subtle.importKey(
    "raw",
    encodeur.encode(motDePasse),
    "PBKDF2",
    false,
    ["deriveKey"]
  );
  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: encodeur.encode(sel),
      iterations: ITERATIONS,
      hash: "SHA-256",
    },
    materiel,
    { name: ALGORITHME, length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}

export async function ouvrirSession(motDePasse: string, sel: string): Promise<void> {
  cleSession = await deriverCle(motDePasse, sel);
}

export function fermerSession(): void {
  cleSession = null;
}

export function sessionOuverte(): boolean {
  return cleSession !== null;
}

export async function chiffrer(donnees: ArrayBuffer): Promise<ArrayBuffer> {
  if (!cleSession) throw new Error("Aucune clé de session : reconnectez-vous.");
  const vecteur = crypto.getRandomValues(new Uint8Array(12));
  const chiffre = await crypto.subtle.encrypt(
    { name: ALGORITHME, iv: vecteur },
    cleSession,
    donnees
  );
  // Le vecteur d'initialisation est stocké en tête du blob : il n'est pas
  // secret, mais il doit être unique par enregistrement.
  const resultat = new Uint8Array(vecteur.length + chiffre.byteLength);
  resultat.set(vecteur, 0);
  resultat.set(new Uint8Array(chiffre), vecteur.length);
  return resultat.buffer;
}

export async function dechiffrer(blob: ArrayBuffer): Promise<ArrayBuffer> {
  if (!cleSession) throw new Error("Aucune clé de session : reconnectez-vous.");
  const donnees = new Uint8Array(blob);
  const vecteur = donnees.slice(0, 12);
  const chiffre = donnees.slice(12);
  return crypto.subtle.decrypt({ name: ALGORITHME, iv: vecteur }, cleSession, chiffre);
}

export async function empreinte(donnees: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", donnees);
  return Array.from(new Uint8Array(digest))
    .map((octet) => octet.toString(16).padStart(2, "0"))
    .join("");
}
