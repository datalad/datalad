#!/bin/sh
git clone http://psydata.ovgu.de/forrest_gump/.git repo
cd repo
git annex get stimulus/task001/annotations/scenes.csv

# we need to remove the restrictive permission in order for the test harness
# to be able to delete the git-annex repo during tear down
chmod -R u+w .

