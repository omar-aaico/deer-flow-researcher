# DeerFlow API Documentation

**Version**: 0.1.0
**Base URL**: `http://localhost:8000`
**Interactive Docs**: http://localhost:8000/docs (Swagger UI)
**Alternative Docs**: http://localhost:8000/redoc (ReDoc)

---

## Table of Contents

- [Authentication](#authentication)
- [Research Endpoints](#research-endpoints)
  - [POST /api/chat/stream](#post-apichatstream)
  - [POST /api/research/async](#post-apiresearchasync)
  - [GET /api/research/{job_id}/status](#get-apiresearchjob_idstatus)
  - [GET /api/research/{job_id}/result](#get-apiresearchjob_idresult)
  - [DELETE /api/research/{job_id}](#delete-apiresearchjob_id)
- [Tool Endpoints](#tool-endpoints)
  - [POST /api/prompt/enhance](#post-apipromptenhance)
- [Report Styles](#report-styles)
- [Structured Output](#structured-output)
- [Examples](#examples)
- [Error Handling](#error-handling)

---

## Authentication

DeerFlow API uses **Bearer token authentication** with API keys.

### Getting an API Key

API keys are configured via environment variables. Contact your administrator for a key, or for local development, set `SKIP_AUTH=true` in `.env`.

### Making Authenticated Requests

Include your API key in the `Authorization` header:

```bash
Authorization: Bearer YOUR_API_KEY
```

**API Key Formats:**
- Production keys: `sk_live_...`
- Development keys: `sk_test_...`

### Example with curl:

```bash
curl -X POST http://localhost:8000/api/research/async \
  -H "Authorization: Bearer sk_test_dev_test_key_67890" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is quantum computing?"}'
```

### Skipping Authentication (Development Only)

Set `SKIP_AUTH=true` in `.env` to disable authentication:

```bash
SKIP_AUTH=true
```

**Warning:** Never use `SKIP_AUTH=true` in production!

---

## Research Endpoints

### POST /api/chat/stream

**Stream research results in real-time via Server-Sent Events (SSE).**

**Tags:** Research
**Authentication:** Required

#### Request Body

```json
{
  "messages": [
    {
      "role": "user",
      "content": "What are the latest developments in AI?"
    }
  ],
  "max_step_num": 5,
  "auto_accepted_plan": true,
  "report_style": "academic",
  "output_schema": {
    "type": "object",
    "properties": {
      "summary": {"type": "string"},
      "key_findings": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

#### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `messages` | array | Yes | - | Chat messages with user query |
| `max_step_num` | integer | No | 5 | Maximum research steps |
| `max_plan_iterations` | integer | No | 3 | Max planning iterations |
| `auto_accepted_plan` | boolean | No | false | Auto-accept research plan |
| `report_style` | string | No | "academic" | Output format (see [Report Styles](#report-styles)) |
| `output_schema` | object | No | null | JSON Schema for structured extraction |
| `search_provider` | string | No | "tavily" | Search engine ("tavily" or "firecrawl") |
| `enable_background_investigation` | boolean | No | false | Pre-planning web search |

#### Response

Server-Sent Events (SSE) stream with real-time updates:

```
event: message
data: {"type": "agent_thought", "content": "Planning research..."}

event: message
data: {"type": "tool_call", "tool": "search", "args": {...}}

event: message
data: {"type": "final_report", "content": "# Research Report\n\n..."}
```

#### Example

```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Authorization: Bearer sk_test_dev_test_key_67890" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain quantum computing"}],
    "max_step_num": 3,
    "auto_accepted_plan": true
  }' \
  --no-buffer
```

---

### POST /api/research/async

**Start an asynchronous research job and receive a job_id immediately.**

**Tags:** Jobs
**Authentication:** Required

#### Request Body

```json
{
  "query": "What are the latest AI breakthroughs in 2024?",
  "max_step_num": 5,
  "auto_accepted_plan": true,
  "report_style": "popular_science",
  "output_schema": {
    "type": "object",
    "properties": {
      "breakthroughs": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "impact": {"type": "string"}
          }
        }
      }
    },
    "required": ["breakthroughs"]
  }
}
```

#### Response

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "message": "Research job started successfully"
}
```

#### Workflow

1. POST to `/api/research/async` → Get `job_id`
2. Poll `/api/research/{job_id}/status` every 2-5 seconds
3. When `status == "completed"`, GET `/api/research/{job_id}/result`

#### Example

```bash
# 1. Start job
JOB_ID=$(curl -s -X POST http://localhost:8000/api/research/async \
  -H "Authorization: Bearer sk_test_dev_test_key_67890" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tesla latest initiatives",
    "report_style": "sales_intelligence",
    "auto_accepted_plan": true
  }' | jq -r '.job_id')

echo "Job ID: $JOB_ID"

# 2. Poll status
curl -X GET "http://localhost:8000/api/research/${JOB_ID}/status" \
  -H "Authorization: Bearer sk_test_dev_test_key_67890"

# 3. Get results when completed
curl -X GET "http://localhost:8000/api/research/${JOB_ID}/result" \
  -H "Authorization: Bearer sk_test_dev_test_key_67890"
```

---

### GET /api/research/{job_id}/status

**Check the current status of an async research job.**

**Tags:** Jobs
**Authentication:** Required

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string (UUID) | Job identifier from `/api/research/async` |

#### Response

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "researching",
  "error": null,
  "created_at": "2025-10-10T12:00:00Z",
  "updated_at": "2025-10-10T12:01:30Z"
}
```

#### Status Values

| Status | Description |
|--------|-------------|
| `pending` | Job is queued, not started yet |
| `coordinating` | Router agent is analyzing the query |
| `planning` | Planner agent is creating the research plan |
| `researching` | Researcher/Coder agents are gathering information |
| `reporting` | Reporter agent is generating the final report |
| `completed` | Research finished successfully |
| `failed` | Job encountered an error (check `error` field) |

#### Example

```bash
curl -X GET "http://localhost:8000/api/research/{job_id}/status" \
  -H "Authorization: Bearer sk_test_dev_test_key_67890"
```

---

### GET /api/research/{job_id}/result

**Retrieve the final research report and structured data from a completed job.**

**Tags:** Jobs
**Authentication:** Required

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string (UUID) | Job identifier |

#### Response

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "thread_id": "thread-uuid",
  "query": "What is quantum computing?",
  "final_report": "# Quantum Computing Research\n\n## Overview\n...",
  "structured_output": {
    "summary": "Quantum computing uses quantum mechanics...",
    "key_findings": [
      "Superposition allows parallel computation",
      "Quantum error correction is a major challenge"
    ]
  },
  "researcher_findings": ["Finding 1", "Finding 2"],
  "plan": {...},
  "error": null,
  "created_at": "2025-10-10T12:00:00Z",
  "completed_at": "2025-10-10T12:05:30Z",
  "duration_seconds": 330
}
```

#### Example

```bash
curl -X GET "http://localhost:8000/api/research/{job_id}/result" \
  -H "Authorization: Bearer sk_test_dev_test_key_67890" \
  | jq '.final_report'
```

---

### DELETE /api/research/{job_id}

**Cancel a running job or delete a completed job from memory.**

**Tags:** Jobs
**Authentication:** Required

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string (UUID) | Job identifier |

#### Response

```json
{
  "message": "Job a1b2c3d4-e5f6-7890-abcd-ef1234567890 cancelled and deleted",
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

#### Example

```bash
curl -X DELETE "http://localhost:8000/api/research/{job_id}" \
  -H "Authorization: Bearer sk_test_dev_test_key_67890"
```

---

## Tool Endpoints

### POST /api/prompt/enhance

**Enhance a research prompt for better results.**

**Tags:** Tools
**Authentication:** Not required by default

#### Request Body

```json
{
  "prompt": "Research Tesla",
  "context": "I need competitive intelligence focusing on AI and automation",
  "report_style": "sales_intelligence"
}
```

#### Response

```json
{
  "result": "Conduct comprehensive B2B sales intelligence research on Tesla with focus on AI and automation capabilities..."
}
```

#### Example

```bash
curl -X POST http://localhost:8000/api/prompt/enhance \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Analyze SpaceX",
    "context": "Focus on reusability and cost reduction",
    "report_style": "strategic_investment"
  }'
```

---

## Report Styles

DeerFlow supports multiple output formats optimized for different use cases:

| Style | Use Case | Word Count |
|-------|----------|------------|
| `academic` | Peer-reviewed research with citations | 2000-5000 |
| `popular_science` | Engaging science communication | 1500-3000 |
| `news` | NBC News-style journalism | 800-1500 |
| `social_media` | Twitter/viral content | 300-800 |
| `strategic_investment` | Deep technology analysis | 10000-15000 |
| `sales_intelligence` | B2B sales research | 3000-5000 |
| `workflow_blueprint` | Process automation (narrative, no bullets) | 2000-4000 |
| `competitive_analysis` | Feature comparison and battle cards | 3000-4000 |

### Example Usage

```json
{
  "query": "Latest AI developments",
  "report_style": "academic"
}
```

---

## Structured Output

Extract structured JSON data alongside the markdown report by providing a JSON Schema.

### Example Request

```json
{
  "query": "Research Python 3.12 features",
  "output_schema": {
    "type": "object",
    "properties": {
      "version": {"type": "string"},
      "release_date": {"type": "string"},
      "new_features": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"}
          }
        }
      }
    },
    "required": ["version", "new_features"]
  }
}
```

### Example Response

```json
{
  "final_report": "# Python 3.12 Research\n\n...",
  "structured_output": {
    "version": "3.12.0",
    "release_date": "2023-10-02",
    "new_features": [
      {
        "name": "Improved error messages",
        "description": "Better syntax error reporting with colors"
      },
      {
        "name": "Performance improvements",
        "description": "Up to 5% faster than 3.11"
      }
    ]
  }
}
```

---

## Examples

### Complete Async Workflow

```bash
#!/bin/bash

API_KEY="sk_test_dev_test_key_67890"
BASE_URL="http://localhost:8000"

# 1. Start async job
echo "Starting research job..."
JOB_RESPONSE=$(curl -s -X POST "$BASE_URL/api/research/async" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Comprehensive analysis of Rust programming language",
    "max_step_num": 5,
    "auto_accepted_plan": true,
    "report_style": "academic",
    "output_schema": {
      "type": "object",
      "properties": {
        "language_name": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}}
      }
    }
  }')

