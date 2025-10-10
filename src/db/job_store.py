"""
PostgreSQL-based job storage for DeerFlow research jobs.
Provides CRUD operations for research_jobs and research_results tables.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger(__name__)


class PostgresJobStore:
    """PostgreSQL storage for research jobs and results."""

    def __init__(self, connection_string: str):
        """
        Initialize PostgreSQL connection.

        Args:
            connection_string: PostgreSQL connection string
                Example: "postgresql://user:password@host:port/database"
        """
        self.connection_string = connection_string
        self.conn = None
        self._connect()

    def _connect(self):
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(
                self.connection_string,
                cursor_factory=RealDictCursor
            )
            self.conn.autocommit = False
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def _reconnect_if_needed(self):
        """Reconnect if connection is closed."""
        if self.conn is None or self.conn.closed:
            logger.warning("Database connection closed, reconnecting...")
            self._connect()

    def close(self):
        """Close database connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            logger.info("Database connection closed")

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
        """
        Create a new research job.

        Returns:
            Dict with job data
        """
        self._reconnect_if_needed()

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_jobs (
                        job_id, query, report_style, max_step_num, max_search_results,
                        search_provider, enable_background_investigation, enable_deep_thinking,
                        auto_accepted_plan, output_schema, resources, user_id, api_key_name,
                        status, progress
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', 0.0
                    )
                    RETURNING *
                    """,
                    (
                        job_id, query, report_style, max_step_num, max_search_results,
                        search_provider, enable_background_investigation, enable_deep_thinking,
                        auto_accepted_plan, Json(output_schema) if output_schema else None,
                        Json(resources) if resources else None, user_id, api_key_name
                    )
                )
                result = cur.fetchone()
                self.conn.commit()
                logger.info(f"Created job {job_id}")
                return dict(result)
        except Exception as e:
            self.conn.rollback()
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
        """
        Create research result for a completed job.

        Returns:
            Dict with result data
        """
        self._reconnect_if_needed()

        try:
            with self.conn.cursor() as cur:
                # Calculate report length and sources
                report_length = len(final_report) if final_report else 0
                sources_count = final_report.count("](http") if final_report else 0

                cur.execute(
                    """
                    INSERT INTO research_results (
                        job_id, thread_id, final_report, researcher_findings,
                        structured_output, plan, observations, duration_seconds,
                        search_count, crawl_count, report_length, sources_count
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        job_id, thread_id, final_report, researcher_findings,
                        Json(structured_output) if structured_output else None,
                        Json(plan) if plan else None,
                        Json(observations) if observations else None,
                        duration_seconds, search_count, crawl_count,
                        report_length, sources_count
                    )
                )
                result = cur.fetchone()
                self.conn.commit()
                logger.info(f"Created result for job {job_id}")
                return dict(result)
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to create result for job {job_id}: {e}")
            raise

    # ========================================================================
    # READ operations
    # ========================================================================

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID."""
        self._reconnect_if_needed()

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM research_jobs WHERE job_id = %s",
                    (job_id,)
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to get job {job_id}: {e}")
            return None

    def get_result(self, job_id: str) -> Optional[Dict]:
        """Get result by job ID."""
        self._reconnect_if_needed()

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM research_results WHERE job_id = %s",
                    (job_id,)
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to get result for job {job_id}: {e}")
            return None

    def get_job_with_result(self, job_id: str) -> Optional[Dict]:
        """Get job with its result (if exists)."""
        self._reconnect_if_needed()

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        j.*,
                        r.thread_id,
                        r.final_report,
                        r.researcher_findings,
                        r.structured_output,
                        r.plan,
                        r.observations,
                        r.duration_seconds,
                        r.search_count,
                        r.crawl_count
                    FROM research_jobs j
                    LEFT JOIN research_results r ON j.job_id = r.job_id
                    WHERE j.job_id = %s
                    """,
                    (job_id,)
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to get job with result {job_id}: {e}")
            return None

    def list_jobs(
        self,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """List jobs with optional filters."""
        self._reconnect_if_needed()

        try:
            with self.conn.cursor() as cur:
                query = "SELECT * FROM research_jobs WHERE 1=1"
                params = []

                if status:
                    query += " AND status = %s"
                    params.append(status)

                if user_id:
                    query += " AND user_id = %s"
                    params.append(user_id)

                query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])

                cur.execute(query, params)
                results = cur.fetchall()
                return [dict(row) for row in results]
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
        error: Optional[str] = None
    ) -> bool:
        """Update job status and progress."""
        self._reconnect_if_needed()

        try:
            with self.conn.cursor() as cur:
                # Build dynamic update query
                updates = ["status = %s"]
                params = [status]

                if progress is not None:
                    updates.append("progress = %s")
                    params.append(progress)

                if current_step is not None:
                    updates.append("current_step = %s")
                    params.append(current_step)

                if steps_completed is not None:
                    updates.append("steps_completed = %s")
                    params.append(steps_completed)

                if total_steps is not None:
                    updates.append("total_steps = %s")
                    params.append(total_steps)

                if error is not None:
                    updates.append("error = %s")
                    params.append(error)

                # Set started_at if moving from pending
                if status != 'pending':
                    updates.append("started_at = COALESCE(started_at, NOW())")

                # Set completed_at if completed or failed
                if status in ('completed', 'failed'):
                    updates.append("completed_at = NOW()")

                params.append(job_id)

                query = f"""
                    UPDATE research_jobs
                    SET {', '.join(updates)}
                    WHERE job_id = %s
                """

                cur.execute(query, params)
                self.conn.commit()

                updated = cur.rowcount > 0
                if updated:
                    logger.info(f"Updated job {job_id} status to {status}")
                return updated
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to update job {job_id}: {e}")
            return False

    # ========================================================================
    # DELETE operations
    # ========================================================================

    def delete_job(self, job_id: str) -> bool:
        """
        Delete job and its result (CASCADE).

        Returns:
            True if deleted, False otherwise
        """
        self._reconnect_if_needed()

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM research_jobs WHERE job_id = %s",
                    (job_id,)
                )
                self.conn.commit()

                deleted = cur.rowcount > 0
                if deleted:
                    logger.info(f"Deleted job {job_id}")
                return deleted
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to delete job {job_id}: {e}")
            return False

    def delete_old_jobs(self, days: int = 30) -> int:
        """
        Delete completed/failed jobs older than specified days.

        Returns:
            Number of jobs deleted
        """
        self._reconnect_if_needed()

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM research_jobs
                    WHERE status IN ('completed', 'failed')
                      AND completed_at < NOW() - INTERVAL '%s days'
                    """,
                    (days,)
                )
                self.conn.commit()

                count = cur.rowcount
                logger.info(f"Deleted {count} old jobs (older than {days} days)")
                return count
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to delete old jobs: {e}")
            return 0
