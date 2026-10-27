/**
 * Typed API client for the DocRipple FastAPI bridge.
 *
 * Every dashboard request is issued against the centralized API base URL in
 * `../lib/api`, which reads VITE_API_BASE_URL at build time.
 */

import { API_BASE_URL } from "../lib/api";

export { API_BASE_URL };

const isLocalhost =
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");

export const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  (isLocalhost ? "http://localhost:8000" : "https://docsync-agent-lyart.vercel.app")
).replace(/\/+$/, "");

// ── Shared models ───────────────────────────────────────────────────────────

export interface DocStyleSkill {
  repo_full_name: string;
  tone_and_voice: string;
  heading_conventions: string[];
  code_block_rules: string[];
  formatting_patterns: string[];
  skill_markdown: string;
  generated_at?: string;
}

export interface MemoryNode {
  node_id: string;
  repo_full_name: string;
  node_type: "module" | "file" | "symbol" | "doc_section";
  name: string;
  path: string;
  summary: string;
  metadata_json?: string;
}

export interface MemoryEdge {
  repo_full_name: string;
  source_id: string;
  target_id: string;
  relation: "CONTAINS" | "IMPORTS" | "DEFINES" | "DOCUMENTED_IN";
}

export interface RepoMemoryMap {
  repo_full_name: string;
  nodes: MemoryNode[];
  edges: MemoryEdge[];
  updated_at?: string;
}

export interface DemoRunPayload {
  delivery_id?: string;
  repo_full_name: string;
  raw_diff: string;
  docs: Record<string, string>;
}

export interface DemoRunResponse {
  delivery_id: string;
  change_report: {
    changed_symbols: Array<{
      symbol_name: string;
      symbol_kind: string;
      change_class: string;
      change_type: string;
      old_signature?: string;
      new_signature?: string;
    }>;
  };
  drift_report: {
    impacted_sections: Array<{
      doc_path: string;
      heading: string;
      anchor?: string;
      matched_symbols: string[];
      match_method: string;
    }>;
  };
  publish_result?: {
    pr_url: string;
    pr_number: number;
    verification_status: string;
    evidence_table_md: string;
  } | null;
}

// ── Web API models ──────────────────────────────────────────────────────────

export interface AuthMe {
  connected: boolean;
  username: string | null;
  avatar_url: string | null;
  plan: string;
  authorized_repos_count: number;
}

export interface AuthConfig {
  oauth_configured: boolean;
  client_id: string | null;
  callback_url: string;
}

export interface GitHubRepoSummary {
  full_name: string;
  name: string;
  owner_login: string;
  private: boolean;
  default_branch: string;
  language: string | null;
  updated_at: string | null;
}

export type RunStatus = "running" | "no_drift" | "pr_open" | "merged" | "failed";

export interface ActivityDiffPreview {
  file_path: string;
  deleted_lines: string[];
  added_lines: string[];
  context: string;
  changed_symbols?: Array<{
    file_path: string;
    symbol_name: string;
    symbol_kind: string;
    change_class: string;
    change_type: string;
    old_signature?: string | null;
    new_signature?: string | null;
  }>;
  impacted_sections?: Array<{
    doc_path: string;
    heading: string;
    anchor?: string | null;
    matched_symbols: string[];
    match_method: string;
    confidence_score: number;
  }>;
}

export interface ActivityRun {
  delivery_id: string;
  repo_full_name: string;
  commit_sha: string;
  commit_message: string;
  author: string;
  status: RunStatus;
  llm_calls: number;
  pr_url: string | null;
  pr_number: number | null;
  evidence_table_md: string;
  diff_preview: ActivityDiffPreview | null;
  created_at: string;
}

export interface MonitoredRepo {
  repo_full_name: string;
  owner: string;
  name: string;
  watch_branch: string;
  doc_paths: string[];
  drift_action: string;
  status: "listening" | "paused";
  language: string | null;
  webhook_id: number | null;
  last_pushed_at: string | null;
  created_at: string;
  run_count?: number;
}

export interface DashboardStats {
  runs_this_week: number;
  skipped_zero_tokens: number;
  prs_merged: number;
}

export interface DashboardResponse {
  stats: DashboardStats;
  repositories: MonitoredRepo[];
  latest_runs: ActivityRun[];
}

export interface ConnectRepoPayload {
  repo_full_name: string;
  watch_branch: string;
  doc_paths: string[];
  drift_action: string;
}

export interface ConnectRepoResponse {
  status: "connected";
  repo_full_name: string;
  webhook_url: string | null;
  style_skill_summary: string;
  memory_nodes_count: number;
  memory_edges_count: number;
  webhook_error?: string;
}

export interface TriggerResponse {
  status: "enqueued" | "already_running" | "already_synced";
  message?: string;
  delivery_id: string;
  repo_full_name: string;
  commit_sha: string;
  base_sha?: string;
  commit_message?: string;
  author?: string;
  branch: string;
}

export interface RepoHistoryItem {
  id: string;
  type: "commit" | "run";
  sha: string;
  full_sha?: string;
  title: string;
  message: string;
  author: string;
  avatar_url?: string;
  date: string;
  html_url?: string;
  status: "synced" | "running" | "no_drift" | "pr_open" | "merged" | "failed";
  status_label: string;
  doc: string;
  pr_number?: number | null;
  pr_url?: string | null;
  has_pipeline_run: boolean;
}

export interface RepoPullRequest {
  number: number;
  title: string;
  state: string;
  merged: boolean;
  html_url: string;
  created_at: string;
  updated_at: string;
  author: string;
  avatar_url?: string;
  head_branch: string;
  base_branch: string;
}

export interface RepoHistoryResponse {
  repo_full_name: string;
  watch_branch: string;
  stats: {
    total_commits: number;
    total_runs: number;
    pull_requests_count: number;
    status: string;
  };
  latest_commit_sha: string;
  latest_run_sha: string;
  latest_run_status: string;
  is_latest_synced: boolean;
  is_latest_running: boolean;
  history: RepoHistoryItem[];
  pull_requests: RepoPullRequest[];
  commits: Array<{
    sha: string;
    message: string;
    author: string;
    avatar_url: string;
    date: string;
    html_url: string;
  }>;
}

export interface UserSettings {
  github_username: string | null;
  require_reviewer_approval: boolean;
  skip_internal_changes: boolean;
  email_on_failed_runs: boolean;
}

export interface DisconnectResponse {
  status: "disconnected";
  removed_repositories: number;
  removed_webhooks: number;
}

// ── Token persistence & Request helper ──────────────────────────────────────

const TOKEN_KEY = "docripple_github_token";

