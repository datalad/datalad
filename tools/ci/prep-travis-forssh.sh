#!/bin/bash

mkdir -p ~/.ssh
echo -e "Host localhost\n\tStrictHostKeyChecking no\n\tIdentityFile /tmp/dl-test-ssh-id\n" >> ~/.ssh/config
echo -e "Host datalad-test\n\tStrictHostKeyChecking no\n\tIdentityFile /tmp/dl-test-ssh-id\n" >> ~/.ssh/config
ssh-keygen -f /tmp/dl-test-ssh-id -N ""
cat /tmp/dl-test-ssh-id.pub >> ~/.ssh/authorized_keys
eval $(ssh-agent)
ssh-add /tmp/dl-test-ssh-id

echo "DEBUG: test connection to localhost ..."
ssh -v localhost exit
echo "DEBUG: test connection to datalad-test ..."
ssh -v datalad-test exit

# tmp: don't run the actual tests:
# exit 1



