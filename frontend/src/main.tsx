import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { FournisseurAuth } from "./etat/auth";
import { FournisseurReseau } from "./etat/reseau";
import "./styles.css";

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // L'absence de Service Worker dégrade le hors ligne mais n'empêche pas
      // l'application de fonctionner en ligne.
    });
  });
}

createRoot(document.getElementById("racine")!).render(
  <StrictMode>
    <BrowserRouter>
      <FournisseurAuth>
        <FournisseurReseau>
          <App />
        </FournisseurReseau>
      </FournisseurAuth>
    </BrowserRouter>
  </StrictMode>
);
