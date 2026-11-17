#!/usr/bin/env bash
# Deploy the room server to the official host over ssh. Steps and layout: docs/OPERATIONS.md.
#
#   scripts/deploy-server.sh <host> trial   <commit> [--manifest]  upload, build the image, try it on port 8011
#   scripts/deploy-server.sh <host> switch  <commit>               back up, swap the container, check
#   scripts/deploy-server.sh <host> economy <file> [--apply]       show the change to the economy file; --apply installs it
#
# trial never touches the running container. switch needs the image and build directory trial made.
# A change to server/requirements.txt or the asset packs other than the manifest needs a full image build, which
# this script does not do.
set -euo pipefail

usage() { sed -n 4,6p "$0" | sed 's/^# //'; exit 2; }
[ $# -ge 3 ] || usage
HOST=$1 MODE=$2 ARG=$3
shift 3
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
  *) usage ;;
esac

ssh "$HOST" bash -s -- "$MODE" "$SHA" "$FLAG" <<'REMOTE'
set -euo pipefail
MODE=$1 SHA=$2 FLAG=${3:-}
BASE=/opt/asoultappo DB=/opt/asoultappo/data/asoultappo.db CFG=/opt/asoultappo/config ENV=/opt/asoultappo/server.env
D=/root/asoultappo-build-$SHA TS=$(date -u +%Y%m%dT%H%M%SZ)
sq() { sqlite3 -cmd ".timeout 30000" "$@"; }
code() { curl -s -m 5 -o /dev/null -w '%{http_code}' "$1"; }

run_server() { # name port data-dir app-dir config-dir image
  docker run -d --name "$1" --network host --restart unless-stopped --env-file $ENV \
    -v "$3":/srv/data -v "$4":/srv/app:ro -v "$5":/srv/config:ro --user app \
    --log-opt max-size=50m --log-opt max-file=3 \
    "asoultappo-server:$6" uvicorn app.main:app --host 127.0.0.1 --port "$2" >/dev/null
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
  sq $DB ".backup $T/data/asoultappo.db"
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
  sq $DB ".backup $BAK"
  echo "players $(sqlite3 $BAK 'select count(*) from players')"
  cp -a $BASE/app $APPBAK
  docker stop -t 30 asoultappo >/dev/null && docker rename asoultappo "asoultappo-$LIVE"
  echo "rooms saved $(sq $DB 'select count(*) from room_restore')"
  rsync -rc --delete --exclude __pycache__ $D/server/app/ $BASE/app/
  chown -R www:www $BASE/app
  run_server asoultappo 8000 $BASE/data $BASE/app $CFG "$SHA"
  echo "backups $BAK $APPBAK; old container asoultappo-$LIVE stopped"
  echo "rollback: docker stop -t 30 asoultappo && docker rename asoultappo asoultappo-$SHA &&"
  echo "  rsync -rc --delete $APPBAK/ $BASE/app/ && docker rename asoultappo-$LIVE asoultappo && docker start asoultappo"
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
  sq $DB ".backup /root/asoultappo-$SHA-before-economy.db"
  install -o www -g www -m 644 $NEW $CFG/economy.json && rm -f $NEW
  echo "backups /root/economy-$SHA-before.json /root/asoultappo-$SHA-before-economy.db"
  docker restart -t 30 asoultappo >/dev/null
  sleep 6
  check 8000 asoultappo
  ;;
esac
REMOTE
