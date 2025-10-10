-- DeerFlow Database Schema for Job Management
-- Database: PostgreSQL (Supabase compatible)
-- Created: 2025-10-10

-- ============================================================================
-- Table 1: research_jobs
-- Purpose: Track job metadata, status, and lifecycle
-- ============================================================================

CREATE TABLE IF NOT EXISTS research_jobs (
    -- Primary identifier
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User/Auth information
    user_id TEXT,  -- Optional: for multi-tenant setups
    api_key_name TEXT,  -- Which API key was used (admin, dev, etc.)

    -- Job configuration
    query TEXT NOT NULL,
    report_style TEXT DEFAULT 'academic',
    max_step_num INTEGER DEFAULT 3,
    max_search_results INTEGER DEFAULT 3,
    search_provider TEXT DEFAULT 'tavily',
    enable_background_investigation BOOLEAN DEFAULT TRUE,
    enable_deep_thinking BOOLEAN DEFAULT FALSE,
    auto_accepted_plan BOOLEAN DEFAULT TRUE,

    -- Output schema (for structured output)
    output_schema JSONB,  -- Stores the JSON schema if provided

    -- RAG resources
    resources JSONB,  -- Array of resource objects

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending',
    -- Status values: pending, coordinating, planning, researching, reporting, completed, failed

    -- Progress tracking
    progress DECIMAL(5,2) DEFAULT 0.0,  -- 0.00 to 100.00
    current_step TEXT,  -- Human-readable current step
    steps_completed INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 0,

    -- Error handling
    error TEXT,  -- Error message if status is 'failed'

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,  -- When actual research started
    completed_at TIMESTAMPTZ,  -- When job finished (success or failure)

    -- Metadata
    metadata JSONB,  -- Extra metadata (IP address, user agent, etc.)

    -- Indexes
    CONSTRAINT valid_status CHECK (status IN ('pending', 'coordinating', 'planning', 'researching', 'reporting', 'completed', 'failed'))
);

