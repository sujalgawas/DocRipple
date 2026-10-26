import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Logo } from "../components/common/Logo";
import { Check, Loader2, AlertCircle, ArrowRight, ShieldCheck } from "lucide-react";
import { API_BASE, getAuthMe, githubLoginUrl } from "../services/api";
import type { AuthMe } from "../services/api";

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();

  const [me, setMe] = useState<AuthMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getAuthMe()
      .then((data) => {
        if (active) setMe(data);
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Backend unreachable");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const handleGitHubAuth = () => {
    // Direct browser straight to GitHub OAuth login
    window.location.href = githubLoginUrl();
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
        <div className="max-w-md w-full my-auto py-12">
          <h1 className="font-serif text-5xl sm:text-6xl text-[#F5F2EB] tracking-tight mb-3">
            Welcome back.
          </h1>
          <p className="text-muted text-base mb-6">
            One click. We only ask GitHub for what we need.
          </p>

          {/* Already Connected Banner */}
          {me?.connected ? (
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
          ) : (
            <>
              {/* Connection status note */}
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

              {/* Direct GitHub OAuth Button */}
              <button
                onClick={handleGitHubAuth}
                type="button"
                className="w-full bg-[#F3EFE6] hover:bg-white text-[#141310] font-medium py-3.5 px-4 rounded-xl flex items-center justify-center gap-2.5 transition-all text-sm shadow-lg hover:shadow-xl mb-8 group active:scale-[0.99]"
              >
                {/* GitHub Octocat SVG */}
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
              </button>
            </>
          )}

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
