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

import logging
from datalad.cmd import Runner
import re
import os
from os.path import join as opj, exists

lgr = logging.getLogger('datalad.support.dsconfig')

cfg_kv_regex = re.compile(r'([^=]+)=(.*)')
cfg_section_regex = re.compile(r'(.*)\.[^.]+')
cfg_sectionoption_regex = re.compile(r'(.*)\.([^.]+)')


def _parse_gitconfig_dump(dump, store, replace):
    if replace:
        # if we want to replace existing values in the store
        # collect into a new dict and `update` the store at the
        # end. This way we get the desired behavior of multi-value
        # keys, but only for the current source
        dct = {}
    else:
        # if we don't want to replace value, perform the multi-value
        # preserving addition on the existing store right away
        dct = store
    for line in dump.split('\n'):
        if not line:
            continue
        k, v = cfg_kv_regex.match(line).groups()
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
    return store


class ConfigManager(object):
    """

    The general idea is to have an object that is primarily used to read/query
    configuration option. Upon creation, current configuration is read via one
    (or max two, in the case of the presence of dataset-specific configuration)
    calls to `git config`).

    The API aims to provide the most significant read-access bits of a
    dictionary, the Python ConfigParser, and GitPython's config parser
    implementation.
    """
    def __init__(self, dataset=None, dataset_only=False):
        # store in a simple dict
        # no subclassing, because we want to be largely read-only, and implement
        # config writing separately
        self._store = {}
        self._dataset = dataset
        self._dataset_only = dataset_only
        if dataset is not None:
            # make sure we run the git config calls in the dataset
            # to pick up the right config files
            self._runner = Runner(cwd=dataset.path)
        else:
            self._runner = Runner()
        self.reload()

    def reload(self):
        self._store = {}
        # 2-step strategy: load git config from all supported sources
        # then load datalad dataset config from dataset
        # in doing so we always stay compatible with where Git gets its
        # config from
        if not self._dataset_only:
            stdout, stderr = self._runner.run(
                ['git', 'config', '-l'], log_stderr=False)
            self._store = _parse_gitconfig_dump(
                stdout, self._store, replace=False)
        if self._dataset:
            # now any dataset config
            dscfg_fname = opj(self._dataset.path, '.datalad', 'config')
            if exists(dscfg_fname):
                stdout, stderr = self._runner.run(
                    ['git', 'config', '-l', '--file', dscfg_fname],
                    log_stderr=False)
                # overwrite existing value, do not amend to get multi-line
                # values
                self._store = _parse_gitconfig_dump(
                    stdout, self._store, replace=True)

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
        return self._store.keys()

    #
    # Compatibility with ConfigParser API
    #
    def sections(self):
        return list(set([cfg_section_regex.match(k).group(1) for k in self._store]))

    def options(self, section):
        opts = []
        for k in self._store:
            sec, opt = cfg_sectionoption_regex.match(k).groups()
            if sec == section:
                opts.append(opt)
        return opts

    def has_section(self, section):
        for k in self._store:
            if k.startswith(section):
                return True
        return False

    def has_option(self, section, option):
        for k in self._store:
            sec, opt = cfg_sectionoption_regex.match(k).groups()
            if sec == section and opt == option:
                return True
        return False

    def get(self, section, option):
        return self._store['.'.join((section, option))]
        pass

    def getint(self, section, option):
        return int(self.get(section, option))

    def getfloat(self, section, option):
        return float(self.get(section, option))

    # this is a hybrid of ConfigParser and dict API
    def items(self, section=None):
        if section is None:
            return self._store.items()
        return [(k, v) for k, v in self._store.items() if cfg_section_regex.match(k).group(1) == section]

    #
    # Compatibility with GitPython's ConfigParser
    #
    def get_value(self, section, option, default=None):
        try:
            return self.get(section, option)
        except KeyError as e:
            # this strange dance is needed because gitpython does it this way
            if default is not None:
                return default
            else:
                raise e

    #
    # Modify configuration (proxy respective git-config call
    #
    def _require_location(self, where, args=None):
        if args is None:
            args = []
        if not where in ('dataset', 'local', 'global'):
            raise ValueError(
                "unknown configuration label '{}' (not 'dataset', or 'global')".format(
                    where))
        if where == 'dataset':
            if not self._dataset:
                raise ValueError(
                    'ConfigManager cannot store to configuration to dataset, none specified')
            # create an empty config file if none exists, `git config` will
            # fail otherwise
            dscfg_dirname = opj(self._dataset.path, '.datalad')
            dscfg_fname = opj(dscfg_dirname, 'config')
            if not exists(dscfg_dirname):
                os.makedirs(dscfg_dirname)
            if not exists(dscfg_fname):
                open(dscfg_fname, 'w').close()
            args.extend(['--file', opj(self._dataset.path, '.datalad', 'config')])
        elif where == 'global':
            args.append('--global')
        elif where == 'local':
            args.append('--local')
        return args

    def add(self, var, value, where='dataset', reload=True):
        args = self._require_location(where)
        args += ('--add', var, value)
        self._runner.run(
            ['git', 'config'] + args,
            log_stderr=True)
        if reload:
            self.reload()

    def rename_section(self, old, new, where='dataset', reload=True):
        args = self._require_location(where)
        self._runner.run(
            ['git', 'config'] + args + ['--rename-section', old, new])
        if reload:
            self.reload()

    def unset(self, var, where='dataset', reload=True):
        args = self._require_location(where)
        self._runner.run(
            # use unset all as it is simpler for now
            ['git', 'config'] + args + ['--unset-all', var])
        if reload:
            self.reload()
