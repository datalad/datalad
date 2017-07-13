# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


from os.path import join as opj
from datalad.api import create
from datalad.tests.utils import create_tree


def make_studyforrest_mockup(path):
    """Generate a dataset structure mimicking aspects of studyforrest.org

    Under the given path there are two directories:

    public - to be published datasets
    private - never to be published datasets

    The 'public' directory itself is a superdataset, the 'private' directory
    is just a directory that contains standalone datasets in subdirectories.
    """
    public = create(opj(path, 'public'), description="umbrella dataset")
    # the following tries to capture the evolution of the project
    phase1 = public.create('phase1',
                           description='old-style, no connection to RAW')
    structural = public.create('structural', description='anatomy')
    tnt = public.create('tnt', description='image templates')
    tnt.clone(source=phase1.path, path=opj('src', 'phase1'), reckless=True)
    tnt.clone(source=structural.path, path=opj('src', 'structural'), reckless=True)
    aligned = public.create('aligned', description='aligned image data')
    aligned.clone(source=phase1.path, path=opj('src', 'phase1'), reckless=True)
    aligned.clone(source=tnt.path, path=opj('src', 'tnt'), reckless=True)
    # new acquisition
    labet = create(opj(path, 'private', 'labet'), description="raw data ET")
    phase2_dicoms = create(opj(path, 'private', 'p2dicoms'), description="raw data P2MRI")
    phase2 = public.create('phase2',
                           description='new-style, RAW connection')
    phase2.clone(source=labet.path, path=opj('src', 'labet'), reckless=True)
    phase2.clone(source=phase2_dicoms.path, path=opj('src', 'dicoms'), reckless=True)
    # add to derivatives
    tnt.clone(source=phase2.path, path=opj('src', 'phase2'), reckless=True)
    aligned.clone(source=phase2.path, path=opj('src', 'phase2'), reckless=True)
    # never to be published media files
    media = create(opj(path, 'private', 'media'), description="raw data ET")
    # assuming all annotations are in one dataset (in reality this is also
    # a superdatasets with about 10 subdatasets
    annot = public.create('annotations', description='stimulus annotation')
    annot.clone(source=media.path, path=opj('src', 'media'), reckless=True)
    # a few typical analysis datasets
    # (just doing 3, actual status quo is just shy of 10)
    # and also the real goal -> meta analysis
    metaanalysis = public.create('metaanalysis', description="analysis of analyses")
    for i in range(1, 3):
        ana = public.create('analysis{}'.format(i),
                            description='analysis{}'.format(i))
        ana.clone(source=annot.path, path=opj('src', 'annot'), reckless=True)
        ana.clone(source=aligned.path, path=opj('src', 'aligned'), reckless=True)
        ana.clone(source=tnt.path, path=opj('src', 'tnt'), reckless=True)
        # link to metaanalysis
        metaanalysis.clone(source=ana.path, path=opj('src', 'ana{}'.format(i)),
                           reckless=True)
        # simulate change in an input (but not raw) dataset
        create_tree(
            aligned.path,
            {'modification{}.txt'.format(i): 'unique{}'.format(i)})
        aligned.add('.')
    # finally aggregate data
    aggregate = public.create('aggregate', description='aggregate data')
    aggregate.clone(source=aligned.path, path=opj('src', 'aligned'), reckless=True)
    # the toplevel dataset is intentionally left dirty, to reflect the
    # most likely condition for the joint dataset to be in at any given
    # point in time
