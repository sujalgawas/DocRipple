import React, { useState } from "react";
import { SEED_ACTIVITY_RUNS } from "../lib/api";
import type { ActivityRunItem } from "../lib/api";
import { RunInspectorDrawer } from "../components/activity/RunInspectorDrawer";

export const ActivityPage: React.FC = () => {
  const [runs] = useState<ActivityRunItem[]>(SEED_ACTIVITY_RUNS);
  const [selectedRun, setSelectedRun] = useState<ActivityRunItem | null>(null);

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
      <div className="mb-6">
        <h1 className="font-serif text-5xl text-[#F5F2EB] tracking-tight leading-tight mb-2">
          Activity
        </h1>
        <p className="text-sm text-[#8E897F]">
          Every push we heard about, and what we did with it.
        </p>
      </div>

      {/* Runs Card Container */}
      <div className="border border-[#26231D] bg-[#141310] rounded-xl divide-y divide-[#26231D] overflow-hidden shadow-xl">
        {runs.map((run) => {
          const pill = getStatusPill(run.status);
          return (
            <div
              key={run.id}
              onClick={() => setSelectedRun(run)}
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
                  <p className="font-mono text-xs text-[#8E897F] mt-0.5">
                    {run.repo_name} · <span className="text-[#F5F2EB]">{run.sha}</span> · {run.author}
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

      {/* Run Inspector Slide-Over Drawer */}
      <RunInspectorDrawer run={selectedRun} onClose={() => setSelectedRun(null)} />
    </div>
  );
};
