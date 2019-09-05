#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import (
    join as opj,
)

from _datalad_build_support.setup import (
    BuildConfigInfo,
    BuildManPage,
    BuildRSTExamplesFromScripts,
    BuildSchema,
    setup_entry_points,
    findsome,
    datalad_setup,
)


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
        'asv',        # benchmarks
        'gprof2dot',  # rendering cProfile output as a graph image
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

datalad_setup(
    'datalad',
    description="data distribution geared toward scientific datasets",
    install_requires=
        requires['core'] + requires['downloaders'] +
        requires['publish'] + requires['metadata'],
    python_requires='>=3.5',
    extras_require=requires,
    cmdclass=cmdclass,
    package_data={
        'datalad':
            findsome('resources',
                     {'sh', 'html', 'js', 'css', 'png', 'svg', 'txt', 'py'}) +
            findsome(opj('downloaders', 'configs'), {'cfg'}) +
            findsome(opj('distribution', 'tests'), {'yaml'}) +
            findsome(opj('metadata', 'tests', 'data'), {'mp3', 'jpg', 'pdf'})
    },
    classifiers=[
        'Programming Language :: Python :: 3 :: Only'
    ],
    **setup_kwargs
)