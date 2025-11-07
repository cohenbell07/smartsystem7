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

# Optional: GitHub integration for agent repositories
GITHUB_TOKEN=ghp_...

# Optional: Hybrid agent generation strategy (default: hybrid)
BUILD_STRATEGY=hybrid  # Options: hybrid, claude-only, gpt-only

# Optional: Email notifications
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_HOST=smtp.gmail.com

# Optional: Discord notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

**Note**: You can also configure API keys through the UI when running agents. The system will prompt you if keys are missing.

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

## New Features: Zero-Fail Orchestration & GitHub Integration

### Zero-Fail API Key Collection

The system now handles missing API keys gracefully:

1. **Run an agent** - If required keys are missing, you'll see a modal instead of an error
2. **Add keys on-the-fly** - Enter your API keys directly in the UI
3. **Auto-retry** - Keys are saved to `.env` and the run automatically retries

**Supported keys:**
- `OPENAI_API_KEY` - OpenAI models (GPT-4, GPT-4o-mini)
- `ANTHROPIC_API_KEY` - Anthropic models (Claude 3.5 Sonnet/Haiku)
- `GITHUB_TOKEN` - GitHub repository creation
- `SERPAPI_KEY` / `BING_SEARCH_API_KEY` - Web search (at least one required)
- `SMTP_USER`, `SMTP_PASSWORD` - Email notifications

### GitHub Integration for Agents

Each agent can have its own GitHub repository:

1. **Navigate to an agent** in the "My Agents" section
2. **Click "Files" tab** → "Create GitHub Repository"
3. **View generated code** - See the agent specification and generated files
4. **Open on GitHub** - Link directly to the repository
5. **Local sync** - Files are stored locally in `./repos/<agent_id>/`

**Requirements:**
- Set `GITHUB_TOKEN` in `.env` or add it via the UI
- Token needs `repo` scope for creating repositories

### Multi-Agent Orchestration

Coordinate multiple agents to work on complex tasks:

1. **Visit /orchestrations** page
2. **Select agents** - Choose 2+ agents from your portfolio
3. **Choose strategy:**
   - **Manager-Led**: AI manager coordinates and delegates (default)
   - **Sequential**: Agents run one after another, passing results
   - **Parallel**: All agents execute simultaneously
4. **Enter prompt** - Describe the collaborative task
5. **Monitor progress** - Watch per-agent progress bars and logs

**Example use cases:**
- Research + Coding: One agent researches, another implements
- Analysis + Reporting: Analyze data, then generate report
- Planning + Execution: Plan project, then execute steps

### Cost & Token Tracking

All runs now track:
- **Total Cost**: USD spent on API calls
- **Total Tokens**: Input + output tokens used
- **Per-Step Breakdown**: See cost/tokens per workflow step

View in:
- Agent run details (Logs & Results tab)
- Orchestration status page
- Run history

---

## Running Database Migrations

After pulling new changes, always run migrations:

```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

This ensures your database schema is up-to-date with the latest features.

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

5. **Prompt a Saved Agent**
   - Go to "My Agents" page
   - Click on any saved agent
   - Navigate to "Run" tab
   - Enter a prompt (e.g., "Analyze the market for design tools in 2024")
   - Click "Run with Prompt"
   - View logs and results in real-time

---

## How Agent Builder Uses Claude + GPT Together

The Agent Factory uses a **hybrid generation strategy** that leverages the strengths of both Claude and GPT:

### Generation Flow

1. **Claude (Planning & Decomposition)**
   - Uses Claude Sonnet or Haiku for high-level planning
   - Breaks down tasks into logical steps
   - Identifies required tools and APIs
   - Provides the "why" and architecture rationale

2. **GPT (Structured Code Emission)**
   - Uses GPT-4o-mini or GPT-4.1-mini for code generation
   - Creates JSON schemas and typed function signatures
   - Generates deterministic tool contracts with Pydantic models
   - Provides the "what" and implementation details

3. **Claude (Review & Refactor)**
   - Reviews generated code for clarity
   - Adds comprehensive docstrings
   - Suggests refactorings for better structure
   - Does NOT change function signatures (maintains contracts)

### Configuration

Control the build strategy with the `BUILD_STRATEGY` environment variable in `.env`:

```bash
# Default: Use Claude for planning, GPT for code, Claude for review
BUILD_STRATEGY=hybrid

# Use only Claude (requires ANTHROPIC_API_KEY)
BUILD_STRATEGY=claude-only

# Use only GPT (requires OPENAI_API_KEY)
BUILD_STRATEGY=gpt-only
```

### Benefits

- **Better Planning**: Claude excels at decomposition and architectural thinking
- **Cleaner Code**: GPT provides structured, deterministic code generation
- **Quality Assurance**: Claude's review adds documentation and catches issues
- **Flexibility**: Fallback strategies if one provider is unavailable

---

## Prompting Saved Agents

Once an agent is saved, you can interact with it in multiple ways:

### Method 1: Direct Prompt (Agent Manager Runtime)

The agent uses the **Agent Manager runtime** which provides:
- **Multi-agent orchestration** with sub-agents (Planner, Researcher, Implementer, etc.)
- **Semantic memory recall** from previous runs
- **Dynamic task execution** based on the prompt

**Example:**
```json
POST /api/agents/{agent_id}/run
{
  "prompt": "Analyze the latest trends in AI agents"
}
```

**Frontend:** Go to agent detail page → "Run" tab → Enter prompt → Click "Run with Prompt"

### Method 2: Direct Inputs (Graph Execution)

For traditional graph-based execution with structured inputs:

**Example:**
```json
POST /api/agents/{agent_id}/run
{
  "inputs": {
    "query": "market research data",
    "filters": ["2024", "SaaS"]
  }
}
```

### API Endpoints

- `POST /api/agents/{agent_id}/run` - Run saved agent (prompt or inputs)
- `POST /api/agents/{agent_id}/prompt` - Run with prompt (legacy, use above)
- `GET /api/runs/{run_id}` - Get run status, logs, and results

### Key Validation

Before running an agent, the system automatically validates that all required API keys are present:

- **LLM Keys**: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- **Tool Keys**: `GITHUB_TOKEN`, `SERPAPI_KEY`, `SNYK_TOKEN`, etc.
- **Missing Keys**: UI shows which keys are missing with setup instructions

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
