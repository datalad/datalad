#!/bin/bash
set -eu

err="thread blocked indefinitely"

cd ~/QA
timeout 5 git annex get -J2 sub-* 2>&1 | tee annex-get-log.txt
if grep -q "$err" annex-get-log.txt; then
	echo "E: $err"
	exit 1
fi

