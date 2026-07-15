# Model calibration evaluation

Phase 5.3 uses a curated deterministic evaluation rather than exact-string
production rules. The cases live in `rules/model_selection_eval_001.jsonl` and
are validated through the real Router Core, live-registry fixture, model policy,
effort policy, and `turn/start` rewriter.

## Dataset composition

| Group | Cases |
|---|---:|
| Trivial writing and transformations | 30 |
| Luna-level simple tasks | 25 |
| Spark-targeted code edits | 25 |
| Terra professional coding | 35 |
| Terra research and tool workflows | 20 |
| Sol architecture/debugging/analysis | 25 |
| Max/Ultra delegation | 10 |
| Availability/fallback/migration | 10 |
| **Total** | **180** |

The dataset includes paired controls and negative controls for harmless uses of
words such as `security`, simple external actions, short grant questions, and
one-line code explanations. Acceptable model sets are used where more than one
route is defensible.

## Phase 5.3 deterministic result

Run:

```bash
./.venv/bin/pytest -q tests/test_model_selection_calibration_eval.py
```

Calibrated result on Codex CLI `0.144.4`:

| Metric | Result | Target |
|---|---:|---:|
| Overall acceptable-route accuracy | 99.44% (179/180) | >=95% |
| Trivial-task de-escalation | 100% | >=95% |
| Eligible targeted edits routed to Spark | 96% | >=85% |
| Terra professional work | 100% | >=90% |
| Sol architecture/frontier work | 100% | >=95% |
| Critical under-routing | 0 | 0 |
| Unsupported effort selections | 0 | 0 |
| Unavailable model selections | 0 | 0 |
| Ultra without delegation reason | 0 | 0 |

The one non-exact case contains a harmless CSS design-token phrase. Router Core
conservatively labels the word `token` as high risk, so the Spark risk filter
rejects it and Terra handles the task. Phase 5.3 does not override or duplicate
Router Core safety classification merely to improve a model-routing score.

## Additional deterministic coverage

`tests/test_dynamic_model_policy_calibration.py` covers:

- Spark present, absent, hidden, temporarily unavailable, text-only/image,
  context under/over capacity, explicit test, implicit test, and prototype paths;
- Sol/Terra/Luna/Spark fallback behavior;
- live effort and modality drift;
- unknown models and conservatively recognized future family models;
- live upgrade targets and explicit legacy compatibility requests;
- workspace model restrictions and fail-closed empty candidate sets;
- explainable score components and fallback metadata;
- model hysteresis, immediate escalation, and material de-escalation;
- Ultra justification and the Luna Ultra prohibition;
- independence between model strength and sandbox/approval authority.

Existing App Server tests continue to cover protocol transparency, exact request
IDs, notification order, backend errors, approval request/response round trips,
active-model events, privacy-safe logs, localhost binding, and launcher safety.

## Original-TUI 12-turn soak

On 2026-07-15, the original Codex TUI was started through
`./scripts/start-routed-codex`. The session was explicitly set to Sol / `max`
before the first turn. The sanitized proxy log contained 12 `forwarded` route
events, 12 matching backend `accepted` events, and an App Server
`active_settings` event for every turn. Forwarded and active model/effort
matched in all 12 turns.

| # | Task class | Forwarded and active setting | Result |
|---:|---|---|---|
| 1 | grammar correction | Luna / low | completed |
| 2 | short summary | Luna / low | completed |
| 3 | simple function explanation | Luna / medium | completed |
| 4 | one-field JSON UI edit | Terra / medium | edit completed; over-routed before camelCase calibration |
| 5 | isolated bug plus one test | Spark / medium | edit completed; focused test passed |
| 6 | several synthetic failures | Terra / medium | diagnosis completed |
| 7 | medium synthetic patch review | Sol / high | review completed; conservative over-route |
| 8 | bounded sourced technical research | Terra / high | completed with official sources |
| 9 | multi-module refactor plan | Sol / xhigh | completed |
| 10 | complex authentication audit | Sol / xhigh | active route proven; protective skill stopped after advisory decision |
| 11 | final project-wide review | Sol / max | active route proven; protective skill stopped after advisory decision |
| 12 | four independent parallel workstreams | Terra / high | active route proven; pre-calibration delegation inflection miss |

Turn 4 exposed loss of the word boundary in a camelCase identifier. The feature
extractor now inserts identifier word boundaries before case-folding, and a
regression requires the same class of small JSON UI edit to select Spark / low.
Turn 12 exposed an English-inflection gap (`delegate` versus `delegated`). The
general delegation feature now recognizes inflected forms, and a regression
requires Terra or Sol / `ultra` with the bounded
`parallel_independent_workstreams` reason. No thirteenth paid turn was started;
the requested 12-turn ceiling was preserved.

The two protective-skill stops did not alter, reject, or obscure the App Server
route evidence; they are a retained defense-in-depth behavior of the advisory
skill rather than a proxy transparency failure. The temporary fixture was
removed after the run. The log contained bounded hashes and routing metadata,
not raw prompt text.

## Recalibration rules

Do not weaken hard capability or safety filters to raise accuracy. A policy
change is acceptable only when it:

1. improves a general semantic boundary rather than matching a single string;
2. preserves zero unsupported/unavailable selections and zero critical
   under-routing;
3. keeps risk/authority separate from model strength;
4. passes all prior Router Core, hooks, proxy, privacy, and launcher tests;
5. records any deliberate ambiguity or conservative exception here.

The full validation command remains:

```bash
./.venv/bin/pytest
git diff --check
```
