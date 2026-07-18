# Repository and Resource Preflight

Recorded: 2026-07-18, Europe/Berlin

## Production repository

- Git root: canonical local SmartRouter checkout (absolute private path omitted
  from the public artifact)
- Remote: `https://github.com/luciferprosun/Kodex-OpenAI-Custom-Skill.git`
- Starting branch: `main`
- Starting HEAD: `e9dd9d0483c2809a2493922af6809ac1d3f51ed6`
- Starting worktree: clean
- Required research baseline: `e32c176adbd42acc732e4a374b301814d1a158f0`
- Baseline remote branch: `feature/model-policy-calibration-v0-1`
- Research branch created from the verified baseline:
  `research/agent-token-economics-2a`

The canonical checkout did not initially contain the required commit object.
The exact remote branch was fetched and the research branch was created from
`e32c176`; `main` was not advanced or rewritten.

## Build Week repository

- Git root: separate local SmartRouter Build Week checkout (absolute private
  path omitted from the public artifact)
- Remote:
  `https://github.com/luciferprosun/Smart-Router-Build-Week-2026.git`
- Branch: `main`
- Starting HEAD: `d4de2fab983e5c209be3ebe7329d9d7144e22ee0`
- Starting worktree: clean

## Environment

- Codex CLI: `0.144.5`
- `python`: unavailable under that command name
- `python3`: `3.12.3`
- Root filesystem: 57 GiB total, 51 GiB used, 3.2 GiB available (95% used)
- Memory: 3.7 GiB total, about 1.3 GiB available at preflight
- Swap: 4.0 GiB total, 2.0 GiB available at preflight
- Additional mounted storage was observed, but this mission does not redirect
  repository data outside its authorized paths.

## Acquisition decision

The root filesystem is resource-constrained. No complete trajectory corpus will
be downloaded. Acquisition is limited to source metadata and small,
license-reviewed, checksum-recorded samples. Every candidate must have a size,
license, redistribution, and sampling decision before download.
