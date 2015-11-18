Contributing to DataLad
=======================

[gh-datalad]: http://github.com/datalad/datalad

Files organization
------------------

- `datalad/` is the main Python module where major development is happening,
  with major submodules being:
    - `cmdline/` contains commands for the command line interface.  See any of
      the `cmd_*.py` files here for an example
    - `crawler/` functionality relevant for `crawl`ing operation of DataLad
    - `customremotes/` support of datalad custom special remotes for annex
    - `tests/` all unit- and regression- tests
        - `utils.py` provides convenience helpers used by unit-tests such as
          `@with_tree`, `@serve_path_via_http` and other decorators
- `tools/` contains helper utilities used during development, testing, and
  benchmarking of DataLad.  Implemented in any most appropriate language
  (Python, bash, etc.)

How to contribute
-----------------

The preferred way to contribute to the DataLad code base is
to fork the [main repository][gh-datalad] on GitHub.  Here
we outline the workflow used by the developers:


0. Have a clone of our main [project repository][gh-datalad] as `origin`
   remote in your git:

          git clone git://github.com/datalad/datalad

1. Fork the [project repository][gh-datalad]: click on the 'Fork'
   button near the top of the page.  This creates a copy of the code
   base under your account on the GitHub server.

2. Add your forked clone as a remote to the local clone you already have on your
   local disk:

          git remote add gh-YourLogin git@github.com:YourLogin/datalad.git
          git fetch gh-YourLogin

    To ease addition of other github repositories as remotes, here is
    a little bash function/script to add to your `~/.bashrc`:

        ghremote () {
                url="$1"
                proj=${url##*/}
                url_=${url%/*}
                login=${url_##*/}
                git remote add gh-$login $url
                git fetch gh-$login
        }

    thus you could simply run:

         ghremote git@github.com:YourLogin/datalad.git

    to add the above `gh-YourLogin` remote.

3. Create a branch (generally off the `origin/master`) to hold your changes:

          git checkout -b nf-my-feature

    and start making changes. Ideally, use a prefix signaling the purpose of the
    branch
    - `nf-` for new features
    - `bf-` for bug fixes
    - `rf-` for refactoring
    - `doc-` for documentation contributions (including in the code docstrings).
    We recommend to not work in the ``master`` branch!

4. Work on this copy on your computer using Git to do the version control. When
   you're done editing, do:

          git add modified_files
          git commit

   to record your changes in Git.  Ideally, prefix your commit messages with the
   `NF`, `BF`, `RF`, `DOC` similar to the branch name prefixes, but you could
   also use `TST` for commits concerned solely with tests, and `BK` to signal
   that the commit causes a breakage (e.g. of tests) at that point.  Multiple
   entries could be listed joined with a `+` (e.g. `rf+doc-`).  See `git log` for
   examples.  If a commit closes an existing DataLad issue, then add to the end
   of the mesage `(Closes #ISSUE_NUMER)`

5. Push to GitHub with:

          git push -u gh-YourLogin nf-my-feature

   Finally, go to the web page of your fork of the DataLad repo, and click
   'Pull request' (PR) to send your changes to the maintainers for review. This
   will send an email to the committers.  You can commit new changes to this branch
   and keep pushing to your remote -- github automagically adds them to your
   previously opened PR.

(If any of the above seems like magic to you, then look up the
[Git documentation](http://git-scm.com/documentation) on the web.)


Quality Assurance
-----------------

It is recommended to check that your contribution complies with the following
rules before submitting a pull request:

- All public methods should have informative docstrings with sample usage
  presented as doctests when appropriate.

- All other tests pass when everything is rebuilt from scratch.

- New code should be accompanied by tests.


### Tests

All tests are available under `datalad/tests`.  To execute tests, the codebase
needs to be "installed" in order to generate scripts for the entry points.  For
that, the recommended course of action is to use `virtualenv`, e.g.

```sh
virtualenv --system-site-packages venv-tests
source venv-tests/bin/activate
pip install -r requirements.txt
python setup.py develop
```

and then use that virtual environment to run the tests, via

```sh
python -m nose -s -v datalad
```

or similarly,

```sh
nosetests -s -v datalad
```

then to later deactivate the virtualenv just simply enter

```sh
deactivate
```

Alternatively, or complimentary to that, you can use `tox` -- there is a `tox.ini`
file which sets up a few virtual environments for testing locally, which you can
later reuse like any other regular virtualenv for troubleshooting.


### Coverage

You can also check for common programming errors with the following tools:

- Code with good unittest coverage (at least 80%), check with:

          pip install nose coverage
          nosetests --with-coverage path/to/tests_for_package


### Linting

We are not (yet) fully PEP8 compliant, so please use these tools as
guidelines for your contributions, but not to PEP8 entire code
base.

[beyond-pep8]: https://www.youtube.com/watch?v=wf-BqAjZb8M

*Sidenote*: watch [Raymond Hettinger - Beyond PEP 8][beyond-pep8]

- No pyflakes warnings, check with:

           pip install pyflakes
           pyflakes path/to/module.py

- No PEP8 warnings, check with:

           pip install pep8
           pep8 path/to/module.py

- AutoPEP8 can help you fix some of the easy redundant errors:

           pip install autopep8
           autopep8 path/to/pep8.py

Also, some team developers use
[PyCharm community edition](https://www.jetbrains.com/pycharm) which
provides built-in PEP8 checker and handy tools such as smart
splits/joins making it easier to maintain code following the PEP8
recommendations.  NeuroDebian provides `pycharm-community-sloppy`
package to ease pycharm installation even further.


Easy Issues
-----------

A great way to start contributing to DataLad is to pick an item from the list of
[Easy issues](https://github.com/datalad/datalad/labels/easy) in the issue
tracker.  Resolving these issues allows you to start contributing to the project
without much prior knowledge.  Your assistance in this area will be greatly
appreciated by the more experienced developers as it helps free up their time to
concentrate on other issues.
