# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


from langgraph.graph import MessagesState

from src.prompts.planner_model import Plan
from src.rag import Resource


class State(MessagesState):
    """State for the agent system, extends MessagesState with next field."""

    # Runtime Variables
    locale: str = "en-US"
    research_topic: str = ""
    observations: list[str] = []
    resources: list[Resource] = []
    plan_iterations: int = 0
    current_plan: Plan | str = None
    final_report: str = ""
    auto_accepted_plan: bool = False
    enable_background_investigation: bool = True
    background_investigation_results: str = None

    # Search provider and cost tracking
    search_provider: str = "tavily"
    searches_executed: int = 0
    cost_tracking: dict = {}

    # Structured output support
    output_schema: dict | None = None
    structured_output: dict | None = None
    skip_reporting: bool = False  # Skip reporter node for faster raw results

    # Person search support
    person_search_mode: bool = False
    quick_research_mode: bool = False  # Skip planner loop for fast person research
    person_name: str | None = None
    person_company: str | None = None
    person_context: str | None = None
    disambiguation_candidates: list[dict] | None = None
    selected_candidate: dict | None = None
    enriched_person_query: str | None = None
