.. -*- mode: rst; fill-column: 78; indent-tabs-mode: nil -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:
  ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ###
  #
  #   See COPYING file distributed along with the datalad package for the
  #   copyright and license terms.
  #
  ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ###

.. _chap_faq:

**************************
Frequently asked questions
**************************

I have no permission to install software on a server I want to use datalad on. Can I make it work nevertheless?
  ``pip`` supports installation into a user's home directory with ``--user``.
  Git-annex, on the other hand, can be deployed by extracting pre-built
  binaries from a tarball (that also includes an up-to-date Git installation).
  `Obtain the tarball <https://downloads.kitenet.net/git-annex/linux/current/>`_,
  extract it, and set the :envvar:`PATH` environment variable to include the
  root of the extracted tarball. Fingers crossed and good luck!
