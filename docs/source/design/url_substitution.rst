.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_url_substitution:

****************
URL substitution
****************

.. topic:: Specification scope and status

   This specification describes the current implementation. This implementation
   is covering URL substitution in ``clone`` only. A further extension to
   URL processing elsewhere is possible.

URL substitution is a transformation of a given URL using a set of
specifications. Such specification can be provided as configuration settings
(via all supported configuration sources). These configuration items must
follow the naming scheme ``datalad.clone.url-substitute.<label>``, where
``<label>`` is an arbitrary identifier.

A substitution specification is a string with a match and substitution
expression, each following Python's regular expression syntax.  Both
expressions are concatenated into a single string with an arbitrary delimiter
character. The delimiter is defined by prefixing the string with the delimiter.
Prefix and delimiter are stripped from the expressions before processing.
Example::

  ,^http://(.*)$,https://\\1

A particular configuration item can be defined multiple times (see examples
below) to form a substitution series. Substitutions in the same series will be
applied incrementally, in order of their definition. If the first substitution
expression does not match, the entire series will be ignored. However,
following a first positive match all further substitutions in a series are
processed, regardless whether intermediate expressions match or not.

Any number of substitution series can be configured. They will be considered in
no particular order. Consequently, it advisable to implement the first match
specification of any series as specific as possible, in order to prevent
undesired transformations.


Examples
========

Change the protocol component of a given URL in order to hand over further
processing to a dedicated Git remote helper. Specifically, the following
example converts Open Science Framework project URLs like
``https://osf.io/f5j3e/`` into ``osf://f5j3e``, a URL that can be handle by
``git-remote-osf``, the Git remote helper provided by the `datalad-osf
extension package <https://github.com/datalad/datalad-osf>`__::

  datalad.clone.url-substitute.osf = ,^https://osf.io/([^/]+)[/]*$,osf://\1

Here is a more complex examples with a series of substitutions. The first
expression ensures that only GitHub URLs are being processed. The associated
substitution disassembles the URL into its two only relevant components,
the organisation/user name, and the project name::

  datalad.clone.url-substitute.github = ,https?://github.com/([^/]+)/(.*)$,\1###\2

All other expressions in this series that are described below will only be considered
if the above expression matched.

The next two expressions in the series normalize URL components that maybe be
auto-generated by some DataLad functionality, e.g. subdataset location
candidate generation from directory names::

  # replace (back)slashes with a single dash
  datalad.clone.url-substitute.github = ,[/\\]+,-

  # replace with whitespace (URL-quoted or not) with a single underscore
  datalad.clone.url-substitute.github = ,\s+|(%2520)+|(%20)+,_

The final expression in the series is recombining the organization/user name
and project name components back into a complete URL::

  datalad.clone.url-substitute.github = ,([^#]+)###(.*),https://github.com/\1/\2
