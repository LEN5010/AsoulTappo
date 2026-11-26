#!/usr/bin/env bash
# Deploy the room server to the official host over ssh. Steps and layout: docs/OPERATIONS.md.
#
#   scripts/deploy-server.sh <host> trial   <commit> [--manifest]  upload, build the image, try it on port 8011
#   scripts/deploy-server.sh <host> switch  <commit>               back up, swap the container, check
#   scripts/deploy-server.sh <host> economy <file> [--apply]       show the change to the economy file; --apply installs it
#   scripts/deploy-server.sh <host> prune [--apply]                list old backups and builds in /root; --apply deletes them
#
# trial never touches the running container. switch needs the image and build directory trial made. prune deletes only
# names this script makes, and keeps the newest 5 of each kind and anything from the last 7 days.
# A change to server/requirements.txt or the asset packs other than the manifest needs a full image build, which
# this script does not do.
set -euo pipefail

usage() { sed -n 4,7p "$0" | sed 's/^# //'; exit 2; }
[ $# -ge 2 ] || usage
HOST=$1 MODE=$2 ARG=
shift 2
if [ "$MODE" != prune ]; then
  [ $# -ge 1 ] || usage
  ARG=$1
  shift
fi
FLAG=${1:-}

case $MODE in
  trial|switch)
    SHA=$(git rev-parse --short=7 "$ARG^{commit}")
    if [ "$MODE" = trial ]; then
      # The build directory holds the commit's server code and manifest; the switch copies the code from there.
      git archive --format=tar "$SHA" server/app assets-packs/manifest.json |
        ssh "$HOST" "rm -rf /root/asoultappo-build-$SHA && mkdir -p /root/asoultappo-build-$SHA && tar -x -C /root/asoultappo-build-$SHA"
    fi
    ;;
  economy)
    [ -f "$ARG" ] || { echo "no such file: $ARG" >&2; exit 2; }
    python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$ARG"
    SHA=$(date -u +%Y%m%dT%H%M%SZ)
    scp -q "$ARG" "$HOST:/root/economy-$SHA-new.json"
    ;;
  prune)
    [ -z "$FLAG" ] || [ "$FLAG" = --apply ] || usage
    SHA=none
    ;;
  *) usage ;;
esac

ssh "$HOST" bash -s -- "$MODE" "$SHA" "$FLAG" <<'REMOTE'
set -euo pipefail
MODE=$1 SHA=$2 FLAG=${3:-}
BASE=/opt/asoultappo DB=/opt/asoultappo/data/asoultappo.db CFG=/opt/asoultappo/config ENV=/opt/asoultappo/server.env
D=/root/asoultappo-build-$SHA TS=$(date -u +%Y%m%dT%H%M%SZ)
sq() { sqlite3 -cmd ".timeout 30000" "$@"; }
code() { curl -s -m 5 -o /dev/null -w '%{http_code}' "$1"; }

# A copy of the live database. sqlite3's .backup copies a few pages at a time and starts over whenever the server
# writes in between, which under load kept a 354 MB copy going for minutes. Connection.backup() with its default
# pages=-1 copies every page in one step from one read snapshot; in WAL mode the server's writes go on meanwhile and
# cannot restart it. A failure exits nonzero, which stops this script. The copy is made under a name prune does not
# count and takes the backup's name only once complete, so a failed one is never kept as a backup.
backup_db() { # source target
  python3 - "$1" "$2" <<'PY'
import os, sqlite3, sys
# connect() would make an empty database at a wrong path and copy that.
if not os.path.isfile(sys.argv[1]):
    sys.exit(f"no database at {sys.argv[1]}")
part = sys.argv[2] + ".part"
try:
    src = sqlite3.connect(sys.argv[1], timeout=30)
    dst = sqlite3.connect(part)
    src.backup(dst)
    dst.close()
    src.close()
    os.replace(part, sys.argv[2])
finally:
    for leftover in (part, part + "-journal"):
        if os.path.exists(leftover):
            os.unlink(leftover)
PY
}

