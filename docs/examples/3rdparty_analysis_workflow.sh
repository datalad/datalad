#!/bin/sh
# SKIP_IN_V6

set -e

OLD_PWD=$PWD
# BOILERPLATE

BOBS_HOME=$(readlink -f "$(mktemp --tmpdir -d datalad_demo_bob.XXXX)")
ALICES_HOME=$(readlink -f "$(mktemp --tmpdir -d datalad_demo_alice.XXXX)")

# Fake an SSH server on this machine for the purpose of this demo
SERVER_URL=localhost:$(readlink -f "$(mktemp --tmpdir -u -d datalad_demo_testpub.XXXX)")

#% EXAMPLE START
#
# A typical collaborative data management workflow 
# ************************************************

# In this demo we will look at how datalad can be used in a rather common data
# management workflow: A 3rd-party dataset is obtained to serve as input for an
# analysis. The data processing is then collaboratively performed by two
# colleagues. Upon completion the results are published alongside the original
# data for further consumption.
#
# Build atop 3rd-party data
# =========================
#
# Now, meet Bob. Bob has just started in the lab and has never used the version
# control system Git_ before. The first thing he does, is to configure his
# identity as it will be used to track changes in the datasets he will be
# working with.  This step only needs to be done once on his first day in the
# lab.
#%

# enter Bob's home directory
HOME="$BOBS_HOME"
cd ~
git config --global --add user.name Bob
git config --global --add user.email bob@example.com

#%
# After this initial setup, Bob is ready to go and can create his first
# :term:`dataset`.
#%

datalad create myanalysis --description "my phd in a day"
cd myanalysis

#%
# A datalad dataset can contain other datasets. As any content of a dataset is
# tracked and its precise state is recorded, this is a powerful method to
# specify and later resolve data dependencies. In this example, Bob wants to
# work with structural MRI data from the `studyforrest project`_, a public
# brain imaging data resource. These data are made available through GitHub_,
# so Bob can simply install the relevant dataset from this service and into
# his own dataset:
#
# .. _studyforrest project: http://studyforrest.org
# .. _github: https://github.com
#%

datalad install -d . --source https://github.com/psychoinformatics-de/studyforrest-data-structural.git src/forrest_structural

#%
# and see that the forrest_structural was registered as a git submodule, which
# is a :term:`subdataset` of his myanalysis dataset, but no data was fetched
# (``datalad ls -L`` provides size_installed/total_size column):
#%

# mostly for a test
grep src/forrest_structural .gitmodules
# to demonstrate ls
datalad ls -r -L .


#%
# Bob has decided to collect all data inputs for his project in a subdirectory
# ``src/``, to make it obvious which parts of his analysis steps and code
# require 3rd-party data. Upon completion of the above command, Bob has now
# access to the entire dataset content, and precise current version of that
# dataset got linked to his ``myanalysis``.  However, no data was actually
# downloaded (yet). DataLad datasets primarily contain information on a
# dataset's content and where to obtain it, hence the installation above was
# done rather quickly, and will still be relatively lean even for a dataset
# that contains several hundred GBs of data.
#
# For his first steps Bob just needs a single file of the dataset. In order to
# make it available locally, Bob can use the get command, and datalad
# will obtain requested data files from a remote data provider.
#%

datalad get src/forrest_structural/sub-01/anat/sub-01_T1w.nii.gz
# just test data for now, could be
#datalad get src/forrest_structural/sub-*/anat/sub-*_T1w.nii.gz

#%
# Although we originally installed the dataset from Github, the actual data is
# hosted elsewhere. DataLad supports multiple redundant data providers per each
# file in a dataset, and will transparently attempt to obtain data from an
# alternative location if a particular data provider is not available.
#
# Bob wants his analysis to be easily reproducible, and therefore manages his
# analysis scripts in the same dataset repository as the input data. Managing
# input data, analysis code, and results the same version control system
# creates a precise record of what version of code and input data was used to
# create which particular results. DataLad datasets are regular Git_
# repositories and therefore provide the same powerful source code management
# features, as any other Git_ repository, and make them available for data too.
#
# .. _Git: https://git-scm.com
#
# Bob decided to adopt the convention to collect all of his analysis code in a
# subdirectory ``code/`` in the root of his dataset. His first "analysis" script
# is rather simple:
#%

mkdir code
echo "file src/forrest_structural/sub-01/anat/sub-*_T1w.nii.gz > result.txt" > code/run_analysis.sh

#%
# In order to definitively document which data file his analysis needs at this
# point, Bob creates a second script that can (re-)obtain the required files:
#%

echo "datalad get src/forrest_structural/sub-01/anat/sub-01_T1w.nii.gz" > code/get_required_data.sh

