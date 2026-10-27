import React, { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import {
  GitBranch,
  Play,
  FileCode,
  Network,
  History,
  GitPullRequest,
  Copy,
  Check,
  Search,
  ExternalLink,
  Loader2,
  RefreshCw,
  AlertCircle,
  GitCommit,
  CheckCircle2,
} from "lucide-react";
import {
  getRepoSkill,
  getRepoMemory,
  getActivity,
  getDashboard,
  getRepoHistory,
  triggerRepo,
  executeDemoRun,
} from "../services/api";
import type {
  DocStyleSkill,
  RepoMemoryMap,
  ActivityRun,
  MonitoredRepo,
  DemoRunResponse,
  RepoHistoryResponse,
  RepoHistoryItem,
} from "../services/api";

const STATUS_META: Record<
  string,
  { label: string; pill: string; dot: string }
> = {
  running: {
    label: "running",
    pill: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400 animate-pulse",
  },
  no_drift: {
    label: "no drift",
    pill: "border-[#26231D] bg-[#1F1D18] text-[#8E897F]",
    dot: "bg-[#8E897F]",
  },
  synced: {
    label: "synced",
    pill: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
    dot: "bg-emerald-400",
  },
  pr_open: {
    label: "PR open",
    pill: "border-accent-orange/40 bg-accent-orange/10 text-accent-orange",
    dot: "bg-accent-orange",
  },
  merged: {
    label: "merged",
    pill: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
    dot: "bg-emerald-400",
  },
  failed: {
    label: "failed",
    pill: "border-red-500/40 bg-red-500/10 text-red-300",
    dot: "bg-red-400",
  },
};

function formatRelativeTime(value?: string): string {
  if (!value) return "just now";
  const delta = Date.now() - new Date(value).getTime();
  if (Number.isNaN(delta)) return "recently";
  const seconds = Math.max(1, Math.floor(delta / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(value).toLocaleDateString();
}

export const RepoDetailPage: React.FC = () => {
  const { owner = "sujalgawas", repo = "DocRipple" } = useParams();
  const repoFullName = `${owner}/${repo}`;

  const [activeTab, setActiveTab] = useState<"overview" | "skill" | "memory">("overview");

  // Overview: real GitHub history + pipeline runs + repository metadata
  const [runs, setRuns] = useState<ActivityRun[]>([]);
  const [repoHistory, setRepoHistory] = useState<RepoHistoryResponse | null>(null);
  const [monitoredRepo, setMonitoredRepo] = useState<MonitoredRepo | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [errorNotice, setErrorNotice] = useState<string | null>(null);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  // Tab 2: Skill data
  const [skill, setSkill] = useState<DocStyleSkill | null>(null);
  const [loadingSkill, setLoadingSkill] = useState(false);
  const [copiedSkill, setCopiedSkill] = useState(false);

  // Tab 3: Memory map data
  const [memory, setMemory] = useState<RepoMemoryMap | null>(null);
  const [loadingMemory, setLoadingMemory] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState("");

  // Modal: Simulate Drift Run
  const [showSimulateModal, setShowSimulateModal] = useState(false);
  const [simDiff, setSimDiff] = useState(
    `--- a/src/billing.py\n+++ b/src/billing.py\n@@ -1,2 +1,3 @@\n-def calc_total(items: list[int]) -> int:\n-    return sum(items)\n+def calc_total(items: list[int], tax_rate: float = 0.05) -> int:\n+    return int(sum(items) * (1 + tax_rate))\n`
  );
  const [simDoc, setSimDoc] = useState(
    `## Billing\n\n<!-- doc-anchor: billing -->\n\nCalculates invoice total:\n\n\`\`\`python\nfrom src.billing import calc_total\ntotal = calc_total([10, 20])\n\`\`\`\n`
  );
  const [simLoading, setSimLoading] = useState(false);
  const [simResult, setSimResult] = useState<DemoRunResponse | null>(null);
  const [simError, setSimError] = useState<string | null>(null);

  // Load Overview Data from real GitHub API & DocRipple Backend
  const loadData = useCallback(
    async (silent = false) => {
      if (!silent) setLoadingData(true);

      const [historyResult, activityResult, dashboardResult] =
        await Promise.allSettled([
          getRepoHistory(owner, repo),
          getActivity(repoFullName),
          getDashboard(),
        ]);

      if (historyResult.status === "fulfilled") {
        setRepoHistory(historyResult.value);
      }

      if (activityResult.status === "fulfilled") {
        setRuns(activityResult.value.runs);
        setErrorNotice(null);
      } else if (historyResult.status === "rejected") {
        setErrorNotice(
          historyResult.reason instanceof Error
            ? historyResult.reason.message
            : "Could not load repository history"
        );
      }

      if (dashboardResult.status === "fulfilled") {
        setMonitoredRepo(
          dashboardResult.value.repositories.find(
            (item) => item.repo_full_name === repoFullName
          ) ?? null
        );
      }

      if (!silent) setLoadingData(false);
    },
    [owner, repo, repoFullName]
  );

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const hasRunning = runs.some((run) => run.status === "running");

  // Auto-refresh when a run is active
  useEffect(() => {
    const timer = window.setInterval(
      () => {
        void loadData(true);
      },
      hasRunning ? 3500 : 20000
    );
    return () => window.clearInterval(timer);
  }, [hasRunning, loadData]);

  // Load Tab 2 data
  useEffect(() => {
    if (activeTab === "skill" && !skill) {
      setLoadingSkill(true);
      getRepoSkill(owner, repo)
        .then(setSkill)
        .finally(() => setLoadingSkill(false));
    }
  }, [activeTab, owner, repo, skill]);

  // Load Tab 3 data
  useEffect(() => {
    if (activeTab === "memory") {
      setLoadingMemory(true);
      getRepoMemory(owner, repo, symbolFilter)
        .then(setMemory)
        .finally(() => setLoadingMemory(false));
    }
  }, [activeTab, owner, repo, symbolFilter]);

  const handleCopySkill = () => {
    if (skill) {
      navigator.clipboard.writeText(skill.skill_markdown);
      setCopiedSkill(true);
      setTimeout(() => setCopiedSkill(false), 2000);
    }
  };

function isSameCommit(shaA?: string | null, shaB?: string | null): boolean {
  if (!shaA || !shaB) return false;
  const a = shaA.trim().toLowerCase();
  const b = shaB.trim().toLowerCase();
  return a === b || a.startsWith(b) || b.startsWith(a);
}

function getItemSha(
  item: ActivityRun | RepoHistoryItem | null | undefined
): string {
  if (!item) return "";
  if ("commit_sha" in item && typeof item.commit_sha === "string") {
    return item.commit_sha;
  }
  if ("sha" in item && typeof item.sha === "string") {
    return item.sha;
  }
  return "";
}

function getItemStatus(
  item: ActivityRun | RepoHistoryItem | null | undefined
): string {
  if (!item) return "";
  return String(item.status || "");
}

// ── Sync / Trigger Handler with edge case checks ───────────────────────────
  const handleSyncLatest = async (targetCommitSha?: string) => {
    setErrorNotice(null);
    setSyncNotice(null);

    // Commit to sync: either explicit target or latest commit from GitHub API
    const latestGitHubSha =
      repoHistory?.latest_commit_sha ||
      (repoHistory?.commits?.[0]?.sha ?? "").slice(0, 7);
    const shaToSync = (
      targetCommitSha ? targetCommitSha.slice(0, 7) : latestGitHubSha
    ).trim();

    // Latest run in execution history (check runs first, then history list)
    const latestRunInHistory =
      runs[0] ||
      repoHistory?.history?.find(
        (h) => h.has_pipeline_run || h.type === "run"
      ) ||
      null;

    const currentLatestRunSha = (
      getItemSha(latestRunInHistory) ||
      repoHistory?.latest_run_sha ||
      ""
    ).slice(0, 7);

    const currentLatestRunStatus =
      getItemStatus(latestRunInHistory) || repoHistory?.latest_run_status || "";

    // ── Apply IF / ELSE checks to prevent redundant/duplicate syncing ──
    if (
      shaToSync &&
      currentLatestRunSha &&
      isSameCommit(shaToSync, currentLatestRunSha)
    ) {
      // IF: The commit being checked is the same as the latest run commit in history
      if (
        currentLatestRunStatus === "running" ||
        syncing ||
        runs.some((r) => r.status === "running") ||
        Boolean(repoHistory?.is_latest_running)
      ) {
        // Sub-case 1: The same latest commit is currently syncing / running
        setSyncNotice(
          `Commit ${shaToSync} is currently syncing. Please wait for the current analysis to finish.`
        );
        return;
      } else if (
        currentLatestRunStatus === "no_drift" ||
        currentLatestRunStatus === "synced"
      ) {
        // Sub-case 2: The same latest commit has already been synced with no documentation drift
        setSyncNotice(
          `Commit ${shaToSync} has already been synced with no documentation drift. Your docs are already up to date!`
        );
        return;
      } else if (
        currentLatestRunStatus === "pr_open" ||
        currentLatestRunStatus === "merged"
      ) {
        // Sub-case 3: The same latest commit already produced a PR
        setSyncNotice(
          `Commit ${shaToSync} has already been analyzed and a documentation PR is already ${
            currentLatestRunStatus === "pr_open" ? "open" : "merged"
          }.`
        );
        return;
      }
      // Sub-case 4: Previous run failed; allow retry by proceeding to sync
    } else {
      // ELSE: It's a new or different commit from the latest run in history
      const anyRunning =
        syncing ||
        runs.some((r) => r.status === "running") ||
        Boolean(repoHistory?.is_latest_running);

      if (anyRunning) {
        setSyncNotice(
          `A drift analysis is currently running. Please wait for it to complete before syncing commit ${shaToSync || "latest"}.`
        );
        return;
      }
    }

    // Proceed to sync / trigger the commit
    setSyncing(true);
    try {
      const result = await triggerRepo(owner, repo, shaToSync || undefined, {
        checkDuplicate: true,
      });

      if (result.status === "already_running") {
        setSyncNotice(
          result.message ||
            `Commit ${shaToSync} is currently syncing. Please wait for it to finish.`
        );
      } else if (result.status === "already_synced") {
        setSyncNotice(
          result.message ||
            `Commit ${shaToSync} has already been synced with no further drift detected.`
        );
      } else {
        setSyncNotice(
          `Queued ${result.commit_sha.slice(0, 7)} on ${result.branch}. Drift analysis is now running.`
        );
      }

      window.setTimeout(() => {
        void loadData(true);
      }, 1500);
    } catch (err) {
      setErrorNotice(
        err instanceof Error ? err.message : "Could not sync commit"
      );
    } finally {
      setSyncing(false);
    }
  };

  const handleRunSimulation = async () => {
    setSimLoading(true);
    setSimResult(null);
    setSimError(null);
    try {
      const res = await executeDemoRun({
        delivery_id: `sim-${Date.now().toString(36)}`,
        repo_full_name: repoFullName,
        raw_diff: simDiff,
        docs: { "README.md": simDoc },
      });
      setSimResult(res);
    } catch (err) {
      setSimError(
        err instanceof Error ? err.message : "Simulation request failed"
      );
    } finally {
      setSimLoading(false);
    }
  };

  // Metric computation from real GitHub API + DocRipple context store
  const totalCommitsCount =
    repoHistory?.stats?.total_commits ?? repoHistory?.commits?.length ?? 0;
  const totalRunsCount =
    repoHistory?.stats?.total_runs ??
    runs.filter((r) => !r.delivery_id.startsWith("gh-") && !r.delivery_id.startsWith("seed-")).length;
  const totalPrsCount =
    repoHistory?.stats?.pull_requests_count ??
    repoHistory?.pull_requests?.length ??
    runs.filter((r) => r.pr_number !== null && !r.delivery_id.startsWith("seed-")).length;
  const watchBranch =
    repoHistory?.watch_branch || monitoredRepo?.watch_branch || "main";
  const isListening = monitoredRepo?.status === "listening";
  const repoStatusLabel = monitoredRepo ? monitoredRepo.status : "listening";

  // Check state for the top sync button
  const latestGitHubSha =
    repoHistory?.latest_commit_sha ||
    (repoHistory?.commits?.[0]?.sha ?? "").slice(0, 7);

  const latestRun =
    runs[0] ||
    repoHistory?.history?.find(
      (h) => h.has_pipeline_run || h.type === "run"
    ) ||
    null;

  const latestRunSha = (
    getItemSha(latestRun) ||
    repoHistory?.latest_run_sha ||
    ""
  ).slice(0, 7);

  const latestRunStatus =
    getItemStatus(latestRun) || repoHistory?.latest_run_status || "";

  const isSameAsLatestRun = Boolean(
    latestGitHubSha &&
      latestRunSha &&
      isSameCommit(latestGitHubSha, latestRunSha)
  );

  const isCurrentlySyncing = Boolean(
    syncing ||
      hasRunning ||
      repoHistory?.is_latest_running ||
      (isSameAsLatestRun && latestRunStatus === "running") ||
      repoHistory?.history?.some((h) => h.status === "running")
  );

  const isUpToDate = Boolean(
    isSameAsLatestRun &&
      !isCurrentlySyncing &&
      (latestRunStatus === "no_drift" ||
        latestRunStatus === "synced" ||
        latestRunStatus === "pr_open" ||
        latestRunStatus === "merged" ||
        repoHistory?.is_latest_synced)
  );

  // History list from GitHub API & pipeline
  const displayHistory: RepoHistoryItem[] =
    repoHistory?.history && repoHistory.history.length > 0
      ? repoHistory.history
      : runs.map((run) => ({
          id: `run-${run.delivery_id}`,
          type: "run",
          sha: (run.commit_sha || "").slice(0, 7) || "—",
          full_sha: run.commit_sha,
          title:
            (run.commit_message || "").split("\n")[0].trim() ||
            `Docs sync at ${(run.commit_sha || "unknown").slice(0, 7)}`,
          message: run.commit_message || "",
          author: run.author || owner,
          avatar_url: "",
          date: run.created_at,
          html_url: run.commit_sha
            ? `https://github.com/${repoFullName}/commit/${run.commit_sha}`
            : undefined,
          status: run.status,
          status_label:
            run.status === "no_drift"
              ? "no drift"
              : run.status.replace("_", " "),
          doc:
            run.diff_preview?.file_path ||
            (run.status === "no_drift"
              ? "No doc sections impacted (0 LLM tokens)"
              : "No doc drift"),
          pr_number: run.pr_number,
          pr_url: run.pr_url,
          has_pipeline_run: true,
        }));

  return (
    <div className="p-8 lg:p-12 max-w-6xl">
      {/* Back to Repositories */}
      <Link
        to="/repositories"
        className="font-mono text-xs text-[#8E897F] hover:text-[#F5F2EB] inline-flex items-center gap-1 mb-4 transition-colors"
      >
        <span>←</span>
        <span>repositories</span>
      </Link>

      {/* Top Header Card */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8 pb-8 border-b border-[#26231D]">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className="font-mono text-xs text-[#8E897F]">{owner} /</span>
            <span className="font-mono text-xs px-2 py-0.5 rounded border border-[#26231D] bg-[#141310] text-[#8E897F] flex items-center gap-1">
              <GitBranch className="w-3 h-3" />
              {watchBranch}
            </span>
            <span
              className={`font-mono text-xs px-2 py-0.5 rounded border flex items-center gap-1 ${
                isListening
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              {repoStatusLabel}
            </span>
          </div>

          <h1 className="font-serif text-4xl lg:text-5xl text-[#F5F2EB] tracking-tight">
            {repo}
          </h1>
        </div>

        {/* Primary Action Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Sync Latest Commit Button with Edge-Case Protection */}
          {isCurrentlySyncing ? (
            <button
              type="button"
              disabled
              className="border border-[#26231D] bg-[#1F1D18] text-[#8E897F] font-medium px-4 py-2.5 rounded-lg text-sm flex items-center gap-2 cursor-not-allowed font-sans"
            >
              <Loader2 className="w-4 h-4 animate-spin text-accent-orange" />
              <span>
                Syncing {latestGitHubSha ? `(${latestGitHubSha})` : ""}...
              </span>
            </button>
          ) : isUpToDate ? (
            <button
              type="button"
              onClick={() => void handleSyncLatest()}
              className="border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 font-medium px-4 py-2.5 rounded-lg text-sm flex items-center gap-2 transition-colors font-sans shadow-sm"
              title="Latest commit has already been analyzed and verified up to date."
            >
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>Up to date ({latestGitHubSha})</span>
            </button>
          ) : (
            <button
              type="button"
              disabled={syncing}
              onClick={() => void handleSyncLatest()}
              className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-4 py-2.5 rounded-lg text-sm flex items-center gap-2 transition-colors shadow-sm font-sans active:scale-[0.99]"
            >
              <RefreshCw className="w-4 h-4" />
              <span>
                Sync latest commit{" "}
                {latestGitHubSha ? `(${latestGitHubSha})` : ""}
              </span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setShowSimulateModal(true)}
            className="border border-[#3A352C] bg-[#1F1D18] hover:bg-[#2A2720] hover:border-accent-orange/60 text-[#F5F2EB] font-medium px-4 py-2.5 rounded-lg text-sm flex items-center gap-2 transition-colors font-sans"
          >
            <Play className="w-4 h-4 fill-current stroke-none" />
            <span>Simulate Drift Run</span>
          </button>
        </div>
      </div>

      {/* Sync / Edge-case notification toast */}
      {syncNotice && (
        <div className="mb-6 border border-emerald-900/50 bg-emerald-950/25 text-emerald-300 rounded-xl px-4 py-3 text-sm flex items-start justify-between gap-3 shadow-md animate-fadeIn">
          <div className="flex items-start gap-2.5">
            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-emerald-400" />
            <span>{syncNotice}</span>
          </div>
          <button
            type="button"
            onClick={() => setSyncNotice(null)}
            className="font-mono text-xs opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      )}

      {/* Error alert banner */}
      {errorNotice && (
        <div className="mb-6 border border-red-900/50 bg-red-950/20 text-red-300 rounded-xl px-4 py-3 text-sm flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{errorNotice}</span>
          </div>
          <button
            type="button"
            onClick={() => void loadData()}
            className="font-mono text-xs underline hover:text-[#F5F2EB] shrink-0"
          >
            retry
          </button>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-[#26231D] mb-8 font-mono text-xs">
        <button
          type="button"
          onClick={() => setActiveTab("overview")}
          className={`px-4 py-2.5 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === "overview"
              ? "border-accent-orange text-accent-orange"
              : "border-transparent text-[#8E897F] hover:text-[#F5F2EB]"
          }`}
        >
          <History className="w-3.5 h-3.5" />
          <span>Overview &amp; Real GitHub History</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("skill")}
          className={`px-4 py-2.5 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === "skill"
              ? "border-accent-orange text-accent-orange"
              : "border-transparent text-[#8E897F] hover:text-[#F5F2EB]"
          }`}
        >
          <FileCode className="w-3.5 h-3.5" />
          <span>Writing Style Skill (SKILL.md)</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("memory")}
          className={`px-4 py-2.5 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === "memory"
              ? "border-accent-orange text-accent-orange"
              : "border-transparent text-[#8E897F] hover:text-[#F5F2EB]"
          }`}
        >
          <Network className="w-3.5 h-3.5" />
          <span>Repo Memory Map (Graph)</span>
        </button>
      </div>

      {/* ── TAB 1: OVERVIEW & RUNS ────────────────────────────────────────── */}
      {activeTab === "overview" && (
        <div className="flex flex-col gap-8">
          {/* Real Metrics Strip backed by GitHub API & SQLite */}
          <div className="grid grid-cols-1 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-[#26231D] border border-[#26231D] rounded-xl bg-[#141310] overflow-hidden">
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">
                GitHub Commits
              </span>
              <span className="font-serif text-3xl text-[#F5F2EB]">
                {loadingData && !repoHistory ? "…" : totalCommitsCount}
              </span>
            </div>
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">
                Pipeline Runs
              </span>
              <span className="font-serif text-3xl text-[#F5F2EB]">
                {totalRunsCount}
              </span>
            </div>
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">
                Documentation PRs
              </span>
              <span className="font-serif text-3xl text-[#F5F2EB]">
                {totalPrsCount}
              </span>
            </div>
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">
                Watch Branch
              </span>
              <span className="font-serif text-3xl text-emerald-400">
                {watchBranch}
              </span>
            </div>
          </div>

          {/* Real Execution History from GitHub API */}
          <div>
            <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
              <div>
                <h2 className="font-serif text-2xl text-[#F5F2EB]">
                  Execution History
                </h2>
                <p className="font-mono text-xs text-[#8E897F] mt-1">
                  Live commits and AST drift analysis for {repoFullName}
                  {hasRunning ? " · live polling" : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void loadData()}
                className="border border-[#26231D] bg-[#1F1D18] hover:bg-[#2A2720] text-[#F5F2EB] px-3 py-1.5 rounded-lg text-xs font-mono flex items-center gap-1.5 transition-colors"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 ${loadingData ? "animate-spin" : ""}`}
                />
                <span>Refresh GitHub</span>
              </button>
            </div>

            {loadingData && displayHistory.length === 0 ? (
              <div className="border border-[#26231D] bg-[#141310] rounded-xl p-8 flex items-center justify-center gap-2 text-xs font-mono text-[#8E897F]">
                <Loader2 className="w-4 h-4 animate-spin text-accent-orange" />
                <span>Fetching real commits from GitHub API...</span>
              </div>
            ) : displayHistory.length === 0 ? (
              <div className="border border-dashed border-[#26231D] rounded-xl p-8 text-center">
                <GitCommit className="w-8 h-8 mx-auto text-[#8E897F] mb-3 opacity-60" />
                <p className="text-sm text-[#8E897F] mb-1">
                  No commits found on {watchBranch}.
                </p>
                <p className="font-mono text-xs text-[#8E897F]/70 mb-4">
                  Push a commit to GitHub to see it appear here.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {displayHistory.map((item) => {
                  const statusInfo =
                    STATUS_META[item.status] || STATUS_META.synced;
                  const shortSha = item.sha || "—";
                  const isItemRunning =
                    item.status === "running" ||
                    (syncing && shortSha === latestGitHubSha);

                  return (
                    <div
                      key={item.id}
                      className="border border-[#26231D] bg-[#141310] hover:border-[#3A352C] rounded-xl p-5 flex flex-col gap-3 transition-colors"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div className="flex items-start sm:items-center gap-3 min-w-0">
                          {/* Status Pill */}
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-xs font-mono border flex items-center gap-1.5 shrink-0 ${statusInfo.pill}`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${statusInfo.dot}`}
                            />
                            {item.status_label}
                          </span>

                          {/* Commit / Run Title */}
                          <span className="text-sm font-medium text-[#F5F2EB] truncate">
                            {item.title}
                          </span>
                        </div>

                        {/* Author & Timestamp */}
                        <div className="flex items-center gap-2 font-mono text-xs text-[#8E897F] shrink-0">
                          {item.avatar_url ? (
                            <img
                              src={item.avatar_url}
                              alt={item.author}
                              className="w-4 h-4 rounded-full border border-[#26231D]"
                            />
                          ) : null}
                          <span>@{item.author}</span>
                          <span>·</span>
                          <span>{formatRelativeTime(item.date)}</span>
                        </div>
                      </div>

                      {/* Bottom row: AST / Doc impact + Actions */}
                      <div className="flex flex-wrap items-center justify-between gap-4 text-xs font-mono pt-2 border-t border-[#26231D]/60 text-[#8E897F]">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[#8E897F]/70">Target:</span>
                          <span className="text-accent-orange font-medium">
                            {item.doc}
                          </span>
                        </div>

                        <div className="flex items-center gap-3">
                          {/* GitHub Commit Link */}
                          {item.html_url && (
                            <a
                              href={item.html_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-[#8E897F] hover:text-[#F5F2EB] transition-colors"
                              title={`View commit ${item.full_sha || item.sha} on GitHub`}
                            >
                              <GitCommit className="w-3.5 h-3.5" />
                              <span>{shortSha}</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}

                          {/* Documentation PR Link */}
                          {item.pr_number && item.pr_url && (
                            <a
                              href={item.pr_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1.5 text-accent-orange hover:text-accent-orange-hover font-semibold"
                            >
                              <GitPullRequest className="w-3.5 h-3.5" />
                              <span>Docs PR #{item.pr_number}</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}

                          {/* Per-Commit Sync/Rerun Action Button */}
                          {isItemRunning ? (
                            <span className="text-amber-400 font-mono text-xs flex items-center gap-1">
                              <Loader2 className="w-3 h-3 animate-spin" />
                              syncing...
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => void handleSyncLatest(shortSha)}
                              className="text-xs px-2.5 py-1 rounded border border-[#26231D] hover:border-accent-orange/50 hover:text-[#F5F2EB] bg-[#0D0C0A] transition-colors inline-flex items-center gap-1 active:scale-[0.98]"
                              title={`Run documentation drift check on commit ${shortSha}`}
                            >
                              <RefreshCw className="w-3 h-3 text-[#8E897F]" />
                              <span>Check drift</span>
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── TAB 2: WRITING STYLE SKILL (SKILL.MD) ─────────────────────────── */}
      {activeTab === "skill" && (
        <div className="flex flex-col gap-6">
          <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6">
            <h2 className="font-serif text-2xl text-[#F5F2EB] mb-2">
              Stage 0 Writing Style Extraction
            </h2>
            <p className="text-xs text-[#8E897F] font-mono leading-relaxed">
              Mined from existing Markdown documents in{" "}
              <code className="text-accent-orange">{repoFullName}</code>. This
              skill is injected verbatim into LangGraph Writer &amp; Reviewer
              prompts to prevent hallucinated rewrites and maintain tone
              consistency.
            </p>
          </div>

          {loadingSkill ? (
            <div className="p-12 flex items-center justify-center font-mono text-xs text-[#8E897F] gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-accent-orange" />
              <span>Loading repository style skill...</span>
            </div>
          ) : skill ? (
            <div className="flex flex-col gap-6">
              {/* Rules Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="border border-[#26231D] bg-[#141310] rounded-xl p-5 flex flex-col gap-2">
                  <span className="font-mono text-xs text-accent-orange font-semibold uppercase tracking-wider">
                    Tone &amp; Voice
                  </span>
                  <p className="text-xs text-[#F5F2EB] leading-relaxed font-sans">
                    {skill.tone_and_voice}
                  </p>
                </div>

                <div className="border border-[#26231D] bg-[#141310] rounded-xl p-5 flex flex-col gap-2">
                  <span className="font-mono text-xs text-accent-orange font-semibold uppercase tracking-wider">
                    Heading Conventions
                  </span>
                  <ul className="text-xs text-[#8E897F] flex flex-col gap-1.5 font-mono list-disc list-inside">
                    {skill.heading_conventions.map((h, i) => (
                      <li key={i} className="text-[#F5F2EB]">
                        {h}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="border border-[#26231D] bg-[#141310] rounded-xl p-5 flex flex-col gap-2">
                  <span className="font-mono text-xs text-accent-orange font-semibold uppercase tracking-wider">
                    Code Block Rules
                  </span>
                  <ul className="text-xs text-[#8E897F] flex flex-col gap-1.5 font-mono list-disc list-inside">
                    {skill.code_block_rules.map((c, i) => (
                      <li key={i} className="text-[#F5F2EB]">
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Raw Injected SKILL.md */}
              <div className="border border-[#26231D] bg-[#141310] rounded-xl overflow-hidden">
                <div className="px-5 py-3 border-b border-[#26231D] flex items-center justify-between bg-[#0D0C0A]">
                  <span className="font-mono text-xs text-[#8E897F] flex items-center gap-2">
                    <FileCode className="w-3.5 h-3.5 text-accent-orange" />
                    <span>Injected SKILL.md Prompt Template</span>
                  </span>
                  <button
                    type="button"
                    onClick={handleCopySkill}
                    className="inline-flex items-center gap-1.5 font-mono text-xs text-accent-orange hover:text-accent-orange-hover"
                  >
                    {copiedSkill ? (
                      <Check className="w-3.5 h-3.5" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                    <span>{copiedSkill ? "Copied" : "Copy SKILL.md"}</span>
                  </button>
                </div>
                <pre className="p-5 font-mono text-xs text-[#F5F2EB] overflow-x-auto whitespace-pre-wrap leading-relaxed bg-[#0D0C0A]/70">
                  {skill.skill_markdown}
                </pre>
              </div>
            </div>
          ) : null}
        </div>
      )}

      {/* ── TAB 3: REPO MEMORY MAP (GRAPH) ─────────────────────────────────── */}
      {activeTab === "memory" && (
        <div className="flex flex-col gap-6">
          <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h2 className="font-serif text-2xl text-[#F5F2EB] mb-1">
                Stage 0 Repository Memory Graph
              </h2>
              <p className="text-xs text-[#8E897F] font-mono">
                2-hop node traversal mapping:{" "}
                <span className="text-indigo-400">Module</span> →{" "}
                <span className="text-sky-400">File</span> →{" "}
                <span className="text-accent-orange">Symbol</span> →{" "}
                <span className="text-emerald-400">DocSection</span>.
              </p>
            </div>

            {/* Symbol Filter Input */}
            <div className="relative max-w-xs w-full">
              <Search className="w-3.5 h-3.5 text-[#8E897F] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                placeholder="Filter by symbol..."
                value={symbolFilter}
                onChange={(e) => setSymbolFilter(e.target.value)}
                className="w-full bg-[#0D0C0A] border border-[#26231D] focus:border-accent-orange rounded-lg pl-9 pr-3 py-1.5 text-xs text-[#F5F2EB] font-mono outline-none"
              />
            </div>
          </div>

          {loadingMemory ? (
            <div className="p-12 flex items-center justify-center font-mono text-xs text-[#8E897F] gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-accent-orange" />
              <span>Traversing memory subgraph...</span>
            </div>
          ) : memory ? (
            <div className="flex flex-col gap-6">
              {/* Nodes Inspector */}
              <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6">
                <span className="font-mono text-xs text-[#8E897F] block mb-4">
                  INDEXED NODES ({memory.nodes.length})
                </span>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono text-xs">
                  {memory.nodes.map((node) => {
                    const badgeColor =
                      node.node_type === "module"
                        ? "bg-indigo-500/15 text-indigo-400 border-indigo-500/30"
                        : node.node_type === "file"
                        ? "bg-sky-500/15 text-sky-400 border-sky-500/30"
                        : node.node_type === "symbol"
                        ? "bg-accent-orange/15 text-accent-orange border-accent-orange/30"
                        : "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";

                    return (
                      <div
                        key={node.node_id}
                        className="border border-[#26231D] bg-[#0D0C0A] rounded-lg p-3.5 flex flex-col justify-between gap-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] border uppercase ${badgeColor}`}
                          >
                            {node.node_type}
                          </span>
                          <span className="text-[#8E897F] text-[11px] truncate max-w-[200px]">
                            {node.path}
                          </span>
                        </div>
                        <p className="text-sm font-semibold text-[#F5F2EB]">
                          {node.name}
                        </p>
                        <p className="text-[11px] text-[#8E897F] line-clamp-2">
                          {node.summary}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Traversal Edges List */}
              <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6">
                <span className="font-mono text-xs text-[#8E897F] block mb-4">
                  DIRECTED RELATIONSHIP EDGES ({memory.edges.length})
                </span>

                <div className="flex flex-col gap-2 font-mono text-xs">
                  {memory.edges.map((edge, idx) => (
                    <div
                      key={idx}
                      className="border border-[#26231D] bg-[#0D0C0A] rounded-lg px-4 py-2.5 flex items-center justify-between text-[#8E897F]"
                    >
                      <span className="text-[#F5F2EB] truncate max-w-[40%]">
                        {edge.source_id.split("::").pop()}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-[#1F1D18] text-accent-orange text-[10px] border border-[#26231D]">
                        ── {edge.relation} ──►
                      </span>
                      <span className="text-emerald-400 truncate max-w-[40%] text-right">
                        {edge.target_id.split("::").pop()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}

      {/* ── MODAL: SIMULATE DRIFT RUN ──────────────────────────────────────── */}
      {showSimulateModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="border border-[#26231D] bg-[#141310] rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 sm:p-8 flex flex-col gap-6 shadow-2xl">
            <div className="flex items-center justify-between pb-4 border-b border-[#26231D]">
              <div className="flex items-center gap-2">
                <Play className="w-5 h-5 text-accent-orange fill-current" />
                <h3 className="font-serif text-2xl text-[#F5F2EB]">
                  Simulate Drift Run
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowSimulateModal(false)}
                className="text-[#8E897F] hover:text-[#F5F2EB] font-mono text-sm"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-[#8E897F] font-mono leading-relaxed">
              Feed raw unified diff hunks and doc files directly through the
              6-stage pipeline to test drift classification, prompt extraction,
              and evidence table generation without pushing a git commit.
            </p>

            {/* Diff Input */}
            <div className="flex flex-col gap-2 font-mono text-xs">
              <label className="text-[#F5F2EB] font-semibold">
                Raw Git Diff
              </label>
              <textarea
                rows={5}
                value={simDiff}
                onChange={(e) => setSimDiff(e.target.value)}
                className="w-full bg-[#0D0C0A] border border-[#26231D] focus:border-accent-orange rounded-lg p-3 text-[#F5F2EB] font-mono outline-none text-xs"
              />
            </div>

            {/* Doc Input */}
            <div className="flex flex-col gap-2 font-mono text-xs">
              <label className="text-[#F5F2EB] font-semibold">
                Existing Markdown Document (README.md)
              </label>
              <textarea
                rows={5}
                value={simDoc}
                onChange={(e) => setSimDoc(e.target.value)}
                className="w-full bg-[#0D0C0A] border border-[#26231D] focus:border-accent-orange rounded-lg p-3 text-[#F5F2EB] font-mono outline-none text-xs"
              />
            </div>

            {/* Execute Button */}
            <button
              type="button"
              disabled={simLoading}
              onClick={() => void handleRunSimulation()}
              className="w-full bg-accent-orange hover:bg-accent-orange-hover text-black font-semibold py-3 rounded-lg text-sm flex items-center justify-center gap-2 transition-colors disabled:opacity-60"
            >
              {simLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Running 6-Stage Pipeline...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current stroke-none" />
                  <span>Execute Drift Simulation</span>
                </>
              )}
            </button>

            {simError && (
              <div className="border border-red-900/50 bg-red-950/20 text-red-300 rounded-xl p-4 text-xs font-mono">
                {simError}
              </div>
            )}

            {/* Simulation Results View */}
            {simResult && (
              <div className="border border-[#26231D] bg-[#0D0C0A] rounded-xl p-5 flex flex-col gap-4 font-mono text-xs">
                <span className="text-emerald-400 font-semibold uppercase tracking-wider flex items-center gap-1.5">
                  <Check className="w-4 h-4" />
                  Simulation Succeeded (Stage 06 Complete)
                </span>

                <div>
                  <span className="text-[#8E897F] block mb-1">
                    CHANGED SYMBOLS DETECTED:
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {simResult.change_report.changed_symbols.map((s, i) => (
                      <span
                        key={i}
                        className="bg-[#1F1D18] text-[#F5F2EB] px-2 py-0.5 rounded border border-[#26231D]"
                      >
                        {s.symbol_name} ({s.change_class})
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <span className="text-[#8E897F] block mb-1">
                    IMPACTED DOCUMENT SECTIONS:
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {simResult.drift_report.impacted_sections.map((sec, i) => (
                      <span
                        key={i}
                        className="bg-accent-orange/10 text-accent-orange px-2 py-0.5 rounded border border-accent-orange/30"
                      >
                        {sec.doc_path} #{sec.heading} ({sec.match_method})
                      </span>
                    ))}
                  </div>
                </div>

                {simResult.publish_result && (
                  <div className="pt-2 border-t border-[#26231D] flex items-center justify-between">
                    <span className="text-[#8E897F]">
                      Verification:{" "}
                      <span className="text-emerald-400">
                        {simResult.publish_result.verification_status}
                      </span>
                    </span>
                    <a
                      href={simResult.publish_result.pr_url || "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="text-accent-orange hover:text-accent-orange-hover flex items-center gap-1"
                    >
                      <span>
                        Simulated PR #{simResult.publish_result.pr_number}
                      </span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
