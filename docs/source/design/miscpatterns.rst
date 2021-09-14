.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_designpatterns:

**********************
Miscellaneous patterns
**********************

DataLad is the result of a distributed and collaborative development effort
over many years.  During this time the scope of the project has changed
multiple times. As a consequence, the API and employed technologies have been
adjusted repeatedly.  Depending on the age of a piece of code, a clear software
design is not always immediately visible. This section documents a few design
patterns that the project strives to adopt at present. Changes to existing code
and new contributions should follow these guidelines.


Generator methods in `Repo` classes
===================================

Substantial parts of DataLad are implemented to behave like Python generators
in order to be maximally responsive when processing long-running tasks. This
included methods of the core API classes
:class:`~datalad.support.gitrepo.GitRepo` and
:class:`~datalad.support.annexrepo.AnnexRepo`. By convention, such methods
carry a trailing `_` in their name. In some cases, sibling methods with the
same name, but without the trailing underscore are provided. These behave like
their generator-equivalent, but eventually return an iterable once processing
is fully completed.


Calls to Git commands
=====================

DataLad is built on Git, so calls to Git commands are a key element of the code
base. All such calls should be made through methods of the
:class:`~datalad.support.gitrepo.GitRepo` class.  This is necessary, as only
there it is made sure that Git operates under the desired conditions
(environment configuration, etc.).

For some functionality, for example querying and manipulating `gitattributes`,
dedicated methods are provided. However, in many cases simple one-off calls to
get specific information from Git, or trigger certain operations are needed.
For these purposes the :class:`~datalad.support.gitrepo.GitRepo` class provides
a set of convenience methods aiming to cover use cases requiring particular
return values:

- test success of a command:
  :meth:`~datalad.support.gitrepo.GitRepo.call_git_success`
- obtain `stdout` of a command:
  :meth:`~datalad.support.gitrepo.GitRepo.call_git`
- obtain a single output line:
  :meth:`~datalad.support.gitrepo.GitRepo.call_git_oneline`
- obtain items from output split by a separator:
  :meth:`~datalad.support.gitrepo.GitRepo.call_git_items_`

All these methods take care of raising appropriate exceptions when expected
conditions are not met. Whenever desired functionality can be achieved
using simple custom calls to Git via these methods, their use is preferred
over the implementation of additional, dedicated wrapper methods.

Command examples
================

Examples of Python and commandline invocations of DataLad's user-oriented
commands are defined in the class of the respective command as dictionaries
within `_examples_`:

.. code-block:: python

   _examples_ = [
    dict(text="""Create a dataset 'mydataset' in the current directory""",
         code_py="create(path='mydataset')",
         code_cmd="datalad create mydataset",
    dict(text="""Apply the text2git procedure upon creation of a dataset""",
         code_py="create(path='mydataset', cfg_proc='text2git')",
         code_cmd="datalad create -c text2git mydataset")
         ]

The formatting of code lines is preserved. Changes to existing examples and
new contributions should provide examples for Python and commandline API, as
well as a concise description.
