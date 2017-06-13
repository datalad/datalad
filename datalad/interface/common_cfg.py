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
from datalad.support.constraints import EnsureInt

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
    'datalad.crawl.default_backend': {
        'ui': ('question', {
               'title': 'Default annex backend',
               # XXX we could add choices... but might get out of sync
               'text': 'Content hashing method to be used by git-annex'}),
        'destination': 'dataset',
    },
    'datalad.crawl.dryrun': {
        'ui': ('yesno', {
               'title': 'Crawler dry-run',
               'text': 'Should the crawler ... I AM NOT QUITE SURE WHAT?'}),
        'destination': 'local',
        'type': EnsureBool(),
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
    'datalad.exc.str.tblimit': {
        'ui': ('question', {
               'title': 'This flag is used by the datalad extract_tb function which extracts and formats stack-traces. It caps the number of lines to DATALAD_EXC_STR_TBLIMIT of pre-processed entries from traceback.'}),
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
    },
    'datalad.repo.version': {
        'ui': ('question', {
               'title': 'git-annex repository version',
               'text': 'Specifies the repository version for git-annex to be used by default'}),
        'type': EnsureInt(),
    },
}
