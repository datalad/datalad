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
from os.path import join as opj
from datalad.support.constraints import EnsureBool
from datalad.support.constraints import EnsureInt
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureChoice

dirs = AppDirs("datalad", "datalad.org")


definitions = {
    # this is actually used in downloaders, but kept cfg name original
    'datalad.crawl.cache': {
        'ui': ('yesno', {
               'title': 'Crawler download caching',
               'text': 'Should the crawler cache downloaded files?'}),
        'destination': 'local',
        'type': bool,
    },
    'datalad.externals.nda.dbserver': {
        'ui': ('question', {
               'title': 'NDA database server',
               'text': 'Hostname of the database server'}),
        'destination': 'global',
    },
    'datalad.locations.cache': {
        'ui': ('question', {
               'title': 'Cache directory',
               'text': 'Where should datalad cache files?'}),
        'destination': 'global',
        'default': dirs.user_cache_dir,
    },
    'datalad.locations.system-plugins': {
        'ui': ('question', {
               'title': 'System plugin directory',
               'text': 'Where should datalad search for system plugins?'}),
        'destination': 'global',
        'default': opj(dirs.site_config_dir, 'plugins'),
    },
    'datalad.locations.user-plugins': {
        'ui': ('question', {
               'title': 'User plugin directory',
               'text': 'Where should datalad search for user plugins?'}),
        'destination': 'global',
        'default': opj(dirs.user_config_dir, 'plugins'),
    },
    'datalad.exc.str.tblimit': {
        'ui': ('question', {
               'title': 'This flag is used by the datalad extract_tb function which extracts and formats stack-traces. It caps the number of lines to DATALAD_EXC_STR_TBLIMIT of pre-processed entries from traceback.'}),
    },
    'datalad.fake-dates': {
        'ui': ('yesno', {
               'title': 'Fake (anonymize) dates',
               'text': 'Should the dates in the logs be faked?'}),
        'destination': 'local',
        'type': EnsureBool(),
        'default': False,
    },
    'datalad.fake-dates-start': {
        'ui': ('question', {
            'title': 'Initial fake date',
            'text': 'When faking dates and there are no commits in any local branches, generate the date by adding one second to this value (Unix epoch time). The value must be positive.'}),
        'type': EnsureInt(),
        'default': 1112911993,
    },
    'datalad.tests.nonetwork': {
        'ui': ('yesno', {
               'title': 'Skips network tests completely if this flag is set Examples include test for s3, git_repositories, openfmri etc'}),
        'type': EnsureBool(),
    },
    'datalad.tests.nonlo': {
        'ui': ('question', {
               'title': 'Specifies network interfaces to bring down/up for testing. Currently used by travis.'}),
    },
    'datalad.tests.noteardown': {
        'ui': ('yesno', {
               'title': 'Does not execute teardown_package which cleans up temp files and directories created by tests if this flag is set'}),
        'type': EnsureBool(),
    },
    'datalad.tests.protocolremote': {
        'ui': ('yesno', {
            'title': 'Binary flag to specify whether to test protocol '
                     'interactions of custom remote with annex'}),
        'type': EnsureBool(),
    },
    'datalad.tests.dataladremote': {
        'ui': ('yesno', {
               'title': 'Binary flag to specify whether each annex repository should get datalad special remote in every test repository'}),
        'type': EnsureBool(),
    },
    'datalad.tests.runcmdline': {
        'ui': ('yesno', {
               'title': 'Binary flag to specify if shell testing using shunit2 to be carried out'}),
        'type': EnsureBool(),
    },
    'datalad.tests.ssh': {
        'ui': ('yesno', {
               'title': 'Skips SSH tests if this flag is **not** set'}),
        'type': EnsureBool(),
    },
    'datalad.tests.knownfailures.skip': {
        'ui': ('yesno', {
               'title': 'Skips tests that are known to currently fail'}),
        'type': EnsureBool(),
        'default': True,
    },
    'datalad.tests.knownfailures.probe': {
        'ui': ('yesno', {
               'title': 'Probes tests that are known to fail on whether or not they are actually still failing'}),
        'type': EnsureBool(),
        'default': False,
    },
    'datalad.tests.temp.dir': {
        'ui': ('question', {
               'title': 'Create a temporary directory at location specified by this flag. It is used by tests to create a temporary git directory while testing git annex archives etc'}),
    },
    'datalad.tests.temp.keep': {
        'ui': ('yesno', {
               'title': 'Function rmtemp will not remove temporary file/directory created for testing if this flag is set'}),
        'type': EnsureBool(),
    },
    'datalad.tests.temp.fs': {
        'ui': ('question', {
               'title': 'Specify the temporary file system to use as loop device for testing DATALAD_TESTS_TEMP_DIR creation'}),
    },
    'datalad.tests.temp.fssize': {
        'ui': ('question', {
               'title': 'Specify the size of temporary file system to use as loop device for testing DATALAD_TESTS_TEMP_DIR creation'}),
    },
    'datalad.tests.ui.backend': {
        'ui': ('question', {
            'title': 'Tests UI backend',
            # XXX we could add choices...
            'text': 'Which UI backend to use'}),
        'default': 'tests-noninteractive',
    },
    'datalad.tests.usecassette': {
        'ui': ('question', {
               'title': 'Specifies the location of the file to record network transactions by the VCR module. Currently used by when testing custom special remotes'}),
    },
    'datalad.log.level': {
        'ui': ('question', {
            'title': 'Used for control the verbosity of logs printed to '
                     'stdout while running datalad commands/debugging'}),
    },
    'datalad.log.name': {
        'ui': ('question', {
            'title': 'Include name of the log target in the log line'}),
    },
    'datalad.log.names': {
        'ui': ('question', {
            'title': 'Which names (,-separated) to print log lines for'}),
    },
    'datalad.log.namesre': {
        'ui': ('question', {
            'title': 'Regular expression for which names to print log lines for'}),
    },
    'datalad.log.outputs': {
        'ui': ('question', {
               'title': 'Used to control either both stdout and stderr of external commands execution are logged in detail (at DEBUG level)'}),
    },
    'datalad.log.timestamp': {
        'ui': ('yesno', {
               'title': 'Used to add timestamp to datalad logs'}),
        'default': False,
        'type': EnsureBool(),
    },
    'datalad.log.traceback': {
        'ui': ('question', {
               'title': 'Runs TraceBack function with collide set to True, if this flag is set to "collide". This replaces any common prefix between current traceback log and previous invocation with "..."'}),
    },
    'datalad.cmd.protocol': {
        'ui': ('question', {
               'title': 'Specifies the protocol number used by the Runner to note shell command or python function call times and allows for dry runs. "externals-time" for ExecutionTimeExternalsProtocol, "time" for ExecutionTimeProtocol and "null" for NullProtocol. Any new DATALAD_CMD_PROTOCOL has to implement datalad.support.protocol.ProtocolInterface'}),
    },
    'datalad.cmd.protocol.prefix': {
        'ui': ('question', {
               'title': 'Sets a prefix to add before the command call times are noted by DATALAD_CMD_PROTOCOL.'}),
    },
    'datalad.repo.direct': {
        'ui': ('yesno', {
               'title': 'Direct Mode for git-annex repositories',
               'text': 'Set this flag to create annex repositories in direct mode by default'}),
        'type': EnsureBool(),
        'default': False,
    },
    'datalad.repo.version': {
        'ui': ('question', {
               'title': 'git-annex repository version',
               'text': 'Specifies the repository version for git-annex to be used by default'}),
        'type': EnsureInt(),
        'default': 5,
    },
    'datalad.metadata.maxfieldsize': {
        'ui': ('question', {
               'title': 'Maximum metadata field size',
               'text': 'Metadata fields exceeding this size (in bytes/chars) are excluded from metadata extractio'}),
        'default': 100000,
        'type': EnsureInt(),
    },
    'datalad.metadata.nativetype': {
        'ui': ('question', {
               'title': 'Native dataset metadata scheme',
               'text': 'Set this label to engage a particular metadata extraction parser'}),
    },
    'datalad.metadata.store-aggregate-content': {
        'ui': ('question', {
               'title': 'Aggregated content metadata storage',
               'text': 'If this flag is enabled, content metadata is aggregated into superdataset to allow for discovery of individual files. If disable unique content metadata values are still aggregated to enable dataset discovery'}),
        'type': EnsureBool(),
        'default': True,
    },
    'datalad.search.default-mode': {
        'ui': ('question', {
               'title': 'Default search mode',
               'text': 'Label of the mode to be used by default'}),
        'type': EnsureChoice('egrep', 'textblob', 'autofield'),  # graph,...
        'default': 'egrep',
    },
    'datalad.search.index-default-documenttype': {
        'ui': ('question', {
               'title': 'Type of search index documents',
               'text': 'Labels of document types to include in a default search index'}),
        'type': EnsureChoice('all', 'datasets', 'files'),
        'default': 'datasets',
    },
    'datalad.metadata.create-aggregate-annex-limit': {
        'ui': ('question', {
               'title': 'Limit configuration annexing aggregated metadata in new dataset',
               'text': 'Git-annex large files expression (see https://git-annex.branchable.com/tips/largefiles; given expression will be wrapped in parentheses)'}),
        'default': 'largerthan=20kb',
    },
    'datalad.runtime.raiseonerror': {
        'ui': ('question', {
               'title': 'Error behavior',
               'text': 'Set this flag to cause DataLad to raise an exception on errors that would have otherwise just get logged'}),
        'type': EnsureBool(),
        'default': False,
    },
    'datalad.runtime.report-status': {
        'ui': ('question', {
               'title': 'Command line result reporting behavior',
               'text': "If set (to other than 'all'), constrains command result report to records matching the given status. 'success' is a synonym for 'ok' OR 'notneeded', 'failure' stands for 'impossible' OR 'error'"}),
        'type': EnsureChoice('all', 'success', 'failure', 'ok', 'notneeded', 'impossible', 'error'),
        'default': None,
    },
    'datalad.search.indexercachesize': {
        'ui': ('question', {
               'title': 'Maximum cache size for search index (per process)',
               'text': 'Actual memory consumption can be twice as high as this value in MB (one process per CPU is used)'}),
        'default': 256,
        'type': EnsureInt(),
    },
}
