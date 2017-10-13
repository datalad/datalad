     ____            _             _                   _ 
    |  _ \    __ _  | |_    __ _  | |       __ _    __| |
    | | | |  / _` | | __|  / _` | | |      / _` |  / _` |
    | |_| | | (_| | | |_  | (_| | | |___  | (_| | | (_| |
    |____/   \__,_|  \__|  \__,_| |_____|  \__,_|  \__,_|
                                                  Read me

[![Travis tests status](https://secure.travis-ci.org/datalad/datalad.png?branch=master)](https://travis-ci.org/datalad/datalad) [![codecov.io](https://codecov.io/github/datalad/datalad/coverage.svg?branch=master)](https://codecov.io/github/datalad/datalad?branch=master) [![Documentation](https://readthedocs.org/projects/datalad/badge/?version=latest)](http://datalad.rtfd.org)

The full documentation is available at: http://docs.datalad.org

# 10000ft overview

DataLad makes data management and data distribution more accessible.
To do that it stands on the shoulders of [Git] and [Git-annex] to deliver a
decentralized system for data exchange. This includes automated ingestion of
data from online portals, and exposing it in readily usable form as Git(-annex)
repositories, so-called datasets. The actual data storage and permission
management, however, remains with the original data providers.

# Status

DataLad is under rapid development.  While the code base is still growing,
the focus is increasingly shifting towards robust and safe operation 
with a sensible API. Organization and configuration are still subject of 
considerable reorganization and standardization.  However, DataLad is, 
in fact, usable today and user feedback is always welcome.

# Support

[Neurostars](https://neurostars.org) is the preferred venue for DataLad
support.  Forum login is possible with your existing Google, Twitter, or GitHub
account.  Before posting a [new
topic](https://neurostars.org/new-topic?tags=datalad), please check the
[previous posts](https://neurostars.org/search?q=tags%3Adatalad) tagged with
`#datalad`. To get help on a datalad-related issue, please consider to follow
this [message
template](https://neurostars.org/new-topic?body=-%20Please%20describe%20the%20problem.%0A-%20What%20steps%20will%20reproduce%20the%20problem%3F%0A-%20What%20version%20of%20DataLad%20are%20you%20using%20%28run%20%60datalad%20--version%60%29%3F%20On%20what%20operating%20system%20%28consider%20running%20%60datalad%20plugin%20wtf%60%29%3F%0A-%20Please%20provide%20any%20additional%20information%20below.%0A-%20Have%20you%20had%20any%20luck%20using%20DataLad%20before%3F%20%28Sometimes%20we%20get%20tired%20of%20reading%20bug%20reports%20all%20day%20and%20a%20lil'%20positive%20end%20note%20does%20wonders%29&tags=datalad).

# DataLad 101

A growing number of datasets is made available from http://datasets.datalad.org .
Those datasets are just regular git/git-annex repositories organized into
a hierarchy using git submodules mechanism.  So you can use regular
git/git-annex commands to work with them, but might need `datalad` to be
installed to provide additional functionality (e.g., fetching from
portals requiring authentication such as CRCNS, HCP; or accessing data
originally distributed in tarballs).  But datalad aims to provide higher
level interface on top of git/git-annex to simplify consumption and sharing
of new or derived datasets.  To that end, you can install **all** of
those datasets using

    datalad install -r ///

which will `git clone` all of those datasets under `datasets.datalad.org`
sub-directory. This command will not fetch any large data files, but will
merely recreate full hierarchy of all of those datasets locally, which
also takes a good chunk of your filesystem meta-data storage.  Instead of
fetching all datasets at once you could either specify specific dataset to
be installed, e.g.

    datalad install ///openfmri/ds000113

or install top level dataset by omitting `-r` option and then calling
`datalad install` for specific sub-datasets you want to have installed,
possibly with `-r` to install their sub-datasets as well, e.g.

    datalad install ///
    cd datasets.datalad.org
    datalad install -r openfmri/ds000001 indi/fcon1000

You can navigate datasets you have installed in your terminal or browser,
while fetching necessary files or installing new sub-datasets using the
`datalad get [FILE|DIR]` command.  DataLad will take care about
downloading, extracting, and possibly authenticating (would ask you for
credentials) in a uniform fashion regardless of the original data location
or distribution serialization (e.g., a tarball).  Since it is using git
and git-annex underneath, you can be assured that you are getting **exact**
correct version of the data.

Use-cases DataLad covers are not limited to "consumption" of data.
DataLad aims also to help publishing original or derived data, thus facilitating
more efficient data management when collaborating or simply sharing your data.
You can find more documentation at http://docs.datalad.org .


# Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) if you are interested in internals or
contributing to the project.

# Installation

## Debian-based systems

On Debian-based systems we recommend to enable [NeuroDebian]
from which we provide recent releases of DataLad.  datalad package recommends
some relatively heavy packages (e.g. scrapy) which are useful only if you are
interested in using `crawl` functionality.  If you need just the base
functionality of the datalad, install without recommended packages
(e.g., `apt-get install --no-install-recommends datalad`)

## Other Linux'es, OSX (Windows yet TODO) via pip

By default, installation via pip installs core functionality of datalad
allowing for managing datasets etc.  Additional installation schemes
are available, so you could provide enhanced installation via
`pip install datalad[SCHEME]` where `SCHEME` could be

- `crawl`
     to also install `scrapy` which is used in some crawling constructs
- `tests`
     to also install dependencies used by unit-tests battery of the datalad
- `full`
     to install all dependencies.

For installation through `pip` you would need some external dependencies
not shipped from it (e.g. `git-annex`, etc.) for which please refer to
the next section.

## Dependencies

Our [setup.py] and accompanying packaging describe all necessary dependencies.
On Debian-based systems we recommend to enable [NeuroDebian]
since we use it to provide backports of recent fixed external modules we
depend upon, and up-to-date [Git-annex] is necessary for proper operation of
DataLad packaged (install `git-annex-standalone` from NeuroDebian repository).
Additionally, if you would like to develop and run our tests battery see
[CONTRIBUTING.md](CONTRIBUTING.md) regarding additional dependencies.

Later we will provide bundled installations of DataLad across popular
platforms.


# License

MIT/Expat


# Disclaimer

It is in a alpha stage -- **nothing** is set in stone yet -- but
already usable in a limited scope.

[Git]: https://git-scm.com
[Git-annex]: http://git-annex.branchable.com
[setup.py]: https://github.com/datalad/datalad/blob/master/setup.py
[NeuroDebian]: http://neuro.debian.net
