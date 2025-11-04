# Agent Factory 🏭

A self-assembling AI agent platform that researches business questions, evaluates viability, and automatically generates custom agents to solve specific problems.

## Overview

Agent Factory is a production-grade monorepo that:
1. **Researches** - Crawls 50+ sources for comprehensive market research
2. **Analyzes** - Produces a Business Viability Score (0-100) with sensitivity analysis
3. **Designs** - Generates an AgentSpec defining a custom agent's architecture
4. **Builds** - Assembles agents using LangGraph with required tools and APIs
5. **Executes** - Runs agents with approval gates and progress tracking
6. **Saves** - Stores successful agents for reuse in your portfolio

## Architecture

```
agent-factory/
├── backend/          # Python FastAPI + LangGraph
│   ├── app/
│   │   ├── models.py          # SQLModel data models
│   │   ├── main.py            # FastAPI routes
│   │   ├── research/          # Multi-source research pipeline
│   │   ├── agents/            # Agent factory & graphs
│   │   └── services/          # LLM router, approvals, notifications
│   ├── workers/               # Background job runner
│   ├── tests/                 # Unit tests
│   └── prompts/               # LLM prompts as markdown
└── frontend/         # Next.js + Tailwind + shadcn/ui
    ├── app/                   # App router pages
    ├── components/            # React components
    └── lib/                   # Utilities
```

## Tech Stack

**Backend:**
- Python 3.11, FastAPI, LangGraph
- OpenAI + Anthropic SDKs for LLM cooperation
- Playwright for browser automation
- BeautifulSoup4 + Trafilatura for content extraction
- SQLite (dev) via SQLModel, Alembic migrations
- RQ for background job processing

**Frontend:**
- Next.js 14 (App Router)
- Tailwind CSS + shadcn/ui
- SWR for data fetching
- TypeScript

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL (optional, SQLite for dev)

### Installation

```bash
# 1. Clone and enter directory
git clone <repo-url> agent-factory
cd agent-factory

# 2. Install dependencies
make install

# 3. Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# 4. Initialize database
make db

# 5. Run development servers
make dev
```

This starts:
- Backend API: http://localhost:8000
- Frontend: http://localhost:3000
- Worker: background job processor

### API Keys Required

```bash
# LLM Providers (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Search (at least one required)
BING_SEARCH_API_KEY=...
SERPAPI_KEY=...

# Optional integrations
GITHUB_TOKEN=ghp_...
SMTP_HOST=smtp.gmail.com
SMTP_USER=you@gmail.com
SMTP_PASSWORD=...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

## Usage

### 1. Ask a Business Question

Visit http://localhost:3000 and enter a question:

> "What's the market viability of an AI-powered meal planning app for busy parents?"

### 2. Review Research & Viability

The system will:
- Search 50+ sources (academic papers, news, market reports)
- Crawl and extract content
- Deduplicate and synthesize findings
- Calculate a **Business Viability Score** with rationale

### 3. Approve Agent Spec

Review the proposed agent's:
- Required tools and APIs
- Test plan
- Success criteria
- Approval gates for risky actions

### 4. Watch Agent Execute

Monitor real-time logs as the agent:
- Gathers data
- Performs analysis
- Generates artifacts (code, reports, designs)
- Requests approvals for sensitive operations

### 5. Save to Portfolio

Save successful agents to reuse with new inputs from the "My Agents" page.

## 💰 Cost Tracking

Agent Factory includes real-time cost estimation and tracking for all LLM API calls:

### Features

- **Pre-Run Cost Estimates**: Before executing an agent, see a breakdown of estimated costs by model
- **Live Pricing**: Automatically fetches current pricing for OpenAI and Anthropic models
- **Token Tracking**: Monitors actual token usage (input + output) during execution
- **Cost Breakdown**: Detailed cost information per model and execution step
- **Historical Data**: View estimated vs. actual costs for all past runs

### How It Works

1. **Click "Run Agent"** → The system fetches current pricing and estimates tokens needed
2. **Review Cost Estimate** → A modal shows the breakdown by model (e.g., GPT-4o, Claude 3.5 Sonnet)
3. **Approve & Run** → The agent executes and tracks actual token usage
4. **View Results** → See actual cost compared to estimate in the run details

### Example Cost Estimate

```
Total Estimated Cost: $0.0234

