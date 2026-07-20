# SmartRouter Local Telemetry Demo View 1A

The Demo View is a dependency-free terminal dashboard over the existing local
telemetry JSONL. It opens configured run and outcome files read-only, validates
each record and outcome link, builds an allowlisted metadata projection in
memory, prints it, and exits. It does not start a server or write a report.

## Launch

From the repository root:

```bash
./scripts/smart-codex telemetry dashboard
```

The default view shows the latest validated, non-synthetic run plus the latest
human-labeled run when one is available; otherwise it shows the two latest
runs. A bounded limit and a machine-readable form are available:

```bash
./scripts/smart-codex telemetry dashboard --limit 1
./scripts/smart-codex telemetry dashboard --limit 2 --json
```

`--json` contains the same privacy-allowlisted projection as the terminal
view. It is not a raw-record endpoint.

## Panels

- Route identity keeps requested, recommended, launched, and backend model
  identities separate.
- Usage shows input, non-cached input, cached input, reasoning output, visible
  output, and reported total with measurement provenance. The exclusive bucket
  check never adds cached input to an already inclusive input total.
- Performance shows wall time and explicitly marks time to first token as
  unavailable because the current schema does not collect it.
- Operations shows request, retry, tool, and escalation counts. A null value is
  rendered as `Unavailable (not zero)`.
- Quality keeps runtime verification, operator-recorded verification, and the
  explicit human outcome separate.
- Integrity shows that schema, hash, privacy, and outcome-link checks passed
  before inclusion.

## Safety and label quality

The dashboard never renders stable run/session/decision IDs, record or linkage
hashes, task/workspace signatures, paths, task content, exact tool types,
prompts, responses, source, diffs, tool payloads, raw errors, or secrets.
Malformed, schema-invalid, hash-invalid, privacy-invalid, duplicate-identity,
and incorrectly linked records are excluded without echoing rejected content.

Known semantic classifier defects are quarantined. `task_subdomain`,
`task_scope`, `task_risk`, and negation-sensitive test intent are not displayed
as evidence and are excluded from ranking, evaluation, learning, and export.
This milestone does not repair or rewrite those labels.

The read path verifies the configured external filesystem identity while not
requiring write access or free capacity. Existing telemetry collection retains
its stricter writable-mount preflight. The dashboard never enables collection,
changes routing, records outcomes, exports data, or changes effect permissions.

Routing, telemetry, and verification remain advisory. Only the existing
explicit human approval path can authorize protected effects, and human
outcomes remain separately authored events.

## Demo sequence

1. Run the dashboard command.
2. Point out the requested-to-executed model path.
3. Show exclusive usage buckets, provenance, and wall time.
4. Show that missing request/retry counts say `Unavailable (not zero)`.
5. Contrast advisory verification with the separate explicit human outcome.
6. End on the local-only, metadata-only, label-quarantine, and authority
   boundary notices.

No real telemetry fixture is checked into the repository. The command uses
only the operator's already configured local storage.
