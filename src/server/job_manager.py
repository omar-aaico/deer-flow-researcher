# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

from src.config.loader import get_str_env
from src.server.async_request import ResearchStatus

logger = logging.getLogger(__name__)


class ResearchJob:
    """Represents a single research job"""

    def __init__(self, job_id: str, query: str):
        self.job_id = job_id
        self.query = query
        self.status = ResearchStatus.PENDING
        self.error: Optional[str] = None
        self.thread_id: Optional[str] = None
        self.final_report: Optional[str] = None
        self.researcher_findings: Optional[str] = None
        self.plan: Optional[dict] = None
        self.structured_output: Optional[dict] = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None
        self.task: Optional[asyncio.Task] = None

    def update_status(self, status: ResearchStatus):
        """Update job status and metadata"""
        self.status = status
        self.updated_at = datetime.utcnow()

        if status == ResearchStatus.COMPLETED:
            self.completed_at = datetime.utcnow()

    def set_error(self, error: str):
        """Mark job as failed with error message"""
        self.status = ResearchStatus.FAILED
        self.error = error
        self.updated_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()

    def get_duration_seconds(self) -> Optional[float]:
        """Get job duration in seconds"""
        if self.completed_at:
            # Ensure both datetimes are timezone-aware or naive
            completed = self.completed_at.replace(tzinfo=None) if self.completed_at.tzinfo else self.completed_at
            created = self.created_at.replace(tzinfo=None) if self.created_at.tzinfo else self.created_at
            return (completed - created).total_seconds()
        return None


