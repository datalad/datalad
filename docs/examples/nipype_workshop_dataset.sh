#!/bin/bash
echo "
  This script is just a set of notes on how
  http://datasets.datalad.org/?dir=/workshops/nipype-2017/ds000114
  was prepared, and by default uses a bogus tarball.  Uncomment correct original
  URL if you want to do it 'for real'.

  You can install the final full dataset from our collection of datasets

      datalad install -r -g ///workshops/nipype-2017/ds000114

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
SUPERDATASET=$(readlink -f "$(mktemp --tmpdir -d datalad_demo_nipype.XXXX)")
# where we will have our dataset published
PUBLISHDIR=$(readlink -f "$(mktemp --tmpdir -d datalad_demo_nipype_published.XXXX)")
PUBLISHLOC=ssh://localhost$PUBLISHDIR

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
# A few tricky points which you do not necessarily would run into in a more
# typical workflow:
#
# - since branch is detached, it would be empty to start with, but we want to
#   preserve the settings within .gitattributes (such as git annex backend).
#   I could have just `git add .gitattributes`
#   after `checkout --orphan` but I haven't thought about that and created
#   a new file from scratch.
# - Original openfmri dataset did not have settings within .gitattributes to
#   add all text files straight into git, so I have added those settings within
#   a new .gitattributes . For more about settings git-annex understands
#   as to what files should it handled (`largefiles`) or otherwise just pass
#   to git to handle see https://git-annex.branchable.com/tips/largefiles/ .
#
#%

cat .gitattributes                  # sneak preview
git checkout --orphan nipype_test1  # generate a new detached branch
git clean -dfx                      # remove
git reset --hard                    # everything, to end up with super clean directory

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
# (see `issue 1416 <https://github.com/datalad/datalad/issues/1416>`__ if resolved already)
# So I have reverted to using git annex directly which uses wget which worked out
# correctly
#
#%

# download (~800MB) and add that file under git-annex without
git annex addurl --file=ds114_test1_with_freesurfer.tar.gz "$URL"

datalad save -m "Downloaded the tarball with derived data into annex"
datalad add-archive-content --delete --strip-leading-dirs ds114_test1_with_freesurfer.tar.gz

#%
# Above `add-archive-content` command extracted content from the archive, stripping
# leading directory, and added all extracted files under git/git-annex using
# those rules specified in `.gitattributes` file:
#
# - use MD5E (annex keys are based on md5 checksum with extension appended) backend
# - add text files directly under git control, so only binary files are added
#   under annex control and the entire repository's `.git/objects` is only around 30MB
#   while pointing to all openfmri releases, and this derived data
#
# Peering inside
# ===============
#
# Because I have reused original `///openfmri/ds000114` dataset, I have gained knowledge
# about all the files which originated from that dataset.  E.g. compare output of
# `whereis` command on `sub-01/anat` (which is also available from original openfmri)
# and derivatives:
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
#
# Adding dataset into bigger dataset
# ==================================
#
# Having succeeded with construction of the dataset, I have decided to share it
# as a part of our bigger super dataset at http://datasets.datalad.org .
# This dataset was the first workshop dataset which was not part of some bigger
# collection, so I have decided to establish a new :term:`subdataset` `workshops`
# within it, and move our nipy workshop superdataset into it.
#%

cd $SUPERDATASET
# since in demo we do not have anything there, let's clone our superdataset
datalad install ///
cd datasets*.datalad.org

# -redone because now datasets.datalad.org already has workshops dataset
# and datalad should refuse to create a new one (without removing old one first)
datalad create -d . workshops-redone  # create subdataset to hold various workshops datasets
cd workshops-redone
mv "$TOPDIR/nipype-workshop-2017" nipype-2017  # chose shorter name
# add it as a subdataset (git submodule) within
datalad add -d . nipype-2017

#%
# Adding meta-data descriptors for the dataset(s)
# ===============================================
#
# If you ever ran `datalad search <http://docs.datalad.org/en/latest/generated/man/datalad-search.html>`_
# you know that one of the goals of DataLad
# is to use :ref:`chap_metadata` associated with the datasets.
#%

