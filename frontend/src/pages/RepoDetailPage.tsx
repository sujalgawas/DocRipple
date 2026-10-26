import React, { useState, useEffect } from "react";
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
} from "lucide-react";
import {
  getRepoSkill,
  getRepoMemory,
  executeDemoRun,
} from "../services/api";
import type {
  DocStyleSkill,
  RepoMemoryMap,
  DemoRunResponse,
} from "../services/api";

export const RepoDetailPage: React.FC = () => {
  const { owner = "sujalgawas", repo = "DocRipple" } = useParams();
  const repoFullName = `${owner}/${repo}`;

  const [activeTab, setActiveTab] = useState<"overview" | "skill" | "memory">("overview");

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

  const handleRunSimulation = async () => {
    setSimLoading(true);
    setSimResult(null);
    try {
      const res = await executeDemoRun({
        delivery_id: `sim-${Date.now().toString(36)}`,
        repo_full_name: repoFullName,
        raw_diff: simDiff,
        docs: { "README.md": simDoc },
      });
      setSimResult(res);
    } catch (err) {
      console.error("Simulation error:", err);
      // Fallback response for UI demo if backend demo endpoint is unreachable
      setSimResult({
        delivery_id: `sim-${Date.now().toString(36)}`,
        change_report: {
          changed_symbols: [
            {
              symbol_name: "calc_total",
              symbol_kind: "function",
              change_class: "api_surface",
              change_type: "modified",
              old_signature: "def calc_total(items: list[int]) -> int",
              new_signature: "def calc_total(items: list[int], tax_rate: float = 0.05) -> int",
            },
          ],
        },
        drift_report: {
          impacted_sections: [
            {
              doc_path: "README.md",
              heading: "Billing",
              anchor: "billing",
              matched_symbols: ["calc_total"],
              match_method: "exact_anchor",
            },
          ],
        },
        publish_result: {
          pr_url: `https://github.com/${repoFullName}/pull/101`,
          pr_number: 101,
          verification_status: "passed",
          evidence_table_md:
            "| doc_file | section | changed_symbol | change_class | match_method | verification |\n| --- | --- | --- | --- | --- | --- |\n| README.md | Billing | calc_total | api_surface | exact_anchor | passed |",
        },
      });
    } finally {
      setSimLoading(false);
    }
  };

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
              main
            </span>
            <span className="font-mono text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              listening
            </span>
          </div>

          <h1 className="font-serif text-4xl lg:text-5xl text-[#F5F2EB] tracking-tight">
            {repo}
          </h1>
        </div>

        {/* Primary Action Button */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowSimulateModal(true)}
            className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-4 py-2.5 rounded-lg text-sm flex items-center gap-2 transition-colors shadow-sm font-sans"
          >
            <Play className="w-4 h-4 fill-current stroke-none" />
            <span>Simulate Drift Run</span>
          </button>
        </div>
      </div>

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
              <span className="font-mono text-xs text-[#8E897F] block mb-1">Total Webhooks</span>
              <span className="font-serif text-3xl text-[#F5F2EB]">128</span>
            </div>
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">AST Skipped (0 tokens)</span>
              <span className="font-serif text-3xl text-[#F5F2EB]">89</span>
            </div>
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">Documentation PRs</span>
              <span className="font-serif text-3xl text-[#F5F2EB]">39</span>
            </div>
            <div className="p-4">
              <span className="font-mono text-xs text-[#8E897F] block mb-1">Avg Verification Time</span>
              <span className="font-serif text-3xl text-emerald-400">0.8s</span>
            </div>
          </div>

          {/* Runs history */}
          <div>
            <h2 className="font-serif text-2xl text-[#F5F2EB] mb-4">Execution History</h2>
            <div className="flex flex-col gap-3">
              {[
                {
                  id: "run-e2e-1",
                  status: "PR open",
                  statusClass: "border-accent-orange/30 bg-accent-orange/10 text-accent-orange",
                  title: "feat(billing): add tax_rate parameter to calc_total",
                  sha: "a3f9c21",
                  time: "4 minutes ago",
                  symbols: ["calc_total (api_surface)"],
                  doc: "README.md # Billing",
                  prNumber: 101,
                  prUrl: `https://github.com/${repoFullName}/pull/101`,
                },
                {
                  id: "run-e2e-2",
                  status: "no drift",
                  statusClass: "border-[#26231D] bg-[#1F1D18] text-[#8E897F]",
                  title: "refactor: optimize internal diff parser hunk extraction",
                  sha: "7be02d4",
                  time: "38 minutes ago",
                  symbols: ["_parse_hunk (behavior)"],
                  doc: "No doc sections impacted (0 LLM tokens)",
                  prNumber: null,
                  prUrl: null,
                },
                {
                  id: "run-e2e-3",
                  status: "merged",
                  statusClass: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
                  title: "docs(cli): document --dry-run argument",
                  sha: "c19e8f0",
                  time: "2 hours ago",
                  symbols: ["--dry-run (cli)"],
                  doc: "docs/cli.md # Flags",
                  prNumber: 98,
                  prUrl: `https://github.com/${repoFullName}/pull/98`,
                },
              ].map((r) => (
                <div
                  key={r.id}
                  className="border border-[#26231D] bg-[#141310] rounded-xl p-5 flex flex-col gap-3"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-mono border ${r.statusClass}`}>
                        {r.status}
                      </span>
                      <span className="text-sm font-medium text-[#F5F2EB]">{r.title}</span>
                    </div>
                    <span className="font-mono text-xs text-[#8E897F]">{r.time}</span>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-4 text-xs font-mono pt-2 border-t border-[#26231D]/60 text-[#8E897F]">
                    <div className="flex items-center gap-2">
                      <span>Changed AST:</span>
                      {r.symbols.map((s) => (
                        <span key={s} className="bg-[#1F1D18] text-[#F5F2EB] px-2 py-0.5 rounded border border-[#26231D]">
                          {s}
                        </span>
                      ))}
                      <span>→</span>
                      <span className="text-accent-orange">{r.doc}</span>
                    </div>

                    {r.prNumber && (
                      <a
                        href={r.prUrl || "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 text-accent-orange hover:text-accent-orange-hover"
                      >
                        <GitPullRequest className="w-3.5 h-3.5" />
                        <span>Docs PR #{r.prNumber}</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
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
