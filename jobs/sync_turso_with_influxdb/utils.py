import json
from typing import Dict, Any


def load_json_data(file_path: str) -> Dict[str, Any]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file '{file_path}': {e}")


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
