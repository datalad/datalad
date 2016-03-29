# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset (component) installation

"""

__docformat__ = 'restructuredtext'


import logging

import os
from os.path import join as opj, abspath, relpath, pardir, isabs, isdir, \
    exists, islink, sep
from datalad.distribution.dataset import Dataset, datasetmethod, \
    resolve_path, EnsureDataset
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureChoice, \
    EnsureBool
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileInGitError, \
    FileNotInAnnexError
from datalad.interface.base import Interface
from datalad.cmd import CommandError
from datalad.cmd import Runner
from datalad.utils import expandpath, knows_annex, assure_dir, is_explicit_path
from datalad.interface.POC_helpers import get_git_dir


lgr = logging.getLogger('datalad.distribution.install')

def _with_sep(path):
    """Little helper to guarantee that path ends with /"""
    return path + sep if not path.endswith(sep) else path

def get_containing_subdataset(ds, path):
    """Given a base dataset and a relative path get containing subdataset

    Parameters
    ----------
    ds : Dataset
      Reference or base dataset
    path : str
      Path relative to the reference dataset

    Returns
    -------
    Dataset
    """

    if is_explicit_path(path) and not path.startswith(ds.path):
        raise ValueError("path {0} not in dataset.".format(path))

    for subds in ds.get_dataset_handles():
        common = os.path.commonprefix((_with_sep(subds), _with_sep(path)))
        if common.endswith(sep) and isdir(opj(ds.path, common)):
            return Dataset(path=opj(ds.path, common))
    return ds


class Install(Interface):
    """Install a dataset component or entire datasets.

    This command can make arbitrary content available in a dataset. This
    includes the fulfillment of exisiting dataset handles or file handles
    in a dataset, as well as the adding such handles for content available
    locally or remotely.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""specify the dataset to perform the install operation on. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            doc="path/name of the installation target",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        source=Parameter(
            args=("-s", "--source",),
            doc="url or local path of the installation source",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        # TODO this probably needs --with-data and --recursive as a plain boolean
        recursive=Parameter(
            args=("--recursive", "-r"),
            constraints=EnsureChoice('handles', 'data') | EnsureBool(),
            doc="""If set, all content is installed recursively, including
            content of any subdatasets."""))

    @staticmethod
    @datasetmethod(name='install')
    def __call__(dataset=None, path=None, source=None, recursive=False):
        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)

        if path is None:
            if ds is None:
                # no dataset, no target location, nothing to do
                raise ValueError(
                    "insufficient information for installation (needs at "
                    "least a dataset or an installation path")
        elif isinstance(path, list):
            return [Install.__call__(
                    dataset=ds,
                    path=p,
                    source=source,
                    recursive=recursive) for p in path]

        # resolve the target location against the provided dataset
        if path is not None:
            path = resolve_path(path, ds)

        lgr.debug("Resolved installation target: {0}".format(path))

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

        lgr.debug("Resolved target dataset for installation: {0}".format(ds))

        vcs = ds.repo
        if vcs is None:
            # TODO check that a "ds.path" actually points to a TOPDIR
            # should be the case already, but maybe nevertheless check
            lgr.info("Creating a new annex repo at %s", ds.path)
            AnnexRepo(ds.path, url=source, create=True)
            vcs = ds.repo
        assert(ds.repo)

        if path is None or path == ds.path:
            # if the goal was to install this dataset, we are done
            return ds

        # at this point this dataset is "installed", now we can test whether to
        # install something into the dataset

        # needed by the logic below
        assert(isabs(path))

        # express the destination path relative to the root of this dataset
        relativepath = relpath(path, start=ds.path)
        if path.startswith(pardir):
            raise ValueError("installation path outside dataset")

        lgr.debug(
            "Resolved installation target relative to dataset {0}: {1}".format(
                ds, relativepath))

        runner = Runner()

        # this dataset must already know everything necessary
        try:
            # it is simplest to let annex tell us what we are dealing with
            lgr.debug("Trying to fetch file %s using annex", relativepath)
            if not isinstance(vcs, AnnexRepo):
                raise FileNotInAnnexError("We don't have yet annex repo here")
                # TODO: relativepath might be in git, then we should have thrown
                # FileInGitError.  Figure it all out! ;)
            if vcs.get_file_key(relativepath):
                # this is an annex'ed file
                # TODO implement `copy --from` using `source`
                # TODO fail if `source` is something strange
                vcs.annex_get(relativepath)
                # return the absolute path to the installed file
                return path
        except FileInGitError:
            # file is checked into git directly -> nothing to do
            # OR this is a submodule of this dataset
            if not isdir(path):
                # file in Git, just return its path
                return path

            # we are dealing with a known submodule (i.e. `source`
            # doesn't matter)
            # check it out
            cmd_list = ["git", "submodule", "update", "--init"]
            if recursive:
                cmd_list.append("--recursive")
            cmd_list.append(relativepath)
            runner.run(cmd_list, cwd=ds.path)

            # TODO: annex init recursively!
            if knows_annex(path):
                lgr.debug("Annex detected in submodule '%s'. "
                          "Calling annex init ..." % relativepath)
                cmd_list = ["git", "annex", "init"]
                runner.run(cmd_list, cwd=ds.path)
            # submodule install done, return Dataset instance pointing
            # to the submodule
            return Dataset(path=path)

        except FileNotInAnnexError:
            # either an untracked file in this dataset, or something that
            # also actually exists in the file system but could be part of
            # a subdataset
            subds = get_containing_subdataset(ds, relativepath)
            if ds.path != subds.path:
                # target path belongs to a subdataset, hand installation
                # over to it
                return subds.install(
                    path=relpath(path, start=subds.path),
                    source=source,
                    recursive=recursive)

            # this must be an untracked/existing something, so either
            # - a file
            # - a directory
            # - an entire repository
            if exists(opj(path, '.git')):
                # this is a repo and must be turned into a submodule
                # of this dataset
                cmd_list = ["git", "submodule", "add", source,
                            relativepath]
                runner.run(cmd_list, cwd=ds.path)
                # move .git to superrepo's .git/modules, remove .git, create
                # .git-file
                subds_git_dir = opj(path, ".git")
                ds_git_dir = get_git_dir(ds.path)
                moved_git_dir = opj(ds.path, ds_git_dir,
                                    "modules", relativepath)
                assure_dir(moved_git_dir)
                from os import rename, listdir, rmdir
                for dot_git_entry in listdir(subds_git_dir):
                    rename(opj(subds_git_dir, dot_git_entry),
                           opj(moved_git_dir, dot_git_entry))
                assert not listdir(subds_git_dir)
                rmdir(subds_git_dir)

                with open(opj(path, ".git"), "w") as f:
                    f.write("gitdir: {moved}\n".format(moved=moved_git_dir))
                # return newly added submodule as a dataset
                return Dataset(path)

            if isdir(path) and not recursive:
                # this is a directory and we want --recursive for it
                raise ValueError(
                    "installation of a directory requires the `recursive` flag")

            # do a blunt `annex add`
            if source and abspath(source) != path:
                raise ValueError(
                    "installation target already exists, but `source` point to "
                    "another location")
            added_files = vcs.annex_add(relativepath)
            # return just the paths of the installed components
            if isinstance(added_files, list):
                added_files = [resolve_path(i['file'], ds) for i in added_files]
            else:
                added_files = resolve_path(added_files['file'], ds)
            if added_files:
                return added_files
            else:
                return None

        except IOError:
            if exists(path) or islink(path):
                # this happens when we have an unfulfilled handle in a
                # subdataset -> hand it over to downstairs
                subds = get_containing_subdataset(ds, relativepath)
                if ds.path != subds.path:
                    # target path belongs to a subdataset, hand installation
                    # over to it
                    return subds.install(
                        path=relpath(path, start=subds.path),
                        source=source,
                        recursive=recursive)
                else:
                    raise RuntimeError("%s, %s, %s" % (path, ds, subds))

            elif source is None:
                # there is no source, and nothing at the destination, not even
                # a handle -> create a new dataset!
                subds = get_containing_subdataset(ds, relativepath)
                AnnexRepo(path, create=True)
                return subds.install(path=relpath(path, start=subds.path),
                                     source=path)
                # TODO: This is actually almost the same thing we do above,
                # isn't it?
                # Think again, too tired currently.

            if source and exists(expandpath(source)):
                source = expandpath(source)
                # this could be
                # - file -> annex add
                # - directory -> annex add with recursive
                # - repository -> submodule add
                if exists(opj(source, '.git')):
                    # add it as a submodule to its superhandle:
                    cmd_list = ["git", "submodule", "add", source,
                                relativepath]
                    runner.run(cmd_list, cwd=ds.path, expect_stderr=True)
                    return Dataset(path)

                raise ValueError(
                    "installing individual local files or directories is not "
                    "supported, copy/move them into the dataset first")
                #if isdir(source):
                #    if not recursive:
                #        # this is a directory and we want --recursive for it
                #        raise ValueError(
                #            "installation of a directory requires the `recursive` flag")
                #    # cp/ln this directory to its target location
                #    raise NotImplementedError
                #else:
                #    # single file as source, cp/ln to target location
                #    raise NotImplementedError

                #added_files = vcs.annex_add(relativepath)
                #if len(added_files):
                #    # XXX think about what to return
                #    return added_files
                #else:
                #    return None

            # `source` is non-local, it could be:
            #   - repository -> try submodule add
            #   - file -> try add url
            try:
                # add it as a submodule to its superhandle:
                # XXX copied from above -> make function
                cmd_list = ["git", "submodule", "add", source,
                            relativepath]
                runner.run(cmd_list, cwd=ds.path)
                return Dataset(path)
            except CommandError:
                # probably not a repo, likely a simple file
                vcs.annex_addurl_to_file(relativepath, source)
                return path

    @staticmethod
    def result_renderer_cmdline(res):
        from datalad.ui import ui
        if res is None:
            res = []
        if not isinstance(res, list):
            res = [res]
        if not len(res):
            ui.message("Nothing was installed")
            return
        items= '\n'.join(map(str, res))
        msg = "{n} installed {obj} available at\n{items}".format(
            obj='items are' if len(res) > 1 else 'item is',
            n=len(res),
            items=items)
        ui.message(msg)
