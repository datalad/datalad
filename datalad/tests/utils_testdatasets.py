# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


from os.path import join as opj

from datalad.api import create
from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import create_tree


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
    tnt.clone(source=phase1.path, path=opj('src', 'phase1'), reckless='auto')
    tnt.clone(source=structural.path, path=opj('src', 'structural'), reckless='auto')
    aligned = public.create('aligned', description='aligned image data')
    aligned.clone(source=phase1.path, path=opj('src', 'phase1'), reckless='auto')
    aligned.clone(source=tnt.path, path=opj('src', 'tnt'), reckless='auto')
    # new acquisition
    labet = create(opj(path, 'private', 'labet'), description="raw data ET")
    phase2_dicoms = create(opj(path, 'private', 'p2dicoms'), description="raw data P2MRI")
    phase2 = public.create('phase2',
                           description='new-style, RAW connection')
    phase2.clone(source=labet.path, path=opj('src', 'labet'), reckless='auto')
    phase2.clone(source=phase2_dicoms.path, path=opj('src', 'dicoms'), reckless='auto')
    # add to derivatives
    tnt.clone(source=phase2.path, path=opj('src', 'phase2'), reckless='auto')
    aligned.clone(source=phase2.path, path=opj('src', 'phase2'), reckless='auto')
    # never to be published media files
    media = create(opj(path, 'private', 'media'), description="raw data ET")
    # assuming all annotations are in one dataset (in reality this is also
    # a superdatasets with about 10 subdatasets
    annot = public.create('annotations', description='stimulus annotation')
    annot.clone(source=media.path, path=opj('src', 'media'), reckless='auto')
    # a few typical analysis datasets
    # (just doing 3, actual status quo is just shy of 10)
    # and also the real goal -> meta analysis
    metaanalysis = public.create('metaanalysis', description="analysis of analyses")
    for i in range(1, 3):
        ana = public.create('analysis{}'.format(i),
                            description='analysis{}'.format(i))
        ana.clone(source=annot.path, path=opj('src', 'annot'), reckless='auto')
        ana.clone(source=aligned.path, path=opj('src', 'aligned'), reckless='auto')
        ana.clone(source=tnt.path, path=opj('src', 'tnt'), reckless='auto')
        # link to metaanalysis
        metaanalysis.clone(source=ana.path, path=opj('src', 'ana{}'.format(i)),
                           reckless='auto')
        # simulate change in an input (but not raw) dataset
        create_tree(
            aligned.path,
            {'modification{}.txt'.format(i): 'unique{}'.format(i)})
        aligned.save()
    # finally aggregate data
    aggregate = public.create('aggregate', description='aggregate data')
    aggregate.clone(source=aligned.path, path=opj('src', 'aligned'), reckless='auto')
    # the toplevel dataset is intentionally left dirty, to reflect the
    # most likely condition for the joint dataset to be in at any given
    # point in time


def _make_dataset_hierarchy(path):
    origin = Dataset(path).create()
    origin_sub1 = origin.create('sub1')
    origin_sub2 = origin_sub1.create('sub2')
    with open(opj(origin_sub2.path, 'file_in_annex.txt'), "w") as f:
        f.write('content2')
    origin_sub3 = origin_sub2.create('sub3')
    with open(opj(origin_sub3.path, 'file_in_annex.txt'), "w") as f:
        f.write('content3')
    origin_sub4 = origin_sub3.create('sub4')
    origin.save(recursive=True)
    return origin, origin_sub1, origin_sub2, origin_sub3, origin_sub4


def _mk_submodule_annex(path, fname, fcontent):
    ca = dict(result_renderer='disabled')
    # a remote dataset with a subdataset underneath
    origds = Dataset(path).create(**ca)
    (origds.pathobj / fname).write_text(fcontent)
    # naming is weird, but a legacy artifact
    s1 = origds.create('subm 1', **ca)
    (s1.pathobj / fname).write_text(fcontent)
    s2 = origds.create('2', **ca)
    (s2.pathobj / fname).write_text(fcontent)
    origds.save(recursive=True, **ca)
    return origds