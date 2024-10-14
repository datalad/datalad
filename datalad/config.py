# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""

import json
import logging
import os
import re
import threading
import warnings
from collections import namedtuple
from functools import (
    lru_cache,
    wraps,
)
from pathlib import Path

from fasteners import InterProcessLock

import datalad
from datalad.consts import DATASET_CONFIG_FILE
from datalad.runner import (
    CommandError,
    GitRunner,
    KillOutput,
    StdOutErrCapture,
)
from datalad.utils import (
    getpwd,
    on_windows,
)

lgr = logging.getLogger('datalad.config')

# git-config key syntax with a section and a subsection
# see git-config(1) for syntax details
cfg_k_regex = re.compile(r'([a-zA-Z0-9-.]+\.[^\0\n]+)$', flags=re.MULTILINE)
# identical to the key regex, but with an additional group for a
# value in a null-delimited git-config dump
cfg_kv_regex = re.compile(
    r'([a-zA-Z0-9-.]+\.[^\0\n]+)\n(.*)$',
    flags=re.MULTILINE | re.DOTALL
)
cfg_section_regex = re.compile(r'(.*)\.[^.]+')
cfg_sectionoption_regex = re.compile(r'(.*)\.([^.]+)')


_scope_reload_doc = """
        scope : {'branch', 'local', 'global', 'override'}, optional
          Indicator which configuration file to modify. 'branch' indicates the
          persistent configuration in .datalad/config of a dataset; 'local'
          the configuration of a dataset's Git repository in .git/config;
          'global' refers to the general configuration that is not specific to
          a single repository (usually in $USER/.gitconfig); 'override'
          limits the modification to the ConfigManager instance, and the
          assigned value overrides any setting from any other source.
          Note: 'dataset' is being DEPRECATED in favor of 'branch'.
        where: {'branch', 'local', 'global', 'override'}, optional
          DEPRECATED, use 'scope'.
        reload : bool
          Flag whether to reload the configuration from file(s) after
          modification. This can be disable to make multiple sequential
          modifications slightly more efficient.""".lstrip()

# Selection of os.stat_result fields we care to collect/compare to judge
# on either file has changed to warrant reload of configuration.
_stat_result = namedtuple('_stat_result', 'st_ino st_size st_ctime st_mtime')


# we cannot import external_versions here, as the cfg comes before anything
# and we would have circular imports
@lru_cache()
def get_git_version(runner=None):
    """Return version of available git"""
    runner = runner or GitRunner()
    return runner.run('git version'.split(),
                      protocol=StdOutErrCapture)['stdout'].split()[2]


def _scope_reload(obj):
    """Helper decorator to simplify providing repetitive docstring"""
    obj.__doc__ = obj.__doc__ % _scope_reload_doc
    return obj


