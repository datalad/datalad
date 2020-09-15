#!/bin/bash
set -eu

mkdir -p "$HOME/.ssh"

cat >>"$HOME/.ssh/config" <<'EOF'

Host datalad-test
HostName localhost
Port 42241
User dl
StrictHostKeyChecking no
IdentityFile /tmp/dl-test-ssh-id
EOF

cat >>"$HOME/.ssh/config" <<'EOF'

Host datalad-test2
HostName localhost
Port 42242
User dl
StrictHostKeyChecking no
IdentityFile /tmp/dl-test-ssh-id
EOF

ssh-keygen -f /tmp/dl-test-ssh-id -N ""

curl -fSsL \
     https://raw.githubusercontent.com/datalad-tester/docker-ssh-target/master/setup \
     >setup-docker-ssh
sh setup-docker-ssh --key=/tmp/dl-test-ssh-id.pub -2 \
   --from=dataladtester/docker-ssh-target:latest

# FIXME: This is hacky and likely too long, but we need to sleep at least a
# little.
sleep 8
ssh -v datalad-test exit
ssh -v datalad-test2 exit
