# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for reporting subdatasets"""

__docformat__ = 'restructuredtext'


import logging
import re
from os.path import join as opj
from os.path import normpath

from git import GitConfigParser

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import EnsureBool
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.distribution.dataset import require_dataset
from datalad.cmd import GitRunner
from datalad.support.gitrepo import GitRepo
from datalad.utils import with_pathsep as _with_sep

from .dataset import EnsureDataset
from .dataset import datasetmethod

lgr = logging.getLogger('datalad.distribution.subdatasets')


submodule_full_props = re.compile(r'([0-9a-f]+) (.*) \((.*)\)$')
submodule_nodescribe_props = re.compile(r'([0-9a-f]+) (.*)$')

status_map = {
    ' ': 'clean',
    '+': 'modified',
    '-': 'absent',
    'U': 'conflict',
}


def _parse_gitmodules(dspath):
    gitmodule_path = opj(dspath, ".gitmodules")
    parser = GitConfigParser(gitmodule_path)
    mods = {}
    for sec in parser.sections():
        modpath = parser.get_value(sec, 'path', default=0)
        if not modpath or not sec.startswith('submodule '):
            continue
        modpath = normpath(opj(dspath, modpath))
        modprops = {opt: parser.get_value(sec, opt)
                    for opt in parser.options(sec)
                    if not (opt.startswith('__') or opt == 'path')}
        modprops['name'] = sec[11:-1]
        mods[modpath] = modprops
    return mods


def _parse_git_submodules(dspath, recursive):
    """All known ones with some properties"""
    # this will not work in direct mode, need better way #1422
    cmd = ['git', '--work-tree=.', 'submodule', 'status']
    if recursive:
        cmd.append('--recursive')

    # need to go rogue  and cannot use proper helper in GitRepo
    # as they also pull in all of GitPython's magic
    stdout, stderr = GitRunner(cwd=dspath).run(
        cmd,
        log_stderr=False,
        log_stdout=True,
        log_online=False,
        expect_stderr=False,
        shell=False,
        expect_fail=False)

    for line in stdout.split('\n'):
        if not line:
            continue
        sm = {}
        sm['state'] = status_map[line[0]]
        props = submodule_full_props.match(line[1:])
        if props:
            sm['reccommit'] = props.group(1)
            sm['path'] = opj(dspath, props.group(2))
            sm['describe'] = props.group(3)
        else:
            props = submodule_nodescribe_props.match(line[1:])
            sm['reccommit'] = props.group(1)
            sm['path'] = opj(dspath, props.group(2))
        yield sm


@build_doc
class Subdatasets(Interface):
    """Report subdatasets and their properties.

    The following properties are reported (if possible) for each matching
    subdataset record.

    "describe"
        Output of `git describe` for the subdataset

    "name"
        Name of the subdataset in the parent (often identical with the
        relative path in the parent dataset)

    "path"
        Absolute path to the subdataset

    "parentpath"
        Absolute path to the parent dataset

    "reccommit"
        SHA1 of the subdataset commit recorded in the parent dataset

    "state"
        Condition of the subdataset: 'clean', 'modified', 'absent', 'conflict'
        as reported by `git submodule`

    "url"
        URL of the subdataset recorded in the parent

    Performance note: Requesting `bottomup` reporting order, or a particular
    numerical `recursion_limit` implies an internal switch to an alternative
    query implementation for recursive query that is more flexible, but also
    notably slower (performs one call to Git per dataset versus a single call
    for all combined).

    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to update.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        fulfilled=Parameter(
            args=("--fulfilled",),
            doc="""if given, must be a boolean flag indicating whether
            to report either only locally present or absent datasets.
            By default subdatasets are reported regardless of their
            status""",
            constraints=EnsureBool() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        bottomup=Parameter(
            args=("--bottomup",),
            action="store_true",
            doc="""whether to report subdatasets in bottom-up order along
            each branch in the dataset tree, and not top-down."""))

    @staticmethod
    @datasetmethod(name='subdatasets')
    @eval_results
    def __call__(
            dataset=None,
            fulfilled=None,
            recursive=False,
            recursion_limit=None,
            bottomup=False):
        dataset = require_dataset(
            dataset, check_installed=False, purpose='subdataset reporting')
        refds_path = dataset.path

        # return as quickly as possible
        if isinstance(recursion_limit, int) and (recursion_limit <= 0):
            return

        if bottomup or (recursive and recursion_limit is not None):
            # IMPLEMENTATION 1
            # slow but flexible (one Git call per dataset)
            for r in _get_submodules(
                    dataset.path, fulfilled, recursive, recursion_limit,
                    bottomup):
                # without the refds_path cannot be rendered/converted relative
                # in the eval_results decorator
                r['refds'] = refds_path
                yield r
        else:
            # IMPLEMENTATION 2
            # as fast as possible (just a single call to Git)
            # need to track current parent
            stack = [refds_path]
            modinfo_cache = {}
            for sm in _parse_git_submodules(refds_path, recursive=recursive):
                # unwind the parent stack until we find the right one
                # this assumes that submodules come sorted
                while not sm['path'].startswith(_with_sep(stack[-1])):
                    stack.pop()
                parent = stack[-1]
                if parent not in modinfo_cache:
                    # read the parent .gitmodules, if not done yet
                    modinfo_cache[parent] = _parse_gitmodules(parent)
                # get URL info, etc.
                sm.update(modinfo_cache[parent].get(sm['path'], {}))
                subdsres = get_status_dict(
                    'subdataset',
                    status='ok',
                    type_='dataset',
                    refds=refds_path,
                    logger=lgr)
                subdsres.update(sm)
                subdsres['parentpath'] = parent
                if (fulfilled is None or
                        GitRepo.is_valid_repo(sm['path']) == fulfilled):
                    yield subdsres
                # for the next "parent" commit this subdataset to the stack
                stack.append(sm['path'])


# internal helper that needs all switches, simply to avoid going through
# the main command interface with all its decorators again
def _get_submodules(dspath, fulfilled, recursive, recursion_limit,
                    bottomup):
    if not GitRepo.is_valid_repo(dspath):
        return
    modinfo = _parse_gitmodules(dspath)
    # put in giant for-loop to be able to yield results before completion
    for sm in _parse_git_submodules(dspath, recursive=False):
        sm.update(modinfo.get(sm['path'], {}))
        subdsres = get_status_dict(
            'subdataset',
            status='ok',
            type_='dataset',
            logger=lgr)
        subdsres.update(sm)
        subdsres['parentpath'] = dspath
        if not bottomup and \
                (fulfilled is None or
                 GitRepo.is_valid_repo(sm['path']) == fulfilled):
            yield subdsres

        # expand list with child submodules. keep all paths relative to parent
        # and convert jointly at the end
        if recursive and \
                (recursion_limit in (None, 'existing') or
                 (isinstance(recursion_limit, int) and
                  recursion_limit > 1)):
            for r in _get_submodules(
                    sm['path'],
                    fulfilled, recursive,
                    (recursion_limit - 1)
                    if isinstance(recursion_limit, int)
                    else recursion_limit,
                    bottomup):
                yield r
        if bottomup and \
                (fulfilled is None or
                 GitRepo.is_valid_repo(sm['path']) == fulfilled):
            yield subdsres
