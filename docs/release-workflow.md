# Development and showcase releases

The private development repository is the source of truth. Create `feature/<topic>` branches from current `main` and open pull requests into `main`. Check the backend, frontend, and Compose jobs on the latest PR head. Review the diff and merge only when those jobs pass. Keep direct pushes off `main`. GitHub may not enforce private-repository branch rules on the account plan; where unavailable, this is a maintainer rule. Enable required PR checks and disallow bypass if the plan supports them.

The public repository is a standalone snapshot, with its own `main` and release tags. Its initial commit represents an already-developed MVP. It does not import private history. Preserve genuine authorship, timestamps, attribution and license notices. Use public issues for work that can be discussed openly. Keep security reports and private development details out of public issues.

## Publish an approved update

1. Pick the exact reviewed private `main` commit. Confirm its push CI is green and tag it in the private repository with an annotated `showcase-vX.Y.Z` tag.
2. Run `git archive --format=tar --output=/tmp/documind-approved.tar showcase-vX.Y.Z` in the private clone, and extract it to an empty staging directory. Review the archive contents. Copy only approved source, tests, lockfiles, configuration templates, CI, documentation, and public demo images into a fresh showcase clone. Reconcile removals explicitly. Preserve required third-party notices.
3. Review the complete staged diff and filenames. Look for credentials, real `.env` files, databases, uploads, cache files, personal data, internal URLs, and sensitive screenshots. Public example environment files must contain blank credentials or safe defaults. Use generated or otherwise publishable sample data.
4. Run backend tests, frontend typecheck/lint/build, and Compose validation. For subsequent updates use a public PR and wait for public CI. Confirm the merged public commit passes CI, then publish a `vX.Y.Z` release on that exact commit. Keep notes about user-visible changes, limitations, and how to run locally. Record the private source revision in private release notes.
5. Check the public tree, release, and CI result. Do not mirror private branches, push private Git objects, or automate publication from every development commit.

Revert a faulty public change with a regular PR and a new patch release. If a secret is accidentally published, revoke or rotate it immediately and follow the host's sensitive-data removal process; a revert alone does not remove exposure.

Dependabot proposes npm and GitHub Actions version updates. Python uses a fully pinned `backend/requirements.lock` with a `.lock` filename, so review Python dependencies separately and run an advisory check such as `pip-audit -r backend/requirements.lock` when preparing releases. Keep dependency changes in their own reviewed PR when practical.
