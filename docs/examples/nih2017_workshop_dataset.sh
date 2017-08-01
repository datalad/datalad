#!/bin/bash
echo "
  This script is just a set of notes on how
  http://datasets.datalad.org/?dir=/workshops/nih-2017/ds000114
  was prepared, and by default uses a bogus tarball.  Uncomment correct original
  URL if you want to do it 'for real'.

  You can install the final full dataset from our collection of datasets

      datalad install -r -g ///workshops/nih-2017/ds000114

  which will fetch data from wherever it is available from.
"

set -e

# due to https://github.com/datalad/datalad/issues/1432
SKIP_IN_DIRECT=1

OLD_PWD=$PWD
TOPDIR=$(readlink -f "$(mktemp --tmpdir -d datalad_demo_nipype.XXXX)")
# In general it is our location for http://datasets.datalad.org on the development
# server, but for the purpose of the demo -- we will install our super dataset
# into a temporary directory
# SUPERDATASET=$(readlink -f "$(mktemp --tmpdir -d datalad_demo_nipype.XXXX)")
# where we will have our dataset published
# PUBLISHDIR=$(readlink -f "$(mktemp --tmpdir -d datalad_demo_nipype_published.XXXX)")
# PUBLISHLOC=ssh://localhost$PUBLISHDIR

cd "$TOPDIR"

# BOILERPLATE

# Original URL
#URL=https://files.osf.io/v1/resources/9q7dv/providers/osfstorage/57e54a106c613b01d9d3ed7d
# but for testing I came up with a smaller example
# URL=http://www.onerussian.com/tmp/fake_ds114.tar.gz

#% EXAMPLE START
#
# Creating a "new" derived dataset for NIH workshop
# ****************************************************
#
# For more information about the workshop, please visit
# http://nipy.org/workshops/2017-03-boston/index.html .
# As we will present git-annex and DataLad, I have decided to prepare a DataLad
# :term:`dataset` from the tarball Satrajit Ghosh has shared URL to.  That tarball
# is a trimmed down version of OpenfMRI_ ds000114_
# dataset which we also crawl and provide as a
# `DataLad dataset <http://datasets.datalad.org/?dir=/openfmri/ds000114>`__.
#
# .. _OpenfMRI: https://openfmri.org
# .. _ds000114: https://openfmri.org/dataset/ds000114/
#
# Deriving (cloning) a dataset
# ============================
#
# I have decided to first create a :term:`superdataset` for the workshop (may be
# more datasets besides ds114 will be later) outside of our master :term:`superdataset`
# which we distribute from http://datasets.datalad.org .
# So I just created a new :term:`dataset` in a random directory.
# I wanted our ds114 dataset to be "derived" from original openfmri ds000114 dataset
# so we could readily reuse all the knowledge git-annex has about where files
# might be coming from. To achieve that I have just installed existing ds000114 dataset
# into our :term:`superdataset`:
#
#%

# Create dataset
datalad create --no-annex nih-workshop-2017
cd nih-workshop-2017
datalad install -d . ///openfmri/ds000114
cd ds000114

#%
#
# What was desired for this dataset, is to enrich it with derivative data --
# results from preprocessing.  To minimize effect on this dataset, since
# derivative data might be large in the number of files, and not necessarily
# desired to be even available for some users, we will organize those preprocessed
# data as subdatasets.
# Since fmriprep output contains summary reports, which could be immediately
# useful to review etc without fetching any additional data files, and in general
# they aren't overwhelmingly large, we will add all text files directly to git
# without annexing them within fmriprep subdataset (`--text-no-annex` option
# available since DataLad 0.8).  This option creates in that dataset `.gitattributes`
# file prescribing for text files (according to the autodetected MIME type)
# being not treated as largefiles, which would be committed to git directly
#
#%

# datalad create -d . --text-no-annex derivatives/fmriprep
datalad create -d . derivatives/fmriprep
datalad create -d . derivatives/freesurfer

#%
#
# TODO: example -d . and submodules here.
#
# And you can use `datalad ls` to visualize current structure of the datasets
#
#%

datalad ls -r -L .

#%
#
# Adding new content from tarballs off the openneuro
# ==================================================
#
# Satra has provided a file with file paths and URLs pointing to files on
# DropBox.  Since I wanted to perform all operations in cmdline, the task
# was to shape them up from json records like
#
#   [
#    "/shares/db81c46c-1908-4bfd-85b3-9fa1284093ab/fmriprep/sub-01/anat/sub-01_t1w_inflated.l.surf.gii",
#    "https://www.dropbox.com/s/11es9f8sw4gkv4m/sub-01_t1w_inflated.l.surf.gii?dl=0"
#   ],
#
# to correct paths and urls (starting with dl. instead of www.) ready for
# download and being added to the datasets.  Following command invoking
# Python to use json module to load the records converted such records as above
# into  dataset path url  triplets, such as
#
#    freesurfer sub-10/touch/rusage.mris_sphere.lh.dat https://dl.dropbox.com/s/av6628b33kz1f09/rusage.mris_sphere.lh.dat?dl=0
#
# Note: there are plans to provide DataLad helper to make such things
# easier/possible without such ad-hoc helpers:
# https://github.com/datalad/datalad/issues/1665
#
#%

python -c 'import json; print "\n".join([l[0].split("/")[3] + " " + "/".join(l[0].split("/")[4:]) + " " + l[1].replace("www.dropbox", "dl.dropbox") for l in json.load(open("nih2017_workshop_dataset_urls.json"))])' >| nih2017_workshop_dataset_urls.txt

#%
#
# Now it became easy to go file by file and add them to annex
# pointing to the corresponding url.
#
#%
wget -O- -q http://www.onerussian.com/tmp/nih2017_workshop_dataset_urls.txt \
| while read ds p url; do \
    git -C derivatives/$ds -c annex.alwayscommit=false annex addurl --file=$p $url; \
done

#%
#
# `-c annex.alwayscommit=false` was specified to make annex delay committing changes
# about where files are available from to `git-annex` branch until later, to not
# generate 4,000 commits (one per each file).
#
# After all files were added to git/annex it was time to save all the changes in those
# datasets, and recursive operation of datalad commands helped to achieve that
#
#%

datalad save -m "Fetched files from dropbox urls" -u -r
