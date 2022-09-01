# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Common configuration options

"""

__docformat__ = 'restructuredtext'

from collections.abc import Mapping
import logging
from os import environ
from os.path import expanduser
from os.path import join as opj
import time

from platformdirs import AppDirs

from datalad.support.constraints import (
    EnsureBool,
    EnsureChoice,
    EnsureInt,
    EnsureFloat,
    EnsureListOf,
    EnsureNone,
    EnsureStr,
)
from datalad.utils import on_windows

lgr = logging.getLogger('datalad.interface.common_cfg')
dirs = AppDirs("datalad", "datalad.org")


class _NotGiven():
    pass


class _ConfigDefinitions(Mapping):
    """A container for configuration definitions

    This class implements the parts of the dictionary interface
    required to work as a drop-in replacement for the legacy
    data structure used for configuration definitions prior
    DataLad 0.16.

    .. note::

      This is an internal helper that may change at any time without
      prior notice.
    """
    def __init__(self):
        self._defs = {
            k: _ConfigDefinition(**v) for k, v in _definitions.items()
            if v is not _NotGiven
        }

    def get(self, *args):
        return self._defs.get(*args)

    def keys(self):
        return self._defs.keys()

    def items(self):
        return self._defs.items()

    def __setitem__(self, key, value):
        self._defs.__setitem__(key, value)

    def __getitem__(self, key):
        return self._defs.__getitem__(key)

    def __contains__(self, key):
        return self._defs.__contains__(key)

    def __iter__(self):
        return self._defs.__iter__()

    def __len__(self):
        return self._defs.__len__()


class _ConfigDefinition(Mapping):
    """A single configuration definition

    This class implements the parts of the dictionary interface
    required to work as a drop-in replacement for the legacy
    data structure used for a configuration definition prior
    DataLad 0.16.

    Moreover, it implement lazy evaluation of default values,
    when a 'default_fn' property is given.

    .. note::

      This is an internal helper that may change at any time without
      prior notice.
    """
    def __init__(self, **kwargs):
        # just take it, no validation on ingestions for max speed
        self._props = kwargs

    def __getitem__(self, prop):
        if prop == 'default' \
                and 'default' not in self._props \
                and 'default_fn' in self._props:
            default = self._props["default_fn"]()
            self._props['default'] = default
            return default
        return self._props[prop]

    def __setitem__(self, key, val):
        self._props.__setitem__(key, val)

    def get(self, prop, default=None):
        try:
            return self.__getitem__(prop)
        except KeyError:
            return default

    def __contains__(self, prop):
        if prop == 'default':
            return 'default' in self._props or 'default_fn' in self._props
        return self._props.__contains__(prop)

    def __str__(self):
        return self._props.__str__()

    def __repr__(self):
        return self._props.__repr__()

    def __iter__(self):
        return self._props.__iter__()

    def __len__(self):
        return self._props.__len__()

    def update(self, *args, **kwargs):
        self._props.update(*args, **kwargs)


def get_default_ssh():
    from datalad.utils import on_windows
    from pathlib import Path

    if on_windows:
        windows_openssh_path = \
            environ.get("WINDIR", r"C:\Windows") + r"\System32\OpenSSH\ssh.exe"
        if Path(windows_openssh_path).exists():
            return windows_openssh_path
    return "ssh"


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


_definitions = {
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
        'type': EnsureBool(),
    },
    # this is actually used in downloaders, but kept cfg name original
    'datalad.credentials.force-ask': {
        'ui': ('yesno', {
               'title': 'Force (re-)entry of credentials',
               'text': 'Should DataLad prompt for credential (re-)entry? This '
                       'can be used to update previously stored credentials.'}),
        'type': EnsureBool(),
        'default': False,
    },
    'datalad.credentials.githelper.noninteractive':{
        'ui': ('yesno', {
               'title': 'Non-interactive mode for git-credential helper',
               'text': 'Should git-credential-datalad operate in '
                       'non-interactive mode? This would mean to not ask for '
                       'user confirmation when storing new '
                       'credentials/provider configs.'}),
        'type': bool,
        'default': False,
    },
    'datalad.extensions.load': {
        'ui': ('question', {
               'title': 'DataLad extension packages to load',
               'text': 'Indicate which extension packages should be loaded '
                       'unconditionally on CLI startup or on importing '
                       "'datalad.[core]api'. This enables the "
                       'respective extensions to customize DataLad with '
                       'functionality and configurability outside the '
                       'scope of extension commands. For merely running '
                       'extension commands it is not necessary to load them '
                       'specifically'}),
        'destination': 'global',
        'default': None,
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
            'title': 'GitHub token note',
            'text': 'Description for a Personal access token to generate.'}),
        'default': 'DataLad',
    },
    'datalad.tests.nonetwork': {
        'ui': ('yesno', {
               'title': 'Skips network tests completely if this flag is set, Examples include test for S3, git_repositories, OpenfMRI, etc'}),
        'type': EnsureBool(),
    },
    'datalad.tests.nonlo': {
        'ui': ('question', {
               'title': 'Specifies network interfaces to bring down/up for testing. Currently used by Travis CI.'}),
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
               'title': 'Includes a compact traceback in a log message, with '
                        'generic components removed. '
                        'This setting is only in effect when given as an '
                        'environment variable DATALAD_LOG_TRACEBACK. '
                        'An integer value specifies the maximum traceback '
                        'depth to be considered. '
                        'If set to "collide", a common traceback prefix '
                        'between a current traceback and a previously logged '
                        'traceback is replaced with "…" (maximum depth 100).'}),
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
    'datalad.ssh.try-use-annex-bundled-git': {
        'ui': ('question', {
               'title': "Whether to attempt adjusting the PATH in a remote "
                        "shell to include Git binaries located in a detected "
                        "git-annex bundle",
               'text': "If enabled, this will be a 'best-effort' attempt that "
                       "only supports remote hosts with a Bourne shell and "
                       "the `which` command available. The remote PATH must "
                       "already contain a git-annex installation. "
                       "If git-annex is not found, or the detected git-annex "
                       "does not have a bundled Git installation, detection "
                       "failure will not result in an error, but only slow "
                       "remote execution by one-time sensing overhead per "
                       "each opened connection."}),
        'destination': 'global',
        'default': False,
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
    'datalad.runtime.max-batched': {
        'ui': ('question', {
            'title': 'Maximum number of batched commands to run in parallel',
            'text': 'Automatic cleanup of batched commands will try to keep at most this many commands running.'}),
        'type': EnsureInt(),
        'default': 20,
    },
    'datalad.runtime.max-inactive-age': {
        'ui': ('question', {
            'title': 'Maximum time (in seconds) a batched command can be'
                     ' inactive before it is eligible for cleanup',
            'text': 'Automatic cleanup of batched commands will consider an'
                    ' inactive command eligible for cleanup if more than this'
                    ' many seconds have transpired since the command\'s last'
                    ' activity.'}),
        'type': EnsureInt(),
        'default': 60,
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
    'datalad.save.windows-compat-warning': {
        'ui': ('question', {
            'title': 'Action when Windows-incompatible file names are saved',
            'text': "Certain characters or names can make file names "
                    "incompatible with Windows. If such files are saved "
                    "'warning' will alert users with a log message, 'error' "
                    "will yield an 'impossible' result, and 'none' will "
                    "ignore the incompatibility."}),
        'type': EnsureChoice('warning', 'error', 'none'),
        'default': 'warning',

    },
    'datalad.source.epoch': {
        'ui': ('question', {
            'title': 'Datetime epoch to use for dates in built materials',
            'text': "Datetime to use for reproducible builds. Originally introduced "
                    "for Debian packages to interface SOURCE_DATE_EPOCH described at "
                    "https://reproducible-builds.org/docs/source-date-epoch/ ."
                    "By default - current time"
        }),
        'type': EnsureFloat(),
        'default': time.time(),

    },
    'datalad.ssh.executable': {
        'ui': ('question', {
            'title': "Name of ssh executable for 'datalad sshrun'",
            'text': "Specifies the name of the ssh-client executable that"
                    "datalad will use. This might be an absolute "
                    "path. On Windows systems it is currently by default set "
                    "to point to the ssh executable of OpenSSH for Windows, "
                    "if OpenSSH for Windows is installed. On other systems it "
                    "defaults to 'ssh'."}),
        'destination': 'global',
        'type': EnsureStr(),
        'default_fn': get_default_ssh,
    }
}

definitions = _ConfigDefinitions()
