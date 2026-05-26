# Contributing

Contributions are welcome and greatly appreciated.

## Types of Contributions

### Report Bugs

Report bugs at https://github.com/NERC-CEH/dri-timeseries-processor/issues.

If you are reporting a bug, please include:

- Your operating system name and version.
- Any details about your local setup that might be helpful in troubleshooting.
- Detailed steps to reproduce the bug.


### Fix Bugs

Look through the GitHub issues for bugs -
these are open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features -
these are open to whoever wants to implement it.

### Write Documentation

DRI Timeseries Processor could always use more documentation, whether as part of the official docs, local
README's or in docstrings, and comments.

### Submit Feedback

The best way to send feedback is to file an issue at
https://github.com/NERC-CEH/dri-timeseries-processor/issues.

If you are proposing a feature:

- Explain in detail how it would work.
- Keep the scope as narrow as possible, to make it easier to implement.


## Get Started

Ready to contribute? Here's how to set up `dri-timeseries-processor` for local development.

1. Fork the `dri-timeseries-processor` repo on GitHub.

1. Clone your fork locally:

   ```sh
   git clone git@github.com:your_name_here/dri-timeseries-processor.git
   ```

1. Install your local copy with uv:

   ```sh
   cd dri-timeseries-processor/
   uv sync
   ```

1. Create a branch for local development off `staging`:

   ```sh
   git checkout staging
   git pull origin staging
   git checkout -b name-of-your-bugfix-or-feature
   ```

   Now you can make your changes locally.

1. When you're done making changes, check that your changes pass linting and the tests:

   ```sh
   make qa
   ```

1. Commit your changes and push your branch to GitHub:

   ```sh
   git add .
   git commit -m "Your detailed description of your changes."
   git push origin name-of-your-bugfix-or-feature
   ```

1. Open a pull request targeting `staging` through the GitHub website.

   **Branch protection on `staging` and `production`:**
   - At least 1 approving review is required before merge.
   - CI checks (`test-python`) must pass.
   - All PR review conversations must be resolved.


## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put your new functionality into a function
with a docstring, and add the feature to the list in README.md.
3. The pull request should pass all quality checks (`make qa`) and GitHub Actions, making sure that the tests pass for all supported Python versions.

## Tips

To run a subset of tests:

```sh
uv run pytest tests/
```

## Releasing a New Version

1. **Bump the version** and create a CHANGELOG stub:
   ```bash
   make bump-patch   # or bump-minor / bump-major
   ```
   This updates `pyproject.toml`, commits the bump, and creates `CHANGELOG/<version>.md`.

2. **Fill in** `CHANGELOG/<version>.md` with the release notes, then commit and push:
   ```bash
   git add CHANGELOG/<version>.md
   git commit -m "Add release notes for <version>"
   git push origin staging
   ```

3. **Release:**
   ```bash
   make release
   ```
   This creates an annotated `v*` tag, pushes it to GitHub, and creates a GitHub Release with the changelog contents as release notes.
