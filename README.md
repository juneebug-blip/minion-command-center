# MINION Command Center v1.1

A real login dashboard for Commander #000 + 100 specialized AI workers. Each worker has a database-backed workspace and warehouse. The dashboard shows actual task states; it does not fake activity.

## Local run
1. Install Python 3.11+.
2. `python -m venv .venv`
3. Activate it (`.venv\\Scripts\\activate` on Windows).
4. `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and fill in your values.
6. Load the environment variables, then run `uvicorn app:app --reload`.
7. Visit `http://127.0.0.1:8000/login`.

Default password if OWNER_PASSWORD is not configured: `minion-change-me` (change this before internet deployment).

## Cloud deployment
Use a GitHub repository + Railway web service + Railway Postgres. Set `OPENAI_API_KEY`, `MINION_MODEL`, `OWNER_PASSWORD`, `SESSION_SECRET`, and `DATABASE_URL` as environment variables. The start command is in `Procfile`.

## Important
The 100 minions can perform AI tasks after an API key is configured. Live commerce research still needs official marketplace/supplier/data integrations. Spending is disabled by default (`AUTO_SPEND_LIMIT=0`). Do not put bank credentials in this app.
