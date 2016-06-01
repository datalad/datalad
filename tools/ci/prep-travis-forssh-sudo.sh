#!/usr/bin/env bash

echo "127.0.0.1  datalad-test" >> /etc/hosts
###### why "ssh: Could not resolve hostname datalad-test: Name or service not known"?
echo "DEBUG:"
cat /etc/hosts
apt-get install openssh-client
echo "DEBUG:"
cat /etc/hosts
exit 1
######