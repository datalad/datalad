.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_basic_principles:

****************
Basic principles
****************

DataLad was designed so it could be used both as a command-line tool, and as
a Python module. Sections following this one (:ref:`chap_cmdline` and :ref:`chap_modref`)
provide detailed description of the commands and functions of the two interfaces.  This section
presents common concepts.  Although examples will be presented using command line
interface commands, all functionality with identically named functions and options
are available through Python API.

Distribution
============

Organization
------------

DataLad "distribution" is just a :term:`superdataset` which organizes multiple
:term:`dataset`'s using standard git mechanism of sub-modules.

install vs get
--------------

``install`` and ``get`` commands, both in Python and command line interfaces, might
seem confusingly similar at first. Both of them could be used to install
any number of subdatasets, and fetch content of the data files.  Differences lie
primarily in their default behaviour and outputs, and thus intended use.
Both ``install`` and ``get`` take local paths as their arguments, but their
default behavior and output might differ;

- **install** primarily operates and reports at the level of **datasets**, and
  returns as a result dataset(s)
  which either were just installed, or were installed previously already under
  specified locations.   So result should be the same if the same ``install``
  command ran twice on the same datasets.  It **does not fetch** data files by
  default

- **get** primarily operates at the level of **paths** (datasets, directories, and/or
  files). As a result it returns only what was installed (datasets) or fetched
  (files).  So result of rerunning the same ``get`` command should report that
  nothing new was installed or fetched.  It **fetches** data files by default.

In how both commands operate on provided paths, it could be said that
``install == get -n``, and ``install -g == get``.  But ``install`` also has ability to
install new datasets from remote locations given their URLs (e.g.,
``http://datasets.datalad.org/`` for our super-dataset) and SSH targets (e.g.,
``[login@]host:path``) if they are provided as the argument to its call or
explicitly as ``--source`` option.  If ``datalad install --source URL DESTINATION`` (command
line example) is used, then dataset from URL gets installed under PATH. In case of
``datalad install URL`` invocation, PATH is taken from the last name within URL similar to
how ``git clone`` does it.  If former specification allows to specify only a single
URL and a PATH at a time, later one can take multiple remote locations from which
datasets could be installed.

So, as a rule of thumb -- if you want to install from external URL or fetch a
sub-dataset without downloading data files stored under annex -- use ``install``.
In Python API ``install`` is also to be used when you want to receive in output the
corresponding Dataset object to operate on, and be able to use it even if you
rerun the script.
If you would like to fetch data (possibly while installing any necessary to be
installed sub-dataset to get to the file) -- use ``get``.


URL shortcuts
-------------

``///`` could be used to point to our canonical :term:`superdataset` at
http://datasets.datalad.org/ , which is largely generated through automated
crawling (see :ref:`chap_crawler`) of data portals.  Some common examples in command line
interface:

``datalad install ///``
    install our canonical super-dataset (alone, no sub-datasets installed during
    this command) under `datasets.datalad.org/` directory in your current directory
``datalad install -r ///openfmri``
    install openfmri super-dataset from our website, with all sub-datasets
    under `openfmri/` directory in your current directory
``datalad install -g -J3 -r ///labs/haxby``
    install Dr. James V. Haxby lab's super-dataset with all sub-datasets, while
    fetching all data files (present in current version) in 3 parallel processes.


Dataset argument
----------------

All commands which operate with/on datasets (e.g., `install`, `uninstall`, etc.)
have `dataset` argument (`-d` or `--dataset` in command line) which takes path
to the dataset you want to operate on. If you specify a dataset explicitly,
then any relative path you provide as an argument to the command will be taken
relative to the top directory of that dataset.  If no dataset argument is
provided, relative paths are taken relative to the current directory.

There are also some "shortcut" values for dataset argument you might find useful:

``///``
   "central" dataset located under `$HOME/datalad/`.  You could install it by running
   ```datalad install -s /// $HOME/datalad``` or simply by running
   ```datalad search smth``` in interactive shell session outside of any dataset,
   which will present you with a choice to install it for you.
   So running ``datalad install -d/// crcns`` will install crcns subdataset
   under your `$HOME/datalad/crcns`.  It is analogous to running
   ```datalad install $HOME/datalad/crcns```.
``^``
   top-most super-dataset containing dataset of your current location.  E.g., if
   you are under `$HOME/datalad/openfmri/ds000001/sub-01` directory and want to
   search meta-data of the entire super-dataset you are under (in this case `///`), run
   ``datalad search -d^ [something to search]``.