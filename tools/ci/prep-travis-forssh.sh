#!/bin/bash

echo "127.0.0.1  datalad-test localhost" > /etc/hosts
apt-get install openssh-client
echo -e "Host localhost datalad-tests\n\tNoHostAuthenticationForLocalhost yes" >> ~/.ssh/config
ssh-keygen -f /tmp/dl-test-ssh-id -N ""
cat /tmp/dl-test-ssh-id.pub >> ~/.ssh/authorized_keys
chmod og-wx ~/.ssh/authorized_keys
#ssh-keyscan -H localhost >> ~/.ssh/known_hosts
#ssh-keyscan -H datalad-test >> ~/.ssh/known_hosts
#echo -ne '\n' | ssh-copy-id -i /tmp/dl-test-ssh-id localhost
#echo -ne '\n' | ssh-copy-id -i /tmp/dl-test-ssh-id datalad-test
