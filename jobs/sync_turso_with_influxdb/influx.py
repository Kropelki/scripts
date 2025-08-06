from typing import List, Dict, Any


def extract_weather_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extracts weather records from the InfluxDB query result saved in JSON format."""
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
