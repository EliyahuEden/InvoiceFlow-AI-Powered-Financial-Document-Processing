# Contributing

This guide is for engineers working on InvoiceFlow.

## Development setup

```bash
cp .env.example .env                                   # set JWT_SECRET; an LLM key is optional
docker compose up -d --build                           # postgres, redis, s3, api, worker, web, mailpit
docker compose exec api python -m app.cli seed --reset # demo organization with processed documents
```

The web app runs on http://localhost:3000, the API on http://localhost:8010 and the local mail inbox on
http://localhost:8025. To work on the frontend with hot reload, run `npm run dev` in `frontend/` with
`BACKEND_URL=http://localhost:8010`.

## Before you open a pull request

```bash
cd backend && python -m pytest -q                       # unit and PostgreSQL integration tests
cd frontend && npm run typecheck && npm run lint && npm test
```

Browser tests change data (they record decisions and send emails), so run them against the disposable stack described
at the top of `docker-compose.e2e.yml`, never against a database you care about.

## Conventions

- **Money is `Decimal`, end to end.** Never add or convert amounts across currencies implicitly.
- **AI output is advisory.** Anything a model writes is labelled as such and linked to its sources. No model or tool
  may approve or schedule a payment.
- **Every tenant-owned table** carries `organization_id` and a row-level security policy, with a test.
- **Every state change** that matters to an auditor is recorded through `app.services.audit.record`.
- **Hebrew first.** UI text lives in `frontend/src/lib/i18n/dictionaries.ts` in both languages; identifiers, amounts and
  dates stay left-to-right inside right-to-left text.
- **Accessibility:** new screens must pass the WCAG 2.2 AA scan in `frontend/tests/e2e/a11y.spec.ts`.

## Database changes

Add an Alembic migration in `backend/alembic/versions/`. Migrations run automatically when the API starts.
