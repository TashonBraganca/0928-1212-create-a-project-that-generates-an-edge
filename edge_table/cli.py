"""Command line interface for the edge table generator.

Run it as ``python -m edge_table ...`` from the project root.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .generator import (
    DEFAULT_RELATION,
    Edge,
    EdgeTableError,
    edge_id,
    load_edges_from_graph,
    load_edges_from_records,
    normalize_edges,
    synthesize_edges,
)
from .render import COLUMNS, FORMATS, Table, describe_columns, render

DEFAULT_OUTPUT_DIR = "out"


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string ending in ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(raw: str) -> str:
    """Validate and normalize a user supplied ISO 8601 timestamp."""
    text = raw.strip()
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        moment = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise EdgeTableError(f"invalid --generated-at value {raw!r}: {exc}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m edge_table",
        description="Generate an edge table file from records, a graph spec, or a seed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="columns written to every table:\n" + describe_columns(),
    )

    source = parser.add_argument_group("input source (choose exactly one)")
    mode = source.add_mutually_exclusive_group(required=True)
    mode.add_argument("--records", metavar="PATH", help="delimited file with source/target columns")
    mode.add_argument("--graph", metavar="PATH", help="JSON graph specification with a 'links' array")
    mode.add_argument("--synthetic", action="store_true", help="generate random edges from a seed")

    source.add_argument("--source-col", default="source", help="source column for --records (default: source)")
    source.add_argument("--target-col", default="target", help="target column for --records (default: target)")
    source.add_argument("--relation-col", default=None, help="relation column for --records (default: auto-detect)")
    source.add_argument("--weight-col", default=None, help="weight column for --records (default: auto-detect)")
    source.add_argument("--delimiter", default=None, help="field delimiter for --records (default: sniffed)")

    synthetic = parser.add_argument_group("synthetic options")
    synthetic.add_argument("--nodes", type=int, default=10, help="number of nodes (default: 10)")
    synthetic.add_argument("--edges", type=int, default=20, help="number of edges (default: 20)")
    synthetic.add_argument("--seed", type=int, default=0, help="random seed, same seed = same table (default: 0)")
    synthetic.add_argument("--prefix", default="n", help="node id prefix (default: n)")
    synthetic.add_argument(
        "--relation",
        action="append",
        default=None,
        metavar="LABEL",
        help="relation label to pick from; repeatable (default: related_to)",
    )
    synthetic.add_argument(
        "--weight-min", type=float, default=1.0, help="minimum synthetic weight (default: 1.0)"
    )
    synthetic.add_argument(
        "--weight-max", type=float, default=5.0, help="maximum synthetic weight (default: 5.0)"
    )

    shape = parser.add_argument_group("table shape")
    shape.add_argument("--undirected", action="store_true", help="treat edges as undirected (canonical order)")
    shape.add_argument("--keep-self-loops", action="store_true", help="keep edges where source == target")
    shape.add_argument("--no-dedupe", action="store_true", help="keep duplicate edges instead of merging them")

    output = parser.add_argument_group("output")
    output.add_argument(
        "--format",
        choices=FORMATS,
        default="csv",
        help="output format (default: csv)",
    )
    output.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help=f"destination file, '-' for stdout (default: {DEFAULT_OUTPUT_DIR}/edge-table.<format>)",
    )
    output.add_argument("--title", default="Edge table", help="title used in markdown output")
    output.add_argument("--generated-at", default=None, metavar="ISO8601", help="override the run timestamp")
    output.add_argument("--omit-generated-at", action="store_true", help="drop the generated_at column")
    output.add_argument("--meta", default=None, metavar="PATH", help="also write run metadata as JSON")
    output.add_argument("--quiet", "-q", action="store_true", help="do not print the summary line")
    return parser


def _collect_edges(args: argparse.Namespace) -> list[Edge]:
    if args.records:
        return load_edges_from_records(
            args.records,
            source_col=args.source_col,
            target_col=args.target_col,
            relation_col=args.relation_col,
            weight_col=args.weight_col,
            delimiter=args.delimiter,
        )
    if args.graph:
        return load_edges_from_graph(args.graph)
    return synthesize_edges(
        node_count=args.nodes,
        edge_count=args.edges,
        seed=args.seed,
        prefix=args.prefix,
        relations=args.relation or [DEFAULT_RELATION],
        weight_range=(args.weight_min, args.weight_max),
        directed=not args.undirected,
    )


def build_table(args: argparse.Namespace) -> Table:
    """Turn parsed arguments into a ready-to-render :class:`Table`."""
    raw_edges = _collect_edges(args)
    directed = not args.undirected
    edges = normalize_edges(
        raw_edges,
        directed=directed,
        dedupe=not args.no_dedupe,
        allow_self_loops=args.keep_self_loops,
    )
    if not edges:
        raise EdgeTableError("no edges left after normalization (check filters/self-loops)")

    generated_at = parse_timestamp(args.generated_at) if args.generated_at else utc_now_iso()
    rows = [
        {
            "edge_id": edge_id(edge, directed=directed),
            "source": edge.source,
            "target": edge.target,
            "relation": edge.relation,
            "weight": edge.weight,
            "generated_at": generated_at,
        }
        for edge in edges
    ]
    columns = COLUMNS if not args.omit_generated_at else tuple(c for c in COLUMNS if c != "generated_at")

    metadata = {
        "title": args.title,
        "generated_at": generated_at,
        "source": (
            args.records
            or args.graph
            or f"synthetic(nodes={args.nodes}, edges={args.edges}, seed={args.seed})"
        ),
        "directed": directed,
        "deduplicated": not args.no_dedupe,
        "input_edge_count": len(raw_edges),
        "edge_count": len(rows),
        "node_count": len({e.source for e in edges} | {e.target for e in edges}),
    }
    table = Table(rows=rows, metadata=metadata, columns=columns)
    return table


def _default_output(output_format: str) -> Path:
    suffix = "markdown" if output_format == "md" else output_format
    return Path(DEFAULT_OUTPUT_DIR) / f"edge-table.{suffix}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        table = build_table(args)
    except EdgeTableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    columns = table.columns
    rendered = render(table, args.format, columns)

    destination = args.output
    if destination in (None, ""):
        destination = str(_default_output(args.format))

    if destination == "-":
        sys.stdout.write(rendered)
    else:
        path = Path(destination)
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        if not args.quiet:
            print(f"wrote {len(table)} edges -> {path}", file=sys.stderr)

    if args.meta:
        meta_path = Path(args.meta)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(table.metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if not args.quiet:
            print(f"wrote metadata -> {meta_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
