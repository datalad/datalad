Background and motivation
*************************

Vision
======

Data is at the core of science, and unobstructed access promotes scientific
discovery through collaboration between data producers and consumers.  The last
years have seen dramatic improvements in availability of data resources for
collaborative research, and new data providers are becoming available all the
time.

However, despite the increased availability of data, their accessibility is far
from being optimal. Potential consumers of these public datasets have to
manually browse various disconnected warehouses with heterogeneous interfaces.
Once obtained, data is disconnected from its origin and data versioning is
often ad-hoc or completely absent. If data consumers can be reliably informed
about data updates at all, review of changes is difficult, and re-deployment is
tedious and error-prone. This leads to wasteful friction caused by outdated or
faulty data.

The vision for this project is to transform the state of data-sharing and
collaborative work by providing uniform access to available datasets --
independent of hosting solutions or authentication schemes -- with reliable
versioning and versatile deployment logistics. This is achieved by means of a
:term:`dataset` handle, a lightweight representation of a dataset
that is capable of tracking the identity and location of a dataset's content as
well as carry meta-data. Together with associated software tools, scientists
are able to obtain, use, extend, and share datasets (or parts thereof) in a
way that is traceable back to the original data producer and is therefore
capable of establishing a strong connection between data consumers and the
evolution of a dataset by future extension or error correction.

Moreover, DataLad aims to provide all tools necessary to create and publish
*data distributions* |---| an analog to software distributions or app-stores
that provide logistics middleware for software deployment. Scientific
communities can use these tools to gather, curate, and make publicly available
specialized collections of datasets for specific research topics or data
modalities. All of this is possible by leveraging existing data sharing
platforms and institutional resources without the need for funding extra
infrastructure of duplicate storage. Specifically, this project aims to provide
a comprehensive, extensible data distribution for neuroscientific datasets that
is kept up-to-date by an automated service.


Technological foundation: git-annex
===================================

The outlined task is not unique to the problem of data-sharing in science.
Logistical challenges such as delivering data, long-term storage and archiving,
identity tracking, and synchronization between multiple sites are rather
common. Consequently, solutions have been developed in other contexts that can
be adapted to benefit scientific data-sharing.

The closest match is the software tool git-annex_. It combines the features of
the distributed version control system (dVCS) Git_ |---| a technology that has
revolutionized collaborative software development -- with versatile data access
and delivery logistics. Git-annex was originally developed to address use cases
such as managing a collection of family pictures at home. With git-annex, any
family member can obtain an individual copy of such a picture library |---| the
:term:`annex`. The annex in this example is essentially an image repository
that presents individual pictures to users as files in a single directory
structure, even though the actual image file contents may be distributed across
multiple locations, including a home-server, cloud-storage, or even off-line
media such as external hard-drives.

Git-annex provides functionality to obtain file contents upon request and can
prompt users to make particular storage devices available when needed (e.g. a
backup hard-drive kept in a fire-proof compartment). Git-annex can also remove
files from a local copy of that image repository, for example to free up space
on a laptop, while ensuring a configurable level of data redundancy across all
known storage locations. Lastly, git-annex is able to synchronize the content
of multiple distributed copies of this image repository, for example in order
to incorporate images added with the git-annex on the laptop of another family
member. It is important to note that git-annex is agnostic of the actual file
types and is not limited to images.

We believe that the approach to data logistics taken by git-annex and the
functionality it is currently providing are an ideal middleware for scientific
data-sharing. Its data repository model :term:`annex` readily provides the
majority of principal features needed for a dataset handle such as history
recording, identity tracking, and item-based resource locators. Consequently,
instead of a from-scratch development, required features, such as dedicated
support for existing data-sharing portals and dataset meta-information, can be
added to a working solution that is already in production for several years.
As a result, DataLad focuses on the expansion of git-annex's functionality and
the development of tools that build atop Git and git-annex and enable the
creation, management, use, and publication of dataset handles and collections
thereof.

Objective
=========

Building atop git-annex, DataLad aims to provide a single, uniform interface to
access data from various data-sharing initiatives and data providers, and
functionality to create, deliver, update, and share datasets for individuals
and portal maintainers. As a command-line tool, it provides an abstraction
layer for the underlying Git-based middleware implementing the actual data
logistics, and serves as a foundation for other future user front-ends, such
as a web-interface.

.. |---| unicode:: U+02014 .. em dash

.. _Git: https://git-scm.com
.. _git-annex: http://git-annex.branchable.com
