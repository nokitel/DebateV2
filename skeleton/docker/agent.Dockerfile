FROM ubuntu:24.04

RUN apt-get update && apt-get install -y   bash curl git jq ripgrep make ca-certificates   && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash agent
WORKDIR /workspace
USER agent

# TODO Phase 5: install Claude Code, Codex CLI, gh, Chrome, and project toolchain.
CMD ["bash"]
