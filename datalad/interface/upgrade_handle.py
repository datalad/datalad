# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for adding metadata
"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import exists, join as opj
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend, \
    CollectionRepoHandleBackend
from ..support.handlerepo import HandleRepo, HandleRepoBackend
from ..support.handle import Handle
from ..support.metadatahandler import CustomImporter, URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from datalad.cmdline.helpers import get_datalad_master


class UpgradeHandle(Interface):
    """Upgrade a handle
    """
    # TODO: A lot of doc ;)

    _params_ = dict(
        handle=Parameter(
            args=('handle',),
            doc="name of or path to the handle to be upgraded.",
            nargs='?',
            constraints=EnsureStr() | EnsureNone()),
        upgrade_data=Parameter(
            args=('--upgrade-data',),
            doc="upgrade the actual data",
            action="store_true"))

    def __call__(self, handle=curdir, upgrade_data=False):
        """
        Returns
        -------
        Handle
        """

        local_master = get_datalad_master()

        if exists(handle):
            repo = get_repo_instance(handle, HandleRepo)
        elif handle in local_master.get_handle_list():
            repo = get_repo_instance(CollectionRepoHandleBackend(local_master,
                                                                 handle).url)
        else:
            lgr.error("Unknown handle '%s'." % handle)
            raise RuntimeError("Unknown handle '%s'." % handle)

        remotes = repo.git_get_remotes()
        if not remotes:
            raise RuntimeError("No remotes were found for %s. Cannot upgrade"
                               % repo.path)

        # TODO: it might be arbitrary other remote, not necessarily origin
        # That information is stored in git/.config -- use it
        upgrade_remote = 'origin'
        if upgrade_remote not in remotes:
            raise RuntimeError("No remote %r found to upgrade from. Known remotes: %s"
                               % (upgrade_remote, ', '.join(remotes)))

        if upgrade_data:
            # what files do we currently have?
            files_to_upgrade = [f for f in repo.get_indexed_files()
                                if repo.file_has_content(f)]

        # upgrade it:
        repo.git_pull(upgrade_remote)

        if upgrade_data:
            # upgrade content:
            repo.get(files_to_upgrade)

        return Handle(HandleRepoBackend(repo))