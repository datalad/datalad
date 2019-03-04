# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad run-procedure

"""

__docformat__ = 'restructuredtext'

import os.path as op

from datalad.utils import chpwd
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_true
from datalad.tests.utils import assert_false
from datalad.tests.utils import assert_in_results
from datalad.tests.utils import assert_not_in_results
from datalad.tests.utils import skip_if
from datalad.tests.utils import on_windows
from datalad.tests.utils import known_failure_direct_mode
from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.api import run_procedure
from datalad import cfg


@with_tempfile(mkdir=True)
def test_invalid_call(path):
    with chpwd(path):
        # ^ Change directory so that we don't fail with an
        # InvalidGitRepositoryError if the test is executed from a git
        # worktree.

        # needs spec or discover
        assert_raises(InsufficientArgumentsError, run_procedure)
        res = run_procedure('unknown', on_failure='ignore')
        assert_true(len(res) == 1)
        assert_in_results(res, status="impossible")


# FIXME: For some reason fails to commit correctly if on windows and in direct
# mode. However, direct mode on linux works
@skip_if(cond=on_windows and cfg.obtain("datalad.repo.version") < 6)
@known_failure_direct_mode  #FIXME
@with_tree(tree={
    'code': {'datalad_test_proc.py': """\
import sys
import os.path as op
from datalad.api import add, Dataset

with open(op.join(sys.argv[1], 'fromproc.txt'), 'w') as f:
    f.write('hello\\n')
add(dataset=Dataset(sys.argv[1]), path='fromproc.txt')
"""}})
@with_tempfile
def test_basics(path, super_path):
    ds = Dataset(path).create(force=True)
    ds.run_procedure('setup_yoda_dataset')
    ok_clean_git(ds.path)
    assert_false(ds.repo.is_under_annex("README.md"))
    # configure dataset to look for procedures in its code folder
    ds.config.add(
        'datalad.locations.dataset-procedures',
        'code',
        where='dataset')
    # commit this procedure config for later use in a clone:
    ds.add(op.join('.datalad', 'config'))
    # configure dataset to run the demo procedure prior to the clean command
    ds.config.add(
        'datalad.clean.proc-pre',
        'datalad_test_proc',
        where='dataset')
    # run command that should trigger the demo procedure
    ds.clean()
    # look for traces
    ok_file_has_content(op.join(ds.path, 'fromproc.txt'), 'hello\n')
    ok_clean_git(ds.path, index_modified=[op.join('.datalad', 'config')])

    # make a fresh dataset:
    super = Dataset(super_path).create()
    # configure dataset to run the demo procedure prior to the clean command
    super.config.add(
        'datalad.clean.proc-pre',
        'datalad_test_proc',
        where='dataset')
    # 'super' doesn't know any procedures but should get to know one by
    # installing the above as a subdataset
    super.install('sub', source=ds.path)
    # run command that should trigger the demo procedure
    super.clean()
    # look for traces
    ok_file_has_content(op.join(super.path, 'fromproc.txt'), 'hello\n')
    ok_clean_git(super.path, index_modified=[op.join('.datalad', 'config')])


# FIXME: For some reason fails to commit correctly if on windows and in direct
# mode. However, direct mode on linux works
@skip_if(cond=on_windows and cfg.obtain("datalad.repo.version") < 6)
@with_tree(tree={
    'code': {'datalad_test_proc.py': """\
import sys
import os.path as op
from datalad.api import add, Dataset

with open(op.join(sys.argv[1], 'fromproc.txt'), 'w') as f:
    f.write('hello\\n')
