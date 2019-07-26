#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import (
    dirname,
    join as opj,
    sep as pathsep,
    splitext,
)

from setuptools import (
    findall,
    find_packages,
    setup,
)

from setup_support import (
    BuildConfigInfo,
    BuildManPage,
    BuildRSTExamplesFromScripts,
    BuildSchema,
    get_version,
    setup_entry_points,
)


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

requires = {
    'core': [
        'appdirs',
        'chardet>=3.0.4',      # rarely used but small/omnipresent
        'colorama; platform_system=="Windows"',
        'distro; python_version >= "3.8"',
        'GitPython>=2.1.8',
        'iso8601',
        'humanize',
        'fasteners',
        'mock>=1.0.1',  # mock is also used for auto.py, not only for testing
        'patool>=1.7',
        'six>=1.8.0',
        'tqdm',
        'wrapt',
    ],
    'downloaders': [
        'boto',
        'keyring>=8.0', 'keyrings.alt',
        'msgpack',
        'requests>=1.2',
    ],
    'downloaders-extra': [
        'requests_ftp',
    ],
    'publish': [
        'jsmin',             # nice to have, and actually also involved in `install`
        'PyGithub',          # nice to have
    ],
    'misc': [
        'pyperclip',         # clipboard manipulations
        'python-dateutil',   # add support for more date formats to check_dates
    ],
    'tests': [
        'BeautifulSoup4',  # VERY weak requirement, still used in one of the tests
        'httpretty>=0.8.14',
        'mock',
        'nose>=1.3.4',
        'vcrpy',
    ],
    'metadata': [
        # lzma is included in python since 3.3
        # We now support backports.lzma as well (besides AutomagicIO), but since
        # there is not way to define an alternative here (AFAIK, yoh), we will
        # use pyliblzma as the default for now.  Patch were you would prefer
        # backports.lzma instead
        'pyliblzma; python_version < "3.3"',
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
        # used for converting README.md -> .rst for long_description
        'pypandoc',
        # Documentation
        'sphinx>=1.7.8',
        'sphinx-rtd-theme',
    ],
    'devel-utils': [
        'asv',
        'nose-timer',
        'psutil',
        'coverage',
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
    'build_examples': BuildRSTExamplesFromScripts,
    'build_cfginfo': BuildConfigInfo,
    'build_schema': BuildSchema,
    # 'build_py': DataladBuild
}

# PyPI doesn't render markdown yet. Workaround for a sane appearance
# https://github.com/pypa/pypi-legacy/issues/148#issuecomment-227757822
README = opj(dirname(__file__), 'README.md')
try:
    import pypandoc
    long_description = pypandoc.convert(README, 'rst')
except (ImportError, OSError) as exc:
    # attempting to install pandoc via brew on OSX currently hangs and
    # pypandoc imports but throws OSError demanding pandoc
    print(
        "WARNING: pypandoc failed to import or thrown an error while converting"
        " README.md to RST: %r   .md version will be used as is" % exc
    )
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

# normal entrypoints for the rest
# a bit of a dance needed, as on windows the situation is different
entry_points = setup_kwargs.get('entry_points', {})
entry_points.update({
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
    ]})
setup_kwargs['entry_points'] = entry_points

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
            findsome('resources', {'sh', 'html', 'js', 'css', 'png', 'svg', 'txt', 'py'}) +
            findsome(opj('downloaders', 'configs'), {'cfg'}) +
            findsome(opj('distribution', 'tests'), {'yaml'}) +
            findsome(opj('metadata', 'tests', 'data'), {'mp3', 'jpg', 'pdf'})
    },
    **setup_kwargs
)
