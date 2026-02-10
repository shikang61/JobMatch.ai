-- Migration 002: Profile enhancements
-- Adds: preferred_location, CV file storage, skill competencies, suggested job titles

ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS preferred_location VARCHAR(255),
  ADD COLUMN IF NOT EXISTS cv_file_data BYTEA,
  ADD COLUMN IF NOT EXISTS cv_file_name VARCHAR(255),
  ADD COLUMN IF NOT EXISTS cv_content_type VARCHAR(100),
  ADD COLUMN IF NOT EXISTS skill_competencies JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS suggested_job_titles JSONB NOT NULL DEFAULT '[]'::jsonb;
