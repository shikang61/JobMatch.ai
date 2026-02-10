-- Job Match Platform - Initial Schema
-- PostgreSQL 15+
-- Run with: psql $DATABASE_URL -f 001_initial_schema.sql

-- Users table (authentication)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- User profiles (CV, skills, experience)
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    full_name VARCHAR(255),
    cv_text TEXT,
    cv_file_url VARCHAR(500),
    parsed_skills JSONB DEFAULT '[]',
    parsed_experience JSONB DEFAULT '[]',
    parsed_education JSONB DEFAULT '[]',
    experience_years INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);

-- Jobs (scraped from various sources)
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name VARCHAR(255) NOT NULL,
    job_title VARCHAR(255) NOT NULL,
    job_description TEXT NOT NULL,
    required_skills JSONB DEFAULT '[]',
    preferred_skills JSONB DEFAULT '[]',
    experience_level VARCHAR(50),
    experience_years_range VARCHAR(50),
    key_responsibilities JSONB DEFAULT '[]',
    company_size VARCHAR(50),
    location VARCHAR(255),
    job_url VARCHAR(500) UNIQUE,
    source VARCHAR(100),
    posted_date DATE,
    is_active BOOLEAN DEFAULT true,
    raw_html_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_company_name ON jobs(company_name);
CREATE INDEX IF NOT EXISTS idx_jobs_is_active ON jobs(is_active);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);

-- Job matches (user profile <-> job compatibility)
CREATE TABLE IF NOT EXISTS job_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_profile_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    compatibility_score DECIMAL(5,2) NOT NULL,
    match_details JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_profile_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_job_matches_profile ON job_matches(user_profile_id);
CREATE INDEX IF NOT EXISTS idx_job_matches_job ON job_matches(job_id);
CREATE INDEX IF NOT EXISTS idx_job_matches_score ON job_matches(compatibility_score DESC);

-- Interview prep kits (generated questions per match)
CREATE TABLE IF NOT EXISTS interview_prep_kits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_match_id UUID NOT NULL REFERENCES job_matches(id) ON DELETE CASCADE,
    questions JSONB NOT NULL DEFAULT '[]',
    company_insights TEXT,
    tips JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prep_kits_match ON interview_prep_kits(job_match_id);

-- Interview practice sessions
CREATE TABLE IF NOT EXISTS interview_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prep_kit_id UUID NOT NULL REFERENCES interview_prep_kits(id) ON DELETE CASCADE,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    transcript JSONB DEFAULT '[]',
    performance_score INTEGER,
    status VARCHAR(50) DEFAULT 'in_progress',
    answers_json JSONB DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_sessions_prep_kit ON interview_sessions(prep_kit_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON interview_sessions(status);

-- Refresh tokens for JWT (optional but recommended for invalidation)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at);
