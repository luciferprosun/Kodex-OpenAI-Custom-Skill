# SmartRouter Agent Token Economics Research 2A

This directory contains public-source discovery, licensing analysis, normalized
telemetry schemas, bounded samples, robust descriptive statistics, and
research-only prediction baselines for future SmartRouter work.

It does not implement or activate a production routing algorithm. Nothing in
this directory is imported by the SmartRouter runtime.

## Evidence policy

- Unknown measurements remain `null`; they are never coerced to zero.
- Provider-, framework-, reconstructed-, estimated-, and unknown measurements
  remain distinguishable.
- Only quality classes A-C may influence numerical priors.
- Raw trajectories are not republished when licensing, privacy, size, secret,
  or hidden-reasoning status is unclear.
- API prices and subscription quotas are separate concepts.
- Cumulative session usage and current context occupancy are separate metrics.
- Public evidence is not represented as exhaustive historical coverage.

Evidence cutoff: 2026-07-18, Europe/Berlin.

## Main artifacts

- [Handbook](handbook/SMARTROUTER_AGENT_TOKEN_ECONOMICS.md)
- [Print-ready HTML](handbook/SMARTROUTER_AGENT_TOKEN_ECONOMICS.html)
- [PDF](output/pdf/SmartRouter_Agent_Token_Economics_2026.pdf)
- [Dataset registry](sources/DATASET_REGISTRY.md)
- [Source registry](sources/SOURCE_REGISTRY.md)
- [License and publication review](sources/LICENSE_AND_PUBLICATION_REVIEW.md)
- [Execution profile](methods/EXECUTION_PROFILE.md)
- [Repository and resource preflight](PREFLIGHT.md)
- [Canonical schemas](schemas/)
- [Task taxonomy](taxonomy/TOKEN_TASK_TAXONOMY.md)
- [Statistical tables](data/derived/STATISTICAL_TABLES.md)
- [Chart index](charts/CHART_INDEX.md)
- [Machine-readable research pack](knowledge/token-economics/README.md)

The bounded public fixture inspection covers 19 SWE-agent demonstration files
(1,503,861 bytes). It yielded no usable measured-token run: placeholder zeros
were normalized to `null`, all records remain quality class E, and the
numerical-prior gate stays empty. This is a deliberate fair-comparison result,
not a failed attempt to manufacture model priors.

## Reproduction

Run the builders from this directory in the following order:

```text
python3 analysis/build_registries.py
python3 analysis/build_coverage_maps.py
python3 ingestion/normalize_swe_agent_demo_inventory.py
python3 analysis/validate_corpus.py
python3 analysis/compute_statistics.py
python3 analysis/fit_baselines.py
python3 analysis/build_manifests.py
python3 analysis/generate_charts.py
python3 analysis/build_knowledge_pack.py
python3 analysis/build_handbook.py
python3 analysis/record_pdf_visual_review.py --confirm-all-pages-reviewed
python3 analysis/run_publication_validation.py
python3 analysis/build_publication_manifest.py
```

PDF generation is a separate rendering step from the deterministic data build.
The committed validation report records the renderer, page count, dimensions,
text extraction, and visual page review.
