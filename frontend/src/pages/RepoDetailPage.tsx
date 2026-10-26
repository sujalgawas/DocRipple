import React, { useCallback, useEffect, useState } from "react";
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
  X,
  ShieldCheck,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import {
  getRepoSkill,
  getRepoMemory,
  executeDemoRun,
  getActivity,
  getDashboard,
  triggerRepo,
} from "../services/api";
import type {
  DocStyleSkill,
  RepoMemoryMap,
  DemoRunResponse,
  ActivityRun,
  MonitoredRepo,
  RunStatus,
} from "../services/api";

const STATUS_META: Record<
  RunStatus,
  { label: string; pill: string; dot: string }
> = {
  running: {
    label: "running",
    pill: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400",
  },
  no_drift: {
    label: "no drift",
    pill: "border-[#26231D] bg-[#1F1D18] text-[#8E897F]",
    dot: "bg-[#8E897F]",
  },
  pr_open: {
    label: "PR open",
    pill: "border-accent-orange/30 bg-accent-orange/10 text-accent-orange",
    dot: "bg-accent-orange",
  },
  merged: {
    label: "merged",
    pill: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
    dot: "bg-emerald-400",
  },
  failed: {
    label: "failed",
    pill: "border-red-500/30 bg-red-500/10 text-red-400",
    dot: "bg-red-400",
  },
};

