Delineation from related solutions
**********************************

To our knowledge, there is no other effort with a scope as broad as DataLad's.
DataLad aims to unify access to vast arrays of (scientific) data in a domain and
data modality agnostic fashion with as few and universally available software
dependencies as possible.

The most comparable project regarding the idea of federating access to various
data providers is the iRODS_-based `INCF Dataspace`_ project.  IRODS is a
powerful, NSF-supported framework, but it requires non-trivial deployment and
management procedures. As a representative of *data grid* technology, it is
more suitable for an institutional deployment, as data access, authentication,
permission management, and versioning are complex and not-feasible to be
performed directly by researchers. DataLad on the other hand federates
institutionally hosted data, but in addition enables individual researchers and
small labs to contribute datasets to the federation with minimal cost and
without the need for centralized coordination and permission management.

.. _IRODS: https://irods.org
.. _INCF Dataspace: http://www.incf.org/resources/data-space


Data catalogs
=============

Existing data-portals, such as DataDryad_, or domain-specific ones (e.g. `Human
Connectome`_, OpenfMRI_), concentrate on collecting, cataloging, and making
data available. They offer an abstraction from local data management
peculiarities (organization, updates, sharing).  Ad-hoc collections of pointers
to available data, such as `reddit datasets`_ and `Inside-R datasets`_, do not
provide any unified interface to assemble and manage such data.  Data portals
can be used as seed information and data providers for DataLad. These portals
could in turn adopt DataLad to expose readily usable data collections via a
federated infrastructure.

.. _Human Connectome: http://www.humanconnectomeproject.org
.. _OpenfMRI: http://openfmri.org
.. _DataDryad: http://datadryad.org
.. _reddit datasets: http://www.reddit.com/r/datasets
.. _Inside-R datasets: http://www.inside-r.org/howto/finding-data-internet


Data delivery/management middleware
===================================

Even though there are projects to manage data directly with dVCS (e.g. Git),
such as the `Rdatasets Git repository`_ this approach does not scale, for example
to the amount of data typically observed in a scientific context. DataLad
uses git-annex_ to support managing large amounts of data with Git, while
avoiding the scalability issues of putting data directly into Git repositories.

In scientific software development, frequently using Git for source code
management, many projects are also confronted with the problem of managing
large data arrays needed, for example, for software testing. An exemplar
project is `ITK Data`_ which is conceptually similar to git-annex: data content
is referenced by unique keys (checksums), which are made redundantly available
through multiple remote key-store farms and can be obtained using specialized
functionality in the CMake software build system.  However, the scope of this
project is limited to software QA, and only provides an ad-hoc collection of
guidelines and supporting scripts.

.. _Rdatasets Git repository: http://github.com/vincentarelbundock/Rdatasets
.. _ITK Data: http://www.itk.org/Wiki/ITK/Git/Develop/Data

The git-annex website provides a comparison_ of Git-annex to other available
distributed data management tools, such as git-media_, git-fat_, and others.
None of the alternative frameworks provides all of the features of git-annex,
such as integration with native Git workflows, distributed redundant storage,
and partial checkouts in one project.  Additional features of git-annex which
are not necessarily needed by DataLad (git-annex assistant, encryption support,
etc.) make it even more appealing for extended coverage of numerous scenarios.
Moreover, neither of the alternative solutions has already reached a maturity,
availability, and level of adoption that would be comparable to that of
git-annex.

.. _git-annex: http://git-annex.branchable.com
.. _comparison: http://git-annex.branchable.com/not
.. _git-media: https://github.com/schacon/git-media
.. _git-fat: https://github.com/jedbrown/git-fat

.. _chap-git-annex-datalad-comparison:

Git/Git-annex/DataLad
=====================

Although it is possible, and intended, to use DataLad without ever invoking git
or git-annex commands directly, it is useful to appreciate that DataLad is
build atop of very flexible and powerful tools.  Knowing basics of git and
git-annex in addition to DataLad helps to not only make better use of
DataLad but also to enable more advanced and more efficient data management
scenarios. DataLad makes use of lower-level configuration and data structures
as much as possible. Consequently, it is possible to manipulate DataLad
datasets with low-level tools if needed. Moreover, DataLad datasets are
compatible with tools and services designed to work with plain Git repositories,
such as the popular GitHub_ service.

.. _github: https://github.com

To better illustrate the different scopes, the following table provides an
overview of the features that are contributed by each software technology
layer.

================================================   =============  ===============   ==============
Feature                                             Git            Git-annex         DataLad
================================================   =============  ===============   ==============
Version control (text, code)                       |tup|          |tup| can mix     |tup| can mix
Version control (binary data)                      (not advised)  |tup|             |tup|
Auto-crawling available resources                                 |tup| RSS feeds   |tup| flexible
Unified dataset handling                                                            |tup|
- recursive operation on datasets                                                   |tup|
- seamless operation across datasets boundaries                                     |tup|
- meta-data support                                               |tup| per-file    |tup|
- meta-data aggregation                                                             |tup| flexible
Unified authentication interface                                                    |tup|
================================================   =============  ===============   ==============

.. |tup| unicode:: U+2713 .. check mark
   :trim:
