#!/bin/sh

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
datalad create myanalysis


cd myanalysis

#datalad install --source https://github.com/psychoinformatics-de/studyforrest-data-structural.git src/forrest_structural
datalad install --source /tmp/studyforrest-data-structural src/forrest_structural

mkdir code

# just test data, could be
#datalad install src/forrest_structural/sub-*/anat/sub-*_T1w.nii.gz
echo "datalad install src/forrest_structural/sub-01/anat/sub-01_T1w.nii.gz" > code/get_required_data.sh
echo "nib-ls src/forrest_structural/sub-*/anat/sub-*_T1w.nii.gz > result.txt" > code/run_analysis.sh

datalad install --recursive yes --add-data-to-git code

datalad save "Initial analysis setup"

bash code/get_required_data.sh
bash code/run_analysis.sh

datalad install result.txt

datalad save "First analysis results"


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

datalad unlock
bash code/run_analysis.sh
datalad save -a "Alice always helps"


HOME=$BOBS_HOME
cd ~/myanalysis
datalad add-sibling alice $ALICES_HOME/bobs_analysis

datalad update alice --merge

datalad install result.txt

# total satisfaction is achieved -> public

#% EXAMPLE END

testEquality() {
  assertEquals 1 1
}

[ -n "$DATALAD_RUN_CMDLINE_TESTS" ] && . shunit2 || true
