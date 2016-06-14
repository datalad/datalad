# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


import os
from os.path import join as opj

from distutils.core import Command
from distutils.errors import DistutilsOptionError
import datetime
import formatters as fmt


class BuildManPage(Command):
    # The BuildManPage code was originally distributed
    # under the same License of Python
    # Copyright (c) 2014 Oz Nahum Tiram  <nahumoz@gmail.com>

    description = 'Generate man page from an ArgumentParser instance.'

    user_options = [
        ('manpath=', None, 'output path for manpages'),
        ('rstpath=', None, 'output path for RST files'),
        ('parser=', None, 'module path to an ArgumentParser instance'
         '(e.g. mymod:func, where func is a method or function which return'
         'a dict with one or more arparse.ArgumentParser instances.'),
    ]

    def initialize_options(self):
        self.manpath = None
        self.rstpath = None
        self.parser = None

    def finalize_options(self):
        if self.manpath is None:
            raise DistutilsOptionError('\'manpath\' option is required')
        if self.rstpath is None:
            raise DistutilsOptionError('\'rstpath\' option is required')
        if self.parser is None:
            raise DistutilsOptionError('\'parser\' option is required')
        mod_name, func_name = self.parser.split(':')
        fromlist = mod_name.split('.')
        try:
            mod = __import__(mod_name, fromlist=fromlist)
            self._parser = getattr(mod, func_name)(
                formatter_class=fmt.ManPageFormatter,
                return_subparsers=True)

        except ImportError as err:
            raise err

        self.announce('Writing man page(s) to %s' % self.manpath)
        self._today = datetime.date.today()

    def run(self):

        dist = self.distribution
        #homepage = dist.get_url()
        #appname = self._parser.prog
        appname = 'datalad'

        sections = {
            'Authors': """{0} is developed by {1} <{2}>.""".format(
                appname, dist.get_author(), dist.get_author_email()),
        }

        dist = self.distribution
        for cls, opath, ext in ((fmt.ManPageFormatter, self.manpath, '1'),
                                (fmt.RSTManPageFormatter, self.rstpath, 'rst')):
            if not os.path.exists(opath):
                os.makedirs(opath)
            for cmdname in self._parser:
                p = self._parser[cmdname]
                cmdname = "{0}{1}".format(
                    'datalad-' if cmdname != 'datalad' else '',
                    cmdname)
                format = cls(cmdname, ext_sections=sections)
                formatted = format.format_man_page(p)
                with open(opj(opath, '{0}.{1}'.format(
                        cmdname,
                        ext)),
                        'w') as f:
                    f.write(formatted)


class BuildRSTExamplesFromScripts(Command):
    description = 'Generate RST variants of example shell scripts.'

    user_options = [
        ('expath=', None, 'path to look for example scripts'),
        ('rstpath=', None, 'output path for RST files'),
    ]

    def initialize_options(self):
        self.expath = None
        self.rstpath = None

    def finalize_options(self):
        if self.expath is None:
            raise DistutilsOptionError('\'expath\' option is required')
        if self.rstpath is None:
            raise DistutilsOptionError('\'rstpath\' option is required')
        self.announce('Converting exanmple scripts')

    def run(self):
        opath = self.rstpath
        if not os.path.exists(opath):
            os.makedirs(opath)

        from glob import glob
        for example in glob(opj(self.expath, '*.sh')):
            exname = os.path.basename(example)[:-3]
            with open(opj(opath, '{0}.rst'.format(exname)), 'w') as out:
                fmt.cmdline_example_to_rst(
                    open(example),
                    out=out,
                    ref='_example_{0}'.format(exname))
