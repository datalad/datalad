.. -*- mode: rst; fill-column: 78; indent-tabs-mode: nil -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:
  ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ###
  #
  #   See COPYING file distributed along with the datalad package for the
  #   copyright and license terms.
  #
  ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ###

.. _chap_glossary:

********
Glossary
********

DataLad purposefully uses a terminology that is different from the one used by
its technological foundations Git_ and git-annex_. This glossary provides
definitions for terms used in the datalad documentation and API, and relates
them to the corresponding Git_/git-annex_ concepts.

.. glossary::
  :sorted:

  dataset
    A regular Git_ repository with an (optional) :term:`annex`.

  subdataset
    A :term:`dataset` that is part of another dataset, by means of being
    tracked as a Git_ submodule. As such, a subdataset is also a complete
    dataset and not different from a standalone dataset.

  superdataset
    A :term:`dataset` that contains at least one :term:`subdataset`.

  sibling
    A :term:`dataset` (location) that is related to a particular dataset,
    by sharing content and history. In Git_ terminology, this is a *clone*
    of a dataset that is configured as a *remote*.

  annex
    Extension to a Git_ repository, provided and managed by git-annex_ as
    means to track and distribute large (and small) files without having to
    inject them directly into a Git_ repository (which would slow Git
    operations significantly and impair handling of such repositories in
    general).

.. _Git: https://git-scm.com
.. _Git-annex: http://git-annex.branchable.com
