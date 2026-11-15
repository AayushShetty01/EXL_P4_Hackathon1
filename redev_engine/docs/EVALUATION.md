# Evaluation

Measured results for the deck. Every number in this file comes from a real run. A row without a measurement says so.

## Status

| Measure | M002 (R) | M001 (SAS) |
|---|---|---|
| First pass parity with the pitfall library | Not measured yet | Waiting for SAS golden files |
| Heal iterations needed with the pitfall library | Not measured yet | Waiting for SAS golden files |
| First pass parity without the pitfall library | Not measured yet | Waiting for SAS golden files |
| Heal iterations needed without the pitfall library | Not measured yet | Waiting for SAS golden files |
| Unit tests written and passed | Not measured yet | Not measured yet |
| Records compared | Not measured yet | Not measured yet |
| Largest PD difference | Not measured yet | Not measured yet |
| Decision match rate | Not measured yet | Not measured yet |
| Wall clock time of a full `/redevelop` run | Not measured yet | Not measured yet |

The measurements need a live LLM run (`LLM_API_KEY` and `LLM_MODEL` in the root `.env`).

## How to measure

Start the service from `redev_engine/` with `uvicorn app.main:app --port 8001`, then for each model:

1. With the pitfall library: clear the cache (`rm -f redev_engine/llm_cache/*.json`), then call `POST /redevelop` with `"use_pitfall_library": true`. Save the response.
2. Without the pitfall library: clear the cache again, then call with `"use_pitfall_library": false`. Save the response.
3. From each response, read:
   * first pass parity: `iterations[0].parity_passed`
   * heal iterations needed: `len(iterations) - 1` when the final status is `PARITY_PASSED`
   * unit tests: `unit_tests`
   * records compared: `parity.records_compared`
   * largest PD difference: `max_abs_diff` of level `L2_record_scores`
   * decision match rate: `match_rate` of level `L3_decisions`
   * wall clock time: `duration_seconds`
4. Run the final configuration once more in live mode so that its replies are in `llm_cache/`. Then check that `LLM_MODE=replay` gives the same result with no key.

LLM replies vary between runs, so report the numbers of the recorded run and do not average them with other runs.
