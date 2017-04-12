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
from os.path import expanduser

# directory containing prepared metadata of a dataset repository:
HANDLE_META_DIR = ".datalad"
CRAWLER_META_DIR = join(HANDLE_META_DIR, 'crawl')
CRAWLER_META_CONFIG_FILENAME = 'crawl.cfg'
CRAWLER_META_CONFIG_PATH = join(CRAWLER_META_DIR, CRAWLER_META_CONFIG_FILENAME)
CRAWLER_META_VERSIONS_DIR = join(CRAWLER_META_DIR, 'versions')
# TODO: RENAME THIS UGLINESS?
CRAWLER_META_STATUSES_DIR = join(CRAWLER_META_DIR, 'statuses')

# Make use of those in datalad.metadata
METADATA_DIR = join(HANDLE_META_DIR, 'meta')
METADATA_FILENAME = 'meta.json'

ARCHIVES_SPECIAL_REMOTE = 'datalad-archives'
DATALAD_SPECIAL_REMOTE = 'datalad'
DATALAD_GIT_DIR = join('.git', 'datalad')

# pregenerated using
# python3 -c 'from datalad.customremotes.base import generate_uuids as guuid; print(guuid())'
DATALAD_SPECIAL_REMOTES_UUIDS = {
    # should not be changed from now on!
    DATALAD_SPECIAL_REMOTE: 'cf13d535-b47c-5df6-8590-0793cb08a90a',
    ARCHIVES_SPECIAL_REMOTE: 'c04eb54b-4b4e-5755-8436-866b043170fa'
}

ARCHIVES_TEMP_DIR = join(DATALAD_GIT_DIR, 'tmp', 'archives')
ANNEX_TEMP_DIR = join('.git', 'annex', 'tmp')

DATASETS_TOPURL = "http://datasets.datalad.org/"

# Centralized deployment
LOCAL_CENTRAL_PATH = join(expanduser('~'), 'datalad')

WEB_META_LOG = join(DATALAD_GIT_DIR, 'logs')
WEB_META_DIR = join(DATALAD_GIT_DIR, 'metadata')
WEB_HTML_DIR = join(DATALAD_GIT_DIR, 'web')

# Format to use for time stamps
TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%S%z"

# We use custom ssh runner while interacting with git
#GIT_SSH_COMMAND = "/tmp/sshrun"  # was a little shell script to help troubleshooting
GIT_SSH_COMMAND = "datalad sshrun"