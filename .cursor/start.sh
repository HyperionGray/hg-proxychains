#!/usr/bin/env bash
set -euo pipefail

docker_available() {
  sudo docker info >/dev/null 2>&1
}

expose_docker_socket() {
  if [ -S /var/run/docker.sock ]; then
    sudo chgrp "$(id -gn)" /var/run/docker.sock
    sudo chmod 660 /var/run/docker.sock
  fi
}

if ! command -v docker >/dev/null 2>&1; then
  exit 0
fi

if docker_available; then
  expose_docker_socket
  exit 0
fi

if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl start docker >/dev/null 2>&1 || true
fi

if ! docker_available && command -v service >/dev/null 2>&1; then
  sudo service docker start >/dev/null 2>&1 || true
fi

if ! docker_available && command -v dockerd >/dev/null 2>&1; then
  if ! pgrep -x dockerd >/dev/null 2>&1; then
    nohup sudo dockerd --host=unix:///var/run/docker.sock >/tmp/dockerd.log 2>&1 &
  fi

  for _ in $(seq 1 30); do
    if docker_available; then
      expose_docker_socket
      exit 0
    fi

    sleep 1
  done

  echo "Docker daemon failed to start; see /tmp/dockerd.log" >&2
  exit 1
fi

if ! docker_available; then
  echo "Docker daemon is not available after startup." >&2
  exit 1
fi

expose_docker_socket
