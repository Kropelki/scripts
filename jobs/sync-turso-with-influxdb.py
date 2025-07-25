#!/usr/bin/env python3

"""
A simple Python script to import weather data from
JSON files to a Turso database using the HTTP API.

> https://docs.turso.tech/sdk/http/quickstart

What env varables are needed: TURSO_AUTH_TOKEN && TURSO_DATABASE_URL
"""

import json
import os
import pathlib
import urllib.request

from dotenv import load_dotenv
from typing import List, Dict, Any


SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
JSON_FILE = pathlib.Path(SCRIPT_DIR, "../influxdb/.downloaded/latest.json").resolve()


def load_json_data(file_path: str) -> Dict[str, Any]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file '{file_path}': {e}")


def extract_weather_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    weather_records = []

    try:
        for result in data.get("results", []):
            for series in result.get("series", []):
                if series.get("name") == "weather":
                    columns = series.get("columns", [])
                    values = series.get("values", [])

                    # left side: InfluxDB column name
                    # right side: Turso column name
                    column_map = {
                        "time": "timestamp",
                        "battery_voltage": "battery_voltage",
                        "dew_point": "dew_point",
                        "humidity": "humidity",
                        "illumination": "illumination",
                        "pressure": "pressure",
                        "solar_panel_voltage": "solar_voltage",
                        "temperature": "temperature",
                    }

                    for row in values:
                        record = {}
                        for i, column in enumerate(columns):
                            if column in column_map and i < len(row):
                                db_column = column_map[column]
                                record[db_column] = row[i]

                        if record:
                            weather_records.append(record)

    except Exception as e:
        print(f"Error extracting weather data: {e}")
        raise

    return weather_records


def fetch_existing_turso_data(
    timestamps: List[int], database_url: str, auth_token: str
) -> Dict[int, Dict[str, Any]]:
    if not timestamps:
        return {}

    min_timestamp = min(timestamps)
    max_timestamp = max(timestamps)

    query = f"SELECT * FROM weather WHERE timestamp >= {min_timestamp} AND timestamp <= {max_timestamp}"

    payload = {
        "requests": [{"type": "execute", "stmt": {"sql": query}}, {"type": "close"}]
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        database_url,
        data=data,
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode("utf-8")
            result = json.loads(response_data)

            existing_records = {}
            if "results" in result and len(result["results"]) > 0:
                query_result = result["results"][0]
                if query_result.get("type") == "ok" and "response" in query_result:
                    response_data = query_result["response"]
                    if (
                        response_data.get("type") == "execute"
                        and "result" in response_data
                    ):
                        query_data = response_data["result"]
                        columns = [col["name"] for col in query_data.get("cols", [])]
                        for row in query_data.get("rows", []):
                            if len(row) > 0:
                                timestamp = int(row[0]["value"])
                                record = {}
                                for i, col in enumerate(columns):
                                    if i < len(row):
                                        val = row[i]
                                        if val["type"] == "null":
                                            record[col] = None
                                        else:
                                            record[col] = val["value"]
                                existing_records[timestamp] = record

            return existing_records

    except Exception as e:
        print(f"Warning: Could not fetch existing data: {e}")
        return {}


def records_are_equal(record1: Dict[str, Any], record2: Dict[str, Any]) -> bool:
    all_fields = [
        "temperature",
        "humidity",
        "pressure",
        "illumination",
        "dew_point",
        "solar_voltage",
        "battery_voltage",
    ]

    for field in all_fields:
        val1 = record1.get(field)
        val2 = record2.get(field)

        if val1 is not None:
            val1 = float(val1)
        if val2 is not None:
            val2 = float(val2)

        if val1 != val2:
            return False

    return True


def create_insert_statements(
    records: List[Dict[str, Any]], database_url: str, auth_token: str
) -> List[Dict[str, Any]]:
    statements = []

    main_fields = ["temperature", "humidity", "pressure", "illumination"]
    optional_fields = ["dew_point", "solar_voltage", "battery_voltage"]

    timestamps = [
        int(record["timestamp"]) for record in records if "timestamp" in record
    ]
    existing_data = fetch_existing_turso_data(timestamps, database_url, auth_token)

    print(f"Found {len(existing_data)} existing records in database for comparison")

    for record in records:
        # The illumination sensor was not working before this timestamp (1753429449),
        # so any value (including -100 or 0) should be treated as missing (null).
        # After this timestamp, the station started sending null for missing illumination.
        # https://github.com/Kropelki/firmware/pull/17
        ILLUMINATION_NULL_TIMESTAMP = 1753429449
        if (
            "timestamp" in record
            and int(record["timestamp"]) < ILLUMINATION_NULL_TIMESTAMP
        ):
            record["illumination"] = None

        # we generally don't want to send data if we don't have at least one sensor reading:
        # https://github.com/Kropelki/firmware/commit/038cdb3d0bab577793d23557cec6467a65d7ac9b
        if not any(record.get(field) is not None for field in main_fields):
            continue

        timestamp = int(record["timestamp"])
        if timestamp in existing_data:
            existing_record = existing_data[timestamp]
            if records_are_equal(record, existing_record):
                continue  # skip this record as it's identical to what's already in the database

        columns = ["timestamp"]
        values = [{"type": "integer", "value": str(int(record["timestamp"]))}]

        for field in main_fields + optional_fields:
            if record.get(field) is not None:
                columns.append(field)
                values.append({"type": "float", "value": float(record[field])})

        sql = f"INSERT OR REPLACE INTO weather ({', '.join(columns)}) VALUES ({', '.join(['?' for _ in columns])})"
        statements.append({"type": "execute", "stmt": {"sql": sql, "args": values}})

    print(
        f"Generated {len(statements)} statements (skipped {len(records) - len(statements)} unchanged records)"
    )

    return statements


def send_to_turso(
    statements: List[Dict[str, Any]], database_url: str, auth_token: str
) -> bool:
    payload = {"requests": statements + [{"type": "close"}]}

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        database_url,
        data=data,
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode("utf-8")
            result = json.loads(response_data)

            if "results" in result:
                for i, res in enumerate(result["results"]):
                    if res.get("type") == "error":
                        print(f"Error in statement {i}: {res.get('error', {})}")
                        return False

                print(
                    f"Successfully inserted {len(statements)} records to Turso database."
                )
                return True
            else:
                print(f"Unexpected response format: {result}")
                return False

    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        try:
            error_response = e.read().decode("utf-8")
            print(f"Error response: {error_response}")
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"Error sending data to Turso: {e}")
        return False


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
