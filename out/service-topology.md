# Service topology edge table

- **generated_at**: 2026-09-28T06:48:02Z
- **source**: examples/service-topology.json
- **directed**: True
- **deduplicated**: True
- **input_edge_count**: 10
- **edge_count**: 10
- **node_count**: 8

| edge_id | source | target | relation | weight | generated_at |
| --- | --- | --- | --- | --- | --- |
| e_04c23365e7 | api | auth | verifies_with | 4 | 2026-09-28T06:48:02Z |
| e_ce61b5bd51 | api | cache | reads_from | 3 | 2026-09-28T06:48:02Z |
| e_335b8ae6e1 | api | db | reads_from | 5 | 2026-09-28T06:48:02Z |
| e_fe8984d5fb | api | queue | publishes_to | 2 | 2026-09-28T06:48:02Z |
| e_eff3415d32 | scheduler | queue | publishes_to | 3 | 2026-09-28T06:48:02Z |
| e_7c14536e25 | scheduler | worker | triggers | 2 | 2026-09-28T06:48:02Z |
| e_44cbd31d1c | web | api | calls | 5 | 2026-09-28T06:48:02Z |
| e_13b4f98ff5 | web | auth | calls | 4 | 2026-09-28T06:48:02Z |
| e_854eb40fd8 | worker | db | writes_to | 5 | 2026-09-28T06:48:02Z |
| e_66d8e8d96b | worker | queue | consumes | 4 | 2026-09-28T06:48:02Z |
