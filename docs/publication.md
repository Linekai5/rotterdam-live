# Preparing the public repository

The current branch excludes `api/`, local automation, runtime configuration,
credentials, database dumps, caches and build outputs. Removing paths from the
Git index leaves this machine's private files in place. IP literals have been
removed from tracked documentation, including the architecture text copies.
Production bind addresses and database passwords are supplied privately.

## History cleanup and publication

Both branch histories have been rewritten to remove backend source,
deployment addresses and credential literals. Audits of reachable historical
file contents and Gitleaks checks passed. GitHub still retains old commits in
pull-request references and cached views; those require its Support cleanup.
The repository remains private until that separate server-side step is verified.

The existing repository is being retained. Verified private bundles of the original
history and the sanitized audit records are stored outside the working checkout. The rewrite removes backend paths from before and after the monorepo
migration and redacts deployment addresses and credential literals throughout
historical files and messages. Changes to commit IDs require other clones to be
recloned or carefully rebased; merging old history back would undo the cleanup.

Closed pull requests retain old references that cannot be replaced by a
normal Git push. After the branch rewrite, GitHub Support must remove affected
pull-request references and cached views before this existing repository is
made public again. A history rewrite by itself cannot erase other people's
copies of data already obtained. See
[GitHub's removal procedure](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

The repository is private during cleanup. Actions are disabled and the
repository's self-hosted runner has been detached. Old workflow logs and caches
were backed up privately and removed, the unused production Actions secret
was removed, and workflow token permissions default to read-only. Keep deployments in trusted
private automation. A public repository exposes all of its branches, including
`malidev`; branch protection does not make a branch private.

Rotate any real credentials that used committed values before publication.
Changing a Compose variable alone does not change an existing database password.
This change does not rotate production credentials. They must be reviewed separately if committed values were ever used.

## Existing development and deployment checkouts

Before pulling the commit that removes tracked private files, securely back up
`api/` and any private automation outside the checkout. A normal Git update in
another clone can delete formerly tracked files. After updating, restore the
private backend from that backup or its private source into the ignored `api/`
directory. Do not use `git clean -fdx` on a checkout containing private files.

The production workflow and machine-specific agent hooks are no longer tracked;
their local copies remain. Provision deployment automation through a private
repository or another trusted channel. The public workflow uses GitHub-hosted
runners and does not deploy. Review and detach any self-hosted runners before
making a repository public; see GitHub's
[secure use reference](https://docs.github.com/en/actions/reference/security/secure-use).

The Compose templates require a separately provisioned private backend.
Copy `.env.example` to an ignored `.env` and supply the existing database
credentials. Production also requires `PUBLIC_BIND_ADDRESS` and
`PRIVATE_BIND_ADDRESS` for the correct public and private host interfaces.
Do not commit real values to example files.

## Validate the selected release tree

```bash
python3 scripts/check-public-tree.py
npm ci
npm test
npm run build
```

The public-tree check runs in CI. It verifies tracked files, not old commits,
server state, GitHub settings, logs or artifacts. Its credential patterns are a
baseline check, not a complete secret audit. Review the exported files and
history policy before publishing.

## Dependency audit recorded during preparation

A fresh frontend installation, all 14 frontend unit tests and the production
build passed from an export containing no backend source. The publication
checker and its four regression tests also passed.

On 11 November 2026, `npm --prefix web audit --json` reported one critical
MapLibre advisory and three low-severity dependency entries. The installed
`maplibre-gl` version is 2.4.0. The
[MapLibre sanitizer advisory](https://github.com/advisories/GHSA-jrc7-96c5-q579)
lists versions through 6.4.0 as affected and 6.4.1 as patched. A compatible
renderer upgrade and browser regression review remain separate work; this
cleanup does not claim to resolve that advisory. The map currently disables
MapLibre's native attribution control, but this is not a library patch.
The low-severity entries trace to
[deepmerge prototype poisoning](https://github.com/advisories/GHSA-gcqx-w48m-w2h4)
through the Svelte Vite plugin/inspector chain; npm reported no available fix.
