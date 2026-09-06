# Plan de déploiement et de maintenance — DCUHAT

---

## 1. Choix de l'hébergement

Deux options, à trancher par la Direction. Elles n'ont pas les mêmes fragilités.

| | Serveur à la mairie | VPS chez un hébergeur |
|---|---|---|
| Souveraineté des données | Totale | Contractuelle |
| Fonctionne sans internet | Oui, en réseau local | Non |
| Dépend de l'électricité | Oui — onduleur indispensable | Non |
| Sauvegardes hors site | À organiser explicitement | Souvent incluses |
| Coût | Investissement initial | Abonnement mensuel |
| Compétence requise sur place | Réelle | Faible |

**Recommandation.** Si la liaison internet de la mairie est instable, le serveur local est
le choix cohérent avec l'objectif du projet — mais il n'a de sens qu'accompagné d'un
onduleur et d'une sauvegarde hors site réellement testée. Un serveur local dont les
sauvegardes dorment sur le même disque n'est pas une garantie, c'est un point unique de
défaillance.

### Dimensionnement indicatif

| Usage | Processeur | Mémoire | Disque |
|---|---|---|---|
| 10 agents, archives modestes | 2 cœurs | 4 Go | 250 Go SSD |
| 30 agents, données topographiques | 4 cœurs | 8 Go | 1 To SSD |
| 60 agents, orthophotos | 8 cœurs | 16 Go | 2 To SSD + archivage |

Le disque est dimensionné par les **versions**, pas par les fichiers : comptez environ
deux fois et demie le volume utile.

---

## 2. Mise en production

