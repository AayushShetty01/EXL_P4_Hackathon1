# factory_core

Service 1 of ModelPassport. Owner: Varun. Port 8000. Branch `feat/factory_core`.

## What this is

The brain and the front door of ModelPassport:

* The only API the dashboard (factory_console) talks to.
* Runs the five stage pipeline for a model (discover, document, redevelop, validate, monitor) and pauses at a human gate after every stage.
* Hosts the LLM agents for discovery, documentation and the validation narrative, plus the code checks that verify their evidence and numbers.
* Calls redev_engine and validation_lab over HTTP for the heavy work.
* Keeps the model inventory, run state and the hash chained audit trail in SQLite.

## Folder map

| Path | Contents |
|---|---|
| `README.md` | This file |

The service code is being added. Rows appear here as each part lands.

## How to run

From this folder, once the service code is in place:

```
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

## How to test

```
pytest
```

## Environment variables

Read from the root `.env` (see `.env.example`): `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_MODEL_VALIDATOR`, `LLM_MODE`, `LLM_TEMPERATURE`, `REDEV_ENGINE_URL`, `VALIDATION_LAB_URL`, `USE_STUBS`, `ESTATE_DIR`, `ARTIFACTS_DIR`.

## API

Section 9.3 of [`docs/PROJECT_CONTEXT.md`](../docs/PROJECT_CONTEXT.md). Example responses are in [`contracts/examples/`](../contracts/examples/).
