# IdleGrid: Predictive Idle-Compute Scheduler

IdleGrid borrows the team's **idle laptops** (Windows, macOS, Linux) to run ML jobs, **pauses a job within a second** when the laptop's owner comes back, and uses an **ML model trained on the team's own usage data** to send each job to the laptop most likely to stay free.

BACSE291 Innovative Design Project, SCOPE, VIT (2026–27). Team: Harith (dispatcher & integration), Arya (node agent), Amaan (database), Rejish (ML oracle & simulator), Ronit (executor, CLI, dashboard & HPO).

## Docs
- [`docs/PRD.md`](docs/PRD.md): the full plan, member sections and binding contracts
- [`docs/contract.md`](docs/contract.md): the shared data contract in plain words
- [`docs/LLM_BUILD_PROMPT.md`](docs/LLM_BUILD_PROMPT.md): prompts for building each phase with an AI assistant
- [`docs/runbook/network.md`](docs/runbook/network.md): network test and Tailscale setup

## Layout
```
idlegrid/
  common/      shared contract (models.py) + paths      [Harith]
  agent/       node agent on every laptop                [Arya]
  dispatcher/  coordinator server (prototype: app + mock cluster)  [Harith]
  db/          database layer (prototype SQL in db/legacy)  [Amaan]
  oracle/      idle-time prediction                      [Rejish]
  executor/    runs jobs, pause/resume                   [Ronit]
  packager/    job and result bundles                    [Ronit]
  cli/         gridctl command-line tool                 [Ronit]
  dashboard/   web dashboard (templates + static)        [Ronit]
examples/jobs/ demo workloads
tests/         unit/ and integration/
scripts/       network probe, secret check
```

## Quick start (Python 3.12)
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements/worker-env.txt -r requirements/dispatcher.txt -r requirements/dev.txt
pip install -e . --no-deps

pytest                                   # all tests
idlegrid-dispatcher --host 0.0.0.0       # coordinator + dashboard on http://<this-laptop>:8000
idlegrid-agent --dispatcher http://<coordinator>:8000/api/v1/heartbeat   # on each laptop
gridctl cluster                          # laptops as the coordinator sees them
gridctl demo-run --type pi               # local pause/resume demo
```

## Contributing
Feature branch → pull request → CI green (lint + tests on Windows, macOS, Linux) → one teammate's review. Contract changes follow [`docs/contract.md`](docs/contract.md). Never commit secrets: credentials come from `IDLEGRID_*` environment variables.
