import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Globe,
  Lock,
  Search,
  Loader2,
  AlertCircle,
  GitBranch,
  CheckCircle2,
} from "lucide-react";
import { connectRepository, getGitHubRepos } from "../services/api";
import type {
  ConnectRepoResponse,
  GitHubRepoSummary,
} from "../services/api";

type Step = 1 | 2 | 3;

function shortDate(value?: string | null): string {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export const AddRepositoryPage: React.FC = () => {
  const navigate = useNavigate();

  // Wizard steps: 1 = Pick repo, 2 = Configure, 3 = Connected
  const [step, setStep] = useState<Step>(1);

  // Step 1 state
  const [repos, setRepos] = useState<GitHubRepoSummary[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(true);
  const [reposError, setReposError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedRepo, setSelectedRepo] = useState<GitHubRepoSummary | null>(
    null
  );
  const [customRepo, setCustomRepo] = useState("");

  // Step 2 state
  const [watchBranch, setWatchBranch] = useState("main");
  const [docPaths, setDocPaths] = useState("README.md, docs/**/*.md");
  const [driftAction, setDriftAction] = useState("Open a pull request");
  const [analyzeLatest, setAnalyzeLatest] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  // Step 3 state
  const [result, setResult] = useState<ConnectRepoResponse | null>(null);

  const loadRepos = useCallback(async () => {
    setLoadingRepos(true);
    setReposError(null);
    try {
      setRepos(await getGitHubRepos());
    } catch (err) {
      setReposError(
        err instanceof Error ? err.message : "Could not load GitHub repositories"
      );
    } finally {
      setLoadingRepos(false);
    }
  }, []);

  useEffect(() => {
    void loadRepos();
  }, [loadRepos]);

  const activeRepoFullName = customRepo.trim() || selectedRepo?.full_name || "";
  const canContinue = activeRepoFullName.includes("/");

  const filteredRepos = repos.filter((repo) =>
    repo.full_name.toLowerCase().includes(search.toLowerCase())
  );

  const handleSelectRepo = (repo: GitHubRepoSummary) => {
    setSelectedRepo(repo);
    setCustomRepo("");
    setWatchBranch(repo.default_branch || "main");
  };

  const handleCustomRepoChange = (value: string) => {
    setCustomRepo(value);
    if (value.trim()) setSelectedRepo(null);
  };

  const handleContinue = () => {
    if (!canContinue) return;
    setConnectError(null);
    setStep(2);
  };

  const handleConnect = async () => {
    const repoFullName = activeRepoFullName.trim();
    if (!repoFullName.includes("/")) {
      setConnectError("Repository must be in owner/repo form.");
      return;
    }

    const paths = docPaths
      .split(",")
      .map((path) => path.trim())
      .filter(Boolean);

    setConnecting(true);
    setConnectError(null);
    try {
      const response = await connectRepository({
        repo_full_name: repoFullName,
        watch_branch: watchBranch.trim() || "main",
        doc_paths: paths.length > 0 ? paths : ["README.md", "docs/**/*.md"],
        drift_action: driftAction,
        analyze_latest: analyzeLatest,
      });
      setResult(response);
      setStep(3);
    } catch (err) {
      setConnectError(
        err instanceof Error ? err.message : "Could not connect repository"
      );
    } finally {
      setConnecting(false);
    }
  };

  const connectedFullName = result?.repo_full_name || activeRepoFullName;

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
          <span
            className={
              step === 1
                ? "text-accent-orange font-medium"
                : step > 1
                ? "text-emerald-400"
                : "text-[#8E897F]"
            }
          >
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
                ? "border-emerald-500/40 text-emerald-400"
                : "border-[#26231D] text-[#8E897F]"
            }`}
          >
            {step === 3 ? "✓" : "3"}
          </span>
          <span
            className={
              step === 3
                ? "text-emerald-400 font-medium"
                : "text-[#8E897F]"
            }
          >
            Connected
          </span>
        </div>
      </div>

      {/* ── STEP 1: PICK REPO ──────────────────────────────────────────────── */}
      {step === 1 && (
        <div>
          {reposError && (
            <div className="mb-4 border border-red-900/50 bg-red-950/20 text-red-300 rounded-xl px-4 py-3 text-sm flex items-start justify-between gap-3">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{reposError}</span>
              </div>
              <button
                type="button"
                onClick={() => void loadRepos()}
                className="font-mono text-xs underline hover:text-[#F5F2EB] shrink-0"
              >
                retry
              </button>
            </div>
          )}

          <div className="border border-[#26231D] bg-[#141310] rounded-xl overflow-hidden mb-6">
            {/* Header: Account & Search */}
            <div className="p-4 border-b border-[#26231D] flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5 font-mono text-sm text-[#F5F2EB]">
                <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                  <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                </svg>
                <span>GitHub repositories</span>
                <span className="text-[#8E897F]">
                  ({loadingRepos ? "…" : repos.length})
                </span>
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
            <div className="divide-y divide-[#26231D] max-h-[420px] overflow-y-auto">
              {loadingRepos ? (
                <div className="p-6 flex items-center gap-2 text-xs font-mono text-[#8E897F]">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Loading repositories from GitHub...</span>
                </div>
              ) : reposError ? (
                <div className="p-6 text-xs font-mono text-[#8E897F]">
                  Repository list unavailable. Fix the error above or enter an
                  owner/repo below.
                </div>
              ) : filteredRepos.length === 0 ? (
                <div className="p-6 text-xs font-mono text-[#8E897F]">
                  {repos.length === 0
                    ? "No repositories found for this GitHub token."
                    : "No repositories match your search."}
                </div>
              ) : (
                filteredRepos.map((repo) => {
                  const isSelected =
                    selectedRepo?.full_name === repo.full_name &&
                    !customRepo.trim();
                  return (
                    <div
                      key={repo.full_name}
                      className="p-4 flex items-center justify-between hover:bg-[#1A1813] transition-colors gap-4"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {repo.private ? (
                          <Lock className="w-4 h-4 text-[#8E897F] shrink-0" />
                        ) : (
                          <Globe className="w-4 h-4 text-[#8E897F] shrink-0" />
                        )}
                        <div className="min-w-0">
                          <div className="flex items-baseline gap-2">
                            <span className="font-mono text-sm text-[#F5F2EB] font-medium truncate">
                              {repo.full_name}
                            </span>
                            {repo.language && (
                              <span className="font-mono text-[10px] text-[#8E897F] border border-[#26231D] bg-[#0D0C0A] rounded px-1.5 py-0.5">
                                {repo.language}
                              </span>
                            )}
                          </div>
                          <p className="font-mono text-xs text-[#8E897F] mt-0.5">
                            <GitBranch className="w-3 h-3 inline mr-1" />
                            {repo.default_branch} · updated{" "}
                            {shortDate(repo.updated_at)}
                          </p>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleSelectRepo(repo)}
                        className={`px-3 py-1 rounded text-xs font-mono transition-colors shrink-0 ${
                          isSelected
                            ? "bg-accent-orange text-black font-semibold"
                            : "border border-[#26231D] bg-[#1F1D18] text-[#F5F2EB] hover:bg-[#2A2720]"
                        }`}
                      >
                        {isSelected ? "Selected" : "Select"}
                      </button>
                    </div>
                  );
                })
              )}

              {/* Or Custom Repository Row */}
              <div className="p-4 flex items-center justify-between gap-3 bg-[#0D0C0A]/40">
                <div className="flex items-center gap-2 flex-1">
                  <span className="font-mono text-xs text-[#8E897F] shrink-0">
                    Or owner/repo:
                  </span>
                  <input
                    type="text"
                    placeholder="e.g. org/repo-name"
                    value={customRepo}
                    onChange={(e) => handleCustomRepoChange(e.target.value)}
                    className="w-full bg-[#141310] border border-[#26231D] focus:border-accent-orange rounded px-2.5 py-1 text-xs font-mono text-[#F5F2EB] outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 bg-[#0D0C0A]/60 border-t border-[#26231D] text-xs font-mono text-[#8E897F]">
              Missing a repo? Adjust the token or GitHub App permissions to
              grant access.
            </div>
          </div>

          {/* Continue Button */}
          <div className="flex items-center justify-between">
            <p className="font-mono text-xs text-[#8E897F]">
              {activeRepoFullName
                ? `Selected: ${activeRepoFullName}`
                : "Select a repository to continue."}
            </p>
            <button
              type="button"
              disabled={!canContinue}
              onClick={handleContinue}
              className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-5 py-2 rounded-lg text-sm transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 2: CONFIGURE + CONNECT ────────────────────────────────────── */}
      {step === 2 && (
        <div>
          {connectError && (
            <div className="mb-4 border border-red-900/50 bg-red-950/20 text-red-300 rounded-xl px-4 py-3 text-sm flex items-start gap-2">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{connectError}</span>
            </div>
          )}

          <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6 flex flex-col gap-5 mb-6">
            {/* Selected repository */}
            <div className="flex items-center justify-between gap-3 pb-4 border-b border-[#26231D]">
              <div>
                <p className="font-mono text-xs text-[#8E897F] mb-1">
                  repository
                </p>
                <p className="font-mono text-sm text-[#F5F2EB]">
                  {activeRepoFullName}
                </p>
              </div>
              {selectedRepo && (
                <span className="font-mono text-[10px] text-[#8E897F] border border-[#26231D] bg-[#0D0C0A] rounded px-2 py-0.5">
                  {selectedRepo.language || "unknown language"}
                </span>
              )}
            </div>

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
                <option value="Open PR + comment on commit">
                  Open PR + comment on commit
                </option>
              </select>
            </div>

            {/* Analyze latest commit */}
            <label className="flex items-start gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={analyzeLatest}
                onChange={(e) => setAnalyzeLatest(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-[#F5A623]"
              />
              <span className="font-mono text-xs text-[#8E897F]">
                Analyze the latest commit now
                <span className="block mt-0.5 text-[#8E897F]/70">
                  Off: new commits are detected automatically from now on.
                </span>
              </span>
            </label>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setStep(1)}
              disabled={connecting}
              className="border border-[#26231D] bg-[#1F1D18] hover:bg-[#2A2720] text-[#F5F2EB] px-4 py-2 rounded-lg text-sm font-mono transition-colors disabled:opacity-50"
            >
              Back
            </button>

            <button
              type="button"
              disabled={connecting}
              onClick={() => void handleConnect()}
              className="bg-accent-orange hover:bg-accent-orange-hover text-black font-medium px-5 py-2 rounded-lg text-sm transition-colors flex items-center gap-2 shadow-sm disabled:opacity-60"
            >
              {connecting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Snapshotting, indexing &amp; connecting...</span>
                </>
              ) : (
                <span>Connect repository</span>
              )}
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 3: CONNECTED ──────────────────────────────────────────────── */}
      {step === 3 && result && (
        <div>
          <div className="border border-[#26231D] bg-[#141310] rounded-xl p-6 flex flex-col gap-4 mb-6">
            {/* Header */}
            <div className="flex items-center gap-2 font-mono text-sm font-medium text-emerald-400">
              <CheckCircle2 className="w-4 h-4" />
              <span>Connected {connectedFullName}</span>
            </div>

            {/* Monospace Code Card */}
            <div className="bg-[#0D0C0A] border border-[#26231D] rounded-lg p-4 font-mono text-xs text-[#8E897F] flex flex-col gap-2 leading-relaxed">
              <p>
                <span className="text-[#8E897F]/60">webhook:</span>{" "}
                <span
                  className={
                    result.webhook_url ? "text-[#F5F2EB]" : "text-amber-300"
                  }
                >
                  {result.webhook_url ? "installed" : "not installed"}
                </span>
                {result.webhook_url && (
                  <>
                    {" "}
                    <span className="text-[#8E897F]/60">· events:</span>{" "}
                    <span className="text-[#F5F2EB]">
                      push, pull_request
                    </span>
                  </>
                )}
              </p>
              <p className="break-all">
                <span className="text-[#8E897F]/60">url:</span>{" "}
                <span className="text-[#F5F2EB]">
                  {result.webhook_url ||
                    "Set PUBLIC_WEBHOOK_URL to a public HTTPS URL to enable push webhooks."}
                </span>
              </p>
              {result.webhook_error && (
                <p className="text-amber-300 break-words">
                  <span className="text-[#8E897F]/60">webhook error:</span>{" "}
                  {result.webhook_error}
                </p>
              )}
              <div className="border-t border-[#26231D] pt-2 mt-1 flex flex-col gap-1.5 text-[11px]">
                <p className="text-emerald-400 flex items-start gap-1">
                  <span>✓</span>
                  <span>
                    Stage 0 DocStyleSkill extracted &amp; cached
                    {result.style_skill_summary
                      ? ` — ${result.style_skill_summary}`
                      : ""}
                  </span>
                </p>
                <p className="text-emerald-400 flex items-start gap-1">
                  <span>✓</span>
                  <span>
                    Stage 0 RepoMemoryMap indexed (
                    {result.memory_nodes_count} nodes,{" "}
                    {result.memory_edges_count} edges)
                  </span>
                </p>
              </div>
            </div>

            {/* Subtitle */}
            <p className="font-mono text-xs text-[#8E897F]">
              {result.webhook_url
                ? "Push any commit to see the first run show up. You can also sync the latest commit manually."
                : "Webhooks are skipped for local URLs. Use “Sync latest commit” on the repository card to run the pipeline."}
            </p>
          </div>

          {/* Done Buttons */}
          <div className="flex items-center justify-end gap-3">
            <Link
              to="/repositories"
              className="border border-[#26231D] bg-[#1F1D18] hover:bg-[#2A2720] text-[#F5F2EB] px-4 py-2 rounded-lg text-sm font-mono transition-colors"
            >
              Back to repositories
            </Link>
            <button
              type="button"
              onClick={() => navigate(`/repositories/${connectedFullName}`)}
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
