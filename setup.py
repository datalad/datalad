#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import sys
from os.path import dirname
from os.path import join as opj

# This is needed for versioneer to be importable when building with PEP 517.
# See <https://github.com/warner/python-versioneer/issues/193> and links
# therein for more information.
sys.path.append(dirname(__file__))

import versioneer
from _datalad_build_support.setup import (
    BuildConfigInfo,
    BuildManPage,
    BuildSchema,
    datalad_setup,
)

requires = {
    'core': [
        'platformdirs',
        'chardet>=3.0.4, <5.0.0',      # rarely used but small/omnipresent
        'colorama; platform_system=="Windows"',
        'distro; python_version >= "3.8"',
        'importlib-metadata >=3.6; python_version < "3.10"',
        'iso8601',
        'humanize',
        'fasteners>=0.14',
        'packaging',
        'patool>=1.7',
        'tqdm',
        'annexremote',
    ],
    'downloaders': [
        'boto',
        'keyring>=20.0,!=23.9.0',
        'keyrings.alt',
        'msgpack',
        'requests>=1.2',
    ],
    'downloaders-extra': [
        'requests_ftp',
    ],
    'publish': [
        'python-gitlab',     # required for create-sibling-gitlab
    ],
    'misc': [
        'argcomplete>=1.12.3',  # optional CLI completion
        'pyperclip',         # clipboard manipulations
        'python-dateutil',   # add support for more date formats to check_dates
    ],
    'tests': [
        'BeautifulSoup4',  # VERY weak requirement, still used in one of the tests
        'httpretty>=0.9.4',  # Introduced py 3.6 support
        'mypy~=0.900',
        'pytest~=7.0',
        'pytest-cov~=3.0',
        'pytest-fail-slow~=0.2',
        'types-python-dateutil',
        'types-requests',
        'vcrpy',
    ],
    'metadata': [
        'simplejson',
        'whoosh',
    ],
    'metadata-extra': [
        'PyYAML',  # very optional
        'mutagen>=1.36',  # audio metadata
        'exifread',  # EXIF metadata
        'python-xmp-toolkit',  # XMP metadata, also requires 'exempi' to be available locally
        'Pillow',  # generic image metadata
    ],
    'duecredit': [
        'duecredit',  # needs >= 0.6.6 to be usable, but should be "safe" with prior ones
    ],
}

requires['full'] = sum(list(requires.values()), [])

# Now add additional ones useful for development
requires.update({
    'devel-docs': [
        'nose>=1.3.4',
        # used for converting README.md -> .rst for long_description
        'pypandoc',
        # Documentation
        'sphinx>=4.3.0',
        'sphinx-rtd-theme>=0.5.1"',
    ],
    'devel-utils': [
        'asv',        # benchmarks
        'coverage',
        'gprof2dot',  # rendering cProfile output as a graph image
        'psutil',
        'pytest-xdist',  # parallelize pytest runs etc
        # disable for now, as it pulls in ipython 6, which is PY3 only
        #'line-profiler',
        # necessary for accessing SecretStorage keyring (system wide Gnome
        # keyring)  but not installable on travis, IIRC since it needs connectivity
        # to the dbus whenever installed or smth like that, thus disabled here
        # but you might need it
        # 'dbus-python',
    ],
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
    # 'build_examples': BuildRSTExamplesFromScripts,
    'build_cfginfo': BuildConfigInfo,
    'build_schema': BuildSchema,
    # 'build_py': DataladBuild
}

setup_kwargs = {}

# normal entrypoints for the rest
# a bit of a dance needed, as on windows the situation is different
entry_points = {
    'console_scripts': [
        'datalad=datalad.cli.main:main',
        'git-annex-remote-datalad-archives=datalad.customremotes.archives:main',
        'git-annex-remote-datalad=datalad.customremotes.datalad:main',
        'git-annex-remote-ora=datalad.distributed.ora_remote:main',
        'git-credential-datalad=datalad.local.gitcredential_datalad:git_credential_datalad',
    ],
    'datalad.metadata.extractors': [
        'annex=datalad.metadata.extractors.annex:MetadataExtractor',
        'audio=datalad.metadata.extractors.audio:MetadataExtractor',
        'datacite=datalad.metadata.extractors.datacite:MetadataExtractor',
        'datalad_core=datalad.metadata.extractors.datalad_core:MetadataExtractor',
        'datalad_rfc822=datalad.metadata.extractors.datalad_rfc822:MetadataExtractor',
        'exif=datalad.metadata.extractors.exif:MetadataExtractor',
        'frictionless_datapackage=datalad.metadata.extractors.frictionless_datapackage:MetadataExtractor',
        'image=datalad.metadata.extractors.image:MetadataExtractor',
        'xmp=datalad.metadata.extractors.xmp:MetadataExtractor',
    ]
}
setup_kwargs['entry_points'] = entry_points

classifiers = [
    'Development Status :: 5 - Production/Stable',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'Intended Audience :: Education',
    'Intended Audience :: End Users/Desktop',
    'Intended Audience :: Science/Research',
    'License :: DFSG approved',
    'License :: OSI Approved :: MIT License',
    'Natural Language :: English',
    'Operating System :: POSIX',
    'Programming Language :: Python :: 3 :: Only',
    'Programming Language :: Unix Shell',
    'Topic :: Communications :: File Sharing',
    'Topic :: Education',
    'Topic :: Internet',
    'Topic :: Other/Nonlisted Topic',
    'Topic :: Scientific/Engineering',
    'Topic :: Software Development :: Libraries :: Python Modules',
    'Topic :: Software Development :: Version Control :: Git',
    'Topic :: Utilities',
]
setup_kwargs['classifiers'] = classifiers

setup_kwargs["version"] = versioneer.get_version()
cmdclass.update(versioneer.get_cmdclass())

datalad_setup(
    'datalad',
    description="data distribution geared toward scientific datasets",
    install_requires=
        requires['core'] + requires['downloaders'] +
        requires['publish'] + requires['metadata'],
    python_requires='>=3.7',
    project_urls={'Homepage': 'https://www.datalad.org',
                  'Developer docs': 'https://docs.datalad.org/en/stable',
                  'User handbook': 'https://handbook.datalad.org',
                  'Source': 'https://github.com/datalad/datalad',
                  'Bug Tracker': 'https://github.com/datalad/datalad/issues'},
    extras_require=requires,
    cmdclass=cmdclass,
    include_package_data=True,
    **setup_kwargs
)
