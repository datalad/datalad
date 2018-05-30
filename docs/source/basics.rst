.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_basic_principles:

****************
Basic principles
****************

DataLad is designed to be used both as a command-line tool, and as a Python
module. The sections :ref:`chap_cmdline` and :ref:`chap_modref` provide
detailed description of the commands and functions of the two interfaces.  This
section presents common concepts.  Although examples will frequently be
presented using command line interface commands, all functionality with
identically named functions and options are available through Python API as
well.

Datasets
========

A DataLad :term:`dataset` is a Git repository that may or may not have a data
:term:`annex` that is used to manage data referenced in a dataset. In practice,
most DataLad datasets will come with an annex.

Dataset nesting
---------------

Datasets can contain other datasets (:term:`subdataset`\s), which can in turn
contain subdatasets, and so on. There is no limit to the depth of nesting
datasets. Each dataset in such a hierarchy has its own annex and its own
history. The parent or :term:`superdataset` only tracks the specific state of a
subdataset, and information on where it can be obtained. This is a powerful yet
lightweight mechanism for combining multiple individual datasets for a specific
purpose, such as the combination of source code repositories with other
resources for a tailored application. In many cases DataLad can work with a
hierarchy of datasets just as if it were a single dataset. Here is a demo:

.. include:: basics_nesteddatasets.rst.in
   :start-after: Let's create a dataset
   :end-before:  ___________________________


Dataset collections
-------------------

A superdataset can also be seen as a curated collection of datasets, for example,
for a certain data modality, a field of science, a certain author, or from
one project (maybe the resource for a movie production). This lightweight
coupling between super and subdatasets enables scenarios where individual datasets
are maintained by a disjoint set of people, and the dataset collection itself can
be curated by a completely independent entity. Any individual dataset can be
part of any number of such collections.

Benefiting from Git's support for workflows based on decentralized "clones" of
a repository, DataLad's datasets can be (re-)published to a new location
without loosing the connection between the "original" and the new "copy". This
is extremely useful for collaborative work, but also in more mundane scenarios
such as data backup, or temporary deployment fo a dataset on a compute cluster,
or in the cloud.  Using git-annex, data can also get synchronized across
different locations of a dataset (:term:`sibling`\s in DataLad terminology).
Using metadata tags, it is even possible to configure different levels of
desired data redundancy across the network of dataset, or to prevent
publication of sensitive data to publicly accessible repositories. Individual
datasets in a hierarchy of (sub)datasets need not be stored at the same location.
Continuing with an earlier example, it is possible to post a curated
collection of datasets, as a superdataset, on Github, while the actual datasets
live on different servers all around the world.

Basic command line usage
========================

.. include:: basics_cmdline.rst.in
   :end-before:  ___________________________


API principles
==============

You can use DataLad's ``install`` command to download datasets. The command accepts
URLs of different protocols (``http``, ``ssh``) as an argument. Nevertheless, the easiest way
to obtain a first dataset is downloading the canonical :term:`superdataset` from
http://datasets.datalad.org/ using a shortcut.

Downloading DataLad's canonical superdataset
--------------------------------------------

DataLad's canonical :term:`superdataset` provides an automated collection of datasets
from various portals and sites. The argument ``///`` can be used 
as a shortcut that points to the superdataset located at http://datasets.datalad.org/. 
Here are three common examples in command line notation:

``datalad install ///``
    installs the canonical superdataset (metadata without subdatasets) in a
    `datasets.datalad.org/` subdirectory under the current directory
``datalad install -r ///openfmri``
    installs the openfmri superdataset into an `openfmri/` subdirectory.
    Additionally, the ``-r`` flag recursively downloads all metadata of datasets 
    available from http://openfmri.org as subdatasets into the `openfmri/` subdirectory
``datalad install -g -J3 -r ///labs/haxby``
    installs the superdataset of datasets released by the lab of Dr. James V. Haxby
    and all subdatasets' metadata. The ``-g`` flag indicates getting the actual data, too.
    It does so by using 3 parallel download processes (``-J3`` flag).

Downloading datasets via http
-----------------------------

In most places where DataLad accepts URLs as arguments these URLs can be
regular ``http`` or ``https`` protocol URLs. For example:

``datalad install https://github.com/psychoinformatics-de/studyforrest-data-phase2.git``

Downloading datasets via ssh
----------------------------
DataLad also supports SSH URLs, such as ``ssh://me@localhost/path``.

``datalad install ssh://me@localhost/path``

Finally, DataLad supports SSH login style resource identifiers, such as ``me@localhost:/path``.

``datalad install me@localhost:/path``

`--dataset` argument
--------------------

All commands which operate with/on datasets (practically all commands) have a
``dataset`` argument (``-d`` or ``--dataset`` for the command line API) which takes a
path to the dataset that the command should operate on. If a dataset is
identified this way then any relative path that is provided as an argument to
the command will be interpreted as being relative to the topmost directory of that
dataset.  If no dataset argument is provided, relative paths are considered to be
relative to the current directory.

There are also some useful pre-defined "shortcut" values for dataset arguments:

``///``
   refers to the "canonical" dataset located under `$HOME/datalad/`.
   So running ``datalad install -d/// crcns`` will install the ``crcns`` subdataset
   under ``$HOME/datalad/crcns``.  This is the same as running
   ``datalad install $HOME/datalad/crcns``.
``^``
   topmost superdataset containing the dataset the current directory is part of.
   For example, if you are in ``$HOME/datalad/openfmri/ds000001/sub-01`` and want
   to search metadata of the entire superdataset you are under (in this case
   ``///``), run ``datalad search -d^ [something to search]``.

Commands `install` vs `get`
---------------------------

The ``install`` and ``get`` commands might seem confusingly similar at first.
Both of them could be used to install any number of subdatasets, and fetch
content of the data files.  Differences lie primarily in their default
behaviour and outputs, and thus intended use.  Both ``install`` and ``get``
take local paths as their arguments, but their default behavior and output
might differ;

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

In how both commands operate on provided paths, it could be said that ``install
== get -n``, and ``install -g == get``.  But ``install`` also has ability to
install new datasets from remote locations given their URLs (e.g.,
``http://datasets.datalad.org/`` for our super-dataset) and SSH targets (e.g.,
``[login@]host:path``) if they are provided as the argument to its call or
explicitly as ``--source`` option.  If ``datalad install --source URL
DESTINATION`` (command line example) is used, then dataset from URL gets
installed under PATH. In case of ``datalad install URL`` invocation, PATH is
taken from the last name within URL similar to how ``git clone`` does it.  If
former specification allows to specify only a single URL and a PATH at a time,
later one can take multiple remote locations from which datasets could be
installed.

So, as a rule of thumb -- if you want to install from external URL or fetch a
sub-dataset without downloading data files stored under annex -- use ``install``.
In Python API ``install`` is also to be used when you want to receive in output the
corresponding Dataset object to operate on, and be able to use it even if you
rerun the script. In all other cases, use ``get``.
