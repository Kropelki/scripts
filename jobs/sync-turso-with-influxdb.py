#!/usr/bin/env python3

"""
A simple Python script to import weather data from
JSON files to a Turso database using the HTTP API.

> https://docs.turso.tech/sdk/http/quickstart

What env varables are needed: TURSO_AUTH_TOKEN && TURSO_DATABASE_URL
"""

import os
import sys

from dotenv import load_dotenv

from sync_turso_with_influxdb.influx import extract_weather_data
from sync_turso_with_influxdb.sql import create_insert_statements
from sync_turso_with_influxdb.turso import send_to_turso
from sync_turso_with_influxdb.utils import load_json_data, resolve_json_file_path
from sync_turso_with_influxdb.report import generate_diff_report, save_report_to_file


def main():
    """
    Syncs weather data from JSON file to Turso database.

    The JSON file is expected to be in the format returned by InfluxDB query containing weather data.
    The script will read the JSON file, extract weather records, create SQL insert statements,
    and send them to the Turso database. It will also handle existing records to avoid duplicates.

    Since we are using the `INSERT OR REPLACE` statement, it will update existing records if
    they have the same timestamp and different values, or insert new records if they do not exist.

    The script only syncs records from the last 30 days, because a free InfluxDB account only allows
    for maximum 30 days of data retention (meaning that any data older than that gets deleted).
    """
    JSON_FILE = resolve_json_file_path(sys.argv)
    if JSON_FILE is None:
        return print("Aborting: No JSON file specified or found")
    load_dotenv()

    TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
    TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

    if not TURSO_DATABASE_URL:
        return print("Error: TURSO_DATABASE_URL environment variable not set")

    if not TURSO_AUTH_TOKEN:
        return print("Error: TURSO_AUTH_TOKEN environment variable not set")

    print(f"[TURSO_DATABASE_URL]: {TURSO_DATABASE_URL}")
    print(f"[JSON_FILE]: {JSON_FILE}")

    # From the docs:
    # > You must append to the Base URL the actual pipeline URL that accepts requests — /v2/pipeline.
    if not TURSO_DATABASE_URL.endswith("/v2/pipeline"):
        if TURSO_DATABASE_URL.endswith("/"):
            TURSO_DATABASE_URL += "v2/pipeline"
        else:
            TURSO_DATABASE_URL += "/v2/pipeline"

    json_data = load_json_data(JSON_FILE)
    weather_records = extract_weather_data(json_data)

    if not weather_records:
        return print("No weather data found in the JSON file")

    insert_statements, existing_data = create_insert_statements(weather_records, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN)

    if not insert_statements:
        print("No new or changed records to sync")
        return

    print(f"Prepared {len(insert_statements)} insert statements for Turso database")

    print("Generating diff report...")
    report_content = generate_diff_report(weather_records, insert_statements, existing_data)
    save_report = input("Do you want to save this report to jobs/.reports/? (yes/no): ").strip().lower()
    if save_report in ["yes", "YES"]:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = save_report_to_file(report_content, script_dir)
        if report_path:
            print(f"Report saved to: {report_path}")
        else:
            print("Failed to save report")

    should_send = input("Do you want to send these statements to the Turso database? (yes/no): ").strip().lower()
    if should_send not in ["yes", "YES"]:
        print("Data import cancelled by user")
        return
    print("Sending data to Turso database...")
    success = send_to_turso(insert_statements, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN)

    if success:
        print("Data import completed successfully!")
    else:
        return print("Failed to import data to Turso database")


if __name__ == "__main__":
    main()
