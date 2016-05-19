# simple makefile to simplify repetetive build env management tasks under posix
# Ideas borrowed from scikit-learn's and PyMVPA Makefiles  -- thanks!

PYTHON ?= python
NOSETESTS ?= nosetests

MODULE ?= datalad

all: clean test

clean:
	$(PYTHON) setup.py clean
	rm -rf dist build bin

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

manpages: bin
	mkdir -p build/man
	# main manpage
	DATALAD_HELP2MAN=1 PYTHONPATH=. help2man --no-discard-stderr \
		--help-option="--help-np" -N -n "data management and sharing tool" \
			"bin/datalad" > build/man/datalad.1 ; \
	# figure out all relevant interface files, fuck yeah Python
	for api in $$(PYTHONPATH=. python -c "from datalad.interface.base import get_interface_groups; print(' '.join([' '.join([j.__module__.split('.')[-1] for j in i[2]]) for i in get_interface_groups()]))"); do \
		cmd="$$(echo "$$api" | tr '_' '-')" ; \
		summary="$$(grep -A 1 'class.*(.*Interface.*)' $$(python -c "import inspect; from datalad.api import $${api} as fx; print(inspect.getfile(fx))") | grep -v ':' | grep -v '^--' | sed -e 's/"//g' -e 's/^[ \t]*//;s/[ \t.]*$$//' | tr 'A-Z' 'a-z')" ; \
		DATALAD_HELP2MAN=1 PYTHONPATH=. help2man --no-discard-stderr \
			--help-option="--help-np" -N -n "$$summary" \
				"bin/datalad $${cmd}" > build/man/datalad-$${cmd}.1 ; \
		sed -i -e "4 s/^datalad /datalad $${cmd} /" build/man/datalad-$${cmd}.1 ; \
	done

