.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_file_url_handling:

*****************
File URL handling
*****************

.. topic:: Specification scope and status

   This specification describes the current implementation.

Datalad datasets can record URLs for file content access as metadata. This is a
feature provided by git-annex and is available for any annexed file. DataLad
improves upon the git-annex functionality in two ways:

1. Support for a variety of (additional) protocols and authentication methods.

2. Support for special URLs pointing to individual files located in registered
   (annexed) archives, such as tarballs and ZIP files.

These additional features are available to all functionality that is processing
URLs, such as ``get``, ``addurls``, or ``download-url``.


Extensible protocol and authentication support
==============================================

DataLad ships with a dedicated implementation of an external `git-annex special
remote`_ named ``git-annex-remote-datalad``. This is a somewhat atypical special
remote, because it cannot receive files and store them, but only supports
read operations.

Specifically, it uses the ``CLAIMURL`` feature of the `external special remote
protocol`_ to take over processing of URLs with supported protocols in all
datasets that have this special remote configured and enabled.

This special remote is automatically configured and enabled in DataLad dataset
as a ``datalad`` remote, by commands that utilize its features, such as
``download-url``. Once enabled, DataLad (but also git-annex) is able to act on
additional protocols, such as ``s3://``, and the respective URLs can be given
directly to commands like ``git annex addurl``, or ``datalad download-url``.

Beyond additional protocol support, the ``datalad`` special remote also
interfaces with DataLad's :ref:`chap_design_credentials`. It can identify a
particular credential required for a given URL (based on something called a
"provider" configuration), ask for the credential or retrieve it from a
credential store, and supply it to the respective service in an appropriate
form. Importantly, this feature neither requires the necessary credential or
provider configuration to be encoded in a URL (where it would become part of
the git-annex metadata), nor to be committed to a dataset. Hence all
information that may depend on which entity is performing a URL request
and in what environment is completely separated from the location information
on a particular file content. This minimizes the required dataset maintenance
effort (when credentials change), and offers a clean separation of identity
and availability tracking vs. authentication management.


Indexing and access of archive content
======================================

Another `git-annex special remote`_, named
``git-annex-remote-datalad-archives``, is used to enable file content retrieval
from annexed archive files, such as tarballs and ZIP files. Its implementation
concept is closely related to the ``git-annex-remote-datalad``, described
above.  Its main difference is that it claims responsibility for a particular
type of "URL" (starting with ``dl+archive:``). These URLs encode the identity
of an archive file, in terms of its git-annex key name, and a relative path
inside this archive pointing to a particular file.

Like ``git-annex-remote-datalad``, only read operations are supported. When
a request to a ``dl+archive:`` "URL" is made, the special remote identifies
the archive file, if necessary obtains it at the precise version needed, and
extracts the respected file content from the archive at the correct location.

This special remote is automatically configured and enabled as
``datalad-archives`` by the ``add-archive-content`` command. This command
indexes annexed archives, extracts, and registers their content to a
dataset.  File content availability information is recorded in terms of the
``dl+archive:`` "URLs", which are put into the git-annex metadata on a file's
content.


.. _git-annex special remote: https://git-annex.branchable.com/special_remotes/
.. _external special remote protocol: https://git-annex.branchable.com/design/external_special_remote_protocol
