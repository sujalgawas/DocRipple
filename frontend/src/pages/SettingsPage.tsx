import React, { useCallback, useEffect, useState } from "react";
import {
  Check,
  Loader2,
  AlertCircle,
  CheckCircle2,
  GitBranch,
} from "lucide-react";
import {
  disconnectGitHub,
  getAuthMe,
  getDashboard,
  getSettings,
  updateSettings,
} from "../services/api";
import type { AuthMe, MonitoredRepo, UserSettings } from "../services/api";

type ToggleKey =
  | "require_reviewer_approval"
  | "skip_internal_changes"
  | "email_on_failed_runs";

const TOGGLES: Array<{
  key: ToggleKey;
  label: string;
  description: string;
}> = [
  {
    key: "require_reviewer_approval",
    label: "Require reviewer approval",
    description: "Agent PRs need a human thumbs-up before merge.",
  },
  {
    key: "skip_internal_changes",
    label: "Skip internal-only changes",
    description: "Exit early when no public symbol changed.",
  },
  {
    key: "email_on_failed_runs",
    label: "Email me on failed runs",
    description: "One email, not a flood.",
  },
];

export const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [me, setMe] = useState<AuthMe | null>(null);
  const [repositories, setRepositories] = useState<MonitoredRepo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<ToggleKey | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);
  const [showManageModal, setShowManageModal] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [settingsResult, meResult, dashboardResult] = await Promise.allSettled(
      [getSettings(), getAuthMe(), getDashboard()]
    );

    const failures: string[] = [];

    if (settingsResult.status === "fulfilled") {
      setSettings(settingsResult.value);
    } else {
      failures.push(
        settingsResult.reason instanceof Error
          ? settingsResult.reason.message
          : "Could not load settings"
      );
    }

    if (meResult.status === "fulfilled") {
      setMe(meResult.value);
    } else {
      failures.push(
        meResult.reason instanceof Error
          ? meResult.reason.message
          : "Could not load GitHub identity"
      );
    }

    if (dashboardResult.status === "fulfilled") {
      setRepositories(dashboardResult.value.repositories);
    } else {
      failures.push(
        dashboardResult.reason instanceof Error
          ? dashboardResult.reason.message
          : "Could not load repositories"
      );
    }

    if (failures.length > 0) setError(failures[0]);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (key: ToggleKey) => {
    if (!settings || savingKey) return;

    const previous = settings;
    const next = !settings[key];
    setSavingKey(key);
    setError(null);
    setNotice(null);
    setSettings({ ...settings, [key]: next });

    try {
      const patch =
        key === "require_reviewer_approval"
          ? { require_reviewer_approval: next }
          : key === "skip_internal_changes"
          ? { skip_internal_changes: next }
          : { email_on_failed_runs: next };
      setSettings(await updateSettings(patch));
    } catch (err) {
      setSettings(previous);
      setError(
        err instanceof Error ? err.message : "Could not save the setting"
      );
    } finally {
      setSavingKey(null);
    }
  };

  const handleDisconnect = async () => {
    const confirmed = window.confirm(
      "Disconnect GitHub? This removes DocRipple webhooks and clears every monitored repository. Your docs stay as they are."
    );
    if (!confirmed) return;

    setDisconnecting(true);
    setError(null);
    setNotice(null);

    try {
      const response = await disconnectGitHub();
      setRepositories([]);
      setMe((current) =>
        current
          ? {
              ...current,
              connected: false,
              username: null,
              avatar_url: null,
              authorized_repos_count: 0,
            }
          : current
      );
      setSettings((current) =>
        current ? { ...current, github_username: null } : current
      );
      setNotice(
        `Disconnected. Removed ${response.removed_repositories} repositor${
          response.removed_repositories === 1 ? "y" : "ies"
        } and ${response.removed_webhooks} webhook${
          response.removed_webhooks === 1 ? "" : "s"
        }.`
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not disconnect GitHub"
      );
    } finally {
      setDisconnecting(false);
    }
  };

  return (
    <div className="p-8 lg:p-12 max-w-4xl">
      {/* Title */}
      <h1 className="font-serif text-5xl text-[#F5F2EB] tracking-tight mb-8">
        Settings
      </h1>

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

      {notice && (
        <div className="mb-6 border border-emerald-900/50 bg-emerald-950/20 text-emerald-300 rounded-xl px-4 py-3 text-sm flex items-start gap-2">
          <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{notice}</span>
        </div>
      )}

      {/* GitHub Connected Card */}
      <div className="border border-[#26231D] bg-[#141310] rounded-xl p-5 flex items-center justify-between mb-8 shadow-sm gap-4">
        <div className="flex items-center gap-3.5 min-w-0">
          {/* GitHub Icon */}
          <div className="w-10 h-10 rounded-xl bg-[#0D0C0A] border border-[#26231D] flex items-center justify-center text-[#F5F2EB] shrink-0">
            <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
              <path
                fillRule="evenodd"
                clipRule="evenodd"
                d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
              />
            </svg>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[#F5F2EB]">
              {loading
                ? "Checking GitHub connection..."
                : me?.connected
                ? "GitHub connected"
                : "GitHub not connected"}
            </p>
            <p className="font-mono text-xs text-[#8E897F] mt-0.5 truncate">
              {loading ? (
                <span className="inline-flex items-center gap-1.5">
                  <Loader2 className="w-3 h-3 animate-spin" /> loading identity
                </span>
              ) : me?.connected ? (
                <>
                  @{me.username} · {me.authorized_repos_count} repos authorised
                  {repositories.length > 0
                    ? ` · ${repositories.length} monitored`
                    : ""}
                </>
              ) : (
                "Set GITHUB_TOKEN in docsync-agent/.env or sign in with OAuth."
              )}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowManageModal(true)}
          className="border border-[#26231D] bg-[#1F1D18] hover:bg-[#2A2720] text-[#F5F2EB] px-4 py-1.5 rounded-lg text-sm font-sans font-medium transition-colors shrink-0"
        >
          Manage
        </button>
      </div>

      {/* 3 Policy Toggle Rows */}
      <div className="border border-[#26231D] bg-[#141310] rounded-xl divide-y divide-[#26231D] overflow-hidden mb-8 shadow-sm">
        {TOGGLES.map((item) => {
          const checked = settings ? settings[item.key] : false;
          const saving = savingKey === item.key;
          return (
            <button
              key={item.key}
              type="button"
              disabled={!settings || saving || loading}
              onClick={() => void toggle(item.key)}
              className="w-full text-left p-5 flex items-center justify-between hover:bg-[#1A1813] transition-colors cursor-pointer select-none disabled:cursor-wait disabled:opacity-70"
            >
              <div>
                <p className="text-sm font-medium text-[#F5F2EB]">
                  {item.label}
                </p>
                <p className="text-xs text-[#8E897F] mt-0.5">
                  {item.description}
                </p>
              </div>

              <div
                className={`w-5 h-5 rounded flex items-center justify-center transition-colors shrink-0 ${
                  checked
                    ? "bg-accent-orange text-black"
                    : "border border-[#3A352C] bg-[#0D0C0A]"
                }`}
              >
                {saving ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-[#8E897F]" />
                ) : (
                  checked && <Check className="w-3.5 h-3.5 stroke-[3]" />
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Danger Zone Card */}
      <div className="border border-red-900/60 bg-red-950/10 rounded-xl p-6 flex flex-col gap-1.5 shadow-sm">
        <h2 className="text-sm font-semibold text-red-500">
          Disconnect GitHub
        </h2>
        <p className="text-xs text-[#8E897F] mb-3">
          Removes webhooks from every repo and clears the monitored list. Your
          docs stay as they are.
        </p>
        <div>
          <button
            type="button"
            disabled={disconnecting}
            onClick={() => void handleDisconnect()}
            className="border border-red-800/80 hover:bg-red-900/20 text-red-400 font-medium px-4 py-1.5 rounded-lg text-sm transition-colors disabled:opacity-60 flex items-center gap-2"
          >
            {disconnecting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            <span>{disconnecting ? "Disconnecting..." : "Disconnect"}</span>
          </button>
        </div>
      </div>

      {/* Manage GitHub Modal */}
      {showManageModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#141310] border border-[#26231D] rounded-2xl w-full max-w-md p-6 shadow-2xl flex flex-col gap-4">
            <h3 className="font-serif text-2xl text-[#F5F2EB]">
              Manage GitHub connection
            </h3>
            <p className="text-xs font-mono text-[#8E897F] leading-relaxed">
              {me?.connected ? (
                <>
                  Connected as{" "}
                  <code className="text-[#F5F2EB]">@{me.username}</code> with
                  read access to code and write access to pull requests.
                </>
              ) : (
                "No GitHub identity is available. Add a token or sign in with OAuth to connect repositories."
              )}
            </p>

            <div className="border border-[#26231D] bg-[#0D0C0A] rounded-lg p-3 font-mono text-xs text-[#8E897F] flex flex-col gap-1.5 max-h-56 overflow-y-auto">
              {loading ? (
                <span className="flex items-center gap-1.5">
                  <Loader2 className="w-3 h-3 animate-spin" /> loading
                  repositories...
                </span>
              ) : repositories.length === 0 ? (
                <span>No repositories are monitored yet.</span>
              ) : (
                repositories.map((repo) => (
                  <span
                    key={repo.repo_full_name}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="truncate">
                      • {repo.repo_full_name}
                    </span>
                    <span className="flex items-center gap-1 shrink-0">
                      <GitBranch className="w-3 h-3" />
                      {repo.watch_branch}
                      <span
                        className={
                          repo.status === "listening"
                            ? "text-emerald-400"
                            : "text-[#8E897F]"
                        }
                      >
                        ({repo.status})
                      </span>
                    </span>
                  </span>
                ))
              )}
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowManageModal(false)}
                className="bg-[#F3EFE6] hover:bg-white text-[#141310] px-4 py-1.5 rounded-lg text-xs font-medium font-sans"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
