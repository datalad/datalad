# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""GNU software style metadata parser"""

# Files to look at

# README        General information
# AUTHORS       Credits
# THANKS        Acknowledgments
# CHANGELOG     A detailed changelog, intended for programmers
# NEWS          A basic changelog, intended for users
# INSTALL       Installation instructions
# COPYING/LICENSE
#               Copyright and licensing information
# BUGS          Known bugs and instructions on reporting new ones
# FAQ
# TODO          file listing possible future changes.

from os.path import exists, join as opj


def has_metadata(ds):
    return exists(opj(ds.path, 'README')) \
        and (exists(opj(ds.path, 'AUTHOR')) or exists(opj(ds.path, 'AUTHORS'))
             or exists(opj(ds.path, 'CONTRIBUTORS'))) \
        and (exists(opj(ds.path, 'COPYING')) or exists(opj(ds.path, 'LICENSE')))


def get_metadata(ds):
    """Extract metadata from GNU-style annotated dataset.

    Parameters
    ----------
    ds : dataset instance
      Dataset to extract metadata from.

    Returns
    -------
    list
      List of 3-tuples with subject, predicate, and object
    """
    pass
