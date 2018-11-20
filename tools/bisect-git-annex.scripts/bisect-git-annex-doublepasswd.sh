#!/bin/bash
set -eu

err="thread blocked indefinitely"

cd ~/QA
# script doesn't work in  a script since probably no tty
timeout 10 script -f -c 'git annex get -J2 sub-*' || :
test 1 -eq `sed -e 's, ,\n,g' typescript | grep -c 'password:' `
