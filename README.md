# DataLad

DataLad aims to deliver a data distribution.  Original motive was to provide
a platform for harvesting data from online portals and
exposing collected data in a readily-usable form from [Git-annex]
repositories, while fetching data load from the original data providers.

# Status

It is currently in a "prototype" state, i.e. **a mess**.  Codebase is
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


# Dependencies

On Debian-based systems we recommend to enable
[NeuroDebian](http://neuro.debian.net) since we use it to provide
backports of recent fixed external modules we depend upon:

```sh
apt-get install patool python-bs4 python-git python-joblib git-annex-standalone
```

or otherwise you can use pip to install Python modules

```sh
pip install -r requirements.txt
```

and will need to install recent git-annex using appropriate for your
OS means.  We later will provide bundled installations of DataLad
across popular platforms.


# License

MIT/Expat


# Disclaimer

It is in a prototype stage -- **nothing** is set in stone yet -- but
already usable in a limited scope.

[Git-annex]: http://git-annex.branchable.com
