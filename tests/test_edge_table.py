"""Tests for the edge table generator.

Run from the project root with ``python -m unittest discover -s tests -v``.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from edge_table import cli, render  # noqa: E402
from edge_table.generator import (  # noqa: E402
    Edge,
    EdgeTableError,
    edge_id,
    load_edges_from_graph,
    load_edges_from_records,
    normalize_edges,
    synthesize_edges,
)

EXAMPLES = PROJECT_ROOT / "examples"


class SyntheticTest(unittest.TestCase):
    def test_same_seed_is_reproducible(self) -> None:
        first = synthesize_edges(12, 25, seed=7)
        second = synthesize_edges(12, 25, seed=7)
        self.assertEqual(first, second)

    def test_different_seed_differs(self) -> None:
        self.assertNotEqual(synthesize_edges(12, 25, seed=7), synthesize_edges(12, 25, seed=8))

    def test_undirected_synthesis_has_canonical_order(self) -> None:
        edges = synthesize_edges(8, 10, seed=3, directed=False)
        for edge in edges:
            self.assertLessEqual(edge.source, edge.target)

    def test_refuses_more_edges_than_possible(self) -> None:
        with self.assertRaises(EdgeTableError):
            synthesize_edges(3, 100, seed=1)

    def test_weights_stay_inside_requested_range(self) -> None:
        edges = synthesize_edges(10, 30, seed=5, weight_range=(2.0, 2.5))
        for edge in edges:
            self.assertGreaterEqual(edge.weight, 2.0)
            self.assertLessEqual(edge.weight, 2.5)


class NormalizeTest(unittest.TestCase):
    def test_drops_self_loops_by_default(self) -> None:
        edges = [Edge("a", "a"), Edge("a", "b")]
        self.assertEqual([e for e in normalize_edges(edges) if e.source != e.target], normalize_edges(edges))
        self.assertEqual(len(normalize_edges(edges, allow_self_loops=True)), 2)

    def test_undirected_normalizes_endpoint_order(self) -> None:
        edges = [Edge("z", "a"), Edge("a", "z")]
        result = normalize_edges(edges, directed=False)
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0].source, result[0].target), ("a", "z"))

    def test_dedupe_keeps_highest_weight(self) -> None:
        edges = [Edge("a", "b", weight=1.0), Edge("a", "b", weight=9.0), Edge("a", "b", weight=4.0)]
        result = normalize_edges(edges)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].weight, 9.0)

    def test_sorted_output_is_stable(self) -> None:
        edges = [Edge("b", "a"), Edge("a", "c"), Edge("a", "b")]
        self.assertEqual(normalize_edges(edges), normalize_edges(list(reversed(edges))))

    def test_edge_id_is_stable_and_direction_sensitive(self) -> None:
        forward = Edge("a", "b", relation="knows")
        backward = Edge("b", "a", relation="knows")
        self.assertEqual(edge_id(forward), edge_id(Edge("a", "b", relation="knows")))
        self.assertNotEqual(edge_id(forward), edge_id(backward))
        self.assertTrue(edge_id(forward).startswith("e_"))
        self.assertEqual(edge_id(forward, directed=False), edge_id(backward, directed=False))


class RecordsTest(unittest.TestCase):
    def test_reads_example_csv(self) -> None:
        edges = load_edges_from_records(EXAMPLES / "services.csv")
        self.assertEqual(len(edges), 16)
        self.assertEqual(edges[0].source, "api")
        self.assertEqual(edges[0].relation, "reads_from")
        self.assertEqual(edges[0].weight, 3.0)

    def test_missing_column_reports_available_columns(self) -> None:
        with self.assertRaises(EdgeTableError) as ctx:
            load_edges_from_records(EXAMPLES / "services.csv", source_col="nope")
        self.assertIn("available columns", str(ctx.exception))

    def test_missing_file(self) -> None:
        with self.assertRaises(EdgeTableError):
            load_edges_from_records(EXAMPLES / "does-not-exist.csv")

    def test_semicolon_delimiter_is_sniffed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pairs.csv"
            path.write_text("from;to\nx;y\n", encoding="utf-8")
            edges = load_edges_from_records(path, source_col="from", target_col="to")
            self.assertEqual(edges, [Edge("x", "y")])


class GraphTest(unittest.TestCase):
    def test_reads_example_json_with_mixed_link_styles(self) -> None:
        edges = load_edges_from_graph(EXAMPLES / "service-topology.json")
        self.assertEqual(len(edges), 10)
        self.assertEqual(edges[-1].source, "scheduler")
        self.assertEqual(edges[-1].relation, "triggers")

    def test_unknown_node_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_text(json.dumps({"nodes": ["a"], "links": [["a", "b"]]}), encoding="utf-8")
            with self.assertRaises(EdgeTableError) as ctx:
                load_edges_from_graph(path)
            self.assertIn("not declared in 'nodes'", str(ctx.exception))

    def test_invalid_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(EdgeTableError):
                load_edges_from_graph(path)

    def test_document_without_links_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_text(json.dumps({"nodes": ["a"]}), encoding="utf-8")
            with self.assertRaises(EdgeTableError):
                load_edges_from_graph(path)


class RenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.table = render.Table(
            rows=[
                {
                    "edge_id": "e_1",
                    "source": "a",
                    "target": "b",
                    "relation": "knows",
                    "weight": 2.5,
                    "generated_at": "2026-01-01T00:00:00Z",
                }
            ],
            metadata={"title": "Demo", "edge_count": 1},
        )

    def test_csv_has_header_and_rows(self) -> None:
        text = render.render(self.table, "csv")
        lines = text.splitlines()
        self.assertEqual(lines[0], "edge_id,source,target,relation,weight,generated_at")
        self.assertEqual(lines[1], "e_1,a,b,knows,2.5,2026-01-01T00:00:00Z")

    def test_tsv_uses_tabs(self) -> None:
        self.assertIn("\t", render.render(self.table, "tsv").splitlines()[1])

    def test_markdown_has_separator_and_metadata(self) -> None:
        text = render.render(self.table, "md")
        self.assertIn("# Demo", text)
        self.assertIn("| --- |", text)
        self.assertIn("| e_1 | a | b |", text)

    def test_json_round_trips(self) -> None:
        payload = json.loads(render.render(self.table, "json"))
        self.assertEqual(payload["edge_count"], 1)
        self.assertEqual(payload["edges"][0]["source"], "a")
        self.assertEqual(payload["metadata"]["title"], "Demo")

    def test_unknown_format_rejected(self) -> None:
        with self.assertRaises(ValueError):
            render.render(self.table, "xml")


class CliTest(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> int:
        return cli.main(argv)

    def test_generates_csv_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "table.csv"
            code = self.run_cli(
                ["--records", str(EXAMPLES / "services.csv"), "--output", str(out), "--quiet"]
            )
            self.assertEqual(code, 0)
            text = out.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("edge_id,source,target,relation,weight,generated_at"))
            self.assertEqual(len(text.strip().splitlines()), 17)

    def test_generated_at_comes_from_the_clock(self) -> None:
        before = datetime.now(timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "table.csv"
            self.run_cli(["--synthetic", "--nodes", "5", "--edges", "6", "--output", str(out), "--quiet"])
            stamp = out.read_text(encoding="utf-8").splitlines()[1].split(",")[-1]
        moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        self.assertGreaterEqual(moment, before - 1)
        self.assertLessEqual(moment, datetime.now(timezone.utc).timestamp() + 1)

    def test_generated_at_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "table.csv"
            self.run_cli(
                [
                    "--graph",
                    str(EXAMPLES / "service-topology.json"),
                    "--generated-at",
                    "2026-03-04T05:06:07+02:00",
                    "--output",
                    str(out),
                    "--quiet",
                ]
            )
            stamp = out.read_text(encoding="utf-8").splitlines()[1].split(",")[-1]
        self.assertEqual(stamp, "2026-03-04T03:06:07Z")

    def test_invalid_timestamp_is_rejected(self) -> None:
        with self.assertRaises(EdgeTableError):
            cli.parse_timestamp("not-a-date")

    def test_omit_generated_at_drops_the_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "table.csv"
            self.run_cli(
                [
                    "--records",
                    str(EXAMPLES / "services.csv"),
                    "--omit-generated-at",
                    "--output",
                    str(out),
                    "--quiet",
                ]
            )
            header = out.read_text(encoding="utf-8").splitlines()[0]
        self.assertNotIn("generated_at", header)

    def test_undirected_deduplicates_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "table.csv"
            self.run_cli(
                [
                    "--records",
                    str(EXAMPLES / "services.csv"),
                    "--undirected",
                    "--output",
                    str(out),
                    "--quiet",
                ]
            )
            count = len(out.read_text(encoding="utf-8").strip().splitlines()) - 1
        self.assertEqual(count, 16)  # no reversed duplicates in the sample

    def test_stdout_mode(self) -> None:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = self.run_cli(
                ["--synthetic", "--nodes", "4", "--edges", "4", "--seed", "1", "--output", "-"]
            )
        self.assertEqual(code, 0)
        self.assertTrue(buffer.getvalue().startswith("edge_id,source"))

    def test_bad_input_returns_error_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "table.csv"
            code = self.run_cli(["--records", str(Path(tmp) / "missing.csv"), "--output", str(out), "--quiet"])
        self.assertEqual(code, 2)

    def test_default_output_lands_in_out_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path.cwd()
            try:
                import os

                os.chdir(tmp)
                code = self.run_cli(["--synthetic", "--nodes", "4", "--edges", "4", "--quiet"])
                generated = Path("out") / "edge-table.csv"
                self.assertEqual(code, 0)
                self.assertTrue(generated.is_file())
            finally:
                os.chdir(previous)

    def test_markdown_and_json_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "table.md"
            json_path = Path(tmp) / "table.json"
            self.run_cli(["--graph", str(EXAMPLES / "service-topology.json"), "--format", "md", "--output", str(md_path), "--quiet"])
            self.run_cli(["--graph", str(EXAMPLES / "service-topology.json"), "--format", "json", "--output", str(json_path), "--quiet"])
            self.assertIn("| edge_id |", md_path.read_text(encoding="utf-8"))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["edge_count"], 10)
            self.assertEqual(payload["metadata"]["directed"], True)


if __name__ == "__main__":
    unittest.main()