JOB_ID=$(echo $JOB_RESPONSE | jq -r '.job_id')
echo "Job ID: $JOB_ID"

# 2. Poll until complete
while true; do
  STATUS=$(curl -s -X GET "$BASE_URL/api/research/$JOB_ID/status" \
    -H "Authorization: Bearer $API_KEY" \
    | jq -r '.status')

  echo "Status: $STATUS"

  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi

  sleep 5
done

# 3. Get results
if [ "$STATUS" = "completed" ]; then
  echo "Fetching results..."
  curl -s -X GET "$BASE_URL/api/research/$JOB_ID/result" \
    -H "Authorization: Bearer $API_KEY" \
    | jq '.structured_output'
fi
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 401 | Unauthorized - Invalid/missing API key |
| 403 | Forbidden - Feature disabled (e.g., MCP without ENABLE_MCP_SERVER_CONFIGURATION) |
| 404 | Not Found - Job ID doesn't exist |
| 422 | Validation Error - Invalid request body |
| 500 | Internal Server Error |

### Error Response Format

```json
{
  "detail": "Invalid API key. Check your credentials."
}
```

### Common Errors

**401 Unauthorized**
```json
{
  "detail": "Missing authorization header. Include 'Authorization: Bearer YOUR_API_KEY'"
}
```

**404 Not Found**
```json
{
  "detail": "Job a1b2c3d4-e5f6-7890-abcd-ef1234567890 not found"
}
```

**422 Validation Error**
```json
{
  "detail": [
    {
      "loc": ["body", "query"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Interactive Documentation

DeerFlow provides two interactive API documentation interfaces:

### Swagger UI
**URL**: http://localhost:8000/docs

- Try out endpoints directly in the browser
- Built-in request/response examples
- Authentication testing
- Auto-generated from OpenAPI schema

### ReDoc
**URL**: http://localhost:8000/redoc

- Clean, organized documentation
- Three-panel layout
- Downloadable OpenAPI spec
- Better for reading/printing

---

## Support

- **GitHub Issues**: https://github.com/your-org/deer-flow/issues
- **Documentation**: `/docs` directory
- **Examples**: `examples/` directory

---

**Last Updated**: 2025-10-10
**API Version**: 0.1.0
