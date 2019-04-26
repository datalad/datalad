DataLad for git/git-annex users
*******************************

Overview
========

At its core, DataLad can be considered a thin layer on top of ``git`` and
``git-annex`` that tries to unify and simplify working with repositories.
DataLad does not store additional state information or use a content store
outside of ``.git/objects`` and ``.git/annex/objects``.  You can work with
DataLad datasets as with any other git/git-annex repository, or you can use
DataLad to work with regular git/git-annex repositories.  DataLad extensively
relies on git's builtin ``submodule`` mechanism to manage a hierarchy of
repositories (:term:`superdataset` in DataLad terms), so you could even use
``git submodule`` directly.

Having said all that, DataLad adds and uses some additional information to git/git-annex
repositories:

- DataLad uses ``git config`` for managing configuration. In addition to
  configuration file locations that git knows (such as ``.git/config``), it
  considers ``.datalad/config``, a file whose content is tracked by git.n
- The main difference between a DataLad :term:`dataset` and a regular git/git-annex
  repository is that each dataset has a unique identifier (UUID) assigned and committed
  (by ``datalad create``) within ``.datalad/config`` (``datalad.dataset.id``).
- DataLad's metadata facilities store extracted and aggregated metadata
  under ``.datalad/metadata``.


Commands
========

The primary difference between the operation of git and git-annex's commands and
DataLad's is that DataLad's can operate on paths that belong to some repository
other than the current one. Whereas git and git-annex would require the caller
to first ``cd`` to the target repository, DataLad figures out which repository
the given paths belong to and then works within that repository.

As DataLad is just a "thin layer", most of the actual "useful" work is done via
calling out to ``git`` and ``git-annex``.  To reduce the amount of magic behind
DataLad commands, in the following sections we translate some commands into the
underlying git, git-annex, and UNIX commands. This presentation is intended to
provide a high-level overview for conceptual understanding rather than give a
complete and accurate description of the underlying calls.

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

That is pretty much all that ``datalad create`` does, but check out
:ref:`datalad create <man_datalad-create>` documentation for additional options
that might augment some steps.

Subdataset
~~~~~~~~~~

Using the ``-d`` option (like in ``datalad create -d . SUBDS``) would not only perform
all the calls listed above but also add the generated ``SUBDS`` to current dataset
(assuming that ``.`` in ``-d .`` is the path for that dataset), extending the
list above with something like::

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