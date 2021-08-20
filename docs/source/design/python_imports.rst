.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_python_imports:

************************
Python import statements
************************

.. topic:: Specification scope and status

   This specification describes the current (albeit incomplete) implementation.

The following rules apply to any ``import`` statement in the code base:

- All imports *must* be absolute, unless they import individual pieces of an integrated code component that is only split across several source code files for technical or organizational reasons.

- Imports *must* be placed at the top of a source file, unless there is a
  specific reason not to do so (e.g., delayed import due to performance
  concerns, circular dependencies). If such a reason exists, it *must*
  be documented by a comment at the import statement.

- There *must* be no more than one import per line.

- Multiple individual imports from a single module *must* follow the pattern::

      from <module> import (
          symbol1,
          symbol2,
      )

  Individual imported symbols *should* be sorted alphabetically. The last symbol
  line *should* end with a comma.

- Imports from packages and modules *should* be grouped in categories like

  - Standard library packages

  - 3rd-party packages

  - Datalad core (absolute imports)

  - Datalad extensions
  
  - Datalad core ("local" relative imports)
  
  Sorting imports can be aided by https://github.com/PyCQA/isort (e.g. ``python -m isort -m3 --fgw 2 --tc <filename>``).



Examples
========

::

    from collections import OrderedDict
    import logging
    import os

    from datalad.utils import (
        bytes2human,
        ensure_list,
        ensure_unicode,
        get_dataset_root as gdr,
    )
    
 In the `datalad/submodule/tests/test_mod.py` test file demonstrating an "exception" to absolute imports
 rule where test files are accompanying corresponding files of the underlying module:: 
 
    import os
  
    from datalad.utils import ensure_list
    
    from ..mod import func1

    from datalad.tests.utils import assert_true
    
