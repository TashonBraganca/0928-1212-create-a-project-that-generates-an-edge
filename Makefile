PYTHON ?= python3
FORMAT ?= csv
SEED ?= 1337

.PHONY: test generate demo columns help

help:
	@$(PYTHON) -m edge_table --help

test:
	$(PYTHON) -m unittest discover -s tests -v

# Regenerates every committed edge table file under out/.
generate:
	$(PYTHON) -m edge_table --graph examples/service-topology.json --format csv --output out/service-topology.csv --meta out/service-topology.meta.json
	$(PYTHON) -m edge_table --graph examples/service-topology.json --format md --title "Service topology edge table" --output out/service-topology.md
	$(PYTHON) -m edge_table --records examples/services.csv --format tsv --output out/services.tsv
	$(PYTHON) -m edge_table --synthetic --nodes 25 --edges 60 --seed $(SEED) --relation calls --relation observes --format json --output out/synthetic-edges.json --meta out/synthetic-edges.meta.json

demo: generate
	@echo "--- out/service-topology.md ---"
	@cat out/service-topology.md

columns:
	@$(PYTHON) -m edge_table --help | tail -n 8
