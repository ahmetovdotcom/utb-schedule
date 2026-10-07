#!/usr/bin/env bash
set -euo pipefail
DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE=local

init() {
  if [[ -f "$DEPLOY_DIR/.env" ]]; then
    echo 'Existing deploy/.env preserved.'
    return
  fi
  # A fresh archive has no .env, but an older installation may still own volumes.
  # Generating new credentials in that case disconnects the API from PostgreSQL.
  if ! docker info >/dev/null 2>&1; then
    echo 'Start Docker before init so existing database volumes can be checked.' >&2
    exit 1
  fi
  local project_name="${COMPOSE_PROJECT_NAME:-okak}"
  if docker volume inspect "${project_name}_student_data" >/dev/null 2>&1 \
      || docker volume inspect "${project_name}_staff_data" >/dev/null 2>&1 \
      || docker volume inspect "${project_name}_manual_data" >/dev/null 2>&1; then
    echo 'Existing database volumes found. Copy deploy/.env from the previous installation (or deploy.env from its backup) into this folder. Do not generate new credentials or delete volumes.' >&2
    exit 1
  fi
  umask 077
  local db_key publish_key
  db_key="$(openssl rand -hex 32)"
  publish_key="$(openssl rand -hex 48)"
  printf 'POSTGRES_PASSWORD=%s\nPUBLISH_SECRET_KEY=%s\nSTUDENT_PORT=8080\nSTAFF_PORT=8081\nSTUDENT_DOMAIN=okak.asia\nEDITOR_DOMAIN=app.okak.asia\n' \
    "$db_key" "$publish_key" > "$DEPLOY_DIR/.env"
  echo 'Created deploy/.env with random secrets. Keep this file for this installation.'
}

compose() {
  case "$MODE" in local|server) ;; *) echo 'Mode must be local or server.' >&2; exit 2;; esac
  docker compose --project-directory "$DEPLOY_DIR" --env-file "$DEPLOY_DIR/.env" \
    -f "$DEPLOY_DIR/compose.yaml" -f "$DEPLOY_DIR/compose.$MODE.yaml" "$@"
}

usage() {
  cat <<'HELP'
Usage: ./deploy.sh COMMAND [arguments]
  init                              Generate secrets once
  up [local|server]                  Build and start both applications (default: local)
  down [local|server]                Stop containers; preserve database volumes
  status [local|server]              Show container health
  logs [local|server]                Follow logs
  user LOGIN [local|server]          Create/change the shared manual-scheduler account
  import-manual FILE [local|server]   Import manual-scheduler schedule.db into an EMPTY volume
  backup [local|server]              Back up both databases; briefly pauses staff API
  package                           Create a source archive without secrets or databases
HELP
}

command="${1:-help}"
case "$command" in
  init) init ;;
  up|down|status|logs)
    MODE="${2:-local}"
    init
    case "$command" in
      up)
        compose up -d --build --wait --wait-timeout 180
        # Bind-mounted configs may change without forcing container recreation.
        compose exec -T student-web nginx -s reload
        compose exec -T staff-web nginx -s reload
        compose exec -T gateway caddy reload --config /etc/caddy/Caddyfile
        ;;
      down) compose down ;;
      status) compose ps ;;
      logs) compose logs --follow --tail 100 ;;
    esac
    ;;
  user)
    [[ -n "${2:-}" ]] || { usage; exit 2; }
    MODE="${3:-local}"
    compose exec staff-api python manage_account.py "$2"
    ;;
  import-manual|import-staff)
    [[ -f "${2:-}" ]] || { echo 'Provide an existing SQLite database file.' >&2; exit 2; }
    MODE="${3:-local}"
    source_dir="$(cd -- "$(dirname -- "$2")" && pwd)"
    source_name="$(basename -- "$2")"
    init
    if [[ -n "$(compose ps --status running -q staff-api)" ]]; then
      echo 'Stop the staff API before importing. Existing database volumes are never overwritten.' >&2
      exit 1
    fi
    # Reject a legacy timetable-system DB before writing to the new volume.
    python3 - "$2" <<'PYCODE'
import sqlite3,sys
from pathlib import Path
with sqlite3.connect(Path(sys.argv[1]).resolve().as_uri()+'?mode=ro',uri=True) as db:
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'refs','lessons','lesson_groups'}.issubset(tables):
        raise SystemExit('Expected manual-scheduler schedule.db; timetable-system DB is not compatible.')
PYCODE
    compose build staff-api
    compose run --rm --no-deps -T --user 0 \
      -v "$source_dir:/import:ro" -v "$DEPLOY_DIR/scripts/sqlite_copy.py:/sqlite_copy.py:ro" \
      staff-api python /sqlite_copy.py "/import/$source_name" /data/schedule.db --uid 10001 --gid 10001
    ;;
  backup)
    MODE="${2:-local}"
    umask 077
    backup_dir="$DEPLOY_DIR/backups/$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir -p "$backup_dir"
    was_running="$(compose ps --status running -q staff-api)"
    if [[ -n "$was_running" ]]; then
      compose stop staff-api
      trap 'compose start staff-api >/dev/null' EXIT
    fi
    compose run --rm --no-deps -T --user 0 \
      -v "$backup_dir:/backup" -v "$DEPLOY_DIR/scripts/sqlite_copy.py:/sqlite_copy.py:ro" \
      staff-api python /sqlite_copy.py /data/schedule.db /backup/manual.sqlite --uid "$(id -u)" --gid "$(id -g)"
    compose exec -T student-db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_dir/students.dump"
    cp "$DEPLOY_DIR/.env" "$backup_dir/deploy.env"
    echo "Backup saved: $backup_dir (contains secrets; keep private)."
    ;;
  package)
    python3 "$DEPLOY_DIR/scripts/package.py"
    ;;
  help|--help|-h) usage ;;
  *) usage; exit 2 ;;
esac