# The server reaches the main site at https://len5010.top/...; this host's own public address is slow to reach from
# itself, so the name resolves to the local nginx instead (same certificate, milliseconds instead of seconds).
# The websocket protocol is named outright: app/ws_writes.py coalesces writes only for websockets-sansio. An image
# whose uvicorn lacks it fails to start, and the trial's check stops there.
run_server() { # name port data-dir app-dir config-dir image
  docker run -d --name "$1" --network host --restart unless-stopped --env-file $ENV \
    --add-host len5010.top:127.0.0.1 \
    -v "$3":/srv/data -v "$4":/srv/app:ro -v "$5":/srv/config:ro --user app \
    --log-opt max-size=50m --log-opt max-file=3 \
    "asoultappo-server:$6" uvicorn app.main:app --host 127.0.0.1 --port "$2" --ws websockets-sansio >/dev/null
}

check() { # port container
  local economy manifest release
  economy=$(code "127.0.0.1:$1/api/economy") || economy=000
  manifest=$(code "127.0.0.1:$1/api/manifest") || manifest=000
  release=$(code "127.0.0.1:$1/api/client/release") || release=000
  echo "economy $economy  manifest $manifest  release $release"
  echo "503 since start $(docker logs "$2" 2>&1 | grep -c '" 503' || true)"
  [ "$economy" = 200 ] && [ "$manifest" = 200 ] && [ "$release" = 200 ]
}

LIVE=$(docker inspect -f '{{.Config.Image}}' asoultappo); LIVE=${LIVE#asoultappo-server:}

case $MODE in
trial)
  echo "live image $LIVE, building $SHA"
  if [ "$FLAG" = --manifest ]; then
    printf 'FROM asoultappo-server:%s\nCOPY assets-packs/manifest.json /srv/assets-packs/manifest.json\n' "$LIVE" > $D/Dockerfile.manifest
    docker build -q -f $D/Dockerfile.manifest -t "asoultappo-server:$SHA" $D >/dev/null
  else
    docker tag "asoultappo-server:$LIVE" "asoultappo-server:$SHA"
  fi
  T=/root/asoultappo-trial-$SHA
  rm -rf $T && mkdir -p $T/data
  backup_db $DB $T/data/asoultappo.db
  chown -R www:www $T
  run_server asoultappo-trial 8011 $T/data $D/server/app $CFG "$SHA"
  sleep 6
  trial_status=0
  check 8011 asoultappo-trial || trial_status=$?
  docker logs asoultappo-trial 2>&1 | tail -5
  docker rm -f asoultappo-trial >/dev/null && rm -rf $T
  [ "$trial_status" = 0 ] || exit "$trial_status"
  echo "trial removed; image asoultappo-server:$SHA kept for the switch"
  ;;
switch)
  docker image inspect "asoultappo-server:$SHA" >/dev/null && [ -d $D/server/app ] || { echo "run trial for $SHA first" >&2; exit 1; }
  [ "$LIVE" != "$SHA" ] || { echo "already running $SHA" >&2; exit 1; }
  BAK=/root/asoultappo-$TS-before-$SHA.db APPBAK=/root/asoultappo-app-$TS-$LIVE
  # The economy file the old code ran with: an economy change made after this switch may hold keys the old code
  # refuses at start, so a rollback puts this one back before it starts the old container.
  ECOBAK=/root/economy-$TS-before.json
  backup_db $DB $BAK
  echo "players $(sqlite3 $BAK 'select count(*) from players')"
  cp -a $BASE/app $APPBAK
  cp -a $CFG/economy.json $ECOBAK
  docker stop -t 30 asoultappo >/dev/null && docker rename asoultappo "asoultappo-$LIVE"
  echo "rooms saved $(sq $DB 'select count(*) from room_restore')"
  rsync -rc --delete --exclude __pycache__ $D/server/app/ $BASE/app/
  chown -R www:www $BASE/app
  run_server asoultappo 8000 $BASE/data $BASE/app $CFG "$SHA"
  echo "backups $BAK $APPBAK $ECOBAK; old container asoultappo-$LIVE stopped"
  echo "rollback: docker stop -t 30 asoultappo && docker rename asoultappo asoultappo-$SHA &&"
  echo "  rsync -rc --delete $APPBAK/ $BASE/app/ && install -o www -g www -m 644 $ECOBAK $CFG/economy.json &&"
  echo "  docker rename asoultappo-$LIVE asoultappo && docker start asoultappo"
  sleep 6
  docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep '^asoultappo '
  check 8000 asoultappo
  echo "rooms left unread $(sq $DB 'select count(*) from room_restore')"
  docker logs asoultappo 2>&1 | tail -3
  ;;
