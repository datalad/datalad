#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import platform
from os.path import dirname
from os.path import join as opj
from os.path import sep as pathsep
from os.path import splitext

from setuptools import findall
from setuptools import setup, find_packages

from setup_support import BuildConfigInfo
from setup_support import BuildManPage, setup_entry_points
from setup_support import BuildRSTExamplesFromScripts
from setup_support import get_version


def findsome(subdir, extensions):
    """Find files under subdir having specified extensions

    Leading directory (datalad) gets stripped
    """
    return [
        f.split(pathsep, 1)[1] for f in findall(opj('datalad', subdir))
        if splitext(f)[-1].lstrip('.') in extensions
    ]

# datalad version to be installed
version = get_version()

# Only recentish versions of find_packages support include
# datalad_pkgs = find_packages('.', include=['datalad*'])
# so we will filter manually for maximal compatibility
datalad_pkgs = [pkg for pkg in find_packages('.') if pkg.startswith('datalad')]

# keyring is a tricky one since it got split into two as of 8.0 and on older
# systems there is a problem installing via pip (e.g. on wheezy) so for those we
# would just ask for keyring
keyring_requires = ['keyring>=8.0', 'keyrings.alt']
pbar_requires = ['tqdm']

dist = platform.dist()
# on oldstable Debian let's ask for lower versions of keyring
if dist[0] == 'debian' and dist[1].split('.', 1)[0] == '7':
    keyring_requires = ['keyring<8.0']

requires = {
    'core': [
        'appdirs',
        'GitPython>=2.1.0',
        'iso8601',
        'humanize',
        'mock>=1.0.1',  # mock is also used for auto.py, not only for testing
        'patool>=1.7',
        'six>=1.8.0',
        'wrapt',
    ] + pbar_requires,
    'downloaders': [
        'boto',
        'msgpack-python',
        'requests>=1.2',
    ] + keyring_requires,
    'downloaders-extra': [
        'requests_ftp',
    ],
    'crawl': [
        'scrapy>=1.1.0rc3',  # versioning is primarily for python3 support
    ],
    'publish': [
        'jsmin',             # nice to have, and actually also involved in `install`
        'PyGithub',          # nice to have
    ],
    'tests': [
        'BeautifulSoup4',  # VERY weak requirement, still used in one of the tests
        'httpretty>=0.8.14',
        'mock',
        'nose>=1.3.4',
        'vcrpy',
    ],
    'metadata': [
        'simplejson',
        'pyld',
    ],
    'metadata-extra': [
        'PyYAML',  # very optional
    ]
}

requires['full'] = sum(list(requires.values()), [])

# Now add additional ones useful for development
requires.update({
    'devel-docs': [
        # used for converting README.md -> .rst for long_description
        'pypandoc',
        # Documentation
        'sphinx',
        'sphinx-rtd-theme',
    ],
    'devel-utils': [
        'nose-timer',
        # disable for now, as it pulls in ipython 6, which is PY3 only
        #'line-profiler',
        # necessary for accessing SecretStorage keyring (system wide Gnome
        # keyring)  but not installable on travis, IIRC since it needs connectivity
        # to the dbus whenever installed or smth like that, thus disabled here
        # but you might need it
        # 'dbus-python',
    ],
    'devel-neuroimaging': [
        # Specifically needed for tests here (e.g. example scripts testing)
        'nibabel',
    ]
})
requires['devel'] = sum(list(requires.values()), [])


# let's not build manpages and examples automatically (gh-896)
# configure additional command for custom build steps
#class DataladBuild(build_py):
#    def run(self):
#        self.run_command('build_manpage')
#        self.run_command('build_examples')
#        build_py.run(self)

cmdclass = {
    'build_manpage': BuildManPage,
    'build_examples': BuildRSTExamplesFromScripts,
    'build_cfginfo': BuildConfigInfo,
    # 'build_py': DataladBuild
}

# PyPI doesn't render markdown yet. Workaround for a sane appearance
# https://github.com/pypa/pypi-legacy/issues/148#issuecomment-227757822
README = opj(dirname(__file__), 'README.md')
try:
    import pypandoc
    long_description = pypandoc.convert(README, 'rst')
except ImportError:
    long_description = open(README).read()


#
# Avoid using entry_points due to their hefty overhead
#
setup_kwargs = setup_entry_points(
    {
        'datalad': 'datalad.cmdline.main',
        'git-annex-remote-datalad-archives': 'datalad.customremotes.archives',
        'git-annex-remote-datalad': 'datalad.customremotes.datalad',
    })

setup(
    name="datalad",
    author="The DataLad Team and Contributors",
    author_email="team@datalad.org",
    version=version,
    description="data distribution geared toward scientific datasets",
    long_description=long_description,
    packages=datalad_pkgs,
    install_requires=
        requires['core'] + requires['downloaders'] +
        requires['publish'] + requires['metadata'],
    extras_require=requires,
    cmdclass=cmdclass,
    package_data={
        'datalad':
            findsome('resources', {'sh', 'html', 'js', 'css', 'png', 'svg'}) +
            findsome('downloaders/configs', {'cfg'})
    },
    **setup_kwargs
)
