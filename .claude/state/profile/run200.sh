#!/usr/bin/env bash
set -x
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter
DC="docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.override.yml -f .claude/state/profile/compose-200.yml"
$DC up -d market-worker
sleep 240
docker stats --no-stream docker-market-worker-1 > .claude/state/profile/stats-200.txt 2>&1
MSYS_NO_PATHCONV=1 docker run --rm --pid=container:docker-market-worker-1 --cap-add SYS_PTRACE --cap-add SYS_ADMIN \
  -v "C:/dev/project-hunter/.claude/state/profile:/out" \
  python:3.12-slim sh -c "pip install --quiet py-spy 2>/dev/null; py-spy record --pid 1 --duration 90 --rate 120 --format raw --output /out/raw-200.txt"
docker stats --no-stream docker-market-worker-1 >> .claude/state/profile/stats-200.txt 2>&1
MSYS_NO_PATHCONV=1 docker run --rm --net=container:docker-market-worker-1 nicolaka/netshoot ss -tin 2>&1 | head -40 > .claude/state/profile/ss-200.txt
echo DONE200
