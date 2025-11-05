# Running Agent Factory Locally

Complete guide to get Agent Factory running on your machine in under 5 minutes.

## Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **Redis** (optional, for background jobs)
- **Git**

## Quick Start (macOS/Linux)

### 1. Clone & Navigate

```bash
git clone <your-repo-url> agent-factory
cd agent-factory
```

### 2. Set Up Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and add **at least one LLM API key**:

```bash
# Required (at least one)
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...

# Search API (recommended - SerpAPI is default with Bing engine)
SERPAPI_KEY=...
# Legacy option (for direct Bing API v7 access)
BING_SEARCH_API_KEY=...
```

### 3. Install Dependencies

```bash
make install
```

This will:
- Create Python virtual environment
- Install backend dependencies
- Install Playwright browsers
- Install frontend dependencies

### 4. Initialize Database

```bash
make db
```

### 5. Configure Vector Store (Optional)

The system uses ChromaDB for vector-based agent memory. It's local, free, and auto-creates on first use.

Add to `.env` to customize the storage location:

```bash
CHROMA_DB_PATH=~/Documents/smartsystem7/chroma_data
```

**Note**:
- Folder auto-created on first use
- Delete the folder to reset memory
- Default location is `./chroma_data` if not specified

### 6. Seed Demo Data (Optional)

```bash
make seed
```

### 7. Run Everything

```bash
make dev
```

This starts:
- **Backend API**: http://localhost:8000
- **Frontend**: http://localhost:3000
- **Worker**: Background job processor

### 8. Open Your Browser

Visit http://localhost:3000 and ask your first question!

---

## Manual Setup (if Makefile doesn't work)

### Backend

```bash
cd backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright
playwright install chromium

# Run migrations
alembic upgrade head

# Seed database (optional)
python -m app.seed

# Start API
uvicorn app.main:app --reload --port 8000
```

### Worker (separate terminal)

```bash
cd backend
source venv/bin/activate
python -m workers.runner
```

### Frontend (separate terminal)

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

---

## Verify Installation

### 1. Check Backend

Visit http://localhost:8000 - should see:

```json
{
  "message": "Agent Factory API",
  "version": "0.1.0",
  "status": "running"
}
```

### 2. Check API Docs

Visit http://localhost:8000/docs for interactive API documentation.

### 3. Check Frontend

Visit http://localhost:3000 - should see the "Ask a Business Question" page.

---

## Common Issues

### Issue: `playwright install` fails

**Solution:**

```bash
cd backend
source venv/bin/activate
playwright install-deps  # Install system dependencies
playwright install chromium
```

### Issue: Port 8000 or 3000 already in use

**Solution:**

```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Kill process on port 3000
lsof -ti:3000 | xargs kill -9
```

Or change ports:

```bash
# Backend
uvicorn app.main:app --reload --port 8001

# Frontend (in frontend/package.json)
"dev": "next dev -p 3001"
```

### Issue: Database migration errors

**Solution:**

```bash
cd backend
rm agent_factory.db  # Delete old database (DEV ONLY!)
alembic upgrade head
python -m app.seed
```

### Issue: `No LLM configured` error

**Solution:**

Make sure you've set at least one API key in `.env`:

```bash
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...
```

Then restart the backend.

### Issue: Search returns no results

**Solution:**

Add a search API key to `.env`:

```bash
SERPAPI_KEY=...
```

The system now uses SerpAPI with Bing engine by default. Without this, the research phase will have limited data.

---

## Development Commands

```bash
# Format code
make fmt

# Run linters
make lint

# Run tests
make test

# Run only backend tests
make test-backend

# Clean generated files
make clean
```

---

## Testing the Full Flow

1. **Ask a Question**
   - Go to http://localhost:3000
   - Enter: "What's the viability of a SaaS tool for freelance designers?"
   - Click "Start Research"

2. **Watch Progress**
   - You'll be redirected to the project page
   - Status updates every 3 seconds
   - Research → Analyzing → Spec Generated

3. **Review Results**
   - See Viability Score (0-100)
   - Read Research Brief with citations
   - Review Proposed Agent spec

4. **Save Agent** (Optional)
   - Enter a name (e.g., "DesignToolAnalyzer")
   - Click "Save Agent"
   - Find it in "My Agents" page

---

## Production Deployment

See [README.md](./README.md#production-deployment) for deployment guides:
- Backend: Railway, Render, Fly.io
- Frontend: Vercel, Netlify
- Database: PostgreSQL

---

## Getting API Keys

### OpenAI
1. Go to https://platform.openai.com/api-keys
2. Create new secret key
3. Copy to `.env` as `OPENAI_API_KEY=sk-...`

### Anthropic
1. Go to https://console.anthropic.com/
2. Create new API key
3. Copy to `.env` as `ANTHROPIC_API_KEY=sk-ant-...`

### SerpAPI (Recommended - Default)
1. Go to https://serpapi.com/
2. Sign up for free tier (100 searches/month)
3. Copy key to `.env` as `SERPAPI_KEY=...`
4. Uses Bing search engine by default

### Bing Search (Legacy)
1. Go to Azure Portal
2. Create Bing Search v7 resource
3. Copy key to `.env` as `BING_SEARCH_API_KEY=...`
4. Add `SEARCH_PROVIDER=bing` to `.env`

---

## Need Help?

- **Documentation**: See [README.md](./README.md)
- **Issues**: https://github.com/yourusername/agent-factory/issues
- **API Docs**: http://localhost:8000/docs (when running)

---

## What's Next?

1. ✅ Ask questions and get viability scores
2. ✅ Save agents to your portfolio
3. 🚧 Run saved agents with new inputs (coming soon)
4. 🚧 Approval gates for risky actions (coming soon)
5. 🚧 Email/Discord notifications (configure in Settings)

Enjoy building with Agent Factory! 🏭
