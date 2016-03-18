# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for uninstalling a handle

"""

__docformat__ = 'restructuredtext'


from os.path import join as opj
import logging

from six.moves.urllib.parse import urlparse

from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.collectionrepo import CollectionRepo
from datalad.support.handle_backends import CollectionRepoHandleBackend
from ..utils import rmtree
from datalad.cmdline.helpers import get_datalad_master

lgr = logging.getLogger('datalad.interface.uninstall-handle')


class UninstallHandle(Interface):
    """Uninstall a handle.

    Uninstall a before installed handle. This unregisters the handle with
    datalad and deletes the repository.

    Examples:

      $ datalad uninstall-handle MyCoolHandle
    """
    _params_ = dict(
        handle=Parameter(
            doc="name of the handle to uninstall",
            constraints=EnsureStr()))

    @staticmethod
    def __call__(handle):

        # TODO: unifying: also accept path to handle

        local_master = get_datalad_master()

        if handle not in local_master.get_handle_list():
            raise ValueError("Handle '%s' unknown." % handle)

        # converting file-scheme url to local path:
        path = urlparse(CollectionRepoHandleBackend(local_master,
                                                    handle).url).path
        try:
            rmtree(path)
        except OSError as e:
            lgr.warning("Couldn't delete %s:\n%s" % (path, str(e)))

        local_master.remove_handle(handle)

