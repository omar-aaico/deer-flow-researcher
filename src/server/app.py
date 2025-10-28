# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import base64
import json
import logging
from typing import Annotated, Any, Dict, List, Optional, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage
from langgraph.checkpoint.mongodb import AsyncMongoDBSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool

from src.config.configuration import get_recursion_limit
from src.config.loader import get_bool_env, get_str_env
from src.config.report_style import ReportStyle
from src.config.tools import SELECTED_RAG_PROVIDER
from src.graph.builder import build_graph_with_memory
from src.graph.checkpoint import chat_stream_message
from src.llms.llm import get_configured_llm_models
from src.podcast.graph.builder import build_graph as build_podcast_graph
from src.ppt.graph.builder import build_graph as build_ppt_graph
from src.prompt_enhancer.graph.builder import build_graph as build_prompt_enhancer_graph
from src.prose.graph.builder import build_graph as build_prose_graph
from src.rag.builder import build_retriever
from src.rag.milvus import load_examples
from src.rag.retriever import Resource
from src.server.chat_request import (
    ChatRequest,
    EnhancePromptRequest,
    GeneratePodcastRequest,
    GeneratePPTRequest,
    GenerateProseRequest,
    TTSRequest,
)
from src.server.async_request import (
    AsyncResearchRequest,
    AsyncResearchResponse,
    ResearchStatus,
    ResearchStatusResponse,
    ResearchResultResponse,
)
from src.server.models import (
    PersonResearchRequest,
    PersonResearchResponse,
    DisambiguationRequest,
    Candidate,
)
from src.config.person_schema import DEFAULT_PERSON_SCHEMA
from src.server.config_request import ConfigResponse
from src.server.job_manager import job_manager, ResearchJob
from src.server.mcp_request import MCPServerMetadataRequest, MCPServerMetadataResponse
from src.server.mcp_utils import load_mcp_tools
from src.server.rag_request import (
    RAGConfigResponse,
    RAGResourceRequest,
    RAGResourcesResponse,
)
from src.middleware.auth import init_api_keys, optional_verify_api_key
from src.tools import VolcengineTTS
from src.utils.json_utils import sanitize_args

logger = logging.getLogger(__name__)

INTERNAL_SERVER_ERROR_DETAIL = "Internal Server Error"

app = FastAPI(
    title="DeerFlow API",
    description="""
# DeerFlow Deep Research API

AI-powered deep research and analysis framework with multi-agent orchestration.

## Features
- 🔍 **Deep Research**: Multi-step research with web search and code execution
- 📊 **Structured Output**: Extract data into custom JSON schemas
- 🎯 **Multiple Report Styles**: Academic, news, sales intelligence, workflow blueprints, and more
- 🤖 **Multi-Agent System**: Coordinator, Planner, Researcher, Coder, Reporter agents
- 💾 **Async Job Processing**: Submit jobs and poll for results
- 🔐 **API Key Authentication**: Secure endpoints with Bearer token auth

## Authentication
Most endpoints require API key authentication. Include your API key in the request header:

```
Authorization: Bearer YOUR_API_KEY
```

Get your API key from your administrator or set `SKIP_AUTH=true` for local development.
    """,
    version="0.1.0",
    docs_url="/docs",  # Swagger UI at /docs
    redoc_url="/redoc",  # ReDoc at /redoc
    openapi_tags=[
        {"name": "Research", "description": "Core research endpoints for running deep analysis"},
        {"name": "Jobs", "description": "Async job management - create, poll, and retrieve results"},
        {"name": "Tools", "description": "Utility endpoints - prompt enhancement, podcast generation, etc."},
        {"name": "RAG", "description": "Retrieval-Augmented Generation - manage knowledge base resources"},
        {"name": "Configuration", "description": "System configuration and MCP server management"},
    ],
)

