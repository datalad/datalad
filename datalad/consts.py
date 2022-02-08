# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""constants for datalad
"""

import os
from os.path import join
import re

# directory containing prepared metadata of a dataset repository:
DATALAD_DOTDIR = ".datalad"
# Compatibility: Used at least in the crawler
# TODO: figure out how to make it possible to issue DeprecationWarning
# upon use.  Possible way: make consts into a class instance, but then they
# all must be imported as `from datalad import consts` and as `consts.CONSTANT`
HANDLE_META_DIR = DATALAD_DOTDIR

# Make use of those in datalad.metadata
OLDMETADATA_DIR = join(DATALAD_DOTDIR, 'meta')
OLDMETADATA_FILENAME = 'meta.json'

METADATA_DIR = join(DATALAD_DOTDIR, 'metadata')
DATASET_METADATA_FILE = join(METADATA_DIR, 'dataset.json')
DATASET_CONFIG_FILE = join(DATALAD_DOTDIR, 'config')

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
WEB_SPECIAL_REMOTE_UUID = '00000000-0000-0000-0000-000000000001'

ARCHIVES_TEMP_DIR = join(DATALAD_GIT_DIR, 'tmp', 'archives')
ANNEX_TEMP_DIR = join('.git', 'annex', 'tmp')
ANNEX_TRANSFER_DIR = join('.git', 'annex', 'transfer')

SEARCH_INDEX_DOTGITDIR = join('datalad', 'search_index')

DATASETS_TOPURL = os.environ.get("DATALAD_DATASETS_TOPURL", None) \
                  or "https://datasets.datalad.org/"
# safeguard
if not DATASETS_TOPURL.endswith('/'):
    DATASETS_TOPURL += '/'

WEB_META_LOG = join(DATALAD_GIT_DIR, 'logs')
WEB_META_DIR = join(DATALAD_GIT_DIR, 'metadata')

# Format to use for time stamps
TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%S%z"

# in order to avoid breakage, import runner-related const
from datalad.runner.gitrunner import GIT_SSH_COMMAND

# magic sha is from `git hash-object -t tree /dev/null`, i.e. from nothing
PRE_INIT_COMMIT_SHA = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'

# git/datalad configuration item to provide a token for github
CONFIG_HUB_TOKEN_FIELD = 'hub.oauthtoken'
GITHUB_LOGIN_URL = 'https://github.com/login'
GITHUB_TOKENS_URL = 'https://github.com/settings/tokens'

# format of git-annex adjusted branch names
ADJUSTED_BRANCH_EXPR = re.compile(r'^adjusted/(?P<name>[^(]+)\(.*\)$')

# Reserved file names on Windows machines
RESERVED_NAMES_WIN = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3',
                      'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1',
                      'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8',
                      'LPT9'}
# Characters that can't be a part of a file name on Windows
ILLEGAL_CHARS_WIN = "[<>:/\\|?*\"]|[\0-\31]"
