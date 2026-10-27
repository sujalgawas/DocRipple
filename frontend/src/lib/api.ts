/**
 * Typed API Client for DocRipple FastAPI Backend
 *
 * `VITE_API_BASE_URL` wins when set (CI/production). Otherwise local dev targets
 * the Vite dev server's API and a production build targets the deployed API,
 * never a developer's localhost. Any trailing slash is stripped so paths such as
 * `/api/v1/auth/me` never become `//api/v1/auth/me` (which 404s on Vercel).
 */

const DEFAULT_PRODUCTION_API = "https://docsync-agent-lyart.vercel.app";

const configuredApiBaseUrl =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://localhost:8000" : DEFAULT_PRODUCTION_API);

/** Single source of truth for the FastAPI origin (no trailing slash). */
export const API_BASE_URL = configuredApiBaseUrl.replace(/\/+$/, "");

/** Backwards-compatible alias used by older imports. */
export const API_BASE = API_BASE_URL;

// ── Models & Types ──────────────────────────────────────────────────────────

export type ChangeClass = "api_surface" | "cli" | "env_config" | "deps" | "behavior";

export interface ChangedSymbol {
  file_path: string;
  symbol_name: string;
  symbol_kind: "function" | "class" | "method" | "route" | "cli_flag" | "env_var" | "dependency";
  change_class: ChangeClass;
  change_type: "added" | "modified" | "removed";
  old_signature?: string | null;
  new_signature?: string | null;
}

export type MatchMethod = "exact_anchor" | "graph_edge" | "inline_symbol" | "embedding_fallback";

export interface ImpactedDocSection {
  doc_path: string;
  heading: string;
  anchor?: string | null;
  matched_symbols: string[];
  match_method: MatchMethod;
  confidence_score: number;
}

export interface PublishResult {
  delivery_id: string;
  pr_url: string;
  pr_number: number;
  branch_name: string;
  updated_docs: Record<string, string>;
  evidence_table_md: string;
  verification_status: "passed" | "repaired" | "failed";
  created_at: string;
}

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

export interface OnboardRepoPayload {
  repo_full_name: string;
  branch?: string;
  code_files?: Record<string, string>;
  docs?: Record<string, string>;
}

export interface OnboardRepoResult {
  repo_full_name: string;
  style_skill: DocStyleSkill;
  memory_node_count: number;
  memory_edge_count: number;
  initial_code_doc_edges: number;
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
    changed_symbols: ChangedSymbol[];
  };
  drift_report: {
    impacted_sections: ImpactedDocSection[];
  };
  publish_result?: PublishResult | null;
}

export type RunStatus = "running" | "no_drift" | "pr_open" | "merged" | "failed" | "synced";

export interface PipelineStageState {
  stage_id: string;
  name: string;
  status: "completed" | "running" | "skipped" | "failed";
  detail: string;
}

export interface ActivityRunItem {
  id: string;
  delivery_id: string;
  status: RunStatus;
  status_label: string;
  title: string;
  repo_name: string;
  repo_full_name: string;
  sha: string;
  author: string;
  llm_calls: number;
  llm_calls_text: string;
  relative_time: string;
  stages: PipelineStageState[];
  changed_symbols: ChangedSymbol[];
  impacted_sections: ImpactedDocSection[];
  evidence_table_md: string;
  diff_preview: {
    file_path: string;
    deleted_lines: string[];
    added_lines: string[];
    context: string;
  };
  pr_url?: string | null;
  pr_number?: number | null;
}

// ── Realistic Seed Data Matching Screenshots ─────────────────────────────────

