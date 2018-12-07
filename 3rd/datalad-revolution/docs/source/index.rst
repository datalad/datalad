Revolutionary DataLad extension
*******************************

The extension equips DataLad with some extra commands that enable
alternative workflows.

What is in it for users?
========================

If you are looking for a simple solution to data management that can help
you track changes in a project, no matter whether it is about data, source code,
or both, this package is for you. With just two simple commands, DataLad does
all the work for you. Especially people who are not familiar with Git_ will
find this simplicity appealing.

Here is a quick demo. The **first command** creates a dataset.  A dataset is
essentially a directory that is managed by DataLad and where all content can be
tracked. Let's change directories and enter this dataset after it was created.

.. code-block:: console

   % datalad rev-create myproject
   [INFO   ] Creating a new annex repo at /tmp/myproject
   create(ok): /tmp/myproject (dataset)
   % cd myproject

From now on, any change to this directory can be recorded. For this demo,
we will copy some very important construction plans for a nice garden bench
into this directory. However, we could also use some GUI tool or a script to
make a change, it would make no difference to DataLad.

.. code-block:: console

   % cp /home/me/bench_plan.svg .

Whenever one feels like a noteworthy change has been made, or a milestone
was reached, the state of the dataset can be recorded with the **second
command**.

.. code-block:: console

   % datalad rev-save
   add(ok): bench_plan.svg (file)
   save(ok): . (dataset)
   action summary:
     add (ok: 1)
     save (ok: 1)

The `rev-save` command will discover any change and record it in the dataset.
Changes can not only be added files, but any modification, or deletion, even
of entire sub-directories -- a simple `datalad rev-save` will make a record
of it.

These two commands are all that is needed to record changes in a project
within DataLad dataset. The resulting dataset is just as capable as any other
DataLad dataset. It can be archived, published, used to go back to a particular
state of the project and everything else that DataLad supports. Check out the
`documentation <http://docs.datalad.org>`_ to learn more about its features.

What is in it for developers?
=============================

This extension amends the core base classes with functionality that enables
command implementation where the state of a dataset is fully inspected first
(in a platform-agnostic fashion) and subsequently low-level tools can execute a
desired function based on this status report, with no or minimal further
queries of the underlying repository. This helps to better isolate developers
from the peculiarities of particular platforms and repository modes, and can
lead to more compact code and better performance.

Key component is the `rev-status` command (and its repository-level
counterparts) that can report the state of a full dataset hierarchy.
It works like a simplified `git status`, but is git-annex aware.

.. code-block:: console

   % datalad rev-status --recursive
       untracked: /tmp/some/directory_untracked (directory)
       untracked: /tmp/some/file_modified (symlink)
       untracked: /tmp/some/link2dir (symlink)
       untracked: /tmp/some/link2subdsroot (symlink)
       untracked: /tmp/some/other (directory)
        modified: /tmp/some/.gitmodules (file)
           added: /tmp/some/link2subdsdir (symlink)
        modified: /tmp/some/subds_modified (dataset)
       untracked: /tmp/some/subds_modified/new_untracked (file)
   % datalad -f json_pp rev-status --annex all subdir/annexed_file.txt
   {
     "action": "status",
     "backend": "MD5E",
     "bytesize": "5",
     "gitshasum": "a79f797e1ce00f414131f7e84f47049c4c5c5f1a",
     "has_content": true,
     "humansize": "5 B",
     "key": "MD5E-s5--275876e34cf609db118f3d84b799a790.txt",
     "keyname": "275876e34cf609db118f3d84b799a790.txt",
     "mtime": "unknown",
     "objloc": "/tmp/some/.git/annex/objects/7p/gp/MD5E-s5--275876e34cf609db118f3d84b799a790.txt/MD5E-s5--275876e34cf609db118f3d84b799a790.txt",
     "parentds": "/tmp/some",
     "path": "/tmp/some/subdir/annexed_file.txt",
     "refds": "/tmp/some",
     "state": "clean",
     "status": "ok",
     "type": "file"
   }

API
===

High-level API commands
-----------------------

.. currentmodule:: datalad.api
.. autosummary::
   :toctree: generated

   rev_create
   rev_save
   rev_status

Low-level API
-------------

.. currentmodule:: datalad_revolution
.. autosummary::
   :toctree: generated

   gitrepo
   annexrepo
   dataset


Acknowledgments
===============

DataLad development is being performed as part of a US-German collaboration in
computational neuroscience (CRCNS) project "DataGit: converging catalogues,
warehouses, and deployment logistics into a federated 'data distribution'"
(Halchenko_/Hanke_), co-funded by the US National Science Foundation (`NSF
1429999`_) and the German Federal Ministry of Education and Research (`BMBF
01GQ1411`_). Additional support is provided by the German federal state of
Saxony-Anhalt and the European Regional Development
Fund (ERDF), Project: `Center for Behavioral Brain Sciences`_, Imaging Platform

DataLad is built atop the git-annex_ software that is being developed and
maintained by `Joey Hess`_.

.. _Halchenko: http://haxbylab.dartmouth.edu/ppl/yarik.html
.. _Hanke: http://www.psychoinformatics.de
.. _NSF 1429999: http://www.nsf.gov/awardsearch/showAward?AWD_ID=1429999
.. _BMBF 01GQ1411: http://www.gesundheitsforschung-bmbf.de/de/2550.php
.. _Center for Behavioral Brain Sciences: http://cbbs.eu/en/
.. _git-annex: http://git-annex.branchable.com
.. _Joey Hess: https://joeyh.name

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. |---| unicode:: U+02014 .. em dash

.. _Git: https://git-scm.com
