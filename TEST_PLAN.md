# Zero-Fail Orchestration & GitHub Integration - Test Plan

## Overview

This test plan covers the new features implemented for zero-fail agent execution with API key collection, GitHub repository integration per agent, and multi-agent orchestration.

---

## Pre-Test Setup

### 1. Fresh Database Setup

```bash
cd backend
source venv/bin/activate
rm agent_factory.db  # Start fresh
alembic upgrade head
```

**Expected Result:**
- Database created with all new tables: `orchestrations`, `agents` with `repo_url` and `repo_local_path` columns
- No migration errors

### 2. Start Services

```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
python -m uvicorn app.main:app --reload

# Terminal 2: Worker
cd backend
source venv/bin/activate
python -m workers.runner

# Terminal 3: Frontend
cd frontend
npm run dev
```

**Expected Result:**
- Backend: http://localhost:8000 - Shows API status
- Frontend: http://localhost:3000 - Shows home page
- No startup errors

---

## Test Suite 1: Zero-Fail API Key Collection

### Test 1.1: Missing Keys Path - Fresh Start (No Keys)

**Setup:**
1. Remove ALL API keys from `.env` file (or rename `.env` to `.env.backup`)
2. Restart backend server

**Steps:**
1. Navigate to http://localhost:3000
2. Ask a question: "What are the latest AI trends?"
3. Wait for agent to be generated
4. Try to run the agent

**Expected Result:**
- Modal appears with "Required API Keys" title
- Shows missing keys with helpful links (e.g., OpenAI, Anthropic, SerpAPI)
- Form has password inputs for each key
- "Get key →" links open correct provider pages

**Pass Criteria:**
- ✅ No 500 error or crash
- ✅ Modal displays correctly
- ✅ Links are correct

### Test 1.2: Add Keys Via Modal and Auto-Retry

**Continuing from Test 1.1:**

**Steps:**
1. In the modal, add valid API keys:
   - `OPENAI_API_KEY`: Your OpenAI key
   - `SERPAPI_KEY`: Your SerpAPI key
2. Click "Save & Continue"

**Expected Result:**
- Modal shows "Saving..." state
- Modal closes automatically
- Agent run starts automatically
- Backend `.env` file is updated with new keys
- Run succeeds and shows logs

**Pass Criteria:**
- ✅ Keys saved to `.env`
- ✅ Run proceeds without requiring page refresh
- ✅ No errors in console
- ✅ Logs appear in "Logs & Results" tab

### Test 1.3: Verify Keys Persist Across Restarts

**Steps:**
1. Restart the backend server
2. Navigate to Settings page
3. Try to run another agent

**Expected Result:**
- Keys are still loaded from `.env`
- No modal appears (keys already present)
- Agent runs successfully

**Pass Criteria:**
- ✅ Keys loaded from `.env`
- ✅ No modal prompt
- ✅ Run succeeds

---

## Test Suite 2: GitHub Repository Integration

### Test 2.1: Create Repository Without GitHub Token

**Setup:**
1. Ensure `GITHUB_TOKEN` is NOT in `.env`
2. Have at least one saved agent

**Steps:**
1. Navigate to "My Agents" page
2. Click on an agent
3. Click "Files" tab
4. Click "Create GitHub Repository" button

**Expected Result:**
- API key modal appears
- Shows "GITHUB_TOKEN" as missing
- Provides link to https://github.com/settings/tokens
- Describes token requirements

**Pass Criteria:**
- ✅ 428 status returned (not 500)
- ✅ Modal shows GITHUB_TOKEN
- ✅ Link is correct

### Test 2.2: Add GitHub Token and Create Repository

**Continuing from Test 2.1:**

**Steps:**
1. Create a GitHub Personal Access Token with `repo` scope
2. Add token in the modal
3. Click "Save & Continue"

**Expected Result:**
- Token saved to `.env`
- Repository created on GitHub as `agent-<slug>`
- Repository initialized with:
  - `README.md`
  - `agent_spec.json`
- Local clone created in `./repos/<agent_id>/`
- Files tab now shows repository link and file list

**Pass Criteria:**
- ✅ Repository visible on GitHub
- ✅ Contains `README.md` and `agent_spec.json`
- ✅ Local clone exists
- ✅ Files tab shows "Open on GitHub" link
- ✅ File browser shows files

### Test 2.3: View and Browse Repository Files

**Continuing from Test 2.2:**

**Steps:**
1. In the "Files" tab, click on `agent_spec.json`
2. Click "Open on GitHub" link

**Expected Result:**
- File content displays in right pane
- Content is properly formatted JSON
- GitHub link opens correct repository

**Pass Criteria:**
- ✅ File content visible
- ✅ JSON is valid
- ✅ GitHub link works

### Test 2.4: Attempt to Create Repository Again (Idempotency)

