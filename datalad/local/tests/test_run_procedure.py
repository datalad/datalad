# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad run-procedure

"""

__docformat__ = 'restructuredtext'

import json
import os.path as op
import sys
from unittest.mock import patch

from datalad.api import run_procedure
from datalad.cmd import (
    KillOutput,
    WitlessRunner,
)
from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import (
    CommandError,
    InsufficientArgumentsError,
)
from datalad.tests.utils_pytest import (
    OBSCURE_FILENAME,
    assert_false,
    assert_in_results,
    assert_not_in_results,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_true,
    eq_,
    known_failure_windows,
    ok_file_has_content,
    patch_config,
    with_tempfile,
    with_tree,
    xfail_buggy_annex_info,
)
from datalad.utils import (
    chpwd,
    quote_cmdlinearg,
    swallow_outputs,
)


@with_tempfile(mkdir=True)
def test_invalid_call(path=None):
    with chpwd(path):
        # ^ Change directory so that we don't fail with an
        # InvalidGitRepositoryError if the test is executed from a git
        # worktree.

        # needs spec or discover
        assert_raises(InsufficientArgumentsError, run_procedure)
        # an unknown procedure should cause an error
        assert_raises(ValueError, run_procedure, 'unknown')


@with_tree(tree={'README.md': 'dirty'})
def test_dirty(path=None):
    ds = Dataset(path).create(force=True)
    # must fail, because README.md is to be modified, but already dirty
    assert_in_results(
        ds.run_procedure('cfg_yoda',
                         on_failure="ignore", result_renderer=None),
        action="run", status="error")
    # make sure that was the issue
    # save to git explicitly to keep the test simple and avoid unlocking...
    ds.save('README.md', to_git=True)
    ds.run_procedure('cfg_yoda')
    assert_repo_status(ds.path)


@with_tree(tree={
    'code': {'datalad_test_proc.py': """\
import sys
import os.path as op
from datalad.api import save, Dataset

with open(op.join(sys.argv[1], 'fromproc.txt'), 'w') as f:
    f.write('hello\\n')
save(dataset=Dataset(sys.argv[1]), path='fromproc.txt')
"""},
    'cfg_yoda.sh': """\
#!/bin/bash
echo "I am never to be ran but could be discovered"
exit 1
"""})
@with_tempfile
def test_procedure_discovery(path=None, super_path=None):
    with chpwd(path):
        # ^ Change directory so that we don't fail with an
        # InvalidGitRepositoryError if the test is executed from a git
        # worktree.
        ps = run_procedure(discover=True, result_renderer='disabled')
        # there are a few procedures coming with datalad, needs to find them
        assert_true(len(ps) > 2)
        # we get essential properties
        _check_procedure_properties(ps)

    # set up dataset with registered procedure (c&p from test_basics):
    ds = Dataset(path).create(force=True)
    # extra check: must not pick up cfg_yoda.sh in top directory
    ds.run_procedure('cfg_yoda')

    # path to a procedure which is not under any "standard" location but
    # present in the dataset
    code_dir_procedure_path = op.join(ds.path, 'code', 'datalad_test_proc.py')
    top_dir_procedure_path = op.join(ds.path, 'cfg_yoda.sh')

    # run discovery on the dataset:
    ps = ds.run_procedure(discover=True, result_renderer='disabled')
    # it should not be found magically by default
    assert_not_in_results(ps, path=code_dir_procedure_path)
    assert_not_in_results(ps, path=top_dir_procedure_path)

    with patch_config({'datalad.locations.extra-procedures': op.join(ds.path, 'code')}):
        # run discovery on the dataset:
        ps = ds.run_procedure(discover=True, result_renderer='disabled')
        # still needs to find procedures coming with datalad
        assert_true(len(ps) > 3)
        # and procedure under the path we specified
        assert_result_count(ps, 1, path=code_dir_procedure_path)
        assert_not_in_results(ps, path=top_dir_procedure_path)

    # multiple extra locations
    with patch_config({'datalad.locations.extra-procedures': [op.join(ds.path, 'code'), ds.path]}):
        # run discovery on the dataset:
        ps = ds.run_procedure(discover=True, result_renderer='disabled')
        # still needs to find procedures coming with datalad
        assert_true(len(ps) > 4)
        # and procedure under the path we specified
        assert_result_count(ps, 1, path=code_dir_procedure_path)
        assert_result_count(ps, 1, path=top_dir_procedure_path)

    # configure dataset to look for procedures in its code folder
    ds.config.add(
        'datalad.locations.dataset-procedures',
        'code',
        scope='branch')
    ds.save(op.join('.datalad', 'config'))

    # run discovery on the dataset:
    ps = ds.run_procedure(discover=True, result_renderer='disabled')

    # still needs to find procedures coming with datalad
    assert_true(len(ps) > 2)
    # we get three essential properties
    _check_procedure_properties(ps)
    # dataset's procedure needs to be in the results
    # and only a single one
    assert_result_count(ps, 1, path=code_dir_procedure_path)
    # a subdir shouldn't be considered a procedure just because it's "executable"
    assert_not_in_results(ps, path=op.join(ds.path, 'code', 'testdir'))

    # make it a subdataset and try again:
    # first we need to save the beast to make install work
    ds.save()
    super = Dataset(super_path).create()
    super.install('sub', source=ds.path)

    ps = super.run_procedure(discover=True, result_renderer='disabled')
    # still needs to find procedures coming with datalad
    assert_true(len(ps) > 2)
    _check_procedure_properties(ps)
    # dataset's procedure needs to be in the results
    assert_in_results(ps, path=op.join(super.path, 'sub', 'code',
                                       'datalad_test_proc.py'))

    if not ds.repo.is_managed_branch():  # no symlinks
        import os

        # create a procedure which is a broken symlink, but recognizable as a
        # python script:
        os.symlink(op.join(super.path, 'sub', 'not_existent'),
                   op.join(super.path, 'sub', 'code', 'broken_link_proc.py'))
        # broken symlink at procedure location, but we can't tell, whether it is
        # an actual procedure without any guess on how to execute it:
        os.symlink(op.join(super.path, 'sub', 'not_existent'),
                   op.join(super.path, 'sub', 'code', 'unknwon_broken_link'))

        ps = super.run_procedure(discover=True, result_renderer='disabled')
        # still needs to find procedures coming with datalad and the dataset
        # procedure registered before
        assert_true(len(ps) > 3)
        assert_in_results(ps, path=op.join(super.path, 'sub', 'code',
                                           'broken_link_proc.py'),
                          state='absent')
        assert_in_results(
            ps,
            path=op.join(super.path, 'sub', 'code',
                         'unknwon_broken_link'),
            state='absent')


def _check_procedure_properties(ps):
    """a common check that we get three essential properties"""
    eq_(
        sum(['procedure_type' in p and
             'procedure_callfmt' in p and
             'path' in p
             for p in ps]),
        len(ps))


@with_tree(tree={
    'code': {'datalad_test_proc.py': """\