export const SEED_ACTIVITY_RUNS: ActivityRunItem[] = [
  {
    id: "act-run-1",
    delivery_id: "deliv-a3f9c21-run",
    status: "running",
    status_label: "running",
    title: "feat(analyzer): add --dry-run flag to CLI",
    repo_name: "DocRipple",
    repo_full_name: "sujalgawas/DocRipple",
    sha: "a3f9c21",
    author: "sujalgawas",
    llm_calls: 3,
    llm_calls_text: "3 llm calls",
    relative_time: "4 min ago",
    stages: [
      { stage_id: "01", name: "Ingest", status: "completed", detail: "HMAC ok · WebhookJob enqueued" },
      { stage_id: "02", name: "Change analyzer", status: "completed", detail: "tree-sitter: 1 CLI flag identified" },
      { stage_id: "03", name: "Drift engine", status: "completed", detail: "1 section hit: docs/cli.md#Flags" },
      { stage_id: "04", name: "Planner → Writer", status: "running", detail: "LangGraph generating section draft" },
      { stage_id: "05", name: "Verifier", status: "running", detail: "Pending syntax checks" },
      { stage_id: "06", name: "Publish PR", status: "running", detail: "Awaiting review approval" },
    ],
    changed_symbols: [
      {
        file_path: "src/cli.py",
        symbol_name: "--dry-run",
        symbol_kind: "cli_flag",
        change_class: "cli",
        change_type: "added",
        old_signature: null,
        new_signature: "--dry-run: bool = False (analyze without opening a PR)",
      },
    ],
    impacted_sections: [
      {
        doc_path: "docs/cli.md",
        heading: "Flags",
        anchor: "flags",
        matched_symbols: ["--dry-run"],
        match_method: "exact_anchor",
        confidence_score: 1.0,
      },
    ],
    evidence_table_md: `| doc_file | section | changed_symbol | change_class | match_method | verification |
|---|---|---|---|---|---|
| docs/cli.md | Flags | --dry-run | cli | exact_anchor | pending |`,
    diff_preview: {
      file_path: "docs/cli.md",
      deleted_lines: ["- --verbose print debug output"],
      added_lines: [
        "+ --dry-run analyze without opening a PR",
        "+ --verbose print pipeline trace",
      ],
      context: "## Flags\n\nCommand-line invocation switches:",
    },
    pr_url: "https://github.com/sujalgawas/DocRipple/pull/102",
    pr_number: 102,
  },
  {
    id: "act-run-2",
    delivery_id: "deliv-7be02d4-nodrift",
    status: "no_drift",
    status_label: "no drift",
    title: "refactor: tidy internal helpers in drift.py",
    repo_name: "DocRipple",
    repo_full_name: "sujalgawas/DocRipple",
    sha: "7be02d4",
    author: "sujalgawas",
    llm_calls: 0,
    llm_calls_text: "0 llm calls",
    relative_time: "38 min ago",
    stages: [
      { stage_id: "01", name: "Ingest", status: "completed", detail: "HMAC ok · WebhookJob enqueued" },
      { stage_id: "02", name: "Change analyzer", status: "completed", detail: "tree-sitter: internal helper function" },
      { stage_id: "03", name: "Drift engine", status: "completed", detail: "0 doc sections impacted (early exit gate)" },
      { stage_id: "04", name: "Planner → Writer", status: "skipped", detail: "0 LLM calls made" },
      { stage_id: "05", name: "Verifier", status: "skipped", detail: "Skipped" },
      { stage_id: "06", name: "Publish PR", status: "skipped", detail: "No PR required" },
    ],
    changed_symbols: [
      {
        file_path: "src/drift/engine.py",
        symbol_name: "_compute_cosine_sim",
        symbol_kind: "function",
        change_class: "behavior",
        change_type: "modified",
        old_signature: "def _compute_cosine_sim(a: np.ndarray, b: np.ndarray) -> float",
        new_signature: "def _compute_cosine_sim(a: np.ndarray, b: np.ndarray) -> np.float32",
      },
    ],
    impacted_sections: [],
    evidence_table_md: "No documentation sections impacted. Early exit gate triggered (0 LLM tokens spent).",
    diff_preview: {
      file_path: "src/drift/engine.py",
      deleted_lines: ["-def _compute_cosine_sim(a: np.ndarray, b: np.ndarray) -> float:"],
      added_lines: ["+def _compute_cosine_sim(a: np.ndarray, b: np.ndarray) -> np.float32:"],
      context: "Internal helper not referenced in public documentation anchors.",
    },
    pr_url: null,
    pr_number: null,
  },
  {
    id: "act-run-3",
    delivery_id: "deliv-c19e8f0-pr",
    status: "pr_open",
    status_label: "PR open",
    title: "rename POST /invoices → /v2/invoices",
    repo_name: "ledger-api",
    repo_full_name: "sujalgawas/ledger-api",
    sha: "c19e8f0",
    author: "mira-k",
    llm_calls: 5,
    llm_calls_text: "5 llm calls",
    relative_time: "2 h ago",
    stages: [
      { stage_id: "01", name: "Ingest", status: "completed", detail: "HMAC ok · WebhookJob enqueued" },
      { stage_id: "02", name: "Change analyzer", status: "completed", detail: "FastAPI route changed" },
      { stage_id: "03", name: "Drift engine", status: "completed", detail: "1 section hit: docs/api.md#Invoicing" },
      { stage_id: "04", name: "Planner → Writer", status: "completed", detail: "Section edit spliced" },
      { stage_id: "05", name: "Verifier", status: "completed", detail: "Syntax and fences passed" },
      { stage_id: "06", name: "Publish PR", status: "completed", detail: "PR #42 opened with evidence table" },
    ],
    changed_symbols: [
      {
        file_path: "src/routes/invoices.py",
        symbol_name: "create_invoice",
        symbol_kind: "route",
        change_class: "api_surface",
        change_type: "modified",
        old_signature: "POST /invoices",
        new_signature: "POST /v2/invoices",
      },
    ],
    impacted_sections: [
      {
        doc_path: "docs/api.md",
        heading: "Invoicing",
        anchor: "invoicing",
        matched_symbols: ["create_invoice"],
        match_method: "graph_edge",
        confidence_score: 0.95,
      },
    ],
    evidence_table_md: `| doc_file | section | changed_symbol | change_class | match_method | verification |
|---|---|---|---|---|---|
| docs/api.md | Invoicing | create_invoice | api_surface | graph_edge | passed |`,
    diff_preview: {
      file_path: "docs/api.md",
      deleted_lines: ["-POST /invoices to generate billing ledger records"],
      added_lines: ["+POST /v2/invoices to generate billing ledger records with tax breakdown"],
      context: "## Invoicing API Endpoints",
    },
    pr_url: "https://github.com/sujalgawas/ledger-api/pull/42",
    pr_number: 42,
  },
  {
    id: "act-run-4",
    delivery_id: "deliv-e44a1b7-merged",
    status: "merged",
    status_label: "merged",
    title: "env: GITHUB_APP_ID now required",
    repo_name: "DocRipple",
    repo_full_name: "sujalgawas/DocRipple",
    sha: "e44a1b7",
    author: "sujalgawas",
    llm_calls: 2,
    llm_calls_text: "2 llm calls",
    relative_time: "5 h ago",
    stages: [
      { stage_id: "01", name: "Ingest", status: "completed", detail: "HMAC ok · WebhookJob enqueued" },
      { stage_id: "02", name: "Change analyzer", status: "completed", detail: "Environment variable added" },
      { stage_id: "03", name: "Drift engine", status: "completed", detail: "README.md#Configuration hit" },
      { stage_id: "04", name: "Planner → Writer", status: "completed", detail: "Doc env table updated" },
      { stage_id: "05", name: "Verifier", status: "completed", detail: "Passed" },
      { stage_id: "06", name: "Publish PR", status: "completed", detail: "PR #100 merged by maintainer" },
    ],
    changed_symbols: [
      {
        file_path: "src/config.py",
        symbol_name: "GITHUB_APP_ID",
        symbol_kind: "env_var",
        change_class: "env_config",
        change_type: "added",
        old_signature: null,
        new_signature: "GITHUB_APP_ID: str",
      },
    ],
    impacted_sections: [
      {
        doc_path: "README.md",
        heading: "Configuration",
        anchor: "configuration",
        matched_symbols: ["GITHUB_APP_ID"],
        match_method: "inline_symbol",
        confidence_score: 0.92,
      },
    ],
    evidence_table_md: `| doc_file | section | changed_symbol | change_class | match_method | verification |
|---|---|---|---|---|---|
| README.md | Configuration | GITHUB_APP_ID | env_config | inline_symbol | passed |`,
    diff_preview: {
      file_path: "README.md",
      deleted_lines: ["-GITHUB_TOKEN=your_token"],
      added_lines: [
        "+GITHUB_APP_ID=your_github_app_id",
        "+GITHUB_TOKEN=your_token",
      ],
      context: "### Environment Variables (.env)",
    },
    pr_url: "https://github.com/sujalgawas/DocRipple/pull/100",
    pr_number: 100,
  },
  {
    id: "act-run-5",
    delivery_id: "deliv-09d3a5e-failed",
    status: "failed",
    status_label: "failed",
    title: "bump cobra to v1.8",
    repo_name: "billing-cli",
    repo_full_name: "acme-labs/billing-cli",
    sha: "09d3a5e",
    author: "dev-ops-bot",
    llm_calls: 4,
    llm_calls_text: "4 llm calls",
    relative_time: "yesterday",
    stages: [
      { stage_id: "01", name: "Ingest", status: "completed", detail: "HMAC ok" },
      { stage_id: "02", name: "Change analyzer", status: "completed", detail: "go.mod dependency bump" },
      { stage_id: "03", name: "Drift engine", status: "completed", detail: "docs/install.md hit" },
      { stage_id: "04", name: "Planner → Writer", status: "completed", detail: "Draft created" },
      { stage_id: "05", name: "Verifier", status: "failed", detail: "Syntax fence mismatch in upstream snippet" },
      { stage_id: "06", name: "Publish PR", status: "skipped", detail: "Publish aborted due to verification failure" },
    ],
    changed_symbols: [
      {
        file_path: "go.mod",
        symbol_name: "github.com/spf13/cobra",
        symbol_kind: "dependency",
        change_class: "deps",
        change_type: "modified",
        old_signature: "github.com/spf13/cobra v1.7.0",
        new_signature: "github.com/spf13/cobra v1.8.0",
      },
    ],
    impacted_sections: [
      {
        doc_path: "docs/install.md",
        heading: "Dependencies",
        anchor: "dependencies",
        matched_symbols: ["github.com/spf13/cobra"],
        match_method: "inline_symbol",
        confidence_score: 0.88,
      },
    ],
    evidence_table_md: `| doc_file | section | changed_symbol | change_class | match_method | verification |
|---|---|---|---|---|---|
| docs/install.md | Dependencies | github.com/spf13/cobra | deps | inline_symbol | failed |`,
    diff_preview: {
      file_path: "docs/install.md",
      deleted_lines: ["-cobra >= 1.7.0 required"],
      added_lines: ["+cobra >= 1.8.0 required"],
      context: "Installation prerequisites:",
    },
    pr_url: null,
    pr_number: null,
  },
  {
    id: "act-run-6",
    delivery_id: "deliv-f88b2c3-typo",
    status: "no_drift",
    status_label: "no drift",
    title: "fix typo in comments",
    repo_name: "ledger-api",
    repo_full_name: "sujalgawas/ledger-api",
    sha: "f88b2c3",
    author: "mira-k",
    llm_calls: 0,
    llm_calls_text: "0 llm calls",
    relative_time: "yesterday",
    stages: [
      { stage_id: "01", name: "Ingest", status: "completed", detail: "HMAC ok" },
      { stage_id: "02", name: "Change analyzer", status: "completed", detail: "Zero AST symbols modified" },
      { stage_id: "03", name: "Drift engine", status: "completed", detail: "Early exit (comment-only change)" },
      { stage_id: "04", name: "Planner → Writer", status: "skipped", detail: "0 LLM calls made" },
      { stage_id: "05", name: "Verifier", status: "skipped", detail: "Skipped" },
      { stage_id: "06", name: "Publish PR", status: "skipped", detail: "No PR required" },
    ],
    changed_symbols: [],
    impacted_sections: [],
    evidence_table_md: "Comment-only commit. Tree-sitter detected zero AST symbol modifications.",
    diff_preview: {
      file_path: "src/utils.ts",
      deleted_lines: ["-// recieves payment payload"],
      added_lines: ["+// receives payment payload"],
      context: "Internal code comment typo fix.",
    },
    pr_url: null,
    pr_number: null,
  },
];

