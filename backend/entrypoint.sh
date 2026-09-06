#!/usr/bin/env sh
# Demarrage du conteneur API DCUHAT.
#
# Les plateformes d'hebergement (Koyeb, Render, Railway...) imposent le port
# d'ecoute par la variable PORT ; on la respecte, avec 8000 par defaut pour
# docker compose en local.
set -e

echo "[DCUHAT] Migrations..."
python manage.py migrate --noinput

echo "[DCUHAT] Fichiers statiques..."
python manage.py collectstatic --noinput

# Un seul worker sur les offres gratuites (512 Mo) : chaque worker charge sa
# propre copie de GDAL et de Django, ce qui saturerait la memoire.
NB_WORKERS="${GUNICORN_WORKERS:-2}"

echo "[DCUHAT] Demarrage sur le port ${PORT:-8000} avec ${NB_WORKERS} worker(s)."
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${NB_WORKERS}" \
    --timeout 300 \
    --access-logfile -
