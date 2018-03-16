# simple makefile to simplify repetetive build env management tasks under posix
# Ideas borrowed from scikit-learn's and PyMVPA Makefiles  -- thanks!

PYTHON ?= python
NOSETESTS ?= nosetests

MODULE ?= datalad

all: clean test

clean:
	$(PYTHON) setup.py clean
	rm -rf dist build bin
	-find . -name '*.pyc' -delete
	-find . -name '__pycache__' -type d -delete

bin:
	mkdir -p $@
	PYTHONPATH=bin:$(PYTHONPATH) python setup.py develop --install-dir $@

test-code: bin
	PATH=bin:$(PATH) PYTHONPATH=bin:$(PYTHONPATH) $(NOSETESTS) -s -v $(MODULE)

test-coverage:
	rm -rf coverage .coverage
	$(NOSETESTS) -s -v --with-coverage $(MODULE)

test: test-code


trailing-spaces:
	find $(MODULE) -name "*.py" -exec perl -pi -e 's/[ \t]*$$//' {} \;

code-analysis:
	flake8 $(MODULE) | grep -v __init__ | grep -v external
	pylint -E -i y $(MODULE)/ # -d E1103,E0611,E1101

update-changelog:
	@echo ".. This file is auto-converted from CHANGELOG.md (make update-changelog) -- do not edit\n\nChange log\n**********" > docs/source/changelog.rst
	pandoc -t rst CHANGELOG.md >> docs/source/changelog.rst


render-casts: docs/source/usecases/simple_provenance_tracking.rst.in

docs/source/usecases/simple_provenance_tracking.rst.in: build/casts/simple_provenance_tracking.json
	tools/cast2rst $^ > $@

docs/source/usecases/reproducible_analysis.rst.in: build/casts/reproducible_analysis.json
	tools/cast2rst $^ > $@

docs/source/usecases/track_data_from_webpage.rst.in: build/casts/track_data_from_webpage.json
	tools/cast2rst $^ > $@

docs/source/basics_cmdline.rst.in: build/casts/cmdline_basic_usage.json
	tools/cast2rst $^ > $@

docs/source/basics_nesteddatasets.rst.in: build/casts/seamless_nested_repos.json
	tools/cast2rst $^ > $@
