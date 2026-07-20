# Classifier Semantic Repair 1A/1B

> Historical milestone note: this document records the classifier repair under
> policy `model-policy-calibration-v0.2`. The RC2 Ultra-admission candidate uses
> explicit `v0.3` provenance; v0.2 remains accepted as historical provenance
> and is not promoted or rewritten.

This milestone repairs deterministic classifier semantics without changing
routing authority, telemetry storage, or the telemetry schema. Historical
records are append-only and are not reclassified.

## Classification flow

The router normalizes a prompt for classification, extracts bounded semantic
facts, scores the controlled category and safety dimensions, selects a routing
profile, and passes categorical metadata to the telemetry bridge. The original
prompt remains unchanged for normal forwarding and the existing
privacy-preserving signature path; semantic analysis does not persist prompt
fragments or file names.

Task subdomain is now independent from action danger. Supported subdomains are
`document_comparison`, `read_only_analysis`, `test_execution`,
`code_generation`, `code_modification`, `security_audit`,
`architecture_design`, and `general_research`. When the classifier lacks
enough evidence, it records no subdomain instead of copying a safety label.

English and Polish test actions use one bounded internal clause-state model.
It distinguishes an executable request, an execution prohibition,
description, explanation, review/decision language, questions, quoted
mentions, and test-file modification. Coordination stays within its clause;
explicit transitions such as `then`, `after that`, `but`, `instead`, `potem`,
`następnie`, `ale`, and `lecz` begin an independent clause. Thus a question or
quoted mention is non-executing, while a later imperative remains executable.
A quoted target in an imperative such as `Run "pytest"` remains executable.
Controlled reason codes may be used internally, but neither prompt fragments
nor free-text explanations are added to telemetry.

`explicit_test_requirement` means that the user actually requested test
execution. Editing a test file does not set it. `correctness_depends_on_tests`
is separate: a code or test modification can still require test evidence even
when execution was omitted or explicitly prohibited. A prohibition can never
coexist with a positive explicit-test requirement unless another independent
clause contains a genuine positive execution request.

Scope is based on the number of distinct normalized explicit file references.
One reference may be `single_file`; two or more become `module`; explicit
repository-wide wording becomes `repo`. Paths are counted in memory and are
not included in telemetry.

A narrow low-difficulty rule applies only when one or two lexical local
documents, a known read-only document domain, and an explicitly bounded output
are all proven. It fails closed for unknown categories, web/API work,
security, privacy, compliance, incident, credential, authentication,
authorization, secret-handling, or threat analysis, architecture synthesis,
exhaustive or large-corpus work, multi-tool workflows, code changes, and
positive test execution. Sensitive filenames are internal evidence for this
gate and are never exported. Sensitive read-only analysis is at least medium
difficulty and retains a read-only sandbox; explicit medium/high complexity
signals cannot be overwritten. Risk, action danger, sandbox, and approval
policy remain independently computed.

## Counter semantics

`request_count` keeps distinct completed provider/model request identifiers and
explicit cumulative provider snapshots as independent evidence. Agreeing
sources are retained; disagreement, regressing snapshots, or contradictory
usage for one request ID fail closed to null. A visible user turn, request
start, or cumulative token update is not completion evidence.

Only the established cumulative `retry.count` event can quantify retries.
Consistent positive snapshots remain positive without requiring successful
completion. A trusted zero additionally requires an explicit valid zero, a
normally completed lifecycle, no positive snapshot, and no malformed,
unsupported, regressing, or contradictory retry-like evidence. Event names
such as `retry.started` are not part of the installed authoritative counting
contract: they do not manufacture a number, but they make zero unresolved.
Aborted or incomplete lifecycles cannot manufacture zero. Duplicate snapshots
do not inflate counts, and regressing or contradictory snapshots fail closed
to null.

## Version boundaries

- Router implementation version remains `0.1.0`; it identifies the software.
- New routing decisions use policy version `model-policy-calibration-v0.2`; it
  identifies the deterministic decision behavior.
- Telemetry schema version remains `2.0.0`; no stored-field contract changed.

Records produced under policy `model-policy-calibration-v0.1` remain readable,
valid, and unchanged. The local dashboard keeps classifier-sensitive labels
quarantined for both old and new policy records. A newer policy version is not
automatically trusted training evidence. Canonical current routers explicitly
attach v0.2. Compatibility-facing `RoutingDecision` and `RoutedTurn`
constructors default to no provenance, not the current policy. Decision-like
objects without a supported explicit v0.1 or v0.2 identity are recorded as
`unknown`; missing or malformed provenance is never promoted merely because
the current software contains the v0.2 constant.

## Authority and privacy

Classification and routing remain advisory. Telemetry and automated
verification do not authorize effects; explicit human approval remains the
authority for protected actions. The repair does not change prompt hashing,
record hashing, external storage, outcome linkage, sandbox behavior, or model
launch permissions.
