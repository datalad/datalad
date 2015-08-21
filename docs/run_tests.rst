How to run the tests
====================

All tests are exposed through the standard PyUnit interface, i.e. any test
discovery and runner implementation for python packages can be used (nose,
testtools, ...). For example::

  % PYTHONPATH=. nosetests datalad