**Steps:**
1. Go to "Files" tab of the same agent
2. (Button should not be visible or should return existing repo)

**Expected Result:**
- Either no "Create" button (since repo exists)
- Or clicking returns: "Repository already exists" with existing URL

**Pass Criteria:**
- ✅ No duplicate repository created
- ✅ Returns existing repository info

---

## Test Suite 3: Multi-Agent Orchestration

### Test 3.1: Manager-Led Orchestration

**Setup:**
1. Create/have at least 2 saved agents with different capabilities
2. Navigate to http://localhost:3000/orchestrations

**Steps:**
1. Select 2-3 agents (e.g., "Research Agent", "Coding Agent")
2. Select strategy: "Manager-Led"
3. Enter prompt: "Research the best React state management library and write a comparison guide"
4. Click "Start Orchestration"

**Expected Result:**
- Orchestration starts immediately
- Progress bars appear for each agent (0%)
- Logs stream in real-time
- Manager coordinates tasks between agents
- Progress bars update as agents complete
- Final output aggregates results
- Status changes to "completed"

**Pass Criteria:**
- ✅ Orchestration record created
- ✅ Progress bars update
- ✅ Logs stream correctly
- ✅ Each agent's output is captured
- ✅ Final status is "completed"

### Test 3.2: Sequential Orchestration

**Steps:**
1. Create new orchestration with same agents
2. Select strategy: "Sequential"
3. Enter prompt: "First research market trends, then suggest a business idea"
4. Start orchestration

**Expected Result:**
- Agents execute one after another
- First agent completes before second starts
- Second agent receives first agent's results as input
- Logs show sequential execution
- Per-agent outputs show progression

**Pass Criteria:**
- ✅ Sequential execution confirmed in logs
- ✅ Results passed between agents
- ✅ Final output includes all steps

### Test 3.3: Parallel Orchestration

**Steps:**
1. Create new orchestration with 3+ agents
2. Select strategy: "Parallel"
3. Enter prompt: "Each agent analyze a different aspect of AI safety"
4. Start orchestration

**Expected Result:**
- All agents start simultaneously
- Progress bars update independently
- All agents finish around the same time
- Separate outputs for each agent
- No inter-agent dependencies

**Pass Criteria:**
- ✅ Parallel execution in logs
- ✅ Independent results
- ✅ All agents complete

### Test 3.4: Orchestration Cost Tracking

**Continuing from any Test 3.x:**

**Steps:**
1. Wait for orchestration to complete
2. Check orchestration status page

**Expected Result:**
- "Total Cost" badge visible (e.g., "$0.0024")
- "Total Tokens" badge visible (e.g., "1,234")
- Cost is sum of all agent costs

**Pass Criteria:**
- ✅ Cost displayed
- ✅ Tokens displayed
- ✅ Numbers are reasonable

---

## Test Suite 4: Cost & Token Tracking

### Test 4.1: Single Agent Run Cost Display

**Steps:**
1. Run any agent with a prompt
2. Wait for completion
3. View "Logs & Results" tab

**Expected Result:**
- Cost badge shows: "💰 Cost: $0.00XX"
- Tokens badge shows: "🔤 Tokens: XXX"
- Values update after completion

**Pass Criteria:**
- ✅ Cost displayed
- ✅ Tokens displayed
- ✅ Values are non-zero for completed runs

### Test 4.2: Per-Step Token Usage

**Steps:**
1. Check run record in database or via API

**Expected Result:**
- `token_usage` field contains array of step-by-step usage
- Each step has: model, input_tokens, output_tokens, cost
- `total_cost` field is sum of all steps

**Pass Criteria:**
- ✅ Step-level tracking exists
- ✅ Totals are correct

---

## Test Suite 5: Error Handling & Edge Cases

### Test 5.1: Invalid API Key

**Steps:**
1. Add an invalid OPENAI_API_KEY via modal
2. Try to run an agent

**Expected Result:**
- Run starts
- Fails with clear error message
- Error suggests checking API key validity
- Run status is "failed"
- Error message is user-friendly

**Pass Criteria:**
- ✅ No crash
- ✅ Clear error message
- ✅ Status updated to "failed"

### Test 5.2: GitHub Token Without Repo Scope

**Steps:**
1. Create GitHub token WITHOUT `repo` scope
2. Try to create repository

**Expected Result:**
- Request fails
- Error message indicates insufficient permissions
- Suggests checking token scopes

**Pass Criteria:**
- ✅ Graceful failure
- ✅ Helpful error message

### Test 5.3: Orchestration with No Agents Selected

**Steps:**
1. Go to /orchestrations
2. Enter prompt but don't select any agents
3. Try to start

**Expected Result:**
- Alert or validation message: "Please select at least one agent"
- Orchestration does not start

**Pass Criteria:**
- ✅ Validation prevents submission
- ✅ Helpful message

### Test 5.4: Orchestration with Missing Keys

