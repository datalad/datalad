# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for testrepos
"""

from datalad.tests.testrepos.repos import *
from datalad.tests.utils import with_tempfile, assert_raises, swallow_logs



@with_tempfile
def test_TestRepo_instantiation(path):
    # we can't instantiate the base class due to missing definition:
    assert_raises(InvalidTestRepoDefinitionError, TestRepo_NEW, path)


@with_tempfile
def test_BasicGit_instantiation(path):

    # Note: Actually, the simple call of the constructor should execute a self
    # test. Here we just use the most basic valid definition (BasicGit) of a
    # TestRepo to test the implementation of TestRepo_NEW. Basically, this is
    # about making sure, that all parts were executed including the assertions
    # defined by TestRepo_NEW and the Item classes.

    with swallow_logs(new_level=5) as cml:
        tr = BasicGit(path)

    for item in [(BasicGit, path),
                 (ItemSelf, path),
                 (ItemFile, opj(path, 'test.dat')),
                 (ItemInfoFile, opj(path, 'INFO.txt')),
                 (ItemCommit, '')]:
        # constructors were executed:
        cmp_str = "{class_}{path}".format(class_=item[0],
                                          path=("(%s)" % item[1])
                                          if item[1] else ""
                                          )
        cml.assert_logged("Processing definition of %s" % cmp_str,
                          level="Level 5",
                          regex=False)

        # creation routines called:
        if item[0] != BasicGit:
            cmp_str = "{create_exec} {it}{detail}".format(
                create_exec="Executing"
                            if item[0] == ItemCommit
                            else "Creating",
                it=item[0],
                detail=(" in %s" % item[1])
                        if item[0] == ItemCommit
                        else "(%s)" % item[1],
            )
            cml.assert_logged(cmp_str, level="Level 5", regex=False)

        else:
            # BasicGit
            cml.assert_logged("Default creation routine by %s for %s" \
                              % (TestRepo_NEW, BasicGit),
                              level="Level 5",
                              regex=False)

        # assertions were executed:
        # TODO:

@with_tempfile
def test_BasicMixed_instantiation(path):
    # We only need to instantiate it to test it!
    tr = BasicMixed(path)



