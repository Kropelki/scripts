import json
from datetime import datetime
from typing import Dict, Any

# BMP280 (pressure):
#   https://www.alldatasheet.com/datasheet-pdf/view/1132069/BOSCH/BMP280.html
# AHT20 (temperature and humidity):
#   https://static.maritex.eu/file/display/RNvX5GenZti93oVcmXPk9n_PKbFzX2F0/AHT20.pdf
# BH1750 (illumination):
#   https://www.handsontec.com/dataspecs/sensor/BH1750%20Light%20Sensor.pdf
VALID_SENSOR_RANGES = {
    "temperature": (-40.0, 85.0),  # Celsius
    "humidity": (0.0, 100.0),  # percentage
    "pressure": (300.0, 1100.0),  # hPa
    "illumination": (0.0, 65535.0),  # lux
}


def _convert_timestamp_to_unix(timestamp) -> int:
    """
    Converts a timestamp to Unix timestamp (seconds since epoch).

    Handles two formats:
    1. Unix timestamp (integer or string that can be converted to int)
    2. ISO 8601 format (e.g., "2025-06-22T09:55:53.637002962Z")
    """
    if timestamp is None:
        raise ValueError("Timestamp cannot be None")

    if isinstance(timestamp, int):
        return timestamp
    if isinstance(timestamp, float):
        return int(timestamp)

    if isinstance(timestamp, str):
        try:  # try to convert directly to int first
            return int(timestamp)
        except ValueError:
            pass

        try:  # try to parse ISO 8601 format
            if timestamp.endswith("Z"):
                timestamp = timestamp[:-1]
            return int(datetime.fromisoformat(timestamp).timestamp())  # in seconds
        except ValueError:
            pass

    raise ValueError(f"Unrecognized timestamp format: {timestamp} (type: {type(timestamp)})")


def _is_valid_sensor_reading(field: str, value: Any) -> bool:
    """Validates a sensor reading to ensure it is within valid and reasonable ranges."""
    if value is None:
        # Missing data is acceptable as we already nullify invalid readings at firmware level
        return True

    try:
        value = float(value)
    except (ValueError, TypeError):
        return False

    if field not in VALID_SENSOR_RANGES:
        return False  # treat unknown fields as invalid since we don't know their ranges

    min_val, max_val = VALID_SENSOR_RANGES[field]
    return min_val <= value <= max_val


def prepare_weather_record(record: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Sanitizes a weather record by converting invalid sensor readings to None,
    then validates if at least one main sensor reading is valid.
    Returns the sanitized record if valid, None if should be skipped.
    """
    sanitized_record = record.copy()
    for field, value in record.items():
        if field != "timestamp" and value is not None:
            if not _is_valid_sensor_reading(field, value):
                sanitized_record[field] = None

    # Then validate: check if we have at least one valid main sensor reading
    # Similar to Measurement::hasSensorData() from the firmware:
    # https://github.com/Kropelki/firmware/blob/24204939d829b84a7638a889c41294f559c0bc4b/src/measurement.cpp#L51-L55
    main_fields = ["temperature", "humidity", "pressure", "illumination"]
    has_valid_main_sensor_data = any(sanitized_record.get(field) is not None for field in main_fields)

    return sanitized_record if has_valid_main_sensor_data else None


def load_json_data(file_path: str) -> Dict[str, Any]:
    """Loads JSON data from a file. Handles some common errors."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file '{file_path}': {e}")


def records_are_equal(record1: Dict[str, Any], record2: Dict[str, Any]) -> bool:
    """Compares two records for equality, ignoring None values."""
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
