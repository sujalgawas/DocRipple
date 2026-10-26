import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, AlertCircle, RefreshCw, Radio } from "lucide-react";
import { getActivity } from "../services/api";
import type { ActivityRun, RunStatus } from "../services/api";
import type {
  ActivityRunItem,
  ChangedSymbol,
  ImpactedDocSection,
  PipelineStageState,
} from "../lib/api";
import { RunInspectorDrawer } from "../components/activity/RunInspectorDrawer";

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

function statusLabel(status: RunStatus): string {
  switch (status) {
    case "no_drift":
      return "no drift";
    case "pr_open":
      return "PR open";
    default:
      return status;
  }
}

function llmCallsText(calls: number): string {
  return `${calls} llm call${calls === 1 ? "" : "s"}`;
}

function buildStages(
  run: ActivityRun,
  symbolCount: number,
  sectionCount: number
): PipelineStageState[] {
  const manual = run.delivery_id.startsWith("manual-");
  const stages: PipelineStageState[] = [
    {
      stage_id: "01",
      name: "Ingest",
      status: "completed",
      detail: manual
        ? "Manual trigger · commit resolved"
        : "HMAC ok · WebhookJob enqueued",
    },
    {
      stage_id: "02",
      name: "Change analyzer",
      status: "completed",
      detail:
        symbolCount > 0
          ? `${symbolCount} public symbol${symbolCount === 1 ? "" : "s"} extracted`
          : "No public AST symbols changed",
    },
    {
      stage_id: "03",
      name: "Drift engine",
      status: "completed",
      detail:
        sectionCount > 0
          ? `${sectionCount} doc section${sectionCount === 1 ? "" : "s"} impacted`
          : "0 doc sections impacted (early exit gate)",
    },
  ];

  const notReached: PipelineStageState[] = [
    {
      stage_id: "04",
      name: "Planner → Writer",
      status: sectionCount > 0 ? "running" : "skipped",
      detail:
        sectionCount > 0
          ? "LangGraph generating section draft"
          : "Waiting on analyzer",
    },
    {
      stage_id: "05",
      name: "Verifier",
      status: sectionCount > 0 ? "running" : "skipped",
      detail: sectionCount > 0 ? "Pending syntax checks" : "Not reached",
    },
    {
      stage_id: "06",
      name: "Publish PR",
      status: "running",
      detail: "Awaiting orchestrator",
    },
  ];

  if (run.status === "running") {
    return [...stages, ...notReached];
  }

  if (run.status === "no_drift") {
    return [
      ...stages,
      {
        stage_id: "04",
        name: "Planner → Writer",
        status: "skipped",
        detail: "0 LLM calls made",
      },
      {
        stage_id: "05",
        name: "Verifier",
        status: "skipped",
        detail: "Skipped",
      },
      {
        stage_id: "06",
        name: "Publish PR",
        status: "skipped",
        detail: "No PR required",
      },
    ];
  }

  if (run.status === "failed") {
    return [
      ...stages,
      {
        stage_id: "04",
        name: "Planner → Writer",
        status: "failed",
        detail: "Pipeline error before publish",
      },
      {
        stage_id: "05",
        name: "Verifier",
        status: "skipped",
        detail: "Not reached",
      },
      {
        stage_id: "06",
        name: "Publish PR",
        status: "failed",
        detail: "No PR created",
      },
    ];
  }

  // pr_open or merged
  return [
    ...stages,
    {
      stage_id: "04",
      name: "Planner → Writer",
      status: "completed",
      detail: "Section edit spliced",
    },
    {
      stage_id: "05",
      name: "Verifier",
      status: "completed",
      detail: "Syntax and fences passed",
    },
    {
      stage_id: "06",
      name: "Publish PR",
      status: "completed",
      detail:
        run.status === "merged"
          ? "PR merged"
          : `PR #${run.pr_number ?? "?"} opened with evidence table`,
    },
  ];
}

function toActivityRunItem(run: ActivityRun): ActivityRunItem {
  const preview = run.diff_preview;

  const changedSymbols: ChangedSymbol[] = (preview?.changed_symbols ?? []).map(
    (symbol) => ({
      file_path: symbol.file_path,
      symbol_name: symbol.symbol_name,
      symbol_kind: symbol.symbol_kind as ChangedSymbol["symbol_kind"],
      change_class: symbol.change_class as ChangedSymbol["change_class"],
      change_type: symbol.change_type as ChangedSymbol["change_type"],
      old_signature: symbol.old_signature ?? null,
      new_signature: symbol.new_signature ?? null,
    })
  );

  const impactedSections: ImpactedDocSection[] = (
    preview?.impacted_sections ?? []
  ).map((section) => ({
    doc_path: section.doc_path,
    heading: section.heading,
    anchor: section.anchor ?? null,
    matched_symbols: section.matched_symbols,
    match_method: section.match_method as ImpactedDocSection["match_method"],
    confidence_score: section.confidence_score,
  }));

  const title =
    (run.commit_message || "").split("\n")[0].trim() ||
    `Docs sync at ${(run.commit_sha || "unknown").slice(0, 7)}`;

  const evidence =
    run.evidence_table_md?.trim() ||
    (run.status === "no_drift"
      ? "No documentation sections impacted. Early exit gate triggered (0 LLM tokens spent)."
      : run.status === "running"
      ? "Pipeline in progress — the evidence table appears when the run finishes."
      : run.status === "failed"
      ? "Pipeline failed before an evidence table was produced."
      : "No evidence table recorded.");

  return {
    id: run.delivery_id,
    delivery_id: run.delivery_id,
    status: run.status,
    status_label: statusLabel(run.status),
    title,
    repo_name: run.repo_full_name.split("/")[1] || run.repo_full_name,
    repo_full_name: run.repo_full_name,
    sha: (run.commit_sha || "").slice(0, 7),
    author: run.author || "unknown",
    llm_calls: run.llm_calls ?? 0,
    llm_calls_text: llmCallsText(run.llm_calls ?? 0),
    relative_time: relativeTime(run.created_at),
    stages: buildStages(run, changedSymbols.length, impactedSections.length),
    changed_symbols: changedSymbols,
    impacted_sections: impactedSections,
    evidence_table_md: evidence,
    diff_preview: {
      file_path: preview?.file_path || "—",
      deleted_lines: preview?.deleted_lines ?? [],
      added_lines: preview?.added_lines ?? [],
      context:
        preview?.context ||
        (run.status === "no_drift"
          ? "No documentation edit required for this commit."
          : "Waiting for a documentation edit preview."),
    },
    pr_url: run.pr_url,
    pr_number: run.pr_number,
  };
}

