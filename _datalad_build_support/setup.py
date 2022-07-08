# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


import datetime
import os
import platform
import sys
from os import (
    linesep,
    makedirs,
)
from os.path import dirname
from os.path import join as opj
from os.path import sep as pathsep
from os.path import splitext

import setuptools
from genericpath import exists
from packaging.version import Version
from setuptools import (
    Command,
    DistutilsOptionError,
    find_namespace_packages,
    findall,
    setup,
)

from . import formatters as fmt


def _path_rel2file(*p):
    # dirname instead of joining with pardir so it works if
    # datalad_build_support/ is just symlinked into some extension
    # while developing
    return opj(dirname(dirname(__file__)), *p)


def get_version(name):
    """Determine version via importlib_metadata

    Parameters
    ----------
    name: str
      Name of the folder (package) where from to read version.py
    """
    # delay import so we do not require it for a simple setup stage
    try:
        from importlib.metadata import version as importlib_version
    except ImportError:
        # TODO - remove whenever python >= 3.8
        from importlib_metadata import version as importlib_version
    return importlib_version(name)


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
        self.manpath = opj('build', 'man')
        self.rstpath = opj('docs', 'source', 'generated', 'man')
        self.parser = 'datalad.cli.parser:setup_parser'

    def finalize_options(self):
        if self.manpath is None:
            raise DistutilsOptionError('\'manpath\' option is required')
        if self.rstpath is None:
            raise DistutilsOptionError('\'rstpath\' option is required')
        if self.parser is None:
            raise DistutilsOptionError('\'parser\' option is required')
        self.manpath = _path_rel2file(self.manpath)
        self.rstpath = _path_rel2file(self.rstpath)
        mod_name, func_name = self.parser.split(':')
        fromlist = mod_name.split('.')
        try:
            mod = __import__(mod_name, fromlist=fromlist)
            self._parser = getattr(mod, func_name)(
                ['datalad'],
                formatter_class=fmt.ManPageFormatter,
                return_subparsers=True,
                help_ignore_extensions=True)

        except ImportError as err:
            raise err

        self.announce('Writing man page(s) to %s' % self.manpath)
        self._today = datetime.date.today()

    @classmethod
    def handle_module(cls, mod_name, **kwargs):
        """Module specific handling.

        This particular one does
        1. Memorize (at class level) the module name of interest here
        2. Check if 'datalad.extensions' are specified for the module,
           and then analyzes them to obtain command names it provides

        If cmdline commands are found, its entries are to be used instead of
        the ones in datalad's _parser.

        Parameters
        ----------
        **kwargs:
            all the kwargs which might be provided to setuptools.setup
        """
        cls.mod_name = mod_name

        exts = kwargs.get('entry_points', {}).get('datalad.extensions', [])
        for ext in exts:
            assert '=' in ext      # should be label=module:obj
            ext_label, mod_obj = ext.split('=', 1)
            assert ':' in mod_obj  # should be module:obj
            mod, obj = mod_obj.split(':', 1)
            assert mod_name == mod  # AFAIK should be identical

            mod = __import__(mod_name)
            if hasattr(mod, obj):
                command_suite = getattr(mod, obj)
                assert len(command_suite) == 2  # as far as I see it
                if not hasattr(cls, 'cmdline_names'):
                    cls.cmdline_names = []
                cls.cmdline_names += [
                    cmd
                    for _, _, cmd, _ in command_suite[1]
                ]

    def run(self):

        dist = self.distribution
        #homepage = dist.get_url()
        #appname = self._parser.prog
        appname = 'datalad'

        sections = {
            'Authors': """{0} is developed by {1} <{2}>.""".format(
                appname, dist.get_author(), dist.get_author_email()),
        }

        for cls, opath, ext in ((fmt.ManPageFormatter, self.manpath, '1'),
                                (fmt.RSTManPageFormatter, self.rstpath, 'rst')):
            if not os.path.exists(opath):
                os.makedirs(opath)
            for cmdname in getattr(self, 'cmdline_names', list(self._parser)):
                p = self._parser[cmdname]
                cmdname = "{0}{1}".format(
                    'datalad ' if cmdname != 'datalad' else '',
                    cmdname)
                format = cls(
                    cmdname,
                    ext_sections=sections,
                    version=get_version(getattr(self, 'mod_name', appname)))
                formatted = format.format_man_page(p)
                with open(opj(opath, '{0}.{1}'.format(
                        cmdname.replace(' ', '-'),
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
        self.expath = opj('docs', 'examples')
        self.rstpath = opj('docs', 'source', 'generated', 'examples')

    def finalize_options(self):
        if self.expath is None:
            raise DistutilsOptionError('\'expath\' option is required')
        if self.rstpath is None:
            raise DistutilsOptionError('\'rstpath\' option is required')
        self.expath = _path_rel2file(self.expath)
        self.rstpath = _path_rel2file(self.rstpath)
        self.announce('Converting example scripts')

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


class BuildConfigInfo(Command):
    description = 'Generate RST documentation for all config items.'

    user_options = [
        ('rstpath=', None, 'output path for RST file'),
    ]

    def initialize_options(self):
        self.rstpath = opj('docs', 'source', 'generated', 'cfginfo')

    def finalize_options(self):
        if self.rstpath is None:
            raise DistutilsOptionError('\'rstpath\' option is required')
        self.rstpath = _path_rel2file(self.rstpath)
        self.announce('Generating configuration documentation')

    def run(self):
        opath = self.rstpath
        if not os.path.exists(opath):
            os.makedirs(opath)

        from datalad.dochelpers import _indent
        from datalad.interface.common_cfg import definitions as cfgdefs

        categories = {
            'global': {},
            'local': {},
            'dataset': {},
            'misc': {}
        }
        for term, v in cfgdefs.items():
            categories[v.get('destination', 'misc')][term] = v

        for cat in categories:
            with open(opj(opath, '{}.rst.in'.format(cat)), 'w') as rst:
                rst.write('.. glossary::\n')
                for term, v in sorted(categories[cat].items(), key=lambda x: x[0]):
                    rst.write(_indent(term, '\n  '))
                    qtype, docs = v.get('ui', (None, {}))
                    desc_tmpl = '\n'
                    if 'title' in docs:
                        desc_tmpl += '{title}:\n'
                    if 'text' in docs:
                        desc_tmpl += '{text}\n'
                    if 'default' in v:
                        default = v['default']
                        if hasattr(default, 'replace'):
                            # protect against leaking specific home dirs
                            v['default'] = default.replace(os.path.expanduser('~'), '~')
                        desc_tmpl += 'Default: {default}\n'
                    if 'type' in v:
                        type_ = v['type']
                        if hasattr(type_, 'long_description'):
                            type_ = type_.long_description()
                        else:
                            type_ = type_.__name__
                        desc_tmpl += '\n[{type}]\n'
                        v['type'] = type_
                    if desc_tmpl == '\n':
                        # we need something to avoid joining terms
                        desc_tmpl += 'undocumented\n'
                    v.update(docs)
                    rst.write(_indent(desc_tmpl.format(**v), '    '))


class BuildSchema(Command):
    description = 'Generate DataLad JSON-LD schema.'

    user_options = [
        ('path=', None, 'output path for schema file'),
    ]

    def initialize_options(self):
        self.path = opj('docs', 'source', '_extras')

    def finalize_options(self):
        if self.path is None:
            raise DistutilsOptionError('\'path\' option is required')
        self.path = _path_rel2file(self.path)
        self.announce('Generating JSON-LD schema file')

    def run(self):
        import json
        import shutil

        from datalad.metadata.definitions import common_defs
        from datalad.metadata.definitions import version as schema_version

        def _mk_fname(label, version):
            return '{}{}{}.json'.format(
                label,
                '_v' if version else '',
                version)

        def _defs2context(defs, context_label, vocab_version, main_version=schema_version):
            opath = opj(
                self.path,
                _mk_fname(context_label, vocab_version))
            odir = dirname(opath)
            if not os.path.exists(odir):
                os.makedirs(odir)

            # to become DataLad's own JSON-LD context
            context = {}
            schema = {"@context": context}
            if context_label != 'schema':
                schema['@vocab'] = 'http://docs.datalad.org/{}'.format(
                    _mk_fname('schema', main_version))
            for key, val in defs.items():
                # git-annex doesn't allow ':', but in JSON-LD we need it for
                # namespace separation -- let's make '.' in git-annex mean
                # ':' in JSON-LD
                key = key.replace('.', ':')
                definition = val['def']
                if definition.startswith('http://') or definition.startswith('https://'):
                    # this is not a URL, hence an @id definitions that points
                    # to another schema
                    context[key] = definition
                    continue
                # the rest are compound definitions
                props = {'@id': definition}
                if 'unit' in val:
                    props['unit'] = val['unit']
                if 'descr' in val:
                    props['description'] = val['descr']
                context[key] = props

            with open(opath, 'w') as fp:
                json.dump(
                    schema,
                    fp,
                    ensure_ascii=True,
                    indent=1,
                    separators=(', ', ': '),
                    sort_keys=True)
            print('schema written to {}'.format(opath))

        # core vocabulary
        _defs2context(common_defs, 'schema', schema_version)

        # present the same/latest version also as the default
        shutil.copy(
            opj(self.path, _mk_fname('schema', schema_version)),
            opj(self.path, 'schema.json'))


def get_long_description_from_README():
    """Read README.md, convert to .rst using pypandoc

    If pypandoc is not available or fails - just output original .md.

    Returns
    -------
    dict
      with keys long_description and possibly long_description_content_type
      for newer setuptools which support uploading of markdown as is.
    """
    # PyPI used to not render markdown. Workaround for a sane appearance
    # https://github.com/pypa/pypi-legacy/issues/148#issuecomment-227757822
    # is still in place for older setuptools

    README = opj(_path_rel2file('README.md'))

    ret = {}
    if Version(setuptools.__version__) >= Version('38.6.0'):
        # check than this
        ret['long_description'] = open(README).read()
        ret['long_description_content_type'] = 'text/markdown'
        return ret

    # Convert or fall-back
    try:
        import pypandoc
        return {'long_description': pypandoc.convert(README, 'rst')}
    except (ImportError, OSError) as exc:
        # attempting to install pandoc via brew on OSX currently hangs and
        # pypandoc imports but throws OSError demanding pandoc
        print(
                "WARNING: pypandoc failed to import or thrown an error while "
                "converting"
                " README.md to RST: %r   .md version will be used as is" % exc
        )
        return {'long_description': open(README).read()}


def findsome(subdir, extensions):
    """Find files under subdir having specified extensions

    Leading directory (datalad) gets stripped
    """
    return [
        f.split(pathsep, 1)[1] for f in findall(opj('datalad', subdir))
        if splitext(f)[-1].lstrip('.') in extensions
    ]


def datalad_setup(name, **kwargs):
    """A helper for a typical invocation of setuptools.setup.

    If not provided in kwargs, following fields will be autoset to the defaults
    or obtained from the present on the file system files:

    - author
    - author_email
    - packages -- all found packages which start with `name`
    - long_description -- converted to .rst using pypandoc README.md
    - version -- parsed `__version__` within `name/version.py`

    Parameters
    ----------
    name: str
        Name of the Python package
    **kwargs:
        The rest of the keyword arguments passed to setuptools.setup as is
    """
    # Simple defaults
    for k, v in {
        'author': "The DataLad Team and Contributors",
        'author_email': "team@datalad.org"
    }.items():
        if kwargs.get(k) is None:
            kwargs[k] = v

    # More complex, requiring some function call

    # Only recentish versions of find_packages support include
    # packages = find_packages('.', include=['datalad*'])
    # so we will filter manually for maximal compatibility
    if kwargs.get('packages') is None:
        # Use find_namespace_packages() in order to include folders that
        # contain data files but no Python code
        kwargs['packages'] = [pkg for pkg in find_namespace_packages('.') if pkg.startswith(name)]
    if kwargs.get('long_description') is None:
        kwargs.update(get_long_description_from_README())

    cmdclass = kwargs.get('cmdclass', {})
    # Check if command needs some module specific handling
    for v in cmdclass.values():
        if hasattr(v, 'handle_module'):
            getattr(v, 'handle_module')(name, **kwargs)
    return setup(name=name, **kwargs)
