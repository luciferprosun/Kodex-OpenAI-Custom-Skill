# License and Publication Review

Evidence cutoff: 2026-07-18, Europe/Berlin.

This is an engineering publication review, not legal advice. It separates the
license of a benchmark or framework repository from the rights in prompts,
trajectories, screenshots, websites, repository snapshots, model outputs, and
other captured run content.

## Registry disposition

The canonical registry contains 41 dataset or telemetry-surface records:

- 17 are metadata-only;
- 10 are blocked pending human rights or content review;
- 8 are accepted for qualitative use only;
- 6 are rejected;
- 0 are admitted to numerical routing priors.

The ten blocked records are:

- `ds_nebius_openhands_swerebench`;
- `ds_nebius_sweagent_trajectories`;
- `ds_swebench_experiments`;
- `hwm_agentbench_public_runs`;
- `hwm_gaia_results_public`;
- `hwm_metagpt_softwaredev_aggregates`;
- `hwm_visualwebarena_agent_trajectories`;
- `hwm_visualwebarena_human_trajectories`;
- `hwm_webarena_execution_traces_v1_v2`;
- `hwm_webarena_human_trajectories`.

No blocked record was downloaded as a corpus or used to fit a numerical prior.

## Bounded SWE-agent fixture inspection

Exactly 19 small files from the SWE-agent demonstration directory were
inspected at repository commit
`3ea751c087f32b16e039a2233dd6eefecef325d5`. Their combined Git-blob content
size was 1,503,861 bytes. Every file contained a thought-like field, so raw
content was discarded. Only allowlisted structure, paths, sizes, checksums,
placeholder usage fields, and derived counts were retained.

The repository code is MIT-licensed, but that fact alone does not make every
captured trajectory safe to republish. The 19 files are therefore class E
parser fixtures, excluded from numerical routing and published only as
privacy-minimized derived metadata. No third-party raw trajectory is committed.

## Publication rules applied

- Raw private Codex sessions, prompts, credentials, cookies, and environment
  data are excluded.
- Hidden reasoning or thought text is never republished.
- Gated or no-reshare datasets remain references only.
- A repository license is not silently extended to embedded third-party data.
- `null` means unknown; missing rights or telemetry are not treated as absent
  risk.
- Derived statistics are published only when the registry records a compatible
  right and the source passes privacy and quality review.
- Source references, schemas, checksums, lawful metadata, and independently
  written summaries are preferred over raw redistribution.

## Remaining human-review boundary

Any future acquisition of a blocked record requires a new review of the exact
version, dataset card or terms, embedded-content provenance, commercial-use
conditions, attribution, personal-data exposure, secrets, hidden reasoning,
and whether derived statistics may be published. A later change in a repository
license does not retroactively resolve captured-content rights.
