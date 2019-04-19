.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_gettingstarted:

***************
Getting started
***************

Installation
============

When there isn't anything more convenient
-----------------------------------------

Unless system packages are available for your operating system (see below), DataLad
can be installed via pip_ (**P**\ip **I**\nstalls **P**\ython). To automatically install 
datalad with all its Python dependencies type::

  pip install datalad

.. _pip: https://pip.pypa.io

In addition, it is necessary to have a current version of git-annex_ installed
which is not set up automatically by using the pip method.

.. _git-annex: http://git-annex.branchable.com

.. note::

  If you do not have admin powers...

  ``pip`` supports installation into a user's home directory with ``--user``.
  Git-annex can be deployed by extracting pre-built binaries from a tarball
  (that also includes an up-to-date Git installation).  `Obtain the tarball
  <https://downloads.kitenet.net/git-annex/linux/current/>`_, extract it, and
  set the :envvar:`PATH` environment variable to include the root of the
  extracted tarball. Fingers crossed and good luck!

Advanced users can chose from several installation schemes (e.g.
``publish``, ``metadata``, ``tests`` or ``crawl``)::

  pip install datalad[SCHEME]
  
where ``SCHEME`` could be

- ``crawl`` to also install `scrapy` which is used in some crawling constructs
- ``tests`` to also install dependencies used by unit-tests battery of the datalad
- ``full`` to install all dependencies


(Neuro)Debian, Ubuntu, and similar systems
------------------------------------------

For Debian-based operating systems the most convenient installation method
is to enable the NeuroDebian_ repository. The following command installs datalad
and all its software dependencies (including the git-annex-standalone package)::

  sudo apt-get install datalad
  
.. _neurodebian: http://neuro.debian.net


MacOSX
------

A simple way to get things installed is the homebrew_ package manager, which in
itself is fairly easy to install. Git-annex is installed by the command::

  brew install git-annex

Once Git-annex is available, datalad can be installed via ``pip`` as described
above. ``pip`` comes with Python distributions like anaconda_.

.. _homebrew: http://brew.sh
.. _anaconda: https://www.continuum.io/downloads


HPC environments or any system with singularity installed
---------------------------------------------------------

If you want to use DataLad in a high-performance computing (HPC) environment,
such as a computer cluster, or a similar multi-user machine, where you don't have
admin privileges, chances are that `Singularity <http://singularity.lbl.gov>`_
is installed. Even if it isn't installed, singularity helps you make a `solid
case <http://singularity.lbl.gov/install-request>`_ why your admin might want
to install it.

On any system with Singularity installed, you can pull a container with a full
installation of DataLad (~300 MB) straight from `Singularity Hub`_. The
following command pulls the latest container for the DataLad development version
(check on `Singularity Hub`_ for alternative container variants)::

  singularity pull shub://datalad/datalad:fullmaster

This will produce an executable image file. You can rename this image to ``datalad``,
and put the directory it is located in into your :envvar:`PATH` environment variable.
From there on, you will have a ``datalad`` command in the commandline that transparently
executes all DataLad functionality in the container.

With Singularity version 2.4.2 you can choose the image name directly in the download
command::

  singularity pull --name datalad shub://datalad/datalad:fullmaster


.. _Singularity Hub: https://singularity-hub.org/collections/667


First steps
===========

DataLad can be queried for information about known datasets. Doing a first search
query, datalad automatically offers assistence to obtain a :term:`superdataset` first.
The superdataset is a lightweight container that contains meta information about known datasets but does not contain actual data itself. 

For example, we might want to look for datasets that were funded by, or acknowledge the US National Science Foundation (NSF)::

  ~ % datalad search NSF
  No DataLad dataset found at current location
  Would you like to install the DataLad superdataset at '/home/yoh/datalad'? (choices: yes, no): yes
  [INFO   ] Cloning http://datasets.datalad.org/ to '/home/yoh/datalad'
  From now on you can refer to this dataset using the label '///'
  [INFO   ] Performing search using DataLad superdataset '/home/yoh/datalad'
  search(ok): /home/yoh/datalad/crcns/cai-2 (dataset)
  search(ok): /home/yoh/datalad/crcns/hc-11 (dataset)
  search(ok): /home/yoh/datalad/hbnssi (dataset)
  search(ok): /home/yoh/datalad/labs/haxby/attention (dataset)
  search(ok): /home/yoh/datalad/labs/haxby/life (dataset)
  search(ok): /home/yoh/datalad/openfmri/ds000001 (dataset)
  search(ok): /home/yoh/datalad/openfmri/ds000002 (dataset)
  ...

Any known dataset can now be installed inside the local superdataset with a
command like this::

  datalad install ///openfmri/ds000002

Now, have a look at the `demos on the DataLad website
<http://datalad.org/features.html>`_, some :ref:`common data management
scenarios <chap_usecases>`, and a bit of background info on the
:ref:`fundamental concepts <chap_basic_principles>` the DataLad API(s) are built
on.
