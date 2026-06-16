services:
  agent-{{ISSUE_ID}}:
    build:
      context: .
      dockerfile: docker/agent.Dockerfile
    working_dir: /workspace
    volumes:
      - {{WORKTREE_PATH}}:/workspace
    networks: [harness-{{ISSUE_ID}}]

networks:
  harness-{{ISSUE_ID}}:
    internal: false
