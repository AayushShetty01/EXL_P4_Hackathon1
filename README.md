# ModelPassport

An agentic model risk factory. EXL x UCD Data and AI Hackathon 2026, Challenge 04.

A Tier 1 UK retail bank runs about 250 credit, fraud and pricing models in SAS, R and Python. Under PRA SS1/23 each model needs current documentation and independent validation, yet the documents are outdated and one validation takes 8 to 12 weeks. ModelPassport takes a legacy model folder (code, a stale model document, data) and produces a **Model Passport**: one evidence pack per model with five stamps. An AI agent or a deterministic engine produces each stamp, and a human reviewer countersigns it before the next stage starts.

| Stamp | Stage | What is produced | Produced by |
|---|---|---|---|
| 1 | Discover | Inventory record and risk tier | factory_core |
| 2 | Document | Current model documentation where every claim cites code lines, plus the differences against the old document | factory_core |
| 3 | Redevelop | Python rebuild of the SAS or R model, unit tests, four level parity certificate | redev_engine |
| 4 | Validate | Discrimination, calibration, stability, fairness, findings, report | validation_lab (numbers), factory_core (words) |
| 5 | Monitor | Drift monitoring on simulated production batches with an automatic revalidation trigger | validation_lab, factory_core |

Three design rules:

* **Every claim is cited.** Anything an LLM writes about a model points to file and line evidence, and code checks that the evidence exists. Unverified claims are flagged, never hidden.
* **Every number is computed.** Metrics, coefficients and statistics come from deterministic code only. The LLM writes words around them, and a checker confirms every number in those words.
* **Every gate is signed.** Agents never approve their own work. Human decisions go into a tamper evident audit trail, and the person who approves validation cannot be the person who approved redevelopment.

The full specification, including every API contract, is in [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md).

## Repository map

| Path | What it is | Owner |
|---|---|---|
| `README.md` | Start here: what the project is, repository map, how to run it | Varun |
| `.env.example` | Every setting, each with a comment | Varun |
| `.gitignore` | Files git never tracks | Varun |
| `docs/` | Project documents. Today: `PROJECT_CONTEXT.md` | Varun |
| `contracts/` | Example request and response for every API, generated from the project context | Varun |
| `model_estate/` | The sample bank: legacy models, data, golden outputs | Dhrishit |
| `factory_core/` | Service 1: orchestrator, agents, API for the dashboard | Varun |
| `redev_engine/` | Service 2: SAS and R to Python rebuild, parity proof | Dhrishit |
| `validation_lab/` | Service 3: validation, fairness, monitoring, report | Harshit |
| `factory_console/` | Service 4: web dashboard | Aayush |
| `artifacts/` | Run outputs, created at run time, ignored by git | (generated) |

Each folder is created and maintained by its owner.

## Team and ownership

| Member | Service | Owns these paths (and nothing else) | Port | Branch |
|---|---|---|---|---|
| Varun | factory_core: agent orchestrator, inventory, documentation agents, governance API. Integration lead. | `factory_core/`, `contracts/`, `docs/`, root files | 8000 | `feat/factory_core_varun` |
| Dhrishit | redev_engine: the sample model estate, SAS and R to Python rebuild, parity proof. Repository owner. | `redev_engine/`, `model_estate/` | 8001 | `feat/redev_engine` |
| Harshit | validation_lab: validation metrics, fairness, monitoring, report rendering | `validation_lab/` | 8002 | `feat/validation_lab` |
| Aayush | factory_console: the web dashboard | `factory_console/` | 5173 | `feat/factory_console` |

Each member creates and changes files only inside their own paths, works on their own branch and commits by hand with one plain line in the form `[service] what changed`. A problem in someone else's folder goes to its owner.

## How to run

The services are being built. The commands below are the intended entry points; each service README is the reference for its own setup and is updated as the service lands.

Prerequisites: Python 3.11 or newer, Node.js with npm.

```
cp .env.example .env        # then fill in LLM_API_KEY and LLM_MODEL, or set LLM_MODE=replay
```

| Service | Port | Start command, run inside the service folder |
|---|---|---|
| factory_core | 8000 | `uvicorn app.main:app --port 8000` |
| redev_engine | 8001 | `uvicorn app.main:app --port 8001` |
| validation_lab | 8002 | `uvicorn app.main:app --port 8002` |
| factory_console | 5173 | `npm install`, then `npm run dev` |

The dashboard talks only to factory_core. factory_core calls redev_engine and validation_lab. Every service can also start on its own with stub or sample data that follows `contracts/examples/`.

## Contracts

`contracts/examples/` holds one JSON example per API shape. Regenerate or check them from the repository root:

```
python contracts/extract_examples.py
python contracts/extract_examples.py --check
```

## Data

Public or synthetic data only, never personal data. Model owners appear as role titles.
