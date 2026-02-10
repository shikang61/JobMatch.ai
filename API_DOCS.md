# Job Match Platform – API Documentation

Base URL: `/api` (e.g. `http://localhost:8000/api`).

## Authentication

- **Register**: `POST /api/auth/register`  
  Body: `{ "email": "user@example.com", "password": "SecurePass1" }`  
  Returns: `{ "access_token", "refresh_token", "token_type": "bearer", "expires_in" }`

- **Login**: `POST /api/auth/login`  
  Body: `{ "email", "password" }`  
  Returns: same as register.

- **Refresh**: `POST /api/auth/refresh`  
  Body: `{ "refresh_token": "..." }`  
  Returns: new access and refresh tokens.

Use the access token in the header: `Authorization: Bearer <access_token>`.

Rate limits: auth endpoints 5 requests per 15 minutes per IP; API 100 per minute per user.

## Profile

- **Get profile**: `GET /api/profile/me` (auth)
- **Update profile**: `PUT /api/profile/me` (auth)  
  Body: `{ "full_name": "Optional Name" }`
- **Upload CV**: `POST /api/profile/cv-upload` (auth)  
  Content-Type: `multipart/form-data`, field: `file` (PDF or DOCX, max 5MB)

## Jobs and matches

- **List my matches**: `GET /api/jobs/matches` (auth)  
  Returns: `{ "matches": [...], "total": N }`. Each match has `id`, `job_id`, `compatibility_score`, `match_details`, `job_title`, `company_name`, `location`, `posted_date`.

- **Get job**: `GET /api/jobs/{job_id}` (auth)
- **Seed sample jobs** (dev only): `POST /api/jobs/seed-jobs` (auth)

## Interview prep

- **Create prep kit**: `POST /api/interviews/prep/{match_id}` (auth)  
  Returns: `{ "id", "job_match_id", "questions", "company_insights", "tips" }`.

- **Get prep kit**: `GET /api/interviews/prep/{prep_id}` (auth)
- **Start session**: `POST /api/interviews/start` (auth)  
  Body: `{ "prep_kit_id": "uuid" }`  
  Returns: `{ "session_id", "prep_kit_id", "status" }`.

## Progress

- **Stats**: `GET /api/progress/stats` (auth)  
  Returns: `{ "sessions_completed", "average_score", "total_questions_practiced", "readiness_percentage" }`.

## Errors

- `400` – Bad request (validation, business rule).
- `401` – Unauthorized (missing or invalid token).
- `404` – Resource not found.
- `422` – Validation error (body/query).
- `429` – Rate limit exceeded.
- `500` – Server error.
- `503` – External service (e.g. LLM) unavailable.

OpenAPI (Swagger): `GET /docs`, ReDoc: `GET /redoc`.
