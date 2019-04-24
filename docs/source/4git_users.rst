DataLad For git/git-annex users
*******************************

Overview
========

DataLad could be considered a "thin layer" on top of ``git`` and ``git-annex``
with the primary goal to provide a unified and simplified interface to
manipulate git/git-annex repositories.  DataLad does neither stores any additional
"state" information nor provides additional to `.git/objects` and
`.git/annex/objects` "content store". So, at large, you can work with DataLad
datasets as with any other git/git-annex repository, or you can use DataLad to work
with regular git/git-annex repositories.  DataLad extensively relies on standard
``git submodule`` to manage collections/hierarchies of the repositories
(called :term:`superdataset` in DataLad terms). So you could even use
`git submodule` commands directly.

Having said all that DataLad adds and uses some additional information to git/git-annex
repositories:

- DataLad uses plain `git config` for managing configuration/settings, but in addition
  to regular configuration file locations (such as `.git/config`) it also considers
  `.datalad/config` which is also kept under git.
- The main difference of DataLad :term:`dataset` from a regular git/git-annex
  repository is that each dataset having a unique identifier (UUID) assigned and committed
  (by `datalad create`) within `.datalad/config` (``datalad.dataset.id``).
- DataLad's meta-data "facilities" store extracted and aggregated metadata
  under `.datalad/metadata`.


Commands
========

Primary difference(s) from regular git/git-annex operation is that DataLad

- can operate on paths which belong to some repository other than the current
  one. Both git and git-annex require first to ``cd`` to the target repository.
  DataLad first figures out what repository given paths belong and then works
  within that repository. `-d` option could be used to instruct DataLad to work
  within specific repository.

As DataLad is just a "thin layer", most of the actual "useful" work is done via
calling out to `git` and `git-annex`.  To reduce amount of "magic" behind DataLad
commands, in the following sections we would like to go through some of them
and explain them in terms of what underlying git, git-annex, or regular UNIX
commands they actually run, and how possibly differently they behave.  This
presentation is primarily to provide high level overview, and might still miss
all the commands we actually execute.  E.g. we religiously consult `git config`
to guarantee that DataLad uses up-to-date configuration settings, but we will
not burden you with such details below.

create
------

Simple
~~~~~~

``datalad create DS``::

    mkdir DS && \
     cd DS && \
     git init && \
     git annex init && \
     mkdir .datalad && \
     echo '* annex.backend=MD5E' > .gitattributes && \
     git add .gitattributes && \
     git commit -m '[DATALAD] Set default backend for all files to be MD5E' && \
     git config -f .datalad/config --add datalad.dataset.id `uuid`
     git commit -m '[DATALAD] New dataset'

and that is pretty much all of the ``datalad create``. But checkout
:ref:`datalad create <man_datalad-create>` documentation for options it carries,
which might augment some steps.

Subdataset
~~~~~~~~~~

Using ``-d`` option (like in ``datalad create -d . SUBDS``) would not only perform
all listed above calls but also add generated ``SUBDS`` to current dataset
(assuming that ``.`` in ``-d .`` is the path for that dataset), so does in addition::

   cd .. && \  # to get back
   git submodule ..... TODO ....


install
-------

``datalad install URL``::

    git clone URL


get
---

``datalad get FILE(s)``::

    git annex get FILE(s)

save
----

create-sibling
--------------

publish
-------