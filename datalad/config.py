# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Registry-like monster for now simply borrowed from bigmess/pymvpa

TODO: integration with cmdline etc
"""

__docformat__ = 'restructuredtext'

import os.path
from appdirs import AppDirs

from os.path import join as opj

from .support.configparserinc import SafeConfigParserWithIncludes

class ConfigManager(SafeConfigParserWithIncludes, object):
    """Central configuration registry for datalad.

    The purpose of this class is to collect all configurable settings
    used by various parts of datalad. It is fairly simple and does
    only little more than the standard Python ConfigParser. Like
    ConfigParser it is blind to the data that it stores, i.e. no type
    checking is performed.

    Configuration files (INI syntax) in multiple location are parsed
    when a class instance is created or whenever `Config.reload()` is
    called later on.  Files are read and parsed in the following
    order:

    1. '/etc/datalad/datalad.cfg'
    2. 'datalad/config' in all directories defined by $XDG_CONFIG_DIRS
       (by default: /etc/xdg/)
    3. 'datalad.cfg' in $XDG_CONFIG_HOME (by default: ~/.config/)
    4. 'datalad.cfg' in the current directory

    Moreover, the constructor takes an optional argument with a list
    of additional file names to parse afterwards.

    In addition to configuration files, this class also looks for
    special environment variables to read settings from. Names of such
    variables have to start with `DATALAD_` following by the an
    optional section name and the variable name itself ('_' as
    delimiter). If no section name is provided, the variables will be
    associated with section `general`. Some examples::

        DATALAD_VERBOSE=1

    will become::

        [general]
        verbose = 1

    However, `DATALAD_VERBOSE_OUTPUT=stdout` becomes::

        [verbose]
        output = stdout

    Any length of variable name as allowed, e.g. DATALAD_SEC1_LONG_NAME=1
    becomes::

        [sec1]
        long name = 1

    Settings from custom configuration files (specified by the constructor
    argument) have the highest priority and override settings found in any of
    the config files read from default locations (which are themselves read in
    the order stated above -- overwriting earlier configuration settings
    accordingly). Finally, the content of any `DATALAD_*` environment variables
    overrides any settings read from any file.
    """

    dirs = AppDirs("datalad", "datalad.org")

    # things we want to count on to be available
    _DEFAULTS = {'general': {'verbose': '1'}}

    def __init__(self, filenames=None, load_default=True):
        """Initialization reads settings from config files and env. variables.

        Parameters
        ----------
        filenames : list of filenames
        load_default: bool, optional
          Either to load default files (e.g. system/user-wide etc)
        """
        self._super.__init__()

        # set critical defaults
        for sec, params in ConfigManager._DEFAULTS.items():
            self.add_section(sec)
            for key, value in params.items():
                self.set(sec, key, value)

        self.__cfg_filenames = []
        self._load_default = load_default

        # now get the setting
        # TODO: look into loading/interaction with config being lazy or better more efficient...
        # could cut on startup time a bit.
        self.reload(filenames)

    @property
    def _super(self):
        return super(ConfigManager, self)

    def _get_default_file_candidates(self):
        # list of filenames to parse (custom plus some standard ones),
        # they are listed in the order they need to be parsed to
        # guarantee a sane configuration file cascade
        homedir = os.path.expanduser('~')  # seems to be useless ???
        cfg_file_candidates = [
            # shipped-with config
            # opj(os.path.dirname(__file__), 'datalad.cfg'),
            # system config
            '/etc/datalad/datalad.cfg']
        # XDG system config
        cfg_file_candidates.append(opj(self.dirs.site_config_dir, 'config'))

        # XDG user config
        home_cfg_base_path = self.dirs.user_config_dir
        if os.path.isabs(home_cfg_base_path):
            cfg_file_candidates.append(opj(home_cfg_base_path, 'datalad.cfg'))

        # current dir config
        cfg_file_candidates.append(opj('.datalad', 'config'))
        return cfg_file_candidates

    def _get_file_candidates(self):
        cfg_file_candidates = self._get_default_file_candidates() if self._load_default else []
        # runtime config
        cfg_file_candidates += self.__cfg_filenames
        return cfg_file_candidates


    def reload(self, filenames=None):
        """Re-read settings from all configured locations.
        """
        # store additional config file names
        if not filenames is None:
            self.__cfg_filenames = filenames

        # read local and user-specific config
        self.read(self._get_file_candidates())

        # now look for variables in the environment
        for var in [v for v in os.environ.keys() if v.startswith('DATALAD_')]:
            # strip leading 'DATALAD_' and lower case entries
            svar = var[8:].lower()

            # section is next element in name (or 'general' if simple name)
            if not svar.count('_'):
                sec = 'general'
            else:
                cut = svar.find('_')
                sec = svar[:cut]
                svar = svar[cut + 1:].replace('_', ' ')

            # check if section is already known and add it if not
            if not self.has_section(sec):
                self.add_section(sec)

            # set value
            self.set(sec, svar, os.environ[var])

    def get(self, section, option, default=None, **kwargs):
        """Wrapper around SafeConfigParser.get() with a custom default value.

        This method simply wraps the base class method, but adds a `default`
        keyword argument. The value of `default` is returned whenever the
        config parser does not have the requested option and/or section.
        """
        if not self.has_option(section, option):
            return default

        try:
            return self._super.get(section, option, **kwargs)
        except ValueError as e:
            # provide somewhat descriptive error
            raise ValueError(
                "Failed to obtain value from configuration for %s.%s. "
                "Original exception was: %s" % (section, option, e))

    def getboolean(self, section, option, default=None):
        """Wrapper around SafeConfigParser.getboolean() with a custom default.

        This method simply wraps the base class method, but adds a `default`
        keyword argument. The value of `default` is returned whenever the
        config parser does not have the requested option and/or section.
        """
        if not self.has_option(section, option):
            if isinstance(default, bool):
                return default
            else:
                # compatibility layer for py3 version of ConfigParser
                if hasattr(self, '_boolean_states'):
                    boolean_states = self._boolean_states
                else:
                    boolean_states = self.BOOLEAN_STATES  # there is no BOOLEAN_STATES ???
                if default is None or (default.lower() not in boolean_states):
                    raise ValueError('Not a boolean: %s' % default)
                return boolean_states[default.lower()]

        return self._super.getboolean(section, option)

    ##REF: Name was automagically refactored
    def get_as_dtype(self, section, option, dtype, default=None):
        """Convenience method to query options with a custom default and type

        This method simply wraps the base class method, but adds a
        `default` keyword argument. The value of `default` is returned
        whenever the config parser does not have the requested option
        and/or section.

        In addition, the returned value is converted into the
        specified `dtype`.
        """
        if not self.has_option(section, option):
            return default
        try:
            return self._super._get(section, dtype, option)
        except ValueError as e:
            # provide somewhat descriptive error
            raise ValueError(
                "Failed to obtain value from configuration for %s.%s. "
                "Original exception was: %s" % (section, option, e))
