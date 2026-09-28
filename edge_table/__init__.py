"""edge_table - build reproducible edge tables from records, graphs, or seeds.

An *edge table* is a flat, machine-readable table describing the edges of a
graph: one row per edge with a stable id, its two endpoints, a relation label,
a weight and the timestamp of the run that produced it.
"""

from .generator import (
    DEFAULT_RELATION,
    DEFAULT_WEIGHT,
    Edge,
    EdgeTableError,
    edge_id,
    load_edges_from_graph,
    load_edges_from_records,
    normalize_edges,
    synthesize_edges,
)
from .render import COLUMNS, Table, render as render_table
from .render import FORMATS  # noqa: F401  (re-exported for convenience)

__all__ = [
    "COLUMNS",
    "DEFAULT_RELATION",
    "DEFAULT_WEIGHT",
    "Edge",
    "EdgeTableError",
    "FORMATS",
    "Table",
    "edge_id",
    "load_edges_from_graph",
    "load_edges_from_records",
    "normalize_edges",
    "render_table",
    "synthesize_edges",
]

__version__ = "1.0.0"
