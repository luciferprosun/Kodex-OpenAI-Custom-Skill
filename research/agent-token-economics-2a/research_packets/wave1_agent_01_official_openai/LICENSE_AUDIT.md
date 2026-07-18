# License and Publication Audit

## Decision summary

| Material | Repository/document license | Public corpus decision |
|---|---|---|
| OpenAI OpenAPI specifications | OpenAPI metadata declares MIT | Record schema-derived field names and source links. Do not publish organization or customer response data. |
| `openai/codex` source | Apache-2.0 repository license | Short field mappings and derived schema facts are safe with attribution. Event payloads produced by user runs remain content-sensitive. |
| `openai/openai-agents-python` source | MIT repository license | Short field mappings and derived schema facts are safe with attribution. Run results and traces require separate content review. |
| OpenAI documentation pages | No reusable documentation license verified in this packet | Link and paraphrase. Do not mirror full pages. |
| Responses/Usage/Costs API records | Customer or organization operational data | Private by default. Publish only consented, sanitized, aggregate derived statistics. |
| Agents SDK traces | Operator application data that can embed prompts, outputs, tools, and identifiers | Do not publish raw traces. Allowlist metrics, replace identifiers, and redact content before release. |
| Codex `exec --json` | Implementation is Apache-2.0; emitted content belongs to the run context | Keep structured token/tool metadata. Remove prompts, assistant text, command output, tool results, paths, and identifiers unless explicitly public-safe. |
| Codex rollout/session JSONL | No independent corpus redistribution authorization; may contain highly sensitive transcript data | Reject raw publication and raw repository commit. Local extraction only, with a strict allowlist and deletion/retention policy. |

## Privacy and hidden-reasoning rules

- A `reasoning_tokens` or `reasoning_output_tokens` count is publishable telemetry; hidden reasoning text is not required and must not be sought or republished.
- A trace or rollout label such as `reasoning` does not create publication rights and does not prove the text is hidden model chain-of-thought.
- Never publish authentication headers, API keys, ChatGPT tokens, cookies, private repository contents, absolute personal paths, raw prompts, private chat text, tool output, or third-party personal data.
- Hashing a stable task/run identifier is not sufficient when the surrounding trajectory can re-identify a person or private repository.
- For public data, prefer aggregates, distributional summaries, task metadata, token counts, tool categories, latency, verifier outcomes, and model/version fields.

## Price and quota publication rules

- A pricing page is a current snapshot, not an immutable historical ledger. Every reconstructed cost must carry `price_table_date`, model, service tier, region/context-price condition, and a `reconstructed` label.
- Organization Costs API values are realized monetary records but are aggregated. Do not attribute them to a run without a defensible join key.
- ChatGPT/Codex subscription credits and rate-limit windows must not be converted to API dollars. No official conversion was established.
- Cache reads, cache writes, uncached input, output, and tool charges must remain separate components.

## Attribution minimum

Derived public artifacts should name OpenAI as the source publisher, include the canonical URL and inspected commit/version, preserve the applicable repository license notice for copied code, and state that telemetry values came from operator-controlled runs rather than from OpenAI's documentation examples.
