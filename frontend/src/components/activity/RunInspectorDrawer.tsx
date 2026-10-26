import React from "react";
import {
  X,
  GitPullRequest,
  ExternalLink,
  CheckCircle2,
  Clock,
  AlertTriangle,
  MinusCircle,
  FileText,
  Code2
} from "lucide-react";
import type { ActivityRunItem } from "../../lib/api";

interface RunInspectorDrawerProps {
  run: ActivityRunItem | null;
  onClose: () => void;
}

export const RunInspectorDrawer: React.FC<RunInspectorDrawerProps> = ({ run, onClose }) => {
  if (!run) return null;

  const getStatusBadge = () => {
    switch (run.status) {
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

  const badge = getStatusBadge();

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Dark backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-xs transition-opacity animate-fade-in"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-2xl bg-[#141310] border-l border-[#26231D] shadow-2xl flex flex-col justify-between overflow-y-auto">
          {/* Header */}
          <div className="p-6 border-b border-[#26231D] bg-[#0D0C0A]/80 sticky top-0 z-10 backdrop-blur-md">
            <div className="flex items-center justify-between mb-3">
              <span className="font-mono text-xs text-[#8E897F]">
                delivery_id: <span className="text-[#F5F2EB]">{run.delivery_id}</span>
              </span>
              <button
                type="button"
                onClick={onClose}
                className="p-1 rounded-lg border border-[#26231D] bg-[#141310] hover:bg-[#1F1D18] text-[#8E897F] hover:text-[#F5F2EB] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-[#F5F2EB] leading-snug">
                  {run.title}
                </h2>
                <p className="font-mono text-xs text-[#8E897F] mt-1">
                  {run.repo_full_name} · <span className="text-accent-orange font-medium">{run.sha}</span> · {run.author}
                </p>
              </div>

              <div className={`border rounded-full px-2.5 py-0.5 text-xs font-mono flex items-center gap-1.5 shrink-0 ${badge.pill}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${badge.dot}`} />
                <span>{badge.label}</span>
              </div>
            </div>
          </div>

          {/* Drawer Body */}
          <div className="p-6 flex flex-col gap-6 flex-1">
            {/* 1. 6-Stage Pipeline Progress Bar */}
            <div>
              <span className="font-mono text-xs text-[#8E897F] uppercase tracking-wider block mb-3">
                Pipeline Execution Trace (6 Stages)
              </span>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 font-mono text-xs">
                {run.stages.map((st) => {
                  const isDone = st.status === "completed";
                  const isRunning = st.status === "running";
                  const isSkipped = st.status === "skipped";
                  const isFailed = st.status === "failed";

                  return (
                    <div
                      key={st.stage_id}
                      className={`border rounded-lg p-2.5 flex flex-col justify-between ${
                        isDone
                          ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400"
                          : isRunning
                          ? "border-amber-500/30 bg-amber-500/5 text-amber-300"
                          : isFailed
                          ? "border-red-500/30 bg-red-500/5 text-red-400"
                          : "border-[#26231D] bg-[#0D0C0A] text-[#8E897F]/60"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] opacity-75">{st.stage_id}</span>
                        {isDone && <CheckCircle2 className="w-3 h-3 text-emerald-400" />}
                        {isRunning && <Clock className="w-3 h-3 text-amber-400 animate-spin" />}
                        {isSkipped && <MinusCircle className="w-3 h-3 text-[#8E897F]" />}
                        {isFailed && <AlertTriangle className="w-3 h-3 text-red-400" />}
                      </div>
                      <p className="font-semibold text-[11px] truncate">{st.name}</p>
                      <p className="text-[10px] text-[#8E897F] mt-1 line-clamp-1">{st.detail}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 2. Extracted AST Changed Symbols */}
            <div>
              <span className="font-mono text-xs text-[#8E897F] uppercase tracking-wider block mb-3">
                Stage 2: Extracted AST Symbols ({run.changed_symbols.length})
              </span>

              {run.changed_symbols.length > 0 ? (
                <div className="flex flex-col gap-2 font-mono text-xs">
                  {run.changed_symbols.map((sym, idx) => (
                    <div
                      key={idx}
                      className="border border-[#26231D] bg-[#0D0C0A] rounded-lg p-3 flex flex-col gap-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase bg-accent-orange/15 text-accent-orange border border-accent-orange/30">
                            {sym.change_class}
                          </span>
                          <span className="text-[#F5F2EB] font-bold">{sym.symbol_name}</span>
                          <span className="text-[#8E897F] text-[11px]">({sym.symbol_kind})</span>
                        </div>
                        <span className="text-[11px] text-[#8E897F]">{sym.file_path}</span>
                      </div>
                      {sym.new_signature && (
                        <p className="text-[11px] text-[#8E897F] bg-[#141310] px-2.5 py-1 rounded border border-[#26231D]">
                          {sym.new_signature}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="border border-[#26231D] bg-[#0D0C0A] rounded-lg p-3 text-xs font-mono text-[#8E897F]">
                  Zero AST symbols modified (comment / whitespace / formatting change only).
                </div>
              )}
            </div>

            {/* 3. Matched Impacted Documentation Sections */}
            <div>
              <span className="font-mono text-xs text-[#8E897F] uppercase tracking-wider block mb-3">
                Stage 3: Impacted Doc Sections ({run.impacted_sections.length})
              </span>

              {run.impacted_sections.length > 0 ? (
                <div className="flex flex-col gap-2 font-mono text-xs">
                  {run.impacted_sections.map((sec, idx) => (
                    <div
                      key={idx}
                      className="border border-[#26231D] bg-[#0D0C0A] rounded-lg p-3 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2.5">
                        <FileText className="w-4 h-4 text-accent-orange shrink-0" />
                        <div>
                          <p className="text-[#F5F2EB] font-medium">
                            {sec.doc_path} <span className="text-accent-orange">#{sec.heading}</span>
                          </p>
                          <p className="text-[11px] text-[#8E897F] mt-0.5">
                            Matched via: <span className="text-[#F5F2EB]">{sec.match_method}</span>
                          </p>
                        </div>
                      </div>

                      <span className="px-2 py-0.5 rounded text-[11px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {Math.round(sec.confidence_score * 100)}% conf
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="border border-[#26231D] bg-[#0D0C0A] rounded-lg p-3 text-xs font-mono text-[#8E897F]">
                  0 doc sections impacted. Early exit gate triggered; 0 LLM calls made.
                </div>
              )}
            </div>

            {/* 4. Warm Cream Paper Diff Preview (#F3EFE6) */}
            <div>
              <span className="font-mono text-xs text-[#8E897F] uppercase tracking-wider block mb-3">
                Stage 4: Surgical Markdown Edit Preview
              </span>

              <div className="bg-[#F3EFE6] text-[#141310] rounded-xl p-5 shadow-xl font-mono text-xs border border-[#E3DEC5] flex flex-col gap-3">
                <div className="flex items-center justify-between border-b border-[#141310]/10 pb-2">
                  <span className="font-bold text-[#141310] flex items-center gap-1.5">
                    <Code2 className="w-3.5 h-3.5 text-[#E8612C]" />
                    <span>{run.diff_preview.file_path}</span>
                  </span>
                  <span className="text-[#8E897F] text-[11px]">suggested by docripple</span>
                </div>

                <p className="text-[11px] text-[#141310]/70 whitespace-pre-wrap">
                  {run.diff_preview.context}
                </p>

                {/* Diff Lines */}
                <div className="flex flex-col gap-1 my-1">
                  {run.diff_preview.deleted_lines.map((l, i) => (
                    <div key={i} className="bg-red-500/15 text-red-800 px-2 py-1 rounded line-through">
                      {l}
                    </div>
                  ))}
                  {run.diff_preview.added_lines.map((l, i) => (
                    <div key={i} className="bg-emerald-500/15 text-emerald-900 px-2 py-1 rounded">
                      {l}
                    </div>
                  ))}
                </div>

                {/* Evidence Table */}
                <div className="border-t border-[#141310]/10 pt-3">
                  <span className="font-bold text-[11px] block mb-1 text-[#141310]">
                    Generated PR Evidence Table:
                  </span>
                  <pre className="text-[10px] text-[#141310]/80 overflow-x-auto whitespace-pre-wrap bg-white/40 p-2 rounded border border-[#141310]/5">
                    {run.evidence_table_md}
                  </pre>
                </div>
              </div>
            </div>
          </div>

          {/* Footer Action */}
          <div className="p-5 border-t border-[#26231D] bg-[#0D0C0A] flex items-center justify-between">
            <span className="font-mono text-xs text-[#8E897F]">
              Cost: <span className="text-[#F5F2EB] font-bold">{run.llm_calls_text}</span>
            </span>

            {run.pr_url ? (
              <a
                href={run.pr_url}
                target="_blank"
                rel="noreferrer"
                className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-4 py-2 rounded-lg text-xs font-mono flex items-center gap-1.5 transition-colors shadow-sm"
              >
                <GitPullRequest className="w-3.5 h-3.5" />
                <span>View Pull Request #{run.pr_number}</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            ) : (
              <span className="font-mono text-xs text-[#8E897F]">
                No pull request created
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
