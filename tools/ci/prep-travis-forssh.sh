#!/bin/bash
set -eu

mkdir -p "$HOME/.ssh"

if command -V docker-machine &> /dev/null
then docker_host="$(docker-machine inspect --format='{{.Driver.IPAddress}}' default)"
else docker_host=localhost
fi

# Upstream `setup-docker-ssh` hardcodes 42241 (datalad-tests-ssh) and 42242
# (datalad-tests-ssh2).  GitHub runners occasionally have one of those
# ports already bound when the job starts, in which case `docker run -p`
# bails out with `address already in use` (cron 25247128617's collide job
# on 2026-05-02 is one such case).  Diagnose, clean up any partial state,
# and retry a few times.
DL_SSH_PORT1=42241
DL_SSH_PORT2=42242

# Print whatever is currently bound to the given TCP port (best-effort,
# uses whichever of ss / lsof / fuser is available).
report_port_user() {
    local port="$1"
    echo "Diagnostics for TCP port $port:"
    if command -v ss > /dev/null 2>&1
    then sudo ss -tlnp "sport = :$port" 2>/dev/null || ss -tlnp "sport = :$port" 2>/dev/null || true
    fi
    if command -v lsof > /dev/null 2>&1
    then sudo lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    fi
    if command -v fuser > /dev/null 2>&1
    then sudo fuser -nv tcp "$port" 2>&1 || true
    fi
    docker ps --filter "publish=$port" 2>/dev/null || true
}

# True iff every named TCP port is currently free on the host.
ports_free() {
    local p
    for p in "$@"
    do
        if (echo > "/dev/tcp/127.0.0.1/$p") 2>/dev/null
        then return 1
        fi
    done
    return 0
}

cat >>"$HOME/.ssh/config" <<EOF

Host datalad-test
HostName $docker_host
Port $DL_SSH_PORT1
User dl
StrictHostKeyChecking no
IdentityFile /tmp/dl-test-ssh-id
EOF

cat >>"$HOME/.ssh/config" <<EOF

Host datalad-test2
HostName $docker_host
Port $DL_SSH_PORT2
User dl
StrictHostKeyChecking no
IdentityFile /tmp/dl-test-ssh-id
EOF

ls -l "$HOME/.ssh"
chmod go-rwx -R "$HOME/.ssh"
ls -ld "$HOME/.ssh"
ls -l "$HOME/.ssh"

ssh-keygen -f /tmp/dl-test-ssh-id -N ""

curl -fSsL \
     https://raw.githubusercontent.com/datalad-tester/docker-ssh-target/master/setup \
     >setup-docker-ssh

# Retry the docker container setup if it fails on a port collision.  On
# each retry, log the offender so we can tell whether GH runners are
# leaking a service on 4224[12] or whether a previous attempt left a
# stale container behind.
max_attempts=3
attempt=0
until [ "$attempt" -ge "$max_attempts" ]
do
    attempt=$((attempt + 1))

    if ! ports_free "$DL_SSH_PORT1" "$DL_SSH_PORT2"
    then
        echo "Pre-flight: TCP port $DL_SSH_PORT1 or $DL_SSH_PORT2 already in use (attempt $attempt/$max_attempts)" >&2
        report_port_user "$DL_SSH_PORT1"
        report_port_user "$DL_SSH_PORT2"
        # Wipe any datalad-tests-ssh* containers from a previous attempt
        # so the next `setup-docker-ssh` invocation does not refuse with
        # "datalad-tests-ssh* container(s) already running".
        docker rm -f datalad-tests-ssh datalad-tests-ssh2 2>/dev/null || true
        sleep 5
        if ! ports_free "$DL_SSH_PORT1" "$DL_SSH_PORT2"
        then
            if [ "$attempt" -lt "$max_attempts" ]
            then
                echo "Ports still busy, waiting and retrying..." >&2
                sleep 10
                continue
            else
                echo "Ports still busy after $max_attempts attempts, giving up" >&2
                exit 1
            fi
        fi
    fi

    if sh setup-docker-ssh --key=/tmp/dl-test-ssh-id.pub -2
    then break
    fi

    echo "setup-docker-ssh failed on attempt $attempt/$max_attempts" >&2
    report_port_user "$DL_SSH_PORT1"
    report_port_user "$DL_SSH_PORT2"
    docker rm -f datalad-tests-ssh datalad-tests-ssh2 2>/dev/null || true

    if [ "$attempt" -ge "$max_attempts" ]
    then
        echo "setup-docker-ssh failed after $max_attempts attempts" >&2
        exit 1
    fi
    sleep 10
done

tries=60
n=0
while true
do nc -vz "$docker_host" "$DL_SSH_PORT1" && nc -vz "$docker_host" "$DL_SSH_PORT2" && break
   ((n++))
   if [ "$n" -lt "$tries" ]
   then sleep 1
   else exit 1
   fi
done

ssh -v datalad-test exit
ssh -v datalad-test2 exit
