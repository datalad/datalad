#!/bin/bash

set -e -u

# configure
sed -e 's,/debian ,/debian-devel ,g' /etc/apt/sources.list.d/neurodebian.sources.list | sudo tee /etc/apt/sources.list.d/neurodebian-devel.sources.list
sudo apt-get update

# check versions
# devel:
devel_annex_version=$(apt-cache policy git-annex-standalone | grep -B1 '/debian-devel ' | awk '/ndall/{print $1;}')
current_annex_version=$(apt-cache policy git-annex-standalone | awk '/\*\*\*/{print $2}')

if dpkg --compare-versions "$devel_annex_version" gt "$current_annex_version"; then
    sudo apt-get install "git-annex-standalone=$devel_annex_version"
else
    echo "I: devel version $devel_annex_version is not newer than installed $current_annex_version"
    exit 1
fi
