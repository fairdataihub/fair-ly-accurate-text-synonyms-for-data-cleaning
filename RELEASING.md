# Releasing `fair-ly-accurate` to PyPI

Publishing is automated with **PyPI Trusted Publishing (OIDC)** — GitHub Actions
mints a short-lived token per run, so there are no API tokens to store or rotate.
The workflow lives in [`.github/workflows/publish.yml`](.github/workflows/publish.yml):
publishing a **GitHub Release** builds the distributions and uploads them to PyPI.

## One-time setup

Register this repo as a *trusted publisher* on PyPI. Because the project does not
exist yet, use the "pending publisher" form:

- **PyPI** — https://pypi.org/manage/account/publishing/ → *Add a pending publisher*
  - PyPI Project Name: `fair-ly-accurate`
  - Owner: `fairdataihub`
  - Repository name: `fair-ly-accurate-text-synonyms-for-data-cleaning`
  - Workflow name: `publish.yml`
  - Environment name: `pypi`

The first successful publish creates the `fair-ly-accurate` project owned by the account
that registered the pending publisher.

(Optional, recommended) In GitHub → *Settings → Environments*, create an
environment named `pypi` and add yourself as a **required reviewer**, so a publish
needs a human click even though the repo may have other maintainers with write
access.

## Cutting a release

1. Bump the version in **both** places (they must match, or the workflow fails the build):
   - `pyproject.toml` → `version = "X.Y.Z"`
   - `src/fairly/__init__.py` → `__version__ = "X.Y.Z"`
   - Add a `CHANGELOG.md` entry.
2. Commit, then tag and push:
   ```bash
   git commit -am "Release X.Y.Z"
   git tag vX.Y.Z
   git push && git push --tags
   ```
3. Create a **GitHub Release** for that tag
   (Releases → Draft a new release → choose `vX.Y.Z` → Publish). That triggers the
   PyPI publish job.
4. Confirm:
   ```bash
   pip install fair-ly-accurate==X.Y.Z
   ```

PyPI refuses to overwrite an existing version, so every release needs a fresh
version number.

## Local build check

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
```
