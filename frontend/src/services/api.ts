import axios, { AxiosError } from "axios";

const API_BASE = "/api";

// Auth types (defined early so interceptors can reference them)
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  async (err: AxiosError) => {
    const status = err.response?.status;
    if (status === 401) {
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        try {
          const { data } = await axios.post<TokenResponse>(
            `${API_BASE}/auth/refresh`,
            { refresh_token: refresh }
          );
          // Store both new access and rotated refresh token
          localStorage.setItem("access_token", data.access_token);
          if (data.refresh_token) {
            localStorage.setItem("refresh_token", data.refresh_token);
          }
          if (err.config) {
            err.config.headers.Authorization = `Bearer ${data.access_token}`;
            return api.request(err.config);
          }
        } catch {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
        }
      } else {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export function register(email: string, password: string) {
  return api.post<TokenResponse>("/auth/register", { email, password }).then((r) => r.data);
}

export function login(email: string, password: string) {
  return api.post<TokenResponse>("/auth/login", { email, password }).then((r) => r.data);
}

export function refreshTokens(refresh_token: string) {
  return api.post<TokenResponse>("/auth/refresh", { refresh_token }).then((r) => r.data);
}

/** Permanently delete the current user's account and all data. Requires auth. */
export function deleteAccount() {
  return api.delete<{ detail: string }>("/auth/account").then((r) => r.data);
}

// Profile
export interface SkillCompetency {
  skill: string;
  level: number; // 1-5
}

export interface Profile {
  id: string;
  user_id: string;
  full_name: string | null;
  preferred_location: string | null;
  has_cv_file: boolean;
  cv_file_name: string | null;
  parsed_skills: string[];
  skill_competencies: SkillCompetency[];
  parsed_experience: Record<string, unknown>[];
  parsed_education: string[];
  experience_years: number | null;
  suggested_job_titles: string[];
}

export function getProfile() {
  return api.get<Profile>("/profile/me").then((r) => r.data);
}

export function updateProfile(data: { full_name?: string | null; preferred_location?: string | null }) {
  return api.put<Profile>("/profile/me", data).then((r) => r.data);
}

export function uploadCV(file: File) {
  const form = new FormData();
  form.append("file", file);
  return api.post<Profile>("/profile/cv-upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
}

export function getCvFileUrl(): string {
  // Returns the URL to fetch the CV file (auth handled by interceptor cookie)
  return `${API_BASE}/profile/cv-file`;
}

// Jobs & matches
export interface JobMatch {
  id: string;
  job_id: string;
  compatibility_score: number;
  match_details: {
    skill_match_required?: number;
    skill_match_preferred?: number;
    matched_required_skills?: string[];
    missing_required_skills?: string[];
    experience_score?: number;
    recency_score?: number;
  };
  job_title: string;
  company_name: string;
  location: string | null;
  job_url: string | null;
  posted_date: string | null;
  industry: string | null;
}

export interface MatchListResponse {
  matches: JobMatch[];
  total: number;
}

export function getJobMatches() {
  return api.get<MatchListResponse>("/jobs/matches").then((r) => r.data);
}

export function recomputeJobMatches() {
  return api.get<MatchListResponse>("/jobs/matches?recompute=true").then((r) => r.data);
}

export interface JobSummary {
  key_skills: string[];
  qualifications: string[];
  cultural_fit: string;
  advantageous_skills: string[];
  expected_salary?: string;
  industry?: string;
}

export interface Job {
  id: string;
  company_name: string;
  job_title: string;
  job_description: string;
  required_skills: string[];
  preferred_skills: string[];
  experience_level: string | null;
  location: string | null;
  job_url: string | null;
  source: string | null;
  posted_date: string | null;
  job_summary?: JobSummary | null;
}

export function getJob(jobId: string) {
  return api.get<Job>(`/jobs/${jobId}`).then((r) => r.data);
}

export function seedJobs() {
  return api.post<{ message: string; count: number }>("/jobs/seed-jobs").then((r) => r.data);
}

// Scraping
export interface ScrapeRequest {
  query: string;
  location: string;
  sources: string[];
  max_per_source: number;
  fetch_details: boolean;
}

export interface ScrapeSourceResult {
  source: string;
  found: number;
  new: number;
  duplicates: number;
  enriched: number;
  errors: string[];
}

export interface ScrapeResponse {
  total_new: number;
  sources: ScrapeSourceResult[];
}

export function scrapeJobs(params: Partial<ScrapeRequest> = {}) {
  return api.post<ScrapeResponse>("/jobs/scrape", {
    query: params.query || "software engineer",
    location: params.location || "",
    sources: params.sources || ["indeed", "linkedin"],
    max_per_source: params.max_per_source || 15,
    fetch_details: params.fetch_details ?? true,
  }).then((r) => r.data);
}

// Deep research scrape (SSE)
export interface DeepScrapeParams {
  role: string;
  location: string;
  max_jobs_per_company: number;
  fetch_details: boolean;
}

/**
 * Start a deep research scrape via SSE. Returns an EventSource-like
 * controller. The caller provides callbacks for each event type.
 */
export function startDeepScrape(
  params: DeepScrapeParams,
  callbacks: {
    onEvent: (event: string, data: Record<string, unknown>) => void;
    onError: (msg: string) => void;
    onDone: () => void;
  }
): AbortController {
  const controller = new AbortController();
  const token = localStorage.getItem("access_token") || "";

  // We use fetch (not EventSource) because EventSource doesn't support POST or custom headers
  fetch(`${API_BASE}/jobs/deep-scrape`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(params),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        try {
          const err = JSON.parse(text);
          callbacks.onError(err.detail || "Deep scrape failed");
        } catch {
          callbacks.onError(`HTTP ${response.status}`);
        }
        return;
      }
      const reader = response.body?.getReader();
      if (!reader) {
        callbacks.onError("No response stream");
        return;
      }
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // Parse SSE frames from the buffer
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // keep incomplete line in buffer
        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ") && currentEvent) {
            try {
              const data = JSON.parse(line.slice(6));
              callbacks.onEvent(currentEvent, data);
            } catch {
              // ignore malformed data
            }
            currentEvent = "";
          }
        }
      }
      callbacks.onDone();
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        callbacks.onError(err.message || "Connection failed");
      }
    });

  return controller;
}

