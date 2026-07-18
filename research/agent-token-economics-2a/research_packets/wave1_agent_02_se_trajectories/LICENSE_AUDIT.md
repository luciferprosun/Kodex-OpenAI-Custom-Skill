# License and publication audit

Evidence cutoff: 2026-07-18. This is an engineering publication-safety assessment, not legal advice.

## Decision table

| Source/assets | License signal | Commercial/derived-statistics posture | Raw trajectory posture | Decision |
|---|---|---|---|---|
| SWE-bench Experiments repository and S3 submission artifacts | No license declared at inspected revision | Locally computed facts/aggregates may be defensible, but provenance and source links are required; seek human/legal confirmation | Do not redistribute | Registry and metadata only; conditional local statistics |
| SWE-agent code and committed demonstrations | MIT | Commercial use and derived statistics permitted with notice | Legally lower risk, but public thought/reasoning text is unnecessary and formats are heterogeneous | Parser fixtures/derived fields only |
| SWE-smith repository | MIT | Code-derived methods acceptable | Confirm that the HF dataset/trajectory assets carry the same license and that underlying repository content is covered | Defer payload |
| OpenHands core | MIT except separately licensed `enterprise/` | Core-derived schemas/statistics acceptable | Exclude `enterprise/`; separately audit any generated trajectory release | Harness accepted, no bulk monorepo copy |
| OpenHands/benchmarks | MIT | Harness schemas and derived statistics acceptable | Generated trajectories inherit additional model/task/source concerns | Harness accepted; run assets case-by-case |
| Harbor framework | Apache-2.0 | Commercial use/derivatives permitted with attribution and notices | Result and trajectory rows may have their own publishers/licenses | Framework schema accepted; rows case-by-case |
| Terminal-Bench 2 tasks | Apache-2.0 | Task metadata and derived verifier statistics acceptable with attribution | Generated trajectories are separate works; environment assets may carry other licenses | Task metadata accepted |
| STATE-Bench | MIT | Code/task-derived statistics acceptable | Generated conversations may contain model output and user-simulator text; publish aggregates, not raw | Task/verifier accepted |
| AgentRE-Bench public release | MIT | Public task/verifier-derived statistics acceptable | Exclude private eval tasks/ground truths and avoid raw reasoning | Public task metadata accepted |
| Multi-SWE-bench repository | Apache-2.0 | Harness/task metadata acceptable with attribution | HF assets and source-repository excerpts need separate audit | Metadata accepted; payload deferred |
| Nebius trajectory releases | Dataset-card license not verified in this pass | No quantitative use until card and provenance audit | Do not redistribute | Discovery registry only |

## Key legal and privacy distinctions

### Public is not licensed

GitHub visibility and public S3 access do not grant redistribution rights. `SWE-bench/experiments` has no declared repository license in the inspected GitHub metadata. Submission authors may also retain rights in prompts, reports, and trajectories. SmartRouter should publish source references, immutable identifiers, field-coverage summaries, and derived aggregate statistics only after a human license decision.

### Code license is not automatically the dataset license

The MIT license in a harness repository may cover code but not necessarily:

- Hugging Face/Xet data assets;
- generated model outputs;
- copied source-repository text;
- Docker/container layers;
- third-party issue text and patches;
- leaderboard submissions authored by outside teams.

Each asset needs an explicit card or manifest license.

### Underlying repositories retain their terms

SWE-bench-style tasks reference real repositories and may include issue text, code patches, tests, and terminal observations. A benchmark's Apache or MIT license cannot erase the original project's copyright and license. Publish task IDs, hashes, derived sizes, and counts rather than copied code unless the original license and attribution are retained.

### Hidden reasoning and chain-of-thought

Some trajectory formats contain fields named `thought`, `reasoning`, or raw assistant messages. Those fields must not be assumed safe or necessary to publish. For token economics, retain only:

- token counts and their measurement provenance;
- message-role and byte/token-length summaries;
- tool name/category and timestamps;
- verifier/outcome metadata;
- short error categories;
- cryptographic source identifiers.

Do not republish hidden reasoning or provider-private traces even when a surrounding dataset appears permissively licensed.

### Secrets and personal data

Trajectory files can contain:

- API keys or authorization headers leaked in logs;
- private repository URLs;
- local usernames and absolute paths;
- emails from Git metadata;
- issue author names;
- tool output containing credentials or environment variables.

A license does not resolve privacy or secret risk. Any future adapter must scan before persistence and must default to excluding raw prompts/tool outputs.

## Safe bounded sample decision

No candidate with **verified actual run-level token telemetry** is approved for public raw sampling in this pass.

The closest legally safe small asset is the MIT-licensed SWE-agent demonstration folder:

- immutable revision: `3ea751c087f32b16e039a2233dd6eefecef325d5`;
- 19 `.traj` blobs;
- total blob bytes: 1,503,861;
- retrieval: individual GitHub blobs/contents API;
- acceptable use: parser fixtures and derived schema-coverage tests;
- unacceptable use: numerical token priors, because uniform run-level token telemetry was not verified.

The closest telemetry-rich asset is a bounded submission in `SWE-bench/experiments`, but raw redistribution is rejected because the repository has no declared license. If a human approves local analysis, publish only aggregates and immutable source references.

## Attribution requirements for future samples

For MIT assets, preserve copyright and license notice. For Apache-2.0 assets, preserve the license, attribution, and applicable NOTICE/changes. Always record:

- source URL and immutable revision;
- asset path and checksum;
- dataset/harness version;
- original license URL and retrieval date;
- whether the stored record is raw, sanitized, or derived;
- any source-repository license that applies to embedded code;
- a `raw_redistribution_allowed` decision separate from `derived_statistics_allowed`.
