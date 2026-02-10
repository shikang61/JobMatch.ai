import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "react-query";
import {
  getJobMatches,
  getJob,
  createPrepKit,
} from "../services/api";
import type { JobMatch } from "../services/api";

export default function JobMatchDetails() {
  const { matchId } = useParams<{ matchId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: matchesData } = useQuery("jobMatches", getJobMatches);
  const match = matchesData?.matches?.find((m: JobMatch) => m.id === matchId);
  const jobId = match?.job_id;

  const { data: job, isLoading: jobLoading } = useQuery(
    ["job", jobId],
    () => getJob(jobId!),
    { enabled: !!jobId }
  );

  const [prepError, setPrepError] = useState("");
  const createPrepMutation = useMutation(
    () => createPrepKit(matchId!),
    {
      onSuccess: (data) => {
        queryClient.invalidateQueries("prepKits");
        navigate(`/prep/${data.id}`);
      },
      onError: (err: { response?: { data?: { detail?: string } } }) => {
        setPrepError(err?.response?.data?.detail ?? "Failed to generate interview prep. Try again.");
      },
    }
  );

  if (!match) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6">
        <p className="text-slate-500">Match not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{match.job_title}</h1>
          <p className="text-slate-600">{match.company_name}</p>
          {match.location && (
            <p className="text-sm text-slate-500">{match.location}</p>
          )}
          {match.job_url && (
            <a
              href={match.job_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-block text-sm text-brand-600 hover:underline"
            >
              View original posting &rarr;
            </a>
          )}
        </div>
        <span className="rounded-full bg-brand-100 px-4 py-2 text-lg font-semibold text-brand-700">
          {Math.round(match.compatibility_score)}% match
        </span>
      </div>

      {/* Compatibility breakdown */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-3 text-lg font-semibold text-slate-800">
          Compatibility breakdown
        </h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {match.match_details?.skill_match_required != null && (
            <div>
              <p className="text-sm text-slate-500">Required skills</p>
              <p className="font-medium text-slate-800">
                {match.match_details.skill_match_required}%
              </p>
            </div>
          )}
          {match.match_details?.skill_match_preferred != null && (
            <div>
              <p className="text-sm text-slate-500">Preferred skills</p>
              <p className="font-medium text-slate-800">
                {match.match_details.skill_match_preferred}%
              </p>
            </div>
          )}
          {match.match_details?.experience_score != null && (
            <div>
              <p className="text-sm text-slate-500">Experience fit</p>
              <p className="font-medium text-slate-800">
                {match.match_details.experience_score}%
              </p>
            </div>
          )}
        </div>
        {match.match_details?.missing_required_skills?.length ? (
          <div className="mt-4">
            <p className="text-sm font-medium text-slate-700">Skill gaps</p>
            <p className="text-slate-600">
              {match.match_details.missing_required_skills.join(", ")}
            </p>
          </div>
        ) : null}
      </section>

      {/* What they look for (summary only; no full description) */}
      {job && (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="mb-3 text-lg font-semibold text-slate-800">
            What they look for
          </h2>
          {job.job_summary ? (
            <div className="space-y-4">
              {job.job_summary.expected_salary && (
                <div>
                  <p className="mb-1 text-sm font-medium text-slate-700">
                    Expected salary
                  </p>
                  <p className="text-slate-600">{job.job_summary.expected_salary}</p>
                </div>
              )}
              {job.job_summary.key_skills?.length > 0 && (
                <div>
                  <p className="mb-1 text-sm font-medium text-slate-700">
                    Key skills & technologies
                  </p>
                  <p className="text-slate-600">
                    {job.job_summary.key_skills.join(", ")}
                  </p>
                </div>
              )}
              {job.job_summary.qualifications?.length > 0 && (
                <div>
                  <p className="mb-1 text-sm font-medium text-slate-700">
                    Qualifications
                  </p>
                  <ul className="list-inside list-disc text-slate-600">
                    {job.job_summary.qualifications.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </div>
              )}
              {job.job_summary.cultural_fit && (
                <div>
                  <p className="mb-1 text-sm font-medium text-slate-700">
                    Culture & fit
                  </p>
                  <p className="text-slate-600">{job.job_summary.cultural_fit}</p>
                </div>
              )}
              {job.job_summary.advantageous_skills?.length > 0 && (
                <div>
                  <p className="mb-1 text-sm font-medium text-slate-700">
                    Advantageous skills
                  </p>
                  <p className="text-slate-600">
                    {job.job_summary.advantageous_skills.join(", ")}
                  </p>
                </div>
              )}
              {job.job_url && (
                <div className="pt-2">
                  <a
                    href={job.job_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-brand-300 bg-brand-50 px-4 py-2 text-sm font-medium text-brand-700 hover:bg-brand-100"
                  >
                    View original job posting &rarr;
                  </a>
                </div>
              )}
            </div>
          ) : jobLoading ? (
            <p className="text-slate-500">Generating summary…</p>
          ) : (
            <p className="text-slate-500">Summary will appear when job details load.</p>
          )}
        </section>
      )}

      <div className="space-y-2">
        <button
          type="button"
          onClick={() => { setPrepError(""); createPrepMutation.mutate(); }}
          disabled={createPrepMutation.isLoading}
          className="rounded-lg bg-brand-600 px-6 py-2.5 font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {createPrepMutation.isLoading
            ? "Generating interview prep…"
            : "Start interview practice"}
        </button>
        {prepError && <p className="text-sm text-red-600">{prepError}</p>}
      </div>
    </div>
  );
}
