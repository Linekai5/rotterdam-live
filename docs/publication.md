# Preparing the public repository

The current branch excludes `api/`, local automation, runtime configuration,
credentials, database dumps, caches and build outputs. Removing paths from the
Git index leaves this machine's private files in place. IP literals have been
removed from tracked documentation, including the architecture text copies.
Production bind addresses and database passwords are supplied privately.

## History still needs a release decision

The repository's existing commits still contain backend source, server addresses
and previously committed database credential defaults. A normal merge, squash
merge or `.gitignore` update does not erase history from the existing repository.
Do not make the current repository public on the strength of this cleanup alone.

The least disruptive release route is to retain this repository privately and
initialize a separate public repository from a reviewed export of the cleaned
commit. Export the committed tree with `git archive`, rather than copying the
working directory, which still contains ignored private files. The public
repository must start with a new initial commit and no private branches or tags.
No new repository has been published by this change.

Keeping the current repository URL instead requires a coordinated history
rewrite across affected branches/tags and cleanup of pull-request references
and cached views where necessary. That changes commit IDs and requires explicit
approval before force-pushing. Do not push an old clone back into the cleaned
repository. GitHub documents the consequences and additional cleanup in
[Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

Rotate any real credentials that used committed values before publication.
Changing a Compose variable alone does not change an existing database password.
This branch does not rotate production credentials or alter repository visibility.

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
