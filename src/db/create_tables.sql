-- DeerFlow Database Tables
-- Run this SQL in your PostgreSQL/Supabase database

-- Table 1: Research Jobs (metadata and status)
CREATE TABLE IF NOT EXISTS research_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User tracking
    user_id TEXT,
    api_key_name TEXT,

    -- Job configuration
    query TEXT NOT NULL,
    report_style TEXT DEFAULT 'academic',
    max_step_num INTEGER DEFAULT 3,
    max_search_results INTEGER DEFAULT 3,
    search_provider TEXT DEFAULT 'tavily',
    enable_background_investigation BOOLEAN DEFAULT TRUE,
    enable_deep_thinking BOOLEAN DEFAULT FALSE,
    auto_accepted_plan BOOLEAN DEFAULT TRUE,
    output_schema JSONB,
    resources JSONB,

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending',
    progress DECIMAL(5,2) DEFAULT 0.0,
    current_step TEXT,
    steps_completed INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 0,
    error TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    CONSTRAINT valid_status CHECK (status IN ('pending', 'coordinating', 'planning', 'researching', 'reporting', 'completed', 'failed'))
);

-- Table 2: Research Results (outputs)
CREATE TABLE IF NOT EXISTS research_results (
    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES research_jobs(job_id) ON DELETE CASCADE,

    thread_id UUID,

    -- Outputs
    final_report TEXT,
    researcher_findings TEXT,
    structured_output JSONB,
    plan JSONB,
    observations JSONB,

    -- Metrics
    duration_seconds DECIMAL(10,2),
    search_count INTEGER DEFAULT 0,
    crawl_count INTEGER DEFAULT 0,
    report_length INTEGER,
    sources_count INTEGER,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_research_jobs_status ON research_jobs(status);
CREATE INDEX IF NOT EXISTS idx_research_jobs_created_at ON research_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_results_job_id ON research_results(job_id);

-- Auto-update trigger
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
