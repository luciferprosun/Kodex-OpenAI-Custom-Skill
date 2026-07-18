# SmartRouter model-selection knowledge pack

This directory is a research-backed, machine-readable proposal for selecting
**which model** should handle a task. It does not implement runtime routing and
does not select reasoning effort, speed tier, agent count, sandbox, approvals,
or action authority.

- `model_inventory.json` — dated public/local identity and surface facts.
- `capability_scales.json` — operational SE, MATH, and PHY level definitions.
- `model_capability_matrix.json` — conservative supervised and autonomous trial
  ceilings or protective policy caps with per-domain confidence, basis, and
  evidence references. A null, unassessed domain means **no route**, not zero
  capability.
- `model_selection_rules.json` — deterministic selection and fallback rules.

The pack must be refreshed when live availability, model metadata, benchmark
quality, or local evaluation changes. Runtime `model/list` and workspace policy
remain authoritative for availability.
