import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Logo } from "../components/common/Logo";
import { ArrowRight } from "lucide-react";

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeStage, setActiveStage] = useState<number | null>(null);

  const pipelineStages = [
    {
      num: "01",
      title: "Ingest",
      subtitle: "webhook verified · HMAC ok",
      detail: "X-Hub-Signature-256 HMAC verified against GITHUB_WEBHOOK_SECRET. X-GitHub-Delivery deduplicated in SQLite.",
    },
    {
      num: "02",
      title: "Change analyzer",
      subtitle: "tree-sitter · 0 tokens",
      detail: "Tree-sitter AST extracts changed functions, classes, routes, and CLI flags. Zero LLM tokens spent.",
    },
    {
      num: "03",
      title: "Drift engine",
      subtitle: "2 doc sections hit",
      detail: "Intersects AST symbols with markdown-it-py doc anchors & code blocks. Early-exit if 0 sections impacted.",
    },
    {
      num: "04",
      title: "Planner → Writer",
      subtitle: "LangGraph",
      detail: "StateGraph drafts section edit plans and splices surgical markdown updates preserving surrounding prose.",
    },
    {
      num: "05",
      title: "Verifier",
      subtitle: "links · fences · syntax",
      detail: "Deterministic AST validation checks backtick fences, target symbols presence, and broken links with auto-repair loop.",
    },
    {
      num: "06",
      title: "Publish PR",
      subtitle: "evidence table attached",
      detail: "Opens GitHub documentation PR with verified Markdown Evidence Table mapping symbol → section → verification status.",
    },
  ];

  return (
    <div className="min-h-screen bg-canvas text-primary selection:bg-accent-orange selection:text-black flex flex-col justify-between">
      {/* Top Navigation */}
      <header className="border-b border-[#26231D] bg-[#0D0C0A]/90 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Logo size="md" />

          <nav className="flex items-center gap-6">
            <Link
              to="/login"
              className="text-sm font-medium text-muted hover:text-primary transition-colors"
            >
              Sign in
            </Link>
            <button
              onClick={() => navigate("/login")}
              type="button"
              className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium text-sm px-4 py-2 rounded-lg transition-colors shadow-sm"
            >
              Get started
            </button>
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-6xl mx-auto px-6 pt-16 pb-24 flex-1 w-full">
        {/* Hero Section */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#26231D] bg-[#141310] text-xs font-mono text-muted mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-orange animate-pulse" />
            <span>Deterministic AST pre-filtering · Zero hallucinated PRs</span>
          </div>

          <h1 className="font-serif text-5xl sm:text-6xl md:text-7xl text-[#F5F2EB] tracking-tight leading-[1.08] mb-6">
            Documentation that updates itself with every pull request.
          </h1>

          <p className="text-base sm:text-lg text-muted max-w-2xl mx-auto mb-8 font-sans leading-relaxed">
            Tree-sitter AST analysis and drift matching before LangGraph. If no documented symbol moved, we stop. Zero LLM calls, zero wasted tokens.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => navigate("/login")}
              type="button"
              className="w-full sm:w-auto bg-[#F3EFE6] hover:bg-white text-[#141310] font-medium px-6 py-3.5 rounded-xl flex items-center justify-center gap-2.5 transition-all text-sm shadow-lg group"
            >
              <span>Continue with GitHub</span>
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
            </button>
            <button
              onClick={() => navigate("/activity")}
              type="button"
              className="w-full sm:w-auto border border-[#26231D] bg-[#141310] hover:bg-[#1F1D18] text-primary font-medium px-6 py-3.5 rounded-xl transition-colors text-sm"
            >
              Explore live activity
            </button>
          </div>
        </div>

        {/* Interactive 6-Stage Terminal Pipeline Card */}
        <div className="border border-[#26231D] bg-[#141310] rounded-2xl overflow-hidden shadow-2xl mb-24 transition-all">
          {/* Top Bar with Mac dots & git branch */}
          <div className="px-5 py-3.5 border-b border-[#26231D] flex items-center justify-between bg-[#0D0C0A]/60">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F56] inline-block" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#FFBD2E] inline-block" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#27C93F] inline-block" />
            </div>
            <div className="font-mono text-xs text-muted flex items-center gap-1.5">
              <span>push →</span>
              <span className="text-primary font-medium">sujalgawas/DocRipple</span>
              <span className="text-accent-orange">@a3f9c21</span>
            </div>
            <div className="w-12 hidden sm:block" />
          </div>

          {/* 6 Equal-Width Bordered Columns */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 divide-y lg:divide-y-0 lg:divide-x divide-[#26231D]">
            {pipelineStages.map((stage, idx) => {
              const isSelected = activeStage === idx;
              return (
                <div
                  key={stage.num}
                  onClick={() => setActiveStage(isSelected ? null : idx)}
                  className={`p-5 transition-colors cursor-pointer group flex flex-col justify-between ${
                    isSelected ? "bg-[#1F1D18]" : "hover:bg-[#1A1813]"
                  }`}
                >
                  <div>
                    <span className="font-mono text-xs text-muted block mb-2 group-hover:text-accent-orange transition-colors">
                      {stage.num}
                    </span>
                    <h2 className="text-sm font-medium text-[#F5F2EB] mb-1.5 leading-snug">
                      {stage.title}
                    </h2>
                  </div>
                  <p className="font-mono text-[11px] text-[#8E897F] leading-relaxed mt-2">
                    {stage.subtitle}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Interactive Inspection Drawer */}
          {activeStage !== null && (
            <div className="p-4 border-t border-[#26231D] bg-[#12110E] flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-2 text-primary">
                <span className="text-accent-orange font-bold">
                  Stage {pipelineStages[activeStage].num}:
                </span>
                <span>{pipelineStages[activeStage].detail}</span>
              </div>
              <button
                onClick={() => setActiveStage(null)}
                className="text-muted hover:text-primary text-[11px] underline ml-4 shrink-0"
              >
                Close
              </button>
            </div>
          )}
        </div>

        {/* 3-Column Value Proposition Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10 md:gap-12 mb-28">
          {/* Column 1: Connect once */}
          <div className="flex flex-col gap-4">
            <div className="w-9 h-9 rounded-lg border border-[#26231D] bg-[#141310] flex items-center justify-center text-accent-orange">
              {/* Custom connector icon —o— */}
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="12" x2="8" y2="12" />
                <circle cx="12" cy="12" r="3" />
                <line x1="16" y1="12" x2="21" y2="12" />
              </svg>
            </div>
            <h2 className="font-serif text-3xl text-[#F5F2EB] tracking-tight">
              Connect once
            </h2>
            <p className="font-sans text-sm text-[#8E897F] leading-relaxed">
              Install the GitHub app, pick repos. We listen for pushes and PRs — nothing else.
            </p>
          </div>

          {/* Column 2: Diff, not vibes */}
          <div className="flex flex-col gap-4">
            <div className="w-9 h-9 rounded-lg border border-[#26231D] bg-[#141310] flex items-center justify-center text-accent-orange">
              {/* Custom scan target icon [•] */}
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 8V5a1 1 0 0 1 1-1h3" />
                <path d="M16 4h3a1 1 0 0 1 1 1v3" />
                <path d="M20 16v3a1 1 0 0 1-1 1h-3" />
                <path d="M8 20H5a1 1 0 0 1-1-1v-3" />
                <circle cx="12" cy="12" r="2" fill="currentColor" />
              </svg>
            </div>
            <h2 className="font-serif text-3xl text-[#F5F2EB] tracking-tight">
              Diff, not vibes
            </h2>
            <p className="font-sans text-sm text-[#8E897F] leading-relaxed">
              Tree-sitter reads the AST. If no documented symbol moved, we stop. No LLM, no bill.
            </p>
          </div>

          {/* Column 3: PRs you can trust */}
          <div className="flex flex-col gap-4">
            <div className="w-9 h-9 rounded-lg border border-[#26231D] bg-[#141310] flex items-center justify-center text-accent-orange">
              {/* Shield with check */}
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
            </div>
            <h2 className="font-serif text-3xl text-[#F5F2EB] tracking-tight">
              PRs you can trust
            </h2>
            <p className="font-sans text-sm text-[#8E897F] leading-relaxed">
              Every PR ships an evidence table: which symbol changed, which section was touched, and why.
            </p>
          </div>
        </div>

        {/* Bottom Cream Callout Banner */}
        <div className="bg-[#F3EFE6] text-[#141310] rounded-2xl p-10 sm:p-14 relative overflow-hidden shadow-2xl flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
          {/* Decorative Wavy Curves SVG Pattern (Matches reference) */}
          <div className="absolute -top-10 -right-10 w-64 h-64 pointer-events-none opacity-40">
            <svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full stroke-[#141310]">
              <path d="M10 30 Q 50 10, 90 30 T 170 30 T 250 30" strokeWidth="4" strokeLinecap="round" />
              <path d="M10 60 Q 50 40, 90 60 T 170 60 T 250 60" strokeWidth="4" strokeLinecap="round" />
              <path d="M10 90 Q 50 70, 90 90 T 170 90 T 250 90" strokeWidth="4" strokeLinecap="round" />
              <path d="M10 120 Q 50 100, 90 120 T 170 120 T 250 120" strokeWidth="4" strokeLinecap="round" />
            </svg>
          </div>

          <div className="max-w-xl relative z-10">
            <h2 className="font-serif text-4xl sm:text-5xl text-[#141310] tracking-tight leading-tight mb-3">
              Stop writing &ldquo;update docs&rdquo; commits.
            </h2>
            <p className="font-sans text-sm sm:text-base text-[#141310]/75 leading-relaxed">
              Let DocRipple monitor pushes, compute AST drift, and open surgical documentation pull requests with full audit evidence.
            </p>
          </div>

          <div className="relative z-10 shrink-0">
            <button
              onClick={() => navigate("/login")}
              type="button"
              className="bg-[#141310] hover:bg-black text-[#F5F2EB] font-medium px-7 py-4 rounded-xl flex items-center gap-2.5 transition-all text-sm shadow-md group"
            >
              <span>Connect GitHub</span>
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1 text-accent-orange" />
            </button>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-[#26231D] py-8 bg-[#0D0C0A]">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs font-mono text-muted">
          <div className="flex items-center gap-3">
            <Logo size="sm" />
            <span>·</span>
            <span>Self-Updating GitHub Documentation Agent</span>
          </div>
          <div>
            Built with FastAPI, Tree-sitter, LangGraph & React.
          </div>
        </div>
      </footer>
    </div>
  );
};
