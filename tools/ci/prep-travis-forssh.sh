#!/bin/bash

echo "127.0.0.1  test99" > /etc/hosts
apt-get install openssh-client
ssh-keygen


