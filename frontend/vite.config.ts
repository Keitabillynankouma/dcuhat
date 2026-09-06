import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // En développement, l'interface et l'API sont servies par la même
    // origine : Vite relaie /api, /admin et /static vers Django. Cela évite
    // toute question de CORS sur le poste de développement — un réglage qui
    // coûte régulièrement une demi-heure de recherche pour rien — et cela
    // reproduit fidèlement la production, où Nginx joue exactement ce rôle.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/admin": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/static": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // Le découpage garde la coquille applicative légère : sur une liaison
        // de terrain, le premier chargement doit rester court.
        manualChunks: {
          carte: ["leaflet"],
          stockage: ["dexie"],
        },
      },
    },
  },
});
