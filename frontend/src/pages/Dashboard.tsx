import { useQuery, useMutation, useQueryClient } from "react-query";
import { Link } from "react-router-dom";
import {
  getProfile,
  getJobMatches,
  recomputeJobMatches,
  uploadCV,
  updateProfile,
  seedJobs,
  scrapeJobs,
  getCvFileUrl,
  startDeepScrape,
} from "../services/api";
import type { JobMatch, ScrapeResponse, SkillCompetency } from "../services/api";
import { useState, useEffect, useRef, useCallback } from "react";

// ---------------------------------------------------------------------------
// Skill competency bar chart (pure CSS)
// ---------------------------------------------------------------------------
const LEVEL_LABELS = ["", "Beginner", "Basic", "Intermediate", "Advanced", "Expert"];
const LEVEL_COLORS = ["", "bg-slate-400", "bg-blue-400", "bg-brand-500", "bg-emerald-500", "bg-amber-500"];

function SkillChart({ competencies }: { competencies: SkillCompetency[] }) {
  if (!competencies.length) return null;
  // Sort by level descending
  const sorted = [...competencies].sort((a, b) => b.level - a.level);
  return (
    <div className="space-y-2">
      {sorted.map((c) => (
        <div key={c.skill} className="flex items-center gap-3">
          <span
            title={c.skill}
            className="w-44 shrink-0 text-right text-sm text-slate-600"
          >
            {c.skill}
          </span>
          <div className="flex-1">
            <div className="h-5 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full transition-all ${LEVEL_COLORS[c.level] || "bg-slate-400"}`}
                style={{ width: `${(c.level / 5) * 100}%` }}
              />
            </div>
          </div>
          <span className="w-24 shrink-0 text-xs text-slate-500">
            {LEVEL_LABELS[c.level] || ""}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export default function Dashboard() {
  const queryClient = useQueryClient();
  const [fileError, setFileError] = useState("");
  const [seedError, setSeedError] = useState("");

  // Preferred location
  const [locationInput, setLocationInput] = useState("");
  const [locationSaved, setLocationSaved] = useState(false);

  // Scrape form state
  const [scrapeQuery, setScrapeQuery] = useState("software engineer");
  const [scrapeLocation, setScrapeLocation] = useState("");
  const [scrapeSources, setScrapeSources] = useState<string[]>(["indeed", "linkedin"]);
  const [scrapeResult, setScrapeResult] = useState<ScrapeResponse | null>(null);
  const [scrapeError, setScrapeError] = useState("");
  const [showScrapeForm, setShowScrapeForm] = useState(false);

  const { data: profile, isLoading: profileLoading } = useQuery("profile", getProfile, {
    retry: false,
  });
  const { data: matchesData, isLoading: matchesLoading } = useQuery(
    "jobMatches",
    getJobMatches,
    { retry: false }
  );

  // Sync preferred location from profile when it loads
  useEffect(() => {
    if (profile?.preferred_location) {
      setLocationInput(profile.preferred_location);
      setScrapeLocation(profile.preferred_location);
      setDeepLocation(profile.preferred_location);
    }
  }, [profile?.preferred_location]);

  const uploadMutation = useMutation(uploadCV, {
    onSuccess: () => {
      queryClient.invalidateQueries("profile");
      queryClient.invalidateQueries("jobMatches");
      setFileError("");
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setFileError(err?.response?.data?.detail ?? "Upload failed");
    },
  });

  const seedMutation = useMutation(seedJobs, {
    onSuccess: () => {
      queryClient.invalidateQueries("jobMatches");
      setSeedError("");
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setSeedError(err?.response?.data?.detail ?? "Failed to seed jobs");
    },
  });

  const scrapeMutation = useMutation(scrapeJobs, {
    onSuccess: (data) => {
      setScrapeResult(data);
      setScrapeError("");
      // Force recompute matches with newly scraped jobs
      recomputeJobMatches()
        .then(() => queryClient.invalidateQueries("jobMatches"))
        .catch(() => queryClient.invalidateQueries("jobMatches"));
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setScrapeError(err?.response?.data?.detail ?? "Scrape failed");
      setScrapeResult(null);
    },
  });

  const locationMutation = useMutation(
    (loc: string) => updateProfile({ preferred_location: loc || null }),
    {
      onSuccess: () => {
        queryClient.invalidateQueries("profile");
        setLocationSaved(true);
        setTimeout(() => setLocationSaved(false), 2000);
      },
    }
  );

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setFileError("File must be under 5MB");
      return;
    }
    if (!file.name.match(/\.(pdf|docx)$/i)) {
      setFileError("Only PDF and DOCX allowed");
      return;
    }
    uploadMutation.mutate(file);
  };

  const handleViewCV = () => {
    // Open the CV in a new tab; we need to add auth header
    // Use a fetch + blob approach for authenticated file download
    const token = localStorage.getItem("access_token");
    fetch(getCvFileUrl(), {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank");
      })
      .catch(() => alert("Failed to load CV file."));
  };

  const handleScrape = (e: React.FormEvent) => {
    e.preventDefault();
    setScrapeResult(null);
    setScrapeError("");
    scrapeMutation.mutate({
      query: scrapeQuery,
      location: scrapeLocation,
      sources: scrapeSources,
      max_per_source: 15,
      fetch_details: true,
    });
  };

  const handleSaveLocation = () => {
    locationMutation.mutate(locationInput);
    setScrapeLocation(locationInput);
    setDeepLocation(locationInput);
  };

  const toggleSource = (source: string) => {
    setScrapeSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]
    );
  };

  // Deep research state
  const [deepRole, setDeepRole] = useState("");
  const [deepLocation, setDeepLocation] = useState("");
  const [deepRunning, setDeepRunning] = useState(false);
  const [deepError, setDeepError] = useState("");
  const [deepCompanies, setDeepCompanies] = useState<
    { name: string; reason: string; industry: string; status: string; found?: number; new?: number }[]
  >([]);
  const [deepCurrentCompany, setDeepCurrentCompany] = useState("");
  const [deepSummary, setDeepSummary] = useState<{ total_new: number } | null>(null);
  const deepAbortRef = useRef<AbortController | null>(null);

  const handleDeepScrape = useCallback(() => {
    const role = deepRole.trim() || scrapeQuery.trim() || "software engineer";
    setDeepRunning(true);
    setDeepError("");
    setDeepCompanies([]);
    setDeepCurrentCompany("");
    setDeepSummary(null);

    deepAbortRef.current = startDeepScrape(
      {
        role,
        location: deepLocation || scrapeLocation || locationInput || "",
        max_jobs_per_company: 5,
        fetch_details: true,
      },
      {
        onEvent: (event, data) => {
          if (event === "research_start") {
            setDeepCurrentCompany("Researching best companies…");
          } else if (event === "companies_found") {
            const companies = (data.companies as { name: string; reason: string; industry: string }[]) || [];
            setDeepCompanies(companies.map((c) => ({ ...c, status: "pending" })));
            setDeepCurrentCompany("");
          } else if (event === "searching_company") {
            const name = (data.company as string) || "";
            setDeepCurrentCompany(name);
            setDeepCompanies((prev) =>
              prev.map((c) => (c.name === name ? { ...c, status: "searching" } : c))
            );
          } else if (event === "company_done") {
            const name = (data.company as string) || "";
            const found = (data.found as number) || 0;
            const newJobs = (data.new as number) || 0;
            const status = (data.status as string) || "done";
            setDeepCompanies((prev) =>
              prev.map((c) => (c.name === name ? { ...c, status, found, new: newJobs } : c))
            );
          } else if (event === "complete") {
            setDeepSummary({ total_new: (data.total_new as number) || 0 });
            setDeepRunning(false);
            setDeepCurrentCompany("");
            // Force recompute matches with the newly scraped jobs
            recomputeJobMatches().then(() => {
              queryClient.invalidateQueries("jobMatches");
            }).catch(() => {
              queryClient.invalidateQueries("jobMatches");
            });
          } else if (event === "error") {
            setDeepError((data.message as string) || "Deep research failed");
            setDeepRunning(false);
          }
        },
        onError: (msg) => {
          setDeepError(msg);
          setDeepRunning(false);
        },
        onDone: () => {
          setDeepRunning(false);
        },
      }
    );
  }, [deepRole, deepLocation, scrapeQuery, scrapeLocation, locationInput, queryClient]);

  const matches = matchesData?.matches ?? [];
  const suggestions = profile?.suggested_job_titles ?? [];
  const competencies = profile?.skill_competencies ?? [];

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-slate-800">Dashboard</h1>

      {/* ============================================================== */}
      {/* CV Upload + View + Profile */}
      {/* ============================================================== */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-800">Your CV &amp; Profile</h2>
        {profileLoading ? (
          <p className="text-slate-500">Loading profile…</p>
        ) : (
          <>
            {/* Action buttons */}
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <label className="cursor-pointer rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
                {uploadMutation.isLoading ? "Uploading…" : "Upload CV (PDF/DOCX)"}
                <input
                  type="file"
                  accept=".pdf,.docx"
                  className="hidden"
                  onChange={handleFile}
                  disabled={uploadMutation.isLoading}
                />
              </label>

              {profile?.has_cv_file && (
                <button
                  type="button"
                  onClick={handleViewCV}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                >
                  View CV ({profile.cv_file_name || "file"})
                </button>
              )}

              {matches.length === 0 && !matchesLoading && (
                <button
                  type="button"
                  onClick={() => seedMutation.mutate()}
                  disabled={seedMutation.isLoading}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                >
                  {seedMutation.isLoading ? "Seeding…" : "Seed sample jobs"}
                </button>
              )}
            </div>

            {fileError && <p className="mb-2 text-sm text-red-600">{fileError}</p>}
            {seedError && <p className="mb-2 text-sm text-red-600">{seedError}</p>}

            {/* Preferred location */}
            <div className="mb-4 flex items-center gap-3">
              <label htmlFor="prefLoc" className="text-sm font-medium text-slate-700">
                Preferred location
              </label>
              <input
                id="prefLoc"
                type="text"
                value={locationInput}
                onChange={(e) => setLocationInput(e.target.value)}
                placeholder="e.g. Remote, New York, London"
                className="w-60 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <button
                type="button"
                onClick={handleSaveLocation}
                disabled={locationMutation.isLoading}
                className="rounded-lg border border-brand-300 bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-100 disabled:opacity-50"
              >
                {locationMutation.isLoading ? "Saving…" : "Save"}
              </button>
              {locationSaved && <span className="text-xs text-green-600">Saved</span>}
            </div>

            {/* Skills summary */}
            {profile?.parsed_skills?.length ? (
              <div className="mb-1">
                <p className="mb-1 text-sm font-medium text-slate-700">
                  Skills
                  {profile.experience_years != null && (
                    <span className="ml-2 font-normal text-slate-500">
                      • {profile.experience_years} years experience
                    </span>
                  )}
                </p>
                <p className="text-sm text-slate-600">{profile.parsed_skills.join(", ")}</p>
              </div>
            ) : (
              <p className="text-slate-500">Upload a CV to get skill analysis, job suggestions, and matches.</p>
            )}

            {/* Skill competency chart */}
            {competencies.length > 0 && (
              <div className="mt-4">
                <p className="mb-2 text-sm font-medium text-slate-700">Skill competency</p>
                <SkillChart competencies={competencies} />
              </div>
            )}
          </>
        )}
      </section>

      {/* ============================================================== */}
      {/* Scrape Jobs (with suggested titles) */}
      {/* ============================================================== */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800">Scrape job postings</h2>
          <button
            type="button"
            onClick={() => setShowScrapeForm(!showScrapeForm)}
            className="text-sm font-medium text-brand-600 hover:underline"
          >
            {showScrapeForm ? "Hide" : "Show"} scraper
          </button>
        </div>

        {/* Suggested job titles from CV analysis */}
        {suggestions.length > 0 && (
          <div className="mb-4">
            <p className="mb-2 text-sm font-medium text-slate-700">
              Suggested searches based on your CV
            </p>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((title: string) => (
                <button
                  key={title}
                  type="button"
                  onClick={() => {
                    setScrapeQuery(title);
                    setDeepRole(title);
                    setShowScrapeForm(true);
                  }}
                  className="rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-sm text-brand-700 transition hover:bg-brand-100"
                >
                  {title}
                </button>
              ))}
            </div>
          </div>
        )}

        {showScrapeForm && (
          <form onSubmit={handleScrape} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="sq" className="mb-1 block text-sm font-medium text-slate-700">
                  Search keywords
                </label>
                <input
                  id="sq"
                  type="text"
                  value={scrapeQuery}
                  onChange={(e) => setScrapeQuery(e.target.value)}
                  placeholder="e.g. python developer"
                  required
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>
              <div>
                <label htmlFor="sl" className="mb-1 block text-sm font-medium text-slate-700">
                  Location
                </label>
                <input
                  id="sl"
                  type="text"
                  value={scrapeLocation}
                  onChange={(e) => setScrapeLocation(e.target.value)}
                  placeholder="e.g. Remote, New York"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Sources</p>
              <div className="flex gap-4">
                {["indeed", "linkedin"].map((src) => (
                  <label key={src} className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={scrapeSources.includes(src)}
                      onChange={() => toggleSource(src)}
                      className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                    />
                    {src.charAt(0).toUpperCase() + src.slice(1)}
                  </label>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-4">
              <button
                type="submit"
                disabled={scrapeMutation.isLoading || scrapeSources.length === 0}
                className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {scrapeMutation.isLoading ? "Scraping… (this takes a minute)" : "Start scrape"}
              </button>
              {scrapeMutation.isLoading && (
                <span className="text-sm text-slate-500">
                  Fetching from {scrapeSources.join(" & ")}…
                </span>
              )}
            </div>

            {scrapeError && <p className="text-sm text-red-600">{scrapeError}</p>}

            {scrapeResult && (
              <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                <p className="mb-2 font-medium text-green-800">
                  Scrape complete: {scrapeResult.total_new} new job
                  {scrapeResult.total_new !== 1 ? "s" : ""} added
                </p>
                <div className="space-y-1 text-sm text-green-700">
                  {scrapeResult.sources.map((s) => (
                    <p key={s.source}>
                      <span className="font-medium capitalize">{s.source}</span>: {s.found} found,{" "}
                      {s.new} new, {s.duplicates} duplicates
                      {s.enriched > 0 && `, ${s.enriched} with full descriptions`}
                      {s.errors.length > 0 && (
                        <span className="text-amber-700">
                          {" "}
                          ({s.errors.length} warning{s.errors.length > 1 ? "s" : ""})
                        </span>
                      )}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </form>
        )}

        {!showScrapeForm && suggestions.length === 0 && (
          <p className="text-sm text-slate-500">
            Search and import real job postings from Indeed and LinkedIn.
          </p>
        )}
      </section>

      {/* ============================================================== */}
      {/* Deep Research */}
      {/* ============================================================== */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-800">
          Deep research
        </h2>
        <p className="mb-4 text-sm text-slate-500">
          AI identifies the best companies for your role, then searches each one for openings.
        </p>

        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="deepRole" className="mb-1 block text-sm font-medium text-slate-700">
                Role
              </label>
              <input
                id="deepRole"
                type="text"
                value={deepRole}
                onChange={(e) => setDeepRole(e.target.value)}
                placeholder={scrapeQuery || "e.g. Senior Python Developer"}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
            <div>
              <label htmlFor="deepLoc" className="mb-1 block text-sm font-medium text-slate-700">
                Location
              </label>
              <input
                id="deepLoc"
                type="text"
                value={deepLocation}
                onChange={(e) => setDeepLocation(e.target.value)}
                placeholder="e.g. Remote, New York, London"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleDeepScrape}
              disabled={deepRunning}
              className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {deepRunning ? "Researching…" : "Start deep research"}
            </button>
            {deepRunning && deepAbortRef.current && (
              <button
                type="button"
                onClick={() => {
                  deepAbortRef.current?.abort();
                  setDeepRunning(false);
                  setDeepCurrentCompany("");
                }}
                className="rounded-lg border border-red-300 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
              >
                Stop
              </button>
            )}
          </div>
        </div>

        {deepError && <p className="mb-3 text-sm text-red-600">{deepError}</p>}

        {/* Live progress box */}
        {deepCompanies.length > 0 && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            {deepCurrentCompany && deepRunning && (
              <div className="mb-3 flex items-center gap-2">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-brand-500" />
                <span className="text-sm font-medium text-brand-700">
                  {deepCurrentCompany === "Researching best companies…"
                    ? deepCurrentCompany
                    : `Searching ${deepCurrentCompany}…`}
                </span>
              </div>
            )}
            <div className="space-y-2">
              {deepCompanies.map((c) => (
                <div
                  key={c.name}
                  className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-all ${
                    c.status === "searching"
                      ? "border border-brand-200 bg-brand-50"
                      : c.status === "done"
                      ? "bg-white border border-slate-100"
                      : c.status === "error"
                      ? "bg-red-50 border border-red-100"
                      : "bg-white border border-slate-100 opacity-60"
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {c.status === "searching" && (
                      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-brand-500 shrink-0" />
                    )}
                    {c.status === "done" && (
                      <span className="text-green-500 shrink-0">&#10003;</span>
                    )}
                    {c.status === "error" && (
                      <span className="text-red-400 shrink-0">&#10007;</span>
                    )}
                    {c.status === "pending" && (
                      <span className="inline-block h-2 w-2 rounded-full bg-slate-300 shrink-0" />
                    )}
                    <div className="min-w-0">
                      <span className="font-medium text-slate-800">{c.name}</span>
                      <span className="ml-2 text-xs text-slate-400">{c.industry}</span>
                      {c.status === "pending" && (
                        <p className="truncate text-xs text-slate-400">{c.reason}</p>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0 text-right text-xs text-slate-500">
                    {c.status === "done" && (
                      <span>
                        {c.found} found{(c.new ?? 0) > 0 ? `, ${c.new} new` : ""}
                      </span>
                    )}
                    {c.status === "searching" && <span className="text-brand-600">searching…</span>}
                    {c.status === "error" && <span className="text-red-500">failed</span>}
                  </div>
                </div>
              ))}
            </div>

            {deepSummary && (
              <div className="mt-3 rounded-lg border border-green-200 bg-green-50 p-3 text-sm font-medium text-green-800">
                Deep research complete: {deepSummary.total_new} new job
                {deepSummary.total_new !== 1 ? "s" : ""} added from{" "}
                {deepCompanies.filter((c) => c.status === "done").length} companies
              </div>
            )}
          </div>
        )}
      </section>

      {/* ============================================================== */}
      {/* Job matches (grouped by industry) */}
      {/* ============================================================== */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-800">Job matches</h2>
        {matchesLoading ? (
          <p className="text-slate-500">Loading matches…</p>
        ) : matches.length === 0 ? (
          <p className="text-slate-500">
            {profile?.parsed_skills?.length
              ? "No matches yet. Scrape jobs or seed samples above."
              : "Upload a CV and scrape or seed jobs to see matches."}
          </p>
        ) : (
          <div className="space-y-6">
            {(() => {
              const byIndustry = matches.reduce<Record<string, JobMatch[]>>(
                (acc, m) => {
                  const key = m.industry?.trim() || "Other";
                  if (!acc[key]) acc[key] = [];
                  acc[key].push(m);
                  return acc;
                },
                {}
              );
              const industries = Object.keys(byIndustry).sort((a, b) => a.localeCompare(b));
              return industries.map((industry) => {
                const list = byIndustry[industry];
                return (
                <div key={industry}>
                  <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                    {industry}
                  </h3>
                  <ul className="space-y-3">
                    {list.slice(0, 10).map((m) => (
                      <li key={m.id}>
                        <Link
                          to={`/match/${m.id}`}
                          className="block rounded-lg border border-slate-200 p-4 transition hover:border-brand-300 hover:bg-brand-50/50"
                        >
                          <div className="flex items-start justify-between">
                            <div>
                              <p className="font-medium text-slate-800">{m.job_title}</p>
                              <p className="text-sm text-slate-600">{m.company_name}</p>
                              {m.location && <p className="text-xs text-slate-500">{m.location}</p>}
                              {m.job_url && (
                                <a
                                  href={m.job_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  className="mt-1 inline-block text-xs text-brand-600 hover:underline"
                                >
                                  View original posting &rarr;
                                </a>
                              )}
                            </div>
                            <span className="rounded-full bg-brand-100 px-3 py-1 text-sm font-medium text-brand-700">
                              {Math.round(m.compatibility_score)}%
                            </span>
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              );
              });
            })()}
          </div>
        )}
      </section>
    </div>
  );
}
