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

echo "I: adding haxby2001"
# Haxby 2001 -- the main demo dataset
datalad add-handle http://data.pymvpa.org/datasets/haxby2001/.git pymvpa haxby2001
datalad describe \
    --author "Haxby, J., Gobbini, M., Furey, M., Ishai, A., Schouten, J., and Pietrini, P." \
    --license 'CC by-SA 3.0' \
    --description "Faces and Objects in Ventral Temporal Cortex (fMRI)

This is a block-design fMRI dataset from a study on face and object
representation in human ventral temporal cortex.  It consists of 6 subjects
with 12 runs per subject. In each run, the subjects passively viewed greyscale
images of eight object categories, grouped in 24s blocks separated by rest
periods. Each image was shown for 500ms and was followed by a 1500ms
inter-stimulus interval.  Full-brain fMRI data were recorded with a volume
repetition time of 2.5s, thus, a stimulus block was covered by roughly 9
volumes. This dataset has been repeatedly reanalyzed. For a complete
description of the experimental design, fMRI acquisition parameters, and
previously obtained results see

Haxby, J., Gobbini, M., Furey, M., Ishai, A., Schouten, J., and Pietrini,
P.  (2001). Distributed and overlapping representations of faces and
objects in ventral temporal cortex. Science 293, 2425–2430.
        " \
        haxby2001

echo "I: adding tutorial_data"
datalad add-handle http://data.pymvpa.org/datasets/tutorial_data/.git pymvpa tutorial_data
datalad describe \
    --author "PyMVPA Team" \
    --license 'CC by-SA 3.0' \
    --description "PyMVPA Tutorial Dataset (based on Haxby 2001 dataset)

At the moment dataset is based on data for a single subject from a study
published by Haxby et al. (2001). The full (raw) dataset of this study is also
available as haxby2001. However, in constrast to the full data
this single subject datasets has been preprocessed to a degree that should
allow people without prior fMRI experience to perform meaningful analyses.
Moreover, it should not require further preprocessing with external tools.

All preprocessing has been performed using tools from FSL. Specifically, the
4D fMRI timeseries has been motion-corrected by applying MCFLIRT to a
skull-stripped and thresholded timeseries (to zero-out non-brain voxels,
using a brain outline estimate significantly larger than the brain, to
prevent removal of edge voxels actually covering brain tissue). The
estimated motion parameters have been subsequently applied to the original
(unthresholded, unstripped) timeseries. For simplicity the T1-weighed
anatomical image has also been projected and resampled into the subjects
functional space." \
        tutorial_data

# Forrest gump dataset, although not yet used in PyMVPA stock materials,
# analysis scripts use PyMVPA heavily so it is a worthwhile addition
#
# As long as we don't want to change anything in the handle/annex, but just
# include it in the collection, we don't need to install it at all.
# Instead, just add the remote location as a handle to the collection.
# Note: This still allows for adding metadata for that handle to the collection.
# Metadata added this way, is available via this very collection only, though.
echo "I: adding forrest_gump dataset"
datalad add-handle http://psydata.ovgu.de/forrest_gump/.git pymvpa forrest_gump


# TODO: publish as http://collections.datalad.org/pymvpa
# datalad publish-collection ssh://collections.datalad.org/pymvpa pymvpa
