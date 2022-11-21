.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_pytest_migration:

*********************************************
Migrating downstream code from nose to pytest
*********************************************

.. topic:: Specification scope and status

   This specification describes the current implementation.

DataLad's test suite has been migrated from `nose <https://nose.readthedocs.io/en/latest/>`_ to `pytest <https://docs.pytest.org/en/latest/contents.html>`_ in the `0.17.0 release <https://github.com/datalad/datalad/releases/tag/0.17.0>`_.

For the time being, ``datalad.tests.utils`` keeps providing ``nose``-based ``utils``, and ``datalad.__init__`` keeps providing nose-based fixtures to not break extensions that still use nose for testing.
A migration to ``pytest`` is recommended, though.
To perform a typical migration of a DataLad extension to use pytest instead of nose, go through the following list:

* keep all the ``assert_*`` and ``ok_`` helpers, but import them from ``datalad.tests.utils_pytest`` instead
* for ``@with_*`` and other decorators populating positional arguments, convert corresponding posarg to kwarg by adding ``=None``
* convert all generator-based parametric tests into direct invocations or, preferably, ``@pytest.mark.parametrized`` tests
* address ``DeprecationWarnings`` in the code. Only where desired to test deprecation, add ``@pytest.mark.filterwarnings("ignore: BEGINNING OF WARNING")`` decorator to the test.

For an example, see a "migrate to pytest" PR against ``datalad-deprecated``: `datalad/datalad-deprecated#51 <https://github.com/datalad/datalad-deprecated/pull/51>`_ .
