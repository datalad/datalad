# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for uninstalling dataset content

"""

__docformat__ = 'restructuredtext'

import logging
from os.path import join as opj, abspath, exists, isabs, relpath, pardir, isdir
from os.path import islink
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileInGitError, \
    FileNotInAnnexError
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureBool
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod, resolve_path
from datalad.distribution.install import get_containing_subdataset, get_git_dir
from datalad.interface.base import Interface
from datalad.utils import assure_dir, on_windows

lgr = logging.getLogger('datalad.distribution.uninstall')


def _move_gitdir(ds, relativepath):

    # relativepath is expected to point to a submodule of ds:
    assert(relativepath in ds.get_subdatasets())
    path = opj(ds.path, relativepath)
    src_dotgit = get_git_dir(path)

    # expect the actual git dir to be within submodule:
    assert(src_dotgit == '.git')

    # move .git to superrepo's .git/modules, remove .git, create
    # .git-file/symlink

    ds_git_dir = get_git_dir(ds.path)
    moved_git_dir = opj(ds.path, ds_git_dir, "modules", relativepath)
    assure_dir(moved_git_dir)
    from os import rename, listdir, rmdir, symlink
    for dot_git_entry in listdir(src_dotgit):
        rename(opj(src_dotgit, dot_git_entry),
               opj(moved_git_dir, dot_git_entry))
    assert not listdir(src_dotgit)
    rmdir(src_dotgit)

    # TODO: symlink or whatever annex does, since annexes beneath
    #       might break
    #       - figure out, what annex does in direct mode
    #         and/or on windows
    #       - for now use .git file on windows and symlink otherwise
    target_path = relpath(moved_git_dir, start=path)
    if not on_windows:
        symlink(target_path, opj(path, ".git"))
    else:
        with open(opj(path, ".git"), "w") as f:
            f.write("gitdir: {moved}\n".format(moved=target_path))


class Uninstall(Interface):
    """Uninstall a dataset component or entire dataset(s)
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="DATASET",
            doc="""specify the dataset to perform the uninstall operation on.
            If no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path/name of the component to be uninstalled",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        data_only=Parameter(
            args=("--data-only",),
            doc="if set, only data is uninstalled, but the handles are kept",
            action="store_true"),
        recursive=Parameter(
            args=("-r", "--recursive"),
            doc="""if set, uninstall recursively, including all subdatasets.
            The value of `data` is used for recursive uninstallation, too""",
            action="store_true"),
        fast=Parameter(
            args=("--fast",),
            doc="when uninstalling (sub-)datasets, don't try uninstalling its "
                "data first. Warning: This will silently ignore any issue "
                "regarding the uninstallation of contained data.",
            action="store_true",))

    @staticmethod
    @datasetmethod(name='uninstall')
    def __call__(dataset=None, path=None, data_only=False, recursive=False,
                 fast=False):

        # Note: copy logic from install to resolve dataset and path:
        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)

        if not path:
            if ds is None:
                # no dataset, no target location, nothing to do
                raise InsufficientArgumentsError(
                    "insufficient information for uninstallation (needs at "
                    "least a dataset or a path")
        elif isinstance(path, list):
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
        if not exists(path) and not islink(path):
            # nothing there, nothing to uninstall
            lgr.info("Nothing found to uninstall at %s" % path)
            return

        if relativepath in ds.get_subdatasets(recursive=True):
            # we want to uninstall a subdataset
            subds = Dataset(opj(ds.path, relativepath))
            if not subds.is_installed():
                raise ValueError("%s is not installed. Can't uninstall." %
                                 subds.path)

            results = []
            if data_only or not fast:
                # uninstall data of subds
                if isinstance(subds.repo, AnnexRepo):
                    # todo: correct return values
                    ds.repo.drop(relativepath)
                    results.append(relativepath)
                    if data_only and not recursive:
                        # all done
                        return results
                else:
                    # can't do anything
                    if recursive:
                        lgr.warning("Can't uninstall data of %s. No annex." %
                                    subds.path)
                    elif data_only:
                        raise ValueError("Can't uninstall data of %s. "
                                         "No annex." % subds.path)
                    else:
                        # we want to uninstall the subds and have a meaningless
                        # 'not fast' => just ignore
                        pass

            if recursive:
                for r_sub in subds.get_subdatasets():
                    try:
                        res = Uninstall.__call__(
                                dataset=subds,
                                path=r_sub,
                                data_only=data_only,
                                recursive=True)
                    except ValueError as e:
                        if "is not installed" in str(e):
                            # ignore not installed subdatasets in recursion
                            continue
                        else:
                            raise
                    if isinstance(res, list):
                        results.extend(res)
                    else:
                        results.append(res)

                if not data_only:
                    # uninstall subds itself
                    # currently this is interpreted as deinitializing the
                    # submodule
                    # TODO: figure out when to completely remove it
                    #       (another command, an additional option?)

                    # Note: submodule deinit will fail, if the submodule has a
                    # .git dir. Since this is, what we expect, we need to move
                    # it to git's default place within the superproject's .git
                    # dir, in order to cleanly deinit and be able to reinit
                    # again later on.
                    _move_gitdir(ds, relativepath)

                    # TODO: Move to GitRepo and provide proper return value
                    ds.repo._git_custom_command(relativepath,
                                                ['git', 'submodule', 'deinit'])
                    results.append(subds)

            return results

        if isdir(path):
            if data_only:
                if isinstance(ds.repo, AnnexRepo):
                    # TODO: Return value for ANnexRepo.drop()!
                    return ds.repo.drop(relativepath)
                else:
                    raise ValueError("%s is not in annex. Removing its "
                                 "data only doesn't make sense." % path)
            else:
                # git rm -r
                # TODO: Move to GitRepo and integrate with remove()
                std_out, std_err = ds.repo._git_custom_command(
                    relativepath, ['git', 'rm', '-r'])
                return [line.split()[1][1:-1] for line in std_out.splitlines()
                        if line.startswith('rm')]

        # we know, it's an existing file
        if isinstance(ds.repo, AnnexRepo):
            try:
                if ds.repo.get_file_key(relativepath):
                    # it's an annexed file
                    if data_only:
                        # drop content
                        ds.repo.drop([relativepath])
                        return path
                    else:
                        # remove from repo
                        ds.repo.remove(relativepath)
                        return path

            except FileInGitError:
                # file directly in git
                _file_in_git = True

            except FileNotInAnnexError:
                # either an untracked file in this dataset, or something that
                # also actually exists in the file system but could be part of
                # a subdataset
                _untracked_or_within_submodule = True

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
                return ds.repo.remove([relativepath])

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

    @staticmethod
    def result_renderer_cmdline(res):
        from datalad.ui import ui
        if not res:
            ui.message("Nothing was uninstalled")
            return
        msg = "{n} {obj} uninstalled:\n".format(
            obj='items were' if len(res) > 1 else 'item was',
            n=len(res))
        for item in res:
            if isinstance(item, Dataset):
                msg += "Dataset: %s\n" % item.path
            else:
                msg += "File: %s\n" % item
        ui.message(msg)
