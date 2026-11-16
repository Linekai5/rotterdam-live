# Production deployment

The production host checks `origin/main` every minute with a systemd user timer.
No self-hosted GitHub runner is attached to the public repository. GitHub Actions
runs validation; deployment also independently runs frontend tests before activation.

The host entrypoint is installed from `scripts/deployment/deploy.py` outside the
source checkout. It fetches main without resetting the production working tree,
exports only `web/` to a temporary directory, builds the Docker image, runs unit
tests, checks the live API through the actual frontend weather controller, and
replaces only the frontend service. The private backend, database,
worker, environment files and gateway configuration remain provisioned on the host.
Changes to those private services or the deployment entrypoint require a separate
operator deployment. Frontend changes on main deploy automatically.

A release is successful only after the frontend container is healthy, the public
`/version.json` returns the exact commit, and `/health/ready` confirms database and Redis connectivity. A preflight
check rejects releases whose weather contract is incompatible with the backend. A failed
activation restores the previous image and retries on the next timer invocation.
Build or test failures leave the existing frontend running. The initial deployment
and container recreation can briefly interrupt frontend requests.

Host configuration in `~/.config/rotterdam-deploy.env` specifies `DEPLOY_SOURCE`,
`DEPLOY_STATE`, `DEPLOY_COMPOSE`, and `DEPLOY_URL`. Set
`DEPLOY_GITHUB_REPOSITORY=owner/repository` to publish deployment results using the
host's authenticated `gh` CLI. Its credential needs permission to write commit
statuses. Keep production values and credentials private.
Install the entrypoint in `~/.local/lib/rotterdam-deploy/`, and the service and timer
in `~/.config/systemd/user/`. Enable user lingering so the timer survives logout
and starts after reboot, then run:

```sh
systemctl --user daemon-reload
systemctl --user enable --now rotterdam-deploy.timer
systemctl --user start rotterdam-deploy.service
systemctl --user status rotterdam-deploy.timer
journalctl --user -u rotterdam-deploy.service -n 100
```

The last successful revision is recorded in the private state directory's
`deployed.json`. The public version endpoint identifies the deployed source commit.
`status.json` records the attempted commit, result and failure reason. With GitHub
reporting configured, each commit has a separate **Production deployment** status:
pending while building, failure when blocked, and success only after public release
verification. CI success alone does not mean the site has deployed. Repeated failures
of the same commit do not create duplicate GitHub status entries; a successful retry
updates the result. A GitHub reporting outage does not block deployment.

Backend changes must be provisioned before a frontend that depends on them. In
particular, the current weather controller requires `/api/v1/weather/grid` independently
of station observations. A missing route blocks deployment while the previous release
continues serving traffic. Diagnose failures with `status.json` and the journal command
above; do not bypass compatibility checks to force an unsupported frontend live.

The current image, rollback tag and two previous release tags are retained.
Intermediate builder tags and older release tags are removed after success. Docker
build caches remain available; monitor available disk space and prune old caches
periodically while retaining rollback images.
