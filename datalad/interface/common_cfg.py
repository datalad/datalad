# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Common configuration options

"""

__docformat__ = 'restructuredtext'

from appdirs import AppDirs
from datalad.support.constraints import EnsureBool
dirs = AppDirs("datalad", "datalad.org")


definitions = {
    # TODO fill with wisdom
    #'datalad.metadata.nativetype': {
    #    'ui': ('question',  # UI dialog type
    #           {'title': 'Metadata',
    #            'text': 'Eh?'}),
    #    'destination': 'dataset',  # where it should be stored by default
    #}
    'datalad.locations.cache': {
        'ui': ('question',
               {'title': 'Cache directory',
                'text': 'Where should datalad cache files?'}),
        'destination': 'global',
        'default': dirs.user_cache_dir,
    },
    # this is actually used in downloaders, but kept cfg name original
    'datalad.crawl.cache': {
        'ui': ('yesno', {
               'title': 'Crawler download caching',
               'text': 'Should the crawler cache downloaded files?'}),
        'destination': 'local',
        'type': bool,
    },
    'datalad.crawl.dryrun': {
        'ui': ('yesno', {
               'title': 'Crawler dry-run',
               'text': 'Should the crawler ... I AM NOT QUITE SURE WHAT?'}),
        'destination': 'local',
        'type': EnsureBool(),
    },
    'datalad.externals.nda.dbserver': {
        'ui': ('question', {
               'title': 'NDA database server',
               'text': 'Hostname of the database server'}),
        'destination': 'global',
    },
    'datalad.crawl.default_backend': {
        'ui': ('question', {
               'title': 'Default annex backend',
               # XXX we could add choices... but might get out of sync
               'text': 'Content hashing method to be used by git-annex'}),
        'destination': 'dataset',
    },
    'datalad.crawl.init_direct': {
        'ui': ('question', {
               'title': 'Default annex repository mode',
               'text': 'Should dataset be initialized in direct mode?'}),
        'destination': 'global',
    },
    'datalad.crawl.pipeline.housekeeping': {
        'ui': ('yesno', {
               'title': 'Crawler pipeline house keeping',
               'text': 'Should the crawler tidy up datasets (git gc, repack, clean)?'}),
        'destination': 'global',
        'type': EnsureBool(),
    },
}
