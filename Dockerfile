# Extend the official Rasa SDK image
FROM rasa/rasa-sdk:latest
USER root
RUN pip install --no-cache-dir rasa
RUN pip install --no-cache-dir sqlalchemy
RUN pip install --no-cache-dir psycopg2-binary
COPY endpoints.yml /app/endpoints.yml
COPY credentials.yml /app/credentials.yml
