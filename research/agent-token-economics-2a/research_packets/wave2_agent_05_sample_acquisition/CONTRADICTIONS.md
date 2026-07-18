# Contradictions and interpretation hazards

## Non-empty trajectories versus zero usage

Eighteen files contain non-empty histories and trajectories while reporting zero sent tokens, zero received tokens, and zero instance cost. The numeric fields exist, but their values are placeholders or replay artifacts rather than credible observed inference. Field availability must not be confused with measurement availability.

## Positive API-call counts versus zero tokens

Three function-calling/replay fixtures report 11, 11, and 13 API calls while reporting zero tokens and zero instance cost. This is incompatible with treating `api_calls` as a count of fresh, billable provider requests. Preserve it only as a source field unless replay semantics are independently resolved.

## `submitted` versus verifier success

Eighteen files report `exit_status = submitted`, but none exposes a verifier result. Submission is a termination event, not evidence that the answer or patch passed.

## Configured model versus executed model

Four replay configurations name `gpt-4o`; another names `replay`. These labels identify configuration or adapter behavior and do not establish the exact provider snapshot, inference timestamp, or that a new inference occurred during replay.

## Multiple representations versus additive counts

Every legacy/replay file has both `trajectory` and `history`, and one file additionally embeds `trajectory[].messages`. Tool-call/message counts across these representations overlap. Adding them would double-count or worse.

## MIT license versus public-safety decision

The repository license is permissive, yet raw trajectories contain explicit thought text, prompts, observations, tool arguments, and task content. Legal permission and prudent public-data minimization are different gates. The recommended artifact is derived metadata only.
