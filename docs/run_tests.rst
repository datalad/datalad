How to run the tests
====================

All tests are exposed through the standard PyUnit interface, i.e. any test
discovery and runner implementation for python packages can be used (nose,
testtools, ...). For example::

  % PYTHONPATH=. nosetests datalad

Some tests use the testkraut framework to wrap the execution of non-unittest
tests in the same PyUnit interface (see ``datalad/tests/testspecs``). These
tests will be executed automatically alongside the conventional unit tests.
However, in contrast to unittests they generate more information on the test
environment and the test output. The easiest way to get access to the
information through the ``subunit`` test runner (apt-get install
python-subunit). All these tests are implemented in
``datalad/tests/test_kraut.py`` and can be executed via subunit as such::

  % PYTHONPATH=. python -m subunit.run datalad.tests.test_kraut

for a more convenient display of results subunit provides a number of filter
commands that can read a subunit stream from stdin. For example::

  % PYTHONPATH=. python -m subunit.run datalad.tests.test_kraut | subunit2pyunit

generates standard pyunit-style output. ``subunit2csv``, ``subunit2gtk``,
``subunit-ls`` additional potentially useful filters.


Adding a new testkraut test
---------------------------

The best place to learn about the test specification required by testkraut is
here: https://testkraut.readthedocs.org/en/latest/spec.html

However, datalad only uses a minimal version of this functionality, and comes
with its own stripped down implementation of testkraut (for the moment). The
test(s) located at ``datalad/tests/testspecs/`` are the best existing
documentation at this point.
