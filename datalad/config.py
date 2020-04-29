# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""

from functools import lru_cache
import datalad
from datalad.consts import (
    DATASET_CONFIG_FILE,
    DATALAD_DOTDIR,
)
from datalad.cmd import GitRunner
from datalad.dochelpers import exc_str
from distutils.version import LooseVersion

import re
import os
from os.path import (
    join as opj,
    exists,
    getmtime,
    abspath,
    isabs,
)
from time import time

import logging
lgr = logging.getLogger('datalad.config')

cfg_kv_regex = re.compile(r'(^.*)\n(.*)$', flags=re.MULTILINE)
cfg_section_regex = re.compile(r'(.*)\.[^.]+')
cfg_sectionoption_regex = re.compile(r'(.*)\.([^.]+)')


_where_reload_doc = """
        where : {'dataset', 'local', 'global', 'override'}, optional
          Indicator which configuration file to modify. 'dataset' indicates the
          persistent configuration in .datalad/config of a dataset; 'local'
          the configuration of a dataset's Git repository in .git/config;
          'global' refers to the general configuration that is not specific to
          a single repository (usually in $USER/.gitconfig); 'override'
          limits the modification to the ConfigManager instance, and the
          assigned value overrides any setting from any other source.
        reload : bool
          Flag whether to reload the configuration from file(s) after
          modification. This can be disable to make multiple sequential
          modifications slightly more efficient.""".lstrip()


# we cannot import external_versions here, as the cfg comes before anything
# and we would have circular imports
@lru_cache()
def get_git_version(runner=None):
    """Return version of available git"""
    runner = runner or GitRunner()
    return runner.run('git version'.split())[0].split()[2]


def _where_reload(obj):
    """Helper decorator to simplify providing repetitive docstring"""
    obj.__doc__ = obj.__doc__ % _where_reload_doc
    return obj


def _parse_gitconfig_dump(dump, store, fileset, replace, cwd=None):
    if replace:
        # if we want to replace existing values in the store
        # collect into a new dict and `update` the store at the
        # end. This way we get the desired behavior of multi-value
        # keys, but only for the current source
        dct = {}
        fileset = set()
    else:
        # if we don't want to replace value, perform the multi-value
        # preserving addition on the existing store right away
        dct = store
    for line in dump.split('\0'):
        if not line:
            continue
        if line.startswith('file:'):
            # origin line
            fname = line[5:]
            if not isabs(fname):
                fname = opj(cwd, fname) if cwd else abspath(fname)
            fileset.add(fname)
            continue
        if line.startswith('command line:'):
            # nothing we could handle
            continue
        kv_match = cfg_kv_regex.match(line)
        if kv_match:
            k, v = kv_match.groups()
        else:
            # could be just a key without = value, which git treats as True
            # if asked for a bool
            k, v = line, None
        present_v = dct.get(k, None)
        if present_v is None:
            dct[k] = v
        else:
            if isinstance(present_v, tuple):
                dct[k] = present_v + (v,)
            else:
                dct[k] = (present_v, v)
    if replace:
        store.update(dct)
    return store, fileset