**Steps:**
1. Remove API keys from `.env`
2. Select agents and try to orchestrate

**Expected Result:**
- API key modal appears
- After adding keys, orchestration proceeds

**Pass Criteria:**
- ✅ Modal appears
- ✅ Keys saved
- ✅ Orchestration proceeds

---

## Test Suite 6: Data Persistence & Migrations

### Test 6.1: Fresh Database Migration

**Steps:**
1. Delete `agent_factory.db`
2. Run: `alembic upgrade head`

**Expected Result:**
- All tables created including `orchestrations`
- Agents table has `repo_url` and `repo_local_path` columns
- No migration errors

**Pass Criteria:**
- ✅ Migration succeeds
- ✅ All new tables/columns present

### Test 6.2: Existing Database Migration

**Setup:**
1. Use a database from before this feature set

**Steps:**
1. Run: `alembic upgrade head`

**Expected Result:**
- New columns added to `agents` table
- New `orchestrations` table created
- Existing data preserved
- No data loss

**Pass Criteria:**
- ✅ Migration succeeds
- ✅ New schema applied
- ✅ Old data intact

---

## Test Suite 7: End-to-End Workflow

### Test 7.1: Complete Zero-Fail Workflow

**Scenario:** New user with no API keys

**Steps:**
1. Start with fresh `.env` (no keys)
2. Navigate to homepage
3. Ask question: "How to build a SaaS business?"
4. Wait for research and agent generation
5. When modal appears for missing keys, add:
   - OPENAI_API_KEY
   - SERPAPI_KEY
6. Watch agent run complete
7. Save agent to portfolio
8. Go to agent detail page
9. Click "Files" tab
10. Click "Create GitHub Repository"
11. When modal appears, add GITHUB_TOKEN
12. View files in repository
13. Navigate to /orchestrations
14. Select the saved agent + another agent
15. Start a manager-led orchestration
16. Monitor progress
17. View final outputs and cost

**Expected Result:**
- Every step succeeds without crashes
- Keys are saved and reused
- GitHub repository is created
- Orchestration completes
- All data is persisted

**Pass Criteria:**
- ✅ Complete workflow without errors
- ✅ All features work together
- ✅ UI remains responsive
- ✅ Data persists across page navigation

---

## Acceptance Criteria Summary

### Must Pass:
- ✅ No 500 errors or unhandled exceptions at any point
- ✅ API key modal appears for all missing keys
- ✅ Keys saved via modal persist in `.env` and reload into runtime
- ✅ GitHub repositories are created successfully
- ✅ File browser displays repository contents
- ✅ Orchestrations execute with all 3 strategies
- ✅ Cost and token tracking displays correctly
- ✅ Database migrations are idempotent
- ✅ All error messages are user-friendly and actionable

### Performance:
- API key modal appears within 1 second
- Repository creation completes within 10 seconds
- File listing loads within 2 seconds
- Orchestration starts within 2 seconds

### Security:
- API keys not logged in plain text
- Secrets properly handled in responses
- GitHub token has appropriate scope requirements documented

---

## Commands for Testing

### Backend Commands

```bash
# Run migrations
cd backend
source venv/bin/activate
alembic upgrade head

# Start backend
python -m uvicorn app.main:app --reload

# Start worker
python -m workers.runner

# Check database
sqlite3 agent_factory.db "SELECT * FROM orchestrations;"
sqlite3 agent_factory.db "PRAGMA table_info(agents);"
```

### Frontend Commands

```bash
cd frontend
npm run dev
```

### Test API Endpoints Directly

```bash
# Get required keys
curl http://localhost:8000/api/settings/required_keys?agent_id=1

# Set keys
curl -X POST http://localhost:8000/api/settings/keys \
  -H "Content-Type: application/json" \
  -d '{"keys": {"OPENAI_API_KEY": "sk-test"}}'

# Create repo
curl -X POST http://localhost:8000/api/agents/1/repo

# Get files
curl http://localhost:8000/api/agents/1/files

# Create orchestration
curl -X POST http://localhost:8000/api/orchestrations \
  -H "Content-Type: application/json" \
  -d '{"agent_ids": [1,2], "prompt": "test", "strategy": "manager-led"}'

# Get orchestration status
curl http://localhost:8000/api/orchestrations/1
```

---

## Sign-Off

Test Date: _______________

Tester: _______________

**Test Results:**
- [ ] All Test Suite 1 tests passed
- [ ] All Test Suite 2 tests passed
- [ ] All Test Suite 3 tests passed
- [ ] All Test Suite 4 tests passed
- [ ] All Test Suite 5 tests passed
- [ ] All Test Suite 6 tests passed
- [ ] All Test Suite 7 tests passed

**Notes:**
_______________________________________________
_______________________________________________
_______________________________________________

**Approved for Deployment:** ☐ Yes ☐ No

Signature: _______________
