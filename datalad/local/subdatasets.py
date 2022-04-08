# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
import warnings

from datalad.interface.base import Interface
from datalad.interface.utils import generic_result_renderer
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
    NoneDeprecated,
)
from datalad.support.param import Parameter
from datalad.support.exceptions import (
    CapturedException,
    CommandError
)
from datalad.interface.common_opts import (
    contains,
    dataset_state,
    fulfilled,
    recursion_flag,
    recursion_limit,
)
from datalad.distribution.dataset import (
    Dataset,
    require_dataset,
)
from datalad.support.gitrepo import GitRepo
from datalad.utils import (
    ensure_list,
    getpwd,
    partition,
    Path,
)

from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    resolve_path,
)

lgr = logging.getLogger('datalad.local.subdatasets')


valid_key = re.compile(r'^[A-Za-z][-A-Za-z0-9]*$')


def _parse_git_submodules(ds, paths, cache):
    """All known ones with some properties"""
    ds_pathobj = ds.pathobj
    if not (ds_pathobj / ".gitmodules").exists():
        # easy way out. if there is no .gitmodules file
        # we cannot have (functional) subdatasets
        return

    if paths:
        paths_outside, paths_at_or_in = partition(
            paths,
            lambda p: ds_pathobj == p or ds_pathobj in p.parents)
        paths = [p.relative_to(ds_pathobj) for p in paths_at_or_in]
        if not paths:
            if any(p for p in paths_outside if p in ds_pathobj.parents):
                # The dataset is directly under some specified path, so include
                # it.
                paths = None
            else:
                # we had path constraints, but none matched this dataset
                return
    # can we use the reported as such, or do we need to recode wrt to the
    # query context dataset?
    cache['repo'] = repo = ds.repo
    if ds_pathobj == repo.pathobj:
        yield from repo.get_submodules_(paths=paths)
    else:
        for props in repo.get_submodules_(paths=paths):
            props['path'] = ds_pathobj / props['path'].relative_to(repo.pathobj)
            yield props


