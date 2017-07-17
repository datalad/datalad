.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_gettingstarted:

***************
Getting started
***************

Installation
============

Datalad is a Python package and can be installed via pip_, which is the
preferred method unless system packages are available for the target platform
(see below). To automatically install datalad and all its software dependencies
type::

  pip install datalad

.. _pip: https://pip.pypa.io

Several additional installation schemes are supported (``[SCHEME]`` can be e.g.
``publish``, ``metadata``, ``tests`` or ``crawl``)::

  pip install datalad [SCHEME]
  
.. cool, but why should I (or a first-time reader) even bother about the schemes?

In addition, it is necessary to have a working installation of git-annex_,
which is not set up automatically at this point.

.. _git-annex: http://git-annex.branchable.com

(Neuro)Debian, Ubuntu, and similar systems
------------------------------------------

For Debian-based operating systems the most convenient installation method
is to enable the NeuroDebian_ repository, and to install datalad as a system
package::

  sudo apt-get install datalad
  
A current version of git-annex (as also provided by the NeuroDebian_ 
repository) can be installed by typing::

  sudo apt-get install git-annex

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


First steps
===========

Datalad can be queried for information about known datasets. Doing a first search 
query, datalad automatically offers assistence to obtain a :term:`superdataset` first.
The superdataset is a lightweight container that contains meta information about known datasets but does not contain actual data itself. 

For example, we might want to look for dataset thats were funded by, or acknowledge the US National Science Foundation (NSF)::

  ~ % datalad search NSF
  No DataLad dataset found at current location
  Would you like to install the DataLad superdataset at '~/datalad'? (choices: yes, no): yes
  2016-10-24 09:13:32,414 [INFO   ] Installing dataset at ~/datalad from http://datasets.datalad.org/
  From now on you can refer to this dataset using the label '///'
  2016-10-24 09:13:39,072 [INFO   ] Performing search using DataLad superdataset '~/datalad'
  2016-10-24 09:13:39,086 [INFO   ] Loading and caching local meta-data... might take a few seconds
  ~/datalad/openfmri/ds000001
  ~/datalad/openfmri/ds000002
  ~/datalad/openfmri/ds000003
  ...

Any known dataset can now be installed inside the local superdataset with a
command like this::

  datalad install ~/datalad/openfmri/ds000002
