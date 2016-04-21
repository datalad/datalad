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

from six import string_types
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureListOf
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
        # Note: add remote currently disabled in publish
        # dest_url=Parameter(
        #     args=('--dest-url',),
        #     doc="""The URL of the dataset sibling named by `dest`. This URL has
        #     to be accessible to anyone, who is supposed to have access to the
        #     published dataset later on.\n
        #     If you want to publish with `recursive`, it is expected, that you
        #     pass a template for building the URLs of all (sub)datasets to be
        #     published by using placeholders.\n
        #     List of currently available placeholders:\n
        #     %%NAME\tthe name of the dataset, where slashes are replaced by
        #     dashes.\nThis option is ignored if there is already a configured
        #     sibling dataset under the name given by `dest`.""",
        #     nargs="?",
        #     constraints=EnsureStr() | EnsureNone()),
        # dest_pushurl=Parameter(
        #     args=('--dest-pushurl',),
        #     doc="""In case the `dest_url` cannot be used to publish to the
        #     dataset sibling, this option specifies a URL to be used for the
        #     actual publication operation.""",
        #     constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="Recursively publish all components of the dataset."),
        with_data=Parameter(
            args=("--with-data",),
            doc="shell pattern",
            constraints=EnsureListOf(string_types) | EnsureNone(),
            nargs='*'),)

    @staticmethod
    @datasetmethod(name='publish')
    def __call__(dataset=None, dest=None, path=None,
                 # Note: add remote currently disabled in publish
                 # dest_url=None, dest_pushurl=None,
                 with_data=None, recursive=False):

        # Note: add remote currently disabled in publish
        # if dest is None and (dest_url is not None
        #                        or dest_pushurl is not None):
        #     raise ValueError("""insufficient information for adding the
        #     destination as a sibling (needs at least a name)""")

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
                    # Note: add remote currently disabled in publish
                    # dest_url=dest_url,
                    # dest_pushurl=dest_pushurl,
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
                                         # Note: add remote currently disabled in publish
                                         # dest_url=dest_url,
                                         # dest_pushurl=dest_pushurl,
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
                                                ["git", "config", "--get", "branch.{active_branch}.remote".format(active_branch=ds.repo.git_get_active_branch())],
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
                                             "branch.{active_branch}.merge".format(active_branch=ds.repo.git_get_active_branch())],
                                            expect_fail=True)
        except CommandError as e:
            if e.code == 1 and e.stdout == "":
                # no tracking branch yet:
                set_upstream = True
            else:
                raise

        # is `dest` an already known remote?
        if dest_resolved not in ds.repo.git_get_remotes():
            # unknown remote
            raise ValueError("No sibling '%s' found." % dest_resolved)

            # Note: add remote currently disabled in publish
            # if dest_url is None:
            #     raise ValueError("No sibling '%s' found. Provide `dest-url`"
            #                      " to register it." % dest_resolved)
            # lgr.info("Sibling %s unknown. Registering ...")
            #
            # # Fill in URL-Template:
            # remote_url = dest_url.replace("%NAME", basename(ds.path))
            # # TODO: handle_name.replace("/", "-")) instead of basename()
            # #       - figure it out ;)
            # #       - either a datasets needs to discover superdatasets in
            # #         order to get it's relative path to provide a name
            # #       - or: We need a different approach on the templates
            #
            # # Add the remote
            # ds.repo.git_remote_add(dest_resolved, remote_url)
            # if dest_pushurl:
            #     # Fill in template:
            #     remote_url_push = \
            #         dest_pushurl.replace("%NAME", basename(ds.path))
            #     # TODO: Different way of replacing %NAME; See above
            #
            #     # Modify push url:
            #     ds.repo._git_custom_command('',
            #                                 ["git", "remote",
            #                                  "set-url",
            #                                  "--push", dest_resolved,
            #                                  remote_url_push])
            # lgr.info("Added sibling '%s'." % dest)
            # lgr.debug("Added remote '%s':\n %s (fetch)\n%s (push)." %
            #           (dest_resolved, remote_url,
            #            remote_url_push if dest_pushurl else remote_url))
        # Note: add remote currently disabled in publish
        # else:
        #     # known remote: parameters dest-url-* currently invalid.
        #     # This may change to adapt the existing remote.
        #     if dest_url:
        #         lgr.warning("Sibling '%s' already exists for dataset '%s'. "
        #                     "Ignoring dest-url %s." %
        #                     (dest_resolved, ds.path, dest_url))
        #     if dest_pushurl:
        #         lgr.warning("Sibling '%s' already exists for dataset '%s'. "
        #                     "Ignoring dest-pushurl %s." %
        #                     (dest_resolved, ds.path, dest_pushurl))

        # Figure out, what to publish
        if path is None or path == ds.path:
            # => publish the dataset itself
            # push local state:
            # TODO: Rework git_push in GitRepo
            cmd = ['git', 'push']
            if set_upstream:
                # no upstream branch yet
                cmd.append("--set-upstream")
            cmd += [dest_resolved, ds.repo.git_get_active_branch()]
            ds.repo._git_custom_command('', cmd)
            # push annex branch:
            if isinstance(ds.repo, AnnexRepo):
                ds.repo.git_push("%s +git-annex:git-annex" % dest_resolved)

            # TODO: if with_data is a shell pattern, we get a list, when called
            # from shell, right?
            # => adapt the following and check constraints to allow for that
            if with_data:
                ds.repo._git_custom_command('', ["git", "annex", "copy"] +
                                            with_data + ["--to", dest_resolved])

            if recursive and ds.get_dataset_handles() != []:
                results = [ds]
                # Note: add remote currently disabled in publish
                # modify URL templates:
                # if dest_url:
                #     dest_url = dest_url.replace('%NAME', basename(ds.path) + '-%NAME')
                # if dest_pushurl:
                #     dest_pushurl = dest_pushurl.replace('%NAME', basename(ds.path) + '-%NAME')
                for subds in ds.get_dataset_handles():
                    results.append(Dataset(opj(ds.path,
                                              subds)).publish(
                        dest=dest,
                        # Note: use `dest` instead of `dest_resolved` in case
                        # dest was None, so subdatasets would use their default
                        # as well
                        # Note: add remote currently disabled in publish
                        # dest_url=dest_url,
                        # dest_pushurl=dest_pushurl,
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
