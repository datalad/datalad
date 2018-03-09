.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_customization:

********************************************
Customization and extension of functionality
********************************************

DataLad provides numerous commands that cover many use cases. However, there
will always be a demand for further customization or extensions of built-in
functionality at a particular site, or for an individual user. DataLad
addresses this need by providing a generic plugin interface.

Using plugins
=============

A number of plugins are shipped with DataLad. This includes plugins which
operate on a particular dataset, but also general functionality that can be
used outside the context of a specific dataset. The following table provides an
overview of plugins included in this DataLad release.

.. currentmodule:: datalad.plugin
.. autosummary::
   :toctree: generated

   add_readme
   export_archive
   no_annex
   wtf


In previous versions of DataLad, plugins were invoked differently than regular
DataLad commands, but they can now be called like any other command. The
``wtf`` plugin, for example, is exposed as

.. code-block:: shell

   % datalad wtf


Plugin detection
================

DataLad will discover plugins at three locations:

1. official plugins that are part of the local DataLad installation

2. system-wide plugins, provided by the local admin

   The location where plugins need to be placed depends on the platform.
   On GNU/Linux systems this will be ``/etc/xdg/datalad/plugins``, whereas
   on Windows it will be ``C:\ProgramData\datalad.org\datalad\plugins``.

   This default location can be overridden by setting the
   ``datalad.locations.system-plugins`` configuration variable in the local or
   global Git configuration.

3. user-supplied plugins, customizable by each user

   Again, the location will depend on the platform.  On GNU/Linux systems this
   will be ``$HOME/.config/datalad/plugins``, whereas on Windows it will be
   ``C:\Users\<username>\AppData\Local\datalad.org\datalad\plugins``.

   This default location can be overridden by setting the
   ``datalad.locations.user-plugins`` configuration variable in the local or
   global Git configuration.

Identically named plugins in latter location replace those in locations
searched before. This can be used to alter the behavior of plugins provided
with DataLad, and enables users to adjust a site-wide configuration.


Writing own plugins
===================

The best way to go about writing your own plugin, is to have a look at the
`source code of those include in DataLad
<https://github.com/datalad/datalad/tree/master/datalad/plugin>`_. Writing
a plugin a rather simple when following the following rules.

Language and location
---------------------

Plugins are written in Python. In order for DataLad to be able to find them,
plugins need to be placed in one of the supported locations described above.
Plugin file names have to have a '.py' extensions and must not start with an
underscore ('_').

Skeleton of a plugin
--------------------

The basic structure of a plugin looks like this::

    from datalad.interface.base import build_doc, Interface


    @build_doc
    class MyPlugin(Interface):
        """Help message description (parameters will be added automatically)"""
        from datalad.distribution.dataset import datasetmethod, EnsureDataset
        from datalad.interface.utils import eval_results
        from datalad.support.constraints import EnsureNone
        from datalad.support.param import Parameter

        _params_ = dict(
            dataset=Parameter(
                args=("-d", "--dataset"),
                doc=""""specify the dataset to report on.
                no dataset is given, an attempt is made to identify the dataset
                based on the current working directory.""",
                constraints=EnsureDataset() | EnsureNone()))

        @staticmethod
        @datasetmethod(name='my-plugin')
        @eval_results
        def __call__(dataset):
            # Do things and yield status dicts.
            pass


    __datalad_plugin__ = MyPlugin

In this example, the plugin is called ``my-plugin``. Any number of parameters
can be added by extending both the ``_params_`` dictionary and the signature of
``__call__``. The help message for the plugin command is generated using the
docstring of the plugin class and the `_params_` dictionary.


Expected behavior
-----------------

The plugin's ``__call__`` method must yield its results as a Python generator.
Results are DataLad status dictionaries. There are no constraints on the number
of results, or the number and nature of result properties. However, conventions
exists and must be followed for compatibility with the result evaluation and
rendering performed by DataLad.

The following property keys must exist:

"status"
    {'ok', 'notneeded', 'impossible', 'error'}

"action"
    label for the action performed by the plugin. In many cases this
    could be the plugin's name.

The following keys should exists if possible:

"path"
    absolute path to a result on the file system

"type"
    label indicating the nature of a result (e.g. 'file', 'dataset',
    'directory', etc.)

"message"
    string message annotating the result, particularly important for
    non-ok results. This can be a tuple with 'logging'-style string
    expansion.
