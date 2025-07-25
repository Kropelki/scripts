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


def create_insert_statements(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    statements = []

    main_fields = ["temperature", "humidity", "pressure", "illumination"]
    optional_fields = ["dew_point", "solar_voltage", "battery_voltage"]

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

        columns = ["timestamp"]
        values = [{"type": "integer", "value": str(int(record["timestamp"]))}]

        for field in main_fields + optional_fields:
            if record.get(field) is not None:
                columns.append(field)
                values.append({"type": "float", "value": float(record[field])})

        sql = f"INSERT OR REPLACE INTO weather ({', '.join(columns)}) VALUES ({', '.join(['?' for _ in columns])})"
        statements.append({"type": "execute", "stmt": {"sql": sql, "args": values}})

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

    insert_statements = create_insert_statements(weather_records)

    print("Sending data to Turso database...")
    success = send_to_turso(insert_statements, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN)

    if success:
        print("Data import completed successfully!")
    else:
        return print("Failed to import data to Turso database")


if __name__ == "__main__":
    main()
