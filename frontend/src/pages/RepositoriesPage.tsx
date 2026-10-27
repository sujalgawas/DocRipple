import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Search,
  Plus,
  GitBranch,
  RefreshCw,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { getAuthMe, getDashboard, triggerRepo } from "../services/api";
import type {
  ActivityRun,
  AuthMe,
  DashboardResponse,
} from "../services/api";

const statusStyles: Record<
  ActivityRun["status"],
  { pill: string; dot: string; label: string }
> = {
  running: {
    pill: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400",
    label: "running",
  },
  no_drift: {
    pill: "border-[#26231D] bg-[#1F1D18] text-[#8E897F]",
    dot: "bg-[#8E897F]",
    label: "no drift",
  },
  synced: {
    pill: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
    dot: "bg-emerald-400",
    label: "synced",
  },
  pr_open: {
    pill: "border-accent-orange/30 bg-accent-orange/10 text-accent-orange",
    dot: "bg-accent-orange",
    label: "PR open",
  },
  merged: {
    pill: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
    dot: "bg-emerald-400",
    label: "merged",
  },
  failed: {
    pill: "border-red-500/30 bg-red-500/10 text-red-400",
    dot: "bg-red-400",
    label: "failed",
  },
};

function relativeTime(value?: string | null): string {
  if (!value) return "never";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "just now";

  const seconds = Math.max(1, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return new Date(value).toLocaleDateString();
}

function greeting(username?: string | null): string {
  const hour = new Date().getHours();
  const part = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  return `good ${part}, ${username || "there"}`;
}

export const RepositoriesPage: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [me, setMe] = useState<AuthMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncingRepo, setSyncingRepo] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await getDashboard();
      setDashboard(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load dashboard");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    getAuthMe()
      .then(setMe)
      .catch(() => setMe(null));

    const timer = window.setInterval(() => {
      void load(true);
    }, 8000);
    return () => window.clearInterval(timer);
  }, [load]);

  const repositories = dashboard?.repositories ?? [];
  const stats = dashboard?.stats ?? {
    runs_this_week: 0,
    skipped_zero_tokens: 0,
    prs_merged: 0,
  };
  const latestRuns = dashboard?.latest_runs ?? [];

  const filteredRepos = repositories.filter(
    (repo) =>
      repo.name.toLowerCase().includes(search.toLowerCase()) ||
      repo.owner.toLowerCase().includes(search.toLowerCase())
  );

  const handleSync = async (repoFullName: string) => {
    const [owner, name] = repoFullName.split("/");
    if (!owner || !name) return;

    setSyncingRepo(repoFullName);
    setNotice(null);
    setError(null);
    try {
      const result = await triggerRepo(owner, name);
      setNotice(
        `Queued ${result.commit_sha.slice(0, 7)} on ${repoFullName}. Opening activity...`
      );
      await load(true);
      window.setTimeout(() => navigate("/activity"), 900);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not trigger a run");
    } finally {
      setSyncingRepo(null);
    }
  };

  return (
    <div className="p-8 lg:p-12 max-w-6xl">
      {/* Header Row */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <p className="font-mono text-xs text-[#8E897F] mb-1">
            {greeting(me?.username)}
          </p>
          <h1 className="font-serif text-5xl text-[#F5F2EB] tracking-tight leading-tight">
            Repositories
          </h1>
        </div>

        <Link
          to="/repositories/new"
          className="bg-[#F3EFE6] hover:bg-white text-[#141310] font-medium px-4 py-2 rounded-lg text-sm flex items-center gap-1.5 transition-colors shadow-sm shrink-0"
        >
          <Plus className="w-4 h-4 stroke-[2.5]" />
          <span>New</span>
        </Link>
      </div>

      {error && (
        <div className="mb-6 border border-red-900/50 bg-red-950/20 text-red-300 rounded-xl px-4 py-3 text-sm flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {notice && (
        <div className="mb-6 border border-emerald-900/50 bg-emerald-950/20 text-emerald-300 rounded-xl px-4 py-3 text-sm font-mono">
          {notice}
        </div>
      )}

      {/* 3-Column Metric Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-[#26231D] border border-[#26231D] rounded-xl bg-[#141310] mb-8 overflow-hidden">
        <div className="p-5">
          <p className="font-mono text-xs text-[#8E897F] mb-2">Runs this week</p>
          <p className="font-serif text-4xl text-[#F5F2EB]">
            {stats.runs_this_week}
          </p>
        </div>
        <div className="p-5">
          <p className="font-mono text-xs text-[#8E897F] mb-2">
            Skipped (0 tokens)
          </p>
          <p className="font-serif text-4xl text-[#F5F2EB]">
            {stats.skipped_zero_tokens}
          </p>
        </div>
        <div className="p-5">
          <p className="font-mono text-xs text-[#8E897F] mb-2">PRs merged</p>
          <p className="font-serif text-4xl text-[#F5F2EB]">
            {stats.prs_merged}
          </p>
        </div>
      </div>

      {/* Filter Input */}
      <div className="relative mb-6">
        <Search className="w-4 h-4 text-muted absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none" />
        <input
          type="text"
          placeholder="Filter repositories..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-[#141310] border border-[#26231D] focus:border-accent-orange rounded-xl pl-11 pr-4 py-2.5 text-sm text-primary placeholder:text-[#8E897F]/60 outline-none font-mono transition-colors"
        />
      </div>

      {/* 2-Column Repository Cards Grid */}
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-[#8E897F] font-mono mb-14">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading monitored repositories...</span>
        </div>
      ) : filteredRepos.length === 0 ? (
        <div className="border border-dashed border-[#26231D] rounded-xl p-8 mb-14 text-center">
          <p className="text-sm text-[#8E897F] mb-3">
            {repositories.length === 0
              ? "No repositories are connected yet."
              : "No repositories match your filter."}
          </p>
          {repositories.length === 0 && (
            <Link
              to="/repositories/new"
              className="inline-flex items-center gap-1.5 bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-4 py-2 rounded-lg text-sm transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span>Add your first repository</span>
            </Link>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-14">
          {filteredRepos.map((repo) => (
            <div
              key={repo.repo_full_name}
              onClick={() =>
                navigate(`/repositories/${repo.owner}/${repo.name}`)
              }
              className="border border-[#26231D] bg-[#141310] hover:border-[#3A352C] rounded-xl p-5 cursor-pointer transition-all flex flex-col justify-between gap-4 group"
            >
              {/* Top row */}
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-xs text-[#8E897F] mb-1">
                    {repo.owner} /
                  </p>
                  <h2 className="text-xl font-bold text-[#F5F2EB] group-hover:text-accent-orange transition-colors">
                    {repo.name}
                  </h2>
                </div>

                {/* Status pill */}
                <div className="flex items-center gap-1.5 font-mono text-xs">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      repo.status === "listening"
                        ? "bg-emerald-400"
                        : "bg-[#8E897F]"
                    }`}
                  />
                  <span
                    className={
                      repo.status === "listening"
                        ? "text-emerald-400"
                        : "text-[#8E897F]"
                    }
                  >
                    {repo.status}
                  </span>
                </div>
              </div>

              {/* Tracked docs badges */}
              <div className="flex flex-wrap items-center gap-2">
                {repo.doc_paths.map((doc) => (
                  <span
                    key={doc}
                    className="bg-[#1F1D18] text-[#F5F2EB] border border-[#26231D] px-2 py-0.5 rounded text-xs font-mono"
                  >
                    {doc}
                  </span>
                ))}
              </div>

              {/* Footer row */}
              <div className="flex items-center justify-between gap-3 text-xs font-mono text-[#8E897F] pt-2 border-t border-[#26231D]/60">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="flex items-center gap-1 text-[#F5F2EB]">
                    <GitBranch className="w-3.5 h-3.5 text-[#8E897F]" />
                    <span>{repo.watch_branch}</span>
                  </span>
                  <span>{repo.language || "unknown"}</span>
                  <span>{repo.run_count ?? 0} runs</span>
                  <span>{relativeTime(repo.last_pushed_at)}</span>
                </div>

                <button
                  type="button"
                  disabled={syncingRepo === repo.repo_full_name}
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleSync(repo.repo_full_name);
                  }}
                  className="shrink-0 flex items-center gap-1.5 border border-[#3A352C] bg-[#1F1D18] hover:bg-[#2A2720] hover:border-accent-orange/60 text-[#F5F2EB] px-2.5 py-1.5 rounded-lg transition-colors disabled:opacity-60"
                  title={`Trigger the pipeline for the latest commit on ${repo.repo_full_name}`}
                >
                  {syncingRepo === repo.repo_full_name ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3.5 h-3.5" />
                  )}
                  <span>Sync latest commit</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Latest Runs Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-serif text-3xl text-[#F5F2EB] tracking-tight">
            Latest runs
          </h2>
          <Link
            to="/activity"
            className="font-mono text-xs text-[#8E897F] hover:text-[#F5F2EB] transition-colors"
          >
            view all →
          </Link>
        </div>

        {latestRuns.length === 0 ? (
          <div className="border border-dashed border-[#26231D] rounded-xl p-6 text-sm text-[#8E897F] font-mono">
            No runs yet. Hit{" "}
            <span className="text-[#F5F2EB]">Sync latest commit</span> to watch
            the agent work.
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {latestRuns.map((run) => {
              const style = statusStyles[run.status];
              const [owner, repo] = run.repo_full_name.split("/");
              const title =
                run.commit_message.split("\n")[0] || "Untitled commit";
              return (
                <div
                  key={run.delivery_id}
                  onClick={() =>
                    owner && repo
                      ? navigate(`/repositories/${owner}/${repo}`)
                      : navigate("/activity")
                  }
                  className="border border-[#26231D] bg-[#141310] hover:border-[#38332A] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-colors cursor-pointer group"
                >
                  {/* Left: Pill & Title */}
                  <div className="flex items-center gap-3.5 min-w-0">
                    <div
                      className={`border rounded-full px-2.5 py-0.5 text-xs font-mono flex items-center gap-1.5 shrink-0 ${style.pill}`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${style.dot}`}
                      />
                      <span>{style.label}</span>
                    </div>

                    <div className="min-w-0">
                      <p className="text-sm font-medium text-[#F5F2EB] group-hover:text-accent-orange transition-colors truncate">
                        {title}
                      </p>
                      <p className="font-mono text-xs text-[#8E897F] mt-0.5">
                        {repo || run.repo_full_name} ·{" "}
                        <span className="text-[#F5F2EB]">
                          {(run.commit_sha || "").slice(0, 7)}
                        </span>{" "}
                        · {run.author}
                      </p>
                    </div>
                  </div>

                  {/* Right: LLM calls & Time */}
                  <div className="text-right font-mono text-xs text-[#8E897F] shrink-0">
                    <p className="text-[#F5F2EB]">
                      {run.llm_calls} llm call
                      {run.llm_calls === 1 ? "" : "s"}
                    </p>
                    <p className="text-[#8E897F] mt-0.5">
                      {relativeTime(run.created_at)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
