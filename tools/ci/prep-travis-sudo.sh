#!/usr/bin/env bash

# we need a UTF locale for DataLad to work properly
apt-get -y install locales
echo "en_US.UTF-8 UTF-8" >| /etc/locale.gen
locale-gen