add(dataset=Dataset(sys.argv[1]), path='fromproc.txt')
"""}})
@with_tempfile
def test_procedure_discovery(path, super_path):
    with chpwd(path):
        # ^ Change directory so that we don't fail with an
        # InvalidGitRepositoryError if the test is executed from a git
        # worktree.
        ps = run_procedure(discover=True)
        # there are a few procedures coming with datalad, needs to find them
        assert_true(len(ps) > 2)
        # we get three essential properties
        eq_(
            sum(['procedure_type' in p and
                 'procedure_callfmt' in p and
                 'path' in p
                 for p in ps]),
            len(ps))

    # set up dataset with registered procedure (c&p from test_basics):
    ds = Dataset(path).create(force=True)
    ds.run_procedure('setup_yoda_dataset')
    ok_clean_git(ds.path)
    # configure dataset to look for procedures in its code folder
    ds.config.add(
        'datalad.locations.dataset-procedures',
        'code',
        where='dataset')
    # configure dataset to run the demo procedure prior to the clean command
    ds.config.add(
        'datalad.clean.proc-pre',
        'datalad_test_proc',
        where='dataset')
    ds.add(op.join('.datalad', 'config'))

    # run discovery on the dataset:
    ps = ds.run_procedure(discover=True)

    # still needs to find procedures coming with datalad
    assert_true(len(ps) > 2)
    # we get three essential properties
    eq_(
        sum(['procedure_type' in p and
             'procedure_callfmt' in p and
             'path' in p
             for p in ps]),
        len(ps))
    # dataset's procedure needs to be in the results
    assert_in_results(ps, path=op.join(ds.path, 'code', 'datalad_test_proc.py'))

    # make it a subdataset and try again:
    super = Dataset(super_path).create()
    super.install('sub', source=ds.path)

    ps = super.run_procedure(discover=True)
    # still needs to find procedures coming with datalad
    assert_true(len(ps) > 2)
    # we get three essential properties
    eq_(
        sum(['procedure_type' in p and
             'procedure_callfmt' in p and
             'path' in p
             for p in ps]),
        len(ps))
    # dataset's procedure needs to be in the results
    assert_in_results(ps, path=op.join(super.path, 'sub', 'code',
                                       'datalad_test_proc.py'))

    if not on_windows:  # no symlinks
        import os
        # create a procedure which is a broken symlink, but recognizable as a
        # python script:
        os.symlink(op.join(super.path, 'sub', 'not_existent'),
                   op.join(super.path, 'sub', 'code', 'broken_link_proc.py'))
        # broken symlink at procedure location, but we can't tell, whether it is
        # an actual procedure without any guess on how to execute it:
        os.symlink(op.join(super.path, 'sub', 'not_existent'),
                   op.join(super.path, 'sub', 'code', 'unknwon_broken_link'))

        ps = super.run_procedure(discover=True)
        # still needs to find procedures coming with datalad and the dataset
        # procedure registered before
        assert_true(len(ps) > 3)
        assert_in_results(ps, path=op.join(super.path, 'sub', 'code',
                                           'broken_link_proc.py'),
                          state='absent')
        assert_not_in_results(ps, path=op.join(super.path, 'sub', 'code',
                                               'unknwon_broken_link'))


# FIXME: For some reason fails to commit correctly if on windows and in direct
# mode. However, direct mode on linux works
@skip_if(cond=on_windows and cfg.obtain("datalad.repo.version") < 6)
@with_tree(tree={
    'code': {'datalad_test_proc.py': """\
import sys
import os.path as op
from datalad.api import add, Dataset

with open(op.join(sys.argv[1], 'fromproc.txt'), 'w') as f:
    f.write('{}\\n'.format(sys.argv[2]))
add(dataset=Dataset(sys.argv[1]), path='fromproc.txt')
"""}})
def test_configs(path):

    # set up dataset with registered procedure (c&p from test_basics):
    ds = Dataset(path).create(force=True)
    ds.run_procedure('setup_yoda_dataset')
    ok_clean_git(ds.path)
    # configure dataset to look for procedures in its code folder
    ds.config.add(
        'datalad.locations.dataset-procedures',
        'code',
        where='dataset')

    # 1. run procedure based on execution guessing by run_procedure:
    ds.run_procedure(spec=['datalad_test_proc', 'some_arg'])
    # look for traces
    ok_file_has_content(op.join(ds.path, 'fromproc.txt'), 'some_arg\n')

    # 2. now configure specific call format including usage of substitution config
    # for run:
    ds.config.add(
        'datalad.procedures.datalad_test_proc.call-format',
        'python "{script}" "{ds}" {{mysub}} {args}',
        where='dataset'
    )
    ds.config.add(
        'datalad.run.substitutions.mysub',
        'dataset-call-config',
        where='dataset'
    )
    # TODO: Should we allow for --inputs/--outputs arguments for run_procedure
    #       (to be passed into run)?
    ds.unlock("fromproc.txt")
    # run again:
    ds.run_procedure(spec=['datalad_test_proc', 'some_arg'])
    # look for traces
    ok_file_has_content(op.join(ds.path, 'fromproc.txt'), 'dataset-call-config\n')

    # 3. have a conflicting config at user-level, which should override the
    # config on dataset level:
    ds.config.add(
        'datalad.procedures.datalad_test_proc.call-format',
        'python "{script}" "{ds}" local {args}',
        where='local'
    )
    ds.unlock("fromproc.txt")
    # run again:
    ds.run_procedure(spec=['datalad_test_proc', 'some_arg'])
    # look for traces
    ok_file_has_content(op.join(ds.path, 'fromproc.txt'), 'local\n')

    # 4. get configured help message:
    r = ds.run_procedure('datalad_test_proc', help_proc=True,
                         on_failure='ignore')
    assert_true(len(r) == 1)
    assert_in_results(r, status="impossible")

    ds.config.add(
        'datalad.procedures.datalad_test_proc.help',
        "This is a help message",
        where='dataset'
    )

    r = ds.run_procedure('datalad_test_proc', help_proc=True)
    assert_true(len(r) == 1)
    assert_in_results(r, message="This is a help message", status='ok')
