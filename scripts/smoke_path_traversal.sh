#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-http://127.0.0.1:8712}"

payloads=(
    "../etc/passwd"
    "..%2f..%2fetc%2fpasswd"
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd"
    "..%252f..%252fetc%252fpasswd"
    "..\\..\\Windows\\win.ini"
    "%2e%2e%5c%2e%2e%5cWindows%5cwin.ini"
)

endpoints=(
  "/api/runs/%s"
  "/api/runs/%s/events"
)

collected_statuses=()

for p in "${payloads[@]}"; do
  for e in "${endpoints[@]}"; do
    url="$BASE$(printf "$e" "$p")"
    code="$(curl -s -o /dev/null -w "%{http_code}" "$url")"
    if [[ "$code" == "200" ]]; then
      echo "FAIL $url -> $code (not expected 200)"
      collected_statuses+=("$url -> $code")
    else
      echo "OK   $url -> $code"
    fi
  done
done

if [[ ${#collected_statuses[@]} -gt 0 ]]; then
  echo "Failed payloads:"
  for s in "${collected_statuses[@]}"; do
    echo "  $s"
  done
  exit 1
fi
echo "All traversal payloads rejected ✅"
exit 0
