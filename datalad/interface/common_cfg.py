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
from os import environ
from os.path import join as opj, expanduser
from datalad.support.constraints import EnsureBool
from datalad.support.constraints import EnsureInt
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureListOf
from datalad.support.constraints import EnsureStr
from datalad.utils import on_windows

dirs = AppDirs("datalad", "datalad.org")

subst_rule_docs = """\
A substitution specification is a string with a match and substitution
expression, each following Python's regular expression syntax. Both expressions
are concatenated to a single string with an arbitrary delimiter character. The
delimiter is defined by prefixing the string with the delimiter. Prefix and
delimiter are stripped from the expressions (Example:
",^http://(.*)$,https://\\1").  This setting can be defined multiple times.
Substitutions will be applied incrementally, in order of their definition. The
first substitution in such a series must match, otherwise no further
substitutions in a series will be considered. However, following the first
match all further substitutions in a series are processed, regardless whether
intermediate expressions match or not."""

definitions = {
    'datalad.clone.url-substitute.github': {
        'ui': ('question', {
               'title': 'GitHub URL substitution rule',
               'text': 'Mangling for GitHub-related URL. ' + subst_rule_docs
        }),
        'destination': 'global',
        'default': (
            # take any github project URL apart into <org>###<identifier>
            r',https?://github.com/([^/]+)/(.*)$,\1###\2',
            # replace any (back)slashes with a single dash
            r',[/\\]+,-',
            # replace any whitespace (include urlquoted variant)
            # with a single underscore
            r',\s+|(%2520)+|(%20)+,_',
            # rebuild functional project URL
            r',([^#]+)###(.*),https://github.com/\1/\2',
        )
    },
    # TODO this one should migrate to the datalad-osf extension. however, right
    # now extensions cannot provide default configuration
    # https://github.com/datalad/datalad/issues/5769
    'datalad.clone.url-substitute.osf': {
        'ui': ('question', {
               'title': 'Open Science Framework URL substitution rule',
               'text': 'Mangling for OSF-related URLs. ' + subst_rule_docs
        }),
        'destination': 'global',
        'default': (
            # accept browser-provided URL and convert to those accepted by
            # the datalad-osf extension
            r',^https://osf.io/([^/]+)[/]*$,osf://\1',
        )
    },
    # this is actually used in downloaders, but kept cfg name original
    'datalad.crawl.cache': {
        'ui': ('yesno', {
               'title': 'Crawler download caching',
               'text': 'Should the crawler cache downloaded files?'}),
        'destination': 'local',
        'type': bool,
    },
    # this is actually used in downloaders, but kept cfg name original
    'datalad.credentials.force-ask': {
        'ui': ('yesno', {
               'title': 'Force (re-)entry of credentials',
               'text': 'Should DataLad prompt for credential (re-)entry? This '
                       'can be used to update previously stored credentials.'}),
        'type': bool,
        'default': False,
    },
    'datalad.externals.nda.dbserver': {
        'ui': ('question', {
               'title': 'NDA database server',
               'text': 'Hostname of the database server'}),
        'destination': 'global',
        # Development one is https://development.nimhda.org
        'default': 'https://nda.nih.gov/DataManager/dataManager',
    },
    'datalad.locations.cache': {
        'ui': ('question', {
               'title': 'Cache directory',
               'text': 'Where should datalad cache files?'}),
        'destination': 'global',
        'default_fn': lambda: dirs.user_cache_dir,
    },
    'datalad.locations.default-dataset': {
        'ui': ('question', {
               'title': 'Default dataset path',
               'text': 'Where should datalad should look for (or install) a '
                       'default dataset?'}),
        'destination': 'global',
        'default_fn': lambda: opj(expanduser('~'), 'datalad'),
    },
    'datalad.locations.locks': {
        'ui': ('question', {
               'title': 'Lockfile directory',
               'text': 'Where should datalad store lock files?'}),
        'destination': 'global',
        'default_fn': lambda: opj(dirs.user_cache_dir, 'locks')
    },
    'datalad.locations.sockets': {
        'ui': ('question', {
               'title': 'Socket directory',
               'text': 'Where should datalad store socket files?'}),
        'destination': 'global',
        'default_fn': lambda: opj(dirs.user_cache_dir, 'sockets'),
    },
    'datalad.locations.system-procedures': {
        'ui': ('question', {
               'title': 'System procedure directory',
               'text': 'Where should datalad search for system procedures?'}),
        'destination': 'global',
        'default_fn': lambda: opj(dirs.site_config_dir, 'procedures'),
    },
    'datalad.locations.user-procedures': {
        'ui': ('question', {
               'title': 'User procedure directory',
               'text': 'Where should datalad search for user procedures?'}),
        'destination': 'global',
        'default_fn': lambda: opj(dirs.user_config_dir, 'procedures'),
    },
    'datalad.locations.extra-procedures': {
        'ui': ('question', {
            'title': 'Extra procedure directory',
            'text': 'Where should datalad search for some additional procedures?'}),
        'destination': 'global',
    },
    'datalad.locations.dataset-procedures': {
        'ui': ('question', {
               'title': 'Dataset procedure directory',
               'text': 'Where should datalad search for dataset procedures (relative to a dataset root)?'}),
        'destination': 'dataset',
        'default': opj('.datalad', 'procedures'),
    },
    'datalad.exc.str.tblimit': {
        'ui': ('question', {
               'title': 'This flag is used by datalad to cap the number of traceback steps included in exception logging and result reporting to DATALAD_EXC_STR_TBLIMIT of pre-processed entries from traceback.'}),
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
    'datalad.github.token-note': {
        'ui': ('question', {
            'title': 'Github token note',
            'text': 'Description for a Personal access token to generate.'}),
        'default': 'DataLad',
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
    'datalad.tests.setup.testrepos': {
        'ui': ('question', {
            'title': 'Pre-creates repositories for @with_testrepos within setup_package'}),
        'type': EnsureBool(),
        'default': False,
    },
    'datalad.tests.temp.dir': {
        'ui': ('question', {
               'title': 'Create a temporary directory at location specified by this flag. It is used by tests to create a temporary git directory while testing git annex archives etc'}),
        'type': EnsureStr(),
        'default_fn': lambda: environ.get('TMPDIR'),
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
    'datalad.tests.cache': {
        'ui': ('question', {
            'title': 'Cache directory for tests',
            'text': 'Where should datalad cache test files?'}),
        'destination': 'global',
        'default_fn': lambda: opj(dirs.user_cache_dir, 'tests')
    },
    'datalad.log.level': {
        'ui': ('question', {
            'title': 'Used for control the verbosity of logs printed to '
                     'stdout while running datalad commands/debugging'}),
    },
    'datalad.log.result-level': {
        'ui': ('question', {
               'title': 'Log level for command result messages',
               'text': "If 'match-status', it will log 'impossible' "
                       "results as a warning, 'error' results as errors, and "
                       "everything else as 'debug'. Otherwise the indicated "
                       "log-level will be used for all such messages"}),
        'type': EnsureChoice('debug', 'info', 'warning', 'error',
                             'match-status'),
        'default': 'debug',
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
               'title': 'Whether to log stdout and stderr for executed commands',
               'text': 'When enabled, setting the log level to 5 '
                       'should catch all execution output, '
                       'though some output may be logged at higher levels'}),
        'default': False,
        'type': EnsureBool(),
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
    'datalad.ssh.identityfile': {
        'ui': ('question', {
               'title': "If set, pass this file as ssh's -i option."}),
        'destination': 'global',
        'default': None,
    },
    'datalad.ssh.multiplex-connections': {
        'ui': ('question', {
               'title': "Whether to use a single shared connection for multiple SSH processes aiming at the same target."}),
        'destination': 'global',
        'default': not on_windows,
        'type': EnsureBool(),
    },
    'datalad.annex.retry': {
        'ui': ('question',
               {'title': 'Value for annex.retry to use for git-annex calls',
                'text': 'On transfer failure, annex.retry (sans "datalad.") '
                        'controls the number of times that git-annex retries. '
                        'DataLad will call git-annex with annex.retry set '
                        'to the value here unless the annex.retry '
                        'is explicitly configured'}),
        'type': EnsureInt(),
        'default': 3,
    },
    'datalad.repo.backend': {
        'ui': ('question', {
               'title': 'git-annex backend',
               'text': 'Backend to use when creating git-annex repositories'}),
        'default': 'MD5E',
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
        'default': 8,
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
        'default': 'anything',
    },
    'datalad.runtime.max-annex-jobs': {
        'ui': ('question', {
               'title': 'Maximum number of git-annex jobs to request when "jobs" option set to "auto" (default)',
               'text': 'Set this value to enable parallel annex jobs that may speed up certain operations (e.g. get file content). The effective number of jobs will not exceed the number of available CPU cores (or 3 if there is less than 3 cores).'}),
        'type': EnsureInt(),
        'default': 1,
    },
    'datalad.runtime.max-jobs': {
        'ui': ('question', {
            'title': 'Maximum number of jobs DataLad can run in "parallel"',
            'text': 'Set this value to enable parallel multi-threaded DataLad jobs that may speed up certain '
                    'operations, in particular operation across multiple datasets (e.g., install multiple '
                    'subdatasets, etc).'}),
        'type': EnsureInt(),
        'default': 1,
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
    'datalad.runtime.stalled-external': {
        'ui': ('question', {
            'title': 'Behavior for handing external processes',
            'text': 'What to do with external processes if they do not finish in some minimal reasonable time. '
                    'If "abandon", datalad would proceed without waiting for external process to exit. '
                    'ATM applies only to batched git-annex processes. Should be changed with caution.'}),
        'type': EnsureChoice('wait', 'abandon'),
        'default': 'wait',
    },
    'datalad.search.indexercachesize': {
        'ui': ('question', {
               'title': 'Maximum cache size for search index (per process)',
               'text': 'Actual memory consumption can be twice as high as this value in MB (one process per CPU is used)'}),
        'default': 256,
        'type': EnsureInt(),
    },
    'datalad.ui.progressbar': {
        'ui': ('question', {
            'title': 'UI progress bars',
            'text': 'Default backend for progress reporting'}),
        'default': None,
        'type': EnsureChoice('tqdm', 'tqdm-ipython', 'log', 'none'),
    },
    'datalad.ui.color': {
        'ui': ('question', {
            'title': 'Colored terminal output',
            'text': 'Enable or disable ANSI color codes in outputs; "on" overrides NO_COLOR environment variable'}),
        'default': 'auto',
        'type': EnsureChoice('on', 'off', 'auto'),
    },
    'datalad.ui.suppress-similar-results': {
        'ui': ('question', {
            'title': 'Suppress rendering of similar repetitive results',
            'text': "If enabled, after a certain number of subsequent "
                    "results that are identical regarding key properties, "
                    "such as 'status', 'action', and 'type', additional "
                    "similar results are not rendered by the common result "
                    "renderer anymore. Instead, a count "
                    "of suppressed results is displayed. If disabled, or "
                    "when not running in an interactive terminal, all results "
                    "are rendered."}),
        'default': True,
        'type': EnsureBool(),
    },
    'datalad.ui.suppress-similar-results-threshold': {
        'ui': ('question', {
            'title': 'Threshold for suppressing similar repetitive results',
            'text': "Minimum number of similar results to occur before "
                    "suppression is considered. "
                    "See 'datalad.ui.suppress-similar-results' for more "
                    "information."}),
        'default': 10,
        'type': EnsureInt(),
    },
    'datalad.save.no-message': {
        'ui': ('question', {
            'title': 'Commit message handling',
            'text': 'When no commit message was provided: '
                    'attempt to obtain one interactively (interactive); '
                    'or use a generic commit message (generic). '
                    'NOTE: The interactive option is experimental. The '
                    'behavior may change in backwards-incompatible ways.'}),
        'default': 'generic',
        'type': EnsureChoice('interactive', 'generic'),
    },
    'datalad.install.inherit-local-origin': {
        'ui': ('question', {
            'title': 'Inherit local origin of dataset source',
            'text': "If enabled, a local 'origin' remote of a local dataset "
                    "clone source is configured as an 'origin-2' remote "
                    "to make its annex automatically available. The process "
                    "is repeated recursively for any further qualifying "
                    "'origin' dataset thereof."
                    "Note that if clone.defaultRemoteName is configured "
                    "to use a name other than 'origin', that name will be "
                    "used instead."}),
        'default': True,
        'type': EnsureBool(),
    },
}


def compute_cfg_defaults():
    """Compute dynamic defaults for configuration options.

    These are options that depend on things like $HOME that change under our
    testing setup.
    """
    for key, value in definitions.items():
        def_fn = value.get("default_fn")
        if def_fn:
            value['default'] = def_fn()


compute_cfg_defaults()
