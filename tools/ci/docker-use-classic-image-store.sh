#!/bin/bash
# Switch the Docker daemon to its classic (non-containerd) image store.
#
# Docker >= 29 defaults to the containerd image store, under which the docker
# adapter of datalad-container does not find the images it loads (their IDs
# are no longer the digests of their configurations), so its tests fail.
# Docker 29 still provides the classic image store, so use that until the
# adapter supports the containerd one.
#
# Must be run as root (e.g. via sudo): edits /etc/docker/daemon.json and
# restarts the daemon.
set -eu -o pipefail

daemon_json=/etc/docker/daemon.json

version=$(docker version --format '{{.Server.Version}}')

if [ -f "$daemon_json" ]; then
    echo "I: original $daemon_json:"
    cat "$daemon_json"
else
    echo '{}' > "$daemon_json"
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
jq '.features["containerd-snapshotter"] = false' "$daemon_json" > "$tmp"
cat "$tmp" > "$daemon_json"

systemctl restart docker

docker info --format 'Docker {{.ServerVersion}}, storage driver {{.Driver}}'
if docker info --format '{{json .DriverStatus}}' | grep -q io.containerd.snapshotter; then
    echo "::error::Docker $version still uses the containerd image store"
    exit 1
fi
if [ "${version%%.*}" -ge 29 ]; then
    echo "::warning::Docker $version defaults to the containerd image store, which the docker adapter of datalad-container does not support yet; testing with the classic image store"
fi
