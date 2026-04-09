import json
from datetime import date, datetime
from decimal import Decimal
from db.connection import OracleConnection


def _serialize(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


def format_result_as_text(result: dict) -> str:
    if "affected_rows" in result:
        return f"Statement executed. {result['affected_rows']} rows affected."

    columns = result["columns"]
    rows = result["rows"]

    if not rows:
        return "Query returned 0 rows."

    # Serialize values for display
    display_rows = []
    for row in rows:
        display_rows.append([_serialize(v) if v is not None else "NULL" for v in row])

    # Calculate column widths
    widths = [len(c) for c in columns]
    for row in display_rows[:50]:  # sample first 50 for width calc
        for i, val in enumerate(row):
            widths[i] = max(widths[i], min(len(str(val)), 40))

    # Build text table
    header = " | ".join(c.ljust(widths[i]) for i, c in enumerate(columns))
    separator = "-+-".join("-" * widths[i] for i in range(len(columns)))
    lines = [header, separator]
    for row in display_rows:
        line = " | ".join(str(v)[:40].ljust(widths[i]) for i, v in enumerate(row))
        lines.append(line)

    footer = f"\n({result['row_count']} rows returned"
    if result.get("truncated"):
        footer += ", results truncated"
    footer += ")"
    lines.append(footer)

    return "\n".join(lines)


def result_to_records(result: dict) -> list[dict]:
    if "columns" not in result:
        return []
    columns = result["columns"]
    records = []
    for row in result["rows"]:
        record = {}
        for i, col in enumerate(columns):
            val = row[i]
            record[col] = _serialize(val) if val is not None else None
        records.append(record)
    return records


def result_to_json(result: dict) -> str:
    if "affected_rows" in result:
        return json.dumps(result)
    records = result_to_records(result)
    return json.dumps({"columns": result["columns"], "row_count": result["row_count"],
                        "truncated": result.get("truncated", False), "data": records}, default=_serialize)
