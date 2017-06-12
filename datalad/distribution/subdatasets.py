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
import os
from os.path import join as opj
from os.path import normpath
from os.path import relpath
from os.path import exists

from git import GitConfigParser

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import EnsureBool
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.gitrepo import InvalidGitRepositoryError
from datalad.support.exceptions import CommandError
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.distribution.dataset import require_dataset
from datalad.cmd import GitRunner
from datalad.support.gitrepo import GitRepo
from datalad.utils import with_pathsep as _with_sep
from datalad.utils import assure_list
from datalad.dochelpers import exc_str

from .dataset import EnsureDataset
from .dataset import datasetmethod
from .dataset import resolve_path

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
        modprops = {'gitmodule_{}'.format(opt): parser.get_value(sec, opt)
                    for opt in parser.options(sec)
                    if not (opt.startswith('__') or opt == 'path')}
        modprops['gitmodule_name'] = sec[11:-1]
        mods[modpath] = modprops
    return mods


def _parse_git_submodules(dspath, recursive):
    """All known ones with some properties"""
    if not exists(opj(dspath, ".gitmodules")):
        # easy way out. if there is no .gitmodules file
        # we cannot have (functional) subdatasets
        return

    # this will not work in direct mode, need better way #1422
    cmd = ['git', '--work-tree=.', 'submodule', 'status']
    if recursive:
        cmd.append('--recursive')

    # need to go rogue  and cannot use proper helper in GitRepo
    # as they also pull in all of GitPython's magic
    try:
        stdout, stderr = GitRunner(cwd=dspath).run(
            cmd,
            log_stderr=True,
            log_stdout=True,
            # not sure why exactly, but log_online has to be false!
            log_online=False,
            expect_stderr=False,
            shell=False,
            # we don't want it to scream on stdout
            expect_fail=True)
    except CommandError as e:
        raise InvalidGitRepositoryError(exc_str(e))

    for line in stdout.split('\n'):
        if not line:
            continue
        sm = {}
        sm['state'] = status_map[line[0]]
        props = submodule_full_props.match(line[1:])
        if props:
            sm['revision'] = props.group(1)
            sm['path'] = opj(dspath, props.group(2))
            sm['revision_descr'] = props.group(3)
        else:
            props = submodule_nodescribe_props.match(line[1:])
            sm['revision'] = props.group(1)
            sm['path'] = opj(dspath, props.group(2))
        yield sm


def _get_gitmodule_parser(dspath):
    """Get a parser instance for write access"""
    gitmodule_path = opj(dspath, ".gitmodules")
    parser = GitConfigParser(gitmodule_path, read_only=False, merge_includes=False)
    parser.read()
    return parser


