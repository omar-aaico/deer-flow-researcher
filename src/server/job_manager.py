# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

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
            return (self.completed_at - self.created_at).total_seconds()
        return None


class JobManager:
    """Manages background research jobs"""

    def __init__(self):
        self.jobs: Dict[str, ResearchJob] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def create_job(self, query: str) -> ResearchJob:
        """Create a new research job"""
        job_id = str(uuid4())
        job = ResearchJob(job_id, query)
        self.jobs[job_id] = job
        logger.info(f"Created research job {job_id} for query: {query[:50]}...")
        return job

    def get_job(self, job_id: str) -> Optional[ResearchJob]:
        """Get a job by ID"""
        return self.jobs.get(job_id)

    def delete_job(self, job_id: str):
        """Delete a job (cancel if running)"""
        job = self.jobs.get(job_id)
        if job:
            if job.task and not job.task.done():
                job.task.cancel()
            del self.jobs[job_id]
            logger.info(f"Deleted job {job_id}")

    async def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Periodically clean up old completed jobs"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                now = datetime.utcnow()
                to_delete = []

                for job_id, job in self.jobs.items():
                    if job.completed_at:
                        age_hours = (now - job.completed_at).total_seconds() / 3600
                        if age_hours > max_age_hours:
                            to_delete.append(job_id)

                for job_id in to_delete:
                    self.delete_job(job_id)

                if to_delete:
                    logger.info(f"Cleaned up {len(to_delete)} old jobs")

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