Breakdown:
- gpt-4o (planning)       120,000 tokens → $0.0145
- claude-3-5-sonnet (exec) 60,000 tokens → $0.0089

Warning: Estimate only - actual costs may vary by 30-50%
```

### API Usage

```bash
# Get current pricing
curl http://localhost:8000/api/pricing

# Estimate cost before running
curl -X POST http://localhost:8000/api/estimate-cost \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "inputs": {}}'

# Check actual cost after run
curl http://localhost:8000/api/runs/123
```

### Cost Tracking in Code

The pricing service in `backend/app/services/pricing.py` provides:

- `estimate_run_cost(agent_spec, input_text)` - Estimate cost before execution
- `calculate_actual_cost(usage_data, model)` - Calculate actual cost from API response
- `get_current_pricing()` - Get live pricing for all models

Costs are automatically tracked in the database `runs` table with fields:
- `cost_estimate` - Estimated cost in USD
- `actual_cost` - Actual cost after execution
- `total_tokens` - Total tokens used
- `cost_breakdown` - JSON with detailed breakdown

## Commands

```bash
make install      # Install all dependencies
make dev          # Run backend + frontend + worker
make backend      # Run backend only
make frontend     # Run frontend only
make worker       # Run worker only
make db           # Run database migrations
make seed         # Seed database with demo agent
make test         # Run all tests
make test-backend # Run backend tests only
make fmt          # Format code (black, ruff, prettier)
make lint         # Lint code
make clean        # Remove generated files
```

## API Endpoints

```
POST   /api/ask              - Start new research project
GET    /api/projects/:id     - Get project status & logs
POST   /api/estimate-cost    - Estimate cost before running agent
POST   /api/run              - Execute an agent spec
POST   /api/approve          - Approve/reject gate action
POST   /api/save-agent       - Save agent to portfolio
GET    /api/agents           - List saved agents
GET    /api/agents/:id       - Get agent details
POST   /api/agents/:id/run   - Run saved agent with new inputs
GET    /api/runs/:id         - Get run details including costs
GET    /api/pricing          - Get current LLM pricing
GET    /api/settings/secrets - Get secret placeholders
PUT    /api/settings/secrets - Update secrets
```

## Development

### Project Structure

```
backend/
├── app/
│   ├── models.py              # SQLModel models
│   ├── main.py                # FastAPI app & routes
│   ├── database.py            # DB connection
│   ├── research/
│   │   ├── search.py          # Bing/SERP search
│   │   ├── crawl.py           # Content extraction
│   │   ├── dedupe.py          # URL + content deduplication
│   │   ├── synthesize.py      # LLM synthesis with citations
│   │   └── viability.py       # Business viability scoring
│   ├── agents/
│   │   ├── factory.py         # AgentSpec -> LangGraph
│   │   ├── tools/
│   │   │   ├── browser.py     # Playwright automation
│   │   │   ├── github_ops.py  # GitHub operations
│   │   │   ├── emailer.py     # Email sending
│   │   │   └── vector_memory.py # Chroma vector store
│   │   └── graphs/
│   │       ├── video_generation.py
│   │       ├── outreach.py
│   │       └── site_builder.py
│   └── services/
│       ├── llm_router.py      # GPT + Claude cooperation
│       ├── approvals.py       # Approval gate system
│       ├── notify.py          # Email + Discord notifications
│       ├── secrets.py         # Secret management
│       └── pricing.py         # Cost estimation & tracking
├── workers/
│   └── runner.py              # RQ job consumer
├── tests/
│   ├── test_viability.py
│   └── test_factory.py
└── prompts/
    ├── research_synthesis.md
    ├── viability_score.md
    └── agent_spec.md

frontend/
├── app/
│   ├── page.tsx               # Home: Ask question
│   ├── projects/[id]/page.tsx # Project detail
│   ├── agents/page.tsx        # Saved agents list
│   └── settings/page.tsx      # API keys & config
├── components/
│   ├── ui/                    # shadcn/ui components
│   ├── viability-score.tsx
│   ├── agent-spec.tsx
│   ├── live-logs.tsx
│   └── approval-gate.tsx
└── lib/
    ├── api.ts                 # API client
    └── utils.ts               # Helpers
