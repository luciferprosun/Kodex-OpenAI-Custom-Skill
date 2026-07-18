# Execution Profile

Recorded: 2026-07-18, Europe/Berlin.

## Requested configuration

- Visible mode: **Ultra**
- Lead model policy: strongest verified general model available
- Reasoning policy: maximum
- Topology: one lead plus no more than three read-only research agents at once
- Internet: enabled for primary-source discovery and direct verification

The lead session's typed turn context exposed model identifier
`gpt-5.6-sol`, provider `openai`, and reasoning effort `max` for this mission.
It did not expose an immutable service revision behind that identifier. The
report therefore records the selected identifier and effort exactly, while
leaving the underlying deployment revision **unknown**. No capability claim is
inferred from the visible Ultra label or from a version number.

## Observed environment

- Codex CLI: `0.144.5`
- Python: `3.12.3` through `python3`; no `python` command was available
- Initial free repository filesystem space: approximately 3.2 GiB
- Initial available memory: approximately 1.3 GiB plus swap

The constrained disk ruled out blind cloning of large trajectory corpora.
Discovery, license review, metadata inspection, and one bounded 1.5 MB fixture
sample preceded all normalization.

## Agent waves

The lead retained methodology, normalization, synthesis, artifact generation,
validation, Git, and publication authority. Read-only agents worked in separate
packets across these scopes:

1. official OpenAI telemetry surfaces;
2. software-engineering trajectory sources;
3. historical, web, computer-use, and multi-agent sources;
4. statistical and baseline-design review;
5. bounded sample acquisition;
6. registry and license audit;
7. research-question evidence mapping;
8. final independent adversarial review.

Concurrency never exceeded three child research agents. No child changed
production runtime, Git history, or publication state. No paid API inference
was used.