@build_doc
class Subdatasets(Interface):
    r"""Report subdatasets and their properties.

    The following properties are reported (if possible) for each matching
    subdataset record.

    "name"
        Name of the subdataset in the parent (often identical with the
        relative path in the parent dataset)

    "path"
        Absolute path to the subdataset

    "parentds"
        Absolute path to the parent dataset

    "gitshasum"
        SHA1 of the subdataset commit recorded in the parent dataset

    "state"
        Condition of the subdataset: 'absent', 'present'

    "gitmodule_url"
        URL of the subdataset recorded in the parent

    "gitmodule_name"
        Name of the subdataset recorded in the parent

    "gitmodule_<label>"
        Any additional configuration property on record.

    Performance note: Property modification, requesting `bottomup` reporting
    order, or a particular numerical `recursion_limit` implies an internal
    switch to an alternative query implementation for recursive query that is
    more flexible, but also notably slower (performs one call to Git per
    dataset versus a single call for all combined).

    The following properties for subdatasets are recognized by DataLad
    (without the 'gitmodule\_' prefix that is used in the query results):

    "datalad-recursiveinstall"
        If set to 'skip', the respective subdataset is skipped when DataLad
        is recursively installing its superdataset. However, the subdataset
        remains installable when explicitly requested, and no other features
        are impaired.

    "datalad-url"
        If a subdataset was originally established by cloning, 'datalad-url'
        records the URL that was used to do so. This might be different from
        'url' if the URL contains datalad specific pieces like any URL of the
        form "ria+<some protocol>...".
    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to query.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""path/name to query for subdatasets. Defaults to the
            current directory[PY: , or the entire dataset if called as
            a dataset method PY].""",
            nargs='*',
            constraints=EnsureStr() | EnsureNone()),
        state=dataset_state,
        fulfilled=fulfilled,
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        contains=contains,
        bottomup=Parameter(
            args=("--bottomup",),
            action="store_true",
            doc="""whether to report subdatasets in bottom-up order along
            each branch in the dataset tree, and not top-down."""),
        set_property=Parameter(
            args=('--set-property',),
            metavar=('NAME', 'VALUE'),
            nargs=2,
            action='append',
            doc="""Name and value of one or more subdataset properties to
            be set in the parent dataset's .gitmodules file. The property name
            is case-insensitive, must start with a letter, and consist only
            of alphanumeric characters. The value can be
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

    result_renderer = "tailored"

    @staticmethod
    @datasetmethod(name='subdatasets')
    @eval_results
    def __call__(
            path=None,
            *,
            dataset=None,
            state='any',
            fulfilled=NoneDeprecated,
            recursive=False,
            recursion_limit=None,
            contains=None,
            bottomup=False,
            set_property=None,
            delete_property=None):
        if fulfilled is not NoneDeprecated:
            # the two mirror options do not agree and the deprecated one is
            # not at default value
            warnings.warn("subdatasets's `fulfilled` option is deprecated "
                          "and will be removed in a future release, "
                          "use the `state` option instead.",
                          DeprecationWarning)
            if state != 'any':
                raise ValueError("Do not specify both 'fulfilled' and 'state', use 'state'")
            # honor the old option for now
            state = {
                None: 'any',
                True: 'present',
                False: 'absent',
            }[fulfilled]
        # Path of minimal resistance/code-change - internally here we will reuse fulfilled
        fulfilled = {
            'any': None,
            'present': True,
            'absent': False,
        }[state]
        ds = require_dataset(
            dataset, check_installed=True, purpose='report on subdataset(s)')

        paths = resolve_path(ensure_list(path), dataset, ds) if path else None

        # no constraints given -> query subdatasets under curdir
        if not paths and dataset is None:
            cwd = Path(getpwd())
            paths = None if cwd == ds.pathobj else [cwd]

        lgr.debug('Query subdatasets of %s', dataset)
        if paths is not None:
            lgr.debug('Query subdatasets underneath paths: %s', paths)
        refds_path = ds.path

        # return as quickly as possible
        if isinstance(recursion_limit, int) and (recursion_limit <= 0):
            return

        if set_property:
            for k, v in set_property:
                if valid_key.match(k) is None:
                    raise ValueError(
                        "key '%s' is invalid (alphanumeric plus '-' only, must "
                        "start with a letter)" % k)
        if contains:
            contains = resolve_path(ensure_list(contains), dataset, ds)
            # expand all test cases for the contains test in the loop below
            # leads to ~20% speedup per loop iteration of a non-match
            expanded_contains = [[c] + list(c.parents) for c in contains]
        else:
            expanded_contains = []
        contains_hits = set()
        for r in _get_submodules(
                ds, paths, fulfilled, recursive, recursion_limit,
                expanded_contains, bottomup, set_property, delete_property,
                refds_path):
            # a boat-load of ancient code consumes this and is ignorant of
            # Path objects
            r['path'] = str(r['path'])
            # without the refds_path cannot be rendered/converted relative
            # in the eval_results decorator
            r['refds'] = refds_path
            if 'contains' in r:
                contains_hits.update(r['contains'])
                r['contains'] = [str(c) for c in r['contains']]
            yield r
        if contains:
            for c in set(contains).difference(contains_hits):
                yield get_status_dict(
                    'subdataset',
                    path=str(c),
                    status='impossible',
                    message='path not contained in any matching subdataset',
                    # we do not want to log such an event, because it is a
                    # legit query to check for matching subdatasets simply
                    # for the purpose of further decision making
                    # user communication in front-end scenarios will happen
                    # via result rendering
                    #logger=lgr
                )

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        generic_result_renderer(res)


# internal helper that needs all switches, simply to avoid going through
# the main command interface with all its decorators again
def _get_submodules(ds, paths, fulfilled, recursive, recursion_limit,
                    contains, bottomup, set_property, delete_property,
                    refds_path):
    lookup_cache = {}
    # it should be OK to skip the extra check, because _parse_git_submodules()
    # we specifically look for .gitmodules and the rest of the function
    # is on its results
    #if not GitRepo.is_valid_repo(dspath):
    #    return
    # put in giant for-loop to be able to yield results before completion
    for sm in _parse_git_submodules(ds, paths, lookup_cache):
        repo = lookup_cache['repo']
        sm_path = sm['path']
        contains_hits = None
        if contains:
            contains_hits = [c[0] for c in contains if sm_path in c]
            if not contains_hits:
                # we are not looking for this subds, because it doesn't
                # match the target path
                continue
        # the following used to be done by _parse_git_submodules()
        # but is expensive and does not need to be done for submodules
        # not matching `contains`
        if not sm_path.exists() or not GitRepo.is_valid_repo(sm_path):
            sm['state'] = 'absent'
        else:
            assert 'state' not in sm
            sm['state'] = 'present'
        # do we just need this to recurse into subdatasets, or is this a
        # real results?
        to_report = paths is None \
            or any(p == sm_path or p in sm_path.parents
                   for p in paths)
        if to_report and (set_property or delete_property):
            # first deletions
            for dprop in ensure_list(delete_property):
                try:
                    repo.call_git(
                        ['config', '--file', '.gitmodules',
                         '--unset-all',
                         'submodule.{}.{}'.format(sm['gitmodule_name'], dprop),
                        ]
                    )
                except CommandError:
                    yield get_status_dict(
                        'subdataset',
                        status='impossible',
                        message=(
                            "Deleting subdataset property '%s' failed for "
                            "subdataset '%s', possibly did "
                            "not exist",
                            dprop, sm['gitmodule_name']),
                        logger=lgr,
                        **sm)
                # also kick from the info we just read above
                sm.pop('gitmodule_{}'.format(dprop), None)
            # and now setting values
            for sprop in ensure_list(set_property):
                prop, val = sprop
                if val.startswith('<') and val.endswith('>') and '{' in val:
                    # expand template string
                    val = val[1:-1].format(
                        **dict(
                            sm,
                            refds_relpath=sm_path.relative_to(refds_path),
                            refds_relname=str(
                                sm_path.relative_to(refds_path)
                            ).replace(os.sep, '-')))
                try:
                    repo.call_git(
                        ['config', '--file', '.gitmodules',
                         '--replace-all',
                         'submodule.{}.{}'.format(sm['gitmodule_name'], prop),
                         str(val),
                        ]
                    )
                except CommandError as e:  # pragma: no cover
                    # this conditional may not be possible to reach, as
                    # variable name validity is checked before and Git
                    # replaces the file completely, resolving any permission
                    # issues, if the file could be read (already done above)
                    ce = CapturedException(e)
                    yield get_status_dict(
                        'subdataset',
                        status='error',
                        message=("Failed to set property '%s': %s", prop, ce),
                        exception=ce,
                        type='dataset',
                        logger=lgr,
                        **sm)
                    # it is up to parent code to decide whether we would continue
                    # after this

                # also add to the info we just read above
                sm['gitmodule_{}'.format(prop)] = val
            yield from ds.save(
                '.gitmodules', to_git=True,
                message='[DATALAD] modified subdataset properties',
                result_renderer='disabled',
                return_type='generator')

        #common = commonprefix((with_pathsep(subds), with_pathsep(path)))
        #if common.endswith(sep) and common == with_pathsep(subds):
        #    candidates.append(common)
        subdsres = get_status_dict(
            'subdataset',
            status='ok',
            type='dataset',
            logger=lgr)
        subdsres.update(sm)
        subdsres['parentds'] = ds.path
        if to_report:
            if contains_hits:
                subdsres['contains'] = contains_hits
            if (not bottomup and \
                (fulfilled is None or
                 GitRepo.is_valid_repo(sm_path) == fulfilled)):
                yield subdsres

        # expand list with child submodules. keep all paths relative to parent
        # and convert jointly at the end
        if recursive and \
                (recursion_limit in (None, 'existing') or
                 (isinstance(recursion_limit, int) and
                  recursion_limit > 1)):
            for r in _get_submodules(
                    Dataset(sm_path),
                    paths,
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
        if to_report and (bottomup and \
                (fulfilled is None or
                 GitRepo.is_valid_repo(sm_path) == fulfilled)):
            yield subdsres
