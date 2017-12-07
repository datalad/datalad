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
from datalad.tests.utils import with_tempfile, assert_raises, swallow_logs, known_failure_v6


@with_tempfile
def test_TestRepo(path):

    # the base class has no definition:
    assert_raises(InvalidTestRepoDefinitionError, TestRepo_NEW, path)

    # Note: Actually, the simple call of the constructor of a subclass of
    # TestRepo should execute a self test.
    # So there is no need to test a subclass of TestRepo other then just
    # trying to get an instance. Whatever assertion you can think of, should go
    # right in the correct `assert_intact` in a generic way.

    # Also note, that due to this concept, whenever we create new TestRepo
    # subclasses we automatically test the code of TestRepo and the Item classes
    # against this new setup.

    # Here we just use the most basic valid definition (BasicGit) of a
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
        # 1. constructors were executed:
        cmp_str = "{class_}{path}".format(class_=item[0],
                                          path=("(%s)" % item[1])
                                          if item[1] else ""
                                          )
        cml.assert_logged("Processing definition of %s" % cmp_str,
                          level="Level 5",
                          regex=False)
        if item[0] == BasicGit:
            # additional constructor messages:
            cml.assert_logged("Physically creating %s" % BasicGit,
                              level="Level 5",
                              regex=False)
            cml.assert_logged("Check integrity of %s" % BasicGit,
                              level="Level 5",
                              regex=False)

        # 2. creation routines called:
        if item[0] == BasicGit:
            # BasicGit actually triggered inherited creation routine:
            cml.assert_logged("Default creation routine by %s for %s" \
                              % (TestRepo_NEW, BasicGit),
                              level="Level 5",
                              regex=False)
        else:
            # actual Items have their own create() called:
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

        # assertions were executed:
        if item[0] == BasicGit:
            # BasicGit triggered default assertions from TestRepo_NEW:
            cml.assert_logged("Default integrity check by %s for %s" %
                              (TestRepo_NEW, BasicGit),
                              level="Level 5",
                              regex=False)

        elif item[0] != ItemCommit:
            # actual Items have their own assert_intact() called:
            cml.assert_logged("Integrity check for %s(%s)" % (item[0], item[1]),
                              level="Level 5",
                              regex=False)
        # no "else": ItemCommands have no assert_intact by design

    # just for demonstration change something in the actual repo:
    from datalad.cmd import Runner
    Runner(path).run(['git', 'checkout', '-b', 'new_branch'])

    assert_raises(AssertionError, tr.assert_intact)


@with_tempfile
def test_BasicMixed_instantiation(path):
    # As far as BasicMixed is concerned, we only need to instantiate it to test
    # it! See comment in test_TestRepo().
    tr = BasicMixed(path)

    # Use the most basic annex to make sure datalad config is respected by
    # ItemRepo
    from datalad import cfg
    version = cfg.obtain("datalad.repo.version")
    direct = cfg.obtain("datalad.repo.direct")
    eq_(tr.repo.annex_version, version)
    eq_(tr.repo.is_direct_mode, direct)


# Note: MixedSubmodulesOldOneLevel is supposed to reconstruct former
# SubmoduleDataset and the same is true for MixedSubmodulesOldNested and
# NestedDataset respectively. Due to the way files are added to git therein,
# clones are dirty from the beginning. So, using that kind of repo via git-clone
# or git-submodule-add fails in V6 (as it should). That's why both classes fail
# on instantiation from within their assert_intact method.
# However, as long as there are old tests, that have hardcoded assumptions on
# how a certain testrepo looks like, we need to have the old ones available and
# cannot actually fix them, which by now needs to be done by providing a
# .gitattributes file in addition. This additional unexpected file in the
# repositories may cause old tests to fail even when not in V6 build.
#
# Summary: Keep those two testrepos for now, but skip them in V6 and have new,
# shiny, better ones for new or rewritten tests. Note, that this skipping is
# done from within their create() method, since we need to skip BUILDING them in
# V6, not just the execution of tests operating on them.

@with_tempfile
def test_MixedSubmodulesOldOneLevel_instantiation(path):
    tr = MixedSubmodulesOldOneLevel(path)


@with_tempfile
def test_MixedSubmodulesOldNested_instantiation(path):
    tr = MixedSubmodulesOldNested(path)


