#!/bin/bash

echo "127.0.0.1  datalad-test localhost" > /etc/hosts
apt-get install openssh-client
ssh-keygen -f /tmp/dl-test-ssh-id -N ""
ssh-keyscan -H localhost >> ~/.ssh/known_hosts
ssh-keyscan -H datalad-test >> ~/.ssh/known_hosts
echo -ne '\n' | ssh-copy-id -i /tmp/dl-test-ssh-id localhost
echo -ne '\n' | ssh-copy-id -i /tmp/dl-test-ssh-id datalad-test
