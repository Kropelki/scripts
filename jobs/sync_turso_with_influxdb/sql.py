from typing import List, Dict, Any

from sync_turso_with_influxdb.turso import fetch_existing_turso_data
from sync_turso_with_influxdb.utils import records_are_equal, prepare_weather_record


def create_insert_statements(records: List[Dict[str, Any]], database_url: str, auth_token: str) -> List[Dict[str, Any]]:
    """Creates SQL insert statements for the Turso database for given records."""
    statements = []

    main_fields = ["temperature", "humidity", "pressure", "illumination"]
    optional_fields = ["dew_point", "solar_voltage", "battery_voltage"]

    timestamps = [int(record["timestamp"]) for record in records if "timestamp" in record]
    existing_data = fetch_existing_turso_data(timestamps, database_url, auth_token)

    print(f"Found {len(existing_data)} existing records in the database for given timestamps")

    skipped_invalid = 0
    sanitized_count = 0

    for original_record in records:
        # The illumination sensor was not working before this timestamp (1753429449),
        # so any value (including -100 or 0) should be treated as missing (null).
        # After this timestamp, the station started sending null for missing illumination.
        # https://github.com/Kropelki/firmware/pull/17
        ILLUMINATION_NULL_TIMESTAMP = 1753429449
        if "timestamp" in original_record and int(original_record["timestamp"]) < ILLUMINATION_NULL_TIMESTAMP:
            original_record["illumination"] = None

        record = prepare_weather_record(original_record)  # sanitizes and validates in one step
        if record is None:
            skipped_invalid += 1
            continue

        if record != original_record:  # track if sanitization occurred
            sanitized_count += 1

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

    total_skipped = len(records) - len(statements)
    unchanged_skipped = total_skipped - skipped_invalid

    print(f"Generated {len(statements)} statements")
    if sanitized_count > 0:
        print(f"Sanitized {sanitized_count} records by converting invalid sensor readings to null")
    if skipped_invalid > 0:
        print(f"Skipped {skipped_invalid} records with no valid main sensor data")
    if unchanged_skipped > 0:
        print(f"Skipped {unchanged_skipped} unchanged records")

    return statements