```

### Adding a New Agent Graph

Create a new file in `backend/app/agents/graphs/`:

```python
from langgraph.graph import StateGraph, END
from app.agents.factory import AgentState

def create_my_agent_graph(spec: dict) -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("research", research_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("output", output_node)

    workflow.set_entry_point("research")
    workflow.add_edge("research", "analyze")
    workflow.add_edge("analyze", "output")
    workflow.add_edge("output", END)

    return workflow.compile()
```

Register in `factory.py` to make it discoverable.

### Running Tests

```bash
# All tests
make test

# Backend only
pytest backend/tests -v

# Frontend only
cd frontend && npm test

# With coverage
pytest backend/tests --cov=app --cov-report=html
```

### Database Migrations

```bash
# Create a new migration
cd backend
alembic revision --autogenerate -m "Add new field"

# Run migrations
make db
# or
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Configuration

### Environment Variables

See `.env.example` for all available options:

```bash
# Core
DATABASE_URL=sqlite:///./agent_factory.db
REDIS_URL=redis://localhost:6379
SECRET_KEY=your-secret-key-here

# LLMs
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEFAULT_LLM=gpt-4o-mini  # or claude-3-5-sonnet-20241022

# Search
BING_SEARCH_API_KEY=...
SERPAPI_KEY=...
SEARCH_PROVIDER=bing  # or serpapi

# Notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
DISCORD_WEBHOOK_URL=...

# GitHub
GITHUB_TOKEN=ghp_...

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Switching to PostgreSQL

Update `DATABASE_URL` in `.env`:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/agent_factory
```

Run migrations:

```bash
make db
```

## Production Deployment

### Backend (Railway, Render, Fly.io)

```bash
# Build
docker build -t agent-factory-backend ./backend

# Run
docker run -p 8000:8000 --env-file .env agent-factory-backend
```

### Frontend (Vercel, Netlify)

```bash
cd frontend
npm run build
# Deploy dist/ folder
```

### Environment

Set all required API keys in your platform's environment variables.

### Database

Use PostgreSQL in production. Run migrations on deploy:

```bash
alembic upgrade head
```

## Features

### ✅ Implemented

- [x] Multi-source research pipeline (50+ sources)
- [x] Content crawling & extraction (Playwright + Trafilatura)
- [x] Smart deduplication (URL normalization + simhash)
- [x] LLM synthesis with inline citations
- [x] Business Viability Score (0-100) with sensitivity analysis
- [x] AgentSpec generation from research
- [x] LangGraph agent factory
- [x] Example agent graphs (video, outreach, site builder)
- [x] Approval gates for risky operations
- [x] Email + Discord notifications
- [x] Agent portfolio (save & reuse)
- [x] Live execution logs
- [x] Secret management (redacted from logs)
- [x] Background job processing (RQ)
- [x] Next.js frontend with shadcn/ui
- [x] SQLite dev database with migrations
- [x] **Real-time cost estimation and tracking**

### 🚧 TODO

- [ ] Vector memory integration (Chroma)
- [ ] GitHub Actions CI/CD
- [ ] OAuth authentication (Clerk/Auth.js)
- [ ] Agent versioning & rollback
- [ ] Cost analytics dashboard (monthly spend, trends)
- [ ] Multi-tenancy
- [ ] Agent marketplace
- [ ] Webhook integrations
- [ ] Agent composition (chains)

## Troubleshooting

### Playwright Installation

```bash
cd backend
playwright install chromium
```

### Redis Connection Issues

Ensure Redis is running:

```bash
redis-server
```

Or use Docker:

```bash
docker run -d -p 6379:6379 redis:alpine
```

### Database Migration Errors

Reset database (DEV ONLY):

```bash
rm backend/agent_factory.db
make db
```

### Import Errors

Ensure you're in the correct virtual environment:

```bash
cd backend
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `make test`
5. Format code: `make fmt`
6. Commit: `git commit -m 'Add amazing feature'`
7. Push: `git push origin feature/amazing-feature`
8. Open a Pull Request

## License

MIT License - see LICENSE file for details

## Support

- Documentation: [Link to docs]
- Issues: [GitHub Issues](https://github.com/yourusername/agent-factory/issues)
- Discussions: [GitHub Discussions](https://github.com/yourusername/agent-factory/discussions)

---

Built with ❤️ using LangGraph, FastAPI, and Next.js
