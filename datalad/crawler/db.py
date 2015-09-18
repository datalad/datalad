# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Module to provide DB for storing crawling/available information"""


class URLDB(object):
    """Database collating urls for the content across all handles

    Schema: TODO, but needs for sure

    - URL (only "public" or internal as for content from archives, or that separate table?)
    - common checksums which we might use/rely upon (MD5, SHA1, SHA256, SHA512)
    - last_checked (if online)
    - last_verified (when verified to contain the content according to the checksums

    allow to query by any known checksum
    """
    pass
