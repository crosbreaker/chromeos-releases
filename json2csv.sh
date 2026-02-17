#!/usr/bin/env bash
# Convert ChromeOS recovery JSON to CSV using jq
# Usage: ./json_to_csv.sh input.json [output.csv]

set -euo pipefail

INPUT="${1:-}"
OUTPUT="${2:-}"

if [[ -z "$INPUT" ]]; then
  echo "Usage: $0 input.json [output.csv]" >&2
  exit 1
fi

if [[ ! -f "$INPUT" ]]; then
  echo "Error: file not found: $INPUT" >&2
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "Error: jq is required but not installed. Install with: sudo apt install jq" >&2
  exit 1
fi

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="${INPUT%.json}.csv"
fi

echo "Reading:  $INPUT"

{
  echo "device,platform_version,chrome_version,channel,last_modified,url"
  jq -r '
    to_entries[] |
    .key as $device |
    .value.images[] |
    [$device, .platform_version, .chrome_version, .channel, (.last_modified | tostring), .url] |
    @csv
  ' "$INPUT"
} > "$OUTPUT"

COUNT=$(tail -n +2 "$OUTPUT" | wc -l | tr -d ' ')
echo "Written:  $OUTPUT  ($COUNT rows)"