export const ActivityPage: React.FC = () => {
  const [runs, setRuns] = useState<ActivityRunItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await getActivity();
      setRuns(data.runs.map(toActivityRunItem));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load activity");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const hasRunning = useMemo(
    () => runs.some((run) => run.status === "running"),
    [runs]
  );

  useEffect(() => {
    const timer = window.setInterval(
      () => {
        void load(true);
      },
      hasRunning ? 4000 : 15000
    );
    return () => window.clearInterval(timer);
  }, [hasRunning, load]);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedId) ?? null,
    [runs, selectedId]
  );

  const getStatusPill = (status: ActivityRunItem["status"]) => {
    switch (status) {
      case "running":
        return {
          pill: "border-amber-500/30 bg-amber-500/10 text-amber-300",
          dot: "bg-amber-400",
          label: "running",
        };
      case "no_drift":
        return {
          pill: "border-[#26231D] bg-[#1F1D18] text-[#8E897F]",
          dot: "bg-[#8E897F]",
          label: "no drift",
        };
      case "pr_open":
        return {
          pill: "border-accent-orange/30 bg-accent-orange/10 text-accent-orange",
          dot: "bg-accent-orange",
          label: "PR open",
        };
      case "merged":
        return {
          pill: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
          dot: "bg-emerald-400",
          label: "merged",
        };
      case "failed":
        return {
          pill: "border-red-500/30 bg-red-500/10 text-red-400",
          dot: "bg-red-400",
          label: "failed",
        };
    }
  };

  return (
    <div className="p-8 lg:p-12 max-w-5xl">
      {/* Title & Subtitle */}
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="font-serif text-5xl text-[#F5F2EB] tracking-tight leading-tight mb-2">
            Activity
          </h1>
          <p className="text-sm text-[#8E897F]">
            Every push we heard about, and what we did with it.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {hasRunning && (
            <span className="font-mono text-xs text-amber-300 flex items-center gap-1.5">
              <Radio className="w-3.5 h-3.5 animate-pulse" />
              live · polling
            </span>
          )}
          <button
            type="button"
            onClick={() => void load()}
            className="border border-[#26231D] bg-[#1F1D18] hover:bg-[#2A2720] text-[#F5F2EB] px-3 py-1.5 rounded-lg text-xs font-mono flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 border border-red-900/50 bg-red-950/20 text-red-300 rounded-xl px-4 py-3 text-sm flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="font-mono text-xs underline hover:text-[#F5F2EB] shrink-0"
          >
            retry
          </button>
        </div>
      )}

      {/* Runs Card Container */}
      {loading ? (
        <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6 flex items-center gap-2 text-xs font-mono text-[#8E897F]">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading activity runs...</span>
        </div>
      ) : runs.length === 0 ? (
        <div className="border border-dashed border-[#26231D] rounded-xl p-8 text-center">
          <p className="text-sm text-[#8E897F] mb-1">No activity yet.</p>
          <p className="font-mono text-xs text-[#8E897F]/70">
            Use “Sync latest commit” on a repository card, or push to a
            connected repo.
          </p>
        </div>
      ) : (
        <div className="border border-[#26231D] bg-[#141310] rounded-xl divide-y divide-[#26231D] overflow-hidden shadow-xl">
          {runs.map((run) => {
            const pill = getStatusPill(run.status);
            return (
              <div
                key={run.id}
                onClick={() => setSelectedId(run.id)}
                className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-[#1A1813] transition-colors cursor-pointer group"
              >
                {/* Left Column: Status Pill + Title & Info */}
                <div className="flex items-center gap-3.5 min-w-0">
                  <div
                    className={`border rounded-full px-2.5 py-0.5 text-xs font-mono flex items-center gap-1.5 shrink-0 ${pill.pill}`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${pill.dot}`} />
                    <span>{pill.label}</span>
                  </div>

                  <div className="min-w-0">
                    <p className="text-sm font-medium text-[#F5F2EB] group-hover:text-accent-orange transition-colors truncate">
                      {run.title}
                    </p>
                    <p className="font-mono text-xs text-[#8E897F] mt-0.5 truncate">
                      {run.repo_name} ·{" "}
                      <span className="text-[#F5F2EB]">{run.sha || "—"}</span> ·{" "}
                      {run.author}
                    </p>
                  </div>
                </div>

                {/* Right Column: LLM Calls & Relative Time */}
                <div className="text-left sm:text-right font-mono text-xs shrink-0">
                  <p className="text-[#F5F2EB]">{run.llm_calls_text}</p>
                  <p className="text-[#8E897F] mt-0.5">{run.relative_time}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Run Inspector Slide-Over Drawer */}
      <RunInspectorDrawer run={selectedRun} onClose={() => setSelectedId(null)} />
    </div>
  );
};
