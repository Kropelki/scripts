from typing import List, Dict, Any

from sync_turso_with_influxdb.turso import fetch_existing_turso_data
from sync_turso_with_influxdb.utils import records_are_equal

def create_insert_statements(
    records: List[Dict[str, Any]], database_url: str, auth_token: str
) -> List[Dict[str, Any]]:
    """Creates SQL insert statements for the Turso database for given records."""
    statements = []

    main_fields = ["temperature", "humidity", "pressure", "illumination"]
    optional_fields = ["dew_point", "solar_voltage", "battery_voltage"]

    timestamps = [
        int(record["timestamp"]) for record in records if "timestamp" in record
    ]
    existing_data = fetch_existing_turso_data(timestamps, database_url, auth_token)

    print(f"Found {len(existing_data)} existing records in the database for given timestamps")

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
