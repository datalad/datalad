# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base classes to custom git-annex remotes (e.g. extraction from archives)"""

from __future__ import absolute_import

__docformat__ = 'restructuredtext'

import errno
import os
import sys

from collections import Counter

from ..support.path import (
    join as opj,
    lexists,
)

from urllib.parse import urlparse

import logging
lgr = logging.getLogger('datalad.customremotes')

from ..ui import ui
from ..support.cache import DictCache
from datalad.support.exceptions import CapturedException
from ..cmdline.helpers import get_repo_instance
from datalad.utils import (
    getargspec,
)

URI_PREFIX = "dl"
SUPPORTED_PROTOCOL = 1

DEFAULT_COST = 100
DEFAULT_AVAILABILITY = "LOCAL"


class AnnexCustomRemote(object):
    def __init__(self, path=None, cost=None, fin=None, fout=None):  # , availability=DEFAULT_AVAILABILITY):
        """
        Parameters
        ----------
        path : string, optional
            Path to the repository for which this custom remote is serving.
            Usually this class is instantiated by a script which runs already
            within that directory, so the default is to point to current
            directory, i.e. '.'
        """
        # instruct annex backend UI to use this remote
        if ui.backend == 'annex':
            ui.set_specialremote(self)

    @classmethod
    def _get_custom_scheme(cls, prefix):
        """Helper to generate custom datalad URL prefixes
        """
        # prefix which will be used in all URLs supported by this custom remote
        # https://tools.ietf.org/html/rfc2718 dictates "URL Schemes" standard
        # 2.1.2   suggests that we do use // since all of our URLs will define
        #         some hierarchical structure.  But actually since we might encode
        #         additional information (such as size) into the URL, it will not be
        #         strictly conforming it. Thus we will not use //
        return "%s+%s" % (URI_PREFIX, prefix)  # if .PREFIX else '')

    def req_GETCOST(self):
        self.send("COST", self.cost)

    def req_GETAVAILABILITY(self):
        self.send("AVAILABILITY", self.AVAILABILITY.upper())


# this function only has anecdotal value and is not used anywhere
def generate_uuids():
    """Generate UUIDs for our remotes. Even though quick, for consistency pre-generated and recorded in consts.py"""
    import uuid
    return {
        remote: str(uuid.uuid5(uuid.NAMESPACE_URL, 'http://datalad.org/specialremotes/%s' % remote))
        for remote in {'datalad', 'datalad-archives'}
    }


def init_datalad_remote(repo, remote, encryption=None, autoenable=False, opts=[]):
    """Initialize datalad special remote"""
    from datalad.consts import DATALAD_SPECIAL_REMOTES_UUIDS
    lgr.info("Initiating special remote %s", remote)
    remote_opts = [
        'encryption=%s' % str(encryption).lower(),
        'type=external',
        'autoenable=%s' % str(bool(autoenable)).lower(),
        'externaltype=%s' % remote
    ]
    # use unique uuid for our remotes
    # This should help with merges of disconnected repos etc
    # ATM only datalad/datalad-archives is expected,
    # so on purpose getitem
    remote_opts.append('uuid=%s' % DATALAD_SPECIAL_REMOTES_UUIDS[remote])
    return repo.init_remote(remote, remote_opts + opts)


def ensure_datalad_remote(repo, remote=None,
                          encryption=None, autoenable=False):
    """Initialize and enable datalad special remote if it isn't already.

    Parameters
    ----------
    repo : AnnexRepo
    remote : str, optional
        Special remote name. This should be one of the values in
        datalad.consts.DATALAD_SPECIAL_REMOTES_UUIDS and defaults to
        datalad.consts.DATALAD_SPECIAL_REMOTE.
    encryption, autoenable : optional
        Passed to `init_datalad_remote`.
    """
    from datalad.consts import DATALAD_SPECIAL_REMOTE
    from datalad.consts import DATALAD_SPECIAL_REMOTES_UUIDS

    remote = remote or DATALAD_SPECIAL_REMOTE

    uuid = DATALAD_SPECIAL_REMOTES_UUIDS.get(remote)
    if not uuid:
        raise ValueError("'{}' is not a known datalad special remote: {}"
                         .format(remote,
                                 ", ".join(DATALAD_SPECIAL_REMOTES_UUIDS)))
    name = repo.get_special_remotes().get(uuid, {}).get("name")

    if not name:
        init_datalad_remote(repo, remote,
                            encryption=encryption, autoenable=autoenable)
    elif repo.is_special_annex_remote(name, check_if_known=False):
        lgr.debug("datalad special remote '%s' is already enabled", name)
    else:
        lgr.info("datalad special remote '%s' found. Enabling", name)
        repo.enable_remote(name)
