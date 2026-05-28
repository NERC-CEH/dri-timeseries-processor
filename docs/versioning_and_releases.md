# Versioning and Releases

This project follows [Semantic Versioning](https://semver.org/). Every version is a `major.minor.patch` number, for
example `0.2.7`. We use these three components as follows:

- **`major`** and **`minor`** mark meaningful changes to the software (breaking changes, new features). These are
  bumped by hand when you are ready to release a new minor or major version.
- **`patch`** is used as an auto-incrementing build number. A local `pre-push` git hook bumps it by one on every push
  that does not already contain a version change, so each push produces a unique image tag and never collides with
  previous builds.

Work flows through three branches: `feature/*` -> `staging` -> `production`.

- Install the hook once per clone with `make install-hooks`. From then on, `git push` automatically bumps the patch
  component when needed.
- `make bump-minor` and `make bump-major` are run by hand when you want a new minor or major version. Both need a
  populated `CHANGELOG/<version>.md` before the release PR can be merged.
- A CI check (`verify-version-bump`) refuses any PR targeting `staging` whose head doesn't include a version bump.
  This catches pushes made without the hook installed and most bot-created PRs (e.g. dependabot).
- Every merge from `staging` to `production` builds the production Docker image, tags the commit as `v<version>`, and
  creates a GitHub release - all automatically.

## Why patch bumps are needed on every push

Docker images are tagged with the `pyproject.toml` version and pushed to an ECR registry that has tag immutability
turned on. If two merges to `staging` shared the same version, the second push to ECR would be rejected. Bumping the
patch on every push guarantees each merge to `staging` produces a unique, monotonically-increasing tag - which is also
what the FluxCD SemVer policy needs to pick the latest image.

## Patch bumps via the pre-push hook (the common case)

The hook lives at `.githooks/pre-push` and is wired in by `make install-hooks` (which sets `git config core.hooksPath
.githooks`). On every `git push` it:

1. Looks at the diff between the commits being pushed and the previous remote tip (or `origin/staging` for a brand-new
   branch).
2. If the `version` line in `pyproject.toml` already changed, it does nothing - you already bumped
   using `make bump-minor`/`bump-major`).
3. Otherwise it runs `python scripts/bump.py patch --no-changelog`, which increments the patch, regenerates `uv.lock`,
   and creates a single `Bump version: <old> -> <new>` commit on your branch. It then re-runs `git push` for you with
   the bumped state. The recursive push fires this same hook a second time, but by then the version line has changed
   so the hook falls through and the push proceeds normally. The original outer push is then aborted (you will see a
   `failed to push some refs` message at the very end - the **updated** push has already succeeded; this is just git
   aborting the **original** push).

Because the bump is made by your local git client (not by a CI job), the push that GitHub sees already contains the
bumped version. `pipeline.yml` runs against the right commit, and the PR's checks panel shows the correct status for
the version that will actually be deployed.

If you forget to install the hook, the `verify-version-bump` check on the PR will fail with a clear message asking
you to run `make install-hooks` and push again.

**Example - `feature/my-thing` branched from `staging` at `0.1.5`:**

```text
staging at 0.1.5
+-- feature/my-thing branched from staging at 0.1.5
    +-- git push commit A
    |   +-- pre-push hook detects no version change vs origin/staging
    |   +-- runs bump.py: pyproject.toml goes 0.1.5 -> 0.1.6, commit created locally
    |   +-- hook re-runs git push with the bumped state
    |   |   +-- hook fires again; sees version was bumped (0.1.5 -> 0.1.6) -> falls through
    |   |   +-- push proceeds; remote receives commit A + bump
    |   +-- original push aborts ("failed to push some refs" - safe to ignore)
    |   +-- PR opened: pipeline.yml runs against 0.1.6, verify-version-bump passes
    |
    +-- git push commit B
    |   +-- pre-push hook detects no version change vs previous remote tip
    |   +-- bumps 0.1.6 -> 0.1.7, re-runs push, original push aborts
    |   +-- pipeline.yml runs against 0.1.7
    |
    +-- PR merged
    +-- staging is now at 0.1.7
    +-- Docker image dri-timeseries-processor:0.1.7 pushed to staging ECR
```

## Manual minor and major bumps

When you want to release a new minor (`0.x.0`) or major (`x.0.0`) version, bump the version manually on your feature
branch:

```sh
make bump-minor   # e.g. 0.1.7 -> 0.2.0
make bump-major   # e.g. 0.2.0 -> 1.0.0
```

This:

