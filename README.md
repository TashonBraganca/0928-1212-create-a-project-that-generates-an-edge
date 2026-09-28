# edge-table generator

A small, dependency-free Python project that generates an **edge table file** —
a flat table describing the edges of a graph — and can write it as CSV, TSV,
Markdown or JSON.

```
edge_id,source,target,relation,weight,generated_at
e_1e0d1a0f0b,api,cache,reads_from,3,<UTC run time>
e_9a3c77b2de,api,db,reads_from,5,<UTC run time>
```

## Columns

| column | meaning |
| --- | --- |
| `edge_id` | stable content hash of `source` + `target` + `relation` (same input → same id) |
| `source` | origin node |
| `target` | destination node |
| `relation` | label describing the connection |
| `weight` | numeric strength of the connection |
| `generated_at` | UTC timestamp of the run in ISO 8601 — read from the clock at run time, never baked into the code |

## Requirements

Python 3.10+ standard library only. No third-party packages.

## Quick start

```bash
# from a JSON graph specification
python -m edge_table --graph examples/service-topology.json --output out/topology.csv

# from a delimited file of records
python -m edge_table --records examples/services.csv --format tsv --output out/services.tsv

# synthetically, reproducibly (same seed → identical file)
python -m edge_table --synthetic --nodes 25 --edges 60 --seed 1337 \
  --format json --output out/synthetic-edges.json

# everything that is committed in out/
make generate

# test suite
make test
```

Add `--output -` to stream the table to stdout instead of writing a file.

## Input sources

Pick exactly one:

| flag | input |
| --- | --- |
| `--records PATH` | CSV/TSV/semicolon file with `source` and `target` columns (delimiter is sniffed). `relation` and `weight` columns are auto-detected, or name them with `--relation-col` / `--weight-col`. |
| `--graph PATH` | JSON object with a `links` array (and optional `nodes` array). Each link can be an object (`{"source": ..., "target": ..., "relation": ..., "weight": ...}`) or a compact array (`["a","b"]`, `["a","b",2.5]`, `["a","b",2.5,"calls"]`). When `nodes` is declared, unknown endpoints are rejected. |
| `--synthetic` | random edges from `--nodes`, `--edges`, `--seed`, `--prefix`, `--relation` and `--weight-min/--weight-max`. Deterministic for a given seed. |

## Useful options

| option | effect |
| --- | --- |
| `--format {csv,tsv,md,json}` | output format (default `csv`) |
| `--output PATH` / `-o` | destination file; defaults to `out/edge-table.<format>` |
| `--undirected` | canonicalize each pair so `source <= target`, then deduplicate |
| `--no-dedupe` | keep duplicate edges instead of merging them (highest weight wins by default) |
| `--keep-self-loops` | keep rows where `source == target` (dropped by default) |
| `--generated-at ISO8601` | pin the timestamp, useful for reproducible builds; validated and normalized to UTC `Z` |
| `--omit-generated-at` | drop the `generated_at` column entirely |
| `--meta PATH` | also write run metadata (source, counts, directedness) as JSON |
| `--title TEXT` | heading used in Markdown output |
| `--quiet` | suppress the summary line on stderr |

Errors (missing file, unknown column, undeclared node, impossible edge count)
exit with status `2` and a message on stderr.

## Project layout

```
edge_table/
  generator.py   # load records/graphs, synthesize edges, normalize
  render.py      # csv / tsv / markdown / json serializers
  cli.py         # argparse front end
  __main__.py    # python -m entry point
examples/        # sample records.csv and service-topology.json
tests/           # unittest suite (reproducibility, normalization, CLI)
out/             # generated edge table files, committed
Makefile         # make generate / make test / make demo
```

## Notes on determinism

Edge ids are content hashes, synthetic edges are drawn from a seeded
`random.Random`, and rows are sorted by `(source, target, relation, weight)`.
Only `generated_at` varies between runs — pass `--generated-at` when you need a
byte-identical file twice.
