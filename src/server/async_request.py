# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import List, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field

from src.config.report_style import ReportStyle
from src.rag.retriever import Resource


class ResearchStatus(str, Enum):
    """Status of a research job"""
    PENDING = "pending"
    COORDINATING = "coordinating"
    PLANNING = "planning"
    RESEARCHING = "researching"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"


class AsyncResearchRequest(BaseModel):
    """Request to start an async research job"""
    query: str = Field(..., description="The research question")
    resources: Optional[List[Resource]] = Field(
        [], description="Resources to be used for the research"
    )
    max_plan_iterations: Optional[int] = Field(
        1, description="The maximum number of plan iterations"
    )
    max_step_num: Optional[int] = Field(
        3, description="The maximum number of steps in a plan"
    )
    max_search_results: Optional[int] = Field(
        3, description="The maximum number of search results"
    )
    auto_accepted_plan: Optional[bool] = Field(
        True, description="Whether to automatically accept the plan"
    )
    enable_background_investigation: Optional[bool] = Field(
        True, description="Whether to get background investigation before plan"
    )
    report_style: Optional[ReportStyle] = Field(
        ReportStyle.ACADEMIC, description="The style of the report"
    )
    enable_deep_thinking: Optional[bool] = Field(
        False, description="Whether to enable deep thinking"
    )
    search_provider: Optional[Literal["tavily", "firecrawl"]] = Field(
        "tavily", description="Search provider to use (tavily or firecrawl)"
    )
    output_schema: Optional[dict] = Field(
        None, description="Optional Pydantic schema for structured output"
    )
    skip_reporting: Optional[bool] = Field(
        False, description="If True, skips report generation and returns raw observations. Saves 5-10s execution time."
    )


class AsyncResearchResponse(BaseModel):
    """Response when starting an async research job"""
    job_id: str = Field(..., description="Unique identifier for this research job")
    status: ResearchStatus = Field(..., description="Current status of the job")
    message: str = Field(..., description="Human-readable status message")


class ResearchStatusResponse(BaseModel):
    """Response for job status check"""
    job_id: str = Field(..., description="Unique identifier for this research job")
    status: ResearchStatus = Field(..., description="Current status of the job")
    error: Optional[str] = Field(None, description="Error message if status is FAILED")
    created_at: str = Field(..., description="ISO timestamp when job was created")
    updated_at: str = Field(..., description="ISO timestamp when job was last updated")


class ResearchResultResponse(BaseModel):
    """Response containing the final research result"""
    job_id: str = Field(..., description="Unique identifier for this research job")
    status: ResearchStatus = Field(..., description="Final status of the job")
    thread_id: str = Field(..., description="Thread ID for conversation continuation")
    query: str = Field(..., description="The original research question")
    final_report: Optional[str] = Field(None, description="The final research report")
    researcher_findings: Optional[str] = Field(None, description="Raw researcher findings")
    plan: Optional[dict] = Field(None, description="The research plan that was executed")
    structured_output: Optional[dict] = Field(None, description="Structured data extracted according to output_schema")
    error: Optional[str] = Field(None, description="Error message if status is FAILED")
    created_at: str = Field(..., description="ISO timestamp when job was created")
    completed_at: Optional[str] = Field(None, description="ISO timestamp when job completed")
    duration_seconds: Optional[float] = Field(None, description="Total duration in seconds")
