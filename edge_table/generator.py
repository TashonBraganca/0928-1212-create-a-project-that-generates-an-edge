"""Load or synthesize edges and normalize them into a canonical edge table.

Everything in this module is deterministic: given the same inputs (and the same
seed, for synthetic edges) the produced table is byte-for-byte identical. No
value that depends on the calendar is ever written into this file - timestamps
are supplied by the caller at run time.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

DEFAULT_RELATION = "related_to"
DEFAULT_WEIGHT = 1.0

#: Column names accepted as endpoints when reading a graph specification.
_SOURCE_KEYS = ("source", "src", "from", "u", "a", "node1")
_TARGET_KEYS = ("target", "dst", "to", "v", "b", "node2")
_RELATION_KEYS = ("relation", "type", "label", "kind")
_WEIGHT_KEYS = ("weight", "value", "cost", "w")


class EdgeTableError(ValueError):
    """Raised when input data cannot be turned into a valid edge table."""


@dataclass(frozen=True)
class Edge:
    """A single directed (or undirected) connection between two nodes."""

    source: str
    target: str
    relation: str = DEFAULT_RELATION
    weight: float = DEFAULT_WEIGHT

    def key(self, directed: bool) -> tuple[str, str, str]:
        """Return the identity of this edge for de-duplication purposes."""
        if directed:
            return (self.source, self.target, self.relation)
        left, right = sorted((self.source, self.target))
        return (left, right, self.relation)


def edge_id(edge: Edge, directed: bool = True) -> str:
    """Return a stable, content-addressed id for an edge.

    The id only depends on the endpoints and the relation, so regenerating a
    table from the same input yields the same ids regardless of when it runs.
    """
    if not directed:
        left, right = sorted((edge.source, edge.target))
        source, target = left, right
    else:
        source, target = edge.source, edge.target
    payload = "\x1f".join((source, target, edge.relation)).encode("utf-8")
    return "e_" + hashlib.sha256(payload).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Input loaders
# ---------------------------------------------------------------------------


def _read_rows(path: str | Path, delimiter: str | None = None) -> list[dict[str, str]]:
    """Read a delimited text file into a list of dictionaries."""
    file_path = Path(path)
    if not file_path.is_file():
        raise EdgeTableError(f"input file not found: {file_path}")

    text = file_path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise EdgeTableError(f"input file is empty: {file_path}")

    if delimiter is None:
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","

    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise EdgeTableError(f"input file has no header row: {file_path}")
    return [dict(row) for row in reader]


def _pick(row: dict[str, Any], candidates: Sequence[str]) -> Any:
    """Return the first value of ``row`` whose key matches one of ``candidates``."""
    for key in candidates:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _as_weight(raw: Any, where: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise EdgeTableError(f"weight must be a number in {where}: {raw!r}") from exc


def _as_text(raw: Any, field: str, where: str) -> str:
    if raw is None or str(raw).strip() == "":
        raise EdgeTableError(f"missing {field} in {where}")
    return str(raw).strip()


def load_edges_from_records(
    path: str | Path,
    source_col: str = "source",
    target_col: str = "target",
    relation_col: str | None = None,
    weight_col: str | None = None,
    delimiter: str | None = None,
) -> list[Edge]:
    """Build edges from a delimited file of records (CSV/TSV/semicolon).

    ``source_col``/``target_col`` must exist; the relation and weight columns
    are optional and fall back to the module defaults when absent.
    """
    rows = _read_rows(path, delimiter=delimiter)
    header = list(rows[0].keys())
    for column in (source_col, target_col):
        if column not in header:
            raise EdgeTableError(
                f"column {column!r} not found in {path}; available columns: "
                + ", ".join(repr(name) for name in header)
            )

    edges: list[Edge] = []
    for index, row in enumerate(rows, start=2):  # line 1 is the header
        where = f"{path} line {index}"
        source = _as_text(row.get(source_col), source_col, where)
        target = _as_text(row.get(target_col), target_col, where)
        relation = DEFAULT_RELATION
        if relation_col:
            if relation_col not in header:
                raise EdgeTableError(
                    f"column {relation_col!r} not found in {path}; available columns: "
                    + ", ".join(repr(name) for name in header)
                )
            relation = _as_text(row.get(relation_col), relation_col, where)
        else:
            found = _pick(row, _RELATION_KEYS)
            if found not in (None, ""):
                relation = str(found).strip()
        weight = DEFAULT_WEIGHT
        if weight_col:
            weight = _as_weight(row.get(weight_col), where)
        else:
            found = _pick(row, _WEIGHT_KEYS)
            if found not in (None, ""):
                weight = _as_weight(found, where)
        edges.append(Edge(source, target, relation, weight))
    return edges


def load_edges_from_graph(path: str | Path) -> list[Edge]:
    """Build edges from a JSON graph specification.

    The document may look like::

        {"nodes": ["a", "b"],
         "links": [{"source": "a", "target": "b", "relation": "knows",
                    "weight": 2.5}]}

    ``links`` (or ``edges``) may also be compact triples/quadruples:
    ``["a", "b"]``, ``["a", "b", 2.5]`` or ``["a", "b", 2.5, "knows"]``.
    When ``nodes`` is present, every endpoint must be listed there.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise EdgeTableError(f"input file not found: {file_path}")
    try:
        document = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EdgeTableError(f"{file_path} is not valid JSON: {exc}") from exc

    if isinstance(document, list):
        document = {"links": document}
    if not isinstance(document, dict):
        raise EdgeTableError(f"{file_path} must contain a JSON object or array")

    raw_links = document.get("links", document.get("edges"))
    if raw_links is None:
        raise EdgeTableError(f"{file_path} has no 'links' (or 'edges') array")
    if not isinstance(raw_links, list):
        raise EdgeTableError(f"'links' in {file_path} must be a list")

    known_nodes: set[str] | None = None
    if "nodes" in document:
        raw_nodes = document["nodes"]
        if not isinstance(raw_nodes, list):
            raise EdgeTableError(f"'nodes' in {file_path} must be a list")
        known_nodes = {str(node) for node in raw_nodes}

    edges: list[Edge] = []
    for index, item in enumerate(raw_links):
        where = f"{file_path} links[{index}]"
        if isinstance(item, dict):
            source = _as_text(_pick(item, _SOURCE_KEYS), "source", where)
            target = _as_text(_pick(item, _TARGET_KEYS), "target", where)
            relation_raw = _pick(item, _RELATION_KEYS)
            relation = str(relation_raw).strip() if relation_raw not in (None, "") else DEFAULT_RELATION
            weight_raw = _pick(item, _WEIGHT_KEYS)
            weight = _as_weight(weight_raw, where) if weight_raw not in (None, "") else DEFAULT_WEIGHT
        elif isinstance(item, (list, tuple)):
            if len(item) < 2:
                raise EdgeTableError(f"{where} needs at least two elements")
            source = _as_text(item[0], "source", where)
            target = _as_text(item[1], "target", where)
            weight = _as_weight(item[2], where) if len(item) > 2 else DEFAULT_WEIGHT
            relation = str(item[3]).strip() if len(item) > 3 and item[3] not in (None, "") else DEFAULT_RELATION
        else:
            raise EdgeTableError(f"{where} must be an object or an array")

        if known_nodes is not None:
            for endpoint, label in ((source, "source"), (target, "target")):
                if endpoint not in known_nodes:
                    raise EdgeTableError(
                        f"{where}: {label} {endpoint!r} is not declared in 'nodes'"
                    )
        edges.append(Edge(source, target, relation, weight))

    if not edges:
        raise EdgeTableError(f"{file_path} contains no links")
    return edges


