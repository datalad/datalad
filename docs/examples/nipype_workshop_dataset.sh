#!/bin/bash
echo "
  This script is just a set of notes on how
  http://datasets.datalad.org/?dir=/workshops/nipype-2017/ds000114
  was prepared, and by default uses a bogus tarball.  Uncomment correct original
  URL if you want to do it 'for real'.

  You can install result dataset from our collection of datasets

      datalad install -r -g ///workshops/nipype-2017/ds000114

  which will fetch data from wherever it is available from.
"

set -e

OLD_PWD=$PWD
TOPDIR=$(readlink -f "$(mktemp --tmpdir -d datalad_demo_nipype.XXXX)")
cd "$TOPDIR"

# BOILERPLATE

# Original URL
#URL=https://files.osf.io/v1/resources/9q7dv/providers/osfstorage/57e54a106c613b01d9d3ed7d
# but for testing I came up with a smaller example
URL=http://www.onerussian.com/tmp/fake_ds114.tar.gz

#% EXAMPLE START
#
# Creating a "new" derived dataset for Nipype workshop
# ****************************************************
#
# For more information about the workshop, please visit
# http://nipy.org/workshops/2017-03-boston/index.html .
# As we will present git-annex and DataLad, I have decided to prepare a DataLad
# :term:`dataset` from the tarball Satrajit Ghosh has shared URL to.  That tarball
# is a trimmed down version of [OpenfMRI ds000114](https://openfmri.org/dataset/ds000114/)
# dataset which we also crawl and provide as a
# [DataLad dataset](http://datasets.datalad.org/?dir=/openfmri/ds000114).
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
datalad create --no-annex nipype-workshop-2017
cd nipype-workshop-2017
datalad install -d . ///openfmri/ds000114
cd ds000114

#%
#
# To make both original and this derived dataset accessible from the same repo
# I generated a detached branch (since I did not know at that
# point on which version of openfmri it is based on). And then added content
# from the tarball available from the OSF.
#
# A few tricky points:
#
# - since branch is detached, it would be empty to start with, but we want to
#   preserve the settings within .gitattributes (such as git annex backend).
#   I could have just `git add .gitattributes`
#   after `checkout --orphan` but I haven't thought about that and created
#   a new file from scratch.
# - Original openfmri dataset did not have settings within .gitattributes to
#   add all text files straight into git, so I have added those settings within
#   a new .gitattributes
#
#%

cat .gitattributes                  # sneak preview
git checkout --orphan nipype_test1  # generate a branch new detached branch
git clean -dfx                      # remove anything
git reset --hard                    # and everything, to end up with super clean directory

#  I did vim .gitattributes, but replacing here with echo
echo -e "* annex.backend=MD5E
* annex.largefiles=(not(mimetype=text/*))
" > .gitattributes

datalad add --to-git .gitattributes  # storing this file within git, default commit msg

#%
#
# Adding new content from a tarball off the web
# =============================================
#
# Next goal was to download and add to annex the tarball Satra prepared for
# the workshop, and add its content under git-annex control.
# In datalad we have 'download-url' command, BUT unfortunately it has failed
# to download via https for this website
# (see https://github.com/datalad/datalad/issues/1416 if resolved already)
# So I have reverted to using git annex directly which uses wget which worked out
# correctly
#
#%

# download (~800MB) and add that file under git-annex without
git annex addurl --file=ds114_test1_with_freesurfer.tar.gz "$URL"

datalad save -m "Downloaded tarball from Satra"
datalad add-archive-content --delete --strip-leading-dirs ds114_test1_with_freesurfer.tar.gz

#%
#
# Above `add-archive-content` command extracted content from the archive, stripping
# leading directory, and added all extracted files under git/git-annex using
# those rules specified in .gitattributes file:
#
# - use MD5E (annex keys are based on md5 checksum with extension appended) backend
# - add text files directly under git control, so only binary files are added
#   under annex control and the entire repository's .git/objects is only around 30MB
#   while pointing to all openfmri releases, and this derived data
#%

#%
# Peering inside
# ===============
#
# Because I have reused original ///openfmri/ds000114 dataset, I have gained knowledge
# about all the files which originated from that dataset.  E.g. compare output of
# whereis command on sub-01/anat (which is also available from original openfmri)
# and derivatives:
#
#%

# in case of a fake tarball, output will not be very interesting
git annex whereis sub-01/anat
git annex whereis derivatives

#%
# and you can see that derivatives are available only locally or from "magical"
# datalad-archives remote which refers to the original tarball.  So, even if
# we drop those files locally, they could get extracted from the tarball. And
# even if you do not have a tarball, git-annex would happily first download it
# from the OSF website for you.
#%
#% EXAMPLE END

testEquality() {
  assertEquals 1 1
}

cd "$OLD_PWD"
[ -n "$DATALAD_TESTS_RUNCMDLINE" ] && . shunit2 || true
