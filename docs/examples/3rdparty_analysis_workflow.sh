#!/bin/sh

set -u
set -e

# BOILERPLATE

BOBS_HOME=$(readlink -f $(mktemp -d datalad_demo.XXXX))
ALICES_HOME=$(readlink -f $(mktemp -d datalad_demo.XXXX))

#% EXAMPLE START

#% Build atop of 3rd-party data
#% ============================
#%
#% This example shows how datalad can be used to obtain a 3rd-party dataset and
#% use it as input for an analysis. Moreover, it demonstrates how two local
#% collaborators can contribute to this analysis, each using their own copy
#% of the dataset, but at the same time, being able to easily share their results
#% back and forth.

HOME=$BOBS_HOME

cd
pwd
git config --global --add user.name Bob
git config --global --add user.email bob@example.com

# will become: datalad create myanalysis --description "my phd in a day"
datalad install myanalysis


cd myanalysis

datalad install --source https://github.com/psychoinformatics-de/studyforrest-data-structural.git src/forrest_structural

mkdir code

# just test data, could be
#datalad install src/forrest_structural/sub-*/anat/sub-*_T1w.nii.gz
echo "datalad install src/forrest_structural/sub-01/anat/sub-01_T1w.nii.gz" > code/get_required_data.sh
echo "nib-ls src/forrest_structural/sub-*/anat/sub-*_T1w.nii.gz > result.txt" > code/run_analysis.sh

datalad install --recursive yes --add-data-to-git code

# will become: datalad make-memory-engram
git commit -m "Initial analysis setup"

bash code/get_required_data.sh
bash code/run_analysis.sh

datalad install result.txt

# will become: datalad make-memory-engram
git commit -m "First analysis results"


# 1. use case: lab colleague wants to work in the same analysis, on the same machine/cluster
HOME=$ALICES_HOME
cd
git config --global --add user.name Alice
git config --global --add user.email alice@example.com

#% we are the colleague now!
# TODO: needs to get --description to avoid confusion
datalad install --source $BOBS_HOME/myanalysis bobs_analysis

cd bobs_analysis
datalad install --recursive yes .
# pulls the data from the local source!
bash -x code/get_required_data.sh

datalad install result.txt
#cat result.txt

echo "file -L src/forrest_structural/sub-*/anat/sub-*_T1w.nii.gz > result.txt" > code/run_analysis.sh

bash code/run_analysis.sh ||true

git annex unlock
bash code/run_analysis.sh
git commit -a -m "Alice always helps"


HOME=$BOBS_HOME
cd ~/myanalysis
datalad add-sibling alice $ALICES_HOME/bobs_analysis

# datalad update failes:
#% datalad update alice
#2016-06-09 13:59:52,338 [INFO   ] Updating handle '/tmp/datalad_demo.PU2F/myanalysis' ... (update.py:125)
#2016-06-09 13:59:52,391 [ERROR  ] Failed to run ['git', '-c', 'receive.autogc=0', '-c', 'gc.auto=0', 'config', '--get', 'branch.master.remote'] under '/tmp/datalad_demo.PU2F/myanalysis'. Exit code=1. out= err= (cmd.py:295)
#
git pull alice master
git fetch alice
git annex merge

datalad install result.txt

