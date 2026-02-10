# Job Match Platform

AI-powered job matching and interview preparation. Upload a CV, get matched to jobs, and use personalized interview prep questions.

---

## How to get the app running

You can run everything with **Docker** (recommended) or run **backend and frontend locally** with a local PostgreSQL database.

---

### Option A: Run with Docker (easiest)

**Prerequisites:** Docker and Docker Compose installed.

1. **Clone and go to the project root**
   ```bash
   cd job-match-platform
   ```

2. **Create backend environment file**
   ```bash
   cp backend/.env.example backend/.env
   ```

3. **Add your OpenAI API key to `backend/.env`**
   ```bash
   OPENAI_API_KEY=sk-your-key-here
   ```
   (Other variables already have defaults for Docker.)

4. **Start all services**
   ```bash
   docker compose up --build
   ```
   First run may take a few minutes to build images and start PostgreSQL.

5. **Open the app**
   - **Web app:** http://localhost:3000  
   - **API docs:** http://localhost:8000/docs  
   - **Health check:** http://localhost:8000/health  

6. **Use the app**
   - Register or log in at http://localhost:3000  
   - Upload a CV (PDF or DOCX)  
   - Click **“Seed sample jobs”** on the dashboard (dev only)  
   - View job matches, open a match, then **“Prepare for interview”**  

To stop: `Ctrl+C`, then `docker compose down` if you want to remove containers.

---

### Option B: Run locally (backend + frontend + PostgreSQL)

**Prerequisites:** Python 3.11+, Node 18+, PostgreSQL 15, and an OpenAI API key.

#### Step 1: Start PostgreSQL and create the database

Make sure PostgreSQL is running, then create the database:

```bash
# macOS (Homebrew)
brew services start postgresql@15
createdb jobmatch

# Or with Docker (only the database)
docker compose up -d db
# Then create DB (if not auto-created):
docker compose exec db psql -U jobmatch -d postgres -c "CREATE DATABASE jobmatch;"
```

#### Step 2: Backend setup

```bash
cd job-match-platform/backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set at least:

- **DATABASE_URL** – PostgreSQL URL with async driver, e.g.  
  `postgresql+asyncpg://youruser:yourpassword@localhost:5432/jobmatch`  
  (Use your OS username if no password, or `postgresql+asyncpg://postgres:postgres@localhost:5432/jobmatch` if you use the default `postgres` user.)
- **JWT_SECRET** – Any string at least 32 characters (or keep the default for local dev).
- **OPENAI_API_KEY** – Your OpenAI API key (required for CV and interview prep).

Run the database migrations (use the same host/user/password as above, with a **sync** URL for `psql`):

```bash
# If your DATABASE_URL is postgresql+asyncpg://user:pass@localhost:5432/jobmatch
# use this for psql (no +asyncpg):
psql postgresql://youruser:yourpassword@localhost:5432/jobmatch -f database/migrations/001_initial_schema.sql
```

Start the backend:

```bash
PYTHONPATH=. uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

You should see “Application startup complete”. API docs: http://localhost:8000/docs  

If you see “Database connection failed at startup”, check that PostgreSQL is running and `DATABASE_URL` is correct.

#### Step 3: Frontend setup

In a **new terminal**:

```bash
cd job-match-platform/frontend
npm install
npm run dev
```

Open http://localhost:3000 in your browser. The dev server proxies `/api` to the backend at port 8000.

#### Step 4: Use the app

1. Register or log in.  
2. Upload a CV (PDF or DOCX).  
3. On the dashboard, click **“Seed sample jobs”** so you have jobs to match against.  
4. View matches, open one, then **“Prepare for interview”** to generate and view prep questions.

---

## Environment variables (backend)

| Variable | Description | Default (Docker) |
|----------|-------------|------------------|
| `DATABASE_URL` | PostgreSQL URL; must use `postgresql+asyncpg://` for the app | `postgresql+asyncpg://jobmatch:jobmatch@db:5432/jobmatch` |
| `JWT_SECRET` | Secret for signing JWTs (min 32 chars) | Set in `.env.example` |
| `OPENAI_API_KEY` | Required for CV parsing and interview prep | **You must set this** |
| `REDIS_URL` | Redis (optional) | `redis://redis:6379/0` (Docker) |
| `CORS_ORIGINS` | Allowed frontend origins (JSON array) | `["http://localhost:3000"]` |
| `ENVIRONMENT` | `development` or `production` | `development` |

See `backend/.env.example` for all options.

---

## Project structure

```
job-match-platform/
├── backend/                 # FastAPI API
│   ├── src/
│   │   ├── api/routes/      # auth, profile, jobs, matches, interviews, progress
│   │   ├── services/        # cv_parser, scraper, llm, matching
│   │   ├── models/          # SQLAlchemy models
│   │   └── database/       # connection, migrations
│   ├── database/migrations/ # SQL schema
│   └── requirements.txt
├── frontend/                # React + Vite + TypeScript
│   ├── src/pages/           # Login, Dashboard, Job details, Interview prep, Progress
│   └── package.json
├── docker-compose.yml       # backend, frontend, db, redis
└── README.md
```

---

## API overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register |
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/refresh` | Refresh access token |
| GET | `/api/profile/me` | Get my profile (auth) |
| PUT | `/api/profile/me` | Update profile (auth) |
| POST | `/api/profile/cv-upload` | Upload CV – PDF/DOCX (auth) |
| GET | `/api/jobs/matches` | List job matches (auth) |
| GET | `/api/jobs/{job_id}` | Job details (auth) |
| POST | `/api/jobs/seed-jobs` | Seed sample jobs (dev only, auth) |
| POST | `/api/interviews/prep/{match_id}` | Create interview prep kit (auth) |
| GET | `/api/interviews/prep/{prep_id}` | Get prep kit (auth) |
| POST | `/api/interviews/start` | Start practice session (auth) |
| GET | `/api/progress/stats` | Progress stats (auth) |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger API docs |

---

## Troubleshooting

- **“Connection refused” at startup**  
  PostgreSQL is not running or not reachable. Start Postgres and check `DATABASE_URL` (host, port, user, password, database name).

- **404 on http://localhost:8000/**  
  The backend is API-only. Use http://localhost:8000/docs for the API, and http://localhost:3000 for the web app (with frontend running).

- **CV upload or “Prepare for interview” fails**  
  Ensure `OPENAI_API_KEY` is set in `backend/.env`. These features call the OpenAI API.

- **No job matches**  
  Seed sample jobs from the dashboard (“Seed sample jobs” button) or run the job scraper so the database has jobs.

- **Frontend can’t reach API**  
  With local frontend (`npm run dev`), requests to `/api` are proxied to port 8000. With Docker, the frontend container proxies to the backend service. Ensure the backend is running on port 8000.

---

## License

MIT.
