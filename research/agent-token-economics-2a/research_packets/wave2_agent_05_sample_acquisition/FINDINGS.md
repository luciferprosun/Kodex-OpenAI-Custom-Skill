# Wave 2 / Agent 05 — bounded SWE-agent demonstration inspection

Evidence cutoff: 2026-07-18 (Europe/Berlin)
Agent ID: `wave2_agent_05_sample_acquisition`
Immutable source revision: `3ea751c087f32b16e039a2233dd6eefecef325d5`

## Decision

The 19 SWE-agent demonstration trajectories are suitable as a small parser-compatibility fixture, but they are **not a valid numerical token-telemetry sample**.

- All 19 `.traj` blobs parsed as JSON.
- Their exact aggregate size is 1,503,861 bytes.
- All 19 raw SHA-256 values and Git blob identifiers are recorded in `FIELD_INVENTORY.jsonl`.
- Eighteen files expose `info.model_stats`.
- In all 18, `tokens_sent`, `tokens_received`, and `instance_cost` are present but equal to zero.
- Fifteen expose `total_cost`, also always zero.
- Fifteen expose `api_calls = 0`; three replay/function-calling fixtures expose `api_calls` values of 11, 11, and 13 while their token and cost values remain zero.
- One history-only fixture has no `info` or `model_stats` object.

The zero values must not be interpreted as measured zero-token inference. They describe demonstrations or replays and are internally incompatible with the non-empty conversations. For canonical normalization, token and cost metrics should therefore be `null` with an explicit missingness reason such as `placeholder_zero_in_demonstration`.

## Bounded acquisition method

The Git tree was enumerated at the immutable commit, then each of the 19 `.traj` blobs was read once into memory. No repository clone, paid inference, multi-gigabyte asset, or raw trajectory was retained. The inspection emitted only:

- path, byte size, Git blob SHA-1, and raw SHA-256;
- JSON field names and value types;
- array/object counts;
- numeric telemetry values;
- safe model-configuration identifiers;
- termination status;
- content-risk indicators without raw text.

No prompt, observation, action argument, response, thought, patch, task statement, or conversation text was copied into this packet.

## Exact structural inventory

### Common legacy/replay shape

Eighteen files have these top-level fields:

- `environment` (string);
- `trajectory` (array);
- `history` (array);
- `info` (object).

Five of those also have `replay_config` (object). The 18 `trajectory` arrays contain 205 entries in total. Their common fields are `action`, `observation`, `response`, `state`, and `thought`; some also expose `execution_time` or nested `messages`.

### History-only shape

`function_calling_simple.traj` contains only `history`. Its 12 messages use fields including `role`, `content`, `agent`, `message_type`, `thought`, `action`, `tool_calls`, and `tool_call_ids`. It has no run-level usage, task, outcome, or model-statistics object.

### History and tool structures

Across all files there are 441 `history` messages. Forty structured tool-call objects occur in the top-level histories. One replay file additionally embeds 91 tool-call objects inside `trajectory[].messages`; those nested messages overlap with another representation of the trajectory and must not be added mechanically to the top-level history count.

All 19 files contain explicit `thought` fields. This makes raw publication unnecessary and inappropriate for the SmartRouter public research pack even though repository licensing is permissive.

## Telemetry-field assessment

| Metric | Field coverage | Observed values | Usable as a routing prior? |
|---|---:|---|---|
| input-like tokens | `tokens_sent` in 18/19 | always 0 | No |
| output-like tokens | `tokens_received` in 18/19 | always 0 | No |
| per-instance cost | `instance_cost` in 18/19 | always 0 | No |
| total/process cost | `total_cost` in 15/19 | always 0 | No |
| API calls | `api_calls` in 18/19 | fifteen 0; three 11/11/13 | No; replay semantics are not verified provider requests |
| cached input | absent | unknown | No |
| reasoning tokens | absent | unknown | No |
| request ledger | absent | unknown | No |
| context occupancy/compactions | absent | unknown | No |
| retries/escalations | configuration limits exist in five files, but observed counts do not | unknown | No |
| wall time | per-step `execution_time` occurs in three files, not a complete run clock | incomplete | No |
| verifier result | absent | unknown | No |
| termination | `exit_status = submitted` in 18/19 | submitted | Not equivalent to success |

The existence of a field does not establish valid measurement. These records should receive token-economics quality class **E** and be excluded from all numerical priors. The corpus can still test parsing, missingness preservation, version handling, and duplicate-representation safeguards.

## Model and task identity coverage

- Four replay configurations name `gpt-4o`.
- One replay configuration names `replay`, which is an adapter/configuration identity rather than a verified provider model.
- Fourteen files do not embed a model identifier in a safe structured configuration field.
- The corpus contains nine CTF files, one HumanEvalFix file, one synthetic function-calling file, and eight variants of the same Marshmallow issue.

This is highly duplicated and domain-skewed. A configured model name in a replay does not prove that the demonstration itself incurred a fresh model request.

## Outcome limitations

Eighteen files say `submitted`; the remaining fixture has no exit status. `submitted` only indicates an agent termination path. There is no objective verifier result, task-success Boolean, partial score, or evaluation report in these files. No accepted-task cost can be computed.

## License and publication safety

The inspected repository identifies its license as MIT at the pinned revision. That is a favorable code and redistribution signal, subject to retaining the license notice. It does not require SmartRouter to republish raw trajectories.

The raw files contain full prompts/observations, action arguments, task material, responses, and explicit thought text. Structured replay configuration also includes an `api_key` field in five files, but its value is `null` in every inspected case. A conservative lexical scan found security-related terms and path/email-shaped strings in some raw text; this may be task content rather than real private data, but it reinforces the derived-only publication decision.

Recommended publication boundary:

- publish this metadata/checksum inventory and aggregate field coverage;
- retain source URLs and immutable revision;
- do not publish raw messages, thoughts, observations, patches, or tool arguments;
- do not publish numerical token priors from placeholder zeros;
- preserve the upstream MIT attribution when derived fixtures are distributed.

## Adapter recommendation

Implement a bounded, opt-in parser adapter with these rules:

1. Require a pinned commit and a predeclared byte ceiling (2 MiB covers this inspected revision).
2. Enumerate `.traj` blobs through the Git tree API before downloading payloads.
3. Verify expected blob count, size, Git blob ID, and SHA-256.
4. Parse JSON without persisting raw content.
5. Emit only structural counts, safe identifiers, checksums, and missingness reasons.
6. Treat `tokens_sent = tokens_received = instance_cost = 0` in non-empty demonstration/replay trajectories as placeholders, not measured zero usage.
7. Never map `submitted` to `task_success = true`.
8. Never add counts from `history` and nested `trajectory[].messages` without deduplicating representations.
9. Keep `api_calls` only as a source field unless provider-request semantics are proven.
10. Assign quality class E and `included_in_numerical_priors = false` for this revision.

## Final recommendation

**Accept for schema/parser testing and coverage reporting. Reject for empirical token, cost, success, latency, or escalation priors. Publish derived metadata only.**
