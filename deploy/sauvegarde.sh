#!/usr/bin/env bash
# Sauvegarde quotidienne DCUHAT : base de donnees + stockage objet.
# A planifier dans cron :  0 2 * * *  /opt/dcuhat/deploy/sauvegarde.sh
#
# Une sauvegarde jamais restauree n'est pas une sauvegarde : le test mensuel
# de restauration (restaurer.sh sur un environnement de recette) fait partie
# du plan de maintenance, il n'est pas optionnel.

set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINATION="${DCUHAT_BACKUP_DIR:-$RACINE/deploy/sauvegardes}"
HORODATAGE="$(date +%Y%m%d-%H%M)"
RETENTION_JOURS="${DCUHAT_BACKUP_RETENTION:-30}"

mkdir -p "$DESTINATION"

echo "[1/3] Base de donnees..."
docker compose -f "$RACINE/docker-compose.yml" exec -T db \
    pg_dump -U "${POSTGRES_USER:-dcuhat}" "${POSTGRES_DB:-dcuhat}" \
    | gzip > "$DESTINATION/db-$HORODATAGE.sql.gz"

echo "[2/3] Stockage objet..."
docker compose -f "$RACINE/docker-compose.yml" run --rm creation_bucket \
    mc mirror --overwrite "dcuhat/${S3_BUCKET:-dcuhat}" "/sauvegardes/objets-$HORODATAGE" \
    || echo "  (miroir MinIO ignore : verifiez la configuration)"

echo "[3/3] Purge au-dela de $RETENTION_JOURS jours..."
find "$DESTINATION" -name 'db-*.sql.gz' -mtime "+$RETENTION_JOURS" -delete

echo "Sauvegarde terminee : $DESTINATION/db-$HORODATAGE.sql.gz"