-- Indexes for research_jobs
CREATE INDEX IF NOT EXISTS idx_research_jobs_status ON research_jobs(status);
CREATE INDEX IF NOT EXISTS idx_research_jobs_created_at ON research_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_jobs_user_id ON research_jobs(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_research_jobs_api_key ON research_jobs(api_key_name) WHERE api_key_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_research_jobs_completed ON research_jobs(completed_at DESC) WHERE completed_at IS NOT NULL;

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_research_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_jobs_updated_at_trigger
    BEFORE UPDATE ON research_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_research_jobs_updated_at();

-- ============================================================================
-- Table 2: research_results
-- Purpose: Store completed research outputs (reports, structured data)
-- ============================================================================

CREATE TABLE IF NOT EXISTS research_results (
    -- Primary identifier
    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign key to job
    job_id UUID NOT NULL REFERENCES research_jobs(job_id) ON DELETE CASCADE,

    -- Thread ID for conversation continuity
    thread_id UUID,

    -- Research outputs
    final_report TEXT,  -- Markdown formatted report
    researcher_findings TEXT,  -- Raw findings from researcher
    structured_output JSONB,  -- Extracted structured data (if schema provided)

    -- Research plan
    plan JSONB,  -- The executed research plan

    -- Observations (per-step findings)
    observations JSONB,  -- Array of observation objects

    -- Metadata
    token_usage JSONB,  -- LLM token usage statistics
    search_count INTEGER DEFAULT 0,  -- Number of searches performed
    crawl_count INTEGER DEFAULT 0,  -- Number of pages crawled

    -- Performance metrics
    duration_seconds DECIMAL(10,2),  -- Total execution time

    -- Quality metrics (optional)
    report_length INTEGER,  -- Character count of final_report
    sources_count INTEGER,  -- Number of sources cited

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_job FOREIGN KEY (job_id) REFERENCES research_jobs(job_id) ON DELETE CASCADE
);

-- Indexes for research_results
CREATE INDEX IF NOT EXISTS idx_research_results_job_id ON research_results(job_id);
CREATE INDEX IF NOT EXISTS idx_research_results_thread_id ON research_results(thread_id) WHERE thread_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_research_results_created_at ON research_results(created_at DESC);

-- Full-text search on reports (optional, for search functionality)
CREATE INDEX IF NOT EXISTS idx_research_results_report_fts ON research_results USING GIN (to_tsvector('english', final_report));

-- ============================================================================
-- Helper Views
-- ============================================================================

-- View: Combined job and result data
CREATE OR REPLACE VIEW research_jobs_with_results AS
SELECT
    j.job_id,
    j.user_id,
    j.api_key_name,
    j.query,
    j.report_style,
    j.status,
    j.progress,
    j.error,
    j.created_at,
    j.updated_at,
    j.completed_at,
    r.thread_id,
    r.final_report,
    r.structured_output,
    r.duration_seconds,
    r.search_count,
    r.crawl_count
FROM research_jobs j
LEFT JOIN research_results r ON j.job_id = r.job_id;

-- View: Active jobs (not completed/failed)
CREATE OR REPLACE VIEW active_research_jobs AS
SELECT *
FROM research_jobs
WHERE status NOT IN ('completed', 'failed')
ORDER BY created_at DESC;

-- View: Completed jobs (last 30 days)
CREATE OR REPLACE VIEW recent_completed_jobs AS
SELECT
    j.*,
    r.duration_seconds,
    r.report_length,
    r.sources_count
FROM research_jobs j
LEFT JOIN research_results r ON j.job_id = r.job_id
WHERE j.status = 'completed'
  AND j.completed_at > NOW() - INTERVAL '30 days'
ORDER BY j.completed_at DESC;

-- ============================================================================
-- Cleanup Functions
-- ============================================================================

-- Function: Delete old completed jobs (older than X days)
CREATE OR REPLACE FUNCTION cleanup_old_jobs(days_to_keep INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM research_jobs
    WHERE status IN ('completed', 'failed')
      AND completed_at < NOW() - (days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function: Get job statistics
CREATE OR REPLACE FUNCTION get_job_statistics(since_date TIMESTAMPTZ DEFAULT NOW() - INTERVAL '7 days')
RETURNS TABLE (
    total_jobs BIGINT,
    completed_jobs BIGINT,
    failed_jobs BIGINT,
    active_jobs BIGINT,
    avg_duration_seconds DECIMAL,
    total_searches BIGINT,
    total_crawls BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT as total_jobs,
        COUNT(*) FILTER (WHERE j.status = 'completed')::BIGINT as completed_jobs,
        COUNT(*) FILTER (WHERE j.status = 'failed')::BIGINT as failed_jobs,
        COUNT(*) FILTER (WHERE j.status NOT IN ('completed', 'failed'))::BIGINT as active_jobs,
        AVG(r.duration_seconds) as avg_duration_seconds,
        SUM(r.search_count)::BIGINT as total_searches,
        SUM(r.crawl_count)::BIGINT as total_crawls
    FROM research_jobs j
    LEFT JOIN research_results r ON j.job_id = r.job_id
    WHERE j.created_at >= since_date;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Sample Queries (for reference)
-- ============================================================================

-- Get job with result
-- SELECT * FROM research_jobs_with_results WHERE job_id = 'xxx';

-- Get all active jobs
-- SELECT * FROM active_research_jobs;

-- Get user's job history
-- SELECT * FROM research_jobs WHERE user_id = 'xxx' ORDER BY created_at DESC;

-- Get statistics for last 7 days
-- SELECT * FROM get_job_statistics();

-- Cleanup jobs older than 30 days
-- SELECT cleanup_old_jobs(30);

-- Find jobs by query text
-- SELECT job_id, query, status, created_at
-- FROM research_jobs
-- WHERE query ILIKE '%keyword%'
-- ORDER BY created_at DESC;

-- Get failed jobs for debugging
-- SELECT job_id, query, error, created_at
-- FROM research_jobs
-- WHERE status = 'failed'
-- ORDER BY created_at DESC
-- LIMIT 10;

-- ============================================================================
-- Row Level Security (RLS) - Optional, for multi-tenant setups
-- ============================================================================

-- Enable RLS on tables
-- ALTER TABLE research_jobs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE research_results ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own jobs
-- CREATE POLICY user_jobs_policy ON research_jobs
--     FOR ALL
--     USING (auth.uid()::text = user_id);

-- Policy: Users can only see results for their jobs
-- CREATE POLICY user_results_policy ON research_results
--     FOR ALL
--     USING (job_id IN (SELECT job_id FROM research_jobs WHERE user_id = auth.uid()::text));

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE research_jobs IS 'Tracks research job metadata, status, and configuration';
COMMENT ON TABLE research_results IS 'Stores completed research outputs including reports and structured data';

COMMENT ON COLUMN research_jobs.job_id IS 'Unique identifier for the research job';
COMMENT ON COLUMN research_jobs.status IS 'Current job status: pending, coordinating, planning, researching, reporting, completed, failed';
COMMENT ON COLUMN research_jobs.output_schema IS 'JSON Schema for structured output extraction';
COMMENT ON COLUMN research_results.final_report IS 'Markdown formatted final report';
COMMENT ON COLUMN research_results.structured_output IS 'Extracted structured data based on output_schema';
