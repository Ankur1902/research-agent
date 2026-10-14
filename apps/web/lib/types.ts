export interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  csrf: string;
}
export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
}
export interface Finding {
  text: string;
  kind: string;
  status: string;
  citations: string[];
  quote: string;
}
export interface Report {
  title: string;
  summary: string;
  findings: Finding[];
  sections: { title: string; finding_indices: number[] }[];
  limitations: string[];
  mode: string;
}
export interface Research {
  id: string;
  question: string;
  status: string;
  mode: string;
  depth: string;
  source_mode: string;
  cost: number;
  budget: number;
  created_at: string;
  error: string | null;
  project_id: string | null;
  plan: {
    objective: string;
    tasks: { id: string; question: string; agent: string }[];
    output_sections: string[];
  } | null;
  report: Report | null;
}
export interface Source {
  id: string;
  citation: string;
  title: string;
  url: string;
  domain: string;
  evidence: string;
  created_at: string;
  metadata_json: Record<string, unknown>;
}
export interface Trace {
  id: string;
  sequence: number;
  agent: string;
  type: string;
  message: string;
  created_at: string;
  details: Record<string, unknown>;
}
export interface ExecutionSummary {
  mode: string;
  retrieval_backend: string | null;
  time_to_draft_ms: number | null;
  processing_ms: number | null;
  planning_ms: number | null;
  execution_ms: number | null;
  approval_wait_ms: number | null;
  llm_calls: number;
  tool_calls: number;
  tools_by_name: Record<string, number>;
  model_calls: {
    agent: string;
    provider?: string;
    model?: string;
    latency_ms?: number;
    input_tokens?: number;
    output_tokens?: number;
  }[];
  tool_activity: {
    name: string;
    arguments?: Record<string, unknown>;
    call_number?: number;
  }[];
}
export interface Document {
  id: string;
  name: string;
  status: string;
  error: string | null;
  created_at: string;
  text?: string;
  chunk_count?: number;
}
export interface Evaluation {
  id: string;
  name: string;
  created_at: string;
  results: {
    metrics: Record<string, number | null>;
    mode: string;
    cost: number;
    method: string;
  };
}
export interface Dashboard {
  projects: number;
  documents: number;
  active: number;
  reports: number;
  cost: number;
  average_duration: number | null;
  volume: Record<string, number>;
  recent: Research[];
}
export interface Settings {
  organization: string;
  role: string;
  provider: string;
  model: string;
  search_provider: string;
  generation_configured: boolean;
  search_configured: boolean;
  embedding_configured: boolean;
  preferences: { default_depth?: string; monthly_budget?: number };
}
