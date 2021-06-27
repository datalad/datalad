# simple makefile to simplify repetetive build env management tasks under posix
# Ideas borrowed from scikit-learn's and PyMVPA Makefiles  -- thanks!

PYTHON ?= python
NOSETESTS ?= $(PYTHON) -m nose

MODULE ?= datalad

all: clean test

clean:
	$(PYTHON) setup.py clean
	rm -rf dist build bin
	-find . -name '*.pyc' -delete
	-find . -name '__pycache__' -type d -delete

bin:
	mkdir -p $@
	PYTHONPATH="bin:$(PYTHONPATH)" $(PYTHON) setup.py develop --install-dir $@

test-code: bin
	PATH="bin:$(PATH)" PYTHONPATH="bin:$(PYTHONPATH)" $(NOSETESTS) -s -v $(MODULE)

test-coverage:
	rm -rf coverage .coverage
	$(NOSETESTS) -s -v --with-coverage $(MODULE)

test: test-code


trailing-spaces:
	find $(MODULE) -name "*.py" -exec perl -pi -e 's/[ \t]*$$//' {} \;

code-analysis:
	flake8 $(MODULE) | grep -v __init__ | grep -v external
	pylint -E -i y $(MODULE)/ # -d E1103,E0611,E1101

linkissues-changelog:
	tools/link_issues_CHANGELOG

update-changelog: CHANGELOG.md
	@echo ".. This file is auto-converted from CHANGELOG.md (make update-changelog) -- do not edit\n\nChange log\n**********" > docs/source/changelog.rst
	# sphinx 3.4.3-2 on Debian incorrectly handles unicode character
	# and then fails claiming that underlines are too short. So we remove all
	# such problematic ones for now.
	# Also, for some reason auto sticks subsections all the way to 4th level of sectioning,
	# so we bring them back to 2nd.
	# And pandoc manages to just skip all the valid markdown urls for authors within (),
	# so doing manual post conversion
	cat "$<" | sed -e 's,^#### ,## ,g' \
	| iconv -c -f utf-8 -t ascii \
	| pandoc -t rst \
	| sed -e 's,\[\(@[^]]*\)\](\([^)]*\)),\`\1 <\2>\`__,g' \
	>> docs/source/changelog.rst


release-pypi: update-changelog
	# avoid upload of stale builds
	test ! -e dist
	$(PYTHON) setup.py sdist
	# the wheels we would produce are broken on windows, because they
	# install an incompatible entrypoint script
	# https://github.com/datalad/datalad/issues/4315
	#$(PYTHON) setup.py bdist_wheel
	twine upload dist/*

docs/source/basics_cmdline.rst.in: build/casts/cmdline_basic_usage.json
	tools/cast2rst $^ > $@

docs/source/basics_nesteddatasets.rst.in: build/casts/seamless_nested_repos.json
	tools/cast2rst $^ > $@
