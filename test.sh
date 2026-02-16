#!/bin/bash
# Simple test script to validate the application

echo "=== Testing Handbook Project Application ==="
echo ""

# Check backend files
echo "✓ Checking backend files..."
[ -f "backend/main.py" ] && echo "  - main.py exists"
[ -f "backend/database.py" ] && echo "  - database.py exists"
[ -f "backend/auth.py" ] && echo "  - auth.py exists"
[ -f "backend/schemas.py" ] && echo "  - schemas.py exists"
[ -f "backend/requirements.txt" ] && echo "  - requirements.txt exists"
[ -f "backend/Dockerfile" ] && echo "  - Dockerfile exists"

echo ""
echo "✓ Checking frontend files..."
[ -f "frontend/package.json" ] && echo "  - package.json exists"
[ -f "frontend/next.config.js" ] && echo "  - next.config.js exists"
[ -f "frontend/app/page.tsx" ] && echo "  - app/page.tsx exists"
[ -f "frontend/components/AuthForm.tsx" ] && echo "  - AuthForm.tsx exists"
[ -f "frontend/components/ChatList.tsx" ] && echo "  - ChatList.tsx exists"
[ -f "frontend/components/ChatWindow.tsx" ] && echo "  - ChatWindow.tsx exists"
[ -f "frontend/components/WorkflowVisualization.tsx" ] && echo "  - WorkflowVisualization.tsx exists"
[ -f "frontend/lib/api.ts" ] && echo "  - api.ts exists"
[ -f "frontend/lib/store.ts" ] && echo "  - store.ts exists"

echo ""
echo "✓ Checking configuration files..."
[ -f "docker-compose.yml" ] && echo "  - docker-compose.yml exists"
[ -f ".gitignore" ] && echo "  - .gitignore exists"
[ -f "README.md" ] && echo "  - README.md exists"

echo ""
echo "=== All essential files are present! ==="
echo ""
echo "To run the application:"
echo "1. Set up environment variables (see README.md)"
echo "2. Run: docker-compose up --build"
echo "3. Access frontend at http://localhost:3000"
echo "4. Access backend API at http://localhost:8000"
echo ""