#%
# In the future, this won't be necessary anymore as datalad itself will be able
# to record this information upon request.
#
# At this point Bob is satisfied with his initial progress. He wants to record
# this precise state. In order to do that, Bob needs to make his just created
# scripts a part of his dataset. Again the ``install`` command is used for this
# purpose. However, Bob doesn't just want datalad to track these files and
# facilitate future downloads. He wants all Git_ features for working with
# them, so he adds them directly to the Git repository underlying his dataset.
#%

# add all content in the code/ directory directly to git
datalad add --to-git code

#%
# At this point, datalad is aware of all changes that were made to the dataset
# and all the changes Bob made were automatically recorded, as you could easily
# check with ``git log`` command.
#
# As Bob's analysis is completely scripted, he can now run it in full:
#%

bash code/get_required_data.sh
bash code/run_analysis.sh

#%
# and add generated results to the dataset and provide a custom message to
# better describe accomplished work:
#%
datalad add  -m "First analysis results" result.txt

#%
# You could also use ``--nosave`` option with add, and invoke ``datalad save``
# later on to group multiple changes into a single commit.
#%

# git log

#%
# Local collaboration
# ===================
#
# Some time later, Bob needs help with his analysis. He turns to his colleague
# Alice for help. Alice and Bob both work on the same computing server. Alice
# initially went through a similar configuration procedure of her Git identity
# as Bob.
#% 

HOME="$ALICES_HOME"
cd
git config --global --add user.name Alice
git config --global --add user.email alice@example.com

#%
# Bob has told Alice in which directory he keeps his analysis dataset. The
# colleagues' directories are configured to have permissions that allow for
# read-access for all lab-member, so Alice can obtain Bob's work directly
# from his home directory, including the ``studyforrest-structural``
# :term:`subdataset` he had:
#%
# TODO: needs to get --description to avoid confusion
datalad install -r --source "$BOBS_HOME/myanalysis" bobs_analysis
cd bobs_analysis

#%
# At this point, Alice has a complete copy of Bob's entire dataset in the exact
# same state that Bob last saved. She is free to make any changes without
# affecting Bob's version of the dataset. Initially, all the datasets are as
# lightweight as possible.
#%

#%
# With the script Bob created, Alice can obtain all required data content. DataLad
# knows that necessary file is available in Bob's version of the dataset on the
# same machine, so it won't even attempt to download it from its original location.
#%

bash code/get_required_data.sh

#%
# Likewise, Alice can use datalad to obtain the results that Bob had generated.
#%

datalad get result.txt
#cat result.txt

#%
# She can modify Bob's code to help him with his analysis...
#%

echo "file src/forrest_structural/sub-*/anat/sub-*_T1w.nii.gz > result.txt" > code/run_analysis.sh

#%
# ... and execute it.
#%
# `|| true` is only there for the purpose of testing this script
bash code/run_analysis.sh || true

#%
# However, when she performs actions that attempt to modify data files managed by
# datalad she will get an error. DataLad, by default, prevents modification of
# data files. If modification is desired (as in this case), datalad can *unlock*
# individual files, or the entire dataset. Afterwards modifications are
# possible.
#%

# unlock the entire dataset
datalad unlock
bash code/run_analysis.sh

#%
# Once Alice is satisfied with her modifications she can save the new state.
#%
# -a make datalad auto-detect modifications
datalad save -u -m "Alice always helps"

#%
# Full circle
# ===========

# Now that Alice has improved Bob's analysis, Bob wants to obtain the changes
# she made. To achieve that, he registers Alice's version of the dataset as a
# :term:`sibling`.  As both are working on the same machine, Bob can just point
# to the respective directory, but it would also be possible to refer to a
# dataset via an http URL, or an SSH login and path.
#%

HOME="$BOBS_HOME"
cd ~/myanalysis
datalad siblings add -s alice --url "$ALICES_HOME/bobs_analysis"

#%
# Once registered, Bob can update his dataset based on Alice's version, and merge
# here changes with his own.
#%

datalad update -s alice --merge

#%
# He can, once again, use the ``get`` command to obtain the latest version
# of data files to get access to data contributed by Alice.
#%

datalad get result.txt

#%
# Going public
# ============

# Lastly, let's assume that Bob completed his analysis and he is ready to share
# the results with the world, or a remote collaborator. One way to make
# datasets available, is to upload them to a webserver via SSH. DataLad
# supports this by creating a :term:`sibling` for the dataset on the server,
# to which the dataset can by published (repeatedly).
#%

# this generated sibling for the dataset and all subdatasets
datalad create-sibling --recursive -s public "$SERVER_URL"

#%
# Once the remote sibling is created and registered under the name "public",
# Bob can publish his version to it.
#%

datalad publish -r --to public .

#%
# This command can be repeated as often as desired. DataLad checks the state
# of both the local and the remote sibling and transmits the changes.
#%

#% EXAMPLE END

testEquality() {
  assertEquals 1 1
}

cd "$OLD_PWD"
[ -n "$DATALAD_TESTS_RUNCMDLINE" ] && . shunit2 || true
