# Proposed Accepted-Task Cost Objective

This is a research proposal and is not wired into SmartRouter.

For task features `x` and candidate route `m`, future work may minimize:

`E[first_attempt + retries + escalation + tools + verification + human_review + failure_penalty | x, m]`

subject to all of:

- minimum calibrated success probability;
- existing capability ceiling;
- task-risk constraints;
- an available verifier appropriate to the stakes;
- token and wall-time budgets;
- current model/surface availability;
- human-approval boundaries.

Expected accepted-task cost is undefined when the acceptance event, cost basis,
or price date is missing. Price never overrides capability, safety, or approval
constraints. A cheaper first request may be economically worse when its failure,
retry, verification, or escalation distribution raises total cost.

The future decision should expose its evidence stratum, uncertainty, missing
features, and fallback reason. Low-confidence or out-of-distribution tasks fail
closed to human-led routing or a conservative supported model; the research pack
does not grant action authority.
