#!/bin/bash

echo "127.0.0.1  datalad-test" > /etc/hosts
apt-get install openssh-client
echo -ne '\n\n' | ssh-keygen


