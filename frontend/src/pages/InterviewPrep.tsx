import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "react-query";
import { getPrepKit, startSession, listSessions } from "../services/api";
import type { PrepQuestion } from "../services/api";

const QUESTION_COUNTS = [5, 10, 15, 20] as const;
const QUESTION_TYPES = [
  { id: "behavioral", label: "Behavioral" },
  { id: "technical", label: "Technical" },
  { id: "company", label: "Company-specific" },
] as const;

export default function InterviewPrep() {
  const { prepId } = useParams<{ prepId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [numQuestions, setNumQuestions] = useState(10);
  const [questionTypes, setQuestionTypes] = useState<string[]>([
    "behavioral",
    "technical",
    "company",
  ]);

  const { data: kit, isLoading } = useQuery(
    ["prepKit", prepId],
    () => getPrepKit(prepId!),
    { enabled: !!prepId }
  );

  const { data: sessionsData } = useQuery(
    ["interviewSessions", prepId],
    () => listSessions(prepId!),
    { enabled: !!prepId }
  );

  const [startError, setStartError] = useState<string | null>(null);
  const startMut = useMutation(
    () =>
      startSession(prepId!, {
        num_questions: numQuestions,
        question_types: questionTypes,
      }),
    {
      onSuccess: (data) => {
        setStartError(null);
        queryClient.invalidateQueries({ queryKey: ["interviewSessions", prepId] });
        navigate(`/practice/session/${data.session_id}`);
      },
      onError: (err: { response?: { data?: { detail?: string | string[] } }; message?: string }) => {
        const detail = err.response?.data?.detail;
        const msg =
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.join(", ")
              : err.message || "Failed to start session.";
        setStartError(msg);
      },
    }
  );

  const toggleType = (id: string) => {
    setQuestionTypes((prev) => {
      const next = prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id];
      return next.length > 0 ? next : prev;
    });
  };

  if (!prepId) {
    return <p className="text-slate-500">No prep kit selected.</p>;
  }
  if (isLoading) {
    return <p className="text-slate-500">Loading prep kit…</p>;
  }
  if (!kit) {
    return <p className="text-slate-500">Prep kit not found.</p>;
  }

  const byType = (type: string) =>
    kit.questions.filter((q: PrepQuestion) => q.type === type);
  const behavioral = byType("behavioral");
  const technical = byType("technical");
  const company = byType("company");
  const other = kit.questions.filter(
    (q: PrepQuestion) => !["behavioral", "technical", "company"].includes(q.type)
  );
  const hasTips = Array.isArray(kit.tips) && kit.tips.length >= 1;

  const savedSessions = sessionsData?.sessions ?? [];
  const companyLabel = kit.company_name
    ? ` for ${kit.company_name}${kit.job_title ? ` (${kit.job_title})` : ""}`
    : "";

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-slate-800">
        Interview prep{companyLabel}
      </h1>

      {kit.company_insights && (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="mb-2 text-lg font-semibold text-slate-800">
            Company insights
          </h2>
          <p className="text-slate-700">{kit.company_insights}</p>
        </section>
      )}

      {hasTips ? (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="mb-2 text-lg font-semibold text-slate-800">Tips</h2>
          <ul className="list-inside list-disc space-y-1 text-slate-700">
            {kit.tips!.map((t: string, i: number) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </section>
      ) : null }

      {/* Practice config + start */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-800">
          Start a practice session
        </h2>
        <div className="mb-4 space-y-4">
          <div>
            <p className="mb-2 text-sm font-medium text-slate-700">
              Number of questions
            </p>
            <div className="flex flex-wrap gap-2">
              {QUESTION_COUNTS.map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setNumQuestions(n)}
                  className={`rounded-lg border px-3 py-1.5 text-sm ${
                    numQuestions === n
                      ? "border-brand-600 bg-brand-50 text-brand-700"
                      : "border-slate-300 text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {n}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setNumQuestions(kit.questions.length)}
                className={`rounded-lg border px-3 py-1.5 text-sm ${
                  numQuestions === kit.questions.length
                    ? "border-brand-600 bg-brand-50 text-brand-700"
                    : "border-slate-300 text-slate-600 hover:bg-slate-50"
                }`}
              >
                All ({kit.questions.length})
              </button>
            </div>
          </div>
          <div>
            <p className="mb-2 text-sm font-medium text-slate-700">
              Question types
            </p>
            <div className="flex flex-wrap gap-2">
              {QUESTION_TYPES.map(({ id, label }) => (
                <label
                  key={id}
                  className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/50 px-3 py-2"
                >
                  <input
                    type="checkbox"
                    checked={questionTypes.includes(id)}
                    onChange={() => toggleType(id)}
                    className="rounded border-slate-300 text-brand-600"
                  />
                  <span className="text-sm text-slate-700">{label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            setStartError(null);
            startMut.mutate();
          }}
          disabled={startMut.isLoading || questionTypes.length === 0}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {startMut.isLoading ? "Starting…" : "Start practice session"}
        </button>
        {startError && (
          <p className="mt-2 text-sm text-red-600">{startError}</p>
        )}
      </section>

      {/* Saved practices for this company */}
      {savedSessions.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="mb-3 text-lg font-semibold text-slate-800">
            Saved practices for this company
          </h2>
          <ul className="space-y-2">
            {savedSessions.map((s) => (
              <li
                key={s.session_id}
                className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50/50 p-3"
              >
                <div>
                  <span className="text-sm text-slate-600">
                    {new Date(s.started_at).toLocaleDateString()} — {s.num_questions} questions
                  </span>
                  {s.status === "completed" && s.performance_score != null && (
                    <span className="ml-2 rounded bg-slate-200 px-2 py-0.5 text-xs">
                      Score: {s.performance_score}/100
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => navigate(`/practice/session/${s.session_id}`)}
                  className="text-sm font-medium text-brand-600 hover:underline"
                >
                  View
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800">Question bank</h2>
        </div>

        <div className="space-y-6">
          {behavioral.length > 0 && (
            <div>
              <h3 className="mb-2 font-medium text-slate-700">Behavioral</h3>
              <ul className="space-y-2">
                {behavioral.map((q: PrepQuestion, i: number) => (
                  <li
                    key={i}
                    className="rounded-lg border border-slate-100 bg-slate-50/50 p-3 text-slate-800"
                  >
                    <span className="text-xs text-slate-500 uppercase">
                      {q.difficulty}
                    </span>
                    <p>{q.question}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {technical.length > 0 && (
            <div>
              <h3 className="mb-2 font-medium text-slate-700">Technical</h3>
              <ul className="space-y-2">
                {technical.map((q: PrepQuestion, i: number) => (
                  <li
                    key={i}
                    className="rounded-lg border border-slate-100 bg-slate-50/50 p-3 text-slate-800"
                  >
                    <span className="text-xs text-slate-500 uppercase">
                      {q.difficulty}
                    </span>
                    <p>{q.question}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {company.length > 0 && (
            <div>
              <h3 className="mb-2 font-medium text-slate-700">
                Company-specific
              </h3>
              <ul className="space-y-2">
                {company.map((q: PrepQuestion, i: number) => (
                  <li
                    key={i}
                    className="rounded-lg border border-slate-100 bg-slate-50/50 p-3 text-slate-800"
                  >
                    <p>{q.question}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {other.length > 0 && (
            <div>
              <h3 className="mb-2 font-medium text-slate-700">Other</h3>
              <ul className="space-y-2">
                {other.map((q: PrepQuestion, i: number) => (
                  <li
                    key={i}
                    className="rounded-lg border border-slate-100 bg-slate-50/50 p-3 text-slate-800"
                  >
                    <p>{q.question}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
