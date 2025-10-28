# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import os
from typing import Annotated, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.types import Command, interrupt
from functools import partial

from src.agents import create_agent
from src.config.agents import AGENT_LLM_MAP
from src.config.configuration import Configuration
from src.llms.llm import get_llm_by_type, get_llm_token_limit_by_type
from src.prompts.planner_model import Plan
from src.prompts.template import apply_prompt_template
from src.tools import (
    crawl_tool,
    get_retriever_tool,
    get_web_search_tool,
    python_repl_tool,
)
from src.tools.search import LoggedTavilySearch
from src.config.person_schema import CANDIDATE_SCHEMA
from src.utils.json_utils import repair_json_output
from src.utils.context_manager import ContextManager

from ..config import SELECTED_SEARCH_ENGINE, SearchEngine
from .types import State

logger = logging.getLogger(__name__)


@tool
def handoff_to_planner(
    research_topic: Annotated[str, "The topic of the research task to be handed off."],
    locale: Annotated[str, "The user's detected language locale (e.g., en-US, zh-CN)."],
):
    """Handoff to planner agent to do plan."""
    # This tool is not returning anything: we're just using it
    # as a way for LLM to signal that it needs to hand off to planner agent
    return


def person_disambiguator_node(
    state: State, config: RunnableConfig
) -> Command[Literal["planner", "reporter", "__end__"]]:
    """
    Quick person search to identify candidates.
    Returns candidates for disambiguation if multiple people found,
    or enriched query if single person identified.
    Routes to reporter in quick_research_mode, planner otherwise.
    """
    logger.info("Person disambiguator node is running")
    configurable = Configuration.from_runnable_config(config)

    # Check if we're in quick research mode
    quick_research_mode = state.get("quick_research_mode", False)
    next_node = "reporter" if quick_research_mode else "planner"
    logger.info(f"Quick research mode: {quick_research_mode}, next node: {next_node}")

    # Extract person search parameters
    person_name = state.get("person_name") or state.get("research_topic", "")
    person_company = state.get("person_company")
    person_context = state.get("person_context")

    logger.info(f"Searching for: {person_name}, company: {person_company}, context: {person_context}")

    # Strategy: Do 2 targeted searches for better disambiguation
    # Search 1: Broad search with just the name
    # Search 2: Specific search with name + company (if provided)
    try:
        all_search_results = []

        # Search 1: Broad person name search
        broad_query = person_name
        logger.info(f"Search 1 (broad): {broad_query}")

        if SELECTED_SEARCH_ENGINE == SearchEngine.TAVILY.value:
            results1 = LoggedTavilySearch(max_results=3).invoke(broad_query)
            if isinstance(results1, tuple):
                results1 = results1[0]
        else:
            results1 = get_web_search_tool(3).invoke(broad_query)

        if isinstance(results1, list):
            all_search_results.extend(results1)
            logger.info(f"Broad search returned {len(results1)} results")

        # Search 2: Specific search with company (if provided)
        if person_company:
            specific_query = f"{person_name} {person_company}"
            logger.info(f"Search 2 (specific): {specific_query}")

            if SELECTED_SEARCH_ENGINE == SearchEngine.TAVILY.value:
                results2 = LoggedTavilySearch(max_results=3).invoke(specific_query)
                if isinstance(results2, tuple):
                    results2 = results2[0]
            else:
                results2 = get_web_search_tool(3).invoke(specific_query)

            if isinstance(results2, list):
                all_search_results.extend(results2)
                logger.info(f"Specific search returned {len(results2)} results")

        logger.info(f"Total search results: {len(all_search_results)}")

        # Log all search results for debugging
        for idx, result in enumerate(all_search_results):
            logger.info(f"Result {idx+1}: {result.get('title', 'No title')}")
            logger.debug(f"Content preview: {result.get('content', result.get('snippet', ''))[:200]}...")

        # Format all search results for LLM
        formatted_results = "\n\n".join([
            f"## {result.get('title', 'No title')}\n{result.get('content', result.get('snippet', ''))}"
            for result in all_search_results
        ])

        # Use LLM to extract candidates
        prompt_content = f"""Analyze these search results for "{person_name}" and identify distinct individuals.

# Search Results

{formatted_results}

# Task

Extract a list of distinct person candidates. For each person found, provide:
- Unique ID (candidate_1, candidate_2, etc.)
- Full name
- Current title
- Current company
- Location
- LinkedIn URL if found
- Brief distinguishing summary (50-100 words)

**Instructions:**
- If search results show MULTIPLE distinct people (different companies, locations, industries), list ALL of them
- If ALL search results clearly refer to the SAME person (same LinkedIn, company, career history), return ONE candidate
- When in doubt between one or multiple, return MULTIPLE candidates - better to ask than guess wrong
- If NO clear person match is found, return an empty candidates array
"""

        # Load disambiguation prompt
        with open(os.path.join(os.path.dirname(__file__), "../prompts/person_disambiguator.md"), 'r') as f:
            system_prompt = f.read()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_content}
        ]

        # Get structured output from LLM
        structured_llm = get_llm_by_type("basic").with_structured_output(
            schema=CANDIDATE_SCHEMA,
            method="json_mode"
        )

        response = structured_llm.invoke(messages)
        candidates_data = response if isinstance(response, dict) else json.loads(str(response))
        candidates = candidates_data.get("candidates", [])

        logger.info(f"Extracted {len(candidates)} candidate(s)")

        # Decide next action based on number of candidates
        if len(candidates) == 0:
            # No person found
            logger.warning("No person candidates found")
            raise ValueError(f"Could not identify person matching '{person_name}' in search results")

        elif len(candidates) == 1:
            # Single person found - enrich query and continue
            candidate = candidates[0]
            enriched_query = f"{candidate['name']}"
            if candidate.get('title'):
                enriched_query += f" {candidate['title']}"
            if candidate.get('company'):
                enriched_query += f" at {candidate['company']}"
            if candidate.get('location'):
                enriched_query += f" in {candidate['location']}"

            logger.info(f"Single candidate identified. Enriched query: {enriched_query}")

            # In quick research mode, store search results as observations for reporter
            update_dict = {
                "enriched_person_query": enriched_query,
                "selected_candidate": candidate,
                "disambiguation_candidates": None,
                "research_topic": enriched_query,  # Update research topic with enriched version
            }

            # Add search results as observations only in quick research mode
            if quick_research_mode:
                # Format search results as observations for the reporter
                observations = [
                    f"Person identified: {candidate['name']}\n"
                    f"Title: {candidate.get('title', 'N/A')}\n"
                    f"Company: {candidate.get('company', 'N/A')}\n"
                    f"Location: {candidate.get('location', 'N/A')}\n"
                    f"Summary: {candidate.get('summary', 'N/A')}\n"
                    f"LinkedIn: {candidate.get('linkedin', 'N/A')}"
                ]
                update_dict["observations"] = observations

            return Command(
                update=update_dict,
                goto=next_node,  # Route to reporter in quick mode, planner otherwise
            )

        else:
            # Multiple people found - need disambiguation, end workflow
            logger.info(f"Multiple candidates found, requiring disambiguation")
            return Command(
                update={
                    "disambiguation_candidates": candidates,
                    "enriched_person_query": None,
                    "selected_candidate": None,
                },
                goto="__end__",  # End workflow to wait for user selection
            )

    except Exception as e:
        logger.error(f"Error in person disambiguation: {e}", exc_info=True)
        raise


