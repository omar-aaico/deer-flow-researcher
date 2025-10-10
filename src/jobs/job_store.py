# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from supabase import create_client, Client

logger = logging.getLogger(__name__)


class JobStore:
    """
    Handles all database operations for research jobs using Supabase.

    This class provides methods to create, retrieve, and update jobs
    stored in the Supabase PostgreSQL database.
    """

    def __init__(self):
        """Initialize the Supabase client."""
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")  # Use service_role key

        if not supabase_url or not supabase_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY environment variables must be set. "
                "Get these from your Supabase project settings."
            )

        self.client: Client = create_client(supabase_url, supabase_key)
        logger.info("JobStore initialized with Supabase connection")

    async def test_connection(self) -> bool:
        """
        Test the Supabase connection by querying the jobs table.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.client.table("jobs").select("count", count="exact").limit(0).execute()
            logger.info("Supabase connection test successful")
            return True
        except Exception as e:
            logger.error(f"Supabase connection test failed: {e}")
            return False

    async def create_job(self, job_data: Dict) -> str:
        """
        Create a new pending job in the database.

        Args:
            job_data: Dictionary containing:
                - prompt (str): Research question
                - breadth (int): Number of searches per step (default: 2)
                - depth (int): Number of iterations (default: 1)
                - search_provider (str): 'tavily' or 'firecrawl' (default: 'tavily')
                - client_id (str): Identifier for the API key owner
                - output_schema (dict, optional): JSON schema for structured extraction

        Returns:
            str: UUID of the created job

        Raises:
            Exception: If job creation fails
        """
        try:
            # Prepare job data with defaults
            insert_data = {
                "prompt": job_data["prompt"],
                "breadth": job_data.get("breadth", 2),
                "depth": job_data.get("depth", 1),
                "search_provider": job_data.get("search_provider", "tavily"),
                "client_id": job_data["client_id"],
                "status": "pending",
                "output_schema": job_data.get("output_schema"),
            }

            # Insert into database
            response = (
                self.client.table("jobs")
                .insert(insert_data)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise Exception("Job creation returned no data")

            job_id = response.data[0]["job_id"]
            logger.info(f"Created job {job_id} for client {insert_data['client_id']}")

            return str(job_id)

        except Exception as e:
            logger.error(f"Failed to create job: {e}")
            raise

    async def get_job(self, job_id: str, include_results: bool = True) -> Optional[Dict]:
        """
        Retrieve a job by its ID, optionally including results.

        Args:
            job_id: UUID of the job to retrieve
            include_results: If True, join with job_results table to get full data

        Returns:
            Dict containing job data (and results if include_results=True), or None if not found
        """
        try:
            if include_results:
                # Join jobs with job_results to get all data
                response = (
                    self.client.table("jobs")
                    .select("*, job_results(*)")
                    .eq("job_id", job_id)
                    .maybe_single()
                    .execute()
                )

                if response.data:
                    # Flatten the structure - merge job_results into main dict
                    job_data = response.data.copy()
                    if job_data.get("job_results"):
                        results = job_data.pop("job_results")
                        job_data["final_report"] = results.get("final_report")
                        job_data["structured_output"] = results.get("structured_output")
                        job_data["cost_tracking"] = results.get("cost_tracking")

                    logger.debug(f"Retrieved job {job_id} with results")
                    return job_data
            else:
                # Get only job metadata (no results)
                response = (
                    self.client.table("jobs")
                    .select("*")
                    .eq("job_id", job_id)
                    .maybe_single()
                    .execute()
                )

                if response.data:
                    logger.debug(f"Retrieved job {job_id} (metadata only)")
                    return response.data

            logger.warning(f"Job {job_id} not found")
            return None

        except Exception as e:
            logger.error(f"Failed to get job {job_id}: {e}")
            raise

    async def update_job(self, job_id: str, updates: Dict) -> bool:
        """
        Update a job's fields intelligently (separates metadata from results).

        Args:
            job_id: UUID of the job to update
            updates: Dictionary of fields to update

        Returns:
            True if update successful, False otherwise
        """
        try:
            # Separate metadata fields (goes to jobs table) from result fields (goes to job_results table)
            metadata_fields = {
                "status",
                "started_at",
                "completed_at",
                "searches_executed",
                "estimated_cost_usd",
                "error",
            }

            result_fields = {
                "final_report",
                "structured_output",
                "cost_tracking",
            }

            # Split updates into two dicts
            metadata_updates = {k: v for k, v in updates.items() if k in metadata_fields}
            results_updates = {k: v for k, v in updates.items() if k in result_fields}

            success = True

            # Update metadata in jobs table
            if metadata_updates:
                response = (
                    self.client.table("jobs")
                    .update(metadata_updates)
                    .eq("job_id", job_id)
                    .execute()
                )
                if not response.data:
                    logger.warning(f"No rows updated in jobs table for {job_id}")
                    success = False
                else:
                    logger.info(f"Updated job metadata {job_id}: {list(metadata_updates.keys())}")

            # Update/insert results in job_results table
            if results_updates:
                results_updates["updated_at"] = "NOW()"

                # Try to update first
                response = (
                    self.client.table("job_results")
                    .update(results_updates)
                    .eq("job_id", job_id)
                    .execute()
                )

                # If no rows updated, insert new record
                if not response.data or len(response.data) == 0:
                    results_updates["job_id"] = job_id
                    response = (
                        self.client.table("job_results")
                        .insert(results_updates)
                        .execute()
                    )

                if response.data:
                    logger.info(f"Updated job results {job_id}: {list(results_updates.keys())}")
                else:
                    logger.warning(f"Failed to update job_results for {job_id}")
                    success = False

            return success

        except Exception as e:
            logger.error(f"Failed to update job {job_id}: {e}")
            raise

    async def get_next_pending_job(self) -> Optional[Dict]:
        """
        Get the next pending job in FIFO order and mark it as processing.

        This method atomically retrieves the oldest pending job and
        updates its status to 'processing' to prevent race conditions.

        Returns:
            Dict containing job data, or None if no pending jobs
        """
        try:
            # Call the PostgreSQL function that atomically gets and updates
            response = self.client.rpc("get_next_pending_job").execute()

            if response.data and len(response.data) > 0:
                job = response.data[0]
                logger.info(f"Retrieved next pending job: {job['job_id']}")
                return job
            else:
                logger.debug("No pending jobs found")
                return None

        except Exception as e:
            logger.error(f"Failed to get next pending job: {e}")
            raise

    async def get_jobs_by_client(
        self, client_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict]:
        """
        Get all jobs for a specific client, ordered by creation date.

        Args:
            client_id: Client identifier to filter by
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip

        Returns:
            List of job dictionaries
        """
        try:
            response = (
                self.client.table("jobs")
                .select("*")
                .eq("client_id", client_id)
                .order("created_at", desc=True)
                .limit(limit)
                .offset(offset)
                .execute()
            )

            logger.debug(f"Retrieved {len(response.data)} jobs for client {client_id}")
            return response.data

        except Exception as e:
            logger.error(f"Failed to get jobs for client {client_id}: {e}")
            raise

    async def delete_old_jobs(self, days: int = 30) -> int:
        """
        Delete completed/failed jobs older than specified days.

        Args:
            days: Number of days to retain jobs (default: 30)

        Returns:
            Number of jobs deleted
        """
        try:
            # Note: Supabase Python client doesn't support interval calculations
            # This query needs to be run manually or via RPC function
            logger.warning(
                "delete_old_jobs() should be implemented via PostgreSQL scheduled job. "
                f"Manual query: DELETE FROM jobs WHERE status IN ('completed', 'failed') "
                f"AND completed_at < NOW() - INTERVAL '{days} days'"
            )
            return 0

        except Exception as e:
            logger.error(f"Failed to delete old jobs: {e}")
            raise
