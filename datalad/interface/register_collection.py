# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for collection registration

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.collectionrepo import CollectionRepo
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class RegisterCollection(Interface):
    """Register a collection with datalad."""
    _params_ = dict(
        url=Parameter(
            doc="url of the collection",
            constraints=EnsureStr()),
        name=Parameter(
            args=('name',),
            nargs='?',
            doc="name, the collection is registered with; if no name is given "
                "the name is derived from the url.",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, url, name=None):

        # TODO: Sanity/validity checks for url. Also constraint?
        #       What's may be different in case it's a local path?

        # derive name from url:
        if name is None:
            parts = url.split('/')
            parts.reverse()
            catch_next = False
            for part in parts:
                if catch_next:
                    name = part
                    break
                elif part == '.git':
                    catch_next = True
                elif part.endswith('.git'):
                    name = part[0:-4]
                    break
                else:
                    pass

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))
        local_master.git_remote_add(name, url)
        local_master.git_fetch(name)