def background_investigation_node(state: State, config: RunnableConfig):
    logger.info("background investigation node is running.")
    configurable = Configuration.from_runnable_config(config)
    query = state.get("research_topic")
    background_investigation_results = None
    if SELECTED_SEARCH_ENGINE == SearchEngine.TAVILY.value:
        searched_content = LoggedTavilySearch(
            max_results=configurable.max_search_results
        ).invoke(query)
        # check if the searched_content is a tuple, then we need to unpack it
        if isinstance(searched_content, tuple):
            searched_content = searched_content[0]
        if isinstance(searched_content, list):
            background_investigation_results = [
                f"## {elem['title']}\n\n{elem['content']}" for elem in searched_content
            ]
            return {
                "background_investigation_results": "\n\n".join(
                    background_investigation_results
                )
            }
        else:
            logger.error(
                f"Tavily search returned malformed response: {searched_content}"
            )
    else:
        background_investigation_results = get_web_search_tool(
            configurable.max_search_results
        ).invoke(query)
    return {
        "background_investigation_results": json.dumps(
            background_investigation_results, ensure_ascii=False
        )
    }


def planner_node(
    state: State, config: RunnableConfig
) -> Command[Literal["human_feedback", "reporter"]]:
    """Planner node that generate the full plan."""
    logger.info("Planner generating full plan")
    configurable = Configuration.from_runnable_config(config)
    plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
    messages = apply_prompt_template("planner", state, configurable)

    if state.get("enable_background_investigation") and state.get(
        "background_investigation_results"
    ):
        messages += [
            {
                "role": "user",
                "content": (
                    "background investigation results of user query:\n"
                    + state["background_investigation_results"]
                    + "\n"
                ),
            }
        ]

    if configurable.enable_deep_thinking:
        llm = get_llm_by_type("reasoning")
    elif AGENT_LLM_MAP["planner"] == "basic":
        llm = get_llm_by_type("basic").with_structured_output(
            Plan,
            method="json_mode",
        )
    else:
        llm = get_llm_by_type(AGENT_LLM_MAP["planner"])

    # if the plan iterations is greater than the max plan iterations, go to reporter or end based on skip_reporting
    if plan_iterations >= configurable.max_plan_iterations:
        if state.get("skip_reporting", False):
            return Command(goto="__end__")
        return Command(goto="reporter")

    full_response = ""
    if AGENT_LLM_MAP["planner"] == "basic" and not configurable.enable_deep_thinking:
        response = llm.invoke(messages)
        full_response = response.model_dump_json(indent=4, exclude_none=True)
    else:
        response = llm.stream(messages)
        for chunk in response:
            full_response += chunk.content
    logger.debug(f"Current state messages: {state['messages']}")
    logger.info(f"Planner response: {full_response}")

    try:
        curr_plan = json.loads(repair_json_output(full_response))
    except json.JSONDecodeError:
        logger.warning("Planner response is not a valid JSON")
        if plan_iterations > 0:
            return Command(goto="reporter")
        else:
            return Command(goto="__end__")
    if isinstance(curr_plan, dict) and curr_plan.get("has_enough_context"):
        logger.info("Planner response has enough context.")
        new_plan = Plan.model_validate(curr_plan)
        # Check if reporting should be skipped
        goto_node = "__end__" if state.get("skip_reporting", False) else "reporter"
        return Command(
            update={
                "messages": [AIMessage(content=full_response, name="planner")],
                "current_plan": new_plan,
            },
            goto=goto_node,
        )
    return Command(
        update={
            "messages": [AIMessage(content=full_response, name="planner")],
            "current_plan": full_response,
        },
        goto="human_feedback",
    )


