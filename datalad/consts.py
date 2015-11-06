# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""constants for datalad
"""

from os.path import join

# file names for metadata of collections and handles:
REPO_STD_META_FILE = 'datalad.ttl'
REPO_CONFIG_FILE = 'config.ttl'

# directory containing prepared metadata of a handle repository:
HANDLE_META_DIR = ".datalad"
CRAWLER_META_DIR = join(HANDLE_META_DIR, 'crawl')

# name of local master collection:
DATALAD_COLLECTION_NAME = "datalad-local"
