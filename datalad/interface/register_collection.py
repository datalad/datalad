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
from os.path import join as opj, abspath, expanduser, expandvars, isdir
import re
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.collectionrepo import CollectionRepo, \
    CollectionRepoBackend
from datalad.support.collection import Collection
from datalad.cmd import CommandError
from datalad.log import lgr
from datalad.cmdline.helpers import get_datalad_master


class RegisterCollection(Interface):
    """Register a collection with datalad.

    Registering a remote collection with datalad allows for including their
    metadata in searches, installing handles they contain and so on.
    Once registered you can keep track of the current state of the remote
    collection.

    Example:
        $ datalad register-collection \
        http://collections.datalad.org/demo/DATALAD_COL_demo_collection
    """
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
        """
        Returns
        -------
        Collection
        """

        local_master = get_datalad_master()

        # check whether url is a local path:
        if isdir(abspath(expandvars(expanduser(url)))):
            url = abspath(expandvars(expanduser(url)))
            # raise exception, if it's not a valid collection:
            repo = CollectionRepo(url, create=False)
            if name is None:
                name = repo.name

        else:
            # Try to auto complete collection's url:
            url += '/' if not url.endswith('/') else ''
            url_completions = [url,
                               url + '.git',
                               url + url.rstrip('/').split('/')[-1] +
                               '.datalad-collection/.git']

            url_ok = False
            for address in url_completions:
                try:
                    # use ls-remote to verify git can talk to that repository:
                    local_master.git_ls_remote(address, "-h")
                    url = address
                    url_ok = True
                    break
                except CommandError as e:
                    if re.match("fatal.+?%s.+?not found" % url, e.stderr):
                        continue
                    else:
                        lgr.error("Registering collection failed.\n%s" % e)
                        return

            if not url_ok:
                lgr.error("Registering collection failed. "
                          "Couldn't find remote repository.")
                return

            if name is None:
                # derive name from url:
                parts = url.rstrip('/').split('/')
                if parts[-1] == '.git':
                    name = parts[-2]
                elif parts[-1].endswith('.git'):
                    name = parts[-1][0:-4]
                elif parts[-1].endswith('.datalad-collection'):
                    name = parts[-1][0:-19]
                else:
                    name = parts[-1]

        local_master.git_remote_add(name, url)
        local_master.git_fetch(name)

        return Collection(CollectionRepoBackend(local_master,
                                                name + "/master"))