import sys
import os.path as op
from datalad.api import save, Dataset

with open(op.join(sys.argv[1], 'fromproc.txt'), 'w') as f:
    f.write('{}\\n'.format(sys.argv[2]))
save(dataset=Dataset(sys.argv[1]), path='fromproc.txt')
"""}})
def test_configs(path=None):

    # set up dataset with registered procedure (c&p from test_basics):
    ds = Dataset(path).create(force=True)
    ds.run_procedure('cfg_yoda')
    # configure dataset to look for procedures in its code folder
    ds.config.add(
        'datalad.locations.dataset-procedures',
        'code',
        scope='branch')

    # 1. run procedure based on execution guessing by run_procedure:
    ds.run_procedure(spec=['datalad_test_proc', 'some_arg'])
    # look for traces
    ok_file_has_content(op.join(ds.path, 'fromproc.txt'), 'some_arg\n')

    # 2. now configure specific call format including usage of substitution config
    # for run:
    ds.config.add(
        'datalad.procedures.datalad_test_proc.call-format',
        u'%s {script} {ds} {{mysub}} {args}' % quote_cmdlinearg(sys.executable),
        scope='branch'
    )
    ds.config.add(
        'datalad.run.substitutions.mysub',
        'dataset-call-config',
        scope='branch'
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
        u'%s {script} {ds} local {args}' % quote_cmdlinearg(sys.executable),
        scope='local'
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
        scope='branch'
    )

    r = ds.run_procedure('datalad_test_proc', help_proc=True)
    assert_true(len(r) == 1)
    assert_in_results(r, message="This is a help message", status='ok')


@with_tree(tree={
    'code': {'datalad_test_proc.py': """\
import sys
import os.path as op
from datalad.api import save, Dataset

with open(op.join(sys.argv[1], sys.argv[2]), 'w') as f:
    f.write('hello\\n')
save(dataset=Dataset(sys.argv[1]), path=sys.argv[2])
"""}})
def test_spaces(path=None):
    """
    Test whether args with spaces are correctly parsed.
    """
    ds = Dataset(path).create(force=True)
    ds.run_procedure('cfg_yoda')
    # configure dataset to look for procedures in its code folder
    ds.config.add(
        'datalad.locations.dataset-procedures',
        'code',
        scope='branch')
    # 1. run procedure based on execution guessing by run_procedure:
    ds.run_procedure(spec=['datalad_test_proc', 'with spaces', 'unrelated'])
    # check whether file has name with spaces
    ok_file_has_content(op.join(ds.path, 'with spaces'), 'hello\n')


@known_failure_windows
@with_tree(tree={OBSCURE_FILENAME:
                 {"code": {"just2args.py": """
