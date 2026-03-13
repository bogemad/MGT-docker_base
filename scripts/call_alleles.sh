#!/usr/bin/env bash
set -euo pipefail

# Run from the repo root. Executes safely inside the web container.
docker compose exec -T web bash -lc '
  set -e
  # wait until DB init has finished (your flag)
  if [ ! -f "${DB_INIT_FLAG:-/var/lib/db_init/.db_initialized}" ]; then
    echo "DB not initialized yet; exiting." >&2
    exit 1
  fi

  # single-run lock to avoid overlapping executions
  lock=/tmp/cron_pipeline.lock
  if ! ( set -o noclobber; echo $$ > "$lock") 2>/dev/null; then
    echo "Another pipeline run is in progress; exiting."
    exit 0
  fi
  trap "rm -f \"$lock\"" EXIT

  # conda env + run
  source /opt/conda/etc/profile.d/conda.sh || true
  conda activate mgtenv
  cd /app/Mgt/Mgt/Scripts

  echo "Running cron_pipeline.py…"
  python cron_pipeline.py \
    -s template \
    -d $DBNAME \
    --allele_to_db --local
'
