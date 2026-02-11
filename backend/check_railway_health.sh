#!/bin/bash
# Check Railway backend health and provide diagnostics

RAILWAY_URL="https://jobmatchai-production-ec30.up.railway.app"

echo "🔍 Checking Railway Backend Health..."
echo "URL: $RAILWAY_URL"
echo ""

# Check health endpoint
echo "1️⃣ Testing /health endpoint..."
HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$RAILWAY_URL/health" 2>&1)

if [ "$HEALTH_RESPONSE" = "200" ]; then
    echo "✅ Backend is healthy!"
    echo ""
    echo "Testing CORS for OPTIONS request..."
    curl -X OPTIONS "$RAILWAY_URL/api/auth/register" \
        -H "Origin: https://job-match-ai-vert.vercel.app" \
        -H "Access-Control-Request-Method: POST" \
        -H "Access-Control-Request-Headers: Content-Type" \
        -v
else
    echo "❌ Backend is not responding (Status: $HEALTH_RESPONSE)"
    echo ""
    echo "Common causes:"
    echo "  1. Service not deployed or crashed"
    echo "  2. Database connection failed"
    echo "  3. Missing environment variables"
    echo ""
    echo "👉 Next steps:"
    echo "  1. Go to Railway dashboard: https://railway.app/dashboard"
    echo "  2. Check Backend service deployment logs"
    echo "  3. Verify DATABASE_URL is set to: \${{Postgres.DATABASE_URL}}"
    echo "  4. Ensure CORS_ORIGINS includes: https://job-match-ai-vert.vercel.app"
fi

echo ""
echo "2️⃣ Testing API docs endpoint..."
curl -I "$RAILWAY_URL/docs" --max-time 10 2>&1 | head -10