#
# TODO: remove when deprecated 'where' is removed. Some time >= 0.17
#
def _where_to_scope(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'where' in kwargs:
            if 'scope' in kwargs:
                raise ValueError("Do not specify both 'scope' and DEPRECATED 'where'")
            kwargs = kwargs.copy()
            where = kwargs.pop('where')
            if where == 'dataset':
                warnings.warn("'where=\"dataset\"' is deprecated, use 'scope=\"branch\"' instead",
                              DeprecationWarning)
                where = 'branch'
            else:
                warnings.warn("'where' is deprecated, use 'scope' instead",
                              DeprecationWarning)
            kwargs['scope'] = where
        return func(*args, **kwargs)
    return wrapper


def parse_gitconfig_dump(dump, cwd=None, multi_value=True):
    """Parse a dump-string from `git config -z --list`

    This parser has limited support for discarding unrelated output
    that may contaminate the given dump. It does so performing a
    relatively strict matching of configuration key syntax, and discarding
    lines in the output that are not valid git-config keys.

    There is also built-in support for parsing outputs generated
    with --show-origin (see return value).

    Parameters
    ----------
    dump : str
      Null-byte separated output
    cwd : path-like, optional
      Use this absolute path to convert relative paths for origin reports
      into absolute paths. By default, the process working directory
      PWD is used.
    multi_value : bool, optional
      If True, report values from multiple specifications of the
      same key as a tuple of values assigned to this key. Otherwise,
      the last configuration is reported.

    Returns:
    --------
    dict, set
      Configuration items are returned as key/value pairs in a dictionary.
      The second tuple-item will be a set of identifiers comprising all
      source files/blobs, if origin information was included
      in the dump (--show-origin). An empty set is returned otherwise.
      For actual files a Path object is included in the set, for a git-blob
      a Git blob ID prefixed with 'blob:' is reported.
    """
    cwd = Path(getpwd() if cwd is None else cwd)
    dct = {}
    fileset = set()
    for line in dump.split('\0'):
        # line is a null-delimited chunk
        k = None
        # in anticipation of output contamination, process within a loop
        # where we can reject non syntax compliant pieces
        while line:
            if line.startswith('file:') or line.startswith('blob:'):
                fileset.add(line)
                break
            if line.startswith('command line:'):
                # no origin that we could as a pathobj
                break
            # try getting key/value pair from the present chunk
            k, v = _gitcfg_rec_to_keyvalue(line)
            if k is not None:
                # we are done with this chunk when there is a good key
                break
            # discard the first line and start over
            ignore, line = line.split('\n', maxsplit=1)
            lgr.debug('Non-standard git-config output, ignoring: %s', ignore)
        if not k:
            # nothing else to log, all ignored dump was reported before
            continue
        # multi-value reporting
        present_v = dct.get(k, None)
        if present_v is None or not multi_value:
            dct[k] = v
        else:
            if isinstance(present_v, tuple):
                dct[k] = present_v + (v,)
            else:
                dct[k] = (present_v, v)
    # take blobs with verbatim markup
    origin_blobs = set(f for f in fileset if f.startswith('blob:'))
    # convert file specifications to Path objects with absolute paths
    origin_paths = set(Path(f[5:]) for f in fileset if f.startswith('file:'))
    origin_paths = set(f if f.is_absolute() else cwd / f for f in origin_paths)
    return dct, origin_paths.union(origin_blobs)


# keep alias with previous name for now
_parse_gitconfig_dump = parse_gitconfig_dump


def _gitcfg_rec_to_keyvalue(rec):
    """Helper for parse_gitconfig_dump()

    Parameters
    ----------
    rec: str
      Key/value specification string

    Returns
    -------
    str, str
      Parsed key and value. Key and/or value could be None
      if not syntax-compliant (former) or absent (latter).
    """
    kv_match = cfg_kv_regex.match(rec)
    if kv_match:
        k, v = kv_match.groups()
    elif cfg_k_regex.match(rec):
        # could be just a key without = value, which git treats as True
        # if asked for a bool
        k, v = rec, None
    else:
        # no value, no good key
        k = v = None
    return k, v


def _update_from_env(store):
    overrides = {}
    dct = {}
    for k in os.environ:
        if k == "DATALAD_CONFIG_OVERRIDES_JSON":
            try:
                overrides = json.loads(os.environ[k])
            except json.decoder.JSONDecodeError as exc:
                lgr.warning("Failed to load DATALAD_CONFIG_OVERRIDES_JSON: %s",
                            exc)
        elif k.startswith('DATALAD_'):
            dct[k.replace('__', '-').replace('_', '.').lower()] = os.environ[k]
    if overrides:
        store.update(overrides)
    store.update(dct)


def anything2bool(val):
    if hasattr(val, 'lower'):
        val = val.lower()
    if val in {"off", "no", "false", "0"} or not bool(val):
        return False
    elif val in {"on", "yes", "true", True} \
            or (hasattr(val, 'isdigit') and val.isdigit() and int(val)) \
            or isinstance(val, int) and val:
        return True
    else:
        raise TypeError(
            "Got value %s which could not be interpreted as a boolean"
            % repr(val))


class ConfigManager(object):
    """Thin wrapper around `git-config` with support for a dataset configuration.

    The general idea is to have an object that is primarily used to read/query
    configuration option.  Upon creation, current configuration is read via one
    (or max two, in the case of the presence of dataset-specific configuration)
    calls to `git config`.  If this class is initialized with a Dataset
    instance, it supports reading and writing configuration from
    ``.datalad/config`` inside a dataset too. This file is committed to Git and
    hence useful to ship certain configuration items with a dataset.

    The API aims to provide the most significant read-access API of a
    dictionary, the Python ConfigParser, and GitPython's config parser
    implementations.

    This class is presently not capable of efficiently writing multiple
    configurations items at once.  Instead, each modification results in a
    dedicated call to `git config`. This author thinks this is OK, as he
    cannot think of a situation where a large number of items need to be
    written during normal operation.

    Each instance carries a public `overrides` attribute. This dictionary
    contains variables that override any setting read from a file. The overrides
    are persistent across reloads.

    Any DATALAD_* environment variable is also presented as a configuration
    item. Settings read from environment variables are not stored in any of the
    configuration files, but are read dynamically from the environment at each
    `reload()` call. Their values take precedence over any specification in
    configuration files, and even overrides.

    Parameters
    ----------
    dataset : Dataset, optional
      If provided, all `git config` calls are executed in this dataset's
      directory. Moreover, any modifications are, by default, directed to
      this dataset's configuration file (which will be created on demand)
    overrides : dict, optional
      Variable overrides, see general class documentation for details.
    source : {'any', 'local', 'branch', 'branch-local'}, optional
      Which sources of configuration setting to consider. If 'branch',
      configuration items are only read from a dataset's persistent
      configuration file in current branch, if any is present
      (the one in ``.datalad/config``, not
      ``.git/config``); if 'local', any non-committed source is considered
      (local and global configuration in Git config's terminology);
      if 'branch-local', persistent configuration in current dataset branch
      and local, but not global or system configuration are considered; if 'any'
      all possible sources of configuration are considered.
      Note: 'dataset' and 'dataset-local' are deprecated in favor of 'branch'
      and 'branch-local'.
    """
    # Lock for running changing operation across multiple threads.
    # Since config itself to the same path could
    # potentially be created independently in multiple threads, and we might be
    # modifying global config as well, making lock static should not allow more than
    # one thread to  write at a time, even if to different repositories.
    _run_lock = threading.Lock()

    def __init__(self, dataset=None, overrides=None, source='any'):
        # TODO: remove along with the removal of deprecated 'where'
        if source in ('dataset', 'dataset-local'):
            source_new = source.replace('dataset', 'branch')
            warnings.warn("'source=\"%s\"' is deprecated, use 'source=\"%s\"' instead"
                          % (source, source_new),
                          DeprecationWarning)
            source = source_new

        if source not in ('any', 'local', 'branch', 'branch-local'):
            raise ValueError(
                'Unknown ConfigManager(source=) setting: {}'.format(source))
        store = dict(
            # store in a simple dict
            # no subclassing, because we want to be largely read-only, and implement
            # config writing separately
            cfg={},
            # track the files that jointly make up the config in this store
            files=set(),
            # and their modification times to be able to avoid needless unforced reloads
            stats=None,
        )
        self._stores = dict(
            # populated with info from git
            git=store,
            # only populated with info from committed dataset config
            branch=store.copy(),
        )
        # merged representation (the only one that existed pre datalad 0.14)
        # will be built on initial reload
        self._merged_store = {}

        self._repo_dot_git = None
        self._repo_pathobj = None
        if dataset:
            if hasattr(dataset, 'dot_git'):
                # `dataset` is actually a Repo instance
                self._repo_dot_git = dataset.dot_git
                self._repo_pathobj = dataset.pathobj
            elif dataset.repo:
                self._repo_dot_git = dataset.repo.dot_git
                self._repo_pathobj = dataset.repo.pathobj

        self._config_cmd = ['git', 'config']
        # public dict to store variables that always override any setting
        # read from a file
        # `hasattr()` is needed because `datalad.cfg` is generated upon first module
        # import, hence when this code runs first, there cannot be any config manager
        # to inherit from
        self.overrides = datalad.cfg.overrides.copy() if hasattr(datalad, 'cfg') else {}
        if overrides is not None:
            self.overrides.update(overrides)
        if dataset is None:
            if source in ('branch', 'branch-local'):
                raise ValueError(
                    'ConfigManager configured to read from a branch of a dataset only, '
                    'but no dataset given')
            # The caller didn't specify a repository. Unfortunately there is
            # no known way to tell git to ignore possible local git repository,
            # and unsetting of --git-dir could cause other problems.
            # See https://lore.kernel.org/git/YscCKuoDPBbs4iPX@lena.dartmouth.edu/T/ .
            # Setting the git directory to /dev/null or on Windows analogous nul file
            # (could be anywhere, see https://stackoverflow.com/a/27773642/1265472)
            # see allow to achieve the goal to prevent a repository in the current
            # working directory from leaking configuration into the output.
            nul = 'b:\\nul' if on_windows else '/dev/null'
            self._config_cmd = ['git', f'--git-dir={nul}', 'config']

        self._src_mode = source
        run_kwargs = dict()
        self._runner = None
        if dataset is not None:
            if hasattr(dataset, '_git_runner'):
                # `dataset` is actually a Repo instance
                self._runner = dataset._git_runner
            elif dataset.repo:
                self._runner = dataset.repo._git_runner
            else:
                # make sure we run the git config calls in the dataset
                # to pick up the right config files
                run_kwargs['cwd'] = dataset.path
        if self._runner is None:
            self._runner = GitRunner(**run_kwargs)

        self.reload(force=True)

    def reload(self, force=False):
        """Reload all configuration items from the configured sources

        If `force` is False, all files configuration was previously read from
        are checked for differences in the modification times. If no difference
        is found for any file no reload is performed. This mechanism will not
        detect newly created global configuration files, use `force` in this case.
        """
        run_args = ['-z', '-l', '--show-origin']

        # update from desired config sources only
        # 2-step strategy:
        #   - load datalad dataset config from dataset
        #   - load git config from all supported by git sources
        # in doing so we always stay compatible with where Git gets its
        # config from, but also allow to override persistent information
        # from dataset locally or globally

        # figure out what needs to be reloaded at all
        to_run = {}
        # committed branch config
        # well, actually not necessarily committed

        if self._src_mode != 'local' and self._repo_pathobj:
            # we have to read the branch config from this existing repo
            if self._repo_dot_git == self._repo_pathobj:
                # this is a bare repo, we go with the default HEAD,
                # if it has a config
                try:
                    # will blow if absent
                    self._runner.run([
                        'git', 'cat-file', '-e', 'HEAD:.datalad/config'],
                        protocol=KillOutput)
                    to_run['branch'] = run_args + [
                        '--blob', 'HEAD:.datalad/config']
                except CommandError:
                    # all good, just no branch config
                    pass
            else:
                # non-bare repo
                # we could use the same strategy as for bare repos, and rely
                # on the committed config, however, for now we must pay off
                # the sins of the past and work with the file at hand
                dataset_cfgfile = self._repo_pathobj / DATASET_CONFIG_FILE
                if dataset_cfgfile.exists() and (
                        force or self._need_reload(self._stores['branch'])):
                    # we have the file and are forced or encourages to (re)load
                    to_run['branch'] = run_args + [
                        '--file', str(dataset_cfgfile)]

        if self._src_mode != 'branch' and (
                force or self._need_reload(self._stores['git'])):
            to_run['git'] = run_args + ['--local'] \
                if self._src_mode == 'branch-local' \
                else run_args

        # reload everything that was found todo
        while to_run:
            store_id, runargs = to_run.popitem()
            self._stores[store_id] = self._reload(runargs)

        # always update the merged representation, even if we did not reload
        # anything from a file. ENV or overrides could change independently
        # start with the commit dataset config
        merged = self._stores['branch']['cfg'].copy()
        # local config always takes precedence
        merged.update(self._stores['git']['cfg'])
        # superimpose overrides
        merged.update(self.overrides)
        # override with environment variables, unless we only want to read the
        # dataset's commit config
        if self._src_mode != 'branch':
            _update_from_env(merged)
        self._merged_store = merged

    def _need_reload(self, store):
        storestats = store['stats']
        if not storestats:
            return True

        # we have read files before
        # check if any file we read from has changed
        curstats = self._get_stats(store)
        return any(curstats[f] != storestats[f] for f in store['files'])

    def _reload(self, run_args):
        # query git-config
        stdout, stderr = self._run(
            run_args,
            protocol=StdOutErrCapture,
            # always expect git-config to output utf-8
            encoding='utf-8',
        )
        store = {}
        store['cfg'], store['files'] = parse_gitconfig_dump(
            stdout, cwd=self._runner.cwd)

        # update stats of config files, they have just been discovered
        # and should still exist
        store['stats'] = self._get_stats(store)
        return store

    def _get_stats(self, store):
        stats = {}
        for f in store['files']:
            if isinstance(f, Path):
                if f.exists():
                    stat = f.stat()
                    stats[f] = _stat_result(
                        stat.st_ino,
                        stat.st_size,
                        stat.st_ctime,
                        stat.st_mtime)
                else:
                    stats[f] = None
            elif f.startswith('blob:'):
                # we record the specific shasum of the blob
                stats[f] = self._runner.run(
                    ['git', 'rev-parse', f[5:]],
                    protocol=StdOutErrCapture)['stdout'].strip()
            else:
                stats[f] = None
        return stats

    @_scope_reload
    @_where_to_scope
    def obtain(self, var, default=None, dialog_type=None, valtype=None,
               store=False, scope=None, reload=True, **kwargs):
        """
        Convenience method to obtain settings interactively, if needed

        A UI will be used to ask for user input in interactive sessions.
        Questions to ask, and additional explanations can be passed directly
        as arguments, or retrieved from a list of pre-configured items.

        Additionally, this method allows for type conversion and storage
        of obtained settings. Both aspects can also be pre-configured.

        Parameters
        ----------
        var : str
          Variable name including any section like `git config` expects them,
          e.g. 'core.editor'
        default : any type
          In interactive sessions and if `store` is True, this default value
          will be presented to the user for confirmation (or modification).
          In all other cases, this value will be silently assigned unless
          there is an existing configuration setting.
        dialog_type : {'question', 'yesno', None}
          Which dialog type to use in interactive sessions. If `None`,
          pre-configured UI options are used.
        store : bool
          Whether to store the obtained value (or default)
        %s
        `**kwargs`
          Additional arguments for the UI function call, such as a question
          `text`.
        """
        # do local import, as this module is import prominently and the
        # could theoretically import all kind of weird things for type
        # conversion
        from datalad.interface.common_cfg import definitions as cfg_defs

        # fetch what we know about this variable
        cdef = cfg_defs.get(var, {})
        # type conversion setup
        if valtype is None and 'type' in cdef:
            valtype = cdef['type']
        if valtype is None:
            valtype = lambda x: x

        # any default?
        if default is None and 'default' in cdef:
            default = cdef['default']

        _value = None
        if var in self:
            # nothing needs to be obtained, it is all here already
            _value = self[var]
        elif store is False and default is not None:
            # nothing will be stored, and we have a default -> no user confirmation
            # we cannot use logging, because we want to use the config to configure
            # the logging
            #lgr.debug('using default {} for config setting {}'.format(default, var))
            _value = default

        if _value is not None:
            # we got everything we need and can exit early
            try:
                return valtype(_value)
            except Exception as e:
                raise ValueError(
                    "value '{}' of existing configuration for '{}' cannot be "
                    "converted to the desired type '{}' ({})".format(
                        _value, var, valtype, e)) from e

        # now we need to try to obtain something from the user
        from datalad.ui import ui

        # configure UI
        dialog_opts = kwargs
        if dialog_type is None:  # no override
            # check for common knowledge on how to obtain a value
            if 'ui' in cdef:
                dialog_type = cdef['ui'][0]
                # pull standard dialog settings
                dialog_opts = cdef['ui'][1]
                # update with input
                dialog_opts.update(kwargs)

        if (not ui.is_interactive or dialog_type is None) and default is None:
            raise RuntimeError(
                "cannot obtain value for configuration item '{}', "
                "not preconfigured, no default, no UI available".format(var))

        if not hasattr(ui, dialog_type):
            raise ValueError("UI '{}' does not support dialog type '{}'".format(
                ui, dialog_type))

        # configure storage destination, if needed
        if store:
            if scope is None and 'destination' in cdef:
                scope = cdef['destination']
            if scope is None:
                raise ValueError(
                    "request to store configuration item '{}', but no "
                    "storage destination specified".format(var))

        # obtain via UI
        dialog = getattr(ui, dialog_type)
        _value = dialog(default=default, **dialog_opts)

        if _value is None:
            # we got nothing
            if default is None:
                raise RuntimeError(
                    "could not obtain value for configuration item '{}', "
                    "not preconfigured, no default".format(var))
            # XXX maybe we should return default here, even it was returned
            # from the UI -- if that is even possible

        # execute type conversion before storing to check that we got
        # something that looks like what we want
        try:
            value = valtype(_value)
        except Exception as e:
            raise ValueError(
                "cannot convert user input `{}` to desired type ({})".format(
                    _value, e)) from e
            # XXX we could consider "looping" until we have a value of proper
            # type in case of a user typo...

        if store:
            # store value as it was before any conversion, needs to be str
            # anyway
            # needs string conversion nevertheless, because default could come
            # in as something else
            self.add(var, '{}'.format(_value), scope=scope, reload=reload)
        return value

    def __repr__(self):
        # give full list of all tracked config files, plus overrides
        return "ConfigManager({}{})".format(
            [str(p) for p in self._stores['branch']['files'].union(
                self._stores['git']['files'])],
            ', overrides={!r}'.format(self.overrides) if self.overrides else '',
        )

    def __str__(self):
        # give path of dataset, if there is any, plus overrides
        return "ConfigManager({}{})".format(
            self._repo_pathobj if self._repo_pathobj else '',
            'with overrides' if self.overrides else '',
        )

    #
    # Compatibility with dict API
    #
    def __len__(self):
        return len(self._merged_store)

    def __getitem__(self, key):
        return self._merged_store.__getitem__(key)

    def __contains__(self, key):
        return self._merged_store.__contains__(key)

    def keys(self):
        """Returns list of configuration item names"""
        return self._merged_store.keys()

    # XXX should this be *args?
    def get(self, key, default=None, get_all=False):
        """D.get(k[,d]) -> D[k] if k in D, else d.  d defaults to None.

        Parameters
        ----------
        default : optional
          Value to return when key is not present. `None` by default.
        get_all : bool, optional
          If True, return all values of multiple identical configuration keys.
          By default only the last specified value is returned.
        """
        try:
            val = self[key]
            if get_all or not isinstance(val, tuple):
                return val
            else:
                return val[-1]
        except KeyError:
            # return as-is, default could be a tuple, hence do not subject to
            # get_all processing
            return default

    def get_from_source(self, source, key, default=None):
        """Like get(), but a source can be specific.

        If `source` is 'branch', only the committed configuration is queried,
        overrides are applied. In the case of 'local', the committed
        configuration is ignored, but overrides and configuration from
        environment variables are applied as usual.
        """
        # TODO: remove along with the removal of deprecated 'where'
        if source == 'dataset':
            warnings.warn("'source=\"%s\"' is deprecated, use 'source=\"%s\"' instead"
                          % (source, 'branch'),
                          DeprecationWarning)
            source = 'branch'
        if source not in ('branch', 'local'):
            raise ValueError("source must be 'branch' or 'local'")
        if source == 'branch':
            return self.overrides.get(
                key,
                self._stores['branch']['cfg'].get(
                    key,
                    default))
        else:
            if key not in self._stores['branch']['cfg']:
                # the key is not in the committed config, hence we can
                # just report based on the merged representation
                return self.get(key, default)
            else:
                # expensive case, rebuild a config without the committed
                # dataset config contributing
                env = {}
                _update_from_env(env)
                return env.get(
                    key,
                    self.overrides.get(
                        key,
                        self._stores['git']['cfg'].get(
                            key,
                            default)))

    #
    # Compatibility with ConfigParser API
    #
    def sections(self):
        """Returns a list of the sections available"""
        return list(set([cfg_section_regex.match(k).group(1) for k in self._merged_store]))

    def options(self, section):
        """Returns a list of options available in the specified section."""
        opts = []
        for k in self._merged_store:
            sec, opt = cfg_sectionoption_regex.match(k).groups()
            if sec == section:
                opts.append(opt)
        return opts

    def has_section(self, section):
        """Indicates whether a section is present in the configuration"""
        for k in self._merged_store:
            if k.startswith(section):
                return True
        return False

    def has_option(self, section, option):
        """If the given section exists, and contains the given option"""
        for k in self._merged_store:
            sec, opt = cfg_sectionoption_regex.match(k).groups()
            if sec == section and opt == option:
                return True
        return False

    def _get_type(self, typefn, section, option):
        key = '.'.join([section, option])
        # Mimic the handling of get_value(..., default=None), while still going
        # through get() in order to get its default tuple handling.
        if key not in self:
            raise KeyError(key)
        return typefn(self.get(key))

    def getint(self, section, option):
        """A convenience method which coerces the option value to an integer"""
        return self._get_type(int, section, option)

    def getfloat(self, section, option):
        """A convenience method which coerces the option value to a float"""
        return self._get_type(float, section, option)

    def getbool(self, section, option, default=None):
        """A convenience method which coerces the option value to a bool

        Values "on", "yes", "true" and any int!=0 are considered True
        Values which evaluate to bool False, "off", "no", "false" are considered
        False
        TypeError is raised for other values.
        """
        key = '.'.join([section, option])
        # Mimic the handling of get_value(..., default=None), while still going
        # through get() in order to get its default tuple handling.
        if default is None and key not in self:
            raise KeyError(key)
        val = self.get(key, default=default)
        if val is None:  # no value at all, git treats it as True
            return True
        return anything2bool(val)

    # this is a hybrid of ConfigParser and dict API
    def items(self, section=None):
        """Return a list of (name, value) pairs for each option

        Optionally limited to a given section.
        """
        if section is None:
            return self._merged_store.items()
        return [(k, v) for k, v in self._merged_store.items()
                if cfg_section_regex.match(k).group(1) == section]

    #
    # Compatibility with GitPython's ConfigParser
    #
    def get_value(self, section, option, default=None):
        """Like `get()`, but with an optional default value

        If the default is not None, the given default value will be returned in
        case the option did not exist. This behavior imitates GitPython's
        config parser.
        """
        try:
            return self['.'.join((section, option))]
        except KeyError as e:
            # this strange dance is needed because gitpython does it this way
            if default is not None:
                return default
            else:
                raise e

    #
    # Modify configuration (proxy respective git-config call)
    #
    @_scope_reload
    def _run(self, args, scope=None, reload=False, **kwargs):
        """Centralized helper to run "git config" calls

        Parameters
        ----------
        args : list
          Arguments to pass for git config
        %s
        **kwargs
          Keywords arguments for Runner's call
        """
        if scope:
            args = self._get_location_args(scope) + args
        if '-l' in args:
            # we are just reading, no need to reload, no need to lock
            out = self._runner.run(self._config_cmd + args, **kwargs)
            return out['stdout'], out['stderr']

        # all other calls are modifications
        if '--file' in args:
            # all paths we are passing are absolute
            custom_file = Path(args[args.index('--file') + 1])
            custom_file.parent.mkdir(exist_ok=True)
        lockfile = None
        if self._repo_dot_git and ('--local' in args or '--file' in args):
            # modification of config in a dataset
            lockfile = self._repo_dot_git / 'config.dataladlock'
        else:
            # follow pattern in downloaders for lockfile location
            lockfile = Path(self.obtain('datalad.locations.locks')) \
                       / 'gitconfig.lck'

        with ConfigManager._run_lock, InterProcessLock(lockfile, logger=lgr):
            out = self._runner.run(self._config_cmd + args, **kwargs)

        if reload:
            self.reload()
            # this function is only used to modify config. If any manager
            # has modified the global scope, and is not itself the global
            # manager, we reload that one too in order to avoid stale
            # configuration reports
            if scope == 'global' and self is not datalad.cfg:
                datalad.cfg.reload()
        return out['stdout'], out['stderr']

    def _get_location_args(self, scope, args=None):
        if args is None:
            args = []
        cfg_labels = ('branch', 'local', 'global', 'override')
        if scope not in cfg_labels:
            raise ValueError(
                "unknown configuration label '{}' (not in {})".format(
                    scope, cfg_labels))
        if scope == 'branch':
            if not self._repo_pathobj:
                raise ValueError(
                    'ConfigManager cannot store configuration to dataset, '
                    'none specified')
            dataset_cfgfile = self._repo_pathobj / DATASET_CONFIG_FILE
            args.extend(['--file', str(dataset_cfgfile)])
        elif scope == 'global':
            args.append('--global')
        elif scope == 'local':
            args.append('--local')
        return args

    @_scope_reload
    @_where_to_scope
    def add(self, var, value, scope='branch', reload=True):
        """Add a configuration variable and value

        Parameters
        ----------
        var : str
          Variable name including any section like `git config` expects them, e.g.
          'core.editor'
        value : str
          Variable value
        %s"""
        if scope == 'override':
            from datalad.utils import ensure_list
            val = ensure_list(self.overrides.pop(var, None))
            val.append(value)
            self.overrides[var] = val[0] if len(val) == 1 else val
            if reload:
                self.reload(force=True)
            return

        self._run(['--add', var, value], scope=scope, reload=reload,
                  protocol=StdOutErrCapture)

    @_scope_reload
    @_where_to_scope
    def set(self, var, value, scope='branch', reload=True, force=False):
        """Set a variable to a value.

        In opposition to `add`, this replaces the value of `var` if there is
        one already.

        Parameters
        ----------
        var : str
          Variable name including any section like `git config` expects them, e.g.
          'core.editor'
        value : str
          Variable value
        force: bool
          if set, replaces all occurrences of `var` by a single one with the
          given `value`. Otherwise raise if multiple entries for `var` exist
          already
        %s"""
        if scope == 'override':
            self.overrides[var] = value
            if reload:
                self.reload(force=True)
            return

        from datalad.support.gitrepo import to_options

        self._run(to_options(replace_all=force) + [var, value],
                  scope=scope, reload=reload, protocol=StdOutErrCapture)

    @_scope_reload
    @_where_to_scope
    def rename_section(self, old, new, scope='branch', reload=True):
        """Rename a configuration section

        Parameters
        ----------
        old : str
          Name of the section to rename.
        new : str
          Name of the section to rename to.
        %s"""
        if scope == 'override':
            self.overrides = {
                (new + k[len(old):]) if k.startswith(old + '.') else k: v
                for k, v in self.overrides.items()
            }
            if reload:
                self.reload(force=True)
            return

        self._run(['--rename-section', old, new], scope=scope, reload=reload)

    @_scope_reload
    @_where_to_scope
    def remove_section(self, sec, scope='branch', reload=True):
        """Rename a configuration section

        Parameters
        ----------
        sec : str
          Name of the section to remove.
        %s"""
        if scope == 'override':
            self.overrides = {
                k: v
                for k, v in self.overrides.items()
                if not k.startswith(sec + '.')
            }
            if reload:
                self.reload(force=True)
            return

        self._run(['--remove-section', sec], scope=scope, reload=reload)

    @_scope_reload
    @_where_to_scope
    def unset(self, var, scope='branch', reload=True):
        """Remove all occurrences of a variable

        Parameters
        ----------
        var : str
          Name of the variable to remove
        %s"""
        if scope == 'override':
            self.overrides.pop(var, None)
            if reload:
                self.reload(force=True)
            return

        # use unset all as it is simpler for now
        self._run(['--unset-all', var], scope=scope, reload=reload)


def rewrite_url(cfg, url):
    """Any matching 'url.<base>.insteadOf' configuration is applied

    Any URL that starts with such a configuration will be rewritten
    to start, instead, with <base>. When more than one insteadOf
    strings match a given URL, the longest match is used.

    Parameters
    ----------
    cfg : ConfigManager or dict
      dict-like with configuration variable name/value-pairs.
    url : str
      URL to be rewritten, if matching configuration is found.

    Returns
    -------
    str
      Rewritten or unmodified URL.
    """
    insteadof = {
        # only leave the base url
        k[4:-10]: v
        for k, v in cfg.items()
        if k.startswith('url.') and k.endswith('.insteadof')
    }

    # all config that applies
    matches = {
        key: v
        for key, val in insteadof.items()
        for v in (val if isinstance(val, tuple) else (val,))
        if url.startswith(v)
    }
    # find longest match, like Git does
    if matches:
        rewrite_base, match = sorted(
            matches.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[0]
        if sum(match == v for v in matches.values()) > 1:
            lgr.warning(
                "Ignoring URL rewrite configuration for '%s', "
                "multiple conflicting definitions exists: %s",
                match,
                ['url.{}.insteadof'.format(k)
                 for k, v in matches.items()
                 if v == match]
            )
        else:
            url = '{}{}'.format(rewrite_base, url[len(match):])
    return url


# for convenience, bind to class too
ConfigManager.rewrite_url = rewrite_url

#
# Helpers for bypassing git-config when _writing_ config items,
# mostly useful when a large number of changes needs to be made
# and directly file manipulation without a safety net is worth
# the risk for performance reasons.
#

def quote_config(v):
    """Helper to perform minimal quoting of config keys/value parts

    Parameters
    ----------
    v : str
      To-be-quoted string
    """
    white = (' ', '\t')
    comment = ('#', ';')
    # backslashes need to be quoted in any case
    v = v.replace('\\', '\\\\')
    # must not have additional unquoted quotes
    v = v.replace('"', '\\"')
    if v[0] in white or v[-1] in white or any(c in v for c in comment):
        # quoting the value due to leading/trailing whitespace
        # or occurrence of comment char
        v = '"{}"'.format(v)
    return v


def write_config_section(fobj, suite, name, props):
    """Write a config section with (multiple) settings.

    Parameters
    ----------
    fobj : File
       Opened target file
    suite : str
       First item of the section name, e.g. 'submodule', or
       'datalad'
    name : str
       Remainder of the section name
    props : dict
       Keys are configuration setting names within the section
       context (i.e. not duplicating `suite` and/or `name`, values
       are configuration setting values.
    """
    fmt = '[{_suite_} {_q_}{_name_}{_q_}]\n'
    for p in props:
        fmt += '\t{p} = {{{p}}}\n'.format(p=p)
    quoted_name = quote_config(name)
    fobj.write(
        fmt.format(
            _suite_=suite,
            _q_='' if quoted_name.startswith('"') else '"',
            _name_=quoted_name,
            **{k: quote_config(v) for k, v in props.items()}))


def warn_on_undefined_git_identity(cfg: ConfigManager):
    """Check whether a Git identity is defined, and warn if not"""
    for cfgkey, envs in (
            ('user.name', ('GIT_AUTHOR_NAME', 'GIT_COMMITTER_NAME')),
            ('user.email', ('GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_EMAIL'))):
        if cfgkey not in cfg \
                and not any(e in os.environ for e in envs):
            lgr.warning(
                "It is highly recommended to configure Git before using "
                "DataLad. Set both 'user.name' and 'user.email' "
                "configuration variables."
            )
            break  # one warning enough
