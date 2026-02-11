#!/bin/bash
# This script will help you create and deploy the backend service

echo "========================================"
echo "Creating Backend Service on Railway"
echo "========================================"
echo ""

cd "$(dirname "$0")/backend"

echo "Step 1: Linking to Railway project..."
railway link --project 882b8b9f-a006-467a-9292-3e4fb01e7d11 --environment production 2>/dev/null

echo ""
echo "Step 2: Attempting to deploy backend..."
echo ""
echo "⚠️  If this fails, you MUST use the Railway Dashboard!"
echo ""

# Try to deploy - this might create a new service
railway up --detach

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Backend deployed!"
    echo ""
    echo "Now run: railway domain"
    echo "To get your backend URL"
else
    echo ""
    echo "❌ CLI deploy failed. Use Railway Dashboard instead:"
    echo ""
    echo "1. Go to: https://railway.app/project/882b8b9f-a006-467a-9292-3e4fb01e7d11"
    echo "2. Click '+ New' button"
    echo "3. Select 'GitHub Repo'"
    echo "4. Choose your repository"
    echo "5. Set Root Directory to: backend"
    echo "6. Add environment variables"
fi
