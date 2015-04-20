# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the testkraut package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Registry-like monster"""

__docformat__ = 'restructuredtext'

from ConfigParser import SafeConfigParser
import os.path
from os.path import join as opj


class ConfigManager(SafeConfigParser):
    """Central configuration registry for testkraut.

    The purpose of this class is to collect all configurable settings used by
    various parts of testkraut. It is fairly simple and does only little more
    than the standard Python ConfigParser. Like ConfigParser it is blind to the
    data that it stores, i.e. no type checking is performed.

    Configuration files (INI syntax) in multiple location are parsed when a
    class instance is created or whenever `Config.reload()` is called later on.
    Files are read and parsed in the following order:

    1. 'testkraut.cfg' in the same directory as this Python module file
    2. 'testkraut/config' in all directories defined by $XDG_CONFIG_DIRS
       (by default: /etc/xdg/)
    3. 'testkraut.cfg' in $XDG_CONFIG_HOME (by default: ~/.config/)
    4. 'testkraut.cfg' in the current directory

    Moreover, the constructor takes an optional argument with a list of
    additional file names to parse afterwards.

    In addition to configuration files, this class also looks for special
    environment variables to read settings from. Names of such variables have to
    start with `TESTKRAUT_` following by the an optional section name and the
    variable name itself ('_' as delimiter). If no section name is provided,
    the variables will be associated with section `general`. Some examples::

        TESTKRAUT_VERBOSE=1

    will become::

        [general]
        verbose = 1

    However, `TESTKRAUT_VERBOSE_OUTPUT=stdout` becomes::

        [verbose]
        output = stdout

    Any length of variable name as allowed, e.g. TESTKRAUT_SEC1_LONG_NAME=1
    becomes::

        [sec1]
        long name = 1

    Settings from custom configuration files (specified by the constructor
    argument) have the highest priority and override settings found in any of
    the config files read from default locations (which are themselves read in
    the order stated above -- overwriting earlier configuration settings
    accordingly). Finally, the content of any `TESTKRAUT_*` environment variables
    overrides any settings read from any file.
    """

    # things we want to count on to be available
    _DEFAULTS = {'general':
                  {
                    'verbose': '1',
                  }
                }


    def __init__(self, filenames=None):
        """Initialization reads settings from config files and env. variables.

        Parameters
        ----------
        filenames : list of filenames
        """
        SafeConfigParser.__init__(self)

        # store additional config file names
        if not filenames is None:
            self.__cfg_filenames = filenames
        else:
            self.__cfg_filenames = []

        # set critical defaults
        for sec, vars in ConfigManager._DEFAULTS.iteritems():
            self.add_section(sec)
            for key, value in vars.iteritems():
                self.set(sec, key, value)

        # now get the setting
        self.reload()


    def reload(self):
        """Re-read settings from all configured locations.
        """
        # listof filenames to parse (custom plus some standard ones), they are
        # listed in the order they need to be parsed to guarantee a sane
        # configuration file cascade
        homedir = os.path.expanduser('~')
        cfg_file_candidates = [
                # the base config shipped in the package
                opj(os.path.dirname(__file__), 'testkraut.cfg')
            ]
        # XDG system config
        cfg_file_candidates += [opj(b, 'testkraut', 'config') for b in
                                        os.environ.get("XDG_CONFIG_DIRS",
                                              "/etc/xdg").split(":")
                                    if os.path.isabs(b)]
        # XDG user config
        home_cfg_base_path = opj(os.environ.get("XDG_CONFIG_HOME",
                                   os.path.expanduser("~/.config")))
        if os.path.isabs(home_cfg_base_path):
            cfg_file_candidates.append(opj(home_cfg_base_path, 'testkraut.cfg'))
        # current dir config
        cfg_file_candidates.append(
                'testkraut.cfg'
            )
        # runtime config
        cfg_file_candidates += self.__cfg_filenames

        # read local and user-specific config
        files = self.read(cfg_file_candidates)

        # now look for variables in the environment
        for var in [v for v in os.environ.keys() if v.startswith('TESTKRAUT_')]:
            # strip leading 'TESTKRAUT_' and lower case entries
            svar = var[10:].lower()

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


    def __repr__(self):
        """Generate INI file content with current configuration.
        """
        # make adaptor to use str as file-like (needed for ConfigParser.write()
        class file2str(object):
            def __init__(self):
                self.__s = ''
            def write(self, val):
                self.__s += val
            def str(self):
                return self.__s

        r = file2str()
        self.write(r)

        return r.str()


    def save(self, filename):
        """Write current configuration to a file.
        """
        f = open(filename, 'w')
        self.write(f)
        f.close()


    def get(self, section, option, default=None, **kwargs):
        """Wrapper around SafeConfigParser.get() with a custom default value.

        This method simply wraps the base class method, but adds a `default`
        keyword argument. The value of `default` is returned whenever the
        config parser does not have the requested option and/or section.
        """
        if not self.has_option(section, option):
            return default

        try:
            return SafeConfigParser.get(self, section, option, **kwargs)
        except ValueError, e:
            # provide somewhat descriptive error
            raise ValueError, \
                  "Failed to obtain value from configuration for %s.%s. " \
                  "Original exception was: %s" % (section, option, e)


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
                    boolean_states = self.BOOLEAN_STATES
                if default.lower() not in boolean_states:
                    raise ValueError, 'Not a boolean: %s' % default
                return boolean_states[default.lower()]

        return SafeConfigParser.getboolean(self, section, option)


    ##REF: Name was automagically refactored
    def get_as_dtype(self, section, option, dtype, default=None):
        """Convenience method to query options with a custom default and type

        This method simply wraps the base class method, but adds a `default`
        keyword argument. The value of `default` is returned whenever the
        config parser does not have the requested option and/or section.

        In addition, the returned value is converted into the specified `dtype`.
        """
        if not self.has_option(section, option):
            return default
        try:
            return SafeConfigParser._get(self, section, dtype, option)
        except ValueError, e:
            # provide somewhat descriptive error
            raise ValueError, \
                  "Failed to obtain value from configuration for %s.%s. " \
                  "Original exception was: %s" % (section, option, e)
