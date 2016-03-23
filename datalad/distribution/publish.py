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
from os.path import join as opj, abspath, expanduser, expandvars, exists, commonprefix

from six import string_types
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureListOf, \
    EnsureDatasetAbsolutePath
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules_dict, get_submodules_list
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
            to be accessible to anyone, who is supposed to have acces to the
            published dataset later on.\n
            If you want to publish with `recursive`, it is expected, that you
            pass a template for building the URLs of all (sub)datasets to be
            published by using placeholders.\n
            List of currently available placeholders:\n
            %%NAME\tthe name of the dataset, where slashes are replaced by
            dashes. This option is ignore if there is already a configured
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
            action="store_true",
            constraintsszpfgjwpjg=EnsureListOf(string_types) | EnsureNone()),)

    @staticmethod
    @datasetmethod(name='publish')
    def __call__(dataset=None, dest=None, path=None, dest_url=None,
            dest_pushurl=None, with_data=None, recursive=None):

        raise FuckedUp
        # Note to myself: "Real" implementation should use getpwd()

        # TODO: check parameter dependencies first

        # TODO: Exception handling:
        top_repo = GitRepo(handle, create=False)

        handles_to_publish = [top_repo]

        if recursive:
            handles_to_publish += [GitRepo(opj(top_repo.path, subhandle),
                                           create=False)
                                   for subhandle in
                                   get_submodules_list(top_repo)]

        for handle_repo in handles_to_publish:

            handle_name = handle_repo.path[len(
                commonprefix([top_repo.path, handle_repo.path])):].strip("/")
            set_upstream = False

            if remote is not None and remote not in handle_repo.git_get_remotes():
                if not remote_url:
                    raise ValueError("No remote '%s' found. Provide REMOTE-URL"
                                     " to add it." % remote)
                lgr.info("Remote '%s' doesn't exist yet.")

                # Fill in URL-Template:
                remote_url = remote_url.replace("%%NAME",
                                                handle_name.replace("/", "-"))
                # Add remote
                handle_repo.git_remote_add(remote, remote_url)
                if remote_url_push:
                    # Fill in template:
                    remote_url_push = \
                        remote_url_push.replace("%%NAME",
                                                handle_name.replace("/", "-"))
                    # Modify push url:
                    handle_repo._git_custom_command('',
                                                    ["git", "remote",
                                                     "set-url",
                                                     "--push", remote,
                                                     remote_url_push])

                lgr.info("Added remote '%s':\n %s (pull)\n%s (push)." %
                         (remote, remote_url,
                          remote_url_push if remote_url_push else remote_url))

            else:
                # known remote: parameters remote-url-* currently invalid.
                # This may change to adapt the existing remote.
                if remote_url:
                    lgr.warning("Remote '%s' already exists for handle '%s'. "
                                "Ignoring remote-url %s." %
                                (remote, handle_name, remote_url))
                if remote_url_push:
                    lgr.warning("Remote '%s' already exists for handle '%s'. "
                                "Ignoring remote-url-push %s." %
                                (remote, handle_name, remote_url_push))

            # upstream branch needed for update (merge) and subsequent push,
            # in case there is no.
            try:
                # Note: tracking branch actually defined bei entry "merge"
                # PLUS entry "remote"
                std_out, std_err = \
                    handle_repo._git_custom_command('',
                                                    ["git", "config", "--get", "branch.{active_branch}.merge".format(active_branch=handle_repo.git_get_active_branch())])
            except CommandError as e:
                if e.code == 1 and e.stdout == "":
                    # no tracking branch:
                    set_upstream = True
                else:
                    raise

            # push local state:
            handle_repo.git_push(("%s %s %s" % ("--set-upstream" if set_upstream else '', remote, handle_repo.git_get_active_branch())) if remote else '', )

            # in case of an annex also push git-annex branch; if no remote
            # given, figure out remote of the tracking branch:
            if knows_annex(handle_repo.path):
                if remote is None:
                    # check for tracking branch's remote:
                    try:
                        std_out, std_err = \
                            handle_repo._git_custom_command('',
                                                            ["git", "config", "--get", "branch.{active_branch}.remote".format(active_branch=handle_repo.git_get_active_branch())])
                    except CommandError as e:
                        if e.code == 1 and e.stdout == "":
                            std_out = None
                        else:
                            raise
                    if std_out:
                        remote = std_out.strip()
                    else:
                        raise RuntimeError("Couldn't determine what remote to push git-annex branch to")

                handle_repo.git_push("%s +git-annex:git-annex" % remote)

            if with_data:
                handle_repo._git_custom_command('',
                                                ["git", "annex", "copy"] +
                                                with_data + ["--to", remote])
