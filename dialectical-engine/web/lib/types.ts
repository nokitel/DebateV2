export type DebateSummary = {
  id: string;
  topic: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  models: string[];
};

export type Generation = {
  id: string;
  job_id?: string;
  model_id: string;
  role: string;
  argument: string;
  worker_id: string;
  worker_name?: string;
  created_at: string;
  is_active?: boolean;
  is_streaming?: boolean;
  tokens_in?: number | null;
  tokens_out?: number | null;
  latency_ms?: number;
};

export type DebateNode = {
  id: string;
  debate_id: string;
  parent_id: string | null;
  node_type: "ROOT_CLAIM" | "SCIENTIFIC_POV" | "STATISTICAL_POV" | "ETHICAL_POV" | "PRACTICAL_POV" | "PRO" | "CON";
  depth: number;
  position: number;
  claim: string;
  status: string;
  materialized_path: string;
  active_generation_id: string | null;
  active_generation: Generation | null;
  children: DebateNode[];
};

export type Synthesis = {
  id: string;
  debate_id: string;
  strongest_pro: string;
  strongest_con: string;
  verdict: string;
  upstream_agent_output_ids?: string[];
  upstream_agent_run_ids?: string[];
  analyzer_findings?: Record<string, string>;
  provenance?: Record<string, unknown>;
  model_id: string;
  worker_id: string;
  worker_name?: string;
  created_at: string;
};

export type DebateBranch = {
  id: string;
  debate_id: string;
  parent_branch_id: string | null;
  root_node_id: string | null;
  status: string;
  created_at: string;
};

export type AnalyzerRun = {
  id: string;
  debate_id: string;
  branch_id: string;
  analyzer_type: string;
  output: {
    findings?: string[];
    [key: string]: unknown;
  };
  status: string;
  provenance: Record<string, unknown>;
  created_at: string;
};

export type SelectedCapability = {
  id: string;
  match_id: string;
  debate_id: string;
  branch_id: string;
  selection_reason: string;
  score: number;
  status: string | null;
  reuse_count: number;
  definition: {
    name?: string;
    description?: string;
    [key: string]: unknown;
  };
  name?: string;
  created_at: string;
};

export type AgentOutput = {
  id: string;
  debate_id: string;
  branch_id: string;
  skill_id: string;
  agent_id: string;
  analyzer_run_ids: string[];
  pros: string[];
  cons: string[];
  summary: string;
  confidence: number;
  provenance: Record<string, unknown>;
  created_at: string;
};

export type AgentRun = {
  id: string;
  debate_id: string;
  branch_id: string;
  agent_definition_id: string;
  selected_skill_ids: string[];
  agent: {
    name?: string;
    description?: string;
    lens?: string;
    default_prompt?: string;
    [key: string]: unknown;
  };
  agent_name?: string;
  role: string;
  lens: string;
  status: string;
  prompt_input: Record<string, unknown>;
  output: Record<string, unknown>;
  pros: string[];
  cons: string[];
  summary: string;
  confidence: number;
  skills_used: {
    id: string;
    name?: string;
    type?: string;
    description?: string;
    tags?: string[];
  }[];
  job_id: string | null;
  worker_id: string | null;
  model_id: string | null;
  provenance: Record<string, unknown>;
  created_at: string;
};

export type ProvenanceRecord = {
  id: string;
  debate_id: string;
  branch_id: string | null;
  artifact_kind: string;
  artifact_id: string;
  model_id: string;
  worker_id: string;
  prompt_id: string;
  job_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type ActiveSynthesis = {
  id: string;
  job_id: string;
  debate_id: string;
  model_id: string;
  worker_id: string;
  worker_name?: string;
  created_at: string;
  raw: string;
  is_streaming?: boolean;
};

export type SingleShotResult = {
  pros: string[];
  cons: string[];
  strongest_pro: string;
  strongest_con: string;
  global_winner: {
    side: "pro" | "con" | "balanced";
    reason: string;
  };
  final_text: string;
  model_id: string;
  tokens_in: number;
  tokens_out: number;
  created_at: string;
};

export type DebateConfig = Record<string, unknown> & {
  single_shot_result?: SingleShotResult | null;
};

export type DebateDetail = {
  id: string;
  topic: string;
  status: string;
  config: DebateConfig;
  direct_answer: null;
  root_node_id: string | null;
  synthesis_id: string | null;
  created_at: string;
  completed_at: string | null;
  tree: DebateNode | null;
  synthesis: Synthesis | null;
  active_synthesis: ActiveSynthesis | null;
  branch_lineage: DebateBranch[];
  analyzer_runs: AnalyzerRun[];
  selected_skills: SelectedCapability[];
  selected_agents: SelectedCapability[];
  agent_outputs: AgentOutput[];
  agent_runs: AgentRun[];
  skills_used: string[];
  provenance_records: ProvenanceRecord[];
  workers: string[];
  models: string[];
  node_count: number;
};

export type WorkerStatus = {
  id: string;
  name: string;
  capabilities: string[];
  last_seen: string;
  status: string;
  current_job_id: string | null;
};
