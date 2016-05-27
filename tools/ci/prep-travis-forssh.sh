#!/bin/bash

echo "127.0.0.1  datalad-test" > /etc/hosts
apt-get install openssh-client
ssh-keygen -f /tmp/dl-test-ssh-id -N ""
ssh-keyscan -H localhost >> ~/.ssh/known_hosts
ssh-keyscan -H datalad-test >> ~/.ssh/known_hosts
ssh-copy-id -i /tmp/dl-test-ssh-id localhost
ssh-copy-id -i /tmp/dl-test-ssh-id datalad-test