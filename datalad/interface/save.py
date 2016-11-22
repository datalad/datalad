# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""For now just a wrapper for Dataset.save()

"""

__docformat__ = 'restructuredtext'

import logging

import os
from os.path import join as opj, isdir, realpath, relpath, pardir
from os.path import isabs

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import resolve_path
from datalad.distribution.utils import _install_subds_inplace
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import super_datasets_flag
from datalad.utils import assure_list
from datalad.utils import with_pathsep as _with_sep

from .base import Interface

lgr = logging.getLogger('datalad.interface.commit')


def untracked_subdatasets_to_submodules(ds, consider_paths):
    # treat special case of still untracked subdatasets.
    # those need to become submodules now, as they are otherwise added
    # without an entry in .gitmodules, and subsequently break Git's
    # submodule functionality completely
    new_modules = []
    if not consider_paths:
        # nothing to test
        return new_modules

    for utf in ds.repo.repo.untracked_files:
        utf_abspath = opj(ds.path, utf)
        if not isdir(utf_abspath):
            # this cannot be a repository
            continue

        # test whether the potential submodule is scheduled for saving
        utf_realpath = realpath(utf_abspath)
        if any([utf_realpath.startswith(_with_sep(realpath(f)))
                for f in consider_paths]):
            # matches at least one path -> turn into submodule
            _install_subds_inplace(
                ds=ds,
                path=utf_abspath,  # can be ignored, we don't need the return value
                relativepath=utf.rstrip(os.sep),
                name=None)
            new_modules.append(utf.rstrip(os.sep))

    return new_modules


def deinit_deleted_submodules(ds):
    # helper to inspect a repo and `deinit` all submodules that are reported
    # as present, but the mountpoint doesn't exist
    deleted = ds.repo.get_deleted_files()
    deinited = []
    for subdspath in ds.get_subdatasets(absolute=False, recursive=False):
        if subdspath in deleted:
            lgr.debug('deinit deleted subdataset {} in {}'.format(subdspath, ds))
            ds.repo.deinit_submodule(subdspath)
            deinited.append(subdspath)
    return deinited


class Save(Interface):
    """Save the current state of a dataset

    Saving the state of a dataset records all changes that have been made
    to it. This change record is annotated with a user-provided description.
    Optionally, an additional tag, such as a version, can be assigned to the
    saved state. Such tag enables straightforward retrieval of past versions
    at a later point in time.

    || PYTHON >>
    Returns
    -------
    commit or None
      `None` if nothing was saved, the resulting commit otherwise.
    << PYTHON ||
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to save. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        files=Parameter(
            args=("files",),
            metavar='FILES',
            doc="""list of files to consider. If given, only changes made
            to those files are recorded in the new state.""",
            nargs='*',
            constraints=EnsureStr() | EnsureNone()),
        message=Parameter(
            args=("-m", "--message",),
            metavar='MESSAGE',
            doc="""a message to annotate the saved state.""",
            constraints=EnsureStr() | EnsureNone()),
        auto_add_changes=Parameter(
            args=("-a", "--auto-add-changes"),
            doc="""automatically include all changes in the entire dataset,
            independent of the current working directory.""",
            action="store_true"),
        version_tag=Parameter(
            args=("--version-tag",),
            metavar='ID',
            doc="""an additional marker for that state.""",
            constraints=EnsureStr() | EnsureNone()),
        super_datasets=super_datasets_flag,
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='save')
    def __call__(message=None, files=None, dataset=None,
                 auto_add_changes=False, version_tag=None,
                 recursive=False, recursion_limit=None, super_datasets=False):
        # shortcut
        ds = require_dataset(dataset, check_installed=True,
                             purpose='saving')

        ds.repo.precommit()

        if not ds.repo.repo.is_dirty(
                index=True,
                working_tree=True,
                untracked_files=True,
                submodules=True):
            # if we cannot see anything dirty at all, the only things we could
            # do is tag
            if version_tag:
                ds.repo.tag(version_tag)
            # take the easy one out
            return

        # always yields list; empty if None
        files = assure_list(files)

        # track what to be committed, so it becomes
        # possible to decide when/what to save further down
        # and one level up
        orig_hexsha = ds.repo.get_hexsha()
        to_commit = []

        # before anything, let's deal with missing submodules that may have
        # been rm'ed by the user
        # this will not alter/amend the history of the dataset
        deinit_deleted_submodules(ds)

        # XXX path resolution needs to happen on the input argument, not the
        # resolved dataset!
        # otherwise we will not be able to figure out, whether there was an
        # explicit dataset provided, or just a matching one resolved
        # automatically.
        # if files are provided but no dataset, we interpret them as
        # CWD-related

        if auto_add_changes:
            # use the dataset's base path to indicate that everything
            # should be saved
            if files:
                lgr.warning(
                    "List of paths was provided to save but auto_add_changes "
                    "was specified, so list of paths was ignored")
            files = [ds.path]
        else:
            # make sure we apply the usual path interpretation logic
            files = [resolve_path(p, dataset) for p in files]

        new_submodules = untracked_subdatasets_to_submodules(ds, files)
        if new_submodules:
            # make sure that .gitmodules is added to the list of files
            # to be committed.  Adding to index might not be enough iff
            # custom files was provided
            to_commit.append('.gitmodules')
        to_commit.extend(new_submodules)

        # now we should have a complete list of submodules to potentially
        # recurse into
        if recursive and (recursion_limit is None or recursion_limit > 0):
            # what subdataset to touch?
            subdss = []
            if auto_add_changes:
                # all installed 1st-level ones
                # we only want immediate subdatasets, higher depths will come
                # via recursion
                subdss = [Dataset(opj(ds.path, subds_path))
                          for subds_path in ds.get_subdatasets(
                              recursive=False)]
            elif files is not None:
                # only subdatasets that contain any of the to-be-considered
                # paths
                # TODO:  the same deductions will be redone later again
                #  very inefficient.  Should be just sorted into subds
                #  once!
                subdss = [ds.get_containing_subdataset(
                    p, recursion_limit=1) for p in files]

            # skip anything that isn't installed, or this dataset
            subdss = [d for d in subdss if d.is_installed() and d != ds]

            prop_recursion_limit = \
                None if recursion_limit is None else max(recursion_limit - 1, 0)

            for subds in subdss:
                # TODO: just make use of get._sort_paths_into_datasets
                # currently it is very inefficient since for the same ds
                # it asks about subdatasets for every file!
                subds_files = []  # files belonging to the subds
                todo_files = []   # leftover files
                for f in files:
                    if ds.get_containing_subdataset(f, recursion_limit=1) == subds:
                        subds_files.append(f)
                    else:
                        todo_files.append(f)
                files = todo_files

                subds_modified = Save.__call__(
                    message=message,
                    files=subds_files,
                    dataset=subds,
                    auto_add_changes=auto_add_changes,
                    version_tag=version_tag,
                    recursive=recursive and (prop_recursion_limit is None or prop_recursion_limit > 0),
                    recursion_limit=prop_recursion_limit,
                )
                if subds_modified:
                    # stage changes in this submodule
                    subdspath = relpath(subds.path, ds.path)
                    ds.repo.add(subdspath, git=True)
                    to_commit.append(subdspath)

        if files:  # could still be none without auto add changes
            ds_subdatasets = ds.get_subdatasets(recursive=False)
            subdatasets_paths = {
                opj(ds.path, f) for f in ds_subdatasets
            }
            # TODO: also use some centralized sorting into sub-datasets
            # e.g. one used in get
            ds_files = [
                f for f in files
                if f in subdatasets_paths or
                    ds.get_containing_subdataset(f, recursion_limit=1) == ds
            ]
            if len(ds_files):
                # XXX Is there a better way to handle files in mixed repos?
                ds.repo.add(ds_files)
                ds.repo.add(ds_files, git=True)
                to_commit.extend(ds_files)
            # it might be that the file itself is the submodule, so we might
            # need to commit .gitmodules
            for f in files:
                for subds in subdatasets_paths:
                    if subds.rstrip('/') == f.rstrip('/'):
                        to_commit.append('.gitmodules')
                        break

        _datalad_msg = False
        if not message:
            message = 'Recorded existing changes'
            _datalad_msg = True

        # extend with files yet to be committed in this dataset
        to_commit.extend(files)

        # anything should be staged by now
        # however, staged submodule changes are not considered as
        # `index`, hence `submodules` needs to be True too
        # we can have an explicit list of stuff to save or (if no `files`
        # provided) have staged stuff
        if ds.repo.repo.is_dirty(
                index=True,
                working_tree=False,
                untracked_files=False,
                submodules=True):

            # Analyze list of known to be committed files/submodules,
            # see if nothing points outside, and then convert to relative paths
            to_commit_rel = []
            if to_commit:
                repopath = ds.repo.path
                for f in to_commit:
                    if isabs(f):
                        frel = relpath(f, repopath)
                        if frel.startswith(pardir):
                            # XXX may be just a warning and skip?
                            raise RuntimeError(
                                "Path %s outside of the dataset %s. Can't commit"
                                % (f, ds)
                            )
                        f = frel
                    to_commit_rel.append(f)
                to_commit_rel = sorted(set(to_commit_rel))
                if '.' in to_commit_rel:
                    # we need to commit everything
                    to_commit_rel = []

            ds.repo.commit(message, options=to_commit_rel, _datalad_msg=_datalad_msg)
        elif to_commit:
            lgr.warning(
                "Was instructed to commit %s files but repository is not dirty",
                to_commit)
        elif not auto_add_changes:
            lgr.info(
                'Nothing to save, consider auto-detection of changes, '
                'if this is unexpected.')

        # MIH: let's tag even if there was nothing commit. I'd forget this
        # option too often...
        if version_tag:
            ds.repo.tag(version_tag)

        _was_modified = ds.repo.get_hexsha() != orig_hexsha

        # and now we could consider saving our changes within super-datasets
        # Let's float up until we get to a non-dataset
        if super_datasets:
            if _was_modified:
                if version_tag:
                    lgr.info("Version tag %s will not be applied to super datasets",
                             version_tag)
                superds = ds
                while True:
                    supersubds = superds
                    superds = superds.get_superdataset(datalad_only=True)
                    if not superds:
                        break
                    Save.__call__(
                        message=message
                            + " [origin: %s]" % relpath(ds.path, superds.path),
                        files=[relpath(supersubds.path, superds.path)],
                        dataset=superds,
                        auto_add_changes=False,
                        version_tag=None,
                        recursive=False,
                    )
            else:
                lgr.info(
                    "Not trying to save super-datasets since no modifications")

        # TODO: figure out what we should return for recursive/super_datasets
        # shouldn't we return all commits???
        return ds.repo.repo.head.commit if _was_modified else None

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if res:
            ui.message('Saved state: "{0}" by {1} [{2}]'.format(
                res.message.splitlines()[0],
                res.committer,
                res.hexsha))
