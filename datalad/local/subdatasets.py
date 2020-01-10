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

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import (
    EnsureBool,
    EnsureStr,
    EnsureNone,
)
from datalad.support.param import Parameter
from datalad.support.exceptions import CommandError
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
)
from datalad.distribution.dataset import (
    Dataset,
    require_dataset,
)
from datalad.support.gitrepo import GitRepo
from datalad.dochelpers import exc_str
from datalad.utils import (
    assure_list,
    partition,
)

from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    resolve_path,
)

lgr = logging.getLogger('datalad.local.subdatasets')


valid_key = re.compile(r'^[A-Za-z][-A-Za-z0-9]*$')


def _parse_git_submodules(ds_pathobj, repo, paths):
    """All known ones with some properties"""
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
                # we had path contraints, but none matched this dataset
                return
    for props in repo.get_submodules_(paths=paths):
        path = props["path"]
        if props.get('type', None) != 'dataset':
            continue
        if ds_pathobj != repo.pathobj:
            props['path'] = ds_pathobj / path.relative_to(repo.pathobj)
        else:
            props['path'] = path
        if not path.exists() or not GitRepo.is_valid_repo(str(path)):
            props['state'] = 'absent'
        # TODO kill this after some time. We used to do custom things here
        # and gitshasum was called revision. Be nice and duplicate for a bit
        # wipe out when patience is gone
        props['revision'] = props['gitshasum']
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
        Condition of the subdataset: 'clean', 'modified', 'absent', 'conflict'
        as reported by `git submodule`

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
            action='append',
            doc="""limit report to the subdatasets containing the
            given path. If a root path of a subdataset is given the last
            reported dataset will be the subdataset itself.[CMD:  This
            option can be given multiple times CMD][PY:  Can be a list with
            multiple paths PY], in which case datasets will be reported that
            contain any of the given paths.""",
            constraints=EnsureStr() | EnsureNone()),
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

    @staticmethod
    @datasetmethod(name='subdatasets')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            fulfilled=None,
            recursive=False,
            recursion_limit=None,
            contains=None,
            bottomup=False,
            set_property=None,
            delete_property=None):
        # no constraints given -> query subdatasets under curdir
        if not path and dataset is None:
            path = os.curdir
        paths = [resolve_path(p, dataset) for p in assure_list(path)] \
            if path else None

        ds = require_dataset(
            dataset, check_installed=True, purpose='subdataset reporting/modification')
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
            contains = [resolve_path(c, dataset) for c in assure_list(contains)]
        contains_hits = set()
        for r in _get_submodules(
                ds, paths, fulfilled, recursive, recursion_limit,
                contains, bottomup, set_property, delete_property,
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



# internal helper that needs all switches, simply to avoid going through
# the main command interface with all its decorators again
def _get_submodules(ds, paths, fulfilled, recursive, recursion_limit,
                    contains, bottomup, set_property, delete_property,
                    refds_path):
    dspath = ds.path
    repo = ds.repo
    if not GitRepo.is_valid_repo(dspath):
        return
    # put in giant for-loop to be able to yield results before completion
    for sm in _parse_git_submodules(ds.pathobj, repo, paths):
        contains_hits = []
        if contains:
            contains_hits = [
                c for c in contains if sm['path'] == c or sm['path'] in c.parents
            ]
            if not contains_hits:
                # we are not looking for this subds, because it doesn't
                # match the target path
                continue
        # do we just need this to recurse into subdatasets, or is this a
        # real results?
        to_report = paths is None \
            or any(p == sm['path'] or p in sm['path'].parents
                   for p in paths)
        if to_report and (set_property or delete_property):
            # first deletions
            for dprop in assure_list(delete_property):
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
            for sprop in assure_list(set_property):
                prop, val = sprop
                if val.startswith('<') and val.endswith('>') and '{' in val:
                    # expand template string
                    val = val[1:-1].format(
                        **dict(
                            sm,
                            refds_relpath=sm['path'].relative_to(refds_path),
                            refds_relname=str(
                                sm['path'].relative_to(refds_path)
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
                    yield get_status_dict(
                        'subdataset',
                        status='error',
                        message=(
                            "Failed to set property '%s': %s",
                            prop, exc_str(e)),
                        type='dataset',
                        logger=lgr,
                        **sm)
                    # it is up to parent code to decide whether we would continue
                    # after this

                # also add to the info we just read above
                sm['gitmodule_{}'.format(prop)] = val
            ds.save(
                '.gitmodules', to_git=True,
                message='[DATALAD] modified subdataset properties')

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
        if to_report:
            if contains_hits:
                subdsres['contains'] = contains_hits
            if (not bottomup and \
                (fulfilled is None or
                 GitRepo.is_valid_repo(sm['path']) == fulfilled)):
                yield subdsres

        # expand list with child submodules. keep all paths relative to parent
        # and convert jointly at the end
        if recursive and \
                (recursion_limit in (None, 'existing') or
                 (isinstance(recursion_limit, int) and
                  recursion_limit > 1)):
            for r in _get_submodules(
                    Dataset(sm['path']),
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
                 GitRepo.is_valid_repo(sm['path']) == fulfilled)):
            yield subdsres
