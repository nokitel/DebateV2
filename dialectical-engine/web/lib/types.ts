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
  node_type: "ROOT_CLAIM" | "PRO" | "CON";
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
  model_id: string;
  worker_id: string;
  worker_name?: string;
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

export type DebateDetail = {
  id: string;
  topic: string;
  status: string;
  config: Record<string, unknown>;
  root_node_id: string | null;
  synthesis_id: string | null;
  created_at: string;
  completed_at: string | null;
  tree: DebateNode | null;
  synthesis: Synthesis | null;
  active_synthesis: ActiveSynthesis | null;
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
