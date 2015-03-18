#!/bin/sh
git clone https://github.com/datalad/testrepo--basic--r1.git repo
cd repo
git annex get test-annex.dat

# we need to remove the restrictive permission in order for the test harness
# to be able to delete the git-annex repo during tear down
chmod -R u+w .

