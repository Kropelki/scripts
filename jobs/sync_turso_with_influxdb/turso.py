import json
import urllib.request

from typing import List, Dict, Any, Optional


def _create_turso_request(payload: Dict[str, Any], database_url: str, auth_token: str) -> urllib.request.Request:
    """Creates an HTTP request for Turso API."""
    # https://docs.turso.tech/sdk/http/quickstart
    data = json.dumps(payload).encode("utf-8")
    return urllib.request.Request(
        database_url,
        data=data,
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )


def _execute_turso_request(req: urllib.request.Request) -> Optional[Dict[str, Any]]:
    """Executes a Turso HTTP request and returns parsed JSON response."""
    # https://docs.turso.tech/sdk/http/quickstart#response
    try:
        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode("utf-8")
            return json.loads(response_data)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        try:
            error_response = e.read().decode("utf-8")
            print(f"Error response: {error_response}")
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"Error executing a Turso request: {e}")
        return None


def _parse_query_result(result: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """Parses query result from Turso response and extracts records keyed by timestamp."""
    # https://docs.turso.tech/sdk/http/quickstart#response
    existing_records = {}
    if "results" in result and len(result["results"]) > 0:
        query_result = result["results"][0]
        if query_result.get("type") == "ok" and "response" in query_result:
            response_data = query_result["response"]
            if response_data.get("type") == "execute" and "result" in response_data:
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


def send_to_turso(sql_statements: List[Dict[str, Any]], database_url: str, auth_token: str) -> bool:
    """Sends prepared SQL statements to the Turso database. Returns True if successful."""
    payload = {"requests": sql_statements + [{"type": "close"}]}
    request = _create_turso_request(payload, database_url, auth_token)
    result = _execute_turso_request(request)

    if result is None:
        return False

    if "results" in result:
        for i, res in enumerate(result["results"]):
            if res.get("type") == "error":
                print(f"Error in statement {i}: {res.get('error', {})}")
                return False

        print(f"Successfully inserted {len(sql_statements)} records to the database")
        return True
    else:
        print(f"Unexpected response format: {result}")
        return False


def fetch_existing_turso_data(timestamps: List[int], database_url: str, auth_token: str) -> Dict[int, Dict[str, Any]]:
    """Fetches existing records from the Turso database for given timestamps."""
    if not timestamps:
        return {}

    min_timestamp = min(timestamps)
    max_timestamp = max(timestamps)

    query = "SELECT * FROM weather WHERE timestamp >= ? AND timestamp <= ?"
    args = [
        {"type": "integer", "value": str(min_timestamp)},
        {"type": "integer", "value": str(max_timestamp)},
    ]
    payload = {"requests": [{"type": "execute", "stmt": {"sql": query, "args": args}}, {"type": "close"}]}

    req = _create_turso_request(payload, database_url, auth_token)
    result = _execute_turso_request(req)

    if result is None:
        print("Warning: Could not fetch existing data from Turso")
        return {}

    return _parse_query_result(result)


"""
# https://docs.turso.tech/sdk/http/quickstart

-> Example JSON payload for Turso HTTP API:
{
  "requests": [
    {
      "type": "execute",
      "stmt": {"sql": "SELECT * FROM weather"}
    },
    {"type": "close"}
  ]
}

-> Example response from Turso HTTP API:
{
  "baton": null,
  "base_url": null,
  "results": [
    {
      "type": "ok",
      "response": {
        "type": "execute",
        "result": {"cols": [], "rows": [], "affected_row_count": 0, "last_insert_rowid": null, "replication_index": "1"}
      }
    },
    {
      "type": "ok",
      "response": {"type": "close"}
    }
  ]
}
"""
