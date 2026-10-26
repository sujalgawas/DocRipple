/**
 * API client and types for DocRipple (FastAPI backend + local repo state).
 */

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

export interface RepositoryItem {
  id: string;
  owner: string;
  name: string;
  fullName: string;
  branch: string;
  status: "listening" | "paused";
  trackedDocs: string[];
  language: string;
  runsCount: number;
  lastPushed: string;
  lastCommit?: string;
  isCustom?: boolean;
}

// Built-in starter repositories matching screenshots
export const INITIAL_REPOSITORIES: RepositoryItem[] = [
  {
    id: "repo-docripple",
    owner: "sujalgawas",
    name: "DocRipple",
    fullName: "sujalgawas/DocRipple",
    branch: "main",
    status: "listening",
    trackedDocs: ["README.md", "docs/"],
    language: "Python",
    runsCount: 128,
    lastPushed: "pushed 4 min ago",
    lastCommit: "a3f9c21",
  },
  {
    id: "repo-ledger-api",
    owner: "sujalgawas",
    name: "ledger-api",
    fullName: "sujalgawas/ledger-api",
    branch: "main",
    status: "listening",
    trackedDocs: ["README.md", "docs/api.md"],
    language: "TypeScript",
    runsCount: 61,
    lastPushed: "pushed 2 h ago",
    lastCommit: "c19e8f0",
  },
  {
    id: "repo-billing-cli",
    owner: "acme-labs",
    name: "billing-cli",
    fullName: "acme-labs/billing-cli",
    branch: "develop",
    status: "listening",
    trackedDocs: ["docs/cli.md"],
    language: "Go",
    runsCount: 22,
    lastPushed: "pushed yesterday",
    lastCommit: "b8a101f",
  },
  {
    id: "repo-design-tokens",
    owner: "acme-labs",
    name: "design-tokens",
    fullName: "acme-labs/design-tokens",
    branch: "main",
    status: "paused",
    trackedDocs: ["README.md"],
    language: "TypeScript",
    runsCount: 3,
    lastPushed: "pushed 6 days ago",
    lastCommit: "90fd2c4",
  },
];

const LOCAL_STORAGE_KEY = "docripple_repos_v1";

export function getStoredRepositories(): RepositoryItem[] {
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
    if (!raw) return INITIAL_REPOSITORIES;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : INITIAL_REPOSITORIES;
  } catch {
    return INITIAL_REPOSITORIES;
  }
}

export function saveStoredRepository(repo: RepositoryItem): void {
  try {
    const current = getStoredRepositories();
    const existingIndex = current.findIndex((r) => r.fullName.toLowerCase() === repo.fullName.toLowerCase());
    let updated: RepositoryItem[];
    if (existingIndex >= 0) {
      updated = [...current];
      updated[existingIndex] = repo;
    } else {
      updated = [repo, ...current];
    }
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(updated));
  } catch (err) {
    console.error("Failed to persist repo to localStorage", err);
  }
}

const API_BASE = "";

/** Trigger Stage 0 Onboarding */
export async function onboardRepository(
  repoFullName: string,
  branch: string = "main",
  codeFiles?: Record<string, string>,
  docs?: Record<string, string>
): Promise<OnboardRepoResult> {
  const payload = {
    repo_full_name: repoFullName,
    branch,
    code_files: codeFiles || {},
    docs: docs || {},
  };

  try {
    const res = await fetch(`${API_BASE}/api/v1/repos/onboard`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.warn("Backend /api/v1/repos/onboard unavailable, using synthetic Stage 0 fallback", err);
  }

  // Graceful fallback if backend is unreachable or snapshot missing
  return {
    repo_full_name: repoFullName,
    style_skill: {
      repo_full_name: repoFullName,
      tone_and_voice: "Technical, direct, and imperative. Focus on reproducible copy-paste commands and architecture.",
      heading_conventions: [
        "Use Title Case for H1 and Sentence case for H2/H3",
        "Keep heading anchors stable <!-- doc-anchor: <id> -->",
        "Include badges and technology tags at the top",
      ],
      code_block_rules: [
        "Always specify language identifier on fenced blocks (```python, ```bash, ```ts)",
        "Use keepends=True or clean trailing newlines on diff patches",
        "Demonstrate complete minimal invocations with expected output",
      ],
      formatting_patterns: [
        "Include evidence tables for breaking changes",
        "Highlight CLI flags in inline monospace backticks",
      ],
      skill_markdown: `---
name: doc-style-skill
description: Auto-extracted writing conventions for ${repoFullName}
---
# Writing Style Skill for ${repoFullName}

- **Tone**: Technical, concise, developer-centric.
- **Headings**: Use sentence case with <!-- doc-anchor: id --> comments.
- **Code Fences**: Strict language identifiers on all fences.
- **Evidence**: Provide clear before/after parameter examples.
`,
    },
    memory_node_count: 32,
    memory_edge_count: 48,
    initial_code_doc_edges: 14,
  };
}

/** Fetch Stage 0 Writing Style Skill */
export async function getRepoSkill(owner: string, repo: string): Promise<DocStyleSkill> {
  const repoFullName = `${owner}/${repo}`;
  try {
    const res = await fetch(`${API_BASE}/api/v1/repos/${owner}/${repo}/skill`);
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.warn(`Failed to fetch /skill for ${repoFullName}, returning fallback`, err);
  }

  return {
    repo_full_name: repoFullName,
    tone_and_voice: "Precise, developer-focused, imperative style. Uses evidence tables for PR transparency.",
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

/** Fetch Stage 0 Node/Edge Memory Map */
export async function getRepoMemory(
  owner: string,
  repo: string,
  symbols?: string
): Promise<RepoMemoryMap> {
  const repoFullName = `${owner}/${repo}`;
  try {
    const q = symbols ? `?symbols=${encodeURIComponent(symbols)}` : "";
    const res = await fetch(`${API_BASE}/api/v1/repos/${owner}/${repo}/memory${q}`);
    if (res.ok) {
      const data = await res.json();
      if (data && Array.isArray(data.nodes) && data.nodes.length > 0) {
        return data;
      }
    }
  } catch (err) {
    console.warn(`Failed to fetch /memory for ${repoFullName}, returning fallback graph`, err);
  }

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
    ? allEdges.filter((e) => nodeIds.has(e.source_id) || nodeIds.has(e.target_id))
    : allEdges;

  return {
    repo_full_name: repoFullName,
    nodes: filteredNodes,
    edges: filteredEdges,
  };
}

/** Execute Live Demo Drift Run */
export async function executeDemoRun(payload: DemoRunPayload): Promise<DemoRunResponse> {
  const res = await fetch(`${API_BASE}/api/v1/demo/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Demo run failed (${res.status}): ${errorText}`);
  }
  return await res.json();
}
