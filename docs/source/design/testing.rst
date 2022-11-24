.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_testing:

**********************************
Continuous integration and testing
**********************************

.. topic:: Specification scope and status

   This specification describes the current implementation.

DataLad is tested using a pytest-based testsuite that is run locally and via continuous integrations setups.
Code development should ensure that old and new functionality is appropriately tested.
The project aims for good unittest coverage (at least 80%).

Running tests
=============


Starting at the top level with ``datalad/tests``, every module in the package comes with a subdirectory ``tests/``, containing the tests for that portion of the codebase. This structure is meant to simplify (re-)running the tests for a particular module.
The test suite is run using

.. code-block:: bash

   pip install -e .[tests]
   python -m pytest -c tox.ini datalad
   # or, with coverage reports
   python -m pytest  -c tox.ini --cov=datalad datalad

Individual tests can be run using a path to the test file, followed by two colons and the test name:

.. code-block:: bash

    python -m pytest datalad/core/local/tests/test_save.py::test_save_message_file

The set of to-be-run tests can be further sub-selected with environment variable based configurations that enable tests based on their :ref:`decorators`, or pytest-specific parameters.
Invoking a test run using ``DATALAD_TESTS_KNOWNFAILURES_PROBE=True pytest datalad``, for example, will run tests marked as known failures whether or not they still fail.
See section :ref:`configuration` for all available configurations.
Invoking a test run using ``DATALAD_TESTS_SSH=1 pytest -m xfail -c tox.ini datalad`` will run only those tests marked as `xfail <https://docs.pytest.org/en/latest/how-to/skipping.html>`_.

Local setup
-----------
Local test execution usually requires a local installation with all development requirements. It is recommended to either use a `virtualenv <https://virtualenv.pypa.io/en/latest/>`_, or `tox <https://tox.wiki/en/latest/>`_ via a ``tox.ini`` file in the code base.

CI setup
--------
At the moment, Travis-CI, Appveyor, and GitHub Workflows exercise the tests battery for every PR and on the default branch, covering different operating systems, Python versions, and file systems.
Tests should be ran on the oldest, latest, and current stable Python release.
The projects uses https://codecov.io for an overview of code coverage.


Writing tests
=============

Additional functionality is tested by extending existing similar tests with new test cases, or adding new tests to the respective test script of the module. Generally, every file `example.py `with datalad code comes with a corresponding `tests/test_example.py`.
Test helper functions assisting various general and DataLad specific assertions as well the construction of test directories and files can be found in ``datalad/tests/utils_pytest.py``.

.. _decorators:

Test annotations
----------------

``datalad/tests/utils_pytest.py`` also defines test decorators.
Some of those are used to annotate tests for various aspects to allow for easy sub-selection via environment variables.

**Speed**: Please annotate tests that take a while to complete with following decorators

* ``@slow`` if test runs over 10 seconds
* ``@turtle`` if test runs over 120 seconds (those would not typically be ran on CIs)

**Purpose**: Please further annotate tests with a special purpose specifically. As those tests also usually tend to be slower, use in conjunction with ``@slow`` or ``@turtle`` when slow.

* ``@integration`` - tests verifying correct operation with external tools/services beyond git/git-annex
* ``@usecase`` - represents some (user) use-case, and not necessarily a "unit-test" of functionality

**Dysfunction**: If tests are not meant to be run on certain platforms or under certain conditions, ``@known_failure`` or ``@skip`` annotations can be used. Examples include:

* ``@skip``, ``@skip_if_on_windows``, ``@skip_ssh``, ``@skip_wo_symlink_capability``, ``@skip_if_adjusted_branch``, ``@skip_if_no_network``, ``@skip_if_root``
* ``@knownfailure``, ``@known_failure_windows``, ``known_failure_githubci_win`` or ``known_failure_githubci_osx``


Migrating tests from nose to pytest
===================================

DataLad's test suite has been migrated from `nose <https://nose.readthedocs.io/en/latest/>`_ to `pytest <https://docs.pytest.org/en/latest/contents.html>`_ in the `0.17.0 release <https://github.com/datalad/datalad/releases/tag/0.17.0>`_.
This might be relevant for DataLad extensions that still use nose.

For the time being, ``datalad.tests.utils`` keeps providing ``nose``-based utils, and ``datalad.__init__`` keeps providing nose-based fixtures to not break extensions that still use nose for testing.
A migration to ``pytest`` is recommended, though.
To perform a typical migration of a DataLad extension to use pytest instead of nose, go through the following list:

* keep all the ``assert_*`` and ``ok_`` helpers, but import them from ``datalad.tests.utils_pytest`` instead
* for ``@with_*`` and other decorators populating positional arguments, convert corresponding posarg to kwarg by adding ``=None``
* convert all generator-based parametric tests into direct invocations or, preferably, ``@pytest.mark.parametrized`` tests
* address ``DeprecationWarnings`` in the code. Only where desired to test deprecation, add ``@pytest.mark.filterwarnings("ignore: BEGINNING OF WARNING")`` decorator to the test.

For an example, see a "migrate to pytest" PR against ``datalad-deprecated``: `datalad/datalad-deprecated#51 <https://github.com/datalad/datalad-deprecated/pull/51>`_ .