// ── Typed API Functions ───────────────────────────────────────────────────────

/** Onboard a repository and index Stage 0 writing style + memory map */
export async function onboardRepo(
  payload: OnboardRepoPayload
): Promise<OnboardRepoResult> {
  const res = await fetch(`${API_BASE_URL}/api/v1/repos/onboard`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Onboard failed (${res.status}): ${errText}`);
  }
  return await res.json();
}

/** Get repository writing style skill */
export async function getRepoSkill(
  owner: string,
  repo: string
): Promise<DocStyleSkill> {
  const res = await fetch(`${API_BASE_URL}/api/v1/repos/${owner}/${repo}/skill`);
  if (!res.ok) {
    throw new Error(`Failed to fetch style skill (${res.status})`);
  }
  return await res.json();
}

/** Get repository memory subgraph */
export async function getRepoMemory(
  owner: string,
  repo: string,
  symbols?: string
): Promise<RepoMemoryMap> {
  const q = symbols ? `?symbols=${encodeURIComponent(symbols)}` : "";
  const res = await fetch(`${API_BASE_URL}/api/v1/repos/${owner}/${repo}/memory${q}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch repo memory (${res.status})`);
  }
  return await res.json();
}

/** Trigger demo run */
export async function triggerDemoRun(
  payload: DemoRunPayload
): Promise<DemoRunResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/demo/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Demo run failed (${res.status}): ${errText}`);
  }
  return await res.json();
}

/** Get run status by delivery ID */
export async function getRunStatus(
  deliveryId: string
): Promise<PublishResult> {
  const res = await fetch(`${API_BASE_URL}/api/v1/runs/${deliveryId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch run result (${res.status})`);
  }
  return await res.json();
}

/** Health check */
export async function getHealth(): Promise<{ status: string; service: string }> {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) {
    throw new Error(`Health check failed (${res.status})`);
  }
  return await res.json();
}
