#!/bin/bash

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

curl ${INFLUXDB_URL} \
  --header "Authorization: Token ${INFLUXDB_TOKEN}" \
  --data-urlencode "db=${BUCKET_NAME}" \
  --data-urlencode "q=SELECT * FROM ${MEASUREMENT_NAME}"
