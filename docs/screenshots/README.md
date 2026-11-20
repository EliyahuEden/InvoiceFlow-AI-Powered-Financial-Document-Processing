# Screenshot provenance

These are real Playwright captures of InvoiceFlow with synthetic demo invoices. They are not generated artwork or screenshots of live financial records.

`01-` through `10-` come from `frontend/tests/e2e/screenshots.spec.ts`. `review-*` comes from `frontend/tests/e2e/review-screenshots.spec.ts`: dashboard, queue and investigation workspace, Hebrew/English, light/dark, 1440×1000 desktop and 375×900 mobile (Hebrew). Captures were refreshed on 2026-11-20 against the local production frontend and an isolated offline demo backend.

Regenerate from the frontend directory against a disposable, seeded stack:

```powershell
$env:SCREENSHOTS = '1'
$env:E2E_BASE_URL = 'http://localhost:3001'
npx playwright test --workers=1
```

The workflow tests record decisions and change the synthetic data. Use a test database, and set the backend and worker to `LLM_PROVIDER=offline`. Run Playwright invocations serially because they share and clean the same output directory.
