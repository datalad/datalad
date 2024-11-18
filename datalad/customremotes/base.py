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


import logging
from collections import Counter

lgr = logging.getLogger('datalad.customremotes')

from annexremote import (
    RemoteError,
    UnsupportedRequest,
)

from datalad.customremotes import SpecialRemote

URI_PREFIX = "dl"


class AnnexCustomRemote(SpecialRemote):
    # default properties
    COST = 100
    AVAILABILITY = "local"

    def __init__(self, annex):  # , availability=DEFAULT_AVAILABILITY):
        super().__init__(annex)
        # TODO self.info = {}, self.configs = {}

        # OPT: a counter to increment upon successful encounter of the scheme
        # (ATM only in gen_URLS but later could also be used in other
        # requests).  This would allow to consider schemes in order of
        # decreasing success instead of arbitrary hardcoded order
        self._scheme_hits = Counter({s: 0 for s in self.SUPPORTED_SCHEMES})

    @classmethod
    def _get_custom_scheme(cls, prefix):
        """Helper to generate custom datalad URL prefixes
        """
        # prefix which will be used in all URLs supported by this custom remote
        # https://tools.ietf.org/html/rfc2718 dictates "URL Schemes" standard
        # 2.1.2 suggests that we do use // since all of our URLs will define
        # some hierarchical structure.  But actually since we might encode
        # additional information (such as size) into the URL, it will not be
        # strictly conforming it. Thus we will not use //
        return "%s+%s" % (URI_PREFIX, prefix)  # if .PREFIX else '')

    # Helper methods
    def gen_URLS(self, key):
        """Yield URL(s) associated with a key, and keep stats on protocols."""
        nurls = 0
        for scheme, _ in self._scheme_hits.most_common():
            scheme_ = scheme + ":"
            scheme_urls = self.annex.geturls(key, scheme_)
            if scheme_urls:
                # note: generator would cease to exist thus not asking
                # for URLs for other schemes if this scheme is good enough
                self._scheme_hits[scheme] += 1
                for url in scheme_urls:
                    nurls += 1
                    yield url
        self.annex.debug("Processed %d URL(s) for key %s", nurls, key)

    # Protocol implementation
    def initremote(self):
        pass

    def prepare(self):
        pass

    def transfer_store(self, key, local_file):
        raise UnsupportedRequest('This special remote cannot store content')

    def remove(self, key):
        raise RemoteError("Removal of content from urls is not possible")

    def getcost(self):
        return self.COST

    def getavailability(self):
        return self.AVAILABILITY


# this function only has anecdotal value and is not used anywhere
def generate_uuids():
    """Generate UUIDs for our remotes. Even though quick, for
    consistency pre-generated and recorded in consts.py"""
    import uuid
    return {
        remote: str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            'http://datalad.org/specialremotes/%s' % remote))
        for remote in {'datalad', 'datalad-archives'}
    }


def init_datalad_remote(repo, remote, encryption=None, autoenable=False,
                        opts=[]):
    """Initialize datalad special remote"""
    from datalad.consts import DATALAD_SPECIAL_REMOTES_UUIDS
    lgr.info("Initializing special remote %s", remote)
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
    from datalad.consts import (
        DATALAD_SPECIAL_REMOTE,
        DATALAD_SPECIAL_REMOTES_UUIDS,
    )

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
