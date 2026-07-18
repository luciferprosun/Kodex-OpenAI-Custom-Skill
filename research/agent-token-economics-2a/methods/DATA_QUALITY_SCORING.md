# Data-Quality Scoring

Each normalized run receives ten binary ten-point components:

1. exact model identity;
2. exact agent/framework identity;
3. exact task identity;
4. provider-reported token counts;
5. complete per-request breakdown;
6. complete public-safe trajectory or lossless event index;
7. objective verifier;
8. timestamped price table when monetary cost is used;
9. repeatable acquisition/transformation;
10. license clarity.

The ten booleans are persisted in every canonical run as
`quality_components`. The validator recomputes their ten-point sum and rejects
any disagreement with `quality_score`; class range is checked separately. This
makes the rubric auditable rather than a free-form human label. Classes are:

| Class | Score | Meaning | Numerical routing use |
| --- | ---: | --- | --- |
| A | 90-100 | Directly measured and fully reproducible | Allowed |
| B | 75-89 | Measured with minor missing metadata | Allowed with limitations |
| C | 55-74 | Framework-reported or reconstructable | Allowed only in explicit strata |
| D | 30-54 | Cost-only, partially inferred, or materially incomplete | Qualitative only |
| E | 0-29 | Anecdotal, unidentified, or non-repeatable | Excluded |

Gating overrides prevent a high arithmetic score from hiding a critical defect:

- unknown or incompatible redistribution/license status caps a record at D;
- anecdotal data is E;
- absent exact model identity caps model-specific inference at D;
- cost without its price date is not normalized as historical billed cost;
- hidden reasoning or secret-bearing raw content is never published;
- records with unknown success criteria cannot inform accepted-task cost.

Only A-C records may enter numerical priors, and every result reports the class
mix. D may explain missingness or directional evidence. E is retained only in
the exclusion registry.

The validator also requires the recomputed numeric score to fall inside the
declared class range. Numerical admission additionally requires explicit permission in
the dataset registry; exact timestamped model/provider/version,
framework/version and product-surface identity; observed prompt and total-token
counts with known scopes and non-unknown measurement methods; a completed
outcome with verifier evidence; a task-level success criterion and objective
verifier profile; and compatible run/provenance licenses. A normalized monetary
cost used for accepted-cost analysis must be run-scoped and tied to one dated
price table and currency. A censored record can enter only the separate
censoring-analysis cohort, with an explicit flag, A-C quality, a censor reason,
and observed time or token exposure.
