# Production deployment

The production host checks `origin/main` every minute with a systemd user timer.
No self-hosted GitHub runner is attached to the public repository. GitHub Actions
runs validation; deployment also independently runs frontend tests before activation.

The host entrypoint is installed from `scripts/deployment/deploy.py` outside the
source checkout. It fetches main without resetting the production working tree,
exports only `web/` to a temporary directory, builds the Docker image, runs unit
tests, and replaces only the frontend service. The private backend, database,
worker, environment files and gateway configuration remain provisioned on the host.
Changes to those private services or the deployment entrypoint require a separate
operator deployment. Frontend changes on main deploy automatically.

A release is successful only after the frontend container is healthy, the public
`/version.json` returns the exact commit, and `/health/live` reports alive. A failed
activation restores the previous image and retries on the next timer invocation.
Build or test failures leave the existing frontend running. The initial deployment
and container recreation can briefly interrupt frontend requests.

Host configuration in `~/.config/rotterdam-deploy.env` specifies `DEPLOY_SOURCE`,
`DEPLOY_STATE`, `DEPLOY_COMPOSE`, and `DEPLOY_URL`. Keep production values private.
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
The current image, rollback tag and two previous release tags are retained.
Intermediate builder tags and older release tags are removed after success. Docker
build caches remain available; monitor available disk space and prune old caches
periodically while retaining rollback images.
