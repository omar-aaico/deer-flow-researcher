# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DeerFlow is a Deep Research framework built on LangGraph that orchestrates multiple AI agents to conduct research, analyze code, and generate comprehensive reports. The system uses a multi-agent architecture where specialized agents (Coordinator, Planner, Researcher, Coder, Reporter) collaborate through a state-based workflow.

## Development Commands

### Python Backend

```bash
# Install dependencies (uv automatically manages venv and Python)
uv sync

# Run console UI
uv run main.py

# Run with specific query
uv run main.py "your research question"

# Run interactive mode with built-in questions
uv run main.py --interactive

# Run with custom parameters
uv run main.py --max_plan_iterations 3 --max_step_num 5 --debug "your question"

# Start development server (with auto-reload)
make serve
# or
uv run server.py --reload

# Run all tests
make test
# or
uv run pytest tests/

# Run specific test file
uv run pytest tests/integration/test_workflow.py

# Run with coverage
make coverage

# Lint code
make lint

# Format code
make format
```

### Web UI (Next.js)

```bash
cd web

# Install dependencies
pnpm install

# Run development server (with backend)
cd .. && ./bootstrap.sh -d

# Web-only development
pnpm dev

# Build for production
pnpm build

# Type checking
pnpm typecheck

# Lint
pnpm lint
```

### LangGraph Debugging

```bash
# Start LangGraph Studio for visual debugging
make langgraph-dev
# or
uvx --refresh --from "langgraph-cli[inmem]" --with-editable . --python 3.12 langgraph dev --allow-blocking
```

Then open the Studio UI at: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024

### Docker

```bash
# Build image
docker build -t deer-flow-api .

# Run container
docker run -d -t -p 127.0.0.1:8000:8000 --env-file .env --name deer-flow-api-app deer-flow-api

# Docker Compose (backend + frontend)
docker compose build
docker compose up
```

## Configuration

### Required Configuration Files

1. **`.env`** - Environment variables for API keys and service configuration
   - Copy from `.env.example`
   - Configure search engine (Tavily, Brave, DuckDuckGo, etc.)
   - Set up RAG provider if needed (RAGFlow, VikingDB, Milvus, etc.)
   - Configure TTS credentials for podcast generation
   - Enable MCP server and Python REPL only in secure environments

2. **`conf.yaml`** - LLM model configuration
   - Copy from `conf.yaml.example`
   - Configure BASIC_MODEL, optionally REASONING_MODEL and CODE_MODEL
   - Supports litellm format for OpenAI-compatible models
   - Local models supported via Ollama or other OpenAI-compatible endpoints

### Agent-to-LLM Mapping

Located in `src/config/agents.py`, the `AGENT_LLM_MAP` dictionary defines which LLM type each agent uses:
- Available types: `"basic"`, `"reasoning"`, `"vision"`, `"code"`
- Modify this mapping when using specialized models (e.g., assign `"reasoning"` to planner/coordinator)

## Architecture

### Multi-Agent System

DeerFlow uses LangGraph's StateGraph to orchestrate agents:

1. **Coordinator** (`src/graph/nodes.py:coordinator_node`)
   - Entry point, manages workflow lifecycle
   - Routes to planner or handles simple queries directly

2. **Background Investigator** (`src/graph/nodes.py:background_investigation_node`)
   - Optional pre-planning web search to gather context
   - Controlled by `enable_background_investigation` parameter

3. **Planner** (`src/graph/nodes.py:planner_node`)
   - Creates structured research plans with typed steps (RESEARCH/PROCESSING)
   - Supports human-in-the-loop feedback via `human_feedback_node`
   - Determines when to generate final report based on context sufficiency

4. **Research Team** (`src/graph/nodes.py:research_team_node`)
   - Dispatcher that routes to specialized agents based on step type
   - **Researcher**: Web search, crawling, RAG retrieval (StepType.RESEARCH)
   - **Coder**: Python code execution and analysis (StepType.PROCESSING)

5. **Reporter** (`src/graph/nodes.py:reporter_node`)
   - Aggregates findings and generates comprehensive reports
   - Supports multiple output formats via `report_style` parameter
   - Optionally extracts structured data when `output_schema` is provided
   - Returns both `final_report` (markdown) and `structured_output` (JSON) when schema specified

### Graph Flow

```
START → coordinator → background_investigator → planner ⇄ human_feedback
                                                    ↓
                                              research_team → [researcher | coder] → planner
                                                    ↓
                                                reporter → END
```