// Interview prep
export interface PrepQuestion {
  question: string;
  type: string;
  category: string;
  difficulty: string;
}

export interface PrepKit {
  id: string;
  job_match_id: string;
  questions: PrepQuestion[];
  company_insights: string | null;
  tips: string[];
  job_title?: string | null;
  company_name?: string | null;
}

export interface StartSessionOptions {
  num_questions?: number;
  question_types?: string[];
}

export interface StartSessionResponse {
  session_id: string;
  prep_kit_id: string;
  status: string;
  questions: PrepQuestion[];
  job_title: string;
  company_name: string;
}

export function createPrepKit(matchId: string) {
  return api.post<PrepKit>(`/interviews/prep/${matchId}`).then((r) => r.data);
}

export function getPrepKit(prepId: string) {
  return api.get<PrepKit>(`/interviews/prep/${prepId}`).then((r) => r.data);
}

export function startSession(
  prepKitId: string,
  options: StartSessionOptions = {}
) {
  return api
    .post<StartSessionResponse>("/interviews/start", {
      prep_kit_id: prepKitId,
      num_questions: options.num_questions ?? 10,
      question_types: options.question_types ?? ["behavioral", "technical", "company"],
    })
    .then((r) => r.data);
}

export interface SessionDetail {
  session_id: string;
  prep_kit_id: string;
  status: string;
  performance_score: number | null;
  completed_at: string | null;
  questions: PrepQuestion[];
  job_title: string;
  company_name: string;
  started_at: string;
}

export function getSession(sessionId: string) {
  return api.get<SessionDetail>(`/interviews/session/${sessionId}`).then((r) => r.data);
}

export interface SessionListItem {
  session_id: string;
  status: string;
  performance_score: number | null;
  completed_at: string | null;
  started_at: string;
  job_title: string;
  company_name: string;
  num_questions: number;
}

export function listSessions(prepKitId?: string) {
  const params = prepKitId ? { prep_kit_id: prepKitId } : {};
  return api
    .get<{ sessions: SessionListItem[] }>("/interviews/sessions", { params })
    .then((r) => r.data);
}

export interface EvaluateAnswerResponse {
  score: number;
  feedback: string;
  strengths: string[];
  improvements: string[];
}

export function evaluateAnswer(params: {
  session_id: string;
  question: string;
  question_type: string;
  answer: string;
  job_title: string;
  company_name: string;
}) {
  return api.post<EvaluateAnswerResponse>("/interviews/evaluate-answer", params).then((r) => r.data);
}

export interface CompleteSessionResponse {
  overall_score: number;
  summary: string;
  strengths: string[];
  areas_to_improve: string[];
  recommendation: string;
  session_id: string;
}

export function completeSession(params: {
  session_id: string;
  answers: Record<string, unknown>[];
  job_title: string;
  company_name: string;
}) {
  return api.post<CompleteSessionResponse>("/interviews/complete-session", params).then((r) => r.data);
}

// Progress
export interface ProgressStats {
  sessions_completed: number;
  average_score: number | null;
  total_questions_practiced: number;
  readiness_percentage: number;
}

export function getProgressStats() {
  return api.get<ProgressStats>("/progress/stats").then((r) => r.data);
}

export interface JobPreparationItem {
  match_id: string;
  job_id: string;
  job_title: string;
  company_name: string;
  compatibility_score: number;
  has_prep_kit: boolean;
  prep_kit_id: string | null;
  sessions_completed: number;
  total_sessions: number;
  last_practice_at: string | null;
  best_score: number | null;
  readiness_score: number;
}

export function getProgressPreparations() {
  return api
    .get<{ preparations: JobPreparationItem[] }>("/progress/preparations")
    .then((r) => r.data);
}