def human_feedback_node(
    state,
) -> Command[Literal["planner", "research_team", "reporter", "__end__"]]:
    current_plan = state.get("current_plan", "")
    # check if the plan is auto accepted
    auto_accepted_plan = state.get("auto_accepted_plan", False)
    if not auto_accepted_plan:
        feedback = interrupt("Please Review the Plan.")

        # if the feedback is not accepted, return the planner node
        if feedback and str(feedback).upper().startswith("[EDIT_PLAN]"):
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=feedback, name="feedback"),
                    ],
                },
                goto="planner",
            )
        elif feedback and str(feedback).upper().startswith("[ACCEPTED]"):
            logger.info("Plan is accepted by user.")
        else:
            raise TypeError(f"Interrupt value of {feedback} is not supported.")

    # if the plan is accepted, run the following node
    plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
    goto = "research_team"
    try:
        current_plan = repair_json_output(current_plan)
        # increment the plan iterations
        plan_iterations += 1
        # parse the plan
        new_plan = json.loads(current_plan)
    except json.JSONDecodeError:
        logger.warning("Planner response is not a valid JSON")
        if plan_iterations > 1:  # the plan_iterations is increased before this check
            goto_node = "__end__" if state.get("skip_reporting", False) else "reporter"
            return Command(goto=goto_node)
        else:
            return Command(goto="__end__")

    return Command(
        update={
            "current_plan": Plan.model_validate(new_plan),
            "plan_iterations": plan_iterations,
            "locale": new_plan["locale"],
        },
        goto=goto,
    )


