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
import glob

from os.path import join as opj, abspath, exists, isabs, relpath, pardir, isdir
from os.path import islink
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileInGitError, \
    FileNotInAnnexError
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod, resolve_path, require_dataset
from datalad.distribution.install import get_git_dir
from datalad.interface.base import Interface
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.utils import handle_dirty_dataset
from datalad.utils import assure_dir

lgr = logging.getLogger('datalad.distribution.uninstall')


def _move_gitdir(ds, relativepath):
    """Move .git directory of submodule `relativepath` into .git/modules of `ds`

    After moving, this will create a .git file in the submodule instead.

    Parameters
    ds: Dataset
    relativepath: str

    """

    # relativepath is expected to point to a submodule of ds:
    assert(relativepath in ds.get_subdatasets())

    path = opj(ds.path, relativepath)
    src_dotgit = get_git_dir(path)

    # expect the actual git dir to be within submodule:
    assert(src_dotgit == '.git')

    # get actual path to the .git to be moved:
    src_git_dir = opj(path, src_dotgit)

    # move .git to superrepo's .git/modules, remove .git, create
    # .git-file/symlink

    ds_git_dir = get_git_dir(ds.path)
    moved_git_dir = opj(ds.path, ds_git_dir, "modules", relativepath)
    assure_dir(moved_git_dir)
    from os import rename, listdir, rmdir
    for dot_git_entry in listdir(src_git_dir):
        rename(opj(src_git_dir, dot_git_entry),
               opj(moved_git_dir, dot_git_entry))
    assert not listdir(src_git_dir)
    rmdir(src_git_dir)

    # write .git file
    # Note: Annex would need a symlink instead to not break sub-submodules. But
    #       as of version 2.7.0 git itself doesn't deal correctly with
    #       .git-symlinks when deinitializing a submodule. Instead, it will
    #       still complain about a .git dir present in the submodule.
    #       Since by now this is about deinitializing only, we go for the .git
    #       file and don't care for possible sub-annexes.
    target_path = relpath(moved_git_dir, start=path)
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
            action="store_true",),
        if_dirty=if_dirty_opt,
    )

    @staticmethod
    @datasetmethod(name='uninstall')
    def __call__(path=None, dataset=None, data_only=False, recursive=False,
                 fast=False, if_dirty='save-before'):

        # upfront check prior any resolution attempt to avoid disaster
        if dataset is None and not path:
            raise InsufficientArgumentsError(
                "insufficient information for uninstallation (needs at "
                "least a dataset or a path. To uninstall an entire dataset, "
                "it needs to be given explicitly.")

        results = []

        # deal with multiple paths
        # TODO batch properly
        if isinstance(path, list):
            if not len(path):
                # simplify logic further down
                path = None
            else:
                for p in path:
                    r = Uninstall.__call__(
                            dataset=dataset,
                            path=p,
                            data_only=data_only,
                            recursive=recursive,
                            fast=fast,
                            if_dirty=if_dirty)
                    if r:
                        if isinstance(r, list):
                            results.extend(r)
                        else:
                            results.append(r)
                return results

        # resolve the target location against the provided dataset
        if path is not None:
            # XXX Important to resolve against `dataset` input argument, and
            # not against the `ds` resolved dataset
            path = resolve_path(path, dataset)
            lgr.debug("Resolved uninstallation target: {0}".format(path))

        ds = require_dataset(
            dataset, check_installed=True, purpose='uninstall')

        # make sure we get to an expected state
        handle_dirty_dataset(ds, if_dirty)

        assert(ds.repo is not None)

        if not path or path == ds.path:
            # uninstall the dataset `ds`
            # we install things INTO a dataset and therefore we can uninstall
            # FROM a dataset only
            # => need to find a dataset  to uninstall this one from:
            dspath = GitRepo.get_toppath(abspath(opj(ds.path, pardir)))
            if dspath is None:
                # ds is not part of another dataset
                # TODO: Do we want to just rm -rf instead of raising?
                #       Or do it with --force or sth?
                raise ValueError("No dataset found to uninstall %s from." %
                                 ds.path)
            return Uninstall.__call__(dataset=Dataset(dspath),
                                      path=relpath(ds.path, start=dspath),
                                      data_only=data_only,
                                      recursive=recursive,
                                      fast=fast)

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

            if data_only or not fast:
                # uninstall data of subds
                if isinstance(subds.repo, AnnexRepo):
                    results.extend(subds.repo.drop(glob.glob1(subds.path, '*')))
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
                    lgr.debug("Uninstalling subdataset %s ..." % r_sub)
                    try:
                        res = Uninstall.__call__(
                                dataset=subds,
                                path=r_sub,
                                data_only=data_only,
                                recursive=True,
                                fast=fast)
                    except ValueError as e:
                        if "is not installed" in str(e):
                            # ignore not installed subdatasets in recursion
                            lgr.debug("Subdataset %s not installed. Skipped." %
                                      r_sub)
                            continue
                        else:
                            raise
                    if res:
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
                # .git dir. Since this is what we expect, we need to move
                # it to git's default place within the superproject's
                # .git/modules dir, in order to cleanly deinit and be able to
                # reinit again later on.
                lgr.debug("Move .git directory of %s into .git/modules of %s." %
                          (relativepath, ds))
                _move_gitdir(ds, relativepath)

                lgr.debug("Deinit submodule %s in %s" % (relativepath, ds))
                # TODO: Move to GitRepo and provide proper return value
                ds.repo._git_custom_command(relativepath,
                                            ['git', 'submodule', 'deinit'])
                results.append(subds)

            return results

        if isdir(path):
            if data_only:
                if isinstance(ds.repo, AnnexRepo):
                    return ds.repo.drop(relativepath)
                else:
                    raise ValueError("%s is not in annex. Removing its "
                                 "data only doesn't make sense." % path)
            else:
                # git rm -r
                return ds.repo.remove(relativepath, r=True)

        # we know, it's an existing file
        if isinstance(ds.repo, AnnexRepo):
            try:
                if ds.repo.get_file_key(relativepath):
                    # it's an annexed file
                    if data_only:
                        # drop content
                        return ds.repo.drop([relativepath])
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
                ds.repo.remove([relativepath])
                return [relativepath]

        elif _untracked_or_within_submodule:
            subds = ds.get_containing_subdataset(relativepath)
            if ds.path != subds.path:
                # target path belongs to a subdataset, hand uninstallation
                # over to it
                return subds.uninstall(
                    path=relpath(path, start=subds.path),
                    data_only=data_only,
                    recursive=recursive,
                    fast=fast)

            # this must be an untracked/existing something
            # it wasn't installed, so we cannot uninstall it
            raise ValueError("Cannot uninstall %s" % path)

    @staticmethod
    def result_renderer_cmdline(res, args):
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
