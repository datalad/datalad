#!/bin/bash

echo "127.0.0.1  datalad-test localhost" > /etc/hosts
apt-get install openssh-client
echo -e "Host localhost\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config
echo -e "Host datalad-test\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config
chmod 755 ~/.ssh
ssh-keygen -f /tmp/dl-test-ssh-id -N ""
cat /tmp/dl-test-ssh-id.pub >> ~/.ssh/authorized_keys
chmod 644 ~/.ssh/authorized_keys
eval $(ssh-agent)
ssh-add /tmp/dl-test-ssh-id


