# Token Task Taxonomy

The taxonomy combines the existing SmartRouter SE, MATH, and PHY capability
scales with operational features that are plausible predictors of token use,
failure, retry, and escalation.

| Dimension | Values | Why it matters |
| --- | --- | --- |
| Interaction | single-turn, agentic, unknown | Agent loops can resend context and create multiple requests. |
| File scope | none, single-file, multi-file, unknown | Broader changes usually require more discovery and verification. |
| Repository scope | none, repository-local, cross-repository, unknown | Cross-repository work adds context and coordination burden. |
| Mutation | read-only, write, mixed, unknown | Write tasks usually add edit and verification loops. |
| Tools | tool-free, light, tool-heavy, unknown | Tool output can dominate later input and context growth. |
| Verifier | deterministic, partial, subjective, none, unknown | Objective verification changes retry and acceptance economics. |
| Horizon | short, medium, long, unknown | Long horizons increase requests, tool calls, and compaction risk. |
| Requirements | clear, partially ambiguous, ambiguous, unknown | Ambiguity is associated with exploration and rework. |
| Context | fresh, continued, long-continuing, unknown | Continued sessions can resend history and improve cache reuse. |
| Risk | low, moderate, high-impact, unknown | High impact raises verification and human-review requirements. |
| Work type | research, implementation, analysis, verification, mixed, unknown | Work type changes tool mix and acceptance criteria. |

Numerical capability levels are nullable per domain. A task with no physics
component does not receive `PHY-0`; its physics level remains `null` and is not
an applicable domain. Unknown operational metadata is explicit rather than
imputed silently.
