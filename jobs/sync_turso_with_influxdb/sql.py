from typing import List, Dict, Any

from sync_turso_with_influxdb.turso import fetch_existing_turso_data
from sync_turso_with_influxdb.utils import records_are_equal, prepare_weather_record

# The illumination sensor was not working before this timestamp (1753429449),
# so any value (including -100 or 0) should be treated as missing (null).
# After this timestamp, the station started sending null for missing illumination.
# https://github.com/Kropelki/firmware/pull/17
ILLUMINATION_NULL_TIMESTAMP = 1753429449

# The UV sensor started sending invalid values after this timestamp,
# so we treat any UV voltage value as missing (null) from this point onward.
# TODO: set proper stop timestamp when the UV sensor is fixed
UV_VOLTAGE_NULL_START_TIMESTAMP = 1764134696  # 2025-11-26T05:24:56Z
# UV_VOLTAGE_NULL_STOP_TIMESTAMP = 0

# TODO: just store an array of invalid timestamps for each sensor


def create_insert_statements(
    raw_records: List[Dict[str, Any]], turso_database_url: str, turso_auth_token: str
) -> tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """
    Builds a list of upsert statements in the format expected by the Turso client, based
    on the provided raw records, applying necessary transformations and validations.

    Returns:
        Tuple of (statements, existing_data) where existing_data is keyed by timestamp
    """
    statements = []

    # TODO: there is no difference between main and optional fields here??
    main_fields = [
        "temperature",
        "humidity",
        "pressure",
        "illumination",
        "uv_voltage",
        "mc_pm1_0",
        "mc_pm2_5",
        "mc_pm10_0",
    ]
    optional_fields = ["dew_point", "solar_voltage", "battery_voltage"]

    timestamps = [int(record["timestamp"]) for record in raw_records if "timestamp" in record]
    existing_data = fetch_existing_turso_data(timestamps, turso_database_url, turso_auth_token)

    print(f"Found {len(existing_data)} existing records in the Turso database for given timestamps")

    skipped_invalid = 0
    sanitized_count = 0

    for raw_record in raw_records:
        record = dict(raw_record)  # copy to avoid mutating the original

        if "timestamp" in record and int(record["timestamp"]) < ILLUMINATION_NULL_TIMESTAMP:
            record["illumination"] = None
        if "uv_voltage" in record and int(record["timestamp"]) >= UV_VOLTAGE_NULL_START_TIMESTAMP:
            record["uv_voltage"] = None

        sanitized_record = prepare_weather_record(record)  # sanitizes and validates in one step
        if sanitized_record is None:
            skipped_invalid += 1
            continue

        if sanitized_record != record:  # track if prepare_weather_record changed anything
            sanitized_count += 1

        timestamp = int(sanitized_record["timestamp"])
        if timestamp in existing_data:
            existing_record = existing_data[timestamp]
            if records_are_equal(sanitized_record, existing_record):
                continue  # skip this record as it's identical to what's already in the database

        columns = ["timestamp"]
        values = [{"type": "integer", "value": str(int(sanitized_record["timestamp"]))}]

        for field in main_fields + optional_fields:
            if sanitized_record.get(field) is not None:
                columns.append(field)
                values.append({"type": "float", "value": float(sanitized_record[field])})

        sql = f"INSERT OR REPLACE INTO weather ({', '.join(columns)}) VALUES ({', '.join(['?' for _ in columns])})"
        statements.append({"type": "execute", "stmt": {"sql": sql, "args": values}})

    total_skipped = len(raw_records) - len(statements)
    unchanged_skipped = total_skipped - skipped_invalid

    print(f"Generated {len(statements)} statements")
    if sanitized_count > 0:
        print(f"Sanitized {sanitized_count} records by converting invalid sensor readings to null")
    if skipped_invalid > 0:
        print(f"Skipped {skipped_invalid} records with no valid main sensor data")
    if unchanged_skipped > 0:
        print(f"Skipped {unchanged_skipped} unchanged records")

    return statements, existing_data
