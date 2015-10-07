#!/bin/sh
# A little script to prepare PyMVPA demo collection based on data used in
# tutorials etc

set -eu

echo "I: adding haxby2001"
# Haxby 2001 -- the main demo dataset
datalad install-handle http://data.pymvpa.org/datasets/haxby2001/.git

# getting its content, since publishing can't clone the repo, we need to push
# content to the published handle and therefore we would loose the connection
# to content, that is not addurl'ed but just available via the original annex.
# Note: May be therefore use "git annex get . --from=origin" to not unnecessarily
# get things, that are reachable from the published handle (and any clone of
# it)? Need to add that option to datalad get.
(
    cd haxby2001
    echo "I: getting haxby2001 content"
    datalad get .
)

# Extracted/processed pieces from haxby2001
echo "I: adding tutorial_data"
datalad install-handle http://data.pymvpa.org/datasets/tutorial_data/.git
# same as above
(
    cd tutorial_data
    echo "I: getting tutorial_data content"
    datalad get .
)

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

# Forrest gump dataset, although not yet used in PyMVPA stock materials,
# analysis scripts use PyMVPA heavily so it is a worthwhile addition
echo "I: adding forrest_gump dataset"
datalad install-handle http://psydata.ovgu.de/forrest_gump/.git
(
    cd forrest_gump
    echo "I: getting forrest_gump content"
    datalad get .
)

# new plain collection
echo "I: creating PyMVPA collection"
datalad create-collection pymvpa_collection pymvpa # path name

# add all handles to the pymvpa_collection
echo "I: adding all handles to the PyMVPA collection"
for h in haxby2001 tutorial_data mnist forrest_gump; do
    datalad add-handle "$h" pymvpa
done

cd pymvpa_collection
# XXX this should pull in the new handle meta-data, but doesn't ???
#echo "I: updating collection"
#datalad update

echo "I: describing collection"
datalad describe \
    --author "DataLad AKA PyMVPA Team" \
    --license 'CC0' \
    --description "Collection of datasets useful for PyMVPA demonstrations and tutorials"

# TODO: publish as http://collections.datalad.org/pymvpa
# datalad publish-collection ssh://collections.datalad.org/pymvpa pymvpa