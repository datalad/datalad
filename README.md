# DataLad

DataLad aims to deliver a data distribution.  Original motive was to provide
a platform for harvesting data from online portals and
exposing collected data in a readily-usable form from [Git-annex]
repositories, while fetching data load from the original data providers.

# Status

It is currently in a heavy initial development mode to establish core
functionality which could be used by others.  Codebase is
rapidly growing, functionality is usable for many use-cases but not
yet officially released to public since its organization and
configuration will be a subject for a considerable reorganization and
standardization.  Primary purpose of the development is to catch major
use-cases and try to address them to get a better understanding of the
ultimate specs and design.

See [CONTRIBUTING.md](CONTRIBUTING.md) if you are interested in
internals and/or contributing to the project.

## Code status:

* [![Travis tests status](https://secure.travis-ci.org/datalad/datalad.png?branch=master)](https://travis-ci.org/datalad/datalad) travis-ci.org (master branch)

* [![Coverage Status](https://coveralls.io/repos/datalad/datalad/badge.png?branch=master)](https://coveralls.io/r/datalad/datalad)

* [![codecov.io](https://codecov.io/github/datalad/datalad/coverage.svg?branch=master)](https://codecov.io/github/datalad/datalad?branch=master)

* [![Documentation](https://readthedocs.org/projects/datalad/badge/?version=latest)](http://datalad.rtfd.org)

# Dependencies

Although we now support Python 3 (>= 3.3), primarily we still use Python 2.7
and thus instructions below are for python 2.7 deployments. 
On Debian-based systems we recommend to enable
[NeuroDebian](http://neuro.debian.net) since we use it to provide
backports of recent fixed external modules we depend upon:

```sh
apt-get install patool python-bs4 python-git python-testtools python-mock python-nose git-annex-standalone
```

or otherwise you can use pip to install Python modules

```sh
pip install -r requirements.txt
```

and will need to install recent git-annex using appropriate for your
OS means (for Debian/Ubuntu, once again, just use NeuroDebian).  We
later will provide bundled installations of DataLad across popular
platforms.


# License

MIT/Expat


# Disclaimer

It is in a prototype stage -- **nothing** is set in stone yet -- but
already usable in a limited scope.

[Git-annex]: http://git-annex.branchable.com
