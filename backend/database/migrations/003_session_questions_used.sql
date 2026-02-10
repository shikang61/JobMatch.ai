-- Store the subset of questions used in each practice session (for saved practice per company)
ALTER TABLE interview_sessions
ADD COLUMN IF NOT EXISTS questions_used JSONB DEFAULT '[]';

COMMENT ON COLUMN interview_sessions.questions_used IS 'Questions selected for this session (question, type, category, difficulty)';