def synthesize_edges(
    node_count: int,
    edge_count: int,
    seed: int = 0,
    prefix: str = "n",
    relations: Sequence[str] = (DEFAULT_RELATION,),
    weight_range: tuple[float, float] = (1.0, 5.0),
    directed: bool = True,
) -> list[Edge]:
    """Create a reproducible random edge set.

    The same ``(node_count, edge_count, seed, ...)`` tuple always produces the
    same edges, so a synthetic table can be regenerated exactly.
    """
    if node_count < 2:
        raise EdgeTableError("--nodes must be at least 2")
    if edge_count < 1:
        raise EdgeTableError("--edges must be at least 1")
    if not relations:
        raise EdgeTableError("at least one relation label is required")

    nodes = [f"{prefix}{index}" for index in range(1, node_count + 1)]
    max_edges = node_count * (node_count - 1) if directed else node_count * (node_count - 1) // 2
    if edge_count > max_edges:
        raise EdgeTableError(
            f"cannot create {edge_count} unique "
            f"{'directed' if directed else 'undirected'} edges "
            f"across {node_count} nodes (maximum is {max_edges})"
        )

    low, high = sorted(weight_range)
    rng = random.Random(seed)
    seen: set[tuple[str, str]] = set()
    edges: list[Edge] = []
    while len(edges) < edge_count:
        source, target = rng.sample(nodes, 2)
        if not directed:
            source, target = sorted((source, target))
        if (source, target) in seen:
            continue
        seen.add((source, target))
        weight = round(rng.uniform(low, high), 2)
        relation = rng.choice(list(relations))
        edges.append(Edge(source, target, relation, weight))
    return edges


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_edges(
    edges: Iterable[Edge],
    directed: bool = True,
    dedupe: bool = True,
    allow_self_loops: bool = False,
) -> list[Edge]:
    """Canonicalize edges: drop self-loops, deduplicate and sort.

    For undirected graphs each edge is re-ordered so ``source <= target``.
    When duplicates share the same identity the one with the highest weight is
    kept, which makes the result independent of input ordering.
    """
    kept: list[Edge] = []
    for edge in edges:
        if edge.source == edge.target and not allow_self_loops:
            continue
        if not directed and edge.source > edge.target:
            edge = replace(edge, source=edge.target, target=edge.source)
        kept.append(edge)

    if dedupe:
        best: dict[tuple[str, str, str], Edge] = {}
        for edge in kept:
            current = best.get(edge.key(directed))
            if current is None or edge.weight > current.weight:
                best[edge.key(directed)] = edge
        kept = list(best.values())

    kept.sort(key=lambda e: (e.source, e.target, e.relation, e.weight))
    return kept