import sys
print(sys.argv)
# script, dataset, and two others
assert len(sys.argv) == 4
"""}}})
def test_quoting(path=None):
    ds = Dataset(op.join(path, OBSCURE_FILENAME)).create(force=True)
    # Our custom procedure fails if it receives anything other than two
    # procedure arguments (so the script itself receives 3). Check a few cases
    # from the Python API and CLI.
    ds.config.add("datalad.locations.dataset-procedures", "code",
                  scope='branch')
    with swallow_outputs():
        ds.run_procedure(spec=["just2args", "with ' sing", 'with " doub'])
        assert_in_results(
            ds.run_procedure(spec=["just2args", "still-one arg"],
                             on_failure="ignore", result_renderer=None),
            action="run", status="error")

        runner = WitlessRunner(cwd=ds.path)
        runner.run(
            "datalad run-procedure just2args \"with ' sing\" 'with \" doub'",
            protocol=KillOutput)
        with assert_raises(CommandError):
            runner.run(
                "datalad run-procedure just2args 'still-one arg'",
                protocol=KillOutput)


@xfail_buggy_annex_info
@with_tree(tree={
    # "TEXT" ones
    'empty': '',  # we have special rule to treat empty ones as text
    # check various structured files - libmagic might change its decisions which
    # can effect git-annex. https://github.com/datalad/datalad/issues/3361
    'JSON': """\
{
    "name": "John Smith",
    "age": 33
}
""",
    'YAML': """\
--- # The Smiths
- {name: John Smith, age: 33}
- name: Mary Smith
  age: 27
""",
    'MARKDOWN': """\
# Title

## Section1

When the earth was flat

## Section2
""",
    # BINARY ones
    '0blob': '\x00',
    'emptyline': '\n',  # libmagic: "binary" "application/octet-stream"
})
def test_text2git(path=None):
    # Test if files being correctly annexed in a ds configured with text2git.
    TEXT_FILES = ('JSON', 'YAML', 'MARKDOWN', 'empty')
    BINARY_FILES = ('0blob', 'emptyline')

    ds = Dataset(path).create(force=True)
    ds.run_procedure('cfg_text2git')
    ds.save(path=TEXT_FILES + BINARY_FILES, message="added all files")
    assert_repo_status(ds.path)

    # check that text files are not annexed
    for f in TEXT_FILES:
        assert_false(ds.repo.is_under_annex(f))
    # and trivial binaries - annexed
    for f in BINARY_FILES:
        assert_true(ds.repo.is_under_annex(f))


@with_tree(tree={".datalad": {"procedures": {"print_args": """
import sys
print(sys.argv)
"""}}})
def test_name_with_underscore(path=None):
    ds = Dataset(path).create(force=True)

    # we are using the presence of a managed branch as a proxy indicator
    # for a crippled FS, were we cannot trust the executable bit
    # which is our only indicator in the absence of a file extension
    if not ds.repo.is_managed_branch():
        # Procedure name with underscore can't be reached directly with a DATALAD_
        # environment variable.
        with patch.dict("os.environ",
                        {"DATALAD_PROCEDURES_PRINT_ARGS_CALL__FORMAT":
                         '%s {script}' % sys.executable}):
            with assert_raises(ValueError):
                ds.run_procedure(spec=["print_args"])

    # But it can be set via DATALAD_CONFIG_OVERRIDES_JSON.
    with patch.dict("os.environ",
                    {"DATALAD_CONFIG_OVERRIDES_JSON":
                     json.dumps({
                         "datalad.procedures.print_args.call-format":
                         "%s {script}" % sys.executable
                    })}):
        ds.config.reload()
        ds.run_procedure(spec=["print_args"])


@with_tempfile
def test_call_fmt_from_env_requires_reload(path=None):
    ds = Dataset(path).create()
    subds = ds.create("sub")
    (subds.pathobj / ".datalad" / "procedures").mkdir(
        parents=True, exist_ok=True)
    script = subds.pathobj / ".datalad" / "procedures" / "p"
    script.write_text("import sys; assert len(sys.argv) == 1")
    with patch.dict("os.environ",
                    {"DATALAD_PROCEDURES_P_CALL__FORMAT":
                     f"{sys.executable} {{script}}"}):
        # This will fail if the above environment variable isn't in effect.
        ds.run_procedure("p")


@with_tempfile
def test_run_proc_with_dict(path=None):
    # Test whether a result from run_procedure(discover=True) will be accepted
    ds = Dataset(path).create()
    g = ds.run_procedure(discover=True, result_renderer='disabled',
                         return_type='generator')
    for proc in g:
        if proc['procedure_name'] == 'cfg_text2git':
            break
    ds.run_procedure(spec=proc)
