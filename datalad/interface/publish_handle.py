# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for publishing a handle
"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import exists, join as opj, abspath, expandvars, expanduser, isdir
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.handlerepo import HandleRepo
from ..support.annexrepo import AnnexRepo
from ..support.metadatahandler import CustomImporter, URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..consts import REPO_STD_META_FILE, HANDLE_META_DIR
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class PublishHandle(Interface):
    """Publish a handle.

    This is basic implementation for testing purposes
    """
    # TODO: A lot of doc ;)

    _params_ = dict(
        target=Parameter(
            args=('target',),
            doc="the target, the handle is to be published to",
            constraints=EnsureStr()),
        handle=Parameter(
            args=('handle',),
            doc="name of or path to the handle",
            nargs="?",
            constraints=EnsureStr()),
        url=Parameter(
            args=('url',),
            doc="public url of the published handle",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        remote=Parameter(
            args=('remote',),
            doc="name for the remote to add to the local handle",
            nargs="?",
            constraints=EnsureStr() | EnsureNone())
        )

    def __call__(self, target, handle=curdir, url=None, remote=None):

        local_handle_repo = get_repo_instance(
            abspath(expandvars(expanduser(handle))), HandleRepo)

        if target is None:
            # assume url is a valid repo to push to;
            assert url is not None
        # TODO: direct ssh-publishing for single handle
        elif not isdir(abspath(expandvars(expanduser(target)))):
            # unexpected target type or invalid path
            raise RuntimeError("Can't handle target %s" % target)
        else:
            # target is local path
            target = abspath(expandvars(expanduser(target)))

        if url is None:
            url = target

        # prepare publish branch in local handle:
        # check for existing publish branches:
        num_pub = len([b for b in local_handle_repo.git_get_branches()
                      if b.startswith("publish")])
        p_branch = "publish%d" % (num_pub + 1)
        local_handle_repo.git_checkout(p_branch, '-b')

        importer = CustomImporter('Handle', 'Handle', DLNS.this)
        importer.import_data(opj(local_handle_repo.path, HANDLE_META_DIR))
        graphs = importer.get_graphs()
        orig_uri = graphs[REPO_STD_META_FILE[0:-4]].value(predicate=RDF.type,
                                                          object=DLNS.Handle)
        new_uri = URIRef(url)
        for graph_name in graphs:
            for p, o in graphs[graph_name].predicate_objects(subject=orig_uri):
                graphs[graph_name].remove((orig_uri, p, o))
                graphs[graph_name].add((new_uri, p, o))

        importer.store_data(opj(local_handle_repo.path, HANDLE_META_DIR))
        local_handle_repo.add_to_git(opj(local_handle_repo.path,
                                         HANDLE_META_DIR),
                                     commit_msg="metadata prepared for "
                                                "publishing")

        if target is not None:
            # create target annex:
            published_handle = AnnexRepo(target, create=True)

        # add as remote to local:
        if remote is None:
            num_pub_remotes = len([r for r in
                                   local_handle_repo.git_get_remotes()
                                   if r.startswith("publish")])
            remote = "published%d" % (num_pub_remotes + 1)
        local_handle_repo.git_remote_add(remote, url)

        # TODO: may be use git annex testremote?

        # 1. push local branch "publish" to remote branch "master"
        # we want to push to master, so a different branch has to be checked
        # out in target; in general we can't explicitly allow for the local
        # repo to push
        if target is not None:
            published_handle.git_checkout("TEMP", '-b')
        local_handle_repo.git_push("%s +%s:master" % (remote, p_branch))
        if target is not None:
            published_handle.git_checkout("master")
        # published_handle._git_custom_command('', "git branch -D TEMP")
        # "TEMP" not found? => because it's empty?

        # 2. push git-annex branch
        local_handle_repo.git_push("%s +git-annex:git-annex" % remote)

        # 3. copy locally available files:
        for file_ in local_handle_repo.get_annexed_files():
            if local_handle_repo.file_has_content(file_):
                local_handle_repo._annex_custom_command(
                    '', "git annex copy %s --to=%s" % (file_, remote))

        # Note: Currently, this is only relevant, when publish-handle is called
        # directly (with local target). Obviously doesn't work remotely!
        if target is not None:
            # 4. get everything else
            published_handle.annex_get('.')

        # finally:
        local_handle_repo.git_checkout("master")