@build_doc
class Subdatasets(Interface):
    """Report subdatasets and their properties.

    The following properties are reported (if possible) for each matching
    subdataset record.

    "name"
        Name of the subdataset in the parent (often identical with the
        relative path in the parent dataset)

    "path"
        Absolute path to the subdataset

    "parentds"
        Absolute path to the parent dataset

    "revision"
        SHA1 of the subdataset commit recorded in the parent dataset

    "state"
        Condition of the subdataset: 'clean', 'modified', 'absent', 'conflict'
        as reported by `git submodule`

    "revision_descr"
        Output of `git describe` for the subdataset

    "gitmodule_url"
        URL of the subdataset recorded in the parent

    "gitmodule_<label>"
        Any additional configuration property on record.

    Performance note: Requesting `bottomup` reporting order, or a particular
    numerical `recursion_limit` implies an internal switch to an alternative
    query implementation for recursive query that is more flexible, but also
    notably slower (performs one call to Git per dataset versus a single call
    for all combined).

    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to query.  If
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
        contains=Parameter(
            args=('--contains',),
            metavar='PATH',
            doc="""limit report to the subdatasets containing the
            given path. If a root path of a subdataset is given the last
            reported dataset will be the subdataset itself.""",
            constraints=EnsureStr() | EnsureNone()),
        bottomup=Parameter(
            args=("--bottomup",),
            action="store_true",
            doc="""whether to report subdatasets in bottom-up order along
            each branch in the dataset tree, and not top-down."""),
        set_property=Parameter(
            args=('--set-property',),
            metavar='VALUE',
            nargs=2,
            action='append',
            doc="""Name and value of one or more subdataset properties to
            be set in the parent dataset's .gitmodules file. The value can be
            a Python format() template string wrapped in '<>' (e.g.
            '<{gitmodule_name}>').
            Supported keywords are any item reported in the result properties
            of this command, plus 'refds_relpath' and 'refds_relname':
            the relative path of a subdataset with respect to the base dataset
            of the command call, and, in the latter case, the same string with
            all directory separators replaced by dashes.[CMD:  This
            option can be given multiple times. CMD]""",
            constraints=EnsureStr() | EnsureNone()),
        delete_property=Parameter(
            args=('--delete-property',),
            metavar='NAME',
            action='append',
            doc="""Name of one or more subdataset properties to be removed
            from the parent dataset's .gitmodules file.[CMD:  This
            option can be given multiple times. CMD]""",
            constraints=EnsureStr() | EnsureNone()))

    @staticmethod
    @datasetmethod(name='subdatasets')
    @eval_results
    def __call__(
            dataset=None,
            fulfilled=None,
            recursive=False,
            recursion_limit=None,
            contains=None,
            bottomup=False,
            set_property=None,
            delete_property=None):
        dataset = require_dataset(
            dataset, check_installed=False, purpose='subdataset reporting/modification')
        refds_path = dataset.path

        # XXX this seems strange, but is tested to be the case -- I'd rather set
        # `check_installed` to true above and fail
        if not GitRepo.is_valid_repo(refds_path):
            return

        # return as quickly as possible
        if isinstance(recursion_limit, int) and (recursion_limit <= 0):
            return

        try:
            if not (bottomup or contains or set_property or delete_property or \
                    (recursive and recursion_limit is not None)):
                # FAST IMPLEMENTATION FOR THE STRAIGHTFORWARD CASE
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
                        type='dataset',
                        refds=refds_path,
                        logger=lgr)
                    subdsres.update(sm)
                    subdsres['parentds'] = parent
                    if (fulfilled is None or
                            GitRepo.is_valid_repo(sm['path']) == fulfilled):
                        yield subdsres
                    # for the next "parent" commit this subdataset to the stack
                    stack.append(sm['path'])
                # MUST RETURN: the rest of the function is doing another implementation
                return
        except InvalidGitRepositoryError as e:
            lgr.debug("fast subdataset query failed, trying slow robust one (%s)",
                      exc_str(e))

        # MORE ROBUST, FLEXIBLE, BUT SLOWER IMPLEMENTATION
        # slow but flexible (one Git call per dataset), but deals with subdatasets in
        # direct mode
        if contains:
            contains = resolve_path(contains, dataset)
        for r in _get_submodules(
                dataset.path, fulfilled, recursive, recursion_limit,
                contains, bottomup, set_property, delete_property,
                refds_path):
            # without the refds_path cannot be rendered/converted relative
            # in the eval_results decorator
            r['refds'] = refds_path
            yield r


# internal helper that needs all switches, simply to avoid going through
# the main command interface with all its decorators again
def _get_submodules(dspath, fulfilled, recursive, recursion_limit,
                    contains, bottomup, set_property, delete_property,
                    refds_path):
    if not GitRepo.is_valid_repo(dspath):
        return
    modinfo = _parse_gitmodules(dspath)
    # write access parser
    parser = None
    if set_property or delete_property:
        parser = _get_gitmodule_parser(dspath)
    # put in giant for-loop to be able to yield results before completion
    for sm in _parse_git_submodules(dspath, recursive=False):
        if contains and \
                not (contains == sm['path'] or
                     contains.startswith(_with_sep(sm['path']))):
            # we are not looking for this subds, because it doesn't
            # match the target path
            continue
        sm.update(modinfo.get(sm['path'], {}))
        if set_property or delete_property:
            # do modifications now before we read the info out for reporting
            # use 'submodule "NAME"' section ID style as this seems to be the default
            submodule_section = 'submodule "{}"'.format(sm['gitmodule_name'])
            # first deletions
            for dprop in assure_list(delete_property):
                parser.remove_option(submodule_section, dprop)
                # also kick from the info we just read above
                sm.pop('gitmodule_{}'.format(dprop), None)
            # and now setting values
            for sprop in assure_list(set_property):
                prop, val = sprop
                if val.startswith('<') and val.endswith('>') and '{' in val:
                    # expand template string
                    val = val[1:-1].format(
                        **dict(
                            sm,
                            refds_relpath=relpath(sm['path'], refds_path),
                            refds_relname=relpath(sm['path'], refds_path).replace(os.sep, '-')))
                parser.set_value(
                    submodule_section,
                    prop,
                    val)
                # also add to the info we just read above
                sm['gitmodule_{}'.format(prop)] = val

        #common = commonprefix((with_pathsep(subds), with_pathsep(path)))
        #if common.endswith(sep) and common == with_pathsep(subds):
        #    candidates.append(common)
        subdsres = get_status_dict(
            'subdataset',
            status='ok',
            type='dataset',
            logger=lgr)
        subdsres.update(sm)
        subdsres['parentds'] = dspath
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
                    contains,
                    bottomup,
                    set_property,
                    delete_property,
                    refds_path):
                yield r
        if bottomup and \
                (fulfilled is None or
                 GitRepo.is_valid_repo(sm['path']) == fulfilled):
            yield subdsres
    if parser is not None:
        # release parser lock manually, auto-cleanup is not reliable in PY3
        parser.release()
