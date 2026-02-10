import { useQuery } from "react-query";
import { getProfile } from "../services/api";
import type { SkillCompetency } from "../services/api";

const LEVEL_LABELS = ["", "Beginner", "Basic", "Intermediate", "Advanced", "Expert"];

// Simulated market averages for common skills (would be real data in production)
const MARKET_AVERAGES: Record<string, number> = {
  python: 3.2, javascript: 3.1, typescript: 2.9, react: 3.0, "node.js": 2.8,
  sql: 3.0, postgresql: 2.7, aws: 2.6, docker: 2.5, kubernetes: 2.3,
  "machine learning": 2.4, "data analysis": 2.8, java: 3.1, "c++": 2.9,
  go: 2.3, rust: 2.0, redis: 2.4, git: 3.5, "rest apis": 3.2, css: 3.0,
  html: 3.3, "ci/cd": 2.5, terraform: 2.2, pandas: 2.6, pytorch: 2.1,
  "natural language processing": 2.0, mathematics: 2.8,
};

function getMarketAvg(skill: string): number {
  const key = skill.toLowerCase().trim();
  return MARKET_AVERAGES[key] ?? 2.8;
}

export default function PeerComparison() {
  const { data: profile, isLoading } = useQuery("profile", getProfile, { retry: false });
  const competencies: SkillCompetency[] = profile?.skill_competencies ?? [];

  if (isLoading) return <p className="text-slate-500">Loading…</p>;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-800">Peer Comparison</h1>
        <span className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
          In Development
        </span>
      </div>

      {/* Feature description */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-5">
        <h2 className="mb-2 font-semibold text-blue-800">Coming soon</h2>
        <p className="text-sm text-blue-700">
          This page will show how your skills and experience compare to other candidates
          applying for similar roles. Data will be aggregated anonymously from job market
          insights and public salary surveys.
        </p>
        <ul className="mt-3 space-y-1 text-sm text-blue-600">
          <li>&#8226; Percentile ranking for each skill vs. market demand</li>
          <li>&#8226; Salary range estimates based on your profile</li>
          <li>&#8226; Skills gap analysis vs. top candidates</li>
          <li>&#8226; Industry benchmarks and trending skills</li>
        </ul>
      </div>

      {/* Preview: skill comparison with simulated market averages */}
      {competencies.length > 0 ? (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="mb-1 text-lg font-semibold text-slate-800">
            Your skills vs. market average
          </h2>
          <p className="mb-4 text-xs text-slate-400">
            Market averages are estimated. Real peer data coming soon.
          </p>
          <div className="space-y-3">
            {[...competencies]
              .sort((a, b) => b.level - a.level)
              .map((c) => {
                const market = getMarketAvg(c.skill);
                const diff = c.level - market;
                const diffLabel =
                  diff > 0.5 ? "Above average" : diff < -0.5 ? "Below average" : "On par";
                const diffColor =
                  diff > 0.5
                    ? "text-green-600"
                    : diff < -0.5
                    ? "text-red-500"
                    : "text-slate-500";
                return (
                  <div key={c.skill} className="rounded-lg border border-slate-100 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="font-medium text-slate-800">{c.skill}</span>
                      <span className={`text-xs font-medium ${diffColor}`}>{diffLabel}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="w-8 text-right text-xs text-slate-500">You</span>
                      <div className="flex-1">
                        <div className="relative h-4 w-full overflow-hidden rounded-full bg-slate-100">
                          <div
                            className="absolute inset-y-0 left-0 rounded-full bg-brand-500"
                            style={{ width: `${(c.level / 5) * 100}%` }}
                          />
                        </div>
                      </div>
                      <span className="w-20 text-xs text-slate-600">
                        {LEVEL_LABELS[c.level]}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-3">
                      <span className="w-8 text-right text-xs text-slate-400">Avg</span>
                      <div className="flex-1">
                        <div className="relative h-4 w-full overflow-hidden rounded-full bg-slate-100">
                          <div
                            className="absolute inset-y-0 left-0 rounded-full bg-slate-300"
                            style={{ width: `${(market / 5) * 100}%` }}
                          />
                        </div>
                      </div>
                      <span className="w-20 text-xs text-slate-400">
                        {market.toFixed(1)}/5
                      </span>
                    </div>
                  </div>
                );
              })}
          </div>
        </section>
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <p className="text-slate-500">
            Upload a CV first to see how your skills compare to the market.
          </p>
        </div>
      )}

      {/* Placeholder cards for future features */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-center">
          <p className="text-3xl text-slate-300">&#128200;</p>
          <p className="mt-2 text-sm font-medium text-slate-500">Percentile Ranking</p>
          <p className="text-xs text-slate-400">Coming soon</p>
        </div>
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-center">
          <p className="text-3xl text-slate-300">&#128176;</p>
          <p className="mt-2 text-sm font-medium text-slate-500">Salary Insights</p>
          <p className="text-xs text-slate-400">Coming soon</p>
        </div>
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-center">
          <p className="text-3xl text-slate-300">&#128293;</p>
          <p className="mt-2 text-sm font-medium text-slate-500">Trending Skills</p>
          <p className="text-xs text-slate-400">Coming soon</p>
        </div>
      </div>
    </div>
  );
}
