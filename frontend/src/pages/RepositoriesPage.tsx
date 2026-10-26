import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, Plus, GitBranch } from "lucide-react";
import { getStoredRepositories } from "../services/api";
import type { RepositoryItem } from "../services/api";

export const RepositoriesPage: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [repositories, setRepositories] = useState<RepositoryItem[]>([]);

  useEffect(() => {
    setRepositories(getStoredRepositories());
  }, []);

  const filteredRepos = repositories.filter(
    (r) =>
      r.name.toLowerCase().includes(search.toLowerCase()) ||
      r.owner.toLowerCase().includes(search.toLowerCase())
  );

  const runs = [
    {
      id: "run-1",
      status: "running",
      statusLabel: "running",
      statusClass: "border-amber-500/30 bg-amber-500/10 text-amber-300",
      dotClass: "bg-amber-400",
      title: "feat(analyzer): add --dry-run flag to CLI",
      repo: "DocRipple",
      owner: "sujalgawas",
      sha: "a3f9c21",
      author: "sujalgawas",
      llmCalls: "3 llm calls",
      time: "4 min ago",
    },
    {
      id: "run-2",
      status: "no_drift",
      statusLabel: "no drift",
      statusClass: "border-[#26231D] bg-[#1F1D18] text-[#8E897F]",
      dotClass: "bg-[#8E897F]",
      title: "refactor: tidy internal helpers in drift.py",
      repo: "DocRipple",
      owner: "sujalgawas",
      sha: "7be02d4",
      author: "sujalgawas",
      llmCalls: "0 llm calls",
      time: "38 min ago",
    },
    {
      id: "run-3",
      status: "pr_open",
      statusLabel: "PR open",
      statusClass: "border-accent-orange/30 bg-accent-orange/10 text-accent-orange",
      dotClass: "bg-accent-orange",
      title: "rename POST /invoices → /v2/invoices",
      repo: "ledger-api",
      owner: "sujalgawas",
      sha: "c19e8f0",
      author: "mira-k",
      llmCalls: "5 llm calls",
      time: "2 h ago",
    },
    {
      id: "run-4",
      status: "merged",
      statusLabel: "merged",
      statusClass: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
      dotClass: "bg-emerald-400",
      title: "env: GITHUB_APP_ID now required",
      repo: "DocRipple",
      owner: "sujalgawas",
      sha: "e44a1b7",
      author: "sujalgawas",
      llmCalls: "2 llm calls",
      time: "5 h ago",
    },
  ];

  return (
    <div className="p-8 lg:p-12 max-w-6xl">
      {/* Header Row */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <p className="font-mono text-xs text-[#8E897F] mb-1">good afternoon, sujal</p>
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

      {/* 3-Column Metric Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-[#26231D] border border-[#26231D] rounded-xl bg-[#141310] mb-8 overflow-hidden">
        <div className="p-5">
          <p className="font-mono text-xs text-[#8E897F] mb-2">Runs this week</p>
          <p className="font-serif text-4xl text-[#F5F2EB]">47</p>
        </div>
        <div className="p-5">
          <p className="font-mono text-xs text-[#8E897F] mb-2">Skipped (0 tokens)</p>
          <p className="font-serif text-4xl text-[#F5F2EB]">31</p>
        </div>
        <div className="p-5">
          <p className="font-mono text-xs text-[#8E897F] mb-2">PRs merged</p>
          <p className="font-serif text-4xl text-[#F5F2EB]">12</p>
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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-14">
        {filteredRepos.map((repo) => (
          <div
            key={repo.id}
            onClick={() => navigate(`/repositories/${repo.owner}/${repo.name}`)}
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
                    repo.status === "listening" ? "bg-emerald-400" : "bg-[#8E897F]"
                  }`}
                />
                <span
                  className={
                    repo.status === "listening" ? "text-emerald-400" : "text-[#8E897F]"
                  }
                >
                  {repo.status}
                </span>
              </div>
            </div>

            {/* Tracked docs badges */}
            <div className="flex flex-wrap items-center gap-2">
              {repo.trackedDocs.map((doc) => (
                <span
                  key={doc}
                  className="bg-[#1F1D18] text-[#F5F2EB] border border-[#26231D] px-2 py-0.5 rounded text-xs font-mono"
                >
                  {doc}
                </span>
              ))}
            </div>

            {/* Footer row */}
            <div className="flex items-center justify-between text-xs font-mono text-[#8E897F] pt-2 border-t border-[#26231D]/60">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1 text-[#F5F2EB]">
                  <GitBranch className="w-3.5 h-3.5 text-[#8E897F]" />
                  <span>{repo.branch}</span>
                </span>
                <span>{repo.language}</span>
                <span>{repo.runsCount} runs</span>
              </div>
              <span>{repo.lastPushed}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Latest Runs Section */}
      <div>
        <h2 className="font-serif text-3xl text-[#F5F2EB] tracking-tight mb-4">
          Latest runs
        </h2>

        <div className="flex flex-col gap-3">
          {runs.map((run) => (
            <div
              key={run.id}
              onClick={() => navigate(`/repositories/${run.owner}/${run.repo}`)}
              className="border border-[#26231D] bg-[#141310] hover:border-[#38332A] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-colors cursor-pointer group"
            >
              {/* Left: Pill & Title */}
              <div className="flex items-center gap-3.5 min-w-0">
                <div
                  className={`border rounded-full px-2.5 py-0.5 text-xs font-mono flex items-center gap-1.5 shrink-0 ${run.statusClass}`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${run.dotClass}`} />
                  <span>{run.statusLabel}</span>
                </div>

                <div className="min-w-0">
                  <p className="text-sm font-medium text-[#F5F2EB] group-hover:text-accent-orange transition-colors truncate">
                    {run.title}
                  </p>
                  <p className="font-mono text-xs text-[#8E897F] mt-0.5">
                    {run.repo} · <span className="text-[#F5F2EB]">{run.sha}</span> · {run.author}
                  </p>
                </div>
              </div>

              {/* Right: LLM calls & Time */}
              <div className="text-right font-mono text-xs text-[#8E897F] shrink-0">
                <p className="text-[#F5F2EB]">{run.llmCalls}</p>
                <p className="text-[#8E897F] mt-0.5">{run.time}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
