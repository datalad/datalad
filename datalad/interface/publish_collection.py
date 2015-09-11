# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for publishing a collection
"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import exists, join as opj, abspath, expandvars, expanduser, isdir
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.collectionrepo import CollectionRepo, GitRepo, \
    CollectionRepoHandleBackend
from ..support.handlerepo import HandleRepo
from ..support.metadatahandler import CustomImporter, URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..consts import REPO_STD_META_FILE, HANDLE_META_DIR
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from appdirs import AppDirs
from six.moves.urllib.parse import urlparse

dirs = AppDirs("datalad", "datalad.org")


class PublishCollection(Interface):
    """publish a collection.

    This is basic implementation for testing purposes
    """
    # TODO: A lot of doc ;)

    _params_ = dict(
        target=Parameter(
            args=('target',),
            doc="server-side base directory for the published collection and "
                "handle repositories",
            constraints=EnsureStr()),
        collection=Parameter(
            args=('collection',),
            doc="name of or path to the local collection",
            nargs="?",
            constraints=EnsureStr()),
        baseurl=Parameter(
            args=('baseurl',),
            doc="public base url of the published collection",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        remote_name=Parameter(
            args=('--remote-name',),
            doc="name for the remote to add to the local collection",
            nargs="?",
            constraints=EnsureStr() | EnsureNone())
        )

    def __call__(self, target, collection=curdir, baseurl=None,
                 remote_name=None):

        # ssh-target: ssh://someone@somewhere/deeper/in/there

        local_collection_repo = get_repo_instance(
            abspath(expandvars(expanduser(collection))), CollectionRepo)

        parsed_target = urlparse(target)  # => scheme, path

        from ..cmd import Runner
        runner = Runner()
        if parsed_target.scheme == 'ssh':
            if parsed_target.netloc == '':
                raise RuntimeError("Invalid ssh address: %s" % target)
            # build control master:
            import os.path
            import os

            # For now, not really cross-platform:
            user_home = os.path.expanduser('~')  #  This has to be available somewhere!
            cm_path = opj(user_home, '.ssh', 'controlmasters')
            ssh_cmd_opt = "-S %s/%s:%d %s" % (cm_path,
                                              parsed_target.netloc,
                                              22 if parsed_target.port is None
                                              else parsed_target.port,
                                              parsed_target.hostname)
            runner.run("ssh -M %s" % ssh_cmd_opt)

            # TODO: copy script to server:
            # TODO: run it:
            # arguments:
            # parsed_target.path
            # "DATALAD_COL_" + local_collection_repo.name
            # local_collection_repo.get_handle_list()

            out, err = runner.run("ssh %s ....." % ssh_cmd_opt)

            # set GIT-SSH:
            os.environ['GIT_SSH'] = "ssh %s" % ' '.join(ssh_cmd_opt)

        elif parsed_target.scheme == 'file' or parsed_target.scheme == '':

            # TODO: run the script:
            # arguments:
            # parsed_target.path
            # "DATALAD_COL_" + local_collection_repo.name
            # local_collection_repo.get_handle_list()

            out, err = runner.run("....")

        else:
            raise RuntimeError("Don't know scheme '%s'." %
                               parsed_target.scheme)

        # check output:
        results = parse_script_output(out, err)

        script_failed = False
        for name in local_collection_repo.get_handle_list() + \
                ["DATALAD_COL_" + local_collection_repo.name]:
            if not results[name].ok:
                lgr.error("Server setup for %s failed." % name)
                script_failed = True
        # exit here, if something went wrong:
        if script_failed:
            raise RuntimeError("Server setup failed.")

        # Now, all the handles:
        from .publish_handle import PublishHandle
        handle_publisher = PublishHandle()
        for handle_name in local_collection_repo.get_handle_list():

            # get location:
            handle_loc = urlparse(CollectionRepoHandleBackend(
                local_collection_repo, handle_name).url).path
            # raise exception if there's no handle at that location:
            try:
                handle_repo = get_repo_instance(handle_loc, HandleRepo)
            except RuntimeError as e:
                lgr.error("No handle available at %s. Skip." % handle_loc)
                raise e

            handle_target = opj(target, handle_name)


            handle_publisher(handle_target, handle=handle_loc,
                             url=baseurl + '/' + handle_name)


        # check succes => go on with collection




        # first try: local path
        if not isdir(abspath(expandvars(expanduser(target)))):
            raise RuntimeError("Can't handle target %s" % target)
        target = abspath(expandvars(expanduser(target)))

        if baseurl is None:
            baseurl = target

        collection_url = baseurl + '/' + local_collection_repo.name
        collection_target = opj(target, local_collection_repo.name)

        # prepare publish branch in local collection:
        # check for existing publish branches:
        # TODO: hash + delete on success
        num_pub = len([b for b in local_collection_repo.git_get_branches()
                      if b.startswith("publish")])
        p_branch = "publish%d" % (num_pub + 1)
        local_collection_repo.git_checkout(p_branch, '-b')

        importer = CustomImporter('Collection', 'Collection', DLNS.this)
        importer.import_data(local_collection_repo.path)
        graphs = importer.get_graphs()
        orig_uri = graphs[REPO_STD_META_FILE[0:-4]].value(predicate=RDF.type,
                                                          object=DLNS.Handle)
        # correct collection uri
        new_uri = URIRef(collection_url)
        for graph_name in graphs:
            for p, o in graphs[graph_name].predicate_objects(subject=orig_uri):
                graphs[graph_name].remove((orig_uri, p, o))
                graphs[graph_name].add((new_uri, p, o))

        # correct handle uris in hasPart statements:
        replacements = []
        for o in graphs[REPO_STD_META_FILE[0:-4]].objects(subject=new_uri,
                                                          predicate=DCTERMS.hasPart):
            from os.path import basename
            path = urlparse(o).path
            if exists(path):
                # local handle
                o_new = URIRef(baseurl + '/' + path[-len(basename(path)):])
                replacements.append((o, o_new))
            else:
                # TODO: what to do? just skip for now
                continue
        for o, o_new in replacements:
            graphs[REPO_STD_META_FILE[0:-4]].remove((new_uri, DCTERMS.hasPart, o))
            graphs[REPO_STD_META_FILE[0:-4]].add((new_uri, DCTERMS.hasPart, o_new))

        # TODO: add commit reference


        importer.store_data(local_collection_repo.path)
        [local_collection_repo.git_add(graph_name + '.ttl')
         for graph_name in graphs]
        local_collection_repo.git_commit("metadata prepared for publishing")


        # add as remote to local:
        if remote_name is None:
            num_pub_remotes = len([r for r in
                                   local_collection_repo.git_get_remotes()
                                   if r.startswith("publish")])
            remote_name = "published%d" % (num_pub_remotes + 1)
        local_collection_repo.git_remote_add(remote_name, collection_url)

        # push local branch "publish" to remote branch "master"
        # we want to push to master, so a different branch has to be checked
        # out in target; in general we can't explicitly allow for the local
        # repo to push
        local_collection_repo.git_push("%s +%s:master" % (remote_name, p_branch))

        # finally:
        local_collection_repo.git_checkout("master")
        # TODO: Delete publish branch? see above
