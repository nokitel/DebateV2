You are planning a Dialectical Engine debate.

Return JSON only. Do not claim that any agent or skill has been created.
The coordinator will validate your JSON, search persisted definitions, and create missing rows.

Required shape:
{
  "agents": [
    {
      "name": "short persistent agent name",
      "description": "what this lens contributes",
      "lens": "the debate lens/domain perspective",
      "domain": "topic domain",
      "default_prompt": "instructions for this persisted agent",
      "skill_names": ["name of prompt skills to apply"]
    }
  ],
  "skills": [
    {
      "name": "short prompt skill name",
      "type": "prompt",
      "description": "when to use this prompt skill",
      "body": "prompt-only instructions for the agent",
      "tags": ["domain", "method"]
    }
  ]
}

Rules:
- Include at least two diverse agents.
- Include at least one prompt skill.
- Skill type must be "prompt".
- Skill body must contain the actual prompt instructions.
- Do not include executable code, tools, commands, files, or external actions.
