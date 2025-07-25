#!/usr/bin/env python3

"""
A simple Python script to import weather data from
JSON files to a Turso database using the HTTP API.

> https://docs.turso.tech/sdk/http/quickstart

What env varables are needed: TURSO_AUTH_TOKEN && TURSO_DATABASE_URL
"""

import os
import pathlib

from dotenv import load_dotenv

from sync_turso_with_influxdb.influx import extract_weather_data
from sync_turso_with_influxdb.sql import create_insert_statements
from sync_turso_with_influxdb.turso import send_to_turso
from sync_turso_with_influxdb.utils import load_json_data

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
JSON_FILE = pathlib.Path(SCRIPT_DIR, "../influxdb/.downloaded/latest.json").resolve()


def main():
    load_dotenv()

    TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
    TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

    if not TURSO_DATABASE_URL:
        return print("Error: TURSO_DATABASE_URL environment variable not set")

    if not TURSO_AUTH_TOKEN:
        return print("Error: TURSO_AUTH_TOKEN environment variable not set")

    # From the docs:
    # > You must append to the Base URL the actual pipeline URL that accepts requests — /v2/pipeline.
    if not TURSO_DATABASE_URL.endswith("/v2/pipeline"):
        if TURSO_DATABASE_URL.endswith("/"):
            TURSO_DATABASE_URL += "v2/pipeline"
        else:
            TURSO_DATABASE_URL += "/v2/pipeline"

    print(f"Loading data from: {JSON_FILE}")

    json_data = load_json_data(JSON_FILE)
    weather_records = extract_weather_data(json_data)

    if not weather_records:
        return print("No weather data found in the JSON file")
    print(f"Found {len(weather_records)} weather records")

    insert_statements = create_insert_statements(
        weather_records, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN
    )

    if not insert_statements:
        print("No new or changed records to sync.")
        return

    print(f"Prepared {len(insert_statements)} insert statements for Turso database.")
    print("You can review the statements before sending them.")
    should_send = (
        input("Do you want to send these statements to the Turso database? (yes/no): ")
        .strip()
        .lower()
    )
    if should_send not in ["yes", "YES"]:
        print("Data import cancelled by user.")
        return
    print("Sending data to Turso database...")
    success = send_to_turso(insert_statements, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN)

    if success:
        print("Data import completed successfully!")
    else:
        return print("Failed to import data to Turso database")


if __name__ == "__main__":
    main()
