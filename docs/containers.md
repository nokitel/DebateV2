# Containers

Each slice runs in a per-issue Docker Compose stack. Containers reduce blast radius from agent mistakes; they are not a guarantee against malicious code. The agent has freedom inside `/workspace`, while host access is intentionally unavailable.
