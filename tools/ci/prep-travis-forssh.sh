#!/bin/bash

echo "127.0.0.1  datalad-test localhost" > /etc/hosts
apt-get install openssh-client
echo "DEBUG:"
ls -al ~/.ssh
echo -e "Host localhost\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config
echo -e "Host datalad-test\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config
echo "DEBUG:"
ls -al ~/.ssh
ssh-keygen -f /tmp/dl-test-ssh-id -N ""
ssh-copy-id -i /tmp/dl-test-ssh-id localhost
ssh-copy-id -i /tmp/dl-test-ssh-id datalad-test
#cat /tmp/dl-test-ssh-id.pub >> ~/.ssh/authorized_keys
#chmod og-wx ~/.ssh/authorized_keys
#ssh-keyscan -H localhost >> ~/.ssh/known_hosts
#ssh-keyscan -H datalad-test >> ~/.ssh/known_hosts