class JobManager:
    """Manages background research jobs with optional database persistence"""

    def __init__(self):
        self.jobs: Dict[str, ResearchJob] = {}  # In-memory cache
        self._cleanup_task: Optional[asyncio.Task] = None
        self._store = None  # Database store (optional)

        # Initialize database store if configured
        self._init_store()

    def _init_store(self):
        """Initialize database store if Supabase is configured"""
        try:
            supabase_url = get_str_env("SUPABASE_URL")
            supabase_key = get_str_env("SUPABASE_KEY")

            if supabase_url and supabase_key:
                from src.db.supabase_job_store import SupabaseJobStore
                self._store = SupabaseJobStore(supabase_url, supabase_key)
                logger.info("Job persistence enabled (Supabase)")
            else:
                logger.info("Job persistence disabled (in-memory only)")
        except Exception as e:
            logger.warning(f"Failed to initialize job store: {e}. Using in-memory only.")
            self._store = None

    def create_job(self, query: str, **kwargs) -> ResearchJob:
        """
        Create a new research job.

        Args:
            query: Research query
            **kwargs: Additional job parameters (report_style, max_step_num, etc.)
        """
        job_id = str(uuid4())
        job = ResearchJob(job_id, query)

        # Store in memory
        self.jobs[job_id] = job

        # Persist to database
        if self._store:
            try:
                self._store.create_job(
                    job_id=job_id,
                    query=query,
                    report_style=kwargs.get("report_style", "academic"),
                    max_step_num=kwargs.get("max_step_num", 3),
                    max_search_results=kwargs.get("max_search_results", 3),
                    search_provider=kwargs.get("search_provider", "tavily"),
                    enable_background_investigation=kwargs.get("enable_background_investigation", True),
                    enable_deep_thinking=kwargs.get("enable_deep_thinking", False),
                    auto_accepted_plan=kwargs.get("auto_accepted_plan", True),
                    output_schema=kwargs.get("output_schema"),
                    resources=kwargs.get("resources"),
                    user_id=kwargs.get("user_id"),
                    api_key_name=kwargs.get("api_key_name"),
                )
            except Exception as e:
                logger.error(f"Failed to persist job {job_id} to database: {e}")

        logger.info(f"Created research job {job_id} for query: {query[:50]}...")
        return job

    def get_job(self, job_id: str) -> Optional[ResearchJob]:
        """Get a job by ID (checks memory first, then database)"""
        # Check memory cache
        if job_id in self.jobs:
            return self.jobs[job_id]

        # Check database if enabled
        if self._store:
            try:
                db_job = self._store.get_job_with_result(job_id)
                if db_job:
                    # Reconstruct job object from database
                    job = ResearchJob(db_job["job_id"], db_job["query"])
                    job.status = ResearchStatus(db_job["status"])
                    job.error = db_job.get("error")
                    job.thread_id = db_job.get("thread_id")
                    job.final_report = db_job.get("final_report")
                    job.researcher_findings = db_job.get("researcher_findings")
                    job.plan = db_job.get("plan")
                    job.structured_output = db_job.get("structured_output")

                    # Parse timestamps
                    if db_job.get("created_at"):
                        job.created_at = datetime.fromisoformat(db_job["created_at"].replace("Z", "+00:00"))
                    if db_job.get("completed_at"):
                        job.completed_at = datetime.fromisoformat(db_job["completed_at"].replace("Z", "+00:00"))

                    # Cache in memory
                    self.jobs[job_id] = job
                    return job
            except Exception as e:
                logger.error(f"Failed to load job {job_id} from database: {e}")

        return None

    def update_job_status(self, job: ResearchJob, status: ResearchStatus):
        """Update job status in memory and database"""
        job.update_status(status)

        # Update in database
        if self._store:
            try:
                # Map ResearchStatus to database status string
                status_map = {
                    ResearchStatus.PENDING: "pending",
                    ResearchStatus.COORDINATING: "coordinating",
                    ResearchStatus.PLANNING: "planning",
                    ResearchStatus.RESEARCHING: "researching",
                    ResearchStatus.REPORTING: "reporting",
                    ResearchStatus.COMPLETED: "completed",
                    ResearchStatus.FAILED: "failed",
                }

                self._store.update_job_status(
                    job_id=job.job_id,
                    status=status_map[status],
                    progress=self._get_progress_for_status(status),
                    current_step=status.value
                )
            except Exception as e:
                logger.error(f"Failed to update job {job.job_id} status in database: {e}")

    def save_job_result(self, job: ResearchJob):
        """Save completed job result to database"""
        if self._store and job.status == ResearchStatus.COMPLETED:
            try:
                self._store.create_result(
                    job_id=job.job_id,
                    thread_id=job.thread_id,
                    final_report=job.final_report,
                    researcher_findings=job.researcher_findings,
                    structured_output=job.structured_output,
                    plan=job.plan,
                    duration_seconds=job.get_duration_seconds(),
                    search_count=0,  # TODO: Track this during research
                    crawl_count=0,   # TODO: Track this during research
                )
                logger.info(f"Saved result for job {job.job_id}")
            except Exception as e:
                logger.error(f"Failed to save result for job {job.job_id}: {e}")

    def delete_job(self, job_id: str):
        """Delete a job (cancel if running) from memory and database"""
        job = self.jobs.get(job_id)
        if job:
            if job.task and not job.task.done():
                job.task.cancel()
            del self.jobs[job_id]

        # Delete from database
        if self._store:
            try:
                self._store.delete_job(job_id)
            except Exception as e:
                logger.error(f"Failed to delete job {job_id} from database: {e}")

        logger.info(f"Deleted job {job_id}")

    def _get_progress_for_status(self, status: ResearchStatus) -> float:
        """Map status to progress percentage"""
        progress_map = {
            ResearchStatus.PENDING: 0.0,
            ResearchStatus.COORDINATING: 10.0,
            ResearchStatus.PLANNING: 20.0,
            ResearchStatus.RESEARCHING: 50.0,
            ResearchStatus.REPORTING: 80.0,
            ResearchStatus.COMPLETED: 100.0,
            ResearchStatus.FAILED: 0.0,
        }
        return progress_map.get(status, 0.0)

    async def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Periodically clean up old completed jobs from memory and database"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour

                # Clean up memory
                now = datetime.utcnow()
                to_delete = []

                for job_id, job in self.jobs.items():
                    if job.completed_at:
                        age_hours = (now - job.completed_at).total_seconds() / 3600
                        if age_hours > max_age_hours:
                            to_delete.append(job_id)

                for job_id in to_delete:
                    # Just remove from memory cache (keep in DB)
                    if job_id in self.jobs:
                        del self.jobs[job_id]

                if to_delete:
                    logger.info(f"Cleaned up {len(to_delete)} old jobs from memory")

                # Clean up database (older jobs)
                if self._store:
                    try:
                        deleted_count = self._store.delete_old_jobs(days=30)
                        if deleted_count > 0:
                            logger.info(f"Cleaned up {deleted_count} jobs from database")
                    except Exception as e:
                        logger.error(f"Failed to clean up database: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")

    def start_cleanup_task(self):
        """Start the background cleanup task"""
        if not self._cleanup_task or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self.cleanup_old_jobs())

    def stop_cleanup_task(self):
        """Stop the background cleanup task"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()


# Global job manager instance
job_manager = JobManager()