# Add CORS middleware
# It's recommended to load the allowed origins from an environment variable
# for better security and flexibility across different environments.
allowed_origins_str = get_str_env("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

# Allow file:// origins for local HTML testing (shows as "null" in CORS)
# This is safe for local development only
if "null" not in allowed_origins:
    allowed_origins.append("null")

logger.info(f"Allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Restrict to specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Use the configured list of methods
    allow_headers=["*"],  # Now allow all headers, but can be restricted further
)

# Load examples into Milvus if configured
load_examples()

in_memory_store = InMemoryStore()
graph = build_graph_with_memory()
# quick_research_graph = build_quick_research_graph()  # Disabled - not used in sync endpoint


@app.on_event("startup")
async def startup_event():
    """Initialize API keys and other resources on server startup."""
    logger.info("Starting DeerFlow API server...")
    init_api_keys()
    logger.info("Server startup complete")


@app.post(
    "/api/chat/stream",
    tags=["Research"],
    summary="Stream research results in real-time",
    description="""
    Submit a research query and receive streaming updates via Server-Sent Events (SSE).

    This endpoint executes the full research workflow synchronously and streams intermediate
    results (agent thoughts, tool calls, observations) back to the client in real-time.

    **Authentication**: Required (unless SKIP_AUTH=true)
    """,
)
async def chat_stream(
    request: ChatRequest,
    auth: Optional[Dict[str, str]] = Depends(optional_verify_api_key),
):
    # Check if MCP server configuration is enabled
    mcp_enabled = get_bool_env("ENABLE_MCP_SERVER_CONFIGURATION", False)

    # Validate MCP settings if provided
    if request.mcp_settings and not mcp_enabled:
        raise HTTPException(
            status_code=403,
            detail="MCP server configuration is disabled. Set ENABLE_MCP_SERVER_CONFIGURATION=true to enable MCP features.",
        )

    thread_id = request.thread_id
    if thread_id == "__default__":
        thread_id = str(uuid4())

    return StreamingResponse(
        _astream_workflow_generator(
            request.model_dump()["messages"],
            thread_id,
            request.resources,
            request.max_plan_iterations,
            request.max_step_num,
            request.max_search_results,
            request.auto_accepted_plan,
            request.interrupt_feedback,
            request.mcp_settings if mcp_enabled else {},
            request.enable_background_investigation,
            request.report_style,
            request.enable_deep_thinking,
            request.search_provider,
            request.output_schema,
        ),
        media_type="text/event-stream",
    )


def _process_tool_call_chunks(tool_call_chunks):
    """Process tool call chunks and sanitize arguments."""
    chunks = []
    for chunk in tool_call_chunks:
        chunks.append(
            {
                "name": chunk.get("name", ""),
                "args": sanitize_args(chunk.get("args", "")),
                "id": chunk.get("id", ""),
                "index": chunk.get("index", 0),
                "type": chunk.get("type", ""),
            }
        )
    return chunks


def _get_agent_name(agent, message_metadata):
    """Extract agent name from agent tuple."""
    agent_name = "unknown"
    if agent and len(agent) > 0:
        agent_name = agent[0].split(":")[0] if ":" in agent[0] else agent[0]
    else:
        agent_name = message_metadata.get("langgraph_node", "unknown")
    return agent_name


def _create_event_stream_message(
    message_chunk, message_metadata, thread_id, agent_name
):
    """Create base event stream message."""
    event_stream_message = {
        "thread_id": thread_id,
        "agent": agent_name,
        "id": message_chunk.id,
        "role": "assistant",
        "checkpoint_ns": message_metadata.get("checkpoint_ns", ""),
        "langgraph_node": message_metadata.get("langgraph_node", ""),
        "langgraph_path": message_metadata.get("langgraph_path", ""),
        "langgraph_step": message_metadata.get("langgraph_step", ""),
        "content": message_chunk.content,
    }

    # Add optional fields
    if message_chunk.additional_kwargs.get("reasoning_content"):
        event_stream_message["reasoning_content"] = message_chunk.additional_kwargs[
            "reasoning_content"
        ]

    if message_chunk.response_metadata.get("finish_reason"):
        event_stream_message["finish_reason"] = message_chunk.response_metadata.get(
            "finish_reason"
        )

    return event_stream_message


def _create_interrupt_event(thread_id, event_data):
    """Create interrupt event."""
    return _make_event(
        "interrupt",
        {
            "thread_id": thread_id,
            "id": event_data["__interrupt__"][0].ns[0],
            "role": "assistant",
            "content": event_data["__interrupt__"][0].value,
            "finish_reason": "interrupt",
            "options": [
                {"text": "Edit plan", "value": "edit_plan"},
                {"text": "Start research", "value": "accepted"},
            ],
        },
    )


def _process_initial_messages(message, thread_id):
    """Process initial messages and yield formatted events."""
    json_data = json.dumps(
        {
            "thread_id": thread_id,
            "id": "run--" + message.get("id", uuid4().hex),
            "role": "user",
            "content": message.get("content", ""),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    chat_stream_message(
        thread_id, f"event: message_chunk\ndata: {json_data}\n\n", "none"
    )


async def _process_message_chunk(message_chunk, message_metadata, thread_id, agent):
    """Process a single message chunk and yield appropriate events."""
    agent_name = _get_agent_name(agent, message_metadata)
    event_stream_message = _create_event_stream_message(
        message_chunk, message_metadata, thread_id, agent_name
    )

    if isinstance(message_chunk, ToolMessage):
        # Tool Message - Return the result of the tool call
        event_stream_message["tool_call_id"] = message_chunk.tool_call_id
        yield _make_event("tool_call_result", event_stream_message)
    elif isinstance(message_chunk, AIMessageChunk):
        # AI Message - Raw message tokens
        if message_chunk.tool_calls:
            # AI Message - Tool Call
            event_stream_message["tool_calls"] = message_chunk.tool_calls
            event_stream_message["tool_call_chunks"] = _process_tool_call_chunks(
                message_chunk.tool_call_chunks
            )
            yield _make_event("tool_calls", event_stream_message)
        elif message_chunk.tool_call_chunks:
            # AI Message - Tool Call Chunks
            event_stream_message["tool_call_chunks"] = _process_tool_call_chunks(
                message_chunk.tool_call_chunks
            )
            yield _make_event("tool_call_chunks", event_stream_message)
        else:
            # AI Message - Raw message tokens
            yield _make_event("message_chunk", event_stream_message)


async def _stream_graph_events(
    graph_instance, workflow_input, workflow_config, thread_id
):
    """Stream events from the graph and process them."""
    try:
        async for agent, _, event_data in graph_instance.astream(
            workflow_input,
            config=workflow_config,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            if isinstance(event_data, dict):
                if "__interrupt__" in event_data:
                    yield _create_interrupt_event(thread_id, event_data)
                continue

            message_chunk, message_metadata = cast(
                tuple[BaseMessage, dict[str, Any]], event_data
            )

            async for event in _process_message_chunk(
                message_chunk, message_metadata, thread_id, agent
            ):
                yield event
    except Exception as e:
        logger.exception("Error during graph execution")
        yield _make_event(
            "error",
            {
                "thread_id": thread_id,
                "error": "Error during graph execution",
            },
        )


async def _astream_workflow_generator(
    messages: List[dict],
    thread_id: str,
    resources: List[Resource],
    max_plan_iterations: int,
    max_step_num: int,
    max_search_results: int,
    auto_accepted_plan: bool,
    interrupt_feedback: str,
    mcp_settings: dict,
    enable_background_investigation: bool,
    report_style: ReportStyle,
    enable_deep_thinking: bool,
    search_provider: str,
    output_schema: dict,
):
    # Process initial messages
    for message in messages:
        if isinstance(message, dict) and "content" in message:
            _process_initial_messages(message, thread_id)

    # Prepare workflow input
    workflow_input = {
        "messages": messages,
        "plan_iterations": 0,
        "final_report": "",
        "current_plan": None,
        "observations": [],
        "auto_accepted_plan": auto_accepted_plan,
        "enable_background_investigation": enable_background_investigation,
        "research_topic": messages[-1]["content"] if messages else "",
        "search_provider": search_provider,
        "searches_executed": 0,
        "output_schema": output_schema,
    }

    if not auto_accepted_plan and interrupt_feedback:
        resume_msg = f"[{interrupt_feedback}]"
        if messages:
            resume_msg += f" {messages[-1]['content']}"
        workflow_input = Command(resume=resume_msg)

    # Prepare workflow config
    workflow_config = {
        "thread_id": thread_id,
        "resources": resources,
        "max_plan_iterations": max_plan_iterations,
        "max_step_num": max_step_num,
        "max_search_results": max_search_results,
        "mcp_settings": mcp_settings,
        "report_style": report_style.value,
        "enable_deep_thinking": enable_deep_thinking,
        "recursion_limit": get_recursion_limit(),
    }

    checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
    checkpoint_url = get_str_env("LANGGRAPH_CHECKPOINT_DB_URL", "")
    # Handle checkpointer if configured
    connection_kwargs = {
        "autocommit": True,
        "row_factory": "dict_row",
        "prepare_threshold": 0,
    }
    if checkpoint_saver and checkpoint_url != "":
        if checkpoint_url.startswith("postgresql://"):
            logger.info("start async postgres checkpointer.")
            async with AsyncConnectionPool(
                checkpoint_url, kwargs=connection_kwargs
            ) as conn:
                checkpointer = AsyncPostgresSaver(conn)
                await checkpointer.setup()
                graph.checkpointer = checkpointer
                graph.store = in_memory_store
                async for event in _stream_graph_events(
                    graph, workflow_input, workflow_config, thread_id
                ):
                    yield event

        if checkpoint_url.startswith("mongodb://"):
            logger.info("start async mongodb checkpointer.")
            async with AsyncMongoDBSaver.from_conn_string(
                checkpoint_url
            ) as checkpointer:
                graph.checkpointer = checkpointer
                graph.store = in_memory_store
                async for event in _stream_graph_events(
                    graph, workflow_input, workflow_config, thread_id
                ):
                    yield event
    else:
        # Use graph without MongoDB checkpointer
        async for event in _stream_graph_events(
            graph, workflow_input, workflow_config, thread_id
        ):
            yield event


def _make_event(event_type: str, data: dict[str, any]):
    if data.get("content") == "":
        data.pop("content")
    # Ensure JSON serialization with proper encoding
    try:
        json_data = json.dumps(data, ensure_ascii=False)

        finish_reason = data.get("finish_reason", "")
        chat_stream_message(
            data.get("thread_id", ""),
            f"event: {event_type}\ndata: {json_data}\n\n",
            finish_reason,
        )

        return f"event: {event_type}\ndata: {json_data}\n\n"
    except (TypeError, ValueError) as e:
        logger.error(f"Error serializing event data: {e}")
        # Return a safe error event
        error_data = json.dumps({"error": "Serialization failed"}, ensure_ascii=False)
        return f"event: error\ndata: {error_data}\n\n"


@app.post("/api/tts")
async def text_to_speech(request: TTSRequest):
    """Convert text to speech using volcengine TTS API."""
    app_id = get_str_env("VOLCENGINE_TTS_APPID", "")
    if not app_id:
        raise HTTPException(status_code=400, detail="VOLCENGINE_TTS_APPID is not set")
    access_token = get_str_env("VOLCENGINE_TTS_ACCESS_TOKEN", "")
    if not access_token:
        raise HTTPException(
            status_code=400, detail="VOLCENGINE_TTS_ACCESS_TOKEN is not set"
        )

    try:
        cluster = get_str_env("VOLCENGINE_TTS_CLUSTER", "volcano_tts")
        voice_type = get_str_env("VOLCENGINE_TTS_VOICE_TYPE", "BV700_V2_streaming")

        tts_client = VolcengineTTS(
            appid=app_id,
            access_token=access_token,
            cluster=cluster,
            voice_type=voice_type,
        )
        # Call the TTS API
        result = tts_client.text_to_speech(
            text=request.text[:1024],
            encoding=request.encoding,
            speed_ratio=request.speed_ratio,
            volume_ratio=request.volume_ratio,
            pitch_ratio=request.pitch_ratio,
            text_type=request.text_type,
            with_frontend=request.with_frontend,
            frontend_type=request.frontend_type,
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=str(result["error"]))

        # Decode the base64 audio data
        audio_data = base64.b64decode(result["audio_data"])

        # Return the audio file
        return Response(
            content=audio_data,
            media_type=f"audio/{request.encoding}",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=tts_output.{request.encoding}"
                )
            },
        )

    except Exception as e:
        logger.exception(f"Error in TTS endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/podcast/generate")
async def generate_podcast(request: GeneratePodcastRequest):
    try:
        report_content = request.content
        print(report_content)
        workflow = build_podcast_graph()
        final_state = workflow.invoke({"input": report_content})
        audio_bytes = final_state["output"]
        return Response(content=audio_bytes, media_type="audio/mp3")
    except Exception as e:
        logger.exception(f"Error occurred during podcast generation: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/ppt/generate")
async def generate_ppt(request: GeneratePPTRequest):
    try:
        report_content = request.content
        print(report_content)
        workflow = build_ppt_graph()
        final_state = workflow.invoke({"input": report_content})
        generated_file_path = final_state["generated_file_path"]
        with open(generated_file_path, "rb") as f:
            ppt_bytes = f.read()
        return Response(
            content=ppt_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    except Exception as e:
        logger.exception(f"Error occurred during ppt generation: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/prose/generate")
async def generate_prose(request: GenerateProseRequest):
    try:
        sanitized_prompt = request.prompt.replace("\r\n", "").replace("\n", "")
        logger.info(f"Generating prose for prompt: {sanitized_prompt}")
        workflow = build_prose_graph()
        events = workflow.astream(
            {
                "content": request.prompt,
                "option": request.option,
                "command": request.command,
            },
            stream_mode="messages",
            subgraphs=True,
        )
        return StreamingResponse(
            (f"data: {event[0].content}\n\n" async for _, event in events),
            media_type="text/event-stream",
        )
    except Exception as e:
        logger.exception(f"Error occurred during prose generation: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/prompt/enhance")
async def enhance_prompt(request: EnhancePromptRequest):
    try:
        sanitized_prompt = request.prompt.replace("\r\n", "").replace("\n", "")
        logger.info(f"Enhancing prompt: {sanitized_prompt}")

        # Convert string report_style to ReportStyle enum
        report_style = None
        if request.report_style:
            try:
                # Handle both uppercase and lowercase input
                style_mapping = {
                    "ACADEMIC": ReportStyle.ACADEMIC,
                    "POPULAR_SCIENCE": ReportStyle.POPULAR_SCIENCE,
                    "NEWS": ReportStyle.NEWS,
                    "SOCIAL_MEDIA": ReportStyle.SOCIAL_MEDIA,
                    "STRATEGIC_INVESTMENT": ReportStyle.STRATEGIC_INVESTMENT,
                }
                report_style = style_mapping.get(
                    request.report_style.upper(), ReportStyle.ACADEMIC
                )
            except Exception:
                # If invalid style, default to ACADEMIC
                report_style = ReportStyle.ACADEMIC
        else:
            report_style = ReportStyle.ACADEMIC

        workflow = build_prompt_enhancer_graph()
        final_state = workflow.invoke(
            {
                "prompt": request.prompt,
                "context": request.context,
                "report_style": report_style,
            }
        )
        return {"result": final_state["output"]}
    except Exception as e:
        logger.exception(f"Error occurred during prompt enhancement: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/mcp/server/metadata", response_model=MCPServerMetadataResponse)
async def mcp_server_metadata(request: MCPServerMetadataRequest):
    """Get information about an MCP server."""
    # Check if MCP server configuration is enabled
    if not get_bool_env("ENABLE_MCP_SERVER_CONFIGURATION", False):
        raise HTTPException(
            status_code=403,
            detail="MCP server configuration is disabled. Set ENABLE_MCP_SERVER_CONFIGURATION=true to enable MCP features.",
        )

    try:
        # Set default timeout with a longer value for this endpoint
        timeout = 300  # Default to 300 seconds for this endpoint

        # Use custom timeout from request if provided
        if request.timeout_seconds is not None:
            timeout = request.timeout_seconds

        # Load tools from the MCP server using the utility function
        tools = await load_mcp_tools(
            server_type=request.transport,
            command=request.command,
            args=request.args,
            url=request.url,
            env=request.env,
            headers=request.headers,
            timeout_seconds=timeout,
        )

        # Create the response with tools
        response = MCPServerMetadataResponse(
            transport=request.transport,
            command=request.command,
            args=request.args,
            url=request.url,
            env=request.env,
            headers=request.headers,
            tools=tools,
        )

        return response
    except Exception as e:
        logger.exception(f"Error in MCP server metadata endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.get("/api/rag/config", response_model=RAGConfigResponse)
async def rag_config():
    """Get the config of the RAG."""
    return RAGConfigResponse(provider=SELECTED_RAG_PROVIDER)


@app.get("/api/rag/resources", response_model=RAGResourcesResponse)
async def rag_resources(request: Annotated[RAGResourceRequest, Query()]):
    """Get the resources of the RAG."""
    retriever = build_retriever()
    if retriever:
        return RAGResourcesResponse(resources=retriever.list_resources(request.query))
    return RAGResourcesResponse(resources=[])


@app.get("/api/config", response_model=ConfigResponse)
async def config():
    """Get the config of the server."""
    return ConfigResponse(
        rag=RAGConfigResponse(provider=SELECTED_RAG_PROVIDER),
        models=get_configured_llm_models(),
    )


# ============================================================================
# ASYNC RESEARCH ENDPOINTS
# ============================================================================


async def _run_research_job(job: ResearchJob, request: AsyncResearchRequest):
    """Run research job in the background"""
    try:
        # Update status to coordinating
        job_manager.update_job_status(job, ResearchStatus.COORDINATING)

        # Create thread_id
        thread_id = str(uuid4())
        job.thread_id = thread_id

        # Prepare workflow input
        workflow_input = {
            "messages": [{"role": "user", "content": request.query}],
            "plan_iterations": 0,
            "final_report": "",
            "current_plan": None,
            "observations": [],
            "auto_accepted_plan": request.auto_accepted_plan,
            "enable_background_investigation": request.enable_background_investigation,
            "research_topic": request.query,
            "search_provider": request.search_provider,
            "searches_executed": 0,
            "output_schema": request.output_schema,
            "skip_reporting": request.skip_reporting,  # Pass skip_reporting flag
        }

        # Prepare workflow config
        workflow_config = {
            "thread_id": thread_id,
            "resources": request.resources,
            "max_plan_iterations": request.max_plan_iterations,
            "max_step_num": request.max_step_num,
            "max_search_results": request.max_search_results,
            "mcp_settings": {},
            "report_style": request.report_style.value,
            "enable_deep_thinking": request.enable_deep_thinking,
            "recursion_limit": get_recursion_limit(),
        }

        # Track current agent node
        final_report_chunks = []
        researcher_findings_chunks = []
        plan_data = None
        latest_structured_output = None
        final_state = None

        # Stream and process events using astream_events for better control
        async for event in graph.astream_events(
            workflow_input,
            config=workflow_config,
            version="v2",
        ):
            event_type = event.get("event")
            event_name = event.get("name", "")
            event_data = event.get("data", {})
            metadata = event.get("metadata", {})

            # Capture structured_output from reporter_node completion
            if event_type == "on_chain_end" and "reporter" in event_name.lower():
                output = event_data.get("output", {})
                logger.debug(f"Reporter node ended with output keys: {output.keys() if isinstance(output, dict) else 'not a dict'}")
                if isinstance(output, dict) and "structured_output" in output:
                    latest_structured_output = output["structured_output"]
                    logger.info(f"✓ Captured structured_output from reporter: {json.dumps(latest_structured_output, indent=2)}")

            # Track node transitions for status updates
            if event_type == "on_chain_start":
                node_name = event_name.lower()
                logger.info(f"[NODE START] {node_name} | skip_reporting={workflow_input.get('skip_reporting', False)}")
                if "coordinator" in node_name:
                    job_manager.update_job_status(job, ResearchStatus.COORDINATING)
                elif "planner" in node_name:
                    job_manager.update_job_status(job, ResearchStatus.PLANNING)
                elif "researcher" in node_name or "coder" in node_name:
                    job_manager.update_job_status(job, ResearchStatus.RESEARCHING)
                elif "reporter" in node_name:
                    logger.warning(f"[REPORTER NODE CALLED] This should NOT happen when skip_reporting=True!")
                    job_manager.update_job_status(job, ResearchStatus.REPORTING)

            # Collect plan data
            if event_type == "on_chain_end" and "planner" in event_name.lower():
                output = event_data.get("output", {})
                if isinstance(output, dict):
                    # Extract plan from AIMessage content if present
                    messages = output.get("messages", [])
                    for msg in messages:
                        if hasattr(msg, "content") and "{" in str(msg.content):
                            try:
                                plan_text = str(msg.content)
                                start = plan_text.find("{")
                                end = plan_text.rfind("}") + 1
                                plan_json = plan_text[start:end]
                                plan_data = json.loads(plan_json)
                                job.plan = plan_data
                                break
                            except:
                                pass

            # Collect message content for report/findings
            if event_type == "on_chat_model_stream":
                chunk = event_data.get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    node = metadata.get("langgraph_node", "")
                    if "reporter" in node:
                        final_report_chunks.append(chunk.content)
                    elif "researcher" in node or "coder" in node:
                        researcher_findings_chunks.append(chunk.content)

            # Capture final state output
            if event_type == "on_chain_end" and event_name == "LangGraph":
                output = event_data.get("output", {})
                if isinstance(output, dict):
                    final_state = output
                    logger.info(f"Captured final state with keys: {list(output.keys())}")

        # Mark as completed
        job.final_report = "".join(final_report_chunks) if final_report_chunks else None

        # When skip_reporting=True, use observations from final_state as researcher_findings
        if request.skip_reporting and final_state:
            observations = final_state.get("observations", [])
            if observations:
                # Format observations as structured text
                formatted_observations = "\n\n---\n\n".join(observations)
                job.researcher_findings = formatted_observations
                logger.info(f"Populated researcher_findings from {len(observations)} observations (skip_reporting=True)")
            else:
                logger.warning(f"No observations found in final state despite skip_reporting=True")
        else:
            # Use streamed researcher content (legacy behavior)
            job.researcher_findings = (
                "".join(researcher_findings_chunks) if researcher_findings_chunks else None
            )

        # Use structured output captured from stream or from final_state
        if latest_structured_output:
            job.structured_output = latest_structured_output
            logger.info(f"Set structured_output from stream for job {job.job_id}: {latest_structured_output}")
        elif final_state and final_state.get("structured_output"):
            job.structured_output = final_state.get("structured_output")
            logger.info(f"Set structured_output from final_state for job {job.job_id}")
        else:
            logger.warning(f"No structured_output captured from stream for job {job.job_id}")

        job_manager.update_job_status(job, ResearchStatus.COMPLETED)

        # Save job result to database
        job_manager.save_job_result(job)

        logger.info(f"Research job {job.job_id} completed successfully")

    except Exception as e:
        logger.exception(f"Error in research job {job.job_id}")
        job.set_error(str(e))


@app.post(
    "/api/research/async",
    response_model=AsyncResearchResponse,
    tags=["Jobs"],
    summary="Start async research job",
    description="""
    Submit a research query and receive a job_id for tracking progress asynchronously.

    This endpoint immediately returns a job_id without waiting for research to complete.
    Use the job_id to poll `/api/research/{job_id}/status` for progress updates and
    `/api/research/{job_id}/result` to retrieve the final report when completed.

    **Workflow:**
    1. POST to this endpoint with your query
    2. Receive job_id immediately
    3. Poll `/api/research/{job_id}/status` until status is 'completed'
    4. GET `/api/research/{job_id}/result` to retrieve final report and structured output

    **Authentication**: Required (unless SKIP_AUTH=true)
    """,
)
async def start_async_research(
    request: AsyncResearchRequest,
    auth: Optional[Dict[str, str]] = Depends(optional_verify_api_key),
):
    """
    Start an asynchronous research job.

    Returns a job_id that can be used to check status and retrieve results.
    """
    try:
        # Extract user info from auth (if available)
        user_id = auth.get("user_id") if auth else None
        api_key_name = auth.get("api_key_name") if auth else None

        # Create job with full parameters for database storage
        job = job_manager.create_job(
            query=request.query,
            report_style=request.report_style.value,
            max_step_num=request.max_step_num,
            max_search_results=request.max_search_results,
            search_provider=request.search_provider,
            enable_background_investigation=request.enable_background_investigation,
            enable_deep_thinking=request.enable_deep_thinking,
            auto_accepted_plan=request.auto_accepted_plan,
            output_schema=request.output_schema,
            resources=request.resources,
            user_id=user_id,
            api_key_name=api_key_name,
        )

        # Start background task
        job.task = asyncio.create_task(_run_research_job(job, request))

        return AsyncResearchResponse(
            job_id=job.job_id,
            status=job.status,
            message="Research job started successfully",
        )

    except Exception as e:
        logger.exception("Error starting async research")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/research/sync",
    response_model=ResearchResultResponse,
    tags=["Jobs"],
    summary="Run synchronous research",
    description="""
    Run research synchronously and return results immediately.

    This endpoint blocks until research completes and returns the full result.
    By default, it skips report generation (skip_reporting=True) for faster execution,
    returning only observations and plan. Set skip_reporting=False to include the final report.

    **Performance:**
    - With skip_reporting=True (default): ~20-40s (no markdown generation)
    - With skip_reporting=False: ~30-60s (includes full report)

    **Use Cases:**
    - API integrations needing raw research data
    - Applications building custom reports from observations
    - Speed-critical workflows

    **Optimization Tips:**
    - Use max_plan_iterations=1, max_step_num=2-3 for fastest results
    - Reduce max_search_results to 2 for lower token usage
    - Disable enable_background_investigation for speed

    **Authentication**: Required (unless SKIP_AUTH=true)
    """,
)
async def sync_research(
    request: AsyncResearchRequest,
    auth: Optional[Dict[str, str]] = Depends(optional_verify_api_key),
):
    """
    Run research synchronously with optional report skipping.

    By default, skips reporter node (skip_reporting=True) for 5-10s faster execution.
    Returns observations, plan, and optional structured output immediately.
    """
    try:
        # Override skip_reporting to True by default for sync endpoint
        if request.skip_reporting is None:
            request.skip_reporting = True

        # Extract user info from auth (if available)
        user_id = auth.get("user_id") if auth else None
        api_key_name = auth.get("api_key_name") if auth else None

        # Create job
        job = job_manager.create_job(
            query=request.query,
            report_style=request.report_style.value,
            max_step_num=request.max_step_num,
            max_search_results=request.max_search_results,
            search_provider=request.search_provider,
            enable_background_investigation=request.enable_background_investigation,
            enable_deep_thinking=request.enable_deep_thinking,
            auto_accepted_plan=request.auto_accepted_plan,
            output_schema=request.output_schema,
            resources=request.resources,
            user_id=user_id,
            api_key_name=api_key_name,
        )

        # Run research synchronously (await instead of background task)
        await _run_research_job(job, request)

        # Return result immediately
        return ResearchResultResponse(
            job_id=job.job_id,
            status=job.status,
            thread_id=job.thread_id or "",
            query=job.query,
            final_report=job.final_report,
            researcher_findings=job.researcher_findings,
            plan=job.plan,
            structured_output=job.structured_output,
            error=job.error,
            created_at=job.created_at.isoformat(),
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            duration_seconds=(
                (job.completed_at - job.created_at).total_seconds()
                if job.completed_at
                else None
            ),
        )

    except Exception as e:
        logger.exception("Error in sync research")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/research/{job_id}/status",
    response_model=ResearchStatusResponse,
    tags=["Jobs"],
    summary="Check job status",
    description="""
    Get the current status of an async research job.

    Poll this endpoint every 2-5 seconds to track research progress.

    **Status values:**
    - `pending`: Job is queued, not started yet
    - `coordinating`: Router agent is analyzing the query
    - `planning`: Planner agent is creating the research plan
    - `researching`: Researcher/Coder agents are gathering information
    - `reporting`: Reporter agent is generating the final report
    - `completed`: Research finished successfully (call /result to get data)
    - `failed`: Job encountered an error (check error field)

    **Authentication**: Required (unless SKIP_AUTH=true)
    """,
)
async def get_research_status(
    job_id: str,
    auth: Optional[Dict[str, str]] = Depends(optional_verify_api_key),
):
    """
    Get the current status of a research job.

    Poll this endpoint to track progress:
    - pending: Job is queued
    - coordinating: Job is being routed
    - planning: Creating research plan
    - researching: Actively searching and gathering information
    - reporting: Generating final report
    - completed: Research is done (fetch results from /result endpoint)
    - failed: Job failed (check error field)
    """
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return ResearchStatusResponse(
        job_id=job.job_id,
        status=job.status,
        error=job.error,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


@app.get(
    "/api/research/{job_id}/result",
    response_model=ResearchResultResponse,
    tags=["Jobs"],
    summary="Get job results",
    description="""
    Retrieve the final research report and structured data from a completed job.

    **Important:** Only call this endpoint after `/status` returns `status='completed'`.

    **Response includes:**
    - `final_report`: Markdown-formatted research report
    - `structured_output`: JSON data (if output_schema was provided in request)
    - `researcher_findings`: Raw observations from research steps
    - `plan`: The research plan that was executed
    - `duration_seconds`: How long the research took

    **Authentication**: Required (unless SKIP_AUTH=true)
    """,
)
async def get_research_result(
    job_id: str,
    auth: Optional[Dict[str, str]] = Depends(optional_verify_api_key),
):
    """
    Get the final result of a completed research job.

    Only call this after status endpoint returns 'completed' status.
    """
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return ResearchResultResponse(
        job_id=job.job_id,
        status=job.status,
        thread_id=job.thread_id or "",
        query=job.query,
        final_report=job.final_report,
        researcher_findings=job.researcher_findings,
        plan=job.plan,
        structured_output=job.structured_output,
        error=job.error,
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        duration_seconds=job.get_duration_seconds(),
    )


@app.delete(
    "/api/research/{job_id}",
    tags=["Jobs"],
    summary="Cancel/delete job",
    description="""
    Cancel a running job or delete a completed job from memory.

    **Use cases:**
    - Stop a long-running job that's no longer needed
    - Clean up completed jobs to free memory

    **Note:** Jobs are automatically cleaned up after 24 hours.

    **Authentication**: Required (unless SKIP_AUTH=true)
    """,
)
async def cancel_research_job(
    job_id: str,
    auth: Optional[Dict[str, str]] = Depends(optional_verify_api_key),
):
    """
    Cancel and delete a research job.

    Can be used to stop running jobs or clean up completed jobs.
    """
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job_manager.delete_job(job_id)

    return {"message": f"Job {job_id} cancelled and deleted", "job_id": job_id}


async def _run_person_research_job(
    job: ResearchJob,
    request: PersonResearchRequest,
    enriched_query: Optional[str] = None
):
    """Run person research job synchronously"""
    try:
        job_manager.update_job_status(job, ResearchStatus.COORDINATING)

        # Create thread_id
        thread_id = str(uuid4())
        job.thread_id = thread_id

        # Use enriched query if provided (after disambiguation), otherwise use person_name
        query = enriched_query or request.person_name

        # Prepare workflow input
        workflow_input = {
            "messages": [{"role": "user", "content": query}],
            "plan_iterations": 0,
            "final_report": "",
            "observations": [],
            "auto_accepted_plan": True,  # Always auto-accept for person search
            "enable_background_investigation": False,  # Skip background - we already did quick search
            "research_topic": query,
            "search_provider": "tavily",
            "searches_executed": 0,
            "output_schema": request.output_schema or DEFAULT_PERSON_SCHEMA,
            "person_search_mode": True,  # Enable person search mode
            "person_name": request.person_name,
            "person_company": request.company,
            "person_context": request.additional_context,
        }

        # Prepare workflow config
        workflow_config = {
            "thread_id": thread_id,
            "resources": [],
            "max_plan_iterations": request.max_plan_iterations,
            "max_step_num": request.max_step_num,
            "max_search_results": 3,
            "mcp_settings": {},
            "report_style": request.report_style,
            "enable_deep_thinking": False,
            "recursion_limit": get_recursion_limit(),
        }

        # Track output
        final_report_chunks = []
        latest_structured_output = None
        disambiguation_candidates = None
        selected_candidate = None

        # Stream and process events
        async for event in graph.astream_events(
            workflow_input,
            config=workflow_config,
            version="v2",
        ):
            event_type = event.get("event")
            event_name = event.get("name", "")
            event_data = event.get("data", {})
            metadata = event.get("metadata", {})

            # Capture structured_output from reporter_node
            if event_type == "on_chain_end" and "reporter" in event_name.lower():
                output = event_data.get("output", {})
                if isinstance(output, dict) and "structured_output" in output:
                    latest_structured_output = output["structured_output"]
                    logger.info(f"Captured structured_output for person: {latest_structured_output}")

            # Capture disambiguation candidates from person_disambiguator_node
            if event_type == "on_chain_end" and "person_disambiguator" in event_name.lower():
                output = event_data.get("output", {})
                if isinstance(output, dict):
                    disambiguation_candidates = output.get("disambiguation_candidates")
                    selected_candidate = output.get("selected_candidate")
                    logger.info(f"Disambiguation result: {len(disambiguation_candidates) if disambiguation_candidates else 0} candidates")

            # Track status
            if event_type == "on_chain_start":
                node_name = event_name.lower()
                if "person_disambiguator" in node_name:
                    job_manager.update_job_status(job, ResearchStatus.COORDINATING)
                elif "planner" in node_name:
                    job_manager.update_job_status(job, ResearchStatus.PLANNING)
                elif "researcher" in node_name or "coder" in node_name:
                    job_manager.update_job_status(job, ResearchStatus.RESEARCHING)
                elif "reporter" in node_name:
                    job_manager.update_job_status(job, ResearchStatus.REPORTING)

            # Collect report content
            if event_type == "on_chat_model_stream":
                chunk = event_data.get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    node = metadata.get("langgraph_node", "")
                    if "reporter" in node:
                        final_report_chunks.append(chunk.content)

        # Check if disambiguation is needed
        if disambiguation_candidates and len(disambiguation_candidates) > 0:
            logger.info(f"Person research requires disambiguation: {len(disambiguation_candidates)} candidates")
            return {
                "disambiguation_needed": True,
                "candidates": disambiguation_candidates,
            }

        # Otherwise, we have the final result
        job.final_report = "".join(final_report_chunks) if final_report_chunks else None
        job.structured_output = latest_structured_output

        job_manager.update_job_status(job, ResearchStatus.COMPLETED)
        job_manager.save_job_result(job)

        logger.info(f"Person research job {job.job_id} completed successfully")

        return {
            "disambiguation_needed": False,
            "final_report": job.final_report,
            "structured_output": job.structured_output,
            "selected_candidate": selected_candidate,
        }

    except Exception as e:
        logger.exception(f"Error in person research job {job.job_id}")
        job.set_error(str(e))
        raise


# DEACTIVATED - Use /api/quickresearch instead
# @app.post(
#     "/api/research/person",
#     response_model=PersonResearchResponse,
#     tags=["Research"],
#     summary="Research a person (synchronous)",
#     description="""
#     Search and research a specific person. Returns either:
#     1. Complete research report (if single person identified)
#     2. List of candidates for disambiguation (if multiple people found)
#     3. Error (if no person found)

#     **This endpoint blocks** until research completes or disambiguation is needed.

#     **Workflow:**
#     - Single match → Returns completed research immediately
#     - Multiple matches → Returns candidates list, call `/api/research/person/{job_id}/disambiguate`
#     - No match → Returns error

#     **Authentication**: Required (unless SKIP_AUTH=true)
#     """,
# )
# async def research_person(
#     request: PersonResearchRequest,
#     auth: Optional[Dict[str, str]] = Depends(optional_verify_api_key),
# ):
#     """
#     Research a person with optional disambiguation.

#     If multiple people match, returns candidates for user to choose from.
#     """
#     try:
#         # Extract user info from auth
#         user_id = auth.get("user_id") if auth else None
#         api_key_name = auth.get("api_key_name") if auth else None
#
#         # Build search query
#         query_parts = [request.person_name]
#         if request.company:
#             query_parts.append(request.company)
#         if request.additional_context:
#             query_parts.append(request.additional_context)
#         query = " ".join(query_parts)
#
#         # Create job
#         job = job_manager.create_job(
#             query=query,
#             report_style=request.report_style,
#             max_step_num=request.max_step_num,
#             max_search_results=3,
#             search_provider="tavily",
#             enable_background_investigation=False,
#             enable_deep_thinking=False,
#             auto_accepted_plan=True,
#             output_schema=request.output_schema or DEFAULT_PERSON_SCHEMA,
#             resources=[],
#             user_id=user_id,
#             api_key_name=api_key_name,
#         )
#
#         # Run research synchronously
#         result = await _run_person_research_job(job, request)
#
#         # Check if disambiguation needed
#         if result.get("disambiguation_needed"):
#             candidates = result["candidates"]
#             return PersonResearchResponse(
#                 job_id=job.job_id,
#                 status="awaiting_disambiguation",
#                 message=f"Found {len(candidates)} people matching '{request.person_name}'",
#                 candidates=[Candidate(**c) for c in candidates],
#             )
#
#         # Return completed research
#         return PersonResearchResponse(
#             job_id=job.job_id,
#             status="completed",
#             final_report=result["final_report"],
#             structured_output=result["structured_output"],
#             selected_candidate=Candidate(**result["selected_candidate"]) if result.get("selected_candidate") else None,
#         )
#
#     except Exception as e:
#         logger.exception("Error in person research")
#         # Create a failed job for error tracking
#         job = job_manager.create_job(query=request.person_name)
#         job.set_error(str(e))
#         raise HTTPException(
#             status_code=500,
#             detail=str(e)
#         )


# DEACTIVATED - Use /api/quickresearch instead
# @app.post(
#     "/api/research/person/{job_id}/disambiguate",
#     response_model=PersonResearchResponse,
#     tags=["Research"],
#     summary="Select person candidate and complete research",
#     description="""
#     After receiving candidates from `/api/research/person`, use this endpoint to:
#     1. Select the correct person by candidate ID
#     2. Optionally provide additional context
#     3. Complete the full research
#
#     **This endpoint blocks** until research completes.
#
#     Returns the complete research report and structured output.
#
#     **Authentication**: Required (unless SKIP_AUTH=true)
#     """,
# )
# async def disambiguate_person(
#     job_id: str,
#     request: DisambiguationRequest,
#     auth: Optional[Dict[str, str]] = Depends(optional_verify_api_key),
# ):
#     """
#     Complete person research after disambiguation.
#
#     Select a candidate from the disambiguation list and run full research.
#     """
#     try:
#         # Get the job
#         job = job_manager.get_job(job_id)
#         if not job:
#             raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
#
#         # Validate job is awaiting disambiguation
#         if job.status != ResearchStatus.COMPLETED:
#             # The job should be in memory with candidates stored
#             # For now, we'll need to re-run from the beginning with enriched context
#             pass
#
#         # We need to get the candidates from somewhere
#         # Since we're using state-only approach, we need to fetch from the graph state
#         # For simplicity, we'll reconstruct the research request with enriched query
#
#         # Build enriched query from selected candidate ID
#         # This is a simplified approach - in production, you'd store candidates in job
#         enriched_query = f"{request.selected_candidate_id}"
#         if request.additional_context:
#             enriched_query += f" {request.additional_context}"
#
#         # Create a new request with enriched context
#         person_request = PersonResearchRequest(
#             person_name=enriched_query,
#             report_style="sales_intelligence",
#             max_plan_iterations=1,
#             max_step_num=1,
#         )
#
#         # Run research with enriched query
#         result = await _run_person_research_job(job, person_request, enriched_query=enriched_query)
#
#         # Should not need disambiguation again
#         if result.get("disambiguation_needed"):
#             raise HTTPException(
#                 status_code=500,
#                 detail="Unexpected disambiguation required after selection"
#             )
#
#         # Return completed research
#         return PersonResearchResponse(
#             job_id=job.job_id,
#             status="completed",
#             final_report=result["final_report"],
#             structured_output=result["structured_output"],
#             selected_candidate=Candidate(**result["selected_candidate"]) if result.get("selected_candidate") else None,
#         )
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.exception(f"Error in person disambiguation for job {job_id}")
#         raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/quickresearch",
    response_model=PersonResearchResponse,
    tags=["Research"],
    summary="Quick person research (fast, no planner loop)",
    description="""
    Fast person research that skips the planner loop for quick results.

    **Flow:** coordinator → person_disambiguator → reporter (10-20s vs 30-60s)

    Returns either:
    1. Quick research report (if single person identified)
    2. List of candidates for disambiguation (if multiple people found)
    3. Error (if no person found)

    **This endpoint blocks** until research completes or disambiguation is needed.

    **Workflow:**
    - Single match → Returns quick report immediately (10-20s)
    - Multiple matches → Returns candidates list for disambiguation
    - No match → Returns error

    **Authentication**: Required (unless SKIP_AUTH=true)
    """,
)
async def quick_research_person(
    request: PersonResearchRequest,
    auth: Optional[Dict[str, str]] = Depends(optional_verify_api_key),
):
    """
    Fast person research with no planner loop.

    Uses simplified graph: coordinator → person_disambiguator → reporter
    """
    try:
        # Extract user info from auth
        user_id = auth.get("user_id") if auth else None
        api_key_name = auth.get("api_key_name") if auth else None

        # Build search query
        query_parts = [request.person_name]
        if request.company:
            query_parts.append(request.company)
        if request.additional_context:
            query_parts.append(request.additional_context)
        query = " ".join(query_parts)

        # Create job
        job = job_manager.create_job(
            query=query,
            report_style=request.report_style,
            max_step_num=request.max_step_num,
            max_search_results=3,
            search_provider="tavily",
            enable_background_investigation=False,
            enable_deep_thinking=False,
            auto_accepted_plan=True,
            output_schema=request.output_schema or DEFAULT_PERSON_SCHEMA,
            resources=[],
            user_id=user_id,
            api_key_name=api_key_name,
        )

        # Run quick research
        job_manager.update_job_status(job, ResearchStatus.COORDINATING)

        # Create thread_id
        thread_id = str(uuid4())
        job.thread_id = thread_id

        # Prepare workflow input with quick_research_mode enabled
        workflow_input = {
            "messages": [{"role": "user", "content": query}],
            "plan_iterations": 0,
            "final_report": "",
            "observations": [],
            "auto_accepted_plan": True,
            "enable_background_investigation": False,
            "research_topic": query,
            "search_provider": "tavily",
            "searches_executed": 0,
            "output_schema": request.output_schema or DEFAULT_PERSON_SCHEMA,
            "person_search_mode": True,
            "quick_research_mode": True,  # Enable quick research mode
            "person_name": request.person_name,
            "person_company": request.company,
            "person_context": request.additional_context,
        }

        # Prepare workflow config
        workflow_config = {
            "thread_id": thread_id,
            "resources": [],
            "max_plan_iterations": 0,  # No planning in quick mode
            "max_step_num": 0,  # No research steps
            "max_search_results": 3,
            "mcp_settings": {},
            "report_style": request.report_style,
            "enable_deep_thinking": False,
            "recursion_limit": get_recursion_limit(),
        }

        # Track output
        final_report_chunks = []
        latest_structured_output = None
        disambiguation_candidates = None
        selected_candidate = None

        # Stream and process events using quick_research_graph
        async for event in quick_research_graph.astream_events(
            workflow_input,
            config=workflow_config,
            version="v2",
        ):
            event_type = event.get("event")
            event_name = event.get("name", "")
            event_data = event.get("data", {})
            metadata = event.get("metadata", {})

            # Capture structured_output from reporter_node
            if event_type == "on_chain_end" and "reporter" in event_name.lower():
                output = event_data.get("output", {})
                if isinstance(output, dict) and "structured_output" in output:
                    latest_structured_output = output["structured_output"]
                    logger.info(f"Captured structured_output for quick research: {latest_structured_output}")

            # Capture disambiguation candidates from person_disambiguator_node
            if event_type == "on_chain_end" and "person_disambiguator" in event_name.lower():
                output = event_data.get("output", {})
                if isinstance(output, dict):
                    disambiguation_candidates = output.get("disambiguation_candidates")
                    selected_candidate = output.get("selected_candidate")
                    logger.info(f"Quick research disambiguation result: {len(disambiguation_candidates) if disambiguation_candidates else 0} candidates")

            # Track status
            if event_type == "on_chain_start":
                node_name = event_name.lower()
                if "person_disambiguator" in node_name:
                    job_manager.update_job_status(job, ResearchStatus.COORDINATING)
                elif "reporter" in node_name:
                    job_manager.update_job_status(job, ResearchStatus.REPORTING)

            # Collect report content
            if event_type == "on_chat_model_stream":
                chunk = event_data.get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    node = metadata.get("langgraph_node", "")
                    if "reporter" in node:
                        final_report_chunks.append(chunk.content)

        # Check if disambiguation is needed
        if disambiguation_candidates and len(disambiguation_candidates) > 0:
            logger.info(f"Quick research requires disambiguation: {len(disambiguation_candidates)} candidates")
            return PersonResearchResponse(
                job_id=job.job_id,
                status="awaiting_disambiguation",
                message=f"Found {len(disambiguation_candidates)} people matching '{request.person_name}'",
                candidates=[Candidate(**c) for c in disambiguation_candidates],
            )

        # Otherwise, we have the final result
        job.final_report = "".join(final_report_chunks) if final_report_chunks else None
        job.structured_output = latest_structured_output

        job_manager.update_job_status(job, ResearchStatus.COMPLETED)
        job_manager.save_job_result(job)

        logger.info(f"Quick research job {job.job_id} completed successfully")

        return PersonResearchResponse(
            job_id=job.job_id,
            status="completed",
            final_report=job.final_report,
            structured_output=job.structured_output,
            selected_candidate=Candidate(**selected_candidate) if selected_candidate else None,
        )

    except Exception as e:
        logger.exception("Error in quick research")
        # Create a failed job for error tracking
        job = job_manager.create_job(query=request.person_name)
        job.set_error(str(e))
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# Start cleanup task on startup
@app.on_event("startup")
async def startup_event():
    """Start background tasks on app startup"""
    job_manager.start_cleanup_task()
    logger.info("Job manager cleanup task started")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on app shutdown"""
    job_manager.stop_cleanup_task()
    logger.info("Job manager cleanup task stopped")
