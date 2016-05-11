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

# directory containing prepared metadata of a handle repository:
HANDLE_META_DIR = ".datalad"
CRAWLER_META_DIR = join(HANDLE_META_DIR, 'crawl')
CRAWLER_META_CONFIG_FILENAME = 'crawl.cfg'
CRAWLER_META_CONFIG_PATH = join(CRAWLER_META_DIR, CRAWLER_META_CONFIG_FILENAME)
CRAWLER_META_VERSIONS_DIR = join(CRAWLER_META_DIR, 'versions')
# TODO: RENAME THIS UGLINESS?
CRAWLER_META_STATUSES_DIR = join(CRAWLER_META_DIR, 'statuses')

ARCHIVES_SPECIAL_REMOTE = 'datalad-archives'
DATALAD_SPECIAL_REMOTE = 'datalad'

ARCHIVES_TEMP_DIR = join('.git', 'datalad', 'tmp', 'archives')
