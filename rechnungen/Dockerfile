# Basis-Image fest vorgegeben: Der Supervisor übergibt sonst sein Alpine-Image
# (ghcr.io/home-assistant/base) als BUILD_FROM, dort gibt es kein apt-get.
FROM python:3.12-slim-bookworm

# Carlito = metrisch kompatibel zu Calibri (Schrift der Vorlage)
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-crosextra-carlito \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app /app
# Für die Versionsanzeige in den Einstellungen
COPY config.yaml /app/
WORKDIR /app

ENV DATA_DIR=/data \
    OPTIONS_PATH=/data/options.json \
    PORT=8099

CMD ["python3", "-u", "/app/main.py"]
