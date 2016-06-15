# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset (component) publishing

"""

__docformat__ = 'restructuredtext'


import logging

from os import curdir
from os.path import join as opj, abspath, exists, relpath

from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileInGitError, \
    FileNotInAnnexError
from datalad.interface.base import Interface
from datalad.distribution.dataset import EnsureDataset, Dataset, \
    datasetmethod, resolve_path
from datalad.distribution.install import get_containing_subdataset
from datalad.cmd import CommandError

lgr = logging.getLogger('datalad.distribution.publish')


class Publish(Interface):
    """Publish (e.g. to a web server) a dataset(s)

    This is basic implementation for testing purposes
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the publish operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        dest=Parameter(
            args=("dest",),
            doc="""url, local path, or sibling name identifying the publication
            target""",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        path=Parameter(
            args=("path",),
            doc="path/name of the dataset component to publish",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("-r", "--recursive"),
            action="store_true",
            doc="recursively publish all components of the dataset"),
        with_data=Parameter(
            args=("--with-data",),
            doc="shell pattern",
            constraints=EnsureStr() | EnsureNone(),
            nargs='*'),)

    @staticmethod
    @datasetmethod(name='publish')
    def __call__(dataset=None, dest=None, path=None,
                 with_data=None, recursive=False):

        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)
        if not path:
            path = curdir

        elif isinstance(path, list):
            return [Publish.__call__(
                    dataset=ds,
                    dest=dest,
                    path=p,
                    with_data=with_data,
                    recursive=recursive) for p in path]

        # resolve the location against the provided dataset
        if path is not None:
            path = resolve_path(path, ds)

        lgr.info("Publishing {0}".format(path))

        # if we have no dataset given, figure out which one we need to operate
        # on, based on the resolved location (that is now guaranteed to
        # be specified
        if ds is None:
            # try to find a dataset at or above the location
            dspath = GitRepo.get_toppath(abspath(path))
            if dspath is None:
                # no top-level dataset found, use path as such
                dspath = path
            ds = Dataset(dspath)
        lgr.debug("Resolved dataset for publication: {0}".format(ds))
        assert(ds is not None)

        # it might still be about a subdataset of ds:
        if path is not None:
            relativepath = relpath(path, start=ds.path)
            subds = get_containing_subdataset(ds, relativepath)
            if subds.path != ds.path:
                    # path belongs to a subdataset; hand it over
                    lgr.debug("Hand over to submodule %s" % subds.path)
                    return subds.publish(dest=dest,
                                         path=relpath(path, start=subds.path),
                                         with_data=with_data,
                                         recursive=recursive)

        # now, we know, we have to operate on ds. So, ds needs to be installed,
        # since we cannot publish anything from a not installed dataset,
        # can we?
        # (But may be just the existence of ds.repo is important here.)
        if not ds.is_installed():
            raise ValueError("No installed dataset found at "
                             "{0}.".format(ds.path))
        assert(ds.repo is not None)

        # TODO: For now we can deal with a sibling(remote) name given by `dest`
        # only. Figure out, when to allow for passing a local path or URL
        # directly and what to do in that case.

        # Note: we need an upstream remote, if there's none given. We could
        # wait for git push to complain, but we need to explicitly figure it
        # out for pushing annex branch anyway and we might as well fail right
        # here.

        # keep original dest in case it's None for passing to recursive calls:
        dest_resolved = dest
        if dest is None:
            # check for tracking branch's remote:
            try:
                std_out, std_err = \
                    ds.repo._git_custom_command('',
                                                ["git", "config", "--get", "branch.{active_branch}.remote".format(active_branch=ds.repo.get_active_branch())],
                                                expect_fail=True)
            except CommandError as e:
                if e.code == 1 and e.stdout == "":
                    std_out = None
                else:
                    raise
            if std_out:
                dest_resolved = std_out.strip()
            else:
                # we have no remote given and no upstream => fail
                raise RuntimeError("No known default target for "
                                   "publication and none given.")

        # upstream branch needed for update (merge) and subsequent push,
        # in case there is no.
        set_upstream = False
        try:
            # Note: tracking branch actually defined bei entry "merge"
            # PLUS entry "remote"
            std_out, std_err = \
                ds.repo._git_custom_command('',
                                            ["git", "config", "--get",
                                             "branch.{active_branch}.merge".format(active_branch=ds.repo.get_active_branch())],
                                            expect_fail=True)
        except CommandError as e:
            if e.code == 1 and e.stdout == "":
                # no tracking branch yet:
                set_upstream = True
            else:
                raise

        # is `dest` an already known remote?
        if dest_resolved not in ds.repo.get_remotes():
            # unknown remote
            raise ValueError("No sibling '%s' found." % dest_resolved)

        # Figure out, what to publish
        if path is None or path == ds.path:
            # => publish the dataset itself
            # push local state:
            ds.repo.push(remote=dest_resolved,
                         refspec=ds.repo.get_active_branch(),
                         set_upstream=set_upstream)
            # push annex branch:
            if isinstance(ds.repo, AnnexRepo):
                ds.repo.push(remote=dest_resolved,
                             refspec="+git-annex:git-annex")

            # TODO: if with_data is a shell pattern, we get a list, when called
            # from shell, right?
            # => adapt the following and check constraints to allow for that
            if with_data:
                ds.repo._git_custom_command('', ["git", "annex", "copy"] +
                                            with_data + ["--to", dest_resolved])

            if recursive and ds.get_dataset_handles() != []:
                results = [ds]
                for subds in ds.get_dataset_handles():
                    results.append(
                        Dataset(
                            opj(ds.path, subds)).publish(
                                dest=dest,
                                # Note: use `dest` instead of `dest_resolved`
                                # in case dest was None, so subdatasets would
                                # use their default as well
                                with_data=with_data,
                                recursive=recursive))
                return results

            return ds

        elif exists(path):
            # At this point `path` is not referencing a (sub)dataset.
            # An annexed file is the only thing left, that `path` might be
            # validly pointing to. Anything else we can't handle currently.
            if isinstance(ds.repo, AnnexRepo):
                try:
                    if ds.repo.get_file_key(relativepath):
                        # file is in annex, publish it
                        ds.repo._run_annex_command('copy',
                                                   annex_options=[path,
                                                                  '--to=%s' % dest_resolved])
                        return path
                except (FileInGitError, FileNotInAnnexError):
                    pass
            # `path` can't be published
            lgr.warning("Don't know how to publish %s." % path)
            return None

        else:
            # nothing to publish found
            lgr.warning("Nothing to publish found at %s." % path)
            return None
