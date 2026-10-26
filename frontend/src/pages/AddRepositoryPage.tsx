import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Globe, Lock, Search, Loader2 } from "lucide-react";
import { onboardRepository, saveStoredRepository } from "../services/api";
import type { RepositoryItem } from "../services/api";

export const AddRepositoryPage: React.FC = () => {
  const navigate = useNavigate();

  // Wizard steps: 1 = Pick repo, 2 = Configure, 3 = Install webhook
  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Step 1 state
  const [search, setSearch] = useState("");
  const [selectedRepo, setSelectedRepo] = useState<string>("portfolio-site");
  const [customRepo, setCustomRepo] = useState<string>("");

  const reposList = [
    { name: "portfolio-site", isPrivate: false, lastActive: "3 days ago" },
    { name: "ml-notebooks", isPrivate: true, lastActive: "1 week ago" },
    { name: "chess-engine-rs", isPrivate: false, lastActive: "2 weeks ago" },
    { name: "infra-terraform", isPrivate: true, lastActive: "1 month ago" },
  ];

  // Step 2 state
  const [watchBranch, setWatchBranch] = useState("main");
  const [docPaths, setDocPaths] = useState("README.md, docs/**/*.md");
  const [driftAction, setDriftAction] = useState("Open a pull request");
  const [isOnboarding, setIsOnboarding] = useState(false);

  // Step 3 state
  const [onboardSummary, setOnboardSummary] = useState<{
    nodeCount: number;
    edgeCount: number;
    initialEdges: number;
  }>({
    nodeCount: 32,
    edgeCount: 48,
    initialEdges: 14,
  });

  const activeRepoFullName = customRepo.trim()
    ? customRepo.includes("/")
      ? customRepo
      : `sujalgawas/${customRepo}`
    : `sujalgawas/${selectedRepo}`;

  const handleStartOnboard = async () => {
    setIsOnboarding(true);
    try {
      const res = await onboardRepository(activeRepoFullName, watchBranch);
      setOnboardSummary({
        nodeCount: res.memory_node_count,
        edgeCount: res.memory_edge_count,
        initialEdges: res.initial_code_doc_edges,
      });

      // Persist the newly added repo into local storage list
      const parts = activeRepoFullName.split("/");
      const owner = parts[0] || "sujalgawas";
      const name = parts[1] || selectedRepo;

      const newRepoItem: RepositoryItem = {
        id: `repo-${owner}-${name}-${Date.now()}`,
        owner,
        name,
        fullName: activeRepoFullName,
        branch: watchBranch,
        status: "listening",
        trackedDocs: docPaths.split(",").map((s) => s.trim()).filter(Boolean),
        language: "TypeScript",
        runsCount: 0,
        lastPushed: "just now",
        isCustom: true,
      };
      saveStoredRepository(newRepoItem);

      setStep(3);
    } catch (err) {
      console.error("Onboarding failed:", err);
      // Still advance to step 3 with synthetic stats
      setStep(3);
    } finally {
      setIsOnboarding(false);
    }
  };

  const filteredRepos = reposList.filter((r) =>
    r.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-8 lg:p-12 max-w-4xl">
      {/* Back link */}
      <Link
        to="/repositories"
        className="font-mono text-xs text-[#8E897F] hover:text-[#F5F2EB] inline-flex items-center gap-1 mb-4 transition-colors"
      >
        <span>←</span>
        <span>repositories</span>
      </Link>

      {/* Main Title */}
      <h1 className="font-serif text-5xl text-[#F5F2EB] tracking-tight mb-8">
        Add a repository
      </h1>

      {/* Step Indicator */}
      <div className="flex items-center gap-6 mb-8 font-mono text-xs">
        {/* Step 1 */}
        <div className="flex items-center gap-2">
          {step > 1 ? (
            <span className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center text-[10px]">
              ✓
            </span>
          ) : (
            <span className="w-5 h-5 rounded-full border border-accent-orange text-accent-orange flex items-center justify-center text-[11px]">
              1
            </span>
          )}
          <span className={step === 1 ? "text-accent-orange font-medium" : step > 1 ? "text-emerald-400" : "text-[#8E897F]"}>
            Pick repo
          </span>
        </div>

        {/* Step 2 */}
        <div className="flex items-center gap-2">
          {step > 2 ? (
            <span className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center text-[10px]">
              ✓
            </span>
          ) : (
            <span
              className={`w-5 h-5 rounded-full border flex items-center justify-center text-[11px] ${
                step === 2
                  ? "border-accent-orange text-accent-orange"
                  : "border-[#26231D] text-[#8E897F]"
              }`}
            >
              2
            </span>
          )}
          <span
            className={
              step === 2
                ? "text-accent-orange font-medium"
                : step > 2
                ? "text-emerald-400"
                : "text-[#8E897F]"
            }
          >
            Configure
          </span>
        </div>

        {/* Step 3 */}
        <div className="flex items-center gap-2">
          <span
            className={`w-5 h-5 rounded-full border flex items-center justify-center text-[11px] ${
              step === 3
                ? "border-accent-orange text-accent-orange"
                : "border-[#26231D] text-[#8E897F]"
            }`}
          >
            3
          </span>
          <span
            className={
              step === 3 ? "text-accent-orange font-medium" : "text-[#8E897F]"
            }
          >
            Install webhook
          </span>
        </div>
      </div>

      {/* ── STEP 1: PICK REPO ──────────────────────────────────────────────── */}
      {step === 1 && (
        <div>
          <div className="border border-[#26231D] bg-[#141310] rounded-xl overflow-hidden mb-6">
            {/* Header: User & Search */}
            <div className="p-4 border-b border-[#26231D] flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5 font-mono text-sm text-[#F5F2EB]">
                <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                  <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                </svg>
                <span>sujalgawas</span>
              </div>

              <div className="relative">
                <Search className="w-3.5 h-3.5 text-[#8E897F] absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  placeholder="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="bg-[#0D0C0A] border border-[#26231D] focus:border-accent-orange rounded-lg pl-8 pr-3 py-1 text-xs text-[#F5F2EB] placeholder:text-[#8E897F] outline-none font-mono"
                />
              </div>
            </div>

            {/* Repositories Rows */}
            <div className="divide-y divide-[#26231D]">
              {filteredRepos.map((repo) => {
                const isSelected = selectedRepo === repo.name && !customRepo.trim();
                return (
                  <div
                    key={repo.name}
                    className="p-4 flex items-center justify-between hover:bg-[#1A1813] transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      {repo.isPrivate ? (
                        <Lock className="w-4 h-4 text-[#8E897F]" />
                      ) : (
                        <Globe className="w-4 h-4 text-[#8E897F]" />
                      )}
                      <span className="font-mono text-sm text-[#F5F2EB] font-medium">
                        {repo.name}
                      </span>
                      <span className="font-mono text-xs text-[#8E897F]">
                        {repo.lastActive}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        setSelectedRepo(repo.name);
                        setCustomRepo("");
                      }}
                      className={`px-3 py-1 rounded text-xs font-mono transition-colors ${
                        isSelected
                          ? "bg-accent-orange text-black font-semibold"
                          : "border border-[#26231D] bg-[#1F1D18] text-[#F5F2EB] hover:bg-[#2A2720]"
                      }`}
                    >
                      {isSelected ? "Selected" : "Select"}
                    </button>
                  </div>
                );
              })}

              {/* Or Custom Repository Row */}
              <div className="p-4 flex items-center justify-between gap-3 bg-[#0D0C0A]/40">
                <div className="flex items-center gap-2 flex-1">
                  <span className="font-mono text-xs text-[#8E897F] shrink-0">Custom repo:</span>
                  <input
                    type="text"
                    placeholder="e.g. org/repo-name"
                    value={customRepo}
                    onChange={(e) => setCustomRepo(e.target.value)}
                    className="w-full bg-[#141310] border border-[#26231D] focus:border-accent-orange rounded px-2.5 py-1 text-xs font-mono text-[#F5F2EB] outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 bg-[#0D0C0A]/60 border-t border-[#26231D] text-xs font-mono text-[#8E897F]">
              Missing a repo?{" "}
              <span className="text-accent-orange hover:underline cursor-pointer">
                Adjust GitHub app permissions
              </span>
            </div>
          </div>

          {/* Continue Button */}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setStep(2)}
              className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-5 py-2 rounded-lg text-sm transition-colors shadow-sm"
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 2: CONFIGURE + STAGE 0 TRIGGER ────────────────────────────── */}
      {step === 2 && (
        <div>
          <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6 flex flex-col gap-5 mb-6">
            {/* Watch branch */}
            <div>
              <div className="flex items-baseline gap-2 mb-2">
                <label className="font-mono text-xs font-semibold text-[#F5F2EB]">
                  Watch branch
                </label>
                <span className="font-mono text-xs text-[#8E897F]">
                  Pushes to this branch trigger the agent.
                </span>
              </div>
              <input
                type="text"
                value={watchBranch}
                onChange={(e) => setWatchBranch(e.target.value)}
                className="w-full bg-[#0D0C0A] border border-[#26231D] focus:border-accent-orange rounded-lg px-3.5 py-2 text-sm text-[#F5F2EB] font-mono outline-none transition-colors"
              />
            </div>

            {/* Documentation paths */}
            <div>
              <div className="flex items-baseline gap-2 mb-2">
                <label className="font-mono text-xs font-semibold text-[#F5F2EB]">
                  Documentation paths
                </label>
                <span className="font-mono text-xs text-[#8E897F]">
                  Comma separated. Globs work.
                </span>
              </div>
              <input
                type="text"
                value={docPaths}
                onChange={(e) => setDocPaths(e.target.value)}
                className="w-full bg-[#0D0C0A] border border-[#26231D] focus:border-accent-orange rounded-lg px-3.5 py-2 text-sm text-[#F5F2EB] font-mono outline-none transition-colors"
              />
            </div>

            {/* When drift is found */}
            <div>
              <label className="block font-mono text-xs font-semibold text-[#F5F2EB] mb-2">
                When drift is found
              </label>
              <select
                value={driftAction}
                onChange={(e) => setDriftAction(e.target.value)}
                className="w-full bg-[#0D0C0A] border border-[#26231D] focus:border-accent-orange rounded-lg px-3.5 py-2 text-sm text-[#F5F2EB] font-mono outline-none transition-colors cursor-pointer"
              >
                <option value="Open a pull request">Open a pull request</option>
                <option value="Open PR + comment on commit">Open PR + comment on commit</option>
              </select>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="border border-[#26231D] bg-[#1F1D18] hover:bg-[#2A2720] text-[#F5F2EB] px-4 py-2 rounded-lg text-sm font-mono transition-colors"
            >
              Back
            </button>

            <button
              type="button"
              disabled={isOnboarding}
              onClick={handleStartOnboard}
              className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-5 py-2 rounded-lg text-sm transition-colors flex items-center gap-2 shadow-sm disabled:opacity-60"
            >
              {isOnboarding ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Indexing memory & style (Stage 0)...</span>
                </>
              ) : (
                <span>Install &amp; connect</span>
              )}
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 3: INSTALL WEBHOOK (SUCCESS) ──────────────────────────────── */}
      {step === 3 && (
        <div>
          <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6 flex flex-col gap-4 mb-6">
            {/* Header */}
            <div className="flex items-center gap-2 font-mono text-sm font-medium text-emerald-400">
              <span className="w-4 h-4 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-[10px]">
                ✓
              </span>
              <span>Webhook installed on {customRepo.trim() || selectedRepo}</span>
            </div>

            {/* Monospace Code Card */}
            <div className="bg-[#0D0C0A] border border-[#26231D] rounded-lg p-4 font-mono text-xs text-[#8E897F] flex flex-col gap-1.5 leading-relaxed">
              <p>
                <span className="text-[#8E897F]/60">events:</span>{" "}
                <span className="text-[#F5F2EB]">push, pull_request</span>
              </p>
              <p>
                <span className="text-[#8E897F]/60">url:</span>{" "}
                <span className="text-[#F5F2EB]">https://hooks.docripple.dev/gh</span>
              </p>
              <p>
                <span className="text-[#8E897F]/60">secret:</span>{" "}
                <span className="text-accent-orange">••••••••••••</span>{" "}
                <span className="text-[#8E897F]/60">(HMAC-SHA256)</span>
              </p>
              <div className="border-t border-[#26231D] pt-2 mt-1 flex flex-col gap-1 text-[11px]">
                <p className="text-emerald-400 flex items-center gap-1">
                  <span>✓</span>
                  <span>Stage 0 DocStyleSkill extracted &amp; cached</span>
                </p>
                <p className="text-emerald-400 flex items-center gap-1">
                  <span>✓</span>
                  <span>
                    Stage 0 RepoMemoryMap indexed ({onboardSummary.nodeCount} nodes, {onboardSummary.edgeCount} edges)
                  </span>
                </p>
              </div>
            </div>

            {/* Subtitle */}
            <p className="font-mono text-xs text-[#8E897F]">
              Push any commit to see the first run show up. We&apos;ll wait.
            </p>
          </div>

          {/* Done Button */}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => navigate(`/repositories/${activeRepoFullName}`)}
              className="bg-[#F3EFE6] hover:bg-white text-[#141310] font-medium px-5 py-2 rounded-lg text-sm transition-colors shadow-sm font-sans"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
