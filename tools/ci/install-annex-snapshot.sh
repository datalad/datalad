#!/bin/bash

_ANNEXDIR=/usr/local/lib/git-annex.linux
(
set -eu

if [ -e "$_ANNEXDIR" ]; then
    echo "I: removing previous version of annex from $_ANNEXDIR"
    rm -rf "$_ANNEXDIR"
fi
echo "I: downloading and extracting under $_ANNEXDIR"
tar -C $(dirname $_ANNEXDIR) -xzf <(
  wget -q -O- https://downloads.kitenet.net/git-annex/linux/current/git-annex-standalone-amd64.tar.gz
)
)

echo "I: You should have either sourced this file or adjust PATH=$_ANNEXDIR:\$PATH"
export PATH=$_ANNEXDIR:$PATH
unset _ANNEXDIR