def _parse_env(store):
    dct = {}
    for k in os.environ:
        if not k.startswith('DATALAD_'):
            continue
        dct[k.replace('__', '-').replace('_', '.').lower()] = os.environ[k]
    store.update(dct)
    return store


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
    written during normal operation. If such need arises, various solutions are
    possible (via GitPython, or an independent writer).

    Each instance carries a public `overrides` attribute. This dictionary
    contains variables that override any setting read from a file. The overrides
    are persistent across reloads, and are not modified by any of the
    manipulation methods, such as `set` or `unset`.

    Any DATALAD_* environment variable is also presented as a configuration
    item. Settings read from environment variables are not stored in any of the
    configuration file, but are read dynamically from the environment at each
    `reload()` call. Their values take precedence over any specification in
    configuration files, and even overrides.

    Parameters
    ----------
    dataset : Dataset, optional
      If provided, all `git config` calls are executed in this dataset's
      directory. Moreover, any modifications are, by default, directed to
      this dataset's configuration file (which will be created on demand)
    dataset_only : bool
      Legacy option, do not use.
    overrides : dict, optional
      Variable overrides, see general class documentation for details.
    source : {'any', 'local', 'dataset', 'dataset-local'}, optional
      Which sources of configuration setting to consider. If 'dataset',
      configuration items are only read from a dataset's persistent
      configuration file, if any is present (the one in ``.datalad/config``, not
      ``.git/config``); if 'local', any non-committed source is considered
      (local and global configuration in Git config's terminology);
      if 'dataset-local', persistent dataset configuration and local, but
      not global or system configuration are considered; if 'any'
      all possible sources of configuration are considered.
    """

    _checked_git_identity = False

    def __init__(self, dataset=None, dataset_only=False, overrides=None, source='any'):
        if source not in ('any', 'local', 'dataset', 'dataset-local'):
            raise ValueError(
                'Unkown ConfigManager(source=) setting: {}'.format(source))
            # legacy compat
        if dataset_only:
            if source != 'any':
                raise ValueError('Refuse to combine legacy dataset_only flag, with '
                                 'source setting')
            source = 'dataset'
        # store in a simple dict
        # no subclassing, because we want to be largely read-only, and implement
        # config writing separately
        self._store = {}
        self._cfgfiles = set()
        self._cfgmtimes = None
        self._dataset_path = None
        self._dataset_cfgfname = None
        self._repo_cfgfname = None
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
            if source in ('dataset', 'dataset-local'):
                raise ValueError(
                    'ConfigManager configured to read dataset only, '
                    'but no dataset given')
            # The caller didn't specify a repository. Unset the git directory
            # when calling 'git config' to prevent a repository in the current
            # working directory from leaking configuration into the output.
            self._config_cmd = ['git', '--git-dir=', 'config']
        else:
            self._dataset_path = dataset.path
            if source != 'local':
                self._dataset_cfgfname = opj(self._dataset_path,
                                             DATASET_CONFIG_FILE)
            if source != 'dataset':
                self._repo_cfgfname = opj(self._dataset_path, '.git', 'config')
        self._src_mode = source
        # Since configs could contain sensitive information, to prevent
        # any "facilitated" leakage -- just disable logging of outputs for
        # this runner
        run_kwargs = dict(log_outputs=False)
        if dataset is not None:
            # make sure we run the git config calls in the dataset
            # to pick up the right config files
            run_kwargs['cwd'] = dataset.path
        self._runner = GitRunner(**run_kwargs)
        try:
            self._gitconfig_has_showorgin = \
                LooseVersion(get_git_version()) >= '2.8.0'
        except Exception:
            # no git something else broken, assume git is present anyway
            # to not delay this, but assume it is old
            self._gitconfig_has_showorgin = False

        self.reload(force=True)

    def reload(self, force=False):
        """Reload all configuration items from the configured sources

        If `force` is False, all files configuration was previously read from
        are checked for differences in the modification times. If no difference
        is found for any file no reload is performed. This mechanism will not
        detect newly created global configuration files, use `force` in this case.
        """
        if not force and self._cfgmtimes:
            # we aren't forcing and we have read files before
            # check if any file we read from has changed
            current_time = time()
            curmtimes = {c: getmtime(c) for c in self._cfgfiles if exists(c)}
            if all(curmtimes[c] == self._cfgmtimes.get(c) and
                   # protect against low-res mtimes (FAT32 has 2s, EXT3 has 1s!)
                   # if mtime age is less than worst resolution assume modified
                   (current_time - curmtimes[c]) > 2.0
                   for c in curmtimes):
                # all the same, nothing to do, except for
                # superimpose overrides, could have changed in the meantime
                self._store.update(self.overrides)
                # reread env, is quick
                self._store = _parse_env(self._store)
                return

        self._store = {}
        # 2-step strategy:
        #   - load datalad dataset config from dataset
        #   - load git config from all supported by git sources
        # in doing so we always stay compatible with where Git gets its
        # config from, but also allow to override persistent information
        # from dataset locally or globally
        run_args = ['-z', '-l']
        if self._gitconfig_has_showorgin:
            run_args.append('--show-origin')

        if self._dataset_cfgfname:
            if exists(self._dataset_cfgfname):
                stdout, stderr = self._run(
                    run_args + ['--file', self._dataset_cfgfname],
                    log_stderr=True
                )
                # overwrite existing value, do not amend to get multi-line
                # values
                self._store, self._cfgfiles = _parse_gitconfig_dump(
                    stdout, self._store, self._cfgfiles, replace=False,
                    cwd=self._runner.cwd)

        if self._src_mode == 'dataset':
            # superimpose overrides, and stop early
            self._store.update(self.overrides)
            return

        if self._src_mode == 'dataset-local':
            run_args.append('--local')
        stdout, stderr = self._run(run_args, log_stderr=True)
        self._store, self._cfgfiles = _parse_gitconfig_dump(
            stdout, self._store, self._cfgfiles, replace=True,
            cwd=self._runner.cwd)

        # always monitor the dataset cfg location, we know where it is in all cases
        if self._dataset_cfgfname:
            self._cfgfiles.add(self._dataset_cfgfname)
            self._cfgfiles.add(self._repo_cfgfname)
        self._cfgmtimes = {c: getmtime(c) for c in self._cfgfiles if exists(c)}

        # superimpose overrides
        self._store.update(self.overrides)

        # override with environment variables
        self._store = _parse_env(self._store)

        if not ConfigManager._checked_git_identity:
            for cfg, envs in (
                    ('user.name', ('GIT_AUTHOR_NAME', 'GIT_COMMITTER_NAME')),
                    ('user.email', ('GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_EMAIL'))):
                if cfg not in self._store \
                        and not any(e in os.environ for e in envs):
                    lgr.warning(
                        "It is highly recommended to configure Git before using "
                        "DataLad. Set both 'user.name' and 'user.email' "
                        "configuration variables."
                    )
            ConfigManager._checked_git_identity = True

    @_where_reload
    def obtain(self, var, default=None, dialog_type=None, valtype=None,
               store=False, where=None, reload=True, **kwargs):
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
        # could theroetically import all kind of weired things for type
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
            # we cannot use logging, because we want to use the config to confiugre
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
                        _value, var, valtype, exc_str(e)))

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
            if where is None and 'destination' in cdef:
                where = cdef['destination']
            if where is None:
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
                    _value, exc_str(e)))
            # XXX we could consider "looping" until we have a value of proper
            # type in case of a user typo...

        if store:
            # store value as it was before any conversion, needs to be str
            # anyway
            # needs string conversion nevertheless, because default could come
            # in as something else
            self.add(var, '{}'.format(_value), where=where, reload=reload)
        return value

    def __str__(self):
        return "ConfigManager({}{})".format(
            self._cfgfiles,
            '+ overrides' if self.overrides else '',
        )

    #
    # Compatibility with dict API
    #
    def __len__(self):
        return len(self._store)

    def __getitem__(self, key):
        return self._store.__getitem__(key)

    def __contains__(self, key):
        return self._store.__contains__(key)

    def keys(self):
        """Returns list of configuration item names"""
        return self._store.keys()

    # XXX should this be *args?
    def get(self, key, default=None):
        """D.get(k[,d]) -> D[k] if k in D, else d.  d defaults to None."""
        return self._store.get(key, default)

    #
    # Compatibility with ConfigParser API
    #
    def sections(self):
        """Returns a list of the sections available"""
        return list(set([cfg_section_regex.match(k).group(1) for k in self._store]))

    def options(self, section):
        """Returns a list of options available in the specified section."""
        opts = []
        for k in self._store:
            sec, opt = cfg_sectionoption_regex.match(k).groups()
            if sec == section:
                opts.append(opt)
        return opts

    def has_section(self, section):
        """Indicates whether a section is present in the configuration"""
        for k in self._store:
            if k.startswith(section):
                return True
        return False

    def has_option(self, section, option):
        """If the given section exists, and contains the given option"""
        for k in self._store:
            sec, opt = cfg_sectionoption_regex.match(k).groups()
            if sec == section and opt == option:
                return True
        return False

    def getint(self, section, option):
        """A convenience method which coerces the option value to an integer"""
        return int(self.get_value(section, option))

    def getbool(self, section, option, default=None):
        """A convenience method which coerces the option value to a bool

        Values "on", "yes", "true" and any int!=0 are considered True
        Values which evaluate to bool False, "off", "no", "false" are considered
        False
        TypeError is raised for other values.
        """
        val = self.get_value(section, option, default=default)
        if val is None:  # no value at all, git treats it as True
            return True
        return anything2bool(val)

    def getfloat(self, section, option):
        """A convenience method which coerces the option value to a float"""
        return float(self.get_value(section, option))

    # this is a hybrid of ConfigParser and dict API
    def items(self, section=None):
        """Return a list of (name, value) pairs for each option

        Optionally limited to a given section.
        """
        if section is None:
            return self._store.items()
        return [(k, v) for k, v in self._store.items()
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
    @_where_reload
    def _run(self, args, where=None, reload=False, **kwargs):
        """Centralized helper to run "git config" calls

        Parameters
        ----------
        args : list
          Arguments to pass for git config
        %s
        **kwargs
          Keywords arguments for Runner's call
        """
        if where:
            args = self._get_location_args(where) + args
        out = self._runner.run(self._config_cmd + args, **kwargs)
        if reload:
            self.reload()
        return out

    def _get_location_args(self, where, args=None):
        if args is None:
            args = []
        cfg_labels = ('dataset', 'local', 'global', 'override')
        if where not in cfg_labels:
            raise ValueError(
                "unknown configuration label '{}' (not in {})".format(
                    where, cfg_labels))
        if where == 'dataset':
            if not self._dataset_cfgfname:
                raise ValueError(
                    'ConfigManager cannot store configuration to dataset, '
                    'none specified')
            # create an empty config file if none exists, `git config` will
            # fail otherwise
            dscfg_dirname = opj(self._dataset_path, DATALAD_DOTDIR)
            if not exists(dscfg_dirname):
                os.makedirs(dscfg_dirname)
            if not exists(self._dataset_cfgfname):
                open(self._dataset_cfgfname, 'w').close()
            args.extend(['--file', self._dataset_cfgfname])
        elif where == 'global':
            args.append('--global')
        elif where == 'local':
            args.append('--local')
        return args

    @_where_reload
    def add(self, var, value, where='dataset', reload=True):
        """Add a configuration variable and value

        Parameters
        ----------
        var : str
          Variable name including any section like `git config` expects them, e.g.
          'core.editor'
        value : str
          Variable value
        %s"""
        if where == 'override':
            from datalad.utils import assure_list
            val = assure_list(self.overrides.pop(var, None))
            val.append(value)
            self.overrides[var] = val[0] if len(val) == 1 else val
            if reload:
                self.reload(force=True)
            return

        self._run(['--add', var, value], where=where, reload=reload, log_stderr=True)

    @_where_reload
    def set(self, var, value, where='dataset', reload=True, force=False):
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
        if where == 'override':
            self.overrides[var] = value
            if reload:
                self.reload(force=True)
            return

        from datalad.support.gitrepo import to_options

        self._run(to_options(replace_all=force) + [var, value],
                  where=where, reload=reload, log_stderr=True)

    @_where_reload
    def rename_section(self, old, new, where='dataset', reload=True):
        """Rename a configuration section

        Parameters
        ----------
        old : str
          Name of the section to rename.
        new : str
          Name of the section to rename to.
        %s"""
        if where == 'override':
            self.overrides = {
                (new + k[len(old):]) if k.startswith(old + '.') else k: v
                for k, v in self.overrides.items()
            }
            if reload:
                self.reload(force=True)
            return

        self._run(['--rename-section', old, new], where=where, reload=reload)

    @_where_reload
    def remove_section(self, sec, where='dataset', reload=True):
        """Rename a configuration section

        Parameters
        ----------
        sec : str
          Name of the section to remove.
        %s"""
        if where == 'override':
            self.overrides = {
                k: v
                for k, v in self.overrides.items()
                if not k.startswith(sec + '.')
            }
            if reload:
                self.reload(force=True)
            return

        self._run(['--remove-section', sec], where=where, reload=reload)

    @_where_reload
    def unset(self, var, where='dataset', reload=True):
        """Remove all occurrences of a variable

        Parameters
        ----------
        var : str
          Name of the variable to remove
        %s"""
        if where == 'override':
            self.overrides.pop(var, None)
            if reload:
                self.reload(force=True)
            return

        # use unset all as it is simpler for now
        self._run(['--unset-all', var], where=where, reload=reload)


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
