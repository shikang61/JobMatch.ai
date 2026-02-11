# Fix 502 Bad Gateway Error on Railway

## Problem
Your backend is crashing with: `Could not parse SQLAlchemy URL from given URL string`

This means **DATABASE_URL is not properly set in Railway**.

## Solution Checklist

### ✅ Step 1: Check Postgres Service
- [ ] Go to https://railway.app/dashboard
- [ ] Open your project
- [ ] Verify you have a **Postgres** service running
- [ ] If not, create one: "+ New" → "Database" → "Add PostgreSQL"

### ✅ Step 2: Link Services
- [ ] Click on **Backend** service
- [ ] Go to **Settings** → **Service Links**
- [ ] Make sure **Postgres** is linked
- [ ] If not: Click "Link Service" → Select Postgres

### ✅ Step 3: Fix DATABASE_URL Variable

**CRITICAL**: The DATABASE_URL must be a **reference** to the Postgres service, not a hardcoded string.

1. In **Backend** service → **Variables** tab
2. Delete existing `DATABASE_URL` if it exists
3. Add it properly:

**Method A (Recommended)**: Use Reference
- Click "Add Reference"
- Select: Postgres service
- Select: DATABASE_URL variable
- Result: `${{Postgres.DATABASE_URL}}`

**Method B**: Manual Entry
- Variable: `DATABASE_URL`
- Value: `${{Postgres.DATABASE_URL}}`
- ⚠️ Type it EXACTLY like that (with double curly braces)

### ✅ Step 4: Verify Other Variables

Make sure these exist in **Backend** service variables:

```bash
CORS_ORIGINS=["https://job-match-ai-vert.vercel.app"]
JWT_SECRET=<your-jwt-secret-from-env-file>
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_MODEL=gpt-4o-mini
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### ✅ Step 5: Trigger Redeploy

- Railway should auto-redeploy after changing variables
- Or manually: Click "Deploy" button
- Wait 2-3 minutes for deployment

### ✅ Step 6: Check Deployment Logs

1. Go to **Deployments** tab
2. Click latest deployment
3. Watch the logs

**Success looks like:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Connecting to database: xxxxx.railway.app:5432/railway
INFO:     Database connection verified
INFO:     Application started
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Failure looks like:**
```
ValueError: DATABASE_URL is not properly configured
```
→ Go back to Step 3 and fix the variable

### ✅ Step 7: Test the Endpoint

Run from your terminal:
```bash
./backend/check_railway_health.sh
```

Or test manually:
```bash
curl https://jobmatchai-production-ec30.up.railway.app/health
```

Expected response:
```json
{"status":"ok"}
```

## Common Issues

### Issue: "Could not parse SQLAlchemy URL"
**Cause**: DATABASE_URL is not set or is invalid
**Fix**: Follow Step 3 above - must use `${{Postgres.DATABASE_URL}}`

### Issue: "Connection refused"
**Cause**: Postgres service not running or not linked
**Fix**: Follow Steps 1-2 above

### Issue: Still getting 502
**Cause**: Backend not redeployed after fixing variables
**Fix**: Manually trigger redeploy in Railway dashboard

### Issue: CORS errors after backend works
**Cause**: CORS_ORIGINS doesn't include your frontend URL
**Fix**: Add `https://job-match-ai-vert.vercel.app` to CORS_ORIGINS

## What I Fixed in the Code

✅ Added better error handling in `backend/src/database/connection.py`
✅ Fixed CORS origins in local `.env` file
✅ Created health check script
✅ Pushed changes to GitHub (Railway will auto-deploy)

## Next Steps After Backend Works

1. Get your backend URL from Railway (e.g., `https://jobmatchai-production-ec30.up.railway.app`)
2. Go to Vercel dashboard
3. Update frontend env variable:
   - Name: `VITE_API_URL`
   - Value: `https://YOUR-BACKEND-URL.railway.app/api`
4. Redeploy frontend

---

**Need more help?** Share your Railway deployment logs and I can diagnose further.
