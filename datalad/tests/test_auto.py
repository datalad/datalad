# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test proxying of core IO operations
"""

import os
from os.path import join as opj, dirname

from mock import patch

from six.moves import StringIO
from .utils import with_testrepos
from .utils import assert_raises, eq_, ok_, assert_false, assert_true
from .utils import swallow_outputs

from ..auto import AutomagicIO

from ..support.annexrepo import AnnexRepo
from .utils import with_tempfile
from .utils import SkipTest
from .utils import chpwd

try:
    import h5py
except ImportError:
    h5py = None

try:
    import nibabel as nib
    import numpy as np
except ImportError:
    nib = None

# somewhat superseeded by  test_proxying_open_regular but still does
# some additional testing, e.g. non-context manager style of invocation
@with_testrepos('basic_annex', flavors=['clone'])
def test_proxying_open_testrepobased(repo):
    TEST_CONTENT = "123\n"
    fname = 'test-annex.dat'
    fpath = opj(repo, fname)
    assert_raises(IOError, open, fpath)

    aio = AutomagicIO(activate=True)
    try:
        with swallow_outputs():
            # now we should be able just to request to open this file
            with open(fpath) as f:
                content = f.read()
                eq_(content, TEST_CONTENT)
    finally:
        aio.deactivate()

    # and now that we have fetched it, nothing should forbid us to open it again
    with open(fpath) as f:
        eq_(f.read(), TEST_CONTENT)

    annex = AnnexRepo(repo, create=False)
    # Let's create another file deeper under the directory with the same content
    # so it would point to the same key, which we would drop and repeat the drill
    fpath2 = opj(repo, 'd1', 'd2', 'test2.dat')
    os.makedirs(dirname(fpath2))
    with open(fpath2, 'w') as f:
        f.write(content)
    annex.add(fpath2)
    annex.drop(fpath2)
    annex.commit("added and dropped")
    assert_raises(IOError, open, fpath2)

    # Let's use context manager form
    with AutomagicIO() as aio:
        ok_(isinstance(aio, AutomagicIO))
        ok_(aio.active)
        with swallow_outputs():
            # now we should be able just to request to open this file
            with open(fpath2) as f:
                content = f.read()
                eq_(content, TEST_CONTENT)

    annex.drop(fpath2)
    assert_raises(IOError, open, fpath2)

    # Let's use relative path
    with chpwd(opj(repo, 'd1')):
        # Let's use context manager form
        with AutomagicIO() as aio, \
                swallow_outputs(), \
                open(opj('d2', 'test2.dat')) as f:
                    content = f.read()
                    eq_(content, TEST_CONTENT)


# TODO: RF to allow for quick testing of various scenarios/backends without duplication
@with_tempfile(mkdir=True)
def _test_proxying_open(generate_load, verify_load, repo):
    annex = AnnexRepo(repo, create=True)
    fpath1 = opj(repo, "test")
    fpath2 = opj(repo, 'd1', 'd2', 'test2')
    # generate load
    fpath1 = generate_load(fpath1) or fpath1
    os.makedirs(dirname(fpath2))
    fpath2 = generate_load(fpath2) or fpath2
    annex.add([fpath1, fpath2])
    verify_load(fpath1)
    verify_load(fpath2)
    annex.commit("Added some files")

    # clone to another repo
    repo2 = repo + "_2"
    annex2 = AnnexRepo.clone(repo, repo2)
    # verify that can't access
    fpath1_2 = fpath1.replace(repo, repo2)
    fpath2_2 = fpath2.replace(repo, repo2)

    assert_raises(IOError, verify_load, fpath1_2)

    with AutomagicIO():
        # verify that it doesn't even try to get files which do not exist
        with patch('datalad.support.annexrepo.AnnexRepo.get') as gricm:
            # if we request absent file
            assert_raises(IOError, open, fpath1_2+"_", 'r')
            # no get should be called
            assert_false(gricm.called)
        verify_load(fpath1_2)
        verify_load(fpath2_2)
        # and even if we drop it -- we still can get it no problem
        annex2.drop(fpath2_2)
        assert_false(annex2.file_has_content(fpath2_2))
        verify_load(fpath2_2)
        assert_true(annex2.file_has_content(fpath2_2))

    # if we override stdout with something not supporting fileno, like tornado
    # does which ruins using get under IPython
    # TODO: we might need to refuse any online logging in other places like that
    annex2.drop(fpath2_2)
    class StringIOfileno(StringIO):
        def fileno(self):
            raise Exception("I have no clue how to do fileno")

    with patch('sys.stdout', new_callable=StringIOfileno), \
         patch('sys.stderr', new_callable=StringIOfileno):
        with AutomagicIO():
            assert_false(annex2.file_has_content(fpath2_2))
            verify_load(fpath2_2)
            assert_true(annex2.file_has_content(fpath2_2))


def test_proxying_open_h5py():
    def generate_hdf5(f):
        with h5py.File(f, "w") as f:
            dset = f.create_dataset("mydataset", (1,), dtype='i')
            dset[0] = 99

    def verify_hdf5(f, mode="r"):
        with h5py.File(f, mode) as f:
            dset = f["mydataset"]
            eq_(dset[0], 99)

    if not h5py:
        raise SkipTest("No h5py found")
    yield _test_proxying_open, generate_hdf5, verify_hdf5


def test_proxying_open_regular():
    def generate_dat(f):
        with open(f, "w") as f:
            f.write("123")

    def verify_dat(f, mode="r"):
        with open(f, "r") as f:
            eq_(f.read(), "123")

    yield _test_proxying_open, generate_dat, verify_dat


def test_proxying_open_nibabel():
    if not nib:
        raise SkipTest("No nibabel found")
    # cannot have numpy if nibabel is available
    from numpy.testing import assert_array_equal

    d = np.empty((3, 3, 3))
    d[1, 1, 1] = 99

    def generate_nii(f):
        f = f + '.nii.gz'
        nib.Nifti1Image(d.copy(), np.eye(4)).to_filename(f)
        return f

    def verify_nii(f, mode="r"):
        ni = nib.load(f)
        assert_array_equal(ni.get_data(), d)

    yield _test_proxying_open, generate_nii, verify_nii
