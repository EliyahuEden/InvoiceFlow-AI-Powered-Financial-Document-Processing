# InvoiceFlow web app

Next.js 15 (App Router), React 19, TypeScript and Tailwind. Hebrew right-to-left by default, with English, in light
and dark themes.

```bash
npm install
BACKEND_URL=http://localhost:8010 npm run dev   # http://localhost:3000, API requests are proxied to the backend
```

| Command | What it does |
|---|---|
| `npm run typecheck` | TypeScript, no emit |
| `npm run lint` | ESLint |
| `npm test` | Unit tests (Vitest, Testing Library) |
| `npm run e2e` | Browser tests (Playwright); run them against the disposable stack in `docker-compose.e2e.yml` |
| `node scripts/axe-page.mjs <route>` | WCAG 2.2 AA scan of one page in both languages, both themes, desktop and phone |

## Layout

```
src/app/(app)/      authenticated pages: queue, inbox, upload, investigations, suppliers, orders, knowledge, ...
src/app/login/      sign-in and the other account pages
src/app/legal/      privacy policy, terms, data-processing agreement, accessibility statement
src/components/     shared UI; page-kit.tsx holds the page header, filters, segments and detail panel
src/lib/            API client, formatting, i18n dictionaries (dictionaries.ts)
tests/unit/         Vitest
tests/e2e/          Playwright: workflows, accounts, accessibility and responsive checks
```
