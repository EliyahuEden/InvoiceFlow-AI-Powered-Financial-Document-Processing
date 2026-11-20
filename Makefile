# InvoiceFlow developer commands (Docker required). On Windows without make, run the commands directly.
.PHONY: up seed demo down test test-backend test-frontend e2e eval logs reset

up:            ## build and start the full stack
	docker compose up -d --build

seed:          ## load the fictional demo organization and process its documents
	docker compose exec api python -m app.cli seed --reset

demo: up seed  ## one command: start everything and load the demo

down:
	docker compose down

test-backend:  ## pytest (unit + PostgreSQL integration)
	cd backend && python -m pytest -q

test-frontend:
	cd frontend && npm run typecheck && npm run lint && npm test

e2e:           ## Playwright against the running stack
	cd frontend && npx playwright test

eval:          ## reproduce benchmark results (writes eval/results/*.json)
	docker compose run --rm --no-deps -v ./eval:/srv/eval worker python /srv/eval/build_extraction_dataset.py
	docker compose run --rm --no-deps -v ./eval:/srv/eval worker python /srv/eval/run_extraction_eval.py
	docker compose run --rm --no-deps -v ./eval:/srv/eval worker python /srv/eval/run_reconciliation_eval.py
	docker compose run --rm --no-deps -v ./eval:/srv/eval worker python /srv/eval/run_rag_eval.py

logs:
	docker compose logs -f api worker
