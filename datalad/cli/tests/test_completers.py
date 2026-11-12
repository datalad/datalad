"""Tests for shell completion of parameter values"""

__docformat__ = 'restructuredtext'

import logging
import os
from argparse import Namespace

import pytest

from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
)
from datalad.interface.base import (
    get_interface_groups,
    load_interface,
)
from datalad.interface.common_opts import sibling_parameter
from datalad.support.constraints import (
    EnsureChoice,
    EnsureInt,
    EnsureNone,
    EnsureStr,
)
from datalad.support.param import Parameter
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_in,
    assert_is,
    assert_is_none,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    chpwd,
    swallow_logs,
)

from ..common_args import common_args
from ..completers import (
    ChoicesCompleter,
    complete_cfg_procedures,
    complete_directories,
    complete_procedures,
    complete_revisions,
    complete_siblings,
    completers,
    get_completer,
    get_param_completer,
)


@pytest.mark.ai_generated
@with_tempfile(mkdir=True)
def test_complete_in_dataset(path=None):
    ds = Dataset(path).create(annex=False)
    for name in ('origin', 'other'):
        ds.repo.add_remote(name, f'https://example.com/{name}')
    ds.repo.tag('v1')
    ds.repo.call_git(['update-ref', 'refs/remotes/origin/main', 'HEAD'])
    for ref in ('refs/heads', 'refs/remotes/origin'):
        ds.repo.call_git(['update-ref', f'{ref}/git-annex', 'HEAD'])
    sub = ds.pathobj / 'sub'
    sub.mkdir()
    branch = ds.repo.get_active_branch()

    urls = {n: f'https://example.com/{n}' for n in ('origin', 'other')}
    for completer, prefix, full, prefixed in (
            # siblings come with their URLs for a description
            (complete_siblings, 'ot', urls, {'other': urls['other']}),
            (complete_revisions, 'v',
             sorted([branch, 'origin/main', 'v1']), ['v1']),
    ):
        def complete(prefix='', **kwargs):
            return completer(prefix, parsed_args=Namespace(**kwargs))

        assert_equal(complete(dataset=path), full)
        assert_equal(complete(prefix, dataset=path), prefixed)
        # -d is relative to -C, which could be given multiple times
        assert_equal(complete(change_path=[str(ds.pathobj.parent)],
                              dataset=ds.pathobj.name),
                     full)
        assert_equal(complete(change_path=[path, 'sub']), full)
        with chpwd(sub):
            assert_equal(complete(), full)
        # no dataset, no completions
        assert not complete(change_path=[path], dataset='nonexistent')


@pytest.mark.ai_generated
def test_complete_procedures():
    assert_in('cfg_yoda', complete_procedures(''))
    assert_equal(complete_procedures('cfg_yo'), ['cfg_yoda'])
    # only the name of the procedure, not its arguments
    assert_equal(
        complete_procedures('', parsed_args=Namespace(spec=['cfg_yoda'])), [])

    assert_in('yoda', complete_cfg_procedures(''))
    assert_equal(complete_cfg_procedures('yo'), ['yoda'])
    assert_equal(complete_cfg_procedures('cfg_'), [])


@pytest.mark.ai_generated
@with_tree(tree={
    'dir1': {'sub': {}},
    'dir2': {},
    'other': {},
    '.hidden': {},
    'dfile': '',
})
def test_complete_directories(path=None):
    def complete(prefix, *change_path):
        return complete_directories(
            prefix, parsed_args=Namespace(change_path=list(change_path)))

    def dirs(*names):
        return [n + os.sep for n in names]

    with chpwd(path):
        assert_equal(complete(''), dirs('dir1', 'dir2', 'other'))
        assert_equal(complete('d'), dirs('dir1', 'dir2'))
        assert_equal(complete('.'), dirs('.hidden'))
        assert_equal(complete('dir1' + os.sep), dirs(os.path.join('dir1', 'sub')))
        assert_equal(complete('', 'dir1'), dirs('sub'))
    assert_equal(complete(os.path.join(path, 'o')),
                 dirs(os.path.join(path, 'other')))
    assert_equal(complete('d', path), dirs('dir1', 'dir2'))
    assert_equal(complete('', path, 'dir1'), dirs('sub'))
    assert_equal(complete('', os.path.join(path, 'nonexistent')), [])


