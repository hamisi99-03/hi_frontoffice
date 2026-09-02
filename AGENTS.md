# AGENTS.md

Guidance for the coding agent working on this repo (MEATMAGIC).

## Project overview

Django point-of-sale desktop app ("MEATMAGIC") packaged as a single Windows
`.exe` (PyInstaller + pywebview). The shop computer runs `update_meatmagic.bat`,
which downloads the **latest GitHub release's** `MEATMAGIC.exe` and swaps it in.

- Source root: this directory (`hi_frontoffice/`)
- Django app: `sales/` (`models.py`, `views.py`, `views_admin.py`, `forms.py`, `pdf.py`)
- Templates: `sales/templates/` (pages extend `sales/templates/base.html`)
- Desktop entry point for the .exe: `build_entry.py`
- PyInstaller spec: `meatmagic.spec`
- Repo: `https://github.com/hamisi99-03/hi_frontoffice.git` (public)
- Python env: `venv\Scripts\python.exe`

## Rebuild & release workflow — run EVERY time the user says "rebuild" / "push"

The .exe bundles the templates and Python code, so any template or Python
change requires a rebuild. The shop computer only receives an update when a
**new GitHub release (new tag + attached `dist\MEATMAGIC.exe`)** is published;
pushing source alone is not enough.

1. **Build** the .exe from the project root:
   ```
   venv\Scripts\python.exe -m PyInstaller meatmagic.spec --clean
   ```
   Output: `dist\MEATMAGIC.exe`. Verify it succeeded (timestamp/size changed).

2. **Commit + push** only the changed source files:
   - `git status --short` to review.
   - `git add <source files>` (never `db.sqlite3`, `dist/`, `build/`, `venv/`,
     `meatmagic.key` — all gitignored).
   - `git commit -m "<message>"; git push origin main`.

3. **Bump the version tag** (patch increment; list current with `git tag -l`):
   `v1.0.2` → `v1.0.3`.

4. **Create a GitHub release** with that new tag and attach `dist\MEATMAGIC.exe`.
   - Preferred (if `gh` is installed + authed):
     ```
     gh release create v1.0.3 dist\MEATMAGIC.exe --title v1.0.3 --notes "what changed"
     ```
   - Or via the GitHub REST API with a token obtained from the local credential
     manager: `"protocol=https`nhost=github.com`n" | git credential fill`
     (use the returned `password` as a Bearer token), then `POST
     /repos/hamisi99-03/hi_frontoffice/releases` with `{tag_name, target_commitish:"main"}`,
     then upload the asset to the returned `upload_url`.

5. **Update** the local `version.txt` to the new tag (untracked local reference).

The shop then runs `update_meatmagic.bat` to detect and download the new tag.

## Notes

- Never commit secrets, the database, or build artifacts.
- Run `venv\Scripts\python.exe manage.py check` to validate Python changes.
- Tests/lint: none configured; rely on `manage.py check` and manual template
  render checks.
