     ____            _             _                   _ 
    |  _ \    __ _  | |_    __ _  | |       __ _    __| |
    | | | |  / _` | | __|  / _` | | |      / _` |  / _` |
    | |_| | | (_| | | |_  | (_| | | |___  | (_| | | (_| |
    |____/   \__,_|  \__|  \__,_| |_____|  \__,_|  \__,_|
                                                  Read me

[![DOI](https://joss.theoj.org/papers/10.21105/joss.03262/status.svg)](https://doi.org/10.21105/joss.03262)
[![Travis tests status](https://app.travis-ci.com/datalad/datalad.svg?branch=master)](https://app.travis-ci.com/datalad/datalad)
[![Build status](https://ci.appveyor.com/api/projects/status/github/datalad/datalad?branch=master&svg=true)](https://ci.appveyor.com/project/mih/datalad/branch/master)
[![codecov.io](https://codecov.io/github/datalad/datalad/coverage.svg?branch=master)](https://codecov.io/github/datalad/datalad?branch=master)
[![Documentation](https://readthedocs.org/projects/datalad/badge/?version=latest)](http://datalad.rtfd.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub release](https://img.shields.io/github/release/datalad/datalad.svg)](https://GitHub.com/datalad/datalad/releases/)
[![PyPI version fury.io](https://badge.fury.io/py/datalad.svg)](https://pypi.python.org/pypi/datalad/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/datalad)](https://pypi.org/project/datalad/)
[![Testimonials 4](https://img.shields.io/badge/testimonials-4-brightgreen.svg)](https://github.com/datalad/datalad/wiki/Testimonials)
[![https://www.singularity-hub.org/static/img/hosted-singularity--hub-%23e32929.svg](https://www.singularity-hub.org/static/img/hosted-singularity--hub-%23e32929.svg)](https://singularity-hub.org/collections/667)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](https://github.com/datalad/datalad/blob/master/CODE_OF_CONDUCT.md)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.5624980.svg)](https://doi.org/10.5281/zenodo.5624980)
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-39-orange.svg?style=flat-square)](#contributors-)
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

## Gentoo-based systems

On Gentoo-based systems (i.e. all systems whose package manager can parse ebuilds as per the [Package Manager Specification]), we recommend [enabling the ::science overlay], via which we
provide recent releases of DataLad. Once enabled, just run:

    emerge datalad

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
project (NIH 1P41EB019936-01A1). Mac mini instance for development is provided
by [MacStadium](https://www.macstadium.com/).

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tr>
    <td align="center"><a href="https://github.com/glalteva"><img src="https://avatars2.githubusercontent.com/u/14296143?v=4?s=100" width="100px;" alt=""/><br /><sub><b>glalteva</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=glalteva" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/adswa"><img src="https://avatars1.githubusercontent.com/u/29738718?v=4?s=100" width="100px;" alt=""/><br /><sub><b>adswa</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=adswa" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/chrhaeusler"><img src="https://avatars0.githubusercontent.com/u/8115807?v=4?s=100" width="100px;" alt=""/><br /><sub><b>chrhaeusler</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=chrhaeusler" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/soichih"><img src="https://avatars3.githubusercontent.com/u/923896?v=4?s=100" width="100px;" alt=""/><br /><sub><b>soichih</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=soichih" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/mvdoc"><img src="https://avatars1.githubusercontent.com/u/6150554?v=4?s=100" width="100px;" alt=""/><br /><sub><b>mvdoc</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=mvdoc" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/mih"><img src="https://avatars1.githubusercontent.com/u/136479?v=4?s=100" width="100px;" alt=""/><br /><sub><b>mih</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=mih" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/yarikoptic"><img src="https://avatars3.githubusercontent.com/u/39889?v=4?s=100" width="100px;" alt=""/><br /><sub><b>yarikoptic</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=yarikoptic" title="Code">💻</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/loj"><img src="https://avatars2.githubusercontent.com/u/15157717?v=4?s=100" width="100px;" alt=""/><br /><sub><b>loj</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=loj" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/feilong"><img src="https://avatars2.githubusercontent.com/u/2242261?v=4?s=100" width="100px;" alt=""/><br /><sub><b>feilong</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=feilong" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/jhpoelen"><img src="https://avatars2.githubusercontent.com/u/1084872?v=4?s=100" width="100px;" alt=""/><br /><sub><b>jhpoelen</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=jhpoelen" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/andycon"><img src="https://avatars1.githubusercontent.com/u/3965889?v=4?s=100" width="100px;" alt=""/><br /><sub><b>andycon</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=andycon" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/nicholsn"><img src="https://avatars3.githubusercontent.com/u/463344?v=4?s=100" width="100px;" alt=""/><br /><sub><b>nicholsn</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=nicholsn" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/adelavega"><img src="https://avatars0.githubusercontent.com/u/2774448?v=4?s=100" width="100px;" alt=""/><br /><sub><b>adelavega</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=adelavega" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/kskyten"><img src="https://avatars0.githubusercontent.com/u/4163878?v=4?s=100" width="100px;" alt=""/><br /><sub><b>kskyten</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=kskyten" title="Code">💻</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/TheChymera"><img src="https://avatars2.githubusercontent.com/u/950524?v=4?s=100" width="100px;" alt=""/><br /><sub><b>TheChymera</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=TheChymera" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/effigies"><img src="https://avatars0.githubusercontent.com/u/83442?v=4?s=100" width="100px;" alt=""/><br /><sub><b>effigies</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=effigies" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/jgors"><img src="https://avatars1.githubusercontent.com/u/386585?v=4?s=100" width="100px;" alt=""/><br /><sub><b>jgors</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=jgors" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/debanjum"><img src="https://avatars1.githubusercontent.com/u/6413477?v=4?s=100" width="100px;" alt=""/><br /><sub><b>debanjum</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=debanjum" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/nellh"><img src="https://avatars3.githubusercontent.com/u/11369795?v=4?s=100" width="100px;" alt=""/><br /><sub><b>nellh</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=nellh" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/emdupre"><img src="https://avatars3.githubusercontent.com/u/15017191?v=4?s=100" width="100px;" alt=""/><br /><sub><b>emdupre</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=emdupre" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/aqw"><img src="https://avatars0.githubusercontent.com/u/765557?v=4?s=100" width="100px;" alt=""/><br /><sub><b>aqw</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=aqw" title="Code">💻</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/vsoch"><img src="https://avatars0.githubusercontent.com/u/814322?v=4?s=100" width="100px;" alt=""/><br /><sub><b>vsoch</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=vsoch" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/kyleam"><img src="https://avatars2.githubusercontent.com/u/1297788?v=4?s=100" width="100px;" alt=""/><br /><sub><b>kyleam</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=kyleam" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/driusan"><img src="https://avatars0.githubusercontent.com/u/498329?v=4?s=100" width="100px;" alt=""/><br /><sub><b>driusan</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=driusan" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/overlake333"><img src="https://avatars1.githubusercontent.com/u/28018084?v=4?s=100" width="100px;" alt=""/><br /><sub><b>overlake333</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=overlake333" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/akeshavan"><img src="https://avatars0.githubusercontent.com/u/972008?v=4?s=100" width="100px;" alt=""/><br /><sub><b>akeshavan</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=akeshavan" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/jwodder"><img src="https://avatars1.githubusercontent.com/u/98207?v=4?s=100" width="100px;" alt=""/><br /><sub><b>jwodder</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=jwodder" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/bpoldrack"><img src="https://avatars2.githubusercontent.com/u/10498301?v=4?s=100" width="100px;" alt=""/><br /><sub><b>bpoldrack</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=bpoldrack" title="Code">💻</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/yetanothertestuser"><img src="https://avatars0.githubusercontent.com/u/19335420?v=4?s=100" width="100px;" alt=""/><br /><sub><b>yetanothertestuser</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=yetanothertestuser" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/christian-monch"><img src="https://avatars.githubusercontent.com/u/17925232?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Christian Mönch</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=christian-monch" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/mattcieslak"><img src="https://avatars.githubusercontent.com/u/170026?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Matt Cieslak</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=mattcieslak" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/mikapfl"><img src="https://avatars.githubusercontent.com/u/7226087?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Mika Pflüger</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=mikapfl" title="Code">💻</a></td>
    <td align="center"><a href="https://me.ypid.de/"><img src="https://avatars.githubusercontent.com/u/1301158?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Robin Schneider</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=ypid" title="Code">💻</a></td>
    <td align="center"><a href="https://orcid.org/0000-0003-4652-3758"><img src="https://avatars.githubusercontent.com/u/7570456?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Sin Kim</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=AKSoo" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/DisasterMo"><img src="https://avatars.githubusercontent.com/u/49207524?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Michael Burgardt</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=DisasterMo" title="Code">💻</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://remi-gau.github.io/"><img src="https://avatars.githubusercontent.com/u/6961185?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Remi Gau</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=Remi-Gau" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/mslw"><img src="https://avatars.githubusercontent.com/u/11985212?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Michał Szczepanik</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=mslw" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/bpinsard"><img src="https://avatars.githubusercontent.com/u/1155388?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Basile</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=bpinsard" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/taylols"><img src="https://avatars.githubusercontent.com/u/28018084?v=4?s=100" width="100px;" alt=""/><br /><sub><b>Taylor Olson</b></sub></a><br /><a href="https://github.com/datalad/datalad/commits?author=taylols" title="Code">💻</a></td>
  </tr>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

[![macstadium](https://uploads-ssl.webflow.com/5ac3c046c82724970fc60918/5c019d917bba312af7553b49_MacStadium-developerlogo.png)](https://www.macstadium.com/)

[Git]: https://git-scm.com
[Git-annex]: http://git-annex.branchable.com
[setup.py]: https://github.com/datalad/datalad/blob/master/setup.py
[NeuroDebian]: http://neuro.debian.net
[Package Manager Specification]: https://projects.gentoo.org/pms/latest/pms.html
[enabling the ::science overlay]: https://github.com/gentoo/sci#manual-install-

[DataLad Handbook: Installation]: http://handbook.datalad.org/en/latest/intro/installation.html