def coordinator_node(
    state: State, config: RunnableConfig
) -> Command[Literal["planner", "background_investigator", "person_disambiguator", "__end__"]]:
    """Coordinator node that communicate with customers."""
    logger.info("Coordinator talking.")
    configurable = Configuration.from_runnable_config(config)

    # Check if person search mode is enabled
    if state.get("person_search_mode"):
        logger.info("Person search mode enabled - routing to person_disambiguator")
        return Command(
            update={
                "messages": state.get("messages", []),
                "locale": state.get("locale", "en-US"),
                "research_topic": state.get("research_topic", ""),
                "resources": configurable.resources,
            },
            goto="person_disambiguator",
        )

    messages = apply_prompt_template("coordinator", state)
    response = (
        get_llm_by_type(AGENT_LLM_MAP["coordinator"])
        .bind_tools([handoff_to_planner])
        .invoke(messages)
    )
    logger.debug(f"Current state messages: {state['messages']}")

    goto = "__end__"
    locale = state.get("locale", "en-US")  # Default locale if not specified
    research_topic = state.get("research_topic", "")

    if len(response.tool_calls) > 0:
        goto = "planner"
        if state.get("enable_background_investigation"):
            # if the search_before_planning is True, add the web search tool to the planner agent
            goto = "background_investigator"
        try:
            for tool_call in response.tool_calls:
                if tool_call.get("name", "") != "handoff_to_planner":
                    continue
                if tool_call.get("args", {}).get("locale") and tool_call.get(
                    "args", {}
                ).get("research_topic"):
                    locale = tool_call.get("args", {}).get("locale")
                    research_topic = tool_call.get("args", {}).get("research_topic")
                    break
        except Exception as e:
            logger.error(f"Error processing tool calls: {e}")
    else:
        logger.warning(
            "Coordinator response contains no tool calls. Terminating workflow execution."
        )
        logger.debug(f"Coordinator response: {response}")
    messages = state.get("messages", [])
    if response.content:
        messages.append(HumanMessage(content=response.content, name="coordinator"))
    return Command(
        update={
            "messages": messages,
            "locale": locale,
            "research_topic": research_topic,
            "resources": configurable.resources,
        },
        goto=goto,
    )


