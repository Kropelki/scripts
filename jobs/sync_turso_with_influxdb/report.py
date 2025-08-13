import os
from datetime import datetime
from typing import List, Dict, Any, Optional


def generate_diff_report(
    weather_records: List[Dict[str, Any]],
    insert_statements: List[Dict[str, Any]],
    existing_data: Dict[int, Dict[str, Any]],
) -> str:
    """
    Generates a human-readable diff report showing all changes that will be made.

    Args:
        weather_records: Original weather records from JSON
        insert_statements: SQL statements that will be executed
        existing_data: Existing records from database keyed by timestamp

    Returns:
        String containing the formatted report
    """
    report_lines = []

    report_lines.append("=" * 80)
    report_lines.append("TURSO DATABASE SYNC REPORT")
    report_lines.append("=" * 80)
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Total records in JSON: {len(weather_records)}")
    report_lines.append(f"Records to be processed: {len(insert_statements)}")
    report_lines.append("")

    # Create a mapping from statements back to records for analysis
    statement_records = []
    for stmt in insert_statements:
        timestamp_arg = stmt["stmt"]["args"][0]  # first arg is always the timestamp
        timestamp = int(timestamp_arg["value"])

        # Find the corresponding record from weather_records
        record = next((r for r in weather_records if int(r.get("timestamp", 0)) == timestamp), None)
        if record:
            statement_records.append((timestamp, record))

    new_records = []
    updated_records = []

    for timestamp, record in statement_records:
        if timestamp in existing_data:
            updated_records.append((timestamp, record, existing_data[timestamp]))
        else:
            new_records.append((timestamp, record))

    report_lines.append("SUMMARY")
    report_lines.append("-" * 40)
    report_lines.append(f"New records to insert: {len(new_records)}")
    report_lines.append(f"Existing records to update: {len(updated_records)}")
    report_lines.append("")

    if new_records:
        report_lines.append("NEW RECORDS")
        report_lines.append("-" * 40)
        for timestamp, record in new_records:
            report_lines.append(
                f"Timestamp: {timestamp} ({datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')})"
            )
            report_lines.append(_format_record(record, "  "))
            report_lines.append("")

    if updated_records:
        report_lines.append("UPDATED RECORDS")
        report_lines.append("-" * 40)
        for timestamp, new_record, old_record in updated_records:
            report_lines.append(
                f"Timestamp: {timestamp} ({datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')})"
            )
            report_lines.append("  Changes:")

            all_fields = set(new_record.keys()) | set(old_record.keys())
            all_fields.discard("timestamp")  

            has_changes = False
            for field in sorted(all_fields):
                old_val = old_record.get(field)
                new_val = new_record.get(field)

                # Convert to comparable types
                if (
                    old_val is not None
                    and isinstance(old_val, str)
                    and old_val.replace(".", "").replace("-", "").isdigit()
                ):
                    try:
                        old_val = float(old_val)
                    except (ValueError, TypeError):
                        pass
                if new_val is not None and not isinstance(new_val, (int, float)):
                    try:
                        new_val = float(new_val)
                    except (ValueError, TypeError):
                        pass

                if old_val != new_val:
                    old_str = _format_value(old_val)
                    new_str = _format_value(new_val)
                    report_lines.append(f"    {field}: {old_str} → {new_str}")
                    has_changes = True

            if not has_changes:
                report_lines.append("    (No field changes detected)")

            report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("END OF REPORT")
    report_lines.append("=" * 80)

    return "\n".join(report_lines)


def _format_record(record: Dict[str, Any], indent: str = "") -> str:
    """Formats a record for display in the report."""
    lines = []
    for key, value in record.items():
        if key != "timestamp":  # shown separately
            lines.append(f"{indent}{key}: {_format_value(value)}")
    return "\n".join(lines)


def _format_value(value: Any) -> str:
    """Formats a value for display in the report."""
    if value is None:
        return "null"
    elif isinstance(value, float):
        return f"{value:.2f}"
    else:
        return str(value)


def save_report_to_file(report_content: str, base_dir: str) -> Optional[str]:
    """
    Saves the report to a file in the .reports directory.

    Args:
        report_content: The report content to save
        base_dir: Base directory (should be the jobs directory)

    Returns:
        Path to the saved file, or None if saving failed
    """
    try:
        reports_dir = os.path.join(base_dir, ".reports")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sync_report_{timestamp}.txt"
        filepath = os.path.join(reports_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report_content)

        return filepath
    except Exception as e:
        print(f"Error saving report: {e}")
        return None
