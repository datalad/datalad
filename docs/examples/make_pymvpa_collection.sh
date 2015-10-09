#!/bin/sh
# A little script to prepare PyMVPA demo collection based on data used in
# tutorials etc

set -eu

# new plain collection
echo "I: creating PyMVPA collection"
datalad create-collection pymvpa_collection pymvpa # path name

cd pymvpa_collection

echo "I: describing collection"
datalad describe \
    --author "DataLad AKA PyMVPA Team" \
    --license 'CC0' \
    --description "Collection of datasets useful for PyMVPA demonstrations and tutorials"
cd ..

# create a new handle and add metadata to it
echo "I: creating MNIST handle"
datalad create-handle mnist
(
    cd mnist
    git annex addurl --pathdepth -1 --fast "http://data.pymvpa.org/datasets/mnist/mnist.hdf5"
    wget -q http://data.pymvpa.org/datasets/mnist/README.rst; git add README.rst
    git commit -m "MNIST dataset added as a '--fast' link"
    datalad describe \
        --author "Yann LeCun and Corinna Cortes" \
        --license 'CC SA 3.0' \
        --description "Dataset of handwritten digits"# \
        # TODO --doi "10.1109/5.726791"
)

# add the handle to the collection
datalad add-handle mnist pymvpa

# Now, we want to add several already existing annexes/handles. There are
# different possibilities to do this.
# We want to publish the collection later on, including the handles. So we need
# to make sure, that the to-be published handles grant access to their actual
# content.
#
# First option:
# Install that handle locally, get all of its content, that therefore can be
# pushed on publishing. This approach is necessary only, if we actually want to
# change the content or the origin is not publicly available or we want to
# provide an additional copy of that content. This approach could be combined
# with the second one, to link several sources of the content.

echo "I: adding haxby2001"
# Haxby 2001 -- the main demo dataset
datalad install-handle http://data.pymvpa.org/datasets/haxby2001/.git
(
    cd haxby2001
    echo "I: getting haxby2001 content"
    datalad get .
)

# add the handle to the collection
datalad add-handle haxby2001 pymvpa


# Second option:
# Install the handle, but don't get the actual content. Instead, link to the
# original annex by using git-annex' special remote, that then can also be used
# by the published handle later on.

echo "I: adding tutorial_data"
datalad install-handle http://data.pymvpa.org/datasets/tutorial_data/.git
(
    cd tutorial_data
    echo "I: adding origin as special remote to tutorial_data"
    git annex initremote orig_src type=git location=http://data.pymvpa.org/datasets/tutorial_data/.git autoenable=true
)

# add the handle to the collection
datalad add-handle tutorial_data pymvpa

# Forrest gump dataset, although not yet used in PyMVPA stock materials,
# analysis scripts use PyMVPA heavily so it is a worthwhile addition
#
# Third option:
# As long as we don't want to change anything in the handle/annex, but just
# include it in the collection, we don't need to install it at all.
# Instead, just add the remote location as a handle to the collection.
# Note: This still allows for adding metadata for that handle to the collection.
# Metadata added this way, is available via this very collection only, though.
echo "I: adding forrest_gump dataset"
datalad add-handle http://psydata.ovgu.de/forrest_gump/.git pymvpa forrest_gump


# TODO: publish as http://collections.datalad.org/pymvpa
# datalad publish-collection ssh://collections.datalad.org/pymvpa pymvpa
