You are synthesizing a Dialectical Engine debate from completed AgentRun outputs.

Return JSON only. Use only actual AgentRun outputs in the context.

Required shape:
{
  "strongest_pro": "...",
  "strongest_con": "...",
  "verdict": "...",
  "contribution_summary": [
    {"agent_run_id": "...", "summary": "..."}
  ],
  "provenance": {
    "model_id": "...",
    "worker_id": "...",
    "prompt_id": "...",
    "job_id": "..."
  }
}

Rules:
- Refuse implied or missing AgentRun content by leaving it out.
- Include a concise contribution summary for each completed AgentRun.
- Do not return status wrappers.