1. Updates `pyproject.toml` (and `CITATION.cff` if present) to the new version.
2. Creates `CHANGELOG/<new_version>.md` with a placeholder.
3. Creates two commits: one for the bump, one for the changelog stub.

**You must edit `CHANGELOG/<new_version>.md`** to replace the `<!-- Add release notes here -->` placeholder with your
real release notes, then commit and push. The `release-ready` check on the production PR rejects merges whose changelog
is missing, still contains the placeholder, or has no content beyond the heading.

Because the manual bump already changed the `version` line, the pre-push hook will detect this and skip its own bump
on the push that delivers `0.2.0`. On subsequent pushes to the PR that don't touch the version, the hook resumes
incrementing the patch (`0.2.0` -> `0.2.1` -> ...).

**Example - releasing a new `0.2.0` minor version:**

```text
staging at 0.1.7
+-- feature/release-2.0 branched from staging at 0.1.7
    +-- make bump-minor
    |   +-- Local commits: "Bump version: 0.1.7 -> 0.2.0", "Add CHANGELOG/0.2.0.md stub"
    |
    +-- Edit CHANGELOG/0.2.0.md with real release notes, commit
    +-- git push
    |   +-- pre-push hook detects version already changed (0.1.7 -> 0.2.0) -> nothing to do
    |   +-- push proceeds at 0.2.0
    |
    +-- PR opened against staging
    +-- PR merged
    +-- staging is now at 0.2.0
```

Note: you should not normally run `make bump-patch` manually - the pre-push hook handles patches. The Makefile target
still exists for unusual situations.

## Production releases

Every push to `production` (i.e. every merge of the staging-to-production PR) does two things:

- Builds the production Docker image, tags it with the current `pyproject.toml` version, and pushes it to the production
  ECR.
- Runs the `release` job, which creates a `v<version>` git tag and a GitHub release populated from
  `CHANGELOG/<version>.md`.

Two checks are run:

- The `release-ready` check (runs on the PR before merge):
    - Compares `pyproject.toml` on `production` vs the incoming version. If they are equal, it fails - production merges
      always require a bump.
    - Requires `CHANGELOG/<new_version>.md` to exist, to not contain the placeholder, and to have content beyond the
      heading.
- ECR tag immutability: if a merge to `production` somehow happened without a bump, the Docker push would also be
  rejected by ECR.

**Example - releasing `0.2.3` to production:**

```text
production at 0.1.5
staging at 0.2.3 (after several auto-patch bumps and a manual minor bump)
+-- Auto-PR opened: staging -> production
    +-- release-ready check
    |   +-- production version (0.1.5) != staging version (0.2.3) -> OK
    |   +-- CHANGELOG/0.2.3.md exists, no placeholder, has content -> OK
    |   +-- check passes
    |
    +-- PR merged
    +-- On push to production:
        +-- Docker image dri-timeseries-processor:0.2.3 pushed to production ECR
        +-- Git tag v0.2.3 created and pushed
        +-- GitHub release "0.2.3" created from CHANGELOG/0.2.3.md
```

If `CHANGELOG/0.2.3.md` did not exist or still had the placeholder, the PR would be blocked at the `release-ready`
check.

## PRs without a hook (humans and bots)

`verify-version-bump` is the safety net for any PR to `staging` that doesn't carry a version bump - typically:

- A human pushed without `make install-hooks` installed.
- A bot pushed via the GitHub API (which never runs client-side hooks). The most common case is dependabot.

In both cases the PR's `verify-version-bump` check fails with a message telling you how to fix it. For a human, that
means installing the hook and pushing again. For dependabot, a maintainer needs to either bump the version on the
dependabot branch by hand (e.g. by running `make bump-patch` and amending the PR), or close the PR and make the
dependency update manually.

## Workflows and hooks involved

**`.githooks/pre-push`** (installed via `make install-hooks`)

- Runs on every `git push` from a client that has the hook installed.
- Bumps the patch component of `pyproject.toml` (and regenerates `uv.lock`) if the push doesn't already include a
  version change. Aborts the current push and asks you to re-run `git push` to include the bump commit.

**`.github/workflows/pipeline.yml`**

- Triggers on: `pull_request` events (any base branch) and `push` events to `staging` or `production`.
- `verify-version-bump` job: on PRs targeting `staging`, fails if `pyproject.toml`'s `version` field is unchanged
  vs `staging`. Catches pushes made without the hook and bot-created PRs.
- Runs tests, builds and pushes Docker images, opens the staging-to-production auto-PR, gates production merges with
  `release-ready`, and creates the GitHub release on production merge.
