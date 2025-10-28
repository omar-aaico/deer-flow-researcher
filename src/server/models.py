# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Pydantic models for API requests and responses.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PersonResearchRequest(BaseModel):
    """Request model for person research."""
    person_name: str = Field(..., description="Full name of the person to research")
    company: Optional[str] = Field(None, description="Company where the person works")
    additional_context: Optional[str] = Field(
        None, description="Additional context (title, location, etc.)"
    )
    report_style: str = Field(
        "sales_intelligence",
        description="Report style to use for the research"
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional custom JSON schema for structured output"
    )
    max_plan_iterations: int = Field(
        1, description="Maximum number of plan iterations (breadth)"
    )
    max_step_num: int = Field(
        1, description="Maximum steps per iteration (depth)"
    )


class DisambiguationRequest(BaseModel):
    """Request model for disambiguation selection."""
    selected_candidate_id: str = Field(
        ..., description="ID of the selected candidate (e.g., candidate_1)"
    )
    additional_context: Optional[str] = Field(
        None, description="Additional context to enrich the research"
    )


class Candidate(BaseModel):
    """Model for a person candidate."""
    id: str = Field(..., description="Unique identifier (e.g., candidate_1)")
    name: str = Field(..., description="Full name")
    title: str = Field(..., description="Current job title")
    company: str = Field(..., description="Current company")
    location: Optional[str] = Field(None, description="Location (city, state/country)")
    linkedin: Optional[str] = Field(None, description="LinkedIn URL")
    summary: str = Field(..., description="Brief distinguishing summary")


class PersonResearchResponse(BaseModel):
    """Response model for person research (both initial and disambiguation)."""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(
        ...,
        description="Job status: completed, awaiting_disambiguation, or failed"
    )
    message: Optional[str] = Field(None, description="Human-readable status message")

    # For completed status
    final_report: Optional[str] = Field(None, description="Full research report (markdown)")
    structured_output: Optional[Dict[str, Any]] = Field(
        None, description="Structured data extracted from report"
    )
    selected_candidate: Optional[Candidate] = Field(
        None, description="The candidate that was researched (after disambiguation)"
    )

    # For awaiting_disambiguation status
    candidates: Optional[List[Candidate]] = Field(
        None, description="List of person candidates requiring disambiguation"
    )

    # For failed status
    error: Optional[str] = Field(None, description="Error message if failed")


class AsyncResearchRequest(BaseModel):
    """Request model for async research endpoint."""
    query: str = Field(..., description="Research query")
    report_style: str = Field("academic", description="Report style")
    max_step_num: int = Field(3, description="Maximum research steps")
    max_search_results: int = Field(3, description="Maximum search results per query")
    search_provider: str = Field("tavily", description="Search provider to use")
    enable_background_investigation: bool = Field(True, description="Enable background search")
    enable_deep_thinking: bool = Field(False, description="Enable deep thinking mode")
    auto_accepted_plan: bool = Field(True, description="Auto-accept research plan")
    output_schema: Optional[Dict[str, Any]] = Field(
        None, description="Optional JSON schema for structured output"
    )
    resources: Optional[List[Dict[str, Any]]] = Field(
        None, description="Optional resources for RAG"
    )


class ResearchStatusResponse(BaseModel):
    """Response model for job status check."""
    job_id: str
    status: str
    progress: Optional[float] = None
    current_step: Optional[str] = None
    error: Optional[str] = None


class ResearchResultResponse(BaseModel):
    """Response model for completed research result."""
    job_id: str
    status: str
    query: str
    final_report: Optional[str] = None
    structured_output: Optional[Dict[str, Any]] = None
    plan: Optional[Dict[str, Any]] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