export function getStoredToken(): string {
  if (typeof window === "undefined") return "";
  try {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    if (urlToken) {
      localStorage.setItem(TOKEN_KEY, urlToken);
      params.delete("token");
      const cleanUrl =
        window.location.pathname +
        (params.toString() ? `?${params.toString()}` : "") +
        window.location.hash;
      window.history.replaceState({}, document.title, cleanUrl);
      return urlToken;
    }
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setStoredToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  } catch {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getStoredToken();
  const authHeaders: Record<string, string> = {};
  if (token) {
    authHeaders["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body?.detail)) {
        detail = body.detail
          .map((item: { msg?: string }) => item.msg ?? "Invalid request")
          .join(", ");
      }
    } catch {
      // Keep the status-based fallback when the body is not JSON.
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

// ── Auth ────────────────────────────────────────────────────────────────────

export function getAuthMe(): Promise<AuthMe> {
  return request<AuthMe>("/api/v1/auth/me");
}

export function getAuthConfig(): Promise<AuthConfig> {
  return request<AuthConfig>("/api/v1/auth/config");
}

export function githubLoginUrl(): string {
  const frontendUrl =
    typeof window !== "undefined" && window.location.origin
      ? `?frontend_url=${encodeURIComponent(window.location.origin)}`
      : "";
  return `${API_BASE}/api/v1/auth/github/login${frontendUrl}`;
}

export async function loginWithToken(token: string): Promise<AuthMe> {
  const res = await request<AuthMe>("/api/v1/auth/token", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
  setStoredToken(token);
  return res;
}

export function saveOAuthConfig(
  clientId: string,
  clientSecret: string
): Promise<{ status: string; oauth_configured: boolean; client_id: string }> {
  return request<{ status: string; oauth_configured: boolean; client_id: string }>(
    "/api/v1/auth/oauth-config",
    {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
    }
  );
}

// ── Repository discovery & onboarding ──────────────────────────────────────

export function getGitHubRepos(): Promise<GitHubRepoSummary[]> {
  return request<GitHubRepoSummary[]>("/api/v1/github/repos");
}

export function connectRepository(
  payload: ConnectRepoPayload
): Promise<ConnectRepoResponse> {
  return request<ConnectRepoResponse>("/api/v1/repos/connect", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Dashboard & activity ────────────────────────────────────────────────────

export function getDashboard(): Promise<DashboardResponse> {
  return request<DashboardResponse>("/api/v1/dashboard");
}

export function getActivity(repoFullName?: string): Promise<{ runs: ActivityRun[] }> {
  const query = repoFullName
    ? `?repo_full_name=${encodeURIComponent(repoFullName)}`
    : "";
  return request<{ runs: ActivityRun[] }>(`/api/v1/activity${query}`);
}

export function getRepoHistory(
  owner: string,
  repo: string
): Promise<RepoHistoryResponse> {
  return request<RepoHistoryResponse>(
    `/api/v1/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/history`
  );
}

export function triggerRepo(
  owner: string,
  repo: string,
  commitSha?: string,
  options?: { force?: boolean; checkDuplicate?: boolean }
): Promise<TriggerResponse> {
  return request<TriggerResponse>(
    `/api/v1/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/trigger`,
    {
      method: "POST",
      body: JSON.stringify({
        ...(commitSha ? { commit_sha: commitSha } : {}),
        ...(options?.force ? { force: true } : {}),
        ...(options?.checkDuplicate ? { check_duplicate: true } : {}),
      }),
    }
  );
}

// ── Settings ────────────────────────────────────────────────────────────────

export function getSettings(): Promise<UserSettings> {
  return request<UserSettings>("/api/v1/settings");
}

export function updateSettings(
  patch: Partial<
    Pick<
      UserSettings,
      "require_reviewer_approval" | "skip_internal_changes" | "email_on_failed_runs"
    >
  >
): Promise<UserSettings> {
  return request<UserSettings>("/api/v1/settings", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function disconnectGitHub(): Promise<DisconnectResponse> {
  setStoredToken("");
  return request<DisconnectResponse>("/api/v1/settings/disconnect", {
    method: "POST",
  });
}

// ── Stage 0 detail views (existing repo detail page) ───────────────────────

/** Fetch the Stage 0 writing style skill. */
export async function getRepoSkill(
  owner: string,
  repo: string
): Promise<DocStyleSkill> {
  const repoFullName = `${owner}/${repo}`;
  try {
    return await request<DocStyleSkill>(
      `/api/v1/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/skill`
    );
  } catch (err) {
    console.warn(
      `Failed to fetch /skill for ${repoFullName}, returning fallback`,
      err
    );
  }

  return {
    repo_full_name: repoFullName,
    tone_and_voice:
      "Precise, developer-focused, imperative style. Uses evidence tables for PR transparency.",
    heading_conventions: [
      "H1: Repository Title & High-level Value",
      "H2: Functional Subsystems with doc-anchor comments",
      "H3: Method/API specifications and parameter tables",
    ],
    code_block_rules: [
      "Explicit syntax highlighting on every fenced block (```python, ```bash, ```typescript)",
      "Always include type hints in signatures",
      "Show return values and error handling patterns",
    ],
    formatting_patterns: [
      "Evidence tables in pull requests with symbol mapping",
      "Inline code tokens for function names and CLI flags",
      "Zero fluff: omit marketing boilerplate in technical docs",
    ],
    skill_markdown: `---
name: ${repo}-style-skill
repo: ${repoFullName}
version: 1.0.0
---

# Documentation Style Rules for ${repoFullName}

1. **Tone**: Active voice, concise and authoritative.
2. **Anchors**: Preserve all \`<!-- doc-anchor: ... -->\` comments for drift tracking.
3. **Signatures**: Always keep type hints aligned with Tree-sitter AST nodes.
4. **Evidence**: Include Markdown Evidence Tables for all signature additions.
`,
  };
}

/** Fetch the Stage 0 node/edge memory map. */
export async function getRepoMemory(
  owner: string,
  repo: string,
  symbols?: string
): Promise<RepoMemoryMap> {
  const repoFullName = `${owner}/${repo}`;
  try {
    const q = symbols ? `?symbols=${encodeURIComponent(symbols)}` : "";
    const data = await request<RepoMemoryMap>(
      `/api/v1/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/memory${q}`
    );
    if (data && Array.isArray(data.nodes) && data.nodes.length > 0) {
      return data;
    }
  } catch (err) {
    console.warn(
      `Failed to fetch /memory for ${repoFullName}, returning fallback graph`,
      err
    );
  }

  return fallbackMemoryMap(repo, repoFullName, symbols);
}

function fallbackMemoryMap(
  repo: string,
  repoFullName: string,
  symbols?: string
): RepoMemoryMap {
  const allNodes: MemoryNode[] = [
    {
      node_id: `module:${repo}::core`,
      repo_full_name: repoFullName,
      node_type: "module",
      name: "core",
      path: "src/core",
      summary: "Core business logic and execution engine",
    },
    {
      node_id: `file:${repo}::src/billing.py`,
      repo_full_name: repoFullName,
      node_type: "file",
      name: "billing.py",
      path: "src/billing.py",
      summary: "Billing and tax calculation implementation",
    },
    {
      node_id: `symbol:${repo}::src/billing.py::calc_total`,
      repo_full_name: repoFullName,
      node_type: "symbol",
      name: "calc_total",
      path: "src/billing.py",
      summary: "def calc_total(items: list[int], tax_rate: float = 0.05) -> int",
    },
    {
      node_id: `symbol:${repo}::src/cli.py::--dry-run`,
      repo_full_name: repoFullName,
      node_type: "symbol",
      name: "--dry-run",
      path: "src/cli.py",
      summary: "CLI flag for non-destructive pipeline dry run",
    },
    {
      node_id: `doc_section:${repo}::README.md#Billing`,
      repo_full_name: repoFullName,
      node_type: "doc_section",
      name: "README.md # Billing",
      path: "README.md",
      summary: "Documentation section explaining invoice total calculation",
    },
    {
      node_id: `doc_section:${repo}::docs/cli.md#Flags`,
      repo_full_name: repoFullName,
      node_type: "doc_section",
      name: "docs/cli.md # Flags",
      path: "docs/cli.md",
      summary: "CLI reference flags and dry-run execution arguments",
    },
  ];

  const allEdges: MemoryEdge[] = [
    {
      repo_full_name: repoFullName,
      source_id: `module:${repo}::core`,
      target_id: `file:${repo}::src/billing.py`,
      relation: "CONTAINS",
    },
    {
      repo_full_name: repoFullName,
      source_id: `file:${repo}::src/billing.py`,
      target_id: `symbol:${repo}::src/billing.py::calc_total`,
      relation: "DEFINES",
    },
    {
      repo_full_name: repoFullName,
      source_id: `symbol:${repo}::src/billing.py::calc_total`,
      target_id: `doc_section:${repo}::README.md#Billing`,
      relation: "DOCUMENTED_IN",
    },
    {
      repo_full_name: repoFullName,
      source_id: `symbol:${repo}::src/cli.py::--dry-run`,
      target_id: `doc_section:${repo}::docs/cli.md#Flags`,
      relation: "DOCUMENTED_IN",
    },
  ];

  const filteredNodes = symbols
    ? allNodes.filter(
        (n) =>
          n.name.toLowerCase().includes(symbols.toLowerCase()) ||
          n.path.toLowerCase().includes(symbols.toLowerCase())
      )
    : allNodes;

  const nodeIds = new Set(filteredNodes.map((n) => n.node_id));
  const filteredEdges = symbols
    ? allEdges.filter(
        (e) => nodeIds.has(e.source_id) || nodeIds.has(e.target_id)
      )
    : allEdges;

  return {
    repo_full_name: repoFullName,
    nodes: filteredNodes,
    edges: filteredEdges,
  };
}

/** Execute the synchronous demo run endpoint. */
export function executeDemoRun(payload: DemoRunPayload): Promise<DemoRunResponse> {
  return request<DemoRunResponse>("/api/v1/demo/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
