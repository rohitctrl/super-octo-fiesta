#!/usr/bin/env bash
# End-to-end test: two CrocBridge instances on this machine pair and move a
# file through a local croc relay, with progress visible on both sides.
#
# The public relay is the default in real use; this script runs its own relay
# on 127.0.0.1 so the test works on locked-down networks and also exercises
# the custom-relay setting.
set -euo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
export NO_PROXY='*'  # everything here is loopback

WORK=$(mktemp -d /tmp/crocbridge-e2e.XXXXXX)
PORT_A=5599 PORT_B=5601
RELAY_PORT=9021
PIDS=()

cleanup() {
  set +e
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null; done
  sleep 2
  for pid in "${PIDS[@]:-}"; do kill -9 "$pid" 2>/dev/null; done
  wait 2>/dev/null
  if pgrep -x croc >/dev/null; then
    echo "FAIL: orphan croc processes survived shutdown:"; pgrep -ax croc
    exit 1
  fi
  echo "clean shutdown: no orphan croc processes"
}
trap cleanup EXIT

api() { # api METHOD PORT PATH [JSON]
  local method=$1 port=$2 path=$3 body=${4:-}
  if [ -n "$body" ]; then
    curl -fsS --noproxy '*' -X "$method" "http://127.0.0.1:$port$path" \
      -H 'Content-Type: application/json' -d "$body"
  else
    curl -fsS --noproxy '*' -X "$method" "http://127.0.0.1:$port$path"
  fi
}

jqpy() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

echo "== relay =="
croc relay --host 127.0.0.1 --ports "$RELAY_PORT,9022,9023,9024,9025" >"$WORK/relay.log" 2>&1 &
PIDS+=($!)
sleep 1

echo "== instances =="
python3 -m crocbridge --port $PORT_A --config "$WORK/a/config.json" >"$WORK/a.log" 2>&1 &
PIDS+=($!)
python3 -m crocbridge --port $PORT_B --config "$WORK/b/config.json" >"$WORK/b.log" 2>&1 &
PIDS+=($!)
for i in $(seq 1 20); do
  api GET $PORT_A /api/status >/dev/null 2>&1 && api GET $PORT_B /api/status >/dev/null 2>&1 && break
  sleep 0.5
done

echo "== settings (distinct download dirs, local relay) =="
# throttle_upload keeps the loopback transfer slow enough that mid-transfer
# progress is actually observable via /api/status on both sides
api PUT $PORT_A /api/settings "{\"device_name\":\"alpha\",\"download_dir\":\"$WORK/a/dl\",\"relay\":\"127.0.0.1:$RELAY_PORT\",\"throttle_upload\":\"1M\"}" >/dev/null
api PUT $PORT_B /api/settings "{\"device_name\":\"bravo\",\"download_dir\":\"$WORK/b/dl\",\"relay\":\"127.0.0.1:$RELAY_PORT\"}" >/dev/null

echo "== pairing (create on A, accept on B, confirm on A) =="
PSTR=$(api POST $PORT_A /api/pair/create '{}' | jqpy "d['pairing_string']")
CONF=$(api POST $PORT_B /api/pair/accept "{\"pairing_string\":\"$PSTR\",\"device_name\":\"bravo\"}" | jqpy "d['confirmation_string']")
PEER=$(api POST $PORT_A /api/pair/confirm "{\"confirmation_string\":\"$CONF\"}" | jqpy "d['peer_name']")
[ "$PEER" = "bravo" ] || { echo "FAIL: A learned peer '$PEER', expected bravo"; exit 1; }
echo "paired: alpha <-> bravo"

echo "== waiting for B's receiver to listen =="
for i in $(seq 1 30); do
  STATE=$(api GET $PORT_B /api/status | jqpy "d['receiver']['state']")
  [ "$STATE" = "listening" ] && break
  sleep 0.5
done
[ "$STATE" = "listening" ] || { echo "FAIL: B receiver state is '$STATE'"; tail -20 "$WORK/b.log"; exit 1; }
echo "B is listening"

echo "== sending a 5 MB file from A to B =="
dd if=/dev/urandom of="$WORK/payload.bin" bs=1M count=5 2>/dev/null
api POST $PORT_A /api/send >/dev/null 2>&1 || true  # no files -> 400, sanity only
curl -fsS --noproxy '*' -F "files[]=@$WORK/payload.bin" "http://127.0.0.1:$PORT_A/api/send" >/dev/null

SEEN_A=0 SEEN_B=0 RESULT=""
for i in $(seq 1 200); do
  SA=$(api GET $PORT_A /api/status)
  SB=$(api GET $PORT_B /api/status)
  PA=$(echo "$SA" | jqpy "(d['send'].get('progress') or {}).get('pct')")
  PB=$(echo "$SB" | jqpy "(d['receiver'].get('progress') or {}).get('pct')")
  [ "$PA" != "None" ] && [ "$PA" -gt 0 ] && [ "$PA" -lt 100 ] && SEEN_A=1
  [ "$PB" != "None" ] && [ "$PB" -gt 0 ] && [ "$PB" -lt 100 ] && SEEN_B=1
  ST=$(echo "$SA" | jqpy "d['send']['state']")
  if [ "$ST" = "done" ]; then RESULT=ok; break; fi
  if [ "$ST" = "error" ]; then
    echo "FAIL: send errored: $(echo "$SA" | jqpy "d['send']['error']")"; exit 1
  fi
  sleep 0.3
done
[ "$RESULT" = "ok" ] || { echo "FAIL: send did not complete"; exit 1; }
echo "send completed; progress seen on A: $SEEN_A, on B: $SEEN_B"
[ "$SEEN_A" = 1 ] || { echo "FAIL: no mid-transfer progress observed on sender"; exit 1; }
[ "$SEEN_B" = 1 ] || { echo "FAIL: no mid-transfer progress observed on receiver"; exit 1; }

echo "== verifying the received file =="
sleep 3  # let B's daemon finish attribution
cmp "$WORK/payload.bin" "$WORK/b/dl/payload.bin" || { echo "FAIL: file differs"; exit 1; }
api GET $PORT_B /api/status | jqpy "[f['name'] for f in d['receiver']['received_files']]" | grep -q payload.bin \
  || { echo "FAIL: B did not list payload.bin in received files"; exit 1; }
echo "file received intact and attributed"

echo
echo "E2E PASSED"
echo "work dir: $WORK (kept for inspection)"
