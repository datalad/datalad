#!/usr/bin/env python

import os.path as op
from setuptools import setup
from setuptools import find_packages


def get_version():
    """Load version of datalad from version.py without entailing any imports
    """
    # This might entail lots of imports which might not yet be available
    # so let's do ad-hoc parsing of the version.py
    with open(op.join(op.dirname(__file__),
                      'datalad_revolution',
                      'version.py')) as f:
        version_lines = list(filter(lambda x: x.startswith('__version__'), f))
    assert (len(version_lines) == 1)
    return version_lines[0].split('=')[1].strip(" '\"\t\n")


# PyPI doesn't render markdown yet. Workaround for a sane appearance
# https://github.com/pypa/pypi-legacy/issues/148#issuecomment-227757822
README = op.join(op.dirname(__file__), 'README.md')
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


setup(
    name="datalad_revolution",
    author="The DataLad Team and Contributors",
    author_email="team@datalad.org",
    version=get_version(),
    description="Revolutionary DataLad extension package",
    long_description=long_description,
    packages=[pkg for pkg in find_packages('.') if pkg.startswith('datalad')],
    install_requires=[
        'datalad',
        'pathlib2; python_version < "3.0"',
    ],
    entry_points = {
        'datalad.extensions': [
            'revolution=datalad_revolution:command_suite',
        ],
        'datalad.tests': [
            'revolution=datalad_revolution',
        ],
        'datalad.metadata.extractors': [
            'custom=datalad_revolution.metadata.extractors.custom:MetadataExtractor',
        ],
    },
)