# created some dataset_description.json (following BIDS format lazy me)
echo '{"Name": "Datasets for various workshops"}' > dataset_description.json
# add that file to git
datalad add --to-git --nosave dataset_description.json
# discover and aggregate all meta-data within workshops
datalad aggregate-metadata --guess-native-type --nosave -r
# and finally save all accumulated changes from above commands
# while also updating the topmost superdataset about this changes under 'workshops'
datalad save -S -m "Added dataset description and aggregated meta-data" -r
# go upstairs and aggregate meta-information across its direct datasets without recursing
# (since might take awhile)
cd ..
datalad aggregate-metadata --guess-native-type

#%
# Publishing
# ==========
#
# NB instructions here might diverge a little from what was actually performed
#
# Now it was time to publish this dataset as a part of our larger super-dataset.
# Because our demo superdataset is just a clone (or :term:`sibling`) of original
# one, it does not have information about where it must be published to. So
# we first can create a sibling on remote server where we want also to deploy our
# web-frontend and then create similar siblings for every
#%

datalad create-sibling --shared all \
   -s public --ui=true \
   --publish-by-default 'refs/heads/*' \
   --publish-by-default 'refs/tags/*' \
   "$PUBLISHLOC"

datalad create-sibling -s public --inherit -r --existing skip

#%
# By default DataLad does not publish any data, and in above create-sibling
# we also did not provide any `--annex-wanted` settings to instruct annex
# about what data should be published to our public sibling.
# So I decided to provide additional instructions for annex directly
# about what data files I want to be published online from our website.
# Since original files under `sub-*` subdirectories are available from original
# OpenfMRI S3 bucket, we really needed to publish only `derivatives/*` files, which
# we can describe via
#%

git -C workshops-redone/nipype-2017/ds000114 annex wanted public 'include=derivatives/*'

#%
# And now I was ready to publish changes to the entire collection of datasets
# with a set of files we decided to share
#%

datalad publish -r --to=public

#%
# Above commands created empty repositories for all the datasets we have locally
# and now I was ready to "publish" our datasets... Just a few final touches
#
# There is a <"shortcoming" `https://github.com/datalad/datalad/issues/1428`>__
# which was discovered just now, because it was the first time we published
# datasets from non-master branch (`nipype_test1`).  Default branch on the remote
# where we published is master, so we need to checkout nipype_test1 branch
# and re-run out hooks/post-update hook to re-generate meta-data for dataset
# listing on web-frontend.  Hopefully this portion of explanation will disappear
# with DataLad 0.5.1 or later ;-)
#%

(
  cd $PUBLISHDIR/workshops-redone/nipype-2017/ds000114
  git checkout nipype_test1
  # rerun the hook to regenerate meta-data for web-frontend
  cd .git;  hooks/post-update
)

#%
# If I do any future changes, and save them, it should be sufficient to just
# rerun this `publish` command (possibly even without explicit --to=public)
# and have all datasets updated online, with data files under `derivatives/`
# in that repository posted as well.
#
# Browsing
# ==========
#
# If the location where we published our datasets is served by any http
# server, they now could be used from that location by others, while having
# complete history of changes stored in annex, and data files available
# either from that location or from original openfmri S3 bucket.
#
# If you do not have published to location served by a web server, as the case in our
# demo script, we could easily start one using the one which comes with Python:
#%

if [ -z "$DATALAD_TESTS_RUNCMDLINE" ]; then   #% SKIP
cd "$PUBLISHDIR"
# Starting webserver
python -m SimpleHTTPServer 8080 1>/dev/null 2>&1 &
# we started webserver and can browse
PUBLISHURL=http://localhost:8080
browser=$(which x-www-browser 2>/dev/null)
if $browser; then
    echo "Opening browser to visit $PUBLISHURL which would allow to browse $PUBLISHDIR content"
    $browser $PUBLISHURL &
else
    echo "Visit http://localhost:8080 in your browser."
fi
echo "

On that page
Press Enter when you want to finish
"

in=$(read)
kill %2 && echo "stopped browser(?)" || :  # killing our browser job if any
kill %1 && echo "stopped server"
fi   #% SKIP

#%
# Since DataLad datasets are just git/git-annex repositories, we could as well
# publish them to multiple locations, including github.com, only without data.
# See `datalad-create-sibling-github <http://docs.datalad.org/en/latest/generated/man/datalad-create-sibling-github.html>`_
# and `--publish-depends` option to
# instruct to publish first to our public http server which will host the data
# and then to github.com for more visibility and collaboration.
#% EXAMPLE END

testEquality() {
  assertEquals 1 1
}

cd "$OLD_PWD"
[ -n "$DATALAD_TESTS_RUNCMDLINE" ] && . shunit2 || true
