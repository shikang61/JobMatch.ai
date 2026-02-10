-- Job description summary (key skills, cultural fit, advantageous skills) from LLM
ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS job_summary JSONB;

COMMENT ON COLUMN jobs.job_summary IS 'LLM summary: key_skills, qualifications, cultural_fit, advantageous_skills';
