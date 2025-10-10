#!/usr/bin/env python3
"""
Comprehensive test script for Supabase job storage.
Tests all CRUD operations on research_jobs and research_results tables.

Usage:
    SUPABASE_URL=xxx SUPABASE_KEY=xxx python tests/test_supabase_store.py
"""

import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.supabase_job_store import SupabaseJobStore


class TestSupabaseStore:
    """Test suite for SupabaseJobStore."""

    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY required")

        self.store = SupabaseJobStore(supabase_url, supabase_key)
        self.test_job_id = str(uuid4())
        self.passed = 0
        self.failed = 0

    def log(self, message: str, success: bool = True):
        """Log test result."""
        symbol = "✅" if success else "❌"
        print(f"{symbol} {message}")
        if success:
            self.passed += 1
        else:
            self.failed += 1

    def test_create_job(self):
        """Test: Create a new job."""
        print("\n--- TEST 1: Create Job ---")
        try:
            job = self.store.create_job(
                job_id=self.test_job_id,
                query="Research Tesla comprehensively",
                report_style="sales_intelligence",
                max_step_num=3,
                output_schema={"type": "object", "properties": {"company": {"type": "string"}}},
                user_id="test_user",
                api_key_name="admin"
            )
            assert job["job_id"] == self.test_job_id
            assert job["status"] == "pending"
            self.log(f"Created job: {self.test_job_id}")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_get_job(self):
        """Test: Get job."""
        print("\n--- TEST 2: Get Job ---")
        try:
            job = self.store.get_job(self.test_job_id)
            assert job is not None
            assert job["query"] == "Research Tesla comprehensively"
            self.log(f"Retrieved job")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_update_to_planning(self):
        """Test: Update to planning."""
        print("\n--- TEST 3: Update to Planning ---")
        try:
            success = self.store.update_job_status(
                self.test_job_id,
                "planning",
                progress=20.0,
                current_step="Creating research plan"
            )
            assert success
            job = self.store.get_job(self.test_job_id)
            assert job["status"] == "planning"
            self.log("Updated to planning")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_update_to_researching(self):
        """Test: Update to researching."""
        print("\n--- TEST 4: Update to Researching ---")
        try:
            success = self.store.update_job_status(
                self.test_job_id,
                "researching",
                progress=60.0,
                current_step="Gathering data",
                steps_completed=2,
                total_steps=3
            )
            assert success
            self.log("Updated to researching")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_update_to_completed(self):
        """Test: Update to completed."""
        print("\n--- TEST 5: Update to Completed ---")
        try:
            success = self.store.update_job_status(
                self.test_job_id,
                "completed",
                progress=100.0,
                steps_completed=3
            )
            assert success
            job = self.store.get_job(self.test_job_id)
            assert job["status"] == "completed"
            assert job["completed_at"] is not None
            self.log("Updated to completed")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_create_result(self):
        """Test: Create result."""
        print("\n--- TEST 6: Create Result ---")
        try:
            result = self.store.create_result(
                job_id=self.test_job_id,
                thread_id=str(uuid4()),
                final_report="# Tesla Research\n\nComprehensive analysis.\n\n[Source](http://tesla.com)",
                researcher_findings="Key findings about Tesla",
                structured_output={"company": "Tesla Inc.", "ceo": "Elon Musk"},
                plan={"title": "Tesla Research", "steps": []},
                observations=[{"step": 1, "data": "test"}],
                duration_seconds=145.2,
                search_count=6,
                crawl_count=3
            )
            assert result["job_id"] == self.test_job_id
            self.log("Created result")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_get_result(self):
        """Test: Get result."""
        print("\n--- TEST 7: Get Result ---")
        try:
            result = self.store.get_result(self.test_job_id)
            assert result is not None
            assert "Tesla" in result["final_report"]
            assert result["structured_output"]["company"] == "Tesla Inc."
            self.log("Retrieved result")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_get_job_with_result(self):
        """Test: Get combined data."""
        print("\n--- TEST 8: Get Job With Result ---")
        try:
            data = self.store.get_job_with_result(self.test_job_id)
            assert data is not None
            assert data["status"] == "completed"
            assert data["final_report"] is not None
            assert data["duration_seconds"] == 145.2
            self.log("Retrieved combined data")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_list_jobs(self):
        """Test: List jobs."""
        print("\n--- TEST 9: List Jobs ---")
        try:
            all_jobs = self.store.list_jobs(limit=10)
            assert len(all_jobs) > 0
            self.log(f"Listed {len(all_jobs)} jobs")

            completed = self.store.list_jobs(status="completed", limit=10)
            assert len(completed) > 0
            self.log(f"Listed {len(completed)} completed jobs")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_failed_job(self):
        """Test: Create and fail a job."""
        print("\n--- TEST 10: Failed Job ---")
        try:
            failed_id = str(uuid4())
            self.store.create_job(failed_id, "Fail test")
            self.store.update_job_status(
                failed_id,
                "failed",
                error="Test error message"
            )
            job = self.store.get_job(failed_id)
            assert job["status"] == "failed"
            assert job["error"] == "Test error message"
            self.store.delete_job(failed_id)
            self.log("Failed job handled correctly")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def test_delete_job(self):
        """Test: Delete job."""
        print("\n--- TEST 11: Delete Job ---")
        try:
            delete_id = str(uuid4())
            self.store.create_job(delete_id, "Delete test")
            self.store.create_result(delete_id, final_report="Test")

            success = self.store.delete_job(delete_id)
            assert success

            job = self.store.get_job(delete_id)
            assert job is None

            result = self.store.get_result(delete_id)
            assert result is None
            self.log("Deleted job and result (CASCADE)")
            return True
        except Exception as e:
            self.log(f"Failed: {e}", False)
            return False

    def cleanup(self):
        """Cleanup test data."""
        print("\n--- CLEANUP ---")
        try:
            self.store.delete_job(self.test_job_id)
            self.log("Cleaned up test job")
        except:
            pass

    def run_all_tests(self):
        """Run all tests."""
        print("=" * 60)
        print("SUPABASE JOB STORE - COMPREHENSIVE TEST SUITE")
        print("=" * 60)

        tests = [
            self.test_create_job,
            self.test_get_job,
            self.test_update_to_planning,
            self.test_update_to_researching,
            self.test_update_to_completed,
            self.test_create_result,
            self.test_get_result,
            self.test_get_job_with_result,
            self.test_list_jobs,
            self.test_failed_job,
            self.test_delete_job,
        ]

        for test in tests:
            test()

        self.cleanup()

        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"Total:  {self.passed + self.failed}")

        if self.failed == 0:
            print("\n🎉 ALL TESTS PASSED!")
            return 0
        else:
            print(f"\n❌ {self.failed} test(s) failed")
            return 1


if __name__ == "__main__":
    try:
        tester = TestSupabaseStore()
        exit_code = tester.run_all_tests()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
