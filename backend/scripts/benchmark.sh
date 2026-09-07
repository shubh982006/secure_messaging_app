#!/usr/bin/env bash
# Horizontal scaling benchmark: run the identical load against 1, 2 and 3 API
# nodes and print the comparison. All nodes share one Postgres and one Redis.
#
#   ./scripts/benchmark.sh [connections] [messages-per-pair]
set -euo pipefail
# Background nodes are killed between rounds; without this bash prints a
# "Killed: 9" job-control line for each one.
set +m

CONNECTIONS=${1:-200}
MESSAGES=${2:-10}
PY=${PYTHON:-python}
PG=${BENCH_DATABASE_URL:-postgresql+asyncpg://$(whoami)@localhost:5432/signal_bench}
REDIS=${BENCH_REDIS_URL:-redis://localhost:6379/14}
PORTS=(8031 8032 8033)

LOGS=$(mktemp -d)

cleanup() {
  for port in "${PORTS[@]}"; do lsof -ti:"$port" 2>/dev/null | xargs -r kill -9 2>/dev/null || true; done
  # Wait for the ports to actually be released before reusing them.
  for port in "${PORTS[@]}"; do
    for _ in $(seq 1 40); do
      lsof -ti:"$port" >/dev/null 2>&1 || break
      sleep 0.25
    done
  done
}
trap cleanup EXIT
cleanup

psql -d postgres -c "DROP DATABASE IF EXISTS signal_bench;" >/dev/null 2>&1 || true
psql -d postgres -c "CREATE DATABASE signal_bench;"          >/dev/null 2>&1 || true
redis-cli -u "$REDIS" flushdb >/dev/null 2>&1 || true

start_node() {
  local port=$1 use_redis=$2
  # Built as an array and passed through `env`: bash decides what is an
  # assignment prefix at parse time, so an *expanded* VAR=value would be treated
  # as the command name instead.
  local -a vars=(
    DATABASE_URL="$PG"
    NODE_ID="node-$port"
    JWT_SECRET=benchmark
    RATE_LIMIT_MESSAGES=1000000
  )
  [ -n "$use_redis" ] && vars+=(REDIS_URL="$REDIS")
  env "${vars[@]}" "$PY" -m uvicorn app.main:app --port "$port" --log-level warning \
    >"$LOGS/$port.log" 2>&1 &
  disown
  for _ in $(seq 1 100); do
    curl -sf -m 1 "http://127.0.0.1:$port/health" >/dev/null 2>&1 && return 0
    sleep 0.3
  done
  echo "node on :$port never came up. log:" >&2
  tail -20 "$LOGS/$port.log" >&2
  exit 1
}

for count in 1 2 3; do
  cleanup; sleep 2
  redis-cli -u "$REDIS" flushdb >/dev/null 2>&1 || true

  hosts=""
  for index in $(seq 0 $((count - 1))); do
    # A single node needs no Redis at all - that is the point of the seam.
    if [ "$count" -eq 1 ]; then start_node "${PORTS[$index]}" ""; else start_node "${PORTS[$index]}" "1"; fi
    hosts="${hosts:+$hosts,}http://127.0.0.1:${PORTS[$index]}"
  done
  sleep 2

  echo ""
  echo "############################################################"
  echo "#  $count NODE(S)   ($( [ "$count" -eq 1 ] && echo 'in-process fan-out' || echo 'redis fan-out' ))"
  echo "############################################################"
  "$PY" scripts/loadtest.py --hosts "$hosts" --connections "$CONNECTIONS" --messages "$MESSAGES" \
    | grep -E "throughput|p50|p95|p99|delivered|concurrent sockets|END-TO-END|server ack"
done
