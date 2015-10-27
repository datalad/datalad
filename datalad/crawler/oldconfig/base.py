# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from six import iteritems

from datalad.support.configparserinc import SafeConfigParserWithIncludes

from datalad.support.archives import DECOMPRESSORS

import logging
lgr = logging.getLogger('datalad.config')

#
# Configuration
#
class EnhancedConfigParser(SafeConfigParserWithIncludes):
    """Enhanced ConfigParser to support evaluations of the values etc

    """

    @staticmethod
    def get_default(sections={}):
        cfg = EnhancedConfigParser(defaults=dict(
            mode='download',                 # TODO -- check, use
            orig='auto',                     # TODO -- now we don't use it
            meta_info='True',                # TODO -- now we just use it
            directory="%(__name__)s",
            archives_re='(%s)' % ('|'.join(DECOMPRESSORS.keys())),
            # 'keep'  -- just keep original without annexing it etc
            # 'annex' -- git annex addurl ...
            # 'drop'  -- 'annex add(url)' and then 'annex drop' upon extract
            # 'rm'    -- remove upon extraction if archive
            # 'auto':
            # if incoming == public:
            #  'auto' == 'rm' if is_archive and 'annex' if
            # else:
            #  'auto' == 'annex'
            incoming_destiny="auto",
            # TODO:
            # maintain - preserve the ones in the archive and place them
            #            at the same level as the archive file (TODO)
            # strip - would remove leading extracted directory if a single one
            archives_directories="strip",
            incoming="repos/incoming/EXAMPLE",
            public="repos/public/EXAMPLE",
            include_href='',
            include_href_a='',
            exclude_href='',
            exclude_href_a='',
            filename='filename',
            # Checks!
            check_url_limit='0',                     # no limits
            # unused... we might like to enable it indeed and then be
            # smart with our actions in extracting archives into
            # directories which might contain those files, so some might
            # need to be annexed and some directly into .git
            # TODO
            #annex='.*',                    #
            # Q: or should we utilize annex.largefiles syntax etc?
            #    cons: for fast/relaxed mode etc we might not kow the size
            # NOTE: that in rm, keep modes those will not be added either since
            #       those modes set it up for handling archives
            git_add=None,                 # which files (regexp) should be added to git directly. Implies that
                                          # they need to be downloaded first
            recurse=None,                     # do not recurse by default, otherwise regex on urls to assume being for directories
            ))
        # TODO: verify correct input config.  Currently would not fail if some
        # unknown option (e.g. add_git) is used
        for section, options in iteritems(sections):
            if section != 'DEFAULT':
                cfg.add_section(section)
            for opt, value in iteritems(options):
                cfg.set(section, opt, value)
        return cfg

    def get_section(self, section):
        """Return container representing the section
        """
        return ConfigSection(self, section)


class ConfigSection(object):
    """Configuration section providing additional enhanced handling of option specifications
    """

    def __init__(self, config, section):
        self._config = config
        self._section = section
        self._env = {}
        # If present -- execute the 'exec' option to populate the environment
        if self._config.has_option(section, 'exec'):
            exec_ = self._config.get(section, 'exec')
            lgr.debug("Executing exec=%r in section %s to populate _env"
                       % (exec_, section))
            exec(exec_, self._env)


    def get(self, option, default=None, vars=None, raw=False, **kwargs):
        """get() with support of _e (evaluate) in `context`

        For an option X supports a set of ways how to obtain the actual
        value

        'X'
            plain value

        'X_e'
            evaluation of the expression in the 'context'.
            `vars` in this case are not passed into the expression
            for the interpolation, and should be used as regular
            variables in evaluation

        N.B. String interpolations are also in effect as provided by
        stock ConfigParser

        If multiple ways (e.g. X and X_e) are present -- _e takes precedence.
        """

        options = [option + suf
                   for suf in ('_e', '')
                   if self._config.has_option(self._section, option+suf)]
        if len(options) > 1:
            lgr.debug("Found multiple specifications: %s. Using first one"
                      % (options,))
        elif len(options) == 0:
            return default

        option = options[0]
        # what environment/variables would be available for
        # interpolation/evaluation
        vars_all = {}
        if self._env:
            vars_all.update(self._env)
        if vars:
            vars_all.update(vars)

        value = self._config.get(self._section,
                                 option,
                                 vars={} if option.endswith('_e') else vars_all,
                                 raw=raw,
                                 **kwargs)

        if option.endswith('_e') and not raw:
            value_ = eval(value, vars_all)
            return value_
        else:
            return value

    def __getitem__(self, k):
        return self.get(k)


def load_config(configs):
    # Load configuration
    cfg = EnhancedConfigParser.get_default()
    cfg_read = cfg.read(configs)
    assert set(configs).issubset(cfg_read), \
           "Not all configs were read. Wanted: %s Read: %s" % (configs, cfg_read)
    return cfg
