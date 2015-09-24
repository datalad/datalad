#!/bin/sh
# A little script to prepare PyMVPA demo collection based on data used in tutorials etc

set -eu

mkdir -p pymvpa-collection
cd pymvpa-collection

echo "I: adding haxby2001"
# Haxby 2001 -- the main demo dataset
datalad install-handle http://data.pymvpa.org/datasets/haxby2001/.git

# Extracted/processed pieces from haxby2001
echo "I: adding tutorial_data"
datalad install-handle http://data.pymvpa.org/datasets/tutorial_data/.git

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

# new plain collection
echo "I: creating PyMVPA collection"
datalad create-collection collection pymvpa # path name

# add all handles to the pymvpa_collection
echo "I: adding all handles to the PyMVPA collection"
for h in haxby2001 tutorial_data mnist forrest_gump; do
    datalad add-handle "$h" pymvpa
done

cd pymvpa_collection
# XXX this should pull in the new handle meta-data, but doesn't ???
echo "I: updating collection"
datalad update
# this leads to all of .git being commited with the meta data change
echo "I: describing collection"
datalad describe \
    --author "DataLad AKA PyMVPA Team" \
    --license 'CC0' \
    --description "Collection of datasets useful for PyMVPA demonstrations and tutorials"

# TODO: publish as http://collections.datalad.org/pymvpa