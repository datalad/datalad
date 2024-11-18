# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


from os.path import join as opj

from datalad.distribution.dataset import Dataset


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
