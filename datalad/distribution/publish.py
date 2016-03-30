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
from os.path import join as opj, abspath, expanduser, expandvars, exists, commonprefix, relpath

from six import string_types
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureListOf, \
    EnsureDatasetAbsolutePath
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileInGitError, FileNotInAnnexError
from datalad.cmdline.helpers import POC_get_root_handle
from datalad.interface.base import Interface
from datalad.interface.POC_helpers import get_submodules_dict, get_submodules_list
from datalad.distribution.dataset import EnsureDataset, Dataset, datasetmethod, resolve_path
from datalad.distribution.install import get_containing_subdataset
from datalad.cmd import CommandError
from datalad.utils import knows_annex

lgr = logging.getLogger('datalad.distribution.publish')


class Publish(Interface):
    """publish a handle.

    This is basic implementation for testing purposes
    """

    _params_ = dict(
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""specify the dataset to perform the publish operation on. If
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
        dest_url=Parameter(
            args=('--dest-url',),
            doc="""The URL of the dataset sibling named by `dest`. This URL has
            to be accessible to anyone, who is supposed to have access to the
            published dataset later on.\n
            If you want to publish with `recursive`, it is expected, that you
            pass a template for building the URLs of all (sub)datasets to be
            published by using placeholders.\n
            List of currently available placeholders:\n
            %%NAME\tthe name of the dataset, where slashes are replaced by
            dashes.\nThis option is ignored if there is already a configured
            sibling dataset under the name given by `dest`.""",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        dest_pushurl=Parameter(
            args=('--dest-pushurl',),
            doc="""In case the `dest_url` cannot be used to publish to the
            dataset sibling, this option specifies a URL to be used for the
            actual publication operation.""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="Recursively publish all components of the dataset."),
        with_data=Parameter(
            args=("--with-data",),
            doc="shell pattern",
            constraints=EnsureListOf(string_types) | EnsureNone()),)

    @staticmethod
    @datasetmethod(name='publish')
    def __call__(dataset=None, dest=None, path=None, dest_url=None,
                 dest_pushurl=None, with_data=None, recursive=False):
        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)
        if path is None:
            if ds is None:
                # no dataset, no component to publish, nothing to do
                raise ValueError(
                    "insufficient information for publication (needs at "
                    "least a dataset or a path")
        elif isinstance(path, list):
            return [Publish.__call__(
                    dataset=ds,
                    dest=dest,
                    path=p,
                    dest_url=dest_url,
                    dest_pushurl=dest_pushurl,
                    with_data=with_data,
                    recursive=recursive) for p in path]

        # resolve the location against the provided dataset
        if path is not None:
            path = resolve_path(path, ds)

        lgr.debug("Resolved component to be published: {0}".format(path))

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
        assert(ds is not None)
        lgr.debug("Resolved dataset for publication: {0}".format(ds))

        # TODO: we cannot publish anything from a not installed dataset, can we?
        # But may be just the existence of ds.repo is important here.
        if not ds.is_installed():
            raise ValueError("No installed dataset found at {0}.".format(ds.path))
        assert(ds.repo is not None)

        # TODO: For now we can deal with a sibling(remote) name given by `dest`
        # only. Figure out, when to allow for passing a local path or URL
        # directly and what to do in that case.

        # TODO: The following is misplaced here. Remote is relevant only, if we
        # need to actually operate on this dataset. And it needs to be checked
        # for all datasets invloved (recursive).
        # is destination a known remote?
        # TODO: in case of dest is None, check for tracking branch right here?
        if dest is not None and dest not in ds.repo.git_get_remotes():
            # unknown remote
            if dest_url is None:
                raise ValueError("Cannot register %s without an URL." % dest)

            lgr.info("%s unknown. Registering ...")
            # TODO: create it
            pass

        # Figure out, what to publish
        if path is None or path == ds.path:
            # TODO: publish the dataset itself
            pass
            # return ds
        elif exists(path):
            relativepath = relpath(path, start=ds.path)
            subds = get_containing_subdataset(ds, relativepath)
            if subds.path != ds.path:
                # path belongs to a subdataset; hand it over
                lgr.debug("Hand over to submodule %s" % subds.path)
                return subds.publish(dest=dest,
                                     path=relpath(path, start=subds.path),
                                     dest_url=dest_url,
                                     dest_pushurl=dest_pushurl,
                                     with_data=with_data,
                                     recursive=recursive)

            # At this point `path` is not referencing a (sub)dataset.
            # An annexed file is the only thing left, that `path` might be
            # validly pointing to. Anything else we can't handle currently.
            if isinstance(ds.repo, AnnexRepo):
                try:
                    if ds.repo.get_file_key(relativepath):
                        # file in annex
                        # TODO: annex copy to
                        # return path
                        pass
                except FileInGitError, FileNotInAnnexError:
                    pass
            # `path` can't be published
            lgr.warning("Don't know how to publish %s." % path)
            return None

        else:
            # nothing to publish found
            lgr.warning("Nothing to publish found at %s." % path)
            return None


        # TODO: Remainings from old one; to be moved upwards:
        #
        # handles_to_publish = [top_repo]
        #
        # if recursive:
        #     handles_to_publish += [GitRepo(opj(top_repo.path, subhandle),
        #                                    create=False)
        #                            for subhandle in
        #                            get_submodules_list(top_repo)]
        #
        # for handle_repo in handles_to_publish:
        #
        #     handle_name = handle_repo.path[len(
        #         commonprefix([top_repo.path, handle_repo.path])):].strip("/")
        #     set_upstream = False
        #
        #     if remote is not None and remote not in handle_repo.git_get_remotes():
        #         if not remote_url:
        #             raise ValueError("No remote '%s' found. Provide REMOTE-URL"
        #                              " to add it." % remote)
        #         lgr.info("Remote '%s' doesn't exist yet.")
        #
        #         # Fill in URL-Template:
        #         remote_url = remote_url.replace("%%NAME",
        #                                         handle_name.replace("/", "-"))
        #         # Add remote
        #         handle_repo.git_remote_add(remote, remote_url)
        #         if remote_url_push:
        #             # Fill in template:
        #             remote_url_push = \
        #                 remote_url_push.replace("%%NAME",
        #                                         handle_name.replace("/", "-"))
        #             # Modify push url:
        #             handle_repo._git_custom_command('',
        #                                             ["git", "remote",
        #                                              "set-url",
        #                                              "--push", remote,
        #                                              remote_url_push])
        #
        #         lgr.info("Added remote '%s':\n %s (pull)\n%s (push)." %
        #                  (remote, remote_url,
        #                   remote_url_push if remote_url_push else remote_url))
        #
        #     else:
        #         # known remote: parameters remote-url-* currently invalid.
        #         # This may change to adapt the existing remote.
        #         if remote_url:
        #             lgr.warning("Remote '%s' already exists for handle '%s'. "
        #                         "Ignoring remote-url %s." %
        #                         (remote, handle_name, remote_url))
        #         if remote_url_push:
        #             lgr.warning("Remote '%s' already exists for handle '%s'. "
        #                         "Ignoring remote-url-push %s." %
        #                         (remote, handle_name, remote_url_push))
        #
        #     # upstream branch needed for update (merge) and subsequent push,
        #     # in case there is no.
        #     try:
        #         # Note: tracking branch actually defined bei entry "merge"
        #         # PLUS entry "remote"
        #         std_out, std_err = \
        #             handle_repo._git_custom_command('',
        #                                             ["git", "config", "--get", "branch.{active_branch}.merge".format(active_branch=handle_repo.git_get_active_branch())])
        #     except CommandError as e:
        #         if e.code == 1 and e.stdout == "":
        #             # no tracking branch:
        #             set_upstream = True
        #         else:
        #             raise
        #
        #     # push local state:
        #     handle_repo.git_push(("%s %s %s" % ("--set-upstream" if set_upstream else '', remote, handle_repo.git_get_active_branch())) if remote else '', )
        #
        #     # in case of an annex also push git-annex branch; if no remote
        #     # given, figure out remote of the tracking branch:
        #     if knows_annex(handle_repo.path):
        #         if remote is None:
        #             # check for tracking branch's remote:
        #             try:
        #                 std_out, std_err = \
        #                     handle_repo._git_custom_command('',
        #                                                     ["git", "config", "--get", "branch.{active_branch}.remote".format(active_branch=handle_repo.git_get_active_branch())])
        #             except CommandError as e:
        #                 if e.code == 1 and e.stdout == "":
        #                     std_out = None
        #                 else:
        #                     raise
        #             if std_out:
        #                 remote = std_out.strip()
        #             else:
        #                 raise RuntimeError("Couldn't determine what remote to push git-annex branch to")
        #
        #         handle_repo.git_push("%s +git-annex:git-annex" % remote)
        #
        #     if with_data:
        #         handle_repo._git_custom_command('',
        #                                         ["git", "annex", "copy"] +
        #                                         with_data + ["--to", remote])
