FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# GDAL, GEOS et PROJ sont requis par GeoDjango ; ogr2ogr assure les conversions.
RUN apt-get update && apt-get install -y --no-install-recommends \
        binutils libproj-dev gdal-bin libgdal-dev \
        libgeos-dev postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/staticfiles /var/dcuhat/objets \
    && chmod +x /app/entrypoint.sh

EXPOSE 8000
CMD ["/app/entrypoint.sh"]
