#!/usr/bin/env bash
echo "
  For now this script is just a set of notes on how
  http://datasets.datalad.org/?dir=/workshops/nipype-2017/ds000114
  was prepared.  You can install it now using

  datalad install -r -g ///workshops/nipype-2017/ds000114
"

exit 0

set -e

#%
#
# Initially I have decided to create a dataset outside of our big collection
# of datasets which we distribute from http://datasets.datalad.org.
# I wanted dataset to be "derived" from original openfmri ds000114 dataset
# so we could readily reuse all the knowledge git-annex has about where files
# might be coming from.
#
#%

# Create dataset
datalad create --no-annex nipype-workshop-2017
cd nipype-workshop-2017
datalad install -d . ///openfmri/ds000114
cd ds000114

#%
#
# To make both openfmri and this derived dataset accessible from the same repo
# I decided just to generate a detached branch (since I did not know at that
# point on which version of openfmri it is based on). And then add content
# from the tarball available from the OSF.
# A few tricky points:
#
# - since branch is detached, it would be empty, but we want to preserve the
#   settings within .gitattributes (such as git annex backend).
#   I could have just "git add .gitattributes"
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
git annex addurl --file=ds114_test1_with_freesurfer.tar.gz \
    https://files.osf.io/v1/resources/9q7dv/providers/osfstorage/57e54a106c613b01d9d3ed7d
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
#
# Because I have reused original ///openfmri/ds000114 dataset, I have gained knowledge
# about all the files which originated from that dataset.  E.g. compare output of
# whereis command on sub-01/anat (which is also available from original openfmri)
# and derivatives:
#
#%

git annex whereis sub-01/anat
git annex whereis derivatives

#%
#
# and you can see that derivatives are available only locally or from "magical"
# datalad-archives remote which refers to the original tarball.  So, even if
# we drop those files locally, they could get extracted from the tarball. And
# even if you do not have a tarball, git-annex would happily first download it
# from the OSF website for you.
#
#%