function relativeTime(value?: string | null): string {
  if (!value) return "just now";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "just now";

  const seconds = Math.max(1, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return new Date(value).toLocaleDateString();
}

export const RepoDetailPage: React.FC = () => {
  const { owner = "sujalgawas", repo = "DocRipple" } = useParams();
  const repoFullName = `${owner}/${repo}`;

  const [activeTab, setActiveTab] = useState<"overview" | "skill" | "memory">("overview");

  // Overview: real pipeline runs and repository metadata
  const [runs, setRuns] = useState<ActivityRun[]>([]);
  const [monitoredRepo, setMonitoredRepo] = useState<MonitoredRepo | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [runsError, setRunsError] = useState<string | null>(null);
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

  const loadRuns = useCallback(
    async (silent = false) => {
      if (!silent) setLoadingRuns(true);

      const [activityResult, dashboardResult] = await Promise.allSettled([
        getActivity(repoFullName),
        getDashboard(),
      ]);

      if (activityResult.status === "fulfilled") {
        setRuns(activityResult.value.runs);
        setRunsError(null);
      } else {
        setRunsError(
          activityResult.reason instanceof Error
            ? activityResult.reason.message
            : "Could not load execution history"
        );
      }

      if (dashboardResult.status === "fulfilled") {
        setMonitoredRepo(
          dashboardResult.value.repositories.find(
            (item) => item.repo_full_name === repoFullName
          ) ?? null
        );
      }

      if (!silent) setLoadingRuns(false);
    },
    [repoFullName]
  );

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const hasRunning = runs.some((run) => run.status === "running");

  useEffect(() => {
    const timer = window.setInterval(
      () => {
        void loadRuns(true);
      },
      hasRunning ? 4000 : 15000
    );
    return () => window.clearInterval(timer);
  }, [hasRunning, loadRuns]);

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

  const handleSyncLatest = async () => {
    setSyncing(true);
    setRunsError(null);
    setSyncNotice(null);
    try {
      const result = await triggerRepo(owner, repo);
      setSyncNotice(
        `Queued ${result.commit_sha.slice(0, 7)} on ${result.branch}. History refreshes as the run progresses.`
      );
      window.setTimeout(() => {
        void loadRuns(true);
      }, 1500);
    } catch (err) {
      setRunsError(
        err instanceof Error ? err.message : "Could not sync the latest commit"
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

  const totalRuns = runs.length;
  const noDriftRuns = runs.filter((run) => run.status === "no_drift").length;
  const docsPrs = runs.filter(
    (run) => run.pr_number !== null || Boolean(run.pr_url)
  ).length;
  const totalLlmCalls = runs.reduce(
    (sum, run) => sum + (run.llm_calls ?? 0),
    0
  );
  const watchBranch = monitoredRepo?.watch_branch ?? "main";
  const isListening = monitoredRepo?.status === "listening";
  const repoStatusLabel = monitoredRepo ? monitoredRepo.status : "not connected";

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
                  : "bg-amber-500/10 text-amber-300 border-amber-500/20"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  isListening ? "bg-emerald-400" : "bg-amber-400"
                }`}
              />
              {repoStatusLabel}
            </span>
          </div>

          <h1 className="font-serif text-4xl lg:text-5xl text-[#F5F2EB] tracking-tight">
            {repo}
          </h1>
        </div>

        {/* Primary Actions */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={syncing}
            onClick={() => void handleSyncLatest()}
            className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-4 py-2.5 rounded-lg text-sm flex items-center gap-2 transition-colors shadow-sm font-sans disabled:opacity-60"
          >
            {syncing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            <span>{syncing ? "Syncing..." : "Sync latest commit"}</span>
          </button>
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

      {syncNotice && (
        <div className="mb-6 border border-emerald-900/50 bg-emerald-950/20 text-emerald-300 rounded-xl px-4 py-3 text-sm flex items-start gap-2">
          <Check className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{syncNotice}</span>
        </div>
      )}

      {runsError && (
        <div className="mb-6 border border-red-900/50 bg-red-950/20 text-red-300 rounded-xl px-4 py-3 text-sm flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{runsError}</span>
          </div>
          <button
            type="button"
            onClick={() => void loadRuns()}
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
          <span>Overview &amp; Runs</span>
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
          {/* Metrics */}
          <div className="grid grid-cols-1 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-[#26231D] border border-[#26231D] rounded-xl bg-[#141310] overflow-hidden">
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">Total Runs</span>
              <span className="font-serif text-3xl text-[#F5F2EB]">
                {loadingRuns && runs.length === 0 ? "…" : totalRuns}
              </span>
            </div>
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">No Drift (0 tokens)</span>
              <span className="font-serif text-3xl text-[#F5F2EB]">{noDriftRuns}</span>
            </div>
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">Documentation PRs</span>
              <span className="font-serif text-3xl text-[#F5F2EB]">{docsPrs}</span>
            </div>
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">LLM Calls</span>
              <span className="font-serif text-3xl text-emerald-400">{totalLlmCalls}</span>
            </div>
          </div>

          {/* Runs history */}
          <div>
            <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
              <div>
                <h2 className="font-serif text-2xl text-[#F5F2EB]">Execution History</h2>
                <p className="font-mono text-xs text-[#8E897F] mt-1">
                  Real pipeline runs for {repoFullName}
                  {hasRunning ? " · live polling" : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void loadRuns()}
                className="border border-[#26231D] bg-[#1F1D18] hover:bg-[#2A2720] text-[#F5F2EB] px-3 py-1.5 rounded-lg text-xs font-mono flex items-center gap-1.5 transition-colors"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 ${loadingRuns ? "animate-spin" : ""}`}
                />
                <span>Refresh</span>
              </button>
            </div>

            {loadingRuns ? (
              <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6 flex items-center gap-2 text-xs font-mono text-[#8E897F]">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Loading execution history...</span>
              </div>
            ) : runs.length === 0 ? (
              <div className="border border-dashed border-[#26231D] rounded-xl p-8 text-center">
                <p className="text-sm text-[#8E897F] mb-1">
                  No pipeline runs for this repository yet.
                </p>
                <p className="font-mono text-xs text-[#8E897F]/70 mb-4">
                  Sync the latest GitHub commit to start the first run.
                </p>
                <button
                  type="button"
                  disabled={syncing}
                  onClick={() => void handleSyncLatest()}
                  className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-4 py-2 rounded-lg text-sm inline-flex items-center gap-2 transition-colors disabled:opacity-60"
                >
                  {syncing ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <RefreshCw className="w-4 h-4" />
                  )}
                  <span>{syncing ? "Syncing..." : "Sync latest commit"}</span>
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {runs.map((run) => {
                  const status = STATUS_META[run.status];
                  const symbols = run.diff_preview?.changed_symbols ?? [];
                  const sections = run.diff_preview?.impacted_sections ?? [];
                  const title =
                    (run.commit_message || "").split("\n")[0].trim() ||
                    `Docs sync at ${(run.commit_sha || "unknown").slice(0, 7)}`;
                  const docTarget =
                    sections.length > 0
                      ? `${sections[0].doc_path} # ${sections[0].heading}${
                          sections.length > 1
                            ? ` +${sections.length - 1} more`
                            : ""
                        }`
                      : run.status === "no_drift"
                      ? "No doc sections impacted (0 LLM tokens)"
                      : "No doc sections impacted";
                  const shortSha = run.commit_sha
                    ? run.commit_sha.slice(0, 7)
                    : "—";

                  return (
                    <div
                      key={run.delivery_id}
                      className="border border-[#26231D] bg-[#141310] rounded-xl p-5 flex flex-col gap-3"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div className="flex items-start sm:items-center gap-3 min-w-0">
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-mono border flex items-center gap-1.5 shrink-0 ${status.pill}`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${status.dot}`}
                            />
                            {status.label}
                          </span>
                          <span className="text-sm font-medium text-[#F5F2EB] truncate">
                            {title}
                          </span>
                        </div>
                        <span className="font-mono text-xs text-[#8E897F] shrink-0">
                          {run.llm_calls ?? 0} LLM calls ·{" "}
                          {relativeTime(run.created_at)}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center justify-between gap-4 text-xs font-mono pt-2 border-t border-[#26231D]/60 text-[#8E897F]">
                        <div className="flex flex-wrap items-center gap-2">
                          <span>Changed AST:</span>
                          {symbols.length > 0 ? (
                            symbols.map((symbol, index) => (
                              <span
                                key={`${symbol.symbol_name}-${index}`}
                                className="bg-[#1F1D18] text-[#F5F2EB] px-2 py-0.5 rounded border border-[#26231D]"
                              >
                                {symbol.symbol_name} ({symbol.change_class})
                              </span>
                            ))
                          ) : (
                            <span className="text-[#8E897F]/70">
                              no public symbols
                            </span>
                          )}
                          <span>→</span>
                          <span className="text-accent-orange">{docTarget}</span>
                        </div>

                        <div className="flex items-center gap-3">
                          {run.commit_sha && (
                            <a
                              href={`https://github.com/${run.repo_full_name}/commit/${run.commit_sha}`}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-[#8E897F] hover:text-[#F5F2EB] transition-colors"
                              title={run.commit_sha}
                            >
                              <span>{shortSha}</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                          {run.author && <span>@{run.author}</span>}
                          {run.pr_number && run.pr_url && (
                            <a
                              href={run.pr_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1.5 text-accent-orange hover:text-accent-orange-hover"
                            >
                              <GitPullRequest className="w-3.5 h-3.5" />
                              <span>Docs PR #{run.pr_number}</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
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
            <h2 className="font-serif text-2xl text-[#F5F2EB] mb-2">Stage 0 Writing Style Extraction</h2>
            <p className="text-xs text-[#8E897F] font-mono leading-relaxed">
              Mined from existing Markdown documents in <code className="text-accent-orange">{repoFullName}</code>. This
              skill is injected verbatim into LangGraph Writer &amp; Reviewer prompts to prevent hallucinated rewrites and
              maintain tone consistency.
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
                  <p className="text-xs text-[#F5F2EB] leading-relaxed font-sans">{skill.tone_and_voice}</p>
                </div>

                <div className="border border-[#26231D] bg-[#141310] rounded-xl p-5 flex flex-col gap-2">
                  <span className="font-mono text-xs text-accent-orange font-semibold uppercase tracking-wider">
                    Heading Conventions
                  </span>
                  <ul className="text-xs text-[#8E897F] flex flex-col gap-1.5 font-mono list-disc list-inside">
                    {skill.heading_conventions.map((h, i) => (
                      <li key={i} className="text-[#F5F2EB]">{h}</li>
                    ))}
                  </ul>
                </div>

                <div className="border border-[#26231D] bg-[#141310] rounded-xl p-5 flex flex-col gap-2">
                  <span className="font-mono text-xs text-accent-orange font-semibold uppercase tracking-wider">
                    Code Block Rules
                  </span>
                  <ul className="text-xs text-[#8E897F] flex flex-col gap-1.5 font-mono list-disc list-inside">
                    {skill.code_block_rules.map((c, i) => (
                      <li key={i} className="text-[#F5F2EB]">{c}</li>
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
                    {copiedSkill ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
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
              <h2 className="font-serif text-2xl text-[#F5F2EB] mb-1">Stage 0 Repository Memory Graph</h2>
              <p className="text-xs text-[#8E897F] font-mono">
                2-hop node traversal mapping: <span className="text-indigo-400">Module</span> →{" "}
                <span className="text-sky-400">File</span> → <span className="text-accent-orange">Symbol</span> →{" "}
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
                          <span className={`px-2 py-0.5 rounded text-[10px] border uppercase ${badgeColor}`}>
                            {node.node_type}
                          </span>
                          <span className="text-[#8E897F] text-[11px] truncate max-w-[200px]">{node.path}</span>
                        </div>
                        <p className="text-sm font-semibold text-[#F5F2EB]">{node.name}</p>
                        <p className="text-[11px] text-[#8E897F] line-clamp-2">{node.summary}</p>
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
                      <span className="text-[#F5F2EB] truncate max-w-[40%]">{edge.source_id.split("::").pop()}</span>
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

      {/* ── MODAL: SIMULATE DRIFT RUN ────────────────────────────────────── */}
      {showSimulateModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#141310] border border-[#26231D] rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
            {/* Header */}
            <div className="p-6 border-b border-[#26231D] flex items-center justify-between">
              <div>
                <h2 className="font-serif text-2xl text-[#F5F2EB]">Simulate End-to-End Drift Run</h2>
                <p className="text-xs text-[#8E897F] font-mono mt-0.5">
                  Sends unified diff to Stage 2 (AST) → Stage 3 (Drift) → Stage 4 (LangGraph) → Stage 5 (PR).
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowSimulateModal(false)}
                className="text-[#8E897F] hover:text-[#F5F2EB] p-1.5 rounded-lg border border-[#26231D] bg-[#0D0C0A]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Content Body */}
            <div className="p-6 overflow-y-auto flex flex-col gap-5">
              <div>
                <label className="block text-xs font-mono text-[#8E897F] mb-1.5 uppercase tracking-wider">
                  Raw Unified Diff
                </label>
                <textarea
                  rows={4}
                  value={simDiff}
                  onChange={(e) => setSimDiff(e.target.value)}
                  className="w-full bg-[#0D0C0A] border border-[#26231D] focus:border-accent-orange rounded-lg p-3 font-mono text-xs text-[#F5F2EB] outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-[#8E897F] mb-1.5 uppercase tracking-wider">
                  Target Documentation (README.md)
                </label>
                <textarea
                  rows={4}
                  value={simDoc}
                  onChange={(e) => setSimDoc(e.target.value)}
                  className="w-full bg-[#0D0C0A] border border-[#26231D] focus:border-accent-orange rounded-lg p-3 font-mono text-xs text-[#F5F2EB] outline-none"
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  disabled={simLoading}
                  onClick={handleRunSimulation}
                  className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-5 py-2.5 rounded-lg text-sm flex items-center gap-2 shadow-sm disabled:opacity-60 font-sans"
                >
                  {simLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Executing 6 Stages...</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 fill-current stroke-none" />
                      <span>Run Pipeline Demo</span>
                    </>
                  )}
                </button>
              </div>

              {simError && (
                <div className="border border-red-900/50 bg-red-950/20 text-red-300 rounded-xl px-4 py-3 text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{simError}</span>
                </div>
              )}

              {/* Simulation Result */}
              {simResult && (
                <div className="border border-emerald-500/30 bg-[#0D0C0A] rounded-xl p-5 flex flex-col gap-4 font-mono text-xs">
                  <div className="flex items-center justify-between text-emerald-400">
                    <span className="flex items-center gap-2 font-bold">
                      <ShieldCheck className="w-4 h-4" />
                      Pipeline Executed Successfully
                    </span>
                    <span className="text-[#8E897F] text-[11px]">{simResult.delivery_id}</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[#8E897F]">
                    <div className="border border-[#26231D] bg-[#141310] p-3 rounded">
                      <span className="text-accent-orange block mb-1 font-semibold">Stage 2: Changed Symbols</span>
                      {simResult.change_report.changed_symbols.map((s, i) => (
                        <p key={i} className="text-[#F5F2EB]">
                          • {s.symbol_name} ({s.change_class})
                        </p>
                      ))}
                    </div>

                    <div className="border border-[#26231D] bg-[#141310] p-3 rounded">
                      <span className="text-accent-orange block mb-1 font-semibold">Stage 3: Impacted Sections</span>
                      {simResult.drift_report.impacted_sections.map((sec, i) => (
                        <p key={i} className="text-[#F5F2EB]">
                          • {sec.doc_path} #{sec.heading}
                        </p>
                      ))}
                    </div>
                  </div>

                  {simResult.publish_result && (
                    <div className="border border-[#26231D] bg-[#141310] p-3 rounded flex flex-col gap-2">
                      <div className="flex items-center justify-between">
                        <span className="text-emerald-400 font-semibold">Stage 4–5: Pull Request Opened</span>
                        <a
                          href={simResult.publish_result.pr_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-accent-orange hover:underline inline-flex items-center gap-1"
                        >
                          <span>PR #{simResult.publish_result.pr_number}</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                      <pre className="text-[11px] text-[#8E897F] overflow-x-auto whitespace-pre-wrap">
                        {simResult.publish_result.evidence_table_md}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
