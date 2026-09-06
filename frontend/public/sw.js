/*
 * Service Worker DCUHAT.
 *
 * Trois strategies, une par nature de ressource :
 *  - coquille applicative : cache d'abord, revalidation en arriere-plan, pour
 *    que l'application s'ouvre instantanement meme sans reseau ;
 *  - tuiles de la carte : cache d'abord, avec plafond, pour que la carte de la
 *    commune reste lisible sur le terrain ;
 *  - API : reseau d'abord avec repli sur le cache, car une donnee fraiche vaut
 *    toujours mieux qu'une donnee mise en cache — mais une donnee ancienne
 *    vaut infiniment mieux qu'un ecran vide.
 *
 * Les televersements et modifications ne passent jamais par le Service Worker :
 * ils sont mis en file dans IndexedDB par l'application elle-meme, qui seule
 * sait reconstruire l'ordre des operations et detecter les conflits.
 */

const VERSION = "dcuhat-v1";
const CACHE_COQUILLE = `${VERSION}-coquille`;
const CACHE_TUILES = `${VERSION}-tuiles`;
const CACHE_API = `${VERSION}-api`;
const MAX_TUILES = 1500;

const COQUILLE = ["/", "/index.html", "/manifest.webmanifest", "/icone.svg"];

self.addEventListener("install", (evenement) => {
  evenement.waitUntil(
    caches.open(CACHE_COQUILLE).then((cache) => cache.addAll(COQUILLE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evenement) => {
  evenement.waitUntil(
    caches.keys().then((noms) =>
      Promise.all(
        noms.filter((nom) => !nom.startsWith(VERSION)).map((nom) => caches.delete(nom))
      )
    ).then(() => self.clients.claim())
  );
});

async function limiterCache(nom, maximum) {
  const cache = await caches.open(nom);
  const cles = await cache.keys();
  if (cles.length > maximum) {
    await Promise.all(cles.slice(0, cles.length - maximum).map((cle) => cache.delete(cle)));
  }
}

self.addEventListener("fetch", (evenement) => {
  const requete = evenement.request;
  if (requete.method !== "GET") return;

  const url = new URL(requete.url);

  // Tuiles cartographiques.
  if (/tile\.openstreetmap|\/tiles?\//.test(url.href)) {
    evenement.respondWith(
      caches.open(CACHE_TUILES).then(async (cache) => {
        const enCache = await cache.match(requete);
        if (enCache) return enCache;
        try {
          const reponse = await fetch(requete);
          if (reponse.ok) {
            cache.put(requete, reponse.clone());
            limiterCache(CACHE_TUILES, MAX_TUILES);
          }
          return reponse;
        } catch (erreur) {
          return new Response("", { status: 504 });
        }
      })
    );
    return;
  }

  // API : reseau d'abord, repli sur le dernier etat connu.
  if (url.pathname.startsWith("/api/")) {
    evenement.respondWith(
      fetch(requete)
        .then((reponse) => {
          if (reponse.ok) {
            const copie = reponse.clone();
            caches.open(CACHE_API).then((cache) => cache.put(requete, copie));
          }
          return reponse;
        })
        .catch(async () => {
          const enCache = await caches.match(requete);
          if (enCache) {
            const entetes = new Headers(enCache.headers);
            entetes.set("X-DCUHAT-Hors-Ligne", "1");
            return new Response(await enCache.blob(), {
              status: enCache.status,
              headers: entetes,
            });
          }
          return new Response(
            JSON.stringify({
              code: "HORS_LIGNE",
              detail: "Donnée indisponible hors ligne.",
            }),
            { status: 503, headers: { "Content-Type": "application/json" } }
          );
        })
    );
    return;
  }

  // Coquille applicative.
  evenement.respondWith(
    caches.open(CACHE_COQUILLE).then(async (cache) => {
      const enCache = await cache.match(requete);
      const reseau = fetch(requete)
        .then((reponse) => {
          if (reponse.ok) cache.put(requete, reponse.clone());
          return reponse;
        })
        .catch(() => enCache || cache.match("/index.html"));
      return enCache || reseau;
    })
  );
});

// Le navigateur previent l'application des que le reseau revient ; c'est elle
// qui declenche la synchronisation, pas le Service Worker.
self.addEventListener("message", (evenement) => {
  if (evenement.data === "SKIP_WAITING") self.skipWaiting();
});
