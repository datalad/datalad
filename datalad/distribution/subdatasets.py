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
from os.path import (
    join as opj,
    relpath,
    exists,
)
from six import (
    iteritems,
    text_type,
)

from datalad.config import _parse_gitconfig_dump

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
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
)
from datalad.distribution.dataset import (
    Dataset,
    require_dataset,
)
from datalad.support.gitrepo import GitRepo
from datalad.utils import (
    assure_list,
    PurePosixPath,
)

# API commands
import datalad.core.local.save

from .dataset import (
    EnsureDataset,
    datasetmethod,
    rev_resolve_path,
)

lgr = logging.getLogger('datalad.distribution.subdatasets')


submodule_full_props = re.compile(r'([0-9]+) (.*) (.*)\t(.*)$')
valid_key = re.compile(r'^[A-Za-z][-A-Za-z0-9]*$')


def _parse_gitmodules(ds):
    gitmodules = ds.pathobj / '.gitmodules'
    if not gitmodules.exists():
        return {}
    # pull out file content
    out, err = ds.repo._git_custom_command(
        '',
        ['git', 'config', '-z', '-l', '--file', '.gitmodules'])
    # abuse our config parser
    db, _ = _parse_gitconfig_dump(out, {}, None, True)
    mods = {}
    for k, v in iteritems(db):
        if not k.startswith('submodule.'):
            # we don't know what this is
            continue
        k_l = k.split('.')
        mod_name = k_l[1]
        mod = mods.get(mod_name, {})
        mod['.'.join(k_l[2:])] = v
        mods[mod_name] = mod

    out = {}
    # bring into traditional shape
    for name, props in iteritems(mods):
        if 'path' not in props:
            lgr.debug("Failed to get '%s.path', skipping section", name)
            continue
        modprops = {'gitmodule_{}'.format(k): v
                    for k, v in iteritems(props)
                    if not (k.startswith('__') or k == 'path')}
        modpath = ds.pathobj / PurePosixPath(props['path'])
        modprops['gitmodule_name'] = name
        out[modpath] = modprops
    return out


def _parse_git_submodules(ds):
    """All known ones with some properties"""
    dspath = ds.path
    if not exists(opj(dspath, ".gitmodules")):
        # easy way out. if there is no .gitmodules file
        # we cannot have (functional) subdatasets
        return

    # TODO support path matching here
    for path, props in iteritems(ds.repo.get_content_info(
            ref=None,
            untracked='no',
            eval_file_type=False)):
        if props.get('type', None) != 'dataset':
            continue
        if ds.pathobj != ds.repo.pathobj:
            props['path'] = ds.pathobj / path.relative_to(ds.repo.pathobj)
        else:
            props['path'] = path
        if not path.exists() or not GitRepo.is_valid_repo(text_type(path)):
            props['state'] = 'absent'
        # TODO kill this after some time. We used to do custom things here
        # and gitshasum was called revision. Be nice and duplicate for a bit
        # wipe out when patience is gone
        props['revision'] = props['gitshasum']
        yield props


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

        if set_property:
            for k, v in set_property:
                if valid_key.match(k) is None:
                    raise ValueError(
                        "key '%s' is invalid (alphanumeric plus '-' only, must start with a letter)",
                        k)
        if contains:
            contains = [rev_resolve_path(c, dataset) for c in assure_list(contains)]
        for r in _get_submodules(
                dataset, fulfilled, recursive, recursion_limit,
                contains, bottomup, set_property, delete_property,
                refds_path):
            # a boat-load of ancient code consumes this and is ignorant of
            # Path objetcs
            r['path'] = text_type(r['path'])
            # without the refds_path cannot be rendered/converted relative
            # in the eval_results decorator
            r['refds'] = refds_path
            yield r


# internal helper that needs all switches, simply to avoid going through
# the main command interface with all its decorators again
def _get_submodules(ds, fulfilled, recursive, recursion_limit,
                    contains, bottomup, set_property, delete_property,
                    refds_path):
    dspath = ds.path
    if not GitRepo.is_valid_repo(dspath):
        return
    modinfo = _parse_gitmodules(ds)
    # write access parser
    parser = None
    # TODO bring back in more global scope from below once segfaults are
    # figured out
    #if set_property or delete_property:
    #    gitmodule_path = opj(dspath, ".gitmodules")
    #    parser = GitConfigParser(
    #        gitmodule_path, read_only=False, merge_includes=False)
    #    parser.read()
    # put in giant for-loop to be able to yield results before completion
    for sm in _parse_git_submodules(ds):
        if contains and not any(
                sm['path'] == c or sm['path'] in c.parents for c in contains):
            # we are not looking for this subds, because it doesn't
            # match the target path
            continue
        sm.update(modinfo.get(sm['path'], {}))
        if set_property or delete_property:
            gitmodule_path = opj(dspath, ".gitmodules")
            parser = GitConfigParser(
                gitmodule_path, read_only=False, merge_includes=False)
            parser.read()
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
            Dataset(dspath).save(
                '.gitmodules', to_git=True,
                message='[DATALAD] modified subdataset properties')
            # let go of resources, locks, ...
            parser.release()

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
                    Dataset(sm['path']),
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
