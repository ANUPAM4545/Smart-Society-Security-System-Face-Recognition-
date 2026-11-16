# GitHub push plan

Target: `ANUPAM4545/Smart-Society-Security-System-Face-Recognition-`

Branch: `main`

## Contents

- Browser application: `web.py`, `web/index.html`, `web/app.js`, `web/style.css`.
- Desktop/CLI applications: `app.py`, `main.py`.
- Shared database, face recognition and evaluation modules under `security/`.
- Automated tests under `tests/`.
- Installation requirements, README, example test manifest and demonstration guide.
- This push plan and `.gitignore`.

## Procedure

1. Check the remote repository before publishing. Preserve any existing work; do not force-push or replace unrelated files.
2. Run `python3 -m unittest discover -s tests -v` and check the source for syntax/errors.
3. Check the tracked file list. Exclude biometric data, local databases, private photos, generated reports, environments and credentials.
4. Commit the source locally and publish it to the target repository through an account with write access.
5. Verify the resulting branch and the complete folder structure on GitHub. Report the actual result and any remaining blocker.

## Verification at preparation

- 20 automated tests pass. Vision calls in API tests use controlled face encodings.
- Local Git working tree was clean before adding this plan.
- `.gitignore` excludes `data/`, `dataset/`, `reports/`, `.venv/`, Python caches and `.env`.
- Runtime verification remains incomplete: the current execution environment blocks localhost port binding and dependency downloads. Do not claim a successful webcam run or measured recognition accuracy.
- The 20-person database and real held-out accuracy report still require actual data collection.
