# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test -J/--jobs value resolution (follow-up to gh-7867)"""

import logging
from unittest.mock import patch

import pytest

from datalad.api import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.parallel import ProducerConsumer
from datalad.tests.utils_pytest import (
    assert_in_results,
    assert_status,
    skip_if_adjusted_branch,
    with_tempfile,
)
from datalad.utils import (
    available_cpu_count,
    swallow_logs,
)


@pytest.mark.ai_generated
@with_tempfile(mkdir=True)
def test_jobs_cpus_get(path=None):
    """'cpus' is accepted and resolves for get"""
    ds = Dataset(path).create()
    (ds.pathobj / 'file.txt').write_text('content')
    ds.save(message='add file')

    res = ds.get('file.txt', jobs='cpus')
    assert_status(['ok', 'notneeded'], res)


@pytest.mark.ai_generated
@skip_if_adjusted_branch  # push->copy semantics differ on Windows adjusted branches
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_jobs_cpus_push(srcpath=None, dstpath=None):
    """'cpus' is accepted and resolves for push"""
    src = Dataset(srcpath).create()
    (src.pathobj / 'file.txt').write_text('content')
    src.save(message='add file')

    target = AnnexRepo(dstpath, init=True, create=True)
    target.config.set(
        'receive.denyCurrentBranch', 'updateInstead', scope='local')
    src.siblings('add', name='target', url=dstpath,
                 result_renderer='disabled')

    res = src.push(to='target', jobs='cpus')
    assert_in_results(res, action='copy', status='ok',
                      path=str(src.pathobj / 'file.txt'))


@pytest.mark.ai_generated
@skip_if_adjusted_branch  # drop content semantics differ on Windows adjusted branches
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_jobs_cpus_drop(srcpath=None, dstpath=None):
    """'cpus' is accepted and resolves for drop"""
    src = Dataset(srcpath).create()
    (src.pathobj / 'file.txt').write_text('content')
    src.save(message='add file')

    target = AnnexRepo(dstpath, init=True, create=True)
    target.config.set(
        'receive.denyCurrentBranch', 'updateInstead', scope='local')
    src.siblings('add', name='target', url=dstpath,
                 result_renderer='disabled')
    src.push(to='target')

    assert src.repo.file_has_content('file.txt')
    res = src.drop(jobs='cpus')
    assert_in_results(res, action='drop', status='ok',
                      path=str(src.pathobj / 'file.txt'))
    assert not src.repo.file_has_content('file.txt')


@pytest.mark.ai_generated
def test_jobs_cpus_resolves_to_cpu_count():
    """'cpus' resolves to available_cpu_count() in ProducerConsumer path"""
    expected = available_cpu_count()
    assert ProducerConsumer.get_effective_jobs('cpus') == expected


@pytest.mark.ai_generated
def test_available_cpu_count():
    """available_cpu_count returns a positive integer"""
    n = available_cpu_count()
    assert isinstance(n, int)
    assert n >= 1


@pytest.mark.ai_generated
@with_tempfile(mkdir=True)
def test_call_annex_resolves_cpus(path=None):
    """_call_annex resolves jobs='cpus' to available_cpu_count() in -J flag

    Unlike 'auto', 'cpus' is not bounded by datalad.runtime.max-annex-jobs,
    so the resolved value is passed straight through as -J<n>.
    """
    repo = AnnexRepo(path, create=True)
    # use a distinctive (>1, so -J is emitted) value to avoid coincidences
    with patch('datalad.support.annexrepo.available_cpu_count',
               return_value=7), \
            patch.object(repo, '_git_runner') as runner:
        repo._call_annex(['find'], jobs='cpus')
    cmd = runner.run.call_args[0][0]
    assert '-J7' in cmd


@pytest.mark.ai_generated
def test_available_cpu_count_warns_when_undetermined():
    """available_cpu_count warns and returns 1 when the OS cannot report a count"""
    import datalad.utils as du
    with patch.object(du, '_n_available_cpus', None), \
         patch('os.sched_getaffinity', side_effect=AttributeError, create=True), \
         patch('os.cpu_count', return_value=None), \
         swallow_logs(new_level=logging.WARNING) as cml:
        n = available_cpu_count()
    assert n == 1
    cml.assert_logged("Could not determine", level='WARNING', regex=False)
