"""
Supabase REST API-based job storage for DeerFlow research jobs.
Uses Supabase Python client instead of direct PostgreSQL connection.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from supabase import create_client, Client

logger = logging.getLogger(__name__)


class SupabaseJobStore:
    """Supabase storage for research jobs and results."""

    def __init__(self, supabase_url: str, supabase_key: str):
        """
        Initialize Supabase client.

        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase anon/service key
        """
        self.client: Client = create_client(supabase_url, supabase_key)
        logger.info(f"Connected to Supabase: {supabase_url}")

    # ========================================================================
    # CREATE operations
    # ========================================================================

    def create_job(
        self,
        job_id: str,
        query: str,
        report_style: str = "academic",
        max_step_num: int = 3,
        max_search_results: int = 3,
        search_provider: str = "tavily",
        enable_background_investigation: bool = True,
        enable_deep_thinking: bool = False,
        auto_accepted_plan: bool = True,
        output_schema: Optional[Dict] = None,
        resources: Optional[List] = None,
        user_id: Optional[str] = None,
        api_key_name: Optional[str] = None,
    ) -> Dict:
        """Create a new research job."""
        try:
            data = {
                "job_id": job_id,
                "query": query,
                "report_style": report_style,
                "max_step_num": max_step_num,
                "max_search_results": max_search_results,
                "search_provider": search_provider,
                "enable_background_investigation": enable_background_investigation,
                "enable_deep_thinking": enable_deep_thinking,
                "auto_accepted_plan": auto_accepted_plan,
                "output_schema": output_schema,
                "resources": resources,
                "user_id": user_id,
                "api_key_name": api_key_name,
                "status": "pending",
                "progress": 0.0,
            }

            result = self.client.table("research_jobs").insert(data).execute()
            logger.info(f"Created job {job_id}")
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Failed to create job {job_id}: {e}")
            raise

    def create_result(
        self,
        job_id: str,
        thread_id: Optional[str] = None,
        final_report: Optional[str] = None,
        researcher_findings: Optional[str] = None,
        structured_output: Optional[Dict] = None,
        plan: Optional[Dict] = None,
        observations: Optional[List] = None,
        duration_seconds: Optional[float] = None,
        search_count: int = 0,
        crawl_count: int = 0,
    ) -> Dict:
        """Create research result."""
        try:
            report_length = len(final_report) if final_report else 0
            sources_count = final_report.count("](http") if final_report else 0

            data = {
                "job_id": job_id,
                "thread_id": thread_id,
                "final_report": final_report,
                "researcher_findings": researcher_findings,
                "structured_output": structured_output,
                "plan": plan,
                "observations": observations,
                "duration_seconds": duration_seconds,
                "search_count": search_count,
                "crawl_count": crawl_count,
                "report_length": report_length,
                "sources_count": sources_count,
            }

            result = self.client.table("research_results").insert(data).execute()
            logger.info(f"Created result for job {job_id}")
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Failed to create result for job {job_id}: {e}")
            raise

    # ========================================================================
    # READ operations
    # ========================================================================

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID."""
        try:
            result = (
                self.client.table("research_jobs")
                .select("*")
                .eq("job_id", job_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get job {job_id}: {e}")
            return None

    def get_result(self, job_id: str) -> Optional[Dict]:
        """Get result by job ID."""
        try:
            result = (
                self.client.table("research_results")
                .select("*")
                .eq("job_id", job_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get result for job {job_id}: {e}")
            return None

    def get_job_with_result(self, job_id: str) -> Optional[Dict]:
        """Get job with its result."""
        try:
            # Get job
            job = self.get_job(job_id)
            if not job:
                return None

            # Get result
            result = self.get_result(job_id)

            # Merge
            if result:
                job.update({
                    "thread_id": result.get("thread_id"),
                    "final_report": result.get("final_report"),
                    "researcher_findings": result.get("researcher_findings"),
                    "structured_output": result.get("structured_output"),
                    "plan": result.get("plan"),
                    "observations": result.get("observations"),
                    "duration_seconds": result.get("duration_seconds"),
                    "search_count": result.get("search_count"),
                    "crawl_count": result.get("crawl_count"),
                })

            return job
        except Exception as e:
            logger.error(f"Failed to get job with result {job_id}: {e}")
            return None

    def list_jobs(
        self,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """List jobs with optional filters."""
        try:
            query = self.client.table("research_jobs").select("*")

            if status:
                query = query.eq("status", status)

            if user_id:
                query = query.eq("user_id", user_id)

            result = (
                query.order("created_at", desc=True)
                .limit(limit)
                .offset(offset)
                .execute()
            )

            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to list jobs: {e}")
            return []

    # ========================================================================
    # UPDATE operations
    # ========================================================================

    def update_job_status(
        self,
        job_id: str,
        status: str,
        progress: Optional[float] = None,
        current_step: Optional[str] = None,
        steps_completed: Optional[int] = None,
        total_steps: Optional[int] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update job status and progress."""
        try:
            updates = {"status": status}

            if progress is not None:
                updates["progress"] = progress

            if current_step is not None:
                updates["current_step"] = current_step

            if steps_completed is not None:
                updates["steps_completed"] = steps_completed

            if total_steps is not None:
                updates["total_steps"] = total_steps

            if error is not None:
                updates["error"] = error

            # Set timestamps
            if status != "pending":
                # Note: started_at logic would need a conditional update
                pass

            if status in ("completed", "failed"):
                updates["completed_at"] = datetime.utcnow().isoformat()

            result = (
                self.client.table("research_jobs")
                .update(updates)
                .eq("job_id", job_id)
                .execute()
            )

            updated = len(result.data) > 0
            if updated:
                logger.info(f"Updated job {job_id} status to {status}")
            return updated
        except Exception as e:
            logger.error(f"Failed to update job {job_id}: {e}")
            return False

    # ========================================================================
    # DELETE operations
    # ========================================================================

    def delete_job(self, job_id: str) -> bool:
        """Delete job (CASCADE deletes result)."""
        try:
            result = (
                self.client.table("research_jobs")
                .delete()
                .eq("job_id", job_id)
                .execute()
            )

            deleted = len(result.data) > 0
            if deleted:
                logger.info(f"Deleted job {job_id}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete job {job_id}: {e}")
            return False

    def delete_old_jobs(self, days: int = 30) -> int:
        """Delete completed/failed jobs older than specified days."""
        try:
            cutoff_date = datetime.utcnow().replace(tzinfo=None)
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - days)

            result = (
                self.client.table("research_jobs")
                .delete()
                .in_("status", ["completed", "failed"])
                .lt("completed_at", cutoff_date.isoformat())
                .execute()
            )

            count = len(result.data) if result.data else 0
            logger.info(f"Deleted {count} old jobs (older than {days} days)")
            return count
        except Exception as e:
            logger.error(f"Failed to delete old jobs: {e}")
            return 0
