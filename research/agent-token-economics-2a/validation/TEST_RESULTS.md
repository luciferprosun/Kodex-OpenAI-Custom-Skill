# Test Results

Date: 2026-07-18, Europe/Berlin.

## Focused research tests

Command:

```text
pytest -q tests/test_agent_token_economics_2a.py
```

Result: **20 passed in 4.58 seconds**.

The focused tests cover strict schema references, explicit missingness,
censoring, persisted quality-component recomputation, A-C numerical admission,
dataset-level rights gates, stable registry provenance, blocked raw sources,
placeholder-zero normalization, hidden-reasoning removal, complete accepted-cost
chains, compatible strata, task-cluster success intervals, empty research
priors, runtime disablement, chart metadata, and uncertainty-safe heatmap status.

## Complete repository test suite

Command shape:

```text
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider
```

Result: **337 passed in 50.10 seconds**.

The complete suite was run with permission outside the filesystem/network
sandbox because five existing WebSocket integration tests need to bind an
ephemeral loopback port on `127.0.0.1`. A prior sandboxed diagnostic failed at
the socket bind rather than at an application assertion. The authorized run
passed all 337 tests. No paid inference or external service was invoked.