def reporter_node(state: State, config: RunnableConfig):
    """Reporter node that write a final report."""
    logger.info("Reporter write final report")
    configurable = Configuration.from_runnable_config(config)

    # Handle quick research mode (no plan)
    quick_research_mode = state.get("quick_research_mode", False)
    current_plan = state.get("current_plan")

    if quick_research_mode and not current_plan:
        # In quick research mode, use research_topic and selected_candidate
        research_topic = state.get("research_topic", "")
        selected_candidate = state.get("selected_candidate", {})

        task_description = f"Quick research on {research_topic}"
        if selected_candidate:
            task_description = (
                f"Research report on {selected_candidate.get('name', research_topic)} "
                f"({selected_candidate.get('title', 'N/A')} at {selected_candidate.get('company', 'N/A')})"
            )

        input_ = {
            "messages": [
                HumanMessage(
                    f"# Research Requirements\n\n## Task\n\n{task_description}\n\n## Description\n\n"
                    f"Generate a concise research report based on the available information about this person."
                )
            ],
            "locale": state.get("locale", "en-US"),
        }
    else:
        # Normal mode with plan
        input_ = {
            "messages": [
                HumanMessage(
                    f"# Research Requirements\n\n## Task\n\n{current_plan.title}\n\n## Description\n\n{current_plan.thought}"
                )
            ],
            "locale": state.get("locale", "en-US"),
        }

    invoke_messages = apply_prompt_template("reporter", input_, configurable)
    observations = state.get("observations", [])

    # Add a reminder about the new report format, citation style, and table usage
    invoke_messages.append(
        HumanMessage(
            content="IMPORTANT: Structure your report according to the format in the prompt. Remember to include:\n\n1. Key Points - A bulleted list of the most important findings\n2. Overview - A brief introduction to the topic\n3. Detailed Analysis - Organized into logical sections\n4. Survey Note (optional) - For more comprehensive reports\n5. Key Citations - List all references at the end\n\nFor citations, DO NOT include inline citations in the text. Instead, place all citations in the 'Key Citations' section at the end using the format: `- [Source Title](URL)`. Include an empty line between each citation for better readability.\n\nPRIORITIZE USING MARKDOWN TABLES for data presentation and comparison. Use tables whenever presenting comparative data, statistics, features, or options. Structure tables with clear headers and aligned columns. Example table format:\n\n| Feature | Description | Pros | Cons |\n|---------|-------------|------|------|\n| Feature 1 | Description 1 | Pros 1 | Cons 1 |\n| Feature 2 | Description 2 | Pros 2 | Cons 2 |",
            name="system",
        )
    )

    observation_messages = []
    for observation in observations:
        observation_messages.append(
            HumanMessage(
                content=f"Below are some observations for the research task:\n\n{observation}",
                name="observation",
            )
        )

    # Context compression
    llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP["reporter"])
    compressed_state = ContextManager(llm_token_limit).compress_messages(
        {"messages": observation_messages}
    )
    invoke_messages += compressed_state.get("messages", [])

    logger.debug(f"Current invoke messages: {invoke_messages}")
    response = get_llm_by_type(AGENT_LLM_MAP["reporter"]).invoke(invoke_messages)
    response_content = response.content
    logger.info(f"reporter response: {response_content}")

    # Generate structured output if schema provided
    structured_output = None
    output_schema = state.get("output_schema")

    logger.info(f"Reporter node - output_schema present: {output_schema is not None}")
    if output_schema:
        logger.info(f"Output schema: {json.dumps(output_schema, indent=2)}")

    if output_schema:
        try:
            logger.info("Generating structured output from report")
            schema = output_schema

            # Use LLM with structured output to extract data from report
            extraction_messages = [
                HumanMessage(
                    content=f"Extract structured data from the following research report according to the provided schema.\n\n# Report\n\n{response_content}\n\n# Schema\n\n```json\n{json.dumps(schema, indent=2)}\n```\n\nExtract and return ONLY the structured data that matches this schema. Be precise and extract all required fields."
                )
            ]

            structured_llm = get_llm_by_type("basic").with_structured_output(
                schema=schema,
                method="json_mode",
            )

            structured_response = structured_llm.invoke(extraction_messages)
            structured_output = structured_response if isinstance(structured_response, dict) else json.loads(str(structured_response))
            logger.info(f"Structured output generated successfully: {json.dumps(structured_output, indent=2)}")

        except Exception as e:
            logger.error(f"Failed to generate structured output: {e}", exc_info=True)
            logger.warning("Continuing without structured output")
            structured_output = None
    else:
        logger.info("No output_schema provided, skipping structured output generation")

    result = {
        "final_report": response_content,
        "structured_output": structured_output
    }
    logger.info(f"Reporter node returning - structured_output is None: {structured_output is None}")

    return result


