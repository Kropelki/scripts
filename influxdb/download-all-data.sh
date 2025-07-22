#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
  INFLUXDB_TOKEN=$(grep "^INFLUXDB_TOKEN=" .env | cut -d '=' -f2-)
else
  echo "Error: .env file not found"
  exit 1
fi

if [ -z "$INFLUXDB_TOKEN" ]; then
  echo "Error: INFLUXDB_TOKEN not found in .env file"
  exit 1
fi

INFLUXDB_URL="https://eu-central-1-1.aws.cloud2.influxdata.com/query"
BUCKET_NAME="db.v0"
MEASUREMENT_NAME="weather"

TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
mkdir -p .downloaded

# https://docs.influxdata.com/influxdb3/core/query-data/execute-queries/influxdb-v1-api/
curl ${INFLUXDB_URL} \
  --header "Authorization: Token ${INFLUXDB_TOKEN}" \
  --data-urlencode "db=${BUCKET_NAME}" \
  --data-urlencode "epoch=s" \
  --data-urlencode "q=SELECT * FROM ${MEASUREMENT_NAME}" | \
  tee .downloaded/latest.json > ".downloaded/${TIMESTAMP}.json"
