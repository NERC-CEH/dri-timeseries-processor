# Versioning and Releases

This project follows [Semantic Versioning](https://semver.org/). Every version is a `major.minor.patch` number, for
example `0.2.7`. We use these three components as follows:

- **`major`** and **`minor`** mark meaningful changes to the software (breaking changes, new features). These are
  bumped by hand when you are ready to release a new minor or major version.
- **`patch`** is used as an auto-incrementing build number. CI bumps it by one whenever a pull request targeting
  `staging` is opened or pushed to, so each build produces a unique image tag and never collides with previous builds.

Work flows through three branches: `feature/*` -> `staging` -> `production`.

- Once a pull request targeting `staging` exists, each push to the PR auto-bumps the patch component
  (e.g. `0.2.7` -> `0.2.8`). Feature-branch pushes without a PR open do not bump.
- `make bump-minor` and `make bump-major` are run by hand when you want a new minor or major version. Both need a
  populated `CHANGELOG/<version>.md` before the release PR can be merged.
- Every merge from `staging` to `production` builds the production Docker image, tags the commit as `v<version>`, and
  creates a GitHub release - all automatically.

## Why patch bumps are automatic

Docker images are tagged with the `pyproject.toml` version and pushed to an ECR registry that has tag immutability
turned on. If two merges to `staging` shared the same version, the second push to ECR would be rejected. Auto-bumping
the patch on every push to an open PR guarantees each merge to `staging` produces a unique, monotonically-increasing
tag - which is also what the FluxCD SemVer policy needs to pick the latest image.

## Automatic patch bumps (the common case)

The `auto-bump-patch` workflow runs **only when there is an open pull request targeting `staging`**. It fires when the
PR is opened, reopened, or a new push is made. Pushes to a feature branch that does not yet have a PR open do not
trigger it.

When it fires it:

1. Checks out the PR's head branch.
2. Looks at the diff to decide whether to act:
   - On **new push to the PR** it inspects the commits added by that push.
   - On **opened** / **reopened**, it inspects the full diff of the branch against `staging`.
3. If `pyproject.toml` was changed in that diff, it skips - you (or a previous CI run) have already bumped the version.
4. Otherwise it runs the bump-patch utility, which increments the patch component in `pyproject.toml`, commits it as
   `Bump version: <old> -> <new>`, and pushes the commit back to the PR's head branch.

The push is made with the workflow's default `GITHUB_TOKEN`. As a consequence, the bump commit itself does **not**
trigger any further workflow runs - GitHub deliberately blocks `GITHUB_TOKEN` pushes from re-triggering workflows to
avoid loops. The PR's checks panel will therefore not refresh against the bump commit, even though the bumped version
is what ends up being deployed when the PR merges to `staging`.

You will need to `git pull` locally before your next push to pick up the bump commit.

**Example - `feature/my-thing` branched from `staging` at `0.1.5`:**

```text
staging at 0.1.5
+-- feature/my-thing branched from staging at 0.1.5
    +-- push commit A   (no PR yet -> no auto-bump)
    +-- push commit B   (no PR yet -> no auto-bump)
    +-- PR opened against staging
    |   +-- pipeline.yml runs against 0.1.5 (tests, Docker build with the pre-bump version)
    |   +-- auto-bump-patch runs (opened event)
    |   |   +-- diff vs staging shows no pyproject.toml change -> bumps to 0.1.6 and pushes
    |   |   +-- bump commit does NOT re-trigger pipeline.yml (GITHUB_TOKEN limitation)
    |
    +-- git pull   (picks up CI's bump commit)
    +-- push commit C
    |   +-- pipeline.yml runs against 0.1.6 (tests, Docker build)
    |   +-- auto-bump-patch runs (synchronize event)
    |   |   +-- diff of commit C shows no pyproject.toml change -> bumps to 0.1.7 and pushes
    |   |   +-- pipeline.yml does NOT re-run against 0.1.7
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

Because the manual bump commit modifies `pyproject.toml`, the auto-bump workflow will skip on the first PR event that
sees it (the diff includes a `pyproject.toml` change). On subsequent pushes to the PR that do not touch
`pyproject.toml`, the auto-bump will resume incrementing the patch (`0.2.0` -> `0.2.1` -> ...).

**Example - releasing a new `0.2.0` minor version:**

```text
staging at 0.1.7
+-- feature/release-2.0 branched from staging at 0.1.7
    +-- make bump-minor
    |   +-- Local commits: "Bump version: 0.1.7 -> 0.2.0", "Add CHANGELOG/0.2.0.md stub"
    |
    +-- Edit CHANGELOG/0.2.0.md with real release notes, commit
    +-- push
    |   +-- CI sees pyproject.toml was changed in this push -> SKIPS auto-bump
    |
    +-- PR opened against staging
    +-- PR merged
    +-- staging is now at 0.2.0
```

Note: you should probably not run `make bump-patch` manually. The Makefile target still
exists for use in unusual situations, but the everyday use is "let the CI do patches".

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
