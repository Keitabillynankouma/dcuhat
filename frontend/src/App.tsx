import { Navigate, Route, Routes } from "react-router-dom";

import MiseEnPage from "./composants/MiseEnPage";
import { useAuth } from "./etat/auth";
import Administration from "./pages/Administration";
import Carte from "./pages/Carte";
import Conflits from "./pages/Conflits";
import Connexion from "./pages/Connexion";
import Corbeille from "./pages/Corbeille";
import Editeur from "./pages/Editeur";
import Explorateur from "./pages/Explorateur";
import Fichier from "./pages/Fichier";
import Journal from "./pages/Journal";
import MonCompte from "./pages/MonCompte";
import Recherche from "./pages/Recherche";

export default function App() {
  const { utilisateur, chargement } = useAuth();

  if (chargement) {
    return (
      <div className="ecran-chargement">
        <div className="pastille-chargement" aria-hidden />
        <p>Chargement de l'espace documentaire…</p>
      </div>
    );
  }

  if (!utilisateur) {
    return (
      <Routes>
        <Route path="/connexion" element={<Connexion />} />
        <Route path="*" element={<Navigate to="/connexion" replace />} />
      </Routes>
    );
  }

  return (
    <MiseEnPage>
      <Routes>
        <Route path="/" element={<Navigate to="/dossiers" replace />} />
        <Route path="/dossiers" element={<Explorateur />} />
        <Route path="/dossiers/:dossierId" element={<Explorateur />} />
        <Route path="/fichiers/:fichierId" element={<Fichier />} />
        <Route path="/fichiers/:fichierId/editer" element={<Editeur />} />
        <Route path="/carte" element={<Carte />} />
        <Route path="/recherche" element={<Recherche />} />
        <Route path="/corbeille" element={<Corbeille />} />
        <Route path="/conflits" element={<Conflits />} />
        <Route path="/journal" element={<Journal />} />
        <Route path="/administration" element={<Administration />} />
        <Route path="/mon-compte" element={<MonCompte />} />
        <Route path="*" element={<Navigate to="/dossiers" replace />} />
      </Routes>
    </MiseEnPage>
  );
}
