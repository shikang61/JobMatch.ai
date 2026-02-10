import { useNavigate } from "react-router-dom";
import { useQuery } from "react-query";
import { getProgressStats, getProgressPreparations } from "../services/api";

export default function ProgressDashboard() {
  const navigate = useNavigate();
  const { data: stats, isLoading } = useQuery("progressStats", getProgressStats);
  const { data: prepData, isLoading: prepLoading } = useQuery(
    "progressPreparations",
    getProgressPreparations
  );

  if (isLoading) {
    return <p className="text-slate-500">Loading progress…</p>;
  }

  const s = stats ?? {
    sessions_completed: 0,
    average_score: null,
    total_questions_practiced: 0,
    readiness_percentage: 0,
  };
  const preparations = prepData?.preparations ?? [];

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-slate-800">Progress</h1>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <p className="text-sm font-medium text-slate-500">
            Sessions completed
          </p>
          <p className="text-2xl font-bold text-slate-800">
            {s.sessions_completed}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <p className="text-sm font-medium text-slate-500">Average score</p>
          <p className="text-2xl font-bold text-slate-800">
            {s.average_score != null ? `${Math.round(s.average_score)}%` : "—"}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <p className="text-sm font-medium text-slate-500">
            Questions practiced
          </p>
          <p className="text-2xl font-bold text-slate-800">
            {s.total_questions_practiced}
          </p>
        </div>
      </div>

      {/* Active job preparation progress */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-3 text-lg font-semibold text-slate-800">
          Active job preparation
        </h2>
        {prepLoading ? (
          <p className="text-slate-500">Loading…</p>
        ) : preparations.length === 0 ? (
          <p className="text-slate-600">
            Jobs you’ve started interview practice for will appear here. Start a practice from a job match to see your progress.
          </p>
        ) : (
          <ul className="space-y-3">
            {preparations.map((p) => (
              <li
                key={p.match_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50/50 p-4"
              >
                <div>
                  <p className="font-medium text-slate-800">{p.job_title}</p>
                  <p className="text-sm text-slate-600">{p.company_name}</p>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-slate-500">Readiness</span>
                    <div className="h-2 w-16 overflow-hidden rounded-full bg-slate-200">
                      <div
                        className="h-full rounded-full bg-brand-600 transition-all"
                        style={{ width: `${Math.min(100, p.readiness_score)}%` }}
                      />
                    </div>
                    <span className="font-medium text-slate-700">{Math.round(p.readiness_score)}%</span>
                  </div>
                  <span className="rounded-full bg-brand-100 px-2.5 py-0.5 font-medium text-brand-700">
                    {Math.round(p.compatibility_score)}% match
                  </span>
                  {p.has_prep_kit ? (
                    <>
                      <span className="text-slate-500">
                        {p.sessions_completed}/{p.total_sessions} sessions
                      </span>
                      {p.best_score != null && (
                        <span className="text-slate-600">
                          Best: {p.best_score}/100
                        </span>
                      )}
                      {p.last_practice_at && (
                        <span className="text-slate-500">
                          Last: {new Date(p.last_practice_at).toLocaleDateString()}
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="text-slate-500">No prep yet</span>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => navigate(`/match/${p.match_id}`)}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    View match
                  </button>
                  {p.has_prep_kit && p.prep_kit_id && (
                    <button
                      type="button"
                      onClick={() => navigate(`/prep/${p.prep_kit_id}`)}
                      className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
                    >
                      Prep
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-2 text-lg font-semibold text-slate-800">
          Next steps
        </h2>
        <p className="text-slate-600">
          Complete practice sessions from your job match prep kits to improve
          your readiness score. Review behavioral and technical questions
          before each session.
        </p>
      </section>
    </div>
  );
}
