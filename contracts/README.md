# contracts

The interface between the four ModelPassport services. Every service codes against these files, and the tests of every service validate their schemas against them.

The files in `examples/` are generated from section 9 (and the manifest example in section 7) of [`docs/PROJECT_CONTEXT.md`](../docs/PROJECT_CONTEXT.md). That document is the source of truth. Never edit an example file by hand.

Owner: Varun. Everyone else reads this folder only.

## Folder map

| Path | Contents |
|---|---|
| `extract_examples.py` | Reads `docs/PROJECT_CONTEXT.md`, writes every example block to `examples/`, resolves `$include` objects. Stops with an error on invalid JSON. |
| `examples/` | One JSON file per example in the project context (19 files, listed below). |

## Regenerate or check

From the repository root, with Python 3.11 or newer (standard library only):

```
python contracts/extract_examples.py            # write examples/ from the project context
python contracts/extract_examples.py --check    # write nothing, exit 1 if examples/ is out of date
```

## Example files

| File | Shape | Endpoint |
|---|---|---|
| `estate_manifest.M001.json` | Model manifest, also stored as `model_estate/<model folder>/manifest.json` | (file on disk) |
| `redevelop_request.json` | Request body | redev_engine `POST /redevelop` |
| `redevelop_result.M001.json` | RedevelopResult | redev_engine `POST /redevelop`, factory_core `GET /api/models/{model_id}/redevelopment` |
| `validate_request.json` | Request body | validation_lab `POST /validate` |
| `validation_result.M001.json` | ValidationResult | validation_lab `POST /validate` |
| `report_request.json` | Request body | validation_lab `POST /report` |
| `monitor_simulate_request.json` | Request body | validation_lab `POST /monitor/simulate` |
| `monitor_run_request.json` | Request body | validation_lab `POST /monitor/run` |
| `monitoring_result.M001.json` | MonitoringResult | validation_lab `POST /monitor/run`, factory_core `GET /api/models/{model_id}/monitoring` |
| `models_list.json` | `{"models": [ModelSummary]}` | factory_core `GET /api/models` |
| `inventory_record.M001.json` | InventoryRecord | factory_core `GET /api/models/{model_id}` |
| `run.json` | Run | factory_core `GET /api/runs/{run_id}` |
| `gate_decision_request.json` | GateDecision request body | factory_core `POST /api/runs/{run_id}/gates/{stage}/decision` |
| `documentation.M001.json` | Documentation | factory_core `GET /api/models/{model_id}/documentation` |
| `validation_view.M001.json` | ValidationView | factory_core `GET /api/models/{model_id}/validation` |
| `compliance.M001.json` | Compliance | factory_core `GET /api/models/{model_id}/compliance` |
| `audit.json` | Audit | factory_core `GET /api/audit` |
| `factory_metrics.json` | FactoryMetrics | factory_core `GET /api/metrics/factory` |
| `file_view.json` | FileView | factory_core `GET /api/files?path=...` |

Some small shapes are written inline in section 9 and have no example file: `GET /health`, the error body, the `POST /parity` body, `GET /pitfalls`, the `POST /report` response, the `POST /monitor/simulate` response, and the request and response of `POST /api/estate/scan` and `POST /api/models/{model_id}/runs`.

## Rules

* Contracts are frozen. Do not rename fields, change types or add required fields. Optional additions are listed in the owning service README under "Contract additions".
* A change needs agreement in the team chat. Varun then updates `docs/PROJECT_CONTEXT.md`, reruns the script and pushes to `main`.
* `{"$include": "other_file.json"}` in the project context means that the full content of that example belongs at that place. The script resolves it, so the files in `examples/` contain no include objects. It is never sent over the wire.
* All values are illustrative samples so that everyone codes against the same shapes. They are not results and never go into the deck.