economy)
  NEW=/root/economy-$SHA-new.json
  python3 - $CFG/economy.json $NEW <<'EOF'
import json, sys
def walk(a, b, p=""):
    if isinstance(a, dict) or isinstance(b, dict):
        a = a if isinstance(a, dict) else {}; b = b if isinstance(b, dict) else {}
        for k in sorted(set(a) | set(b)):
            walk(a.get(k), b.get(k), f"{p}.{k}")
    elif a != b:
        print(f"{p}: {json.dumps(a, ensure_ascii=False)} -> {json.dumps(b, ensure_ascii=False)}")
walk(json.load(open(sys.argv[1])), json.load(open(sys.argv[2])))
EOF
  if [ "$FLAG" != --apply ]; then echo "not applied; rerun with --apply"; rm -f $NEW; exit 0; fi
  cp -a $CFG/economy.json /root/economy-$SHA-before.json
  backup_db $DB /root/asoultappo-$SHA-before-economy.db
  install -o www -g www -m 644 $NEW $CFG/economy.json && rm -f $NEW
  echo "backups /root/economy-$SHA-before.json /root/asoultappo-$SHA-before-economy.db"
  echo "rollback: install -o www -g www -m 644 /root/economy-$SHA-before.json $CFG/economy.json && docker restart -t 30 asoultappo"
  echo "before a rollback of the code: put back the economy file its switch backed up (rollback line of switch);"
  echo "  older code may refuse keys of this file at start"
  docker restart -t 30 asoultappo >/dev/null
  sleep 6
  check 8000 asoultappo
  ;;
prune)
  # What switch and economy back up, and the build directories trial makes. Each kind keeps its newest KEEP; of the
  # rest, what is older than DAYS days goes. The patterns do not overlap, so an entry is counted in one kind only.
  # Only names this script makes count: /root also holds copies made by hand (asoultappo-<time>-before-cleanup.db
  # and the like), which can be the only record of what they were made before. Those are listed and never deleted.
  # Age is the inode change time: cp -a keeps the copied directory's or file's own modification time, which can be
  # much older than the backup.
  KEEP=5 DAYS=7
  CUTOFF=$(( $(date +%s) - DAYS * 86400 ))
  TIME='[0-9]{8}T[0-9]{6}Z' HEX='[0-9a-f]{7,40}'
  verb="would delete"
  [ "$FLAG" != --apply ] || verb=deleted
  for kind in db app build economy; do
    case $kind in
      db) args=(-type f -name 'asoultappo-*-before-*.db' ! -name 'asoultappo-app-*' ! -name 'asoultappo-build-*')
          ours="^asoultappo-$TIME-before-($HEX|economy)\.db\$" ;;
      app) args=(-type d -name 'asoultappo-app-*') ours="^asoultappo-app-$TIME-$HEX\$" ;;
      build) args=(-type d -name 'asoultappo-build-*') ours="^asoultappo-build-$HEX\$" ;;
      economy) args=(-type f -name 'economy-*-before.json') ours="^economy-$TIME-before\.json\$" ;;
    esac
    n=0
    find /root -mindepth 1 -maxdepth 1 "${args[@]}" -printf '%C@ %p\n' | sort -rn |
      while read -r made path; do
        if ! [[ ${path##*/} =~ $ours ]]; then
          echo "kept (not made by this script) $kind $path"
          continue
        fi
        n=$((n + 1))
        [ "$n" -gt "$KEEP" ] && [ "${made%.*}" -lt "$CUTOFF" ] || continue
        echo "$verb $kind $(du -sh -- "$path" | cut -f1) $path"
        [ "$FLAG" = --apply ] || continue
        # A database copy may have its WAL files next to it.
        rm -rf -- "$path" "$path-wal" "$path-shm"
      done
  done
  [ "$FLAG" = --apply ] || echo "nothing deleted; rerun with --apply"
  ;;
esac
REMOTE
