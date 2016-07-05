# DataLad

DataLad aims to make data management and data distribution more accessible.  To
do that it stands on the shoulders of [Git] and [Git-annex] to deliver a
decentralized system for data exchange. This includes automated ingestion of
data from online portals, and exposing it in readily usable form as Git(-annex)
repositories, so-called datasets. The actual data storage and permission
management, however, remains with the original data providers.

# Status

DataLad is under rapid development to establish core functionality.  While
the code base is still growing the focus is increasingly shifting towards
robust and safe operation with a sensible API. There has been no major public
release yet, as organization and configuration are still subject of
considerable reorganization and standardization. However, DataLad is, in fact,
usable today and user feedback is always welcome.


See [CONTRIBUTING.md](CONTRIBUTING.md) if you are interested in
internals and/or contributing to the project.

## Code status:

* [![Travis tests status](https://secure.travis-ci.org/datalad/datalad.png?branch=master)](https://travis-ci.org/datalad/datalad) travis-ci.org (master branch)

* [![Coverage Status](https://coveralls.io/repos/datalad/datalad/badge.png?branch=master)](https://coveralls.io/r/datalad/datalad)

* [![codecov.io](https://codecov.io/github/datalad/datalad/coverage.svg?branch=master)](https://codecov.io/github/datalad/datalad?branch=master)

* [![Documentation](https://readthedocs.org/projects/datalad/badge/?version=latest)](http://datalad.rtfd.org)

# Installation

## Debian-based systems

On Debian-based systems we recommend to enable [NeuroDebian](http://neuro.debian.net)
from which we provide recent releases of DataLad.  datalad package recommends
some relatively heavy packages (e.g. scrapy) which are useful only if you are 
interested in using `crawl` functionality.  If you need just the base
functionality of the datalad, install without recommended packages
(e.g. `apt-get install --no-install-recommends datalad`)

## Other Linux'es, OSX (Windows yet TODO) via pip

By default, installation via pip installs core functionality of datalad
allowing for managing datasets etc.  Additional installation schemes
are available, so you could provide enhanced installation via
`pip install datalad[SCHEME]` where `SCHEME` could be

- crawl
     to also install scrapy which is used in some crawling constructs
- tests
     to also install dependencies used by unit-tests battery of the datalad
- full
     to install all of possible dependencies.

For installation through `pip` you would need some external dependencies
not shipped from it (e.g. `git-annex`, etc.) for which please refer to
the next section.  

## Dependencies

Our `setup.py` and corresponding packaging describes all necessary dependencies.
On Debian-based systems we recommend to enable [NeuroDebian](http://neuro.debian.net)
since we use it to provide backports of recent fixed external modules we
depend upon, and up-to-date [Git-annex] necessary for proper operation of
DataLad packaged from a standalone build.  Additionally, if you would
like to develop and run our tests battery see [CONTRIBUTING.md](CONTRIBUTING.md)
regarding additional dependencies.

Later we will provide bundled installations of DataLad across popular
platforms.


# License

MIT/Expat


# Disclaimer

It is in a alpha stage -- **nothing** is set in stone yet -- but
already usable in a limited scope.

[Git]: https://git-scm.com
[Git-annex]: http://git-annex.branchable.com