The graph is built in `src/graph/builder.py` with conditional routing logic in `continue_to_running_research_team()`.

### State Management

- Primary state type: `State` (defined in `src/graph/types.py`)
- Key state fields:
  - `output_schema`: Optional Pydantic schema dict for structured data extraction
  - `structured_output`: Extracted JSON data conforming to output_schema
  - `final_report`: Markdown formatted research report
  - `current_plan`: Active research plan with steps
  - `observations`: Collected research findings
- Checkpointing supported via MongoDB or PostgreSQL (configure in `.env` with `LANGGRAPH_CHECKPOINT_SAVER=true`)
- In-memory checkpointing used by default for development

### Tools

Tools are located in `src/tools/`:
- `search.py`: Multi-engine web search (Tavily, Brave, DuckDuckGo, Arxiv, Searx)
- `crawl.py`: Web content extraction via Jina
- `python_repl.py`: Sandboxed Python code execution
- `retriever.py`: RAG integration for private knowledge bases
- `tts.py`: Text-to-speech for podcast generation

Tools are decorated with `@configurable_tool` or `@configurable_tool_with_session` (see `src/tools/decorators.py`) to enable dynamic configuration and MCP integration.

## MCP (Model Context Protocol) Integration

DeerFlow supports MCP servers to extend capabilities. Configuration example in `src/workflow.py`:

```python
"mcp_settings": {
    "servers": {
        "mcp-github-trending": {
            "transport": "stdio",
            "command": "uvx",
            "args": ["mcp-github-trending"],
            "enabled_tools": ["get_github_trending_repositories"],
            "add_to_agents": ["researcher"]
        }
    }
}
```

## Prompts

All prompts are in `src/prompts/` using Jinja2 templates:
- Agent system prompts: `coordinator.md`, `planner.md`, `researcher.md`, `coder.md`, `reporter.md`
- Report styles defined in `src/config/report_style.py` with styles applied via `reporter.md`
- Prompt application: `src/prompts/template.py:apply_prompt_template()`

### Report Styles

The system supports multiple report styles (configured via `report_style` parameter):
- **`academic`**: Formal, peer-reviewed journal style with rigorous citations
- **`popular_science`**: Engaging science communication for general audiences
- **`news`**: NBC News-style broadcast journalism format
- **`social_media`**: Twitter/Xiaohongshu viral content optimization
- **`strategic_investment`**: Deep technology investment analysis (10k-15k words)
- **`sales_intelligence`**: B2B sales research with decision-maker focus, competitor analysis, and digital transformation intelligence
- **`workflow_blueprint`**: Process automation blueprints in narrative format (no bullets) with action verbs for LLM implementation

## Testing

Tests use pytest with asyncio support (`tests/` directory):
- Integration tests require configured `.env` and `conf.yaml`
- Mock dependencies with `mongomock` and `pytest-postgresql`
- Coverage threshold: 25% (configured in `pyproject.toml`)

## Key Implementation Details

### LLM Configuration

LLMs are initialized in `src/llms/llm.py`:
- Uses litellm for multi-provider support
- Supports OpenAI-compatible endpoints
- Model types configured per agent in `src/config/agents.py`

### Human-in-the-Loop

When `auto_accepted_plan=False`:
1. Planner generates plan and sends to `human_feedback_node`
2. Node waits for user feedback via interrupt
3. User can accept with `[ACCEPTED]` or provide edit instructions
4. Planner revises plan based on feedback

### Podcast Generation

Workflow in `src/podcast/`:
1. Generate script from report (`script_generator.py`)
2. Convert to audio via TTS (`tts_generator.py`)
3. Requires Volcengine TTS credentials in `.env`

### Web Server

FastAPI backend in `src/server/`:
- **Async Research API**: `/api/research/async` - Submit research jobs and poll for completion
- **Job Status**: `/api/research/{job_id}/status` - Check job progress (returns status enum)
- **Job Results**: `/api/research/{job_id}/result` - Retrieve completed research with both `final_report` and `structured_output`
- **Streaming endpoint**: `/api/chat/stream` - Real-time SSE streaming for synchronous research
- Job management via `src/server/job_manager.py` with in-memory storage
- CORS configured via `ALLOWED_ORIGINS` in `.env`

### Structured Output System

DeerFlow supports optional structured data extraction alongside markdown reports:

