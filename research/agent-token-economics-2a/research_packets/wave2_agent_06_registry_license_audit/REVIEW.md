# Registry and License Audit

Evidence cutoff: 2026-07-18. Audit agent: `wave2_agent_06_registry_license_audit`.

## Scope and method

This read-only review examined all three Wave 1 source packets and the generated-registry implementation in `analysis/build_registries.py`. It compared the raw packet records with the generated source and dataset registries. No final registry, schema, runtime file, handbook, or Git history was changed.

The inspected corpus contains:

- 75 raw source records and 75 generated source records;
- 41 raw dataset/telemetry-surface records and 41 generated dataset records;
- no duplicate groups under the builder's current exact `(canonical URL, name)` key;
- no dataset currently accepted as a numerical routing prior;
- 31 generated `accepted_qualitative`, 4 `blocked_pending_review`, and 6 `rejected` decisions.

## Verdict

**PASS FOR DISCOVERY ONLY; HIGH-SEVERITY CORRECTIONS REQUIRED BEFORE THE GENERATED REGISTRIES ARE PUBLICATION-CANONICAL.**

The conservative numerical gate is currently closed, so the defects below have not admitted a numerical prior. They can still break provenance, misstate field availability, and make a discovery-only record appear cleared for qualitative use. No raw third-party trajectory should be acquired or published on the basis of the current generated decision alone.

## High findings

### HIGH-01 — Official OpenAI source IDs are discarded

Wave 1 Agent 01 uses `id`, while the builder reads only `source_id`. All 15 official source records therefore have an `original_refs` value ending in `:None`. The generated IDs affected at inspection are `SRC-2A-003` through `SRC-2A-005`, `SRC-2A-019` through `SRC-2A-026`, `SRC-2A-053` through `SRC-2A-055`, and `SRC-2A-072`.

Correction: resolve the raw identifier with `first(row, "source_id", "id")`; reject duplicate scoped identifiers; add a referential-integrity test.

### HIGH-02 — Seven official telemetry records have no source provenance

Every `OA-TELEM-*` dataset omits `source_ids`, and the builder does not infer a source from its canonical URL. Generated datasets `DS-2A-003`, `004`, `005`, `006`, `012`, `039`, and `040` therefore have empty `source_ids`.

Correction: add the explicit mappings in `DATASET_CORRECTIONS.jsonl`; fail generation when a dataset has no resolvable source.

### HIGH-03 — Boolean availability values become fictitious field names

`as_list(False)` becomes `[false]` and `as_list(True)` becomes `[true]`. The generated registry currently contains 21 invalid availability-list instances across 11 datasets. A boolean says only whether an uninspected field category may exist; it is not a field name.

Correction: for `false`, emit an empty field list. For `true`, emit `null` plus a separate status such as `present_untyped`. Do not invent field names.

### HIGH-04 — Decision resolution is lexical and misses packet semantics

The builder ignores `accepted_for_discovery_registry` and `accepted_for_quantitative_priors`. It guesses `blocked_pending_review` by searching a rejection-reason string for a short word list. This leaves `ds_swebench_experiments` and `ds_nebius_sweagent_trajectories` as `accepted_qualitative` despite explicit license/provenance gates in their packets. The decision vocabulary also conflates registry inclusion with permission to use data.

Correction: use independent typed booleans/enums for discovery inclusion, raw acquisition, raw redistribution, derived-statistics use, qualitative use, and numerical-prior use. Never infer a rights decision from prose.

### HIGH-05 — Duplicate conflict resolution is permissive

For a future duplicate, the builder chooses the longest serialized record for scalar fields, uses `any()` for acceptance and numerical eligibility, and merges lists without source-specific authority. One permissive packet could override a license block from another packet.

Correction: conflicts in license, redistribution, privacy, or numerical eligibility must resolve to the most restrictive value or stop for human review. Scalar conflicts require an explicit source-authority rule and a contradiction record. Although no duplicate group exists today, this is a publication-safety defect in the required continual-ingestion path.

### HIGH-06 — Generated identifiers are not stable

`SRC-2A-NNN` and `DS-2A-NNN` are sequence numbers assigned after URL sorting. Adding a lexically earlier source or dataset renumbers later records, breaking citations, manifests, and machine-readable evidence links.

Correction: derive stable IDs from the original publisher ID or a canonical identity hash. Store aliases separately. Never use order-dependent identifiers as durable evidence keys.

### HIGH-07 — Count and availability fields are not type-stable

`number_of_tasks` is an integer or `null` for most records but a narrative string for six generated datasets. `success_labels_available`, `verifiers_available`, and `raw_trajectory_availability` also mix booleans, strings, and nulls. This prevents strict schema validation and encourages accidental coercion.

Correction: keep counts numeric or null and move scope/variant explanations into separate fields. Use typed status enums plus optional field-name arrays.

### HIGH-08 — License of code/schema is conflated with rights in telemetry

Several OpenAI records combine an MIT/Apache implementation or schema license with customer/operator telemetry. Similar conflation appears wherever a benchmark repository license is used alongside separately hosted trajectories. A code license does not license prompts, responses, traces, private organization usage, model output, or third-party captured pages.

Correction: separate `software_or_schema_license`, `dataset_or_telemetry_rights`, `raw_redistribution_status`, and `allowed_derived_statistics_status`.

### HIGH-09 — Size metadata is not normalized by size kind

GitHub `diskUsage`, Hugging Face display size, Git blob bytes, compressed archive bytes, extracted bytes, container layers, and unbounded S3 payloads are mixed in one free-text `estimated_download_size` field. In particular, GitHub repository `diskUsage` is not a clone/archive download estimate.

Correction: store numeric bytes when known, size kind, source, inspected revision/date, and separate compressed/extracted/container/external-payload values. Preserve unknown as null.

### HIGH-10 — First-release dates sometimes identify a paper or parent project, not the dataset

Examples include ReAct artifacts using the paper date and OpenHands benchmark run outputs using the core-project lineage date. The current field does not record date type or precision.

Correction: use `first_public_evidence_date`, `dataset_first_release_date`, `repository_created_date`, and `date_precision` separately. Leave dataset release null when it was not established.

## Medium findings

- The canonical URLs for the three OpenAPI-derived sources point to live API endpoints rather than the inspected OpenAPI document. Preserve the endpoint as `api_endpoint`, but cite an immutable `openai/openai-openapi` revision or an official API-reference page as the source.
- Several GitHub documentation/source URLs use `blob/main` or `blob/master` even though an inspected commit is recorded. Pin those URLs to the inspected revision.
- The generated Markdown registry omits license, redistribution, privacy, and rejection details. It is therefore not sufficient as the sole human review surface.
- Generic string defaults such as `"unknown"` are mixed with null. For unavailable measurements, prefer null plus a structured missingness reason.
- The registry lacks a `record_type` distinction between reusable public datasets, private operator telemetry surfaces, benchmark task collections, aggregate paper tables, and framework schemas.
- The generated dataset record lacks an explicit `rejected` boolean even though the mission lists “accepted or rejected” as required fields. A typed decision enum can replace both only if documented and schema-validated.

## Publication gate

Before treating the generated registries as canonical:

1. repair official source IDs and dataset-to-source links;
2. normalize all availability fields and counts to stable types;
3. split discovery inclusion from raw/derived/numerical permissions;
4. apply the restrictive conflict rule;
5. introduce stable IDs and immutable source URLs;
6. keep every currently blocked or rejected raw trajectory blocked;
7. retain zero accepted numerical priors unless a separately licensed, field-audited, outcome-linked sample passes the quality gate.
