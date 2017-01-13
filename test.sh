#!/bin/sh

set -eu

d=/tmp/dataladt123

mkdir -p $d
cd $d
git init
echo "123" > 123
git add 123
git commit -m 'just so we have something' -a

echo 124 > 124
git add  124
'git' '-c' 'receive.autogc=0' '-c' 'gc.auto=0' 'commit' '-m' '[DATALAD] added content' $d/124

echo "worked fine"
