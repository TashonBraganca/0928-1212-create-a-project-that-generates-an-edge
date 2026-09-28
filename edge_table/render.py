"""Render an edge table as CSV, TSV, Markdown or JSON."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Any, Sequence

#: Column order of the generated table.
COLUMNS: tuple[str, ...] = ("edge_id", "source", "target", "relation", "weight", "generated_at")

FORMATS: tuple[str, ...] = ("csv", "tsv", "md", "json")

_DELIMITERS = {"csv": ",", "tsv": "\t"}

_COLUMN_HELP = {
    "edge_id": "stable hash of source, target and relation",
    "source": "origin node",
    "target": "destination node",
    "relation": "label describing the connection",
    "weight": "numeric strength of the connection",
    "generated_at": "UTC timestamp of the run, ISO 8601",
}


@dataclass
class Table:
    """A finished edge table plus the metadata describing how it was built."""

    rows: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)
    columns: tuple[str, ...] = COLUMNS

    def __len__(self) -> int:
        return len(self.rows)


def _cell(row: dict[str, Any], column: str) -> str:
    value = row.get(column, "")
    if isinstance(value, float):
        return format(value, "g")
    return str(value)


def _delimited(rows: Sequence[dict[str, Any]], columns: Sequence[str], delimiter: str) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row, column) for column in columns])
    return buffer.getvalue()


def _markdown(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> str:
    def clean(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ").strip()

    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join(" --- " for _ in columns) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(clean(_cell(row, column)) for column in columns) + " |")
    return "\n".join(lines) + "\n"


def render(table: Table, output_format: str, columns: Sequence[str] | None = None) -> str:
    """Serialize ``table`` in ``output_format`` (csv, tsv, md or json)."""
    columns = tuple(columns) if columns else table.columns
    if output_format not in FORMATS:
        raise ValueError(f"unsupported format {output_format!r}; choose from {', '.join(FORMATS)}")

    if output_format == "json":
        payload = {
            "metadata": table.metadata,
            "columns": list(columns),
            "edge_count": len(table.rows),
            "edges": [{column: row.get(column) for column in columns} for row in table.rows],
        }
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"

    if output_format == "md":
        header = table.metadata.get("title", "Edge table")
        body = _markdown(table.rows, columns)
        if not table.metadata:
            return body
        lines = [f"# {header}", ""]
        for key, value in table.metadata.items():
            if key == "title":
                continue
            lines.append(f"- **{key}**: {value}")
        lines.extend(["", *body.splitlines()])
        return "\n".join(lines) + "\n"

    return _delimited(table.rows, columns, _DELIMITERS[output_format])


def describe_columns(columns: Sequence[str] = COLUMNS) -> str:
    """Return a human readable description of the table columns."""
    width = max(len(column) for column in columns)
    return "\n".join(f"  {column.ljust(width)}  {_COLUMN_HELP.get(column, '')}" for column in columns)
