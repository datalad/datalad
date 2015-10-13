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


from os import curdir, environ, geteuid, urandom
from os.path import exists, join as opj, abspath, expandvars, expanduser, isdir
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.collectionrepo import CollectionRepo, GitRepo, \
    CollectionRepoHandleBackend
from ..support.handlerepo import HandleRepo
from ..support.metadatahandler import CustomImporter, URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from datalad.cmd import CommandError
from ..consts import REPO_STD_META_FILE, HANDLE_META_DIR
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from appdirs import AppDirs
from six.moves.urllib.parse import urlparse

dirs = AppDirs("datalad", "datalad.org")


def parse_script_output(out, err):
    """parse out put of server setup script"""
    results = dict()
    import re
    col_p = re.compile("DATALAD_COLLECTION_REPO_.+?: init")
    for entry in re.findall(col_p, out):
        results[entry[24:-6]] = dict()
        results[entry[24:-6]]['init'] = True

    # handle occurences:
    hdl_p = re.compile("DATALAD_HANDLE_REPO_.+?:")
    for entry in re.findall(hdl_p, out):
        if entry.startswith("_INFO"):
            continue
        else:
            results[entry[20:-1]] = dict()

    hdl_p = re.compile("DATALAD_HANDLE_REPO_.+?: init DATALAD_END")
    for entry in re.findall(hdl_p, out):
        results[entry[20:-18]]['init'] = True

    hdl_p = re.compile("DATALAD_HANDLE_REPO_.+?: annex_init DATALAD_END")
    for entry in re.findall(hdl_p, out):
        results[entry[20:-24]]['annex init'] = True

    return results


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

        # Note:
        # ssh-target: ssh://someone@somewhere/deeper/in/there

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                          'localcollection'))

        if isdir(abspath(expandvars(expanduser(collection)))):
            c_path = abspath(expandvars(expanduser(collection)))
        elif collection in local_master.git_get_remotes():
            c_path = urlparse(local_master.git_get_remote_url(collection)).path
            if not isdir(c_path):
                raise RuntimeError("Invalid path to collection '%s':\n%s" %
                                   (collection, c_path))
        else:
            raise RuntimeError("Unknown collection '%s'." % collection)

        local_collection_repo = get_repo_instance(
            abspath(expandvars(expanduser(c_path))), CollectionRepo)

        available_handles = [key for key in
                             local_collection_repo.get_handle_list()
                             if exists(urlparse(CollectionRepoHandleBackend(
                                 local_collection_repo, key).url).path)]

        parsed_target = urlparse(target)  # => scheme, path

        from pkg_resources import resource_filename
        prepare_script_path = \
            resource_filename('datalad',
                              'resources/sshserver_prepare_for_publish.sh')
        cleanup_script_path = \
            resource_filename('datalad',
                              'resources/sshserver_cleanup_after_publish.sh')

        from ..cmd import Runner
        runner = Runner()
        if parsed_target.scheme == 'ssh':
            if parsed_target.netloc == '':
                raise RuntimeError("Invalid ssh address: %s" % target)

            if baseurl is None:
                baseurl = target
            collection_url = baseurl + '/' + "DATALAD_COL_" + \
                             local_collection_repo.name

            # build control master:
            from datalad.utils import assure_dir
            var_run_user_datalad = "/var/run/user/%s/datalad" % geteuid()
            assure_dir(var_run_user_datalad)
            control_path = "%s/%s" % (var_run_user_datalad, parsed_target.netloc)
            control_path += ":%s" % parsed_target.port if parsed_target.port else ""

            # start controlmaster:

            cmd_str = "ssh -o \"ControlMaster=yes\" -o \"ControlPath=%s\" " \
                      "-o \"ControlPersist=yes\" %s exit" % \
                      (control_path,  parsed_target.hostname)
            lgr.error("DEBUG: %s" % cmd_str)
            import subprocess
            proc = subprocess.Popen(cmd_str, shell=True)
            proc.communicate(input="\n")  # why the f.. this is necessary?

            # prepare target repositories:

            script_options = "%s DATALAD_COL_%s" % (parsed_target.path,
                                                    local_collection_repo.name)
            for key in available_handles:
                # prepare repos for locally available handles only
                script_options += " %s" % key

            cmd_str = "ssh -S %s %s \'cat | sh /dev/stdin\' %s" % \
                      (control_path, parsed_target.hostname, script_options)
            cmd_str += " < %s" % prepare_script_path
            try:
                out, err = runner.run(cmd_str)
            except CommandError as e:
                lgr.error("Preparation script failed: %s" % str(e))
                out = e.stdout
                err = e.stderr

            # set GIT-SSH:
            environ['GIT_SSH'] = resource_filename('datalad',
                                                   'resources/git_ssh.sh')

        elif parsed_target.scheme == 'file' or parsed_target.scheme == '':
            # we should have a local target path
            if not isdir(abspath(expandvars(expanduser(parsed_target.path)))):
                raise RuntimeError("%s doesn't exist." % parsed_target.path)

            target_path = abspath(expandvars(expanduser(parsed_target.path)))
            if baseurl is None:
                baseurl = target_path
            collection_url = baseurl + '/' + "DATALAD_COL_" + \
                             local_collection_repo.name

            try:
                out, err = runner.run(["sh", prepare_script_path,
                                       target_path,
                                       "DATALAD_COL_" + local_collection_repo.name]
                                      + available_handles)
            except CommandError as e:
                lgr.error("Preparation script failed: %s" % str(e))
                out = e.stdout
                err = e.stderr

        else:
            raise RuntimeError("Don't know scheme '%s'." %
                               parsed_target.scheme)

        # check output:
        results = parse_script_output(out, err)

        script_failed = False
        for name in available_handles + \
                ["DATALAD_COL_" + local_collection_repo.name]:
            if not results[name]['init']:
                lgr.error("Server setup for %s failed." % name)
                script_failed = True
        # exit here, if something went wrong:
        if script_failed:
            raise RuntimeError("Server setup failed.")

        # Now, all the handles:
        from .publish_handle import PublishHandle
        handle_publisher = PublishHandle()
        for handle_name in available_handles:

            # get location:
            handle_loc = urlparse(CollectionRepoHandleBackend(
                local_collection_repo, handle_name).url).path
            # raise exception if there's no handle at that location:
            try:
                handle_repo = get_repo_instance(handle_loc, HandleRepo)
            except RuntimeError as e:
                lgr.error("'%s': No handle available at %s. Skip." %
                          (handle_name, handle_loc))
                continue

            annex_ssh = "-S %s" % control_path \
                if parsed_target.scheme == 'ssh' else None
            handle_publisher(None, handle=handle_loc,
                             url=baseurl + '/' + handle_name,
                             ssh_options=annex_ssh)

        # TODO: check success => go on with collection

        # prepare publish branch in local collection:
        # check for existing publish branches:
        from random import choice
        from string import ascii_letters
        from six.moves import xrange
        p_branch = "publish_" + ''.join(choice(ascii_letters) for i in xrange(6))
        local_collection_repo.git_checkout(p_branch, '-b')

        importer = CustomImporter('Collection', 'Collection', DLNS.this)
        importer.import_data(local_collection_repo.path)
        graphs = importer.get_graphs()
        orig_uri = graphs[REPO_STD_META_FILE[0:-4]].value(predicate=RDF.type,
                                                          object=DLNS.Collection)

        # correct collection uri
        new_uri = URIRef(collection_url)
        for graph_name in graphs:
            for p, o in graphs[graph_name].predicate_objects(subject=orig_uri):
                graphs[graph_name].remove((orig_uri, p, o))
                graphs[graph_name].add((new_uri, p, o))

        # correct handle uris in hasPart statements:
        replacements = []
        from datalad.support.collection import Collection
        from datalad.support.collectionrepo import CollectionRepoBackend
        col_meta = Collection(CollectionRepoBackend(local_collection_repo))
        for o in graphs[REPO_STD_META_FILE[0:-4]].objects(subject=new_uri,
                                                          predicate=DCTERMS.hasPart):
            from os.path import basename
            path = urlparse(o).path
            if exists(path):
                # local handle
                # retrieve name for that uri:
                # Note: That's an experimental implementation
                hdl_name = None
                for key in col_meta:
                    if urlparse(col_meta[key].url).path == path:
                        hdl_name = col_meta[key].name
                if hdl_name is None:
                    raise RuntimeError("No handle found for path '%s'." % path)

                o_new = URIRef(baseurl + '/' + hdl_name)
                # replacements for collection level:
                replacements.append((o, o_new))

                # replace in collection's handle storage:
                hdl_dir = opj(local_collection_repo.path,
                              local_collection_repo._key2filename(hdl_name))
                hdl_importer = CustomImporter('Collection', 'Handle', o)
                hdl_importer.import_data(hdl_dir)
                hdl_graphs = hdl_importer.get_graphs()
                for g in hdl_graphs:
                    import rdflib
                    rdflib.Graph()
                    for pre, obj in hdl_graphs[g].predicate_objects(o):
                        hdl_graphs[g].remove((o, pre, obj))
                        hdl_graphs[g].add((o_new, pre, obj))
                hdl_importer.store_data(hdl_dir)
                local_collection_repo.git_add(hdl_dir)

            else:
                # We have a locally not available handle
                # in that collection, that therefore can't be published.
                # Just skip for now and assume uri simply doesn't change.
                continue
        for o, o_new in replacements:
            graphs[REPO_STD_META_FILE[0:-4]].remove((new_uri, DCTERMS.hasPart, o))
            graphs[REPO_STD_META_FILE[0:-4]].add((new_uri, DCTERMS.hasPart, o_new))

        # TODO: add commit reference?

        importer.store_data(local_collection_repo.path)
        [local_collection_repo.git_add(graph_name + '.ttl')
         for graph_name in graphs]
        local_collection_repo.git_commit("metadata prepared for publishing")

        # add as remote to local:
        # TODO: Better remote name?
        if remote_name is None:
            remote_name = p_branch
        local_collection_repo.git_remote_add(remote_name, collection_url)

        # push local branch "publish" to remote branch "master"
        # we want to push to master, so a different branch has to be checked
        # out in target; in general we can't explicitly allow for the local
        # repo to push
        local_collection_repo.git_push("%s +%s:master" % (remote_name, p_branch))

        # checkout master in local collection:
        local_collection_repo.git_checkout("master")

        # checkout master in published collection:
        if parsed_target.scheme == 'ssh':
            cmd_str = "ssh -S %s %s \'cat | sh /dev/stdin\' %s" % \
                      (control_path, parsed_target.hostname, script_options)
            cmd_str += " < %s" % cleanup_script_path
            try:
                out, err = runner.run(cmd_str)
            except CommandError as e:
                lgr.error("Clean-up script failed: %s" % str(e))

            # stop controlmaster:
            cmd_str = "ssh -O stop -S %s %s" % (control_path,
                                                parsed_target.hostname)
            try:
                out, err = runner.run(cmd_str)
            except CommandError as e:
                lgr.error("Stopping ssh control master failed: %s" % str(e))

        else:
            try:
                out, err = runner.run(["sh", cleanup_script_path,
                                       target_path,
                                       "DATALAD_COL_" +
                                       local_collection_repo.name]
                                      + available_handles)
            except CommandError as e:
                lgr.error("Clean-up script failed: %s" % str(e))

        # TODO: final check, whether everything is fine
        # Delete publish branch:
        local_collection_repo._git_custom_command('', 'git branch -D %s'
                                                  % p_branch)