#!/bin/sh
# Dump the database to /backups as a compressed, timestamped file and delete the ones older than
# KEEP_DAYS. Run through compose:  docker compose --profile backup run --rm backup
# Restore:  gunzip -c wfm-YYYYmmdd-HHMMSS.sql.gz | docker compose exec -T db psql -U $POSTGRES_USER $POSTGRES_DB
set -eu
stamp=$(date +%Y%m%d-%H%M%S)
file="/backups/wfm-${stamp}.sql.gz"
pg_dump --no-owner --clean --if-exists | gzip -9 > "${file}.partial"
mv "${file}.partial" "${file}"
echo "wrote ${file}"
find /backups -name 'wfm-*.sql.gz' -mtime +"${KEEP_DAYS:-14}" -delete
