# Negated safety constraints

## Problem

The Router Core previously treated a sensitive noun as execution intent before
considering its grammar. As a result, a prohibition such as `Do not access
credentials` matched the same hard trigger as a request to read credentials.
The action-danger rules then repeated the false positive and forced the
security profile.

## Central correction

`smart_codex.preprocessor.analyze_prompt_semantics` now creates two in-memory
views:

- the normalized prompt used only while processing the current request; and
- an actionable view with recognized, negated secret-access clauses removed.

The scorer uses the actionable view for hard overrides, category scoring, risk,
complexity, and action danger. It retains only canonical labels such as
`credential_access_prohibited` on the score card and routing decision. Raw
constraint text is not added to logs or persisted.

This is a Router Core correction. Hooks and App Server integrations consume the
same decision and do not carry their own credential-negation exceptions.

## Safety boundary

The parser recognizes prohibitions such as `do not`, `never`, `without`, and
passive `must not be` clauses when they govern secret-access actions. Removing
those clauses from the actionable classification view does not remove them
from the prompt forwarded to Codex.

Direct secret access remains a hard critical route. Reads, prints, exports,
copies, retrievals, and similar operations targeting credential stores,
passwords, tokens, `.env`, private keys, or saved browser cookies produce:

- `secret_handling`;
- `critical` risk;
- `secret_touching_operation`;
- the `security` profile;
- `read-only` sandboxing;
- `on-request` approval; and
- a confirmation warning.

Documentation and policy text about prohibiting disclosure remain
documentation or read-only analysis. A real Gmail send is separately labeled
`external_service_action`: it retains the communication task profile while
still requiring the normal human approval policy. Model capability and action
authority remain independent.
