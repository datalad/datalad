.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_customization:

********************************************
Customization and extension of functionality
********************************************

DataLad provides numerous commands that cover many use cases. However, there
will always be a demand for further customization or extensions of built-in
functionality at a particular site, or for an individual user. DataLad
addresses this need with a mechanism for extending particular Datalad
functionality, such as metadata extractor, or providing entire command suites
for a specialized purpose.

As the name suggests, a :term:`DataLad extension` package is a proper Python package.
Consequently, there is a significant amount of boilerplate code involved in the
creation of a new Datalad extension. However, this overhead enables a number of
useful features for extension developers:

- extensions can provide any number of additional commands that can be grouped into
  labeled command suites, and are automatically exposed via the standard DataLad commandline
  and Python API
- extensions can define `entry_points` for any number of additional metadata extractors
  that become automatically available to DataLad
- extensions can define `entry_points` for their test suites, such that the standard `datalad test`
  command will automatically run these tests in addition to the tests shipped with Datalad core
- extensions can ship additional dataset procedures by installing them into a
  directory ``resources/procedures`` underneath the extension module directory


Using an extension
==================

A :term:`DataLad extension` is a standard Python package. Beyond installation of the package there is
no additional setup required.


Writing your own extensions
===========================

A good starting point for implementing a new extension is the "helloworld" demo extension
available at https://github.com/datalad/datalad-extension-template. This repository can be cloned
and adjusted to suit one's needs. It includes:

- a basic Python package setup
- simple demo command implementation
- Travis test setup

A more complex extension setup can be seen in the DataLad Neuroimaging
extension: https://github.com/datalad/datalad-neuroimaging, including additional metadata extractors,
test suite registration, and a sphinx-based documentation setup for a DataLad extension.

As a DataLad extension is a standard Python package, an extension should declare
dependencies on an appropriate DataLad version, and possibly other extensions
via the standard mechanisms.
