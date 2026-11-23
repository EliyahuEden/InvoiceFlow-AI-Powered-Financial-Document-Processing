# Database backups: the same Postgres 16 client tools as the server, plus the AWS CLI for an optional offsite copy to
# any S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2...). Build context: infra/backup.
FROM pgvector/pgvector:pg16
RUN apt-get update \
 && apt-get install -y --no-install-recommends awscli \
 && rm -rf /var/lib/apt/lists/*
COPY backup.sh restore.sh drill.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/drill.sh
ENTRYPOINT []
# one backup now, then every BACKUP_INTERVAL_HOURS (24 by default)
CMD ["sh", "-c", "while :; do backup.sh || echo 'backup FAILED' >&2; sleep $(( ${BACKUP_INTERVAL_HOURS:-24} * 3600 )); done"]
