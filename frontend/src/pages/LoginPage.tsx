import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Logo } from "../components/common/Logo";
import {
  Check,
  Loader2,
  AlertCircle,
  Key,
  ExternalLink,
  ArrowRight,
  ShieldCheck,
  ChevronUp,
} from "lucide-react";
import {
  API_BASE,
  getAuthMe,
  getAuthConfig,
  githubLoginUrl,
  loginWithToken,
  saveOAuthConfig,
} from "../services/api";
import type { AuthMe, AuthConfig } from "../services/api";

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [me, setMe] = useState<AuthMe | null>(null);
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // PAT input state
  const [tokenInput, setTokenInput] = useState("");
  const [connectingToken, setConnectingToken] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);

  // OAuth Config modal/drawer state
  const [showOAuthConfig, setShowOAuthConfig] = useState(false);
  const [clientIdInput, setClientIdInput] = useState("");
  const [clientSecretInput, setClientSecretInput] = useState("");
  const [savingOAuth, setSavingOAuth] = useState(false);
  const [oauthError, setOauthError] = useState<string | null>(null);

  // Check URL params for error
  const urlError = searchParams.get("error");

  const loadAuthStatus = async () => {
    try {
      const [meData, configData] = await Promise.all([
        getAuthMe().catch(() => null),
        getAuthConfig().catch(() => null),
      ]);
      if (meData) setMe(meData);
      if (configData) {
        setAuthConfig(configData);
        if (configData.client_id) {
          setClientIdInput(configData.client_id);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backend unreachable");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAuthStatus();
  }, []);

  const handleGitHubAuth = () => {
    // If OAuth is configured, redirect to GitHub authorization page
    if (authConfig?.oauth_configured) {
      window.location.href = githubLoginUrl();
      return;
    }

    // If OAuth is not configured, reveal the setup panel
    setShowOAuthConfig(true);
  };

  const handleConnectToken = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = tokenInput.trim();
    if (!token) {
      setTokenError("Please enter your GitHub Personal Access Token.");
      return;
    }

    setConnectingToken(true);
    setTokenError(null);
    try {
      const updatedUser = await loginWithToken(token);
      setMe(updatedUser);
      // Directly proceed to pick repositories from GitHub
      navigate("/repositories/new");
    } catch (err) {
      setTokenError(
        err instanceof Error
          ? err.message
          : "Invalid token. Ensure it has 'repo' scope."
      );
    } finally {
      setConnectingToken(false);
    }
  };

  const handleSaveOAuthAndLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!clientIdInput.trim() || !clientSecretInput.trim()) {
      setOauthError("Both Client ID and Client Secret are required.");
      return;
    }

    setSavingOAuth(true);
    setOauthError(null);
    try {
      await saveOAuthConfig(clientIdInput.trim(), clientSecretInput.trim());
      // Redirect to GitHub authorization screen
      window.location.href = githubLoginUrl();
    } catch (err) {
      setOauthError(
        err instanceof Error ? err.message : "Failed to save OAuth config."
      );
      setSavingOAuth(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas text-primary flex flex-col lg:flex-row selection:bg-accent-orange selection:text-black">
      {/* Left Column - Authentication Form */}
      <div className="w-full lg:w-1/2 p-8 sm:p-12 lg:p-16 flex flex-col justify-between min-h-screen border-b lg:border-b-0 lg:border-r border-[#26231D] bg-[#0D0C0A]">
        {/* Top: Brand Logo */}
        <div className="pt-2">
          <Logo size="md" />
        </div>

        {/* Center: Auth Action */}
        <div className="max-w-md w-full my-auto py-10">
          <h1 className="font-serif text-5xl sm:text-6xl text-[#F5F2EB] tracking-tight mb-3">
            Welcome back.
          </h1>
          <p className="text-muted text-base mb-6">
            Connect your GitHub account to inspect repositories and detect documentation drift.
          </p>

          {/* URL Error Banner */}
          {urlError === "oauth_not_configured" && (
            <div className="mb-6 p-4 rounded-xl border border-amber-800/60 bg-amber-950/20 text-amber-200 text-xs leading-relaxed flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-amber-300">GitHub OAuth is not configured yet.</span>{" "}
                Enter your GitHub Personal Access Token below, or configure OAuth credentials.
              </div>
            </div>
          )}

          {/* Already Connected Banner */}
          {me?.connected && (
            <div className="mb-8 p-5 rounded-xl border border-emerald-800/40 bg-emerald-950/20 text-emerald-200">
              <div className="flex items-center gap-2 text-sm font-semibold text-emerald-300 mb-1">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                Connected as @{me.username}
              </div>
              <p className="text-xs text-muted mb-4 font-mono">
                {me.authorized_repos_count} repositories accessible.
              </p>
              <button
                type="button"
                onClick={() => navigate("/repositories/new")}
                className="w-full bg-accent-orange hover:bg-accent-orange-hover text-black font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2 text-sm transition-all shadow-md active:scale-[0.99]"
              >
                <span>Pick Repositories from GitHub</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Live connection status */}
          <div className="mb-6 font-mono text-xs min-h-[20px]">
            {loading ? (
              <span className="flex items-center gap-2 text-[#8E897F]">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Checking GitHub connection...
              </span>
            ) : error ? (
              <span className="flex items-start gap-2 text-red-400">
                <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>
                  Backend not reachable at {API_BASE}. Start it with{" "}
                  <code className="text-[#F5F2EB]">python run.py</code>.
                </span>
              </span>
            ) : null}
          </div>

          {/* 1. Primary GitHub OAuth Button */}
          <div className="mb-6">
            <button
              onClick={handleGitHubAuth}
              type="button"
              className="w-full bg-[#F3EFE6] hover:bg-white text-[#141310] font-medium py-3.5 px-4 rounded-xl flex items-center justify-center gap-2.5 transition-all text-sm shadow-lg hover:shadow-xl group active:scale-[0.99]"
            >
              <svg
                className="w-5 h-5 fill-current transition-transform group-hover:scale-105"
                viewBox="0 0 24 24"
              >
                <path
                  fillRule="evenodd"
                  clipRule="evenodd"
                  d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                />
              </svg>
              <span>Continue with GitHub</span>
              {authConfig?.oauth_configured && <ExternalLink className="w-4 h-4 ml-1 opacity-60" />}
            </button>
          </div>

          {/* OAuth Setup Panel (Toggles when not yet configured) */}
          {showOAuthConfig && (
            <div className="mb-6 border border-[#26231D] bg-[#141310] rounded-xl p-4 text-xs font-mono transition-all">
              <div className="flex items-center justify-between mb-3 text-[#F5F2EB] font-sans font-medium">
                <span>Configure GitHub OAuth App</span>
                <button
                  type="button"
                  onClick={() => setShowOAuthConfig(false)}
                  className="text-muted hover:text-white"
                >
                  <ChevronUp className="w-4 h-4" />
                </button>
              </div>

              <p className="text-muted text-[11px] mb-3 leading-relaxed">
                Set Authorization callback URL in GitHub Developer settings to:
                <br />
                <code className="text-accent-orange font-semibold select-all">
                  http://localhost:8000/api/v1/auth/github/callback
                </code>
              </p>

              {oauthError && (
                <div className="mb-3 p-2 rounded bg-red-950/40 border border-red-800 text-red-300 text-[11px]">
                  {oauthError}
                </div>
              )}

              <form onSubmit={handleSaveOAuthAndLogin} className="flex flex-col gap-2.5">
                <div>
                  <label className="text-muted text-[10px] uppercase">Client ID</label>
                  <input
                    type="text"
                    value={clientIdInput}
                    onChange={(e) => setClientIdInput(e.target.value)}
                    placeholder="Iv1.xxxxxxxxxxxx"
                    className="w-full mt-1 bg-[#1F1D18] border border-[#26231D] rounded-lg px-3 py-2 text-primary focus:border-accent-orange focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-muted text-[10px] uppercase">Client Secret</label>
                  <input
                    type="password"
                    value={clientSecretInput}
                    onChange={(e) => setClientSecretInput(e.target.value)}
                    placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                    className="w-full mt-1 bg-[#1F1D18] border border-[#26231D] rounded-lg px-3 py-2 text-primary focus:border-accent-orange focus:outline-none"
                  />
                </div>
                <button
                  type="submit"
                  disabled={savingOAuth}
                  className="mt-2 w-full bg-accent-orange hover:bg-accent-orange-hover text-black font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 text-xs transition-colors"
                >
                  {savingOAuth ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Saving & Authorizing...
                    </>
                  ) : (
                    <>
                      <span>Save & Authorize with GitHub</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </>
                  )}
                </button>
              </form>
            </div>
          )}

          {/* Divider */}
          <div className="relative my-6 text-center">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-[#26231D]" />
            </div>
            <div className="relative inline-block bg-[#0D0C0A] px-3 font-mono text-xs text-[#8E897F]">
              or connect with Personal Access Token
            </div>
          </div>

          {/* 2. Direct Personal Access Token Form */}
          <form onSubmit={handleConnectToken} className="mb-8">
            <div className="border border-[#26231D] bg-[#141310] rounded-xl p-4">
              <label className="block text-xs font-medium text-[#F5F2EB] mb-1.5 flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-accent-orange" />
                <span>GitHub Personal Access Token (PAT)</span>
              </label>
              <p className="text-[11px] text-[#8E897F] mb-3">
                Classic token with <code className="text-[#F5F2EB]">repo</code> scope, or fine-grained token with contents/PR write access.
              </p>

              {tokenError && (
                <div className="mb-3 p-2.5 rounded-lg bg-red-950/40 border border-red-800 text-red-300 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
                  <span>{tokenError}</span>
                </div>
              )}

              <div className="flex gap-2">
                <input
                  type="password"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                  className="flex-1 bg-[#1F1D18] border border-[#26231D] rounded-lg px-3 py-2 text-sm text-[#F5F2EB] font-mono placeholder:text-[#8E897F]/50 focus:border-accent-orange focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={connectingToken}
                  className="bg-[#F3EFE6] hover:bg-white text-[#141310] font-medium px-4 py-2 rounded-lg text-xs font-mono flex items-center gap-1.5 transition-colors shrink-0 disabled:opacity-50"
                >
                  {connectingToken ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Checking...
                    </>
                  ) : (
                    <span>Connect</span>
                  )}
                </button>
              </div>

              <div className="mt-3 text-right">
                <a
                  href="https://github.com/settings/tokens/new?scopes=repo,read:user"
                  target="_blank"
                  rel="noreferrer"
                  className="text-[11px] text-accent-orange hover:underline inline-flex items-center gap-1 font-mono"
                >
                  Generate a token on GitHub <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          </form>

          {/* Scopes & Permissions Checkmarks */}
          <div className="flex flex-col gap-3 font-mono text-xs text-[#8E897F]">
            <div className="flex items-center gap-2.5">
              <Check className="w-4 h-4 text-emerald-400 shrink-0" strokeWidth={2.5} />
              <span>Read access to code & metadata</span>
            </div>
            <div className="flex items-center gap-2.5">
              <Check className="w-4 h-4 text-emerald-400 shrink-0" strokeWidth={2.5} />
              <span>Write access to pull requests only</span>
            </div>
            <div className="flex items-center gap-2.5">
              <Check className="w-4 h-4 text-emerald-400 shrink-0" strokeWidth={2.5} />
              <span>Webhooks for push and pull_request</span>
            </div>
          </div>
        </div>

        {/* Bottom Footer Text */}
        <div className="pb-2">
          <p className="font-mono text-xs text-[#8E897F]/70">
            By continuing you agree to not let your docs rot.
          </p>
        </div>
      </div>

      {/* Right Column - Dot Grid with Interactive Tilted Card & Quote */}
      <div className="w-full lg:w-1/2 bg-dot-grid p-8 sm:p-12 lg:p-16 flex flex-col justify-between min-h-screen relative overflow-hidden">
        {/* Subtle decorative glow */}
        <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-accent-orange/5 rounded-full blur-3xl pointer-events-none" />

        {/* Top spacer */}
        <div className="hidden lg:block" />

        {/* Center: Slightly Tilted Cream Card */}
        <div className="my-auto py-12 flex items-center justify-center">
          <div className="w-full max-w-md transform -rotate-1 hover:rotate-0 transition-transform duration-300 ease-out">
            <div className="bg-[#F3EFE6] text-[#141310] rounded-xl p-6 shadow-2xl font-mono text-xs sm:text-sm border border-[#E3DEC5]">
              {/* Header */}
              <div className="text-[#8E897F] text-xs mb-4 flex items-center gap-2">
                <span>docs/cli.md</span>
                <span>·</span>
                <span>suggested by docripple</span>
              </div>

              {/* Title */}
              <div className="font-semibold text-sm mb-3 text-[#141310]">
                ## Flags
              </div>

              {/* Diff lines */}
              <div className="flex flex-col gap-1.5 mb-5">
                <div className="bg-red-500/15 text-red-700 px-2 py-1 rounded line-through select-none">
                  - --verbose print debug output
                </div>
                <div className="bg-emerald-500/15 text-emerald-900 px-2 py-1 rounded">
                  + --dry-run analyze without opening a PR
                </div>
                <div className="bg-emerald-500/15 text-emerald-900 px-2 py-1 rounded">
                  + --verbose print pipeline trace
                </div>
              </div>

              {/* Divider & Footer */}
              <div className="border-t border-[#141310]/10 pt-3 text-xs text-[#141310]/80">
                evidence: <span className="font-semibold">cli.--dry-run</span> added in{" "}
                <span className="text-[#8E897F]">a3f9c21</span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Quote */}
        <div className="pb-2">
          <blockquote className="font-serif italic text-2xl sm:text-3xl text-[#F5F2EB] tracking-tight leading-snug max-w-lg">
            &ldquo;Finally, a bot that edits three lines instead of thirty.&rdquo;
          </blockquote>
        </div>
      </div>
    </div>
  );
};