### 2.1 Préparation du serveur

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker "$USER"     # puis reconnectez-vous
```

### 2.2 Installation

```bash
git clone <dépôt> /opt/dcuhat && cd /opt/dcuhat
cp .env.example .env
```

Renseignez dans `.env`, **sans laisser aucune valeur d'exemple** :

- `DJANGO_SECRET_KEY` — 50 caractères aléatoires (`openssl rand -base64 48`)
- `DJANGO_DEBUG=0` — impératif en production
- `ALLOWED_HOSTS` — le nom d'hôte réel de la plateforme
- `POSTGRES_PASSWORD`, `S3_SECRET_KEY` — mots de passe longs et uniques
- `CORS_ALLOWED_ORIGINS` — l'adresse exacte de l'interface

```bash
docker compose up -d --build
docker compose exec api python manage.py initialiser_dcuhat --admin-email=...
```

### 2.3 TLS

Le chiffrement du transport n'est pas négociable : des dossiers d'urbanisme circulent sur
ce réseau.

- **Serveur exposé sur internet** : Let's Encrypt (certbot), renouvellement automatique.
- **Serveur en réseau local** : autorité interne ou certificat auto-signé installé sur les
  postes. Un certificat auto-signé que les agents apprennent à « accepter malgré
  l'avertissement » les entraîne à ignorer les alertes de sécurité — installez-le
  réellement sur les postes.

Le modèle `deploy/nginx.conf` contient la configuration TLS, les en-têtes de sécurité et
les limites de taille adaptées aux levés topographiques.

### 2.4 Recette avant ouverture aux agents

- [ ] Connexion, changement de mot de passe imposé, 2FA sur les comptes ADMIN et DIRECTEUR
- [ ] Un agent d'un service ne voit pas l'espace d'un autre service
- [ ] Téléversement d'un fichier de plus de 100 Mo, interruption volontaire du réseau, reprise
- [ ] Dépôt d'un Shapefile zippé : emprise correcte sur la carte
- [ ] Dépôt d'un fichier sans `.prj` : la plateforme demande la projection, ne la devine pas
- [ ] Mode avion : consultation d'un document mis hors ligne, création d'un dossier, retour du réseau, synchronisation
- [ ] Conflit provoqué volontairement : les deux versions sont présentes
- [ ] Suppression puis restauration depuis la corbeille
- [ ] Sauvegarde exécutée **et restaurée** sur un environnement de test
- [ ] Journal d'activité complet et exportable

---

## 3. Sauvegardes

Trois éléments à sauvegarder, et un seul suffit à rendre les autres inutiles s'il manque :

1. **La base PostgreSQL** — l'arborescence, les droits, les métadonnées, le journal.
2. **Le stockage objet** — les contenus des fichiers et de toutes leurs versions.
3. **Le fichier `.env`** — sans lui, une restauration ne redémarre pas.

```bash
# Quotidien, à 2 h
0 2 * * * /opt/dcuhat/deploy/sauvegarde.sh >> /var/log/dcuhat-sauvegarde.log 2>&1
```

Rétention recommandée : 30 sauvegardes quotidiennes, 12 mensuelles. Copie hors site
chiffrée — un disque externe rangé ailleurs qu'à côté du serveur suffit, à condition qu'il
soit effectivement emporté.

> **Le test de restauration mensuel n'est pas optionnel.** Une sauvegarde jamais restaurée
> n'est pas une sauvegarde : c'est une hypothèse. Restaurez le dernier `pg_dump` sur
> l'environnement de recette, ouvrez trois documents au hasard, et notez la date du test.

---

## 4. Exploitation courante

| Fréquence | Tâche |
|---|---|
| Quotidienne | Vérifier que la sauvegarde de la nuit s'est terminée |
| Hebdomadaire | Consulter le journal : échecs de connexion répétés, purges, partages externes |
| Hebdomadaire | Vérifier l'espace disque et les quotas des services |
| Mensuelle | **Test de restauration** |
| Mensuelle | Purger la corbeille au-delà de la rétention, après information des services |
| Trimestrielle | Revue des comptes : désactiver les agents partis, revoir les rôles |
| Trimestrielle | Mises à jour de sécurité (images Docker, système) |
| Annuelle | Revue des permissions et des liens de partage encore actifs |

```bash
docker compose ps                       # état des services
docker compose logs -f api worker       # journaux applicatifs
docker compose exec api python manage.py shell   # accès Django
docker compose restart api              # redémarrage sans perte
```

---

## 5. Sécurité en exploitation

- **Comptes** : un agent, un compte. Désactivez plutôt que supprimer : la traçabilité du
  journal repose sur des acteurs identifiables.
- **Rôles** : le rôle ADMIN se justifie pour une à deux personnes, pas davantage.
- **2FA** obligatoire pour ADMIN et DIRECTEUR.
- **Appareils** : un appareil perdu se révoque depuis le profil de l'agent ; son cache
  local reste chiffré et illisible sans le mot de passe.
- **Liens de partage** : donnez toujours une date d'expiration. Revoyez les liens actifs
  chaque trimestre.
- **Journal** : conservation cinq ans, aucune suppression possible depuis l'application.

---

## 6. Incidents

| Symptôme | Première vérification | Action |
|---|---|---|
| L'interface ne répond plus | `docker compose ps` | Redémarrer le service arrêté |
| « Erreur de base de données » | Journaux du conteneur `db` | Vérifier l'espace disque avant tout |
| Téléversements en échec | Espace disque du stockage objet | Purger la corbeille, étendre le volume |
| Carte vide | Statut d'extraction des fichiers | Vérifier que le worker Celery tourne |
| Synchronisations en échec | Journaux `api`, horloge du poste | Vérifier l'heure système du poste |
| Lenteurs générales | Charge, taille de la base | Vérifier les index, envisager `VACUUM ANALYZE` |

**Perte complète du serveur** : réinstaller Docker, récupérer `.env` et la dernière
sauvegarde, `docker compose up -d`, restaurer le `pg_dump`, restaurer le stockage objet,
vérifier trois documents. Le temps de reprise dépend presque entièrement du temps de
récupération de la sauvegarde hors site : c'est ce délai-là qu'il faut mesurer une fois, à
froid, plutôt que de le découvrir le jour de l'incident.

---

## 7. Évolutions prévues par l'architecture

L'architecture modulaire permet d'ajouter sans reprise de fond :

- signature électronique des arrêtés et décisions ;
- API publique pour la consultation des documents d'urbanisme opposables ;
- extraction automatique des références de parcelles depuis les documents scannés (OCR) ;
- tuiles vectorielles servies par PostGIS pour les couches très volumineuses ;
- application mobile native, si la PWA se révèle insuffisante à l'usage.

Chacune est une application Django supplémentaire et un écran de plus dans l'interface :
aucune ne remet en cause le modèle de données ni le moteur de synchronisation.