def research_team_node(state: State):
    """Research team node that collaborates on tasks."""
    logger.info("Research team is collaborating on tasks.")
    pass


async def _execute_agent_step(
    state: State, agent, agent_name: str
) -> Command[Literal["research_team"]]:
    """Helper function to execute a step using the specified agent."""
    current_plan = state.get("current_plan")
    plan_title = current_plan.title
    observations = state.get("observations", [])

    # Find the first unexecuted step
    current_step = None
    completed_steps = []
    for step in current_plan.steps:
        if not step.execution_res:
            current_step = step
            break
        else:
            completed_steps.append(step)

    if not current_step:
        logger.warning("No unexecuted step found")
        return Command(goto="research_team")

    logger.info(f"Executing step: {current_step.title}, agent: {agent_name}")

    # Format completed steps information
    completed_steps_info = ""
    if completed_steps:
        completed_steps_info = "# Completed Research Steps\n\n"
        for i, step in enumerate(completed_steps):
            completed_steps_info += f"## Completed Step {i + 1}: {step.title}\n\n"
            completed_steps_info += f"<finding>\n{step.execution_res}\n</finding>\n\n"

    # Prepare the input for the agent with completed steps info
    agent_input = {
        "messages": [
            HumanMessage(
                content=f"# Research Topic\n\n{plan_title}\n\n{completed_steps_info}# Current Step\n\n## Title\n\n{current_step.title}\n\n## Description\n\n{current_step.description}\n\n## Locale\n\n{state.get('locale', 'en-US')}"
            )
        ]
    }

    # Add citation reminder for researcher agent
    if agent_name == "researcher":
        if state.get("resources"):
            resources_info = "**The user mentioned the following resource files:**\n\n"
            for resource in state.get("resources"):
                resources_info += f"- {resource.title} ({resource.description})\n"

            agent_input["messages"].append(
                HumanMessage(
                    content=resources_info
                    + "\n\n"
                    + "You MUST use the **local_search_tool** to retrieve the information from the resource files.",
                )
            )

        agent_input["messages"].append(
            HumanMessage(
                content="IMPORTANT: DO NOT include inline citations in the text. Instead, track all sources and include a References section at the end using link reference format. Include an empty line between each citation for better readability. Use this format for each reference:\n- [Source Title](URL)\n\n- [Another Source](URL)",
                name="system",
            )
        )

    # Invoke the agent
    default_recursion_limit = 25
    try:
        env_value_str = os.getenv("AGENT_RECURSION_LIMIT", str(default_recursion_limit))
        parsed_limit = int(env_value_str)

        if parsed_limit > 0:
            recursion_limit = parsed_limit
            logger.info(f"Recursion limit set to: {recursion_limit}")
        else:
            logger.warning(
                f"AGENT_RECURSION_LIMIT value '{env_value_str}' (parsed as {parsed_limit}) is not positive. "
                f"Using default value {default_recursion_limit}."
            )
            recursion_limit = default_recursion_limit
    except ValueError:
        raw_env_value = os.getenv("AGENT_RECURSION_LIMIT")
        logger.warning(
            f"Invalid AGENT_RECURSION_LIMIT value: '{raw_env_value}'. "
            f"Using default value {default_recursion_limit}."
        )
        recursion_limit = default_recursion_limit

    logger.info(f"Agent input: {agent_input}")
    result = await agent.ainvoke(
        input=agent_input, config={"recursion_limit": recursion_limit}
    )

    # Process the result
    response_content = result["messages"][-1].content
    logger.debug(f"{agent_name.capitalize()} full response: {response_content}")

    # Update the step with the execution result
    current_step.execution_res = response_content
    logger.info(f"Step '{current_step.title}' execution completed by {agent_name}")

    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=response_content,
                    name=agent_name,
                )
            ],
            "observations": observations + [response_content],
        },
        goto="research_team",
    )


