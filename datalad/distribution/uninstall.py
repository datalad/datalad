# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for uninstalling a handle

"""

__docformat__ = 'restructuredtext'

import logging
from os.path import join as opj, abspath, exists, isabs, relpath, pardir, isdir
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileInGitError, \
    FileNotInAnnexError
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureBool
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod, resolve_path
from datalad.distribution.install import get_containing_subdataset
from datalad.interface.base import Interface

lgr = logging.getLogger('datalad.distribution.uninstall')


class Uninstall(Interface):
    """Uninstall a dataset component or entire datasets."""

    # TODO: It's not actually clear yet, what are the actual meanings of
    # uninstall (including options) and what exactly are the methods to
    # uninstall certain components.

    # uninstall should be the opposite of install, obviously. that means:
    #   - we uninstall FROM a dataset as opposed to install INTO a dataset
    #   - any operation possible by install should be possible to be reverted
    #     by uninstall

    # If we want to uninstall something "completely", --recursive is implied.
    # Do we require the user to nevertheless explicitly use `recursive`?

    # possible components to uninstall:
    #   - submodule (checked out or not checked out) (fulfilled, unfulfilled)
    #   - annex'ed files with no content
    #   - annex'ed files with content
    #   - files in git
    #   - untracked files ? Do we want to deal with them at all?
    #   - directories (empty or not)? May be not, since we cannot install a
    #     directory, or can we?

    _params_ = dict(
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""specify the dataset to perform the uninstall operation on.
            If no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            doc="path/name of the component to be uninstalled",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        data_only=Parameter(
            args=("--data-only",),
            doc="If set, only data is uninstalled, but the handles are kept.",
            action="store_true"),
        recursive=Parameter(
            args=("--recursive", "-r"),
            doc="""If set, uninstall recursively, including all subdatasets.
            The value of `data` is used for recursive uninstallation, too.""",
            action="store_true"))

    @staticmethod
    @datasetmethod(name='uninstall')
    def __call__(dataset=None, path=None, data_only=True, recursive=False):

        # Note: copy logic from install to resolve dataset and path:
        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)

        if not path:
            if ds is None:
                # no dataset, no target location, nothing to do
                raise ValueError(
                    "insufficient information for uninstallation (needs at "
                    "least a dataset or a path")
        elif isinstance(path, list):
            # TODO: not sure. might be possible to deal with that list directly
            return [Uninstall.__call__(
                    dataset=ds,
                    path=p,
                    data_only=data_only,
                    recursive=recursive) for p in path]

        # resolve the target location against the provided dataset
        if path is not None:
            path = resolve_path(path, ds)

        lgr.debug("Resolved uninstallation target: {0}".format(path))

        # if we have no dataset given, figure out which one we need to operate
        # on, based on the resolved target location (that is now guaranteed to
        # be specified
        if ds is None:
            # try to find a dataset at or above the installation target
            dspath = GitRepo.get_toppath(abspath(path))
            if dspath is None:
                # no top-level dataset found, use path as such
                dspath = path
            ds = Dataset(dspath)
        assert(ds is not None)

        lgr.debug("Resolved target dataset for uninstallation: {0}".format(ds))

        if not ds.is_installed():
            if not path or path == ds.path:
                # we want to uninstall the dataset itself, which is not
                # installed => nothing to do
                # TODO: consider `data` option! is_installed currently only
                # checks for a repository
                lgr.info("Dataset {0} not installed. Nothing to "
                         "do.".format(ds.path))
                return
            else:
                # we want to uninstall something from a not installed dataset
                # Doesn't make sense, does it? => fail
                raise ValueError("Dataset {0} is not installed.".format(ds.path))

        assert(ds.repo is not None)

        if not path or path == ds.path:
            # uninstall the dataset `ds`
            # TODO: what to consider?
            #   - whether it is a submodule of another dataset
            #   - `data_only` ?
            #   - `recursive`
            #   - what to return in what case (data_only)?
            raise NotImplementedError("TODO: Uninstall dataset %s" % ds.path)

        # needed by the logic below
        assert(isabs(path))

        # express the destination path relative to the root of this dataset
        relativepath = relpath(path, start=ds.path)
        if path.startswith(pardir):
            raise ValueError("uninstallation path outside dataset")

        lgr.debug(
            "Resolved uninstallation target relative to dataset {0}: {1}".format(
                ds, relativepath))

        # figure out, what path actually is pointing to:
        if not exists(path):
            # nothing there, nothing to uninstall
            lgr.info("Nothing found to uninstall at %s" % path)
            return

        if relativepath in ds.get_dataset_handles(recursive=True):
            # it's a submodule
            # --recursive required or implied?
            raise NotImplementedError("TODO: uninstall submodule %s from "
                                      "dataset %s" % (relativepath, ds.path))

        if isdir(path):
            # don't know what to do yet
            # in git vs. untracked?
            # recursive?
            raise NotImplementedError("TODO: uninstall directory %s from "
                                      "dataset %s" % (path, ds.path))

        # we know, it's an existing file
        if isinstance(ds.repo, AnnexRepo):
            try:
                ds.repo.get_file_key(relativepath)
            except FileInGitError:
                # file directly in git
                _file_in_git = True

            except FileNotInAnnexError:
                # either an untracked file in this dataset, or something that
                # also actually exists in the file system but could be part of
                # a subdataset
                _untracked_or_within_submodule = True

            # it's an annexed file
            if data_only:
                ds.repo.annex_drop([path])
                return path
            else:
                raise NotImplementedError("TODO: fully uninstall file %s "
                                          "(annex) from dataset %s" %
                                          (path, ds.path))
        else:
            # plain git repo
            if relativepath in ds.repo.get_indexed_files():
                # file directly in git
                _file_in_git = True
            else:
                # either an untracked file in this dataset, or something that
                # also actually exists in the file system but could be part of
                # a subdataset
                _untracked_or_within_submodule = True


        if _file_in_git:
            if data_only:
                raise ValueError("%s is not a file handle. Removing its "
                                 "data only doesn't make sense." % path)
            else:
                return ds.repo.git_remove([relativepath])

        elif _untracked_or_within_submodule:
            subds = get_containing_subdataset(ds, relativepath)
            if ds.path != subds.path:
                # target path belongs to a subdataset, hand uninstallation
                # over to it
                return subds.uninstall(
                    path=relpath(path, start=subds.path),
                    data_only=data_only,
                    recursive=recursive)

            # this must be an untracked/existing something
            # it wasn't installed, so we cannot uninstall it
            raise ValueError("Cannot uninstall %s" % path)


