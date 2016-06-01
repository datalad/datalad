#!/bin/bash

echo "127.0.0.1  datalad-test localhost" > /etc/hosts
apt-get install openssh-client
mkdir -p ~/.ssh
chmod 755 ~/.ssh
echo -e "Host localhost\n\tStrictHostKeyChecking no\n\tIdentityFile /tmp/dl-test-ssh-id\n" >> ~/.ssh/config
echo -e "Host datalad-test\n\tStrictHostKeyChecking no\n\tIdentityFile /tmp/dl-test-ssh-id\n" >> ~/.ssh/config
ssh-keygen -f /tmp/dl-test-ssh-id -N ""
cat /tmp/dl-test-ssh-id.pub >> ~/.ssh/authorized_keys
echo "DEBUG: Exit of cat: $?"
echo "DEBUG: $(ls -sl $HOME/.ssh/authorized_keys)"
chmod 644 ~/.ssh/authorized_keys
eval $(ssh-agent)
ssh-add /tmp/dl-test-ssh-id
echo "DEBUG: test connection ..."
ssh -v localhost exit
# don't wait for travis to timeout:
exit 1

