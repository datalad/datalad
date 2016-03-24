#!/bin/sh
# A little script to prepare PyMVPA demo collection based on data used in
# tutorials etc

# I see dead people!


set -eu

## new plain collection
#echo "I: creating PyMVPA collection"
#datalad create-collection pymvpa_collection pymvpa # path name
#
#cd pymvpa_collection
#
#echo "I: describing collection"
#datalad describe \
#    --author "DataLad AKA PyMVPA Team" \
#    --license 'CC0' \
#    --description "Collection of datasets useful for PyMVPA demonstrations and tutorials"
#cd ..
#
## create a new handle and add metadata to it
#echo "I: creating MNIST handle"
#datalad create-handle mnist
#(
#    cd mnist
#    git annex addurl --pathdepth -1 --fast "http://data.pymvpa.org/datasets/mnist/mnist.hdf5"
#    wget -q http://data.pymvpa.org/datasets/mnist/README.rst; git add README.rst
#    git commit -m "MNIST dataset added as a '--fast' link"
#    datalad describe \
#        --author "Yann LeCun and Corinna Cortes" \
#        --license 'CC SA 3.0' \
#        --description "Dataset of handwritten digits"# \
#        # TODO --doi "10.1109/5.726791"
#)
#
## add the handle to the collection
#datalad add-handle mnist pymvpa
#
#echo "I: adding haxby2001"
## Haxby 2001 -- the main demo dataset
#datalad add-handle http://data.pymvpa.org/datasets/haxby2001/.git pymvpa haxby2001
#
#echo "I: adding tutorial_data"
#datalad add-handle http://data.pymvpa.org/datasets/tutorial_data/.git pymvpa tutorial_data
#
## Forrest gump dataset, although not yet used in PyMVPA stock materials,
## analysis scripts use PyMVPA heavily so it is a worthwhile addition
##
## As long as we don't want to change anything in the handle/annex, but just
## include it in the collection, we don't need to install it at all.
## Instead, just add the remote location as a handle to the collection.
## Note: This still allows for adding metadata for that handle to the collection.
## Metadata added this way, is available via this very collection only, though.
#echo "I: adding forrest_gump dataset"
#datalad add-handle http://psydata.ovgu.de/forrest_gump/.git pymvpa forrest_gump
#
#
## TODO: publish as http://collections.datalad.org/pymvpa
## datalad publish-collection ssh://collections.datalad.org/pymvpa pymvpa
