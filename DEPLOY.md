# 🚀 Deploy to Railway.app (100% Free, No Credit Card)

## Why Railway?
- ✅ **Completely FREE** for hobby projects (no credit card required)
- ✅ **500 hours/month** of runtime (enough for small apps)
- ✅ **Built-in PostgreSQL** database (free)
- ✅ **Supports Docker** natively
- ✅ **Auto-deploys** from GitHub

---

## 📋 Step-by-Step Deployment

### 1️⃣ Push Code to GitHub
```bash
git add .
git commit -m "Ready for Railway deployment"
git push origin main
```

### 2️⃣ Create Railway Account
1. Go to [railway.app](https://railway.app)
2. Click **"Start a New Project"**
3. Sign up with GitHub (no credit card needed!)

### 3️⃣ Deploy Backend
1. Click **"Deploy from GitHub repo"**
2. Select your `Handbook-Project` repository
3. Railway will auto-detect the Dockerfile
4. Click **"Add variables"** and add:
   - `OPENAI_API_KEY` = your OpenAI API key
   - `SECRET_KEY` = any random string (e.g., `mysecretkey123`)

### 4️⃣ Add PostgreSQL Database
1. In your Railway project, click **"New"** → **"Database"** → **"PostgreSQL"**
2. Railway automatically connects it via `DATABASE_URL` environment variable
3. No configuration needed! ✨

### 5️⃣ Get Your Backend URL
1. In Railway dashboard, go to your backend service
2. Click **"Settings"** → **"Generate Domain"**
3. Copy the URL (e.g., `https://your-app.up.railway.app`)

### 6️⃣ Update Frontend API URL
Update `frontend/lib/api.ts`:
```typescript
const API_BASE_URL = 'https://YOUR-BACKEND-URL.up.railway.app';
```

### 7️⃣ Deploy Frontend (Optional - or use Vercel)
Railway can also host the frontend, or you can use **Vercel** (also free):
- [Vercel Deployment](https://vercel.com) - Just connect GitHub, it auto-detects Next.js!

---

## 🎉 That's It!
Your app is now live at:
- **Backend**: `https://your-backend.up.railway.app`
- **Frontend**: Deploy to Vercel for free Next.js hosting

## 💡 Railway Free Tier Limits
- **500 hours/month** execution time
- **512 MB RAM** per service
- **1 GB storage** for database
- Perfect for side projects and demos!

## 🔧 Troubleshooting
- **Can't connect to database?** Railway auto-injects `DATABASE_URL`, make sure backend is reading it
- **CORS errors?** Backend already includes Railway URLs in CORS config
- **API not responding?** Check Railway logs in dashboard under your service

---

## 🆓 Alternative Free Hosting Options

### Frontend:
- **Vercel** - Best for Next.js (unlimited projects, auto-deploy from GitHub)
- **Netlify** - Great for static sites
- **Cloudflare Pages** - Fast global CDN

### Backend + Database:
- **Railway** (recommended) - 500 hrs/month, includes PostgreSQL
- **Fly.io** - Free tier: 3 VMs, 3 GB storage
- **Koyeb** - Free tier with basic PostgreSQL

All require **NO credit card** for basic tier! 🎉
