     ____            _             _                   _ 
    |  _ \    __ _  | |_    __ _  | |       __ _    __| |
    | | | |  / _` | | __|  / _` | | |      / _` |  / _` |
    | |_| | | (_| | | |_  | (_| | | |___  | (_| | | (_| |
    |____/   \__,_|  \__|  \__,_| |_____|  \__,_|  \__,_|
                                                  Read me

[![Travis tests status](https://travis-ci.com/datalad/datalad.png?branch=master)](https://travis-ci.com/datalad/datalad)
[![Build status](https://ci.appveyor.com/api/projects/status/github/datalad/datalad?branch=master&svg=true)](https://ci.appveyor.com/project/mih/datalad/branch/master)
[![codecov.io](https://codecov.io/github/datalad/datalad/coverage.svg?branch=master)](https://codecov.io/github/datalad/datalad?branch=master)
[![Documentation](https://readthedocs.org/projects/datalad/badge/?version=latest)](http://datalad.rtfd.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub release](https://img.shields.io/github/release/datalad/datalad.svg)](https://GitHub.com/datalad/datalad/releases/)
[![PyPI version fury.io](https://badge.fury.io/py/datalad.svg)](https://pypi.python.org/pypi/datalad/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/datalad)](https://pypi.org/project/datalad/)
[![Testimonials 4](https://img.shields.io/badge/testimonials-4-brightgreen.svg)](https://github.com/datalad/datalad/wiki/Testimonials)
[![https://www.singularity-hub.org/static/img/hosted-singularity--hub-%23e32929.svg](https://www.singularity-hub.org/static/img/hosted-singularity--hub-%23e32929.svg)](https://singularity-hub.org/collections/667) [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.3233911.svg)](https://doi.org/10.5281/zenodo.3233911)
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
<!-- ALL-CONTRIBUTORS-BADGE:END -->


# 10000-ft. overview

DataLad makes data management and data distribution more accessible.
To do that, it stands on the shoulders of [Git] and [Git-annex] to deliver a
decentralized system for data exchange. This includes automated ingestion of
data from online portals and exposing it in readily usable form as Git(-annex)
repositories, so-called datasets. The actual data storage and permission
management, however, remains with the original data providers.

The full documentation is available at http://docs.datalad.org and
http://handbook.datalad.org provides a hands-on crash-course on DataLad.

# Extensions

A number of extensions are available that provide additional functionality for
DataLad. Extensions are separate packages that are to be installed in addition
to DataLad. In order to install DataLad customized for a particular domain, one
can simply install an extension directly, and DataLad itself will be
automatically installed with it. An [annotated list of
extensions](http://handbook.datalad.org/extension_pkgs.html) is available in
the [DataLad handbook](http://handbook.datalad.org).


# Support

The documentation for this project is found here:
http://docs.datalad.org

All bugs, concerns, and enhancement requests for this software can be submitted here:
https://github.com/datalad/datalad/issues

If you have a problem or would like to ask a question about how to use DataLad,
please [submit a question to
NeuroStars.org](https://neurostars.org/new-topic?body=-%20Please%20describe%20the%20problem.%0A-%20What%20steps%20will%20reproduce%20the%20problem%3F%0A-%20What%20version%20of%20DataLad%20are%20you%20using%20%28run%20%60datalad%20--version%60%29%3F%20On%20what%20operating%20system%20%28consider%20running%20%60datalad%20plugin%20wtf%60%29%3F%0A-%20Please%20provide%20any%20additional%20information%20below.%0A-%20Have%20you%20had%20any%20luck%20using%20DataLad%20before%3F%20%28Sometimes%20we%20get%20tired%20of%20reading%20bug%20reports%20all%20day%20and%20a%20lil'%20positive%20end%20note%20does%20wonders%29&tags=datalad)
with a `datalad` tag.  NeuroStars.org is a platform similar to StackOverflow
but dedicated to neuroinformatics.

All previous DataLad questions are available here:
http://neurostars.org/tags/datalad/


# Installation

## Debian-based systems

On Debian-based systems, we recommend enabling [NeuroDebian], via which we
provide recent releases of DataLad. Once enabled, just do:

    apt-get install datalad

## Other Linux'es via conda

    conda install -c conda-forge datalad

will install the most recently released version, and release candidates are
available via

    conda install -c conda-forge/label/rc datalad

## Other Linux'es, macOS via pip

Before you install this package, please make sure that you [install a recent
version of git-annex](https://git-annex.branchable.com/install).  Afterwards,
install the latest version of `datalad` from
[PyPI](https://pypi.org/project/datalad). It is recommended to use
a dedicated [virtualenv](https://virtualenv.pypa.io):

    # Create and enter a new virtual environment (optional)
    virtualenv --python=python3 ~/env/datalad
    . ~/env/datalad/bin/activate

    # Install from PyPI
    pip install datalad

By default, installation via pip installs the core functionality of DataLad,
allowing for managing datasets etc.  Additional installation schemes
are available, so you can request enhanced installation via
`pip install datalad[SCHEME]`, where `SCHEME` could be:

- `tests`
     to also install dependencies used by DataLad's battery of unit tests
- `full`
     to install all dependencies.

More details on installation and initial configuration can be found in the
[DataLad Handbook: Installation].

# License

MIT/Expat


# Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) if you are interested in internals or
contributing to the project. 

## Acknowledgements

DataLad development is supported by a US-German collaboration in computational
neuroscience (CRCNS) project "DataGit: converging catalogues, warehouses, and
deployment logistics into a federated 'data distribution'" (Halchenko/Hanke),
co-funded by the US National Science Foundation (NSF 1429999) and the German
Federal Ministry of Education and Research (BMBF 01GQ1411). Additional support
is provided by the German federal state of Saxony-Anhalt and the European
Regional Development Fund (ERDF), Project: Center for Behavioral Brain
Sciences, Imaging Platform.  This work is further facilitated by the ReproNim
project (NIH 1P41EB019936-01A1).

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- ALL-CONTRIBUTORS-LIST:END -->


[Git]: https://git-scm.com
[Git-annex]: http://git-annex.branchable.com
[setup.py]: https://github.com/datalad/datalad/blob/master/setup.py
[NeuroDebian]: http://neuro.debian.net

[DataLad Handbook: Installation]: http://handbook.datalad.org/en/latest/intro/installation.html