@pytest.mark.ai_generated
def test_get_completer():
    assert_is(get_completer('siblings').completer, complete_siblings)

    def custom(prefix, **kwargs):
        return [prefix + '1']

    completer = get_completer(custom)
    assert_is(completer.completer, custom)
    assert_equal(completer(prefix='a', parsed_args=None), ['a1'])

    completer = get_completer(['abc', 'abd', 'b'])
    assert_equal(completer.completer, ChoicesCompleter('abc', 'abd', 'b'))
    assert_equal(completer(prefix='a'), ['abc', 'abd'])

    with swallow_logs(new_level=logging.WARNING) as cml:
        assert_is_none(get_completer('bogus'))
        assert_in("Unknown completer 'bogus'", cml.out)

    # a failing completer must not crash the completion
    def failing(prefix, **kwargs):
        raise RuntimeError("some problem")

    with swallow_logs(new_level=logging.DEBUG) as cml:
        assert_equal(get_completer(failing)(prefix=''), [])
        assert_in("some problem", cml.out)


@pytest.mark.ai_generated
@pytest.mark.parametrize('param,target', [
    (Parameter(), None),
    (Parameter(constraints=EnsureStr() | EnsureNone()), None),
    # is made into `choices` of the parser instead
    (Parameter(constraints=EnsureChoice('a', 'b')), None),
    (Parameter(constraints=EnsureInt() | EnsureChoice('a', None, True, 'b')),
     ChoicesCompleter('a', 'b')),
    (Parameter(constraints=EnsureDataset()), complete_directories),
    (Parameter(constraints=EnsureDataset() | EnsureNone()),
     complete_directories),
    # explicit one takes precedence
    (Parameter(constraints=EnsureDataset() | EnsureNone(),
               completer='revisions'),
     complete_revisions),
    (Parameter(constraints=EnsureInt() | EnsureChoice('a'), completer=['c']),
     ChoicesCompleter('c')),
    (sibling_parameter(), complete_siblings),
    (sibling_parameter(completer=None, doc="custom"), None),
])
def test_get_param_completer(param, target):
    completer = get_param_completer(param)
    if target is None:
        assert_is_none(completer)
    else:
        assert_equal(completer.completer, target)


@pytest.mark.ai_generated
def test_sibling_parameter():
    param = sibling_parameter()
    assert_equal(param.cmd_kwargs['metavar'], 'SIBLING')
    assert_equal(param._doc, "name of the sibling")
    assert_equal(param.constraints('name'), 'name')
    assert_is_none(param.constraints(None))
    param = sibling_parameter(
        args=('--to',), doc="custom", action='append', metavar='NAME')
    assert_equal(param.cmd_args, ('--to',))
    assert_equal(param._doc, "custom")
    assert_equal(param.cmd_kwargs, dict(action='append', metavar='NAME'))
    assert_equal(param.completer, 'siblings')


@pytest.mark.ai_generated
def test_known_completers():
    # all named completers of the core commands' parameters and of the common
    # arguments are known
    specs = [(name, kwargs.get('completer'))
             for name, (_, kwargs) in common_args.items()]
    for _, _, intfspecs in get_interface_groups():
        for intfspec in intfspecs:
            intf = load_interface(intfspec)
            specs.extend(
                (f'{intf.__name__}.{name}', param.completer)
                for name, param in intf._params_.items())
    named = {name: spec for name, spec in specs if isinstance(spec, str)}
    for name, spec in named.items():
        assert_in(spec, completers, msg=name)