async def _setup_and_execute_agent_step(
    state: State,
    config: RunnableConfig,
    agent_type: str,
    default_tools: list,
) -> Command[Literal["research_team"]]:
    """Helper function to set up an agent with appropriate tools and execute a step.

    This function handles the common logic for both researcher_node and coder_node:
    1. Configures MCP servers and tools based on agent type
    2. Creates an agent with the appropriate tools or uses the default agent
    3. Executes the agent on the current step

    Args:
        state: The current state
        config: The runnable config
        agent_type: The type of agent ("researcher" or "coder")
        default_tools: The default tools to add to the agent

    Returns:
        Command to update state and go to research_team
    """
    configurable = Configuration.from_runnable_config(config)
    mcp_servers = {}
    enabled_tools = {}

    # Extract MCP server configuration for this agent type
    if configurable.mcp_settings:
        for server_name, server_config in configurable.mcp_settings["servers"].items():
            if (
                server_config["enabled_tools"]
                and agent_type in server_config["add_to_agents"]
            ):
                mcp_servers[server_name] = {
                    k: v
                    for k, v in server_config.items()
                    if k in ("transport", "command", "args", "url", "env", "headers")
                }
                for tool_name in server_config["enabled_tools"]:
                    enabled_tools[tool_name] = server_name

    # Create and execute agent with MCP tools if available
    if mcp_servers:
        client = MultiServerMCPClient(mcp_servers)
        loaded_tools = default_tools[:]
        all_tools = await client.get_tools()
        for tool in all_tools:
            if tool.name in enabled_tools:
                tool.description = (
                    f"Powered by '{enabled_tools[tool.name]}'.\n{tool.description}"
                )
                loaded_tools.append(tool)

        llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP[agent_type])
        pre_model_hook = partial(ContextManager(llm_token_limit, 3).compress_messages)
        agent = create_agent(
            agent_type, agent_type, loaded_tools, agent_type, pre_model_hook
        )
        return await _execute_agent_step(state, agent, agent_type)
    else:
        # Use default tools if no MCP servers are configured
        llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP[agent_type])
        pre_model_hook = partial(ContextManager(llm_token_limit, 3).compress_messages)
        agent = create_agent(
            agent_type, agent_type, default_tools, agent_type, pre_model_hook
        )
        return await _execute_agent_step(state, agent, agent_type)


async def researcher_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team"]]:
    """Researcher node that do research"""
    logger.info("Researcher node is researching.")
    configurable = Configuration.from_runnable_config(config)

    # Get search provider from state (runtime override)
    search_provider = state.get("search_provider", "tavily")
    logger.info(f"Using search provider: {search_provider}")

    # Select search tool based on provider
    if search_provider == "firecrawl":
        from src.tools.firecrawl import firecrawl_search
        search_tool = firecrawl_search
        logger.info("Using Firecrawl search provider for deep content extraction")
    else:
        search_tool = get_web_search_tool(configurable.max_search_results)
        logger.info(f"Using {search_provider} search provider")

    tools = [search_tool, crawl_tool]
    retriever_tool = get_retriever_tool(state.get("resources", []))
    if retriever_tool:
        tools.insert(0, retriever_tool)
    logger.info(f"Researcher tools: {[t.name for t in tools]}")

    # Execute agent and increment search counter
    result = await _setup_and_execute_agent_step(
        state,
        config,
        "researcher",
        tools,
    )

    # Increment search counter
    searches_executed = state.get("searches_executed", 0) + 1

    # Update result with search tracking
    if isinstance(result, Command):
        current_update = result.update or {}
        current_update["searches_executed"] = searches_executed
        result = Command(
            update=current_update,
            goto=result.goto
        )

    return result


async def coder_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team"]]:
    """Coder node that do code analysis."""
    logger.info("Coder node is coding.")
    return await _setup_and_execute_agent_step(
        state,
        config,
        "coder",
        [python_repl_tool],
    )