**How it works:**
1. Client provides `output_schema` (JSON Schema dict) in research request
2. Planner receives schema and optimizes research steps to gather required data
3. Reporter generates markdown report as usual
4. Reporter then extracts structured JSON from report using LLM with `with_structured_output()`
5. Both `final_report` (markdown) and `structured_output` (JSON) returned to client

**Benefits:**
- Dual format output: human-readable markdown + machine-readable JSON
- No information loss - both formats available
- Backward compatible - works with or without schema
- Graceful fallback - if extraction fails, markdown report still available

**Example Request:**
```json
{
  "query": "Research Tesla's latest initiatives",
  "report_style": "sales_intelligence",
  "output_schema": {
    "type": "object",
    "properties": {
      "company_name": {"type": "string"},
      "ceo": {"type": "string"},
      "recent_initiatives": {"type": "array", "items": {"type": "string"}},
      "tech_stack": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["company_name", "ceo"]
  }
}
```

**Example Response:**
```json
{
  "job_id": "uuid",
  "final_report": "# Tesla Research Report\n\n...",
  "structured_output": {
    "company_name": "Tesla Inc.",
    "ceo": "Elon Musk",
    "recent_initiatives": ["FSD v12", "Cybertruck Production", "AI Training Cluster"],
    "tech_stack": ["Python", "C++", "Custom ML Framework"]
  }
}
```

## Common Patterns

### Adding a New Agent

1. Define agent in `src/agents/agents.py` using `create_agent()`
2. Add node function in `src/graph/nodes.py`
3. Register node in `src/graph/builder.py`
4. Create prompt template in `src/prompts/`
5. Add to `AGENT_LLM_MAP` in `src/config/agents.py`

### Adding a New Tool

1. Create tool function in `src/tools/`
2. Decorate with `@configurable_tool` or `@configurable_tool_with_session`
3. Add to agent's tool list in corresponding node function

### Adding a New Report Style

1. Add enum value to `src/config/report_style.py` (e.g., `MY_STYLE = "my_style"`)
2. Add persona and requirements in `src/prompts/reporter.md` within the `{% elif report_style == "my_style" %}` block
3. Define report structure in the "Survey Note" section for your style
4. Add writing style guidelines in the "Writing Guidelines" section
5. Optionally update `src/prompts/planner.md` to optimize research for your style

## Authentication & Security

### API Authentication

DeerFlow uses Bearer token authentication with API keys:

**Implementation** (`src/middleware/auth.py`):
- In-memory API key store loaded from environment variables
- Two security schemes:
  - `security = HTTPBearer()` - Required authentication
  - `optional_security = HTTPBearer(auto_error=False)` - Optional authentication
- Two middleware functions:
  - `verify_api_key()` - Enforces authentication (401 if missing/invalid)
  - `optional_verify_api_key()` - Respects `SKIP_AUTH` setting

**Configuration** (`.env`):
```bash
# Development mode - allows unauthenticated requests
SKIP_AUTH=true

# API Keys (format: sk_live_* or sk_test_*)
ADMIN_API_KEY=sk_live_admin_test_key_12345
DEV_API_KEY=sk_test_dev_test_key_67890

# Additional keys can be added as API_KEY_1, API_KEY_2, etc.
```

**Usage**:
- Endpoints use `Depends(optional_verify_api_key)` for optional auth
- Protected endpoints use `Depends(verify_api_key)` for required auth
- When `SKIP_AUTH=true`, all requests allowed without authentication
- When `SKIP_AUTH=false`, valid API key required in `Authorization: Bearer <key>` header

**API Documentation**:
- Interactive Swagger UI: http://localhost:8000/docs
- Alternative ReDoc: http://localhost:8000/redoc
- OpenAPI schema: http://localhost:8000/openapi.json
- Comprehensive guide: `API_DOCUMENTATION.md`

**Testing**:
```bash
# Run authentication test suite
./test_authentication.sh
```

### Security Considerations

- `ENABLE_MCP_SERVER_CONFIGURATION` and `ENABLE_PYTHON_REPL` default to `false` for security
- Only enable in secured, managed environments
- Backend binds to `127.0.0.1` by default (change to `0.0.0.0` only when properly secured)
- Never commit `.env` or `conf.yaml` files containing API keys
- **IMPORTANT**: Set `SKIP_AUTH=false` in production environments
- API keys should be rotated regularly and stored securely
