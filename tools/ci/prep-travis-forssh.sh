#!/bin/bash

echo "127.0.0.1  datalad-test localhost" > /etc/hosts
apt-get install openssh-client
echo -e "Host localhost\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config
echo -e "Host datalad-test\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config
echo "DEBUG: /etc/ssh/sshd_config:"
cat /etc/ssh/sshd_config
chmod 755 ~/.ssh
ssh-keygen -f /tmp/dl-test-ssh-id -N ""
cat /tmp/dl-test-ssh-id.pub >> ~/.ssh/authorized_keys
chmod 644 ~/.ssh/authorized_keys
echo "DEBUG: ssh-agent"
eval $(ssh-agent)
echo "DEBUG: Exit: $?"
echo "DEBUG: ssh-add"
ssh-add
echo "DEBUG: Exit: $?"

