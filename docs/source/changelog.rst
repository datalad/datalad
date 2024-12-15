.. This file is auto-converted from CHANGELOG.md (make update-changelog) -- do not edit

Change log
**********
1.1.5 (2024-12-15)
==================

Tests
-----

-  test: xfail test_subsuperdataset_save on newer gits. `PR
   #7687 <https://github.com/datalad/datalad/pull/7687>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  test: refactor test_parallel.py to be abit more pytest’y. `PR
   #7690 <https://github.com/datalad/datalad/pull/7690>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  BF: use datalad/packages method of installing git-annex. `PR
   #7692 <https://github.com/datalad/datalad/pull/7692>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-1:

1.1.4 (2024-11-18)
==================

Bug Fixes
---------

-  Exit with the original non-0 exit code if underlying functionality,
   in particular “datalad run”, returned incomplete result record with a
   non-0 exit code. Fixes
   `#7504 <https://github.com/datalad/datalad/issues/7504>`__ via `PR
   #7641 <https://github.com/datalad/datalad/pull/7641>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Provide detail on why CHECKURL failed for datalad and archive special
   remotes (would require new AnnexRemote release (above 1.6.5) to take
   advantage of this PR). `PR
   #7648 <https://github.com/datalad/datalad/pull/7648>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  BF: allow for empty output directory to be specified to run. Fixes
   `#7653 <https://github.com/datalad/datalad/issues/7653>`__ via `PR
   #7654 <https://github.com/datalad/datalad/pull/7654>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  fix: do load extension interfaces if early parsing errors out. Fixes
   `#7678 <https://github.com/datalad/datalad/issues/7678>`__ via `PR
   #7679 <https://github.com/datalad/datalad/pull/7679>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Drop Python 3.8. Fixes
   `#7678 <https://github.com/datalad/datalad/issues/7678>`__ via `PR
   #7682 <https://github.com/datalad/datalad/pull/7682>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

Performance
-----------

-  OPT: use set O(log(n)) instead of list O(n) for checking if modified
   in \_check_files. `PR
   #7655 <https://github.com/datalad/datalad/pull/7655>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-1:

Tests
-----

-  Declare minimal compat version of pytest to be 7.0. Fixes
   `#7555 <https://github.com/datalad/datalad/issues/7555>`__ via `PR
   #7645 <https://github.com/datalad/datalad/pull/7645>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  BF: replace url for codecov uploader for macos to versioned one with
   two archs. Fixes
   `#7642 <https://github.com/datalad/datalad/issues/7642>`__ via `PR
   #7649 <https://github.com/datalad/datalad/pull/7649>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-2:

1.1.3 (2024-08-08)
==================

.. _tests-2:

Tests
-----

-  Account for the fix in git-annex behavior in
   test_add_delete_after_and_drop_subdir. `PR
   #7640 <https://github.com/datalad/datalad/pull/7640>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-3:

1.1.2 (2024-07-25)
==================

.. _bug-fixes-1:

Bug Fixes
---------

-  Correct remote OS detection when working with RIA (ORA) stores: this
   should enable RIA operations, including push, from Mac clients to
   Linux hosts (and likely vice versa). Fixes
   `#7536 <https://github.com/datalad/datalad/issues/7536>`__ via `PR
   #7549 <https://github.com/datalad/datalad/pull/7549>`__ (by
   `@mslw <https://github.com/mslw>`__)

-  Allow only one thread in S3 downloader’s progress report callback.
   `PR #7636 <https://github.com/datalad/datalad/pull/7636>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

.. _section-4:

1.1.1 (2024-07-03)
==================

.. _bug-fixes-2:

Bug Fixes
---------

-  Ensure timestamps of files in ZIP archives are within years
   1980-2107. Fixes
   `#3753 <https://github.com/datalad/datalad/issues/3753>`__ via `PR
   #7450 <https://github.com/datalad/datalad/pull/7450>`__ (by
   `@adswa <https://github.com/adswa>`__)

Documentation
-------------

-  Update README.md: improve wording. `PR
   #7550 <https://github.com/datalad/datalad/pull/7550>`__ (by
   `@alliesw <https://github.com/alliesw>`__)

Internal
--------

-  Add codespell and minor fixuppers to pre-commit configuration and
   apply it to non-``datalad/`` components. `PR
   #7621 <https://github.com/datalad/datalad/pull/7621>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-3:

Tests
-----

-  For appveyor ssh setup, setup MaxSessions 100 to avoid ‘channel 22:
   open failed: connect failed: open failed’. `PR
   #7617 <https://github.com/datalad/datalad/pull/7617>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  test_gracefull_death: raise test_gracefull_death threshold to 300
   from 100. `PR #7619 <https://github.com/datalad/datalad/pull/7619>`__
   (by `@yarikoptic <https://github.com/yarikoptic>`__)

-  Make test for presence of max_path in partitions not run for current
   psutil 6.0.0. `PR
   #7622 <https://github.com/datalad/datalad/pull/7622>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-5:

1.1.0 (2024-06-06)
==================

Dependencies
------------

-  Deprecated ``boto`` is replaced with ``boto3`` (used to handle AWS S3
   downloads). Fixes
   `#5597 <https://github.com/datalad/datalad/issues/5597>`__ via `PR
   #7340 <https://github.com/datalad/datalad/pull/7340>`__ (by
   `@mslw <https://github.com/mslw>`__,
   `@effigies <https://github.com/effigies>`__, and
   `@yarikoptic <https://github.com/yarikoptic>`__). Remaining issues:

   -  no download progress indication,
   -  no “Range” support (for partial downloads).

.. _internal-1:

Internal
--------

-  Retry logic for S3 connections is now handed over to Boto3 and its
   standard mode, removing our custom method. `PR
   #7340 <https://github.com/datalad/datalad/pull/7340>`__

.. _section-6:

1.0.3 (2024-06-06)
==================

.. _bug-fixes-3:

Bug Fixes
---------

-  Raise exception if an annex remote process without console tries to
   interact with the user, e.g. prompt for a password. `PR
   #7578 <https://github.com/datalad/datalad/pull/7578>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  Fix add-archive-content for patool>=2.0. `PR
   #7603 <https://github.com/datalad/datalad/pull/7603>`__ (by
   `@dguibert <https://github.com/dguibert>`__)

.. _internal-2:

Internal
--------

-  Fixup minor typos in documentation/comments using fresh codespell.
   `PR #7610 <https://github.com/datalad/datalad/pull/7610>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-4:

Tests
-----

-  Stop testing on Python 3.7. Switch MacOS tests to 3.11, include 3.11
   in Appveyor, and use 3.8 for other tests. Fixes
   `#7584 <https://github.com/datalad/datalad/issues/7584>`__ via `PR
   #7585 <https://github.com/datalad/datalad/pull/7585>`__ (by
   `@mslw <https://github.com/mslw>`__)

-  Convert ``.travis.yml`` to GitHub Actions workflow. Fixes
   `#7574 <https://github.com/datalad/datalad/issues/7574>`__ via `PR
   #7600 <https://github.com/datalad/datalad/pull/7600>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Cancel lengthy running workflows if a new commit is pushed. `PR
   #7601 <https://github.com/datalad/datalad/pull/7601>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

.. _section-7:

1.0.2 (2024-04-19)
==================

.. _tests-5:

Tests
-----

-  Relax condition in ``test_force_checkdatapresent`` to avoid flaky
   test failures. `PR
   #7581 <https://github.com/datalad/datalad/pull/7581>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

.. _section-8:

1.0.1 (2024-04-17)
==================

.. _internal-3:

Internal
--------

-  The main entrypoint for annex remotes now also runs the standard
   extension load hook. This enables extensions to alter annex remote
   implementation behavior in the same way than other DataLad
   components. (by `@mih <https://github.com/mih>`__)

.. _section-9:

1.0.0 (2024-04-06)
==================

Breaking Changes
----------------

-  Merging maint to make the first major release. `PR
   #7577 <https://github.com/datalad/datalad/pull/7577>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

Enhancements and New Features
-----------------------------

-  Increase minimal Git version to 2.25. Fixes
   `#7389 <https://github.com/datalad/datalad/issues/7389>`__ via `PR
   #7431 <https://github.com/datalad/datalad/pull/7431>`__ (by
   `@adswa <https://github.com/adswa>`__)

.. _section-10:

0.19.6 (2024-02-02)
===================

.. _enhancements-and-new-features-1:

Enhancements and New Features
-----------------------------

-  Add the “http_token” authentication mechanism which provides
   ‘Authentication: Token {TOKEN}’ header. `PR
   #7551 <https://github.com/datalad/datalad/pull/7551>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _internal-4:

Internal
--------

-  Update ``pytest_ignore_collect()`` for pytest 8.0. `PR
   #7546 <https://github.com/datalad/datalad/pull/7546>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Add manual triggering support/documentation for release workflow. `PR
   #7553 <https://github.com/datalad/datalad/pull/7553>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-11:

0.19.5 (2023-12-28)
===================

.. _tests-6:

Tests
-----

-  Fix text to account for a recent change in git-annex dropping
   sub-second clock precision. As a result we might not report push of
   git-annex branch since there would be none. `PR
   #7544 <https://github.com/datalad/datalad/pull/7544>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-12:

0.19.4 (2023-12-13)
===================

.. _bug-fixes-4:

Bug Fixes
---------

-  Update target detection for adjusted mode datasets has been improved.
   Fixes `#7507 <https://github.com/datalad/datalad/issues/7507>`__ via
   `PR #7522 <https://github.com/datalad/datalad/pull/7522>`__ (by
   `@mih <https://github.com/mih>`__)

-  Fix typos found by new codespell 2.2.6 and also add checking/fixing
   “hidden files”. `PR
   #7530 <https://github.com/datalad/datalad/pull/7530>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _documentation-1:

Documentation
-------------

-  Improve threaded-runner documentation. Fixes
   `#7498 <https://github.com/datalad/datalad/issues/7498>`__ via `PR
   #7500 <https://github.com/datalad/datalad/pull/7500>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

.. _internal-5:

Internal
--------

-  add RRID to package metadata. `PR
   #7495 <https://github.com/datalad/datalad/pull/7495>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  Fix time_diff\* and time_remove benchmarks to account for long RFed
   interfaces. `PR
   #7502 <https://github.com/datalad/datalad/pull/7502>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-7:

Tests
-----

-  Cache value of the has_symlink_capability to spare some cycles. `PR
   #7471 <https://github.com/datalad/datalad/pull/7471>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  RF(TST): use setup_method and teardown_method in
   TestAddArchiveOptions. `PR
   #7488 <https://github.com/datalad/datalad/pull/7488>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Announce test_clone_datasets_root xfail on github osx. `PR
   #7489 <https://github.com/datalad/datalad/pull/7489>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Inform asv that there should be no warmup runs for time_remove
   benchmark. `PR
   #7505 <https://github.com/datalad/datalad/pull/7505>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  BF(TST): Relax matching of git-annex error message about unsafe drop,
   which was changed in 10.20231129-18-gfd0b510573. `PR
   #7541 <https://github.com/datalad/datalad/pull/7541>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-13:

0.19.3 (2023-08-10)
===================

.. _bug-fixes-5:

Bug Fixes
---------

-  Type annotate get_status_dict and note that we can pass Exception or
   CapturedException which is not subclass. `PR
   #7403 <https://github.com/datalad/datalad/pull/7403>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  BF: create-sibling-gitlab used to raise a TypeError when attempting a
   recursive operation in a dataset with uninstalled subdatasets. It now
   raises an impossible result instead. `PR
   #7430 <https://github.com/datalad/datalad/pull/7430>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  Pass branch option into recursive call within Install - for the cases
   whenever install is invoked with URL(s). Fixes
   `#7461 <https://github.com/datalad/datalad/issues/7461>`__ via `PR
   #7463 <https://github.com/datalad/datalad/pull/7463>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Allow for reckless=ephemeral clone using relative path for the
   original location. Fixes
   `#7469 <https://github.com/datalad/datalad/issues/7469>`__ via `PR
   #7472 <https://github.com/datalad/datalad/pull/7472>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _documentation-2:

Documentation
-------------

-  Fix a property name and default costs described in “getting
   subdatasets” section of ``get`` documentation. Fixes
   `#7458 <https://github.com/datalad/datalad/issues/7458>`__ via `PR
   #7460 <https://github.com/datalad/datalad/pull/7460>`__ (by
   `@mslw <https://github.com/mslw>`__)

.. _internal-6:

Internal
--------

-  Copy an adjusted environment only if requested to do so. `PR
   #7399 <https://github.com/datalad/datalad/pull/7399>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  Eliminate uses of ``pkg_resources``. Fixes
   `#7435 <https://github.com/datalad/datalad/issues/7435>`__ via `PR
   #7439 <https://github.com/datalad/datalad/pull/7439>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

.. _tests-8:

Tests
-----

-  Disable some S3 tests of their VCR taping where they fail for known
   issues. `PR #7467 <https://github.com/datalad/datalad/pull/7467>`__
   (by `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-14:

0.19.2 (2023-07-03)
===================

.. _bug-fixes-6:

Bug Fixes
---------

-  Remove surrounding quotes in output filenames even for newer version
   of annex. Fixes
   `#7440 <https://github.com/datalad/datalad/issues/7440>`__ via `PR
   #7443 <https://github.com/datalad/datalad/pull/7443>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _documentation-3:

Documentation
-------------

-  DOC: clarify description of the “install” interface to reflect its
   convoluted behavior. `PR
   #7445 <https://github.com/datalad/datalad/pull/7445>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-15:

0.19.1 (2023-06-26)
===================

.. _internal-7:

Internal
--------

-  Make compatible with upcoming release of git-annex (next after
   10.20230407) and pass explicit core.quotepath=false to all git calls.
   Also added ``tools/find-hanged-tests`` helper. `PR
   #7372 <https://github.com/datalad/datalad/pull/7372>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-9:

Tests
-----

-  Adjust tests for upcoming release of git-annex (next after
   10.20230407) and ignore DeprecationWarning for pkg_resources for now.
   `PR #7372 <https://github.com/datalad/datalad/pull/7372>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-16:

0.19.0 (2023-06-14)
===================

.. _enhancements-and-new-features-2:

Enhancements and New Features
-----------------------------

-  Address gitlab API special character restrictions. `PR
   #7407 <https://github.com/datalad/datalad/pull/7407>`__ (by
   `@jsheunis <https://github.com/jsheunis>`__)

-  BF: The default layout of create-sibling-gitlab is now
   ``collection``. The previous default, ``hierarchy`` has been removed
   as it failed in –recursive mode in different edgecases. For
   single-level datasets, the outcome of ``collection`` and
   ``hierarchy`` is identical. `PR
   #7410 <https://github.com/datalad/datalad/pull/7410>`__ (by
   `@jsheunis <https://github.com/jsheunis>`__ and
   `@adswa <https://github.com/adswa>`__)

.. _bug-fixes-7:

Bug Fixes
---------

-  WTF - bring back and extend information on metadata extractors etc,
   and allow for sections to have subsections and be selected at both
   levels `PR #7309 <https://github.com/datalad/datalad/pull/7309>`__
   (by `@yarikoptic <https://github.com/yarikoptic>`__)

-  BF: Run an actual git invocation with interactive commit config. `PR
   #7398 <https://github.com/datalad/datalad/pull/7398>`__ (by
   `@adswa <https://github.com/adswa>`__)

.. _dependencies-1:

Dependencies
------------

-  Raise minimal version of tqdm (progress bars) to v.4.32.0 `PR
   #7330 <https://github.com/datalad/datalad/pull/7330>`__ (by
   `@mslw <https://github.com/mslw>`__)

.. _documentation-4:

Documentation
-------------

-  DOC: Add a “User messaging” design doc. `PR
   #7310 <https://github.com/datalad/datalad/pull/7310>`__ (by
   `@jsheunis <https://github.com/jsheunis>`__)

.. _tests-10:

Tests
-----

-  Remove nose-based testing utils and possibility to test extensions
   using nose. `PR
   #7261 <https://github.com/datalad/datalad/pull/7261>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-17:

0.18.5 (2023-06-13)
===================

.. _bug-fixes-8:

Bug Fixes
---------

-  More correct summary reporting for relaxed (no size) –annex. `PR
   #7050 <https://github.com/datalad/datalad/pull/7050>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  ENH: minor tune up of addurls to be more tolerant and “informative”.
   `PR #7388 <https://github.com/datalad/datalad/pull/7388>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Ensure that data generated by timeout handlers in the asynchronous
   runner are accessible via the result generator, even if no other
   other events occur. `PR
   #7390 <https://github.com/datalad/datalad/pull/7390>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  Do not map (leave as is) trailing / or  in github URLs. `PR
   #7418 <https://github.com/datalad/datalad/pull/7418>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _documentation-5:

Documentation
-------------

-  Use ``sphinx_autodoc_typehints``. Fixes
   `#7404 <https://github.com/datalad/datalad/issues/7404>`__ via `PR
   #7412 <https://github.com/datalad/datalad/pull/7412>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

.. _internal-8:

Internal
--------

-  Discontinue ConfigManager abuse for Git identity warning. `PR
   #7378 <https://github.com/datalad/datalad/pull/7378>`__ (by
   `@mih <https://github.com/mih>`__) and `PR
   #7392 <https://github.com/datalad/datalad/pull/7392>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-11:

Tests
-----

-  Boost python to 3.8 during extensions testing. `PR
   #7413 <https://github.com/datalad/datalad/pull/7413>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Skip test_system_ssh_version if no ssh found + split parsing into
   separate test. `PR
   #7422 <https://github.com/datalad/datalad/pull/7422>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-18:

0.18.4 (2023-05-16)
===================

.. _bug-fixes-9:

Bug Fixes
---------

-  Provider config files were ignored, when CWD changed between
   different datasets during runtime. Fixes
   `#7347 <https://github.com/datalad/datalad/issues/7347>`__ via `PR
   #7357 <https://github.com/datalad/datalad/pull/7357>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _documentation-6:

Documentation
-------------

-  Added a workaround for an issue with documentation theme (search
   function not working on Read the Docs). Fixes
   `#7374 <https://github.com/datalad/datalad/issues/7374>`__ via `PR
   #7385 <https://github.com/datalad/datalad/pull/7385>`__ (by
   `@mslw <https://github.com/mslw>`__)

.. _internal-9:

Internal
--------

-  Type-annotate ``datalad/support/gitrepo.py``. `PR
   #7341 <https://github.com/datalad/datalad/pull/7341>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

.. _tests-12:

Tests
-----

-  Fix failing testing on CI `PR
   #7379 <https://github.com/datalad/datalad/pull/7379>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

   -  use sample S3 url DANDI archive,
   -  use our copy of old .deb from datasets.datalad.org instead of
      snapshots.d.o
   -  use specific miniconda installer for py 3.7.

.. _section-19:

0.18.3 (2023-03-25)
===================

.. _bug-fixes-10:

Bug Fixes
---------

-  Fixed that the ``get`` command would fail, when subdataset
   source-candidate-templates where using the ``path`` property from
   ``.gitmodules``. Also enhance the respective documentation for the
   ``get`` command. Fixes
   `#7274 <https://github.com/datalad/datalad/issues/7274>`__ via `PR
   #7280 <https://github.com/datalad/datalad/pull/7280>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  Improve up-to-dateness of config reports across manager instances.
   Fixes `#7299 <https://github.com/datalad/datalad/issues/7299>`__ via
   `PR #7301 <https://github.com/datalad/datalad/pull/7301>`__ (by
   `@mih <https://github.com/mih>`__)

-  BF: GitRepo.merge do not allow merging unrelated unconditionally. `PR
   #7312 <https://github.com/datalad/datalad/pull/7312>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Do not render (empty) WTF report on other records. `PR
   #7322 <https://github.com/datalad/datalad/pull/7322>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Fixed a bug where changing DataLad’s log level could lead to failing
   git-annex calls. Fixes
   `#7328 <https://github.com/datalad/datalad/issues/7328>`__ via `PR
   #7329 <https://github.com/datalad/datalad/pull/7329>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  Fix an issue with uninformative error reporting by the datalad
   special remote. Fixes
   `#7332 <https://github.com/datalad/datalad/issues/7332>`__ via `PR
   #7333 <https://github.com/datalad/datalad/pull/7333>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  Fix save to not force committing into git if reference dataset is
   pure git (not git-annex). Fixes
   `#7351 <https://github.com/datalad/datalad/issues/7351>`__ via `PR
   #7355 <https://github.com/datalad/datalad/pull/7355>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _documentation-7:

Documentation
-------------

-  Include a few previously missing commands in html API docs. Fixes
   `#7288 <https://github.com/datalad/datalad/issues/7288>`__ via `PR
   #7289 <https://github.com/datalad/datalad/pull/7289>`__ (by
   `@mslw <https://github.com/mslw>`__)

.. _internal-10:

Internal
--------

-  Type-annotate almost all of ``datalad/utils.py``; add
   ``datalad/typing.py``. `PR
   #7317 <https://github.com/datalad/datalad/pull/7317>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Type-annotate and fix ``datalad/support/strings.py``. `PR
   #7318 <https://github.com/datalad/datalad/pull/7318>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Type-annotate ``datalad/support/globbedpaths.py``. `PR
   #7327 <https://github.com/datalad/datalad/pull/7327>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Extend type-annotations for ``datalad/support/path.py``. `PR
   #7336 <https://github.com/datalad/datalad/pull/7336>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Type-annotate various things in ``datalad/runner/``. `PR
   #7337 <https://github.com/datalad/datalad/pull/7337>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Type-annotate some more files in ``datalad/support/``. `PR
   #7339 <https://github.com/datalad/datalad/pull/7339>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

.. _tests-13:

Tests
-----

-  Skip or xfail some currently failing or stalling tests. `PR
   #7331 <https://github.com/datalad/datalad/pull/7331>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Skip with_sameas_remote when rsync and annex are incompatible. Fixes
   `#7320 <https://github.com/datalad/datalad/issues/7320>`__ via `PR
   #7342 <https://github.com/datalad/datalad/pull/7342>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  Fix testing assumption - do create pure GitRepo superdataset and test
   against it. `PR
   #7353 <https://github.com/datalad/datalad/pull/7353>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-20:

0.18.2 (2023-02-27)
===================

.. _bug-fixes-11:

Bug Fixes
---------

-  Fix ``create-sibling`` for non-English SSH remotes by providing
   ``LC_ALL=C`` for the ``ls`` call. `PR
   #7265 <https://github.com/datalad/datalad/pull/7265>`__ (by
   `@nobodyinperson <https://github.com/nobodyinperson>`__)

-  Fix EnsureListOf() and EnsureTupleOf() for string inputs. `PR
   #7267 <https://github.com/datalad/datalad/pull/7267>`__ (by
   `@nobodyinperson <https://github.com/nobodyinperson>`__)

-  create-sibling: Use C.UTF-8 locale instead of C on the remote end.
   `PR #7273 <https://github.com/datalad/datalad/pull/7273>`__ (by
   `@nobodyinperson <https://github.com/nobodyinperson>`__)

-  Address compatibility with most recent git-annex where info would
   exit with non-0. `PR
   #7292 <https://github.com/datalad/datalad/pull/7292>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _dependencies-2:

Dependencies
------------

-  Revert “Revert”Remove chardet version upper limit”“. `PR
   #7263 <https://github.com/datalad/datalad/pull/7263>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _internal-11:

Internal
--------

-  Codespell more (CHANGELOGs etc) and remove custom CLI options from
   tox.ini. `PR #7271 <https://github.com/datalad/datalad/pull/7271>`__
   (by `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-14:

Tests
-----

-  Use older python 3.8 in testing nose utils in github-action
   test-nose. Fixes
   `#7259 <https://github.com/datalad/datalad/issues/7259>`__ via `PR
   #7260 <https://github.com/datalad/datalad/pull/7260>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-21:

0.18.1 (2023-01-16)
===================

.. _bug-fixes-12:

Bug Fixes
---------

-  Fixes crashes on windows where DataLad was mistaking git-annex
   10.20221212 for a not yet released git-annex version and trying to
   use a new feature. Fixes
   `#7248 <https://github.com/datalad/datalad/issues/7248>`__ via `PR
   #7249 <https://github.com/datalad/datalad/pull/7249>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _documentation-8:

Documentation
-------------

-  DOC: fix EnsureCallable docstring. `PR
   #7245 <https://github.com/datalad/datalad/pull/7245>`__ (by
   `@matrss <https://github.com/matrss>`__)

.. _performance-1:

Performance
-----------

-  Integrate buffer size optimization from datalad-next, leading to
   significant performance improvement for status and diff. Fixes
   `#7190 <https://github.com/datalad/datalad/issues/7190>`__ via `PR
   #7250 <https://github.com/datalad/datalad/pull/7250>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _section-22:

0.18.0 (2022-12-31)
===================

.. _breaking-changes-1:

Breaking Changes
----------------

-  Move all old-style metadata commands ``aggregate_metadata``,
   ``search``, ``metadata`` and ``extract-metadata``, as well as the
   ``cfg_metadatatypes`` procedure and the old metadata extractors into
   the datalad-deprecated extension. Now recommended way of handling
   metadata is to install the datalad-metalad extension instead. Fixes
   `#7012 <https://github.com/datalad/datalad/issues/7012>`__ via `PR
   #7014 <https://github.com/datalad/datalad/pull/7014>`__

-  Automatic reconfiguration of the ORA special remote when cloning from
   RIA stores now only applies locally rather than being committed. `PR
   #7235 <https://github.com/datalad/datalad/pull/7235>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _enhancements-and-new-features-3:

Enhancements and New Features
-----------------------------

-  A repository description can be specified with a new
   ``--description`` option when creating siblings using
   ``create-sibling-[gin|gitea|github|gogs]``. Fixes
   `#6816 <https://github.com/datalad/datalad/issues/6816>`__ via `PR
   #7109 <https://github.com/datalad/datalad/pull/7109>`__ (by
   `@mslw <https://github.com/mslw>`__)

-  Make validation failure of alternative constraints more informative.
   Fixes `#7092 <https://github.com/datalad/datalad/issues/7092>`__ via
   `PR #7132 <https://github.com/datalad/datalad/pull/7132>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  Saving removed dataset content was sped-up, and reporting of types of
   removed content now accurately states ``dataset`` for added and
   removed subdatasets, instead of ``file``. Moreover, saving previously
   staged deletions is now also reported. `PR
   #6784 <https://github.com/datalad/datalad/pull/6784>`__ (by
   `@mih <https://github.com/mih>`__)

-  ``foreach-dataset`` command got a new possible value for the
   –output-streamns\|–o-s option ‘relpath’ to capture and pass-through
   prefixing with path to subds. Very handy for e.g. running
   ``git grep`` command across subdatasets. `PR
   #7071 <https://github.com/datalad/datalad/pull/7071>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  New config
   ``datalad.create-sibling-ghlike.extra-remote-settings.NETLOC.KEY=VALUE``
   allows to add and/or overwrite local configuration for the created
   sibling by the commands
   ``create-sibling-<gin|gitea|github|gitlab|gogs>``. `PR
   #7213 <https://github.com/datalad/datalad/pull/7213>`__ (by
   `@matrss <https://github.com/matrss>`__)

-  The ``siblings`` command does not concern the user with messages
   about inconsequential failure to annex-enable a remote anymore. `PR
   #7217 <https://github.com/datalad/datalad/pull/7217>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  ORA special remote now allows to override its configuration locally.
   `PR #7235 <https://github.com/datalad/datalad/pull/7235>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  Added a ‘ria’ special remote to provide backwards compatibility with
   datasets that were set up with the deprecated
   `ria-remote <https://github.com/datalad/git-annex-ria-remote>`__. `PR
   #7235 <https://github.com/datalad/datalad/pull/7235>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _bug-fixes-13:

Bug Fixes
---------

-  When ``create-sibling-ria`` was invoked with a sibling name of a
   pre-existing sibling, a duplicate key in the result record caused a
   crashed. Fixes
   `#6950 <https://github.com/datalad/datalad/issues/6950>`__ via `PR
   #6952 <https://github.com/datalad/datalad/pull/6952>`__ (by
   `@adswa <https://api.github.com/users/adswa>`__)

.. _documentation-9:

Documentation
-------------

-  create-sibling-ria’s docstring now defines the schema of RIA URLs and
   clarifies internal layout of a RIA store. `PR
   #6861 <https://github.com/datalad/datalad/pull/6861>`__ (by
   `@adswa <https://api.github.com/users/adswa>`__)

-  Move maintenance team info from issue to CONTRIBUTING. `PR
   #6904 <https://github.com/datalad/datalad/pull/6904>`__ (by
   `@adswa <https://api.github.com/users/adswa>`__)

-  Describe specifications for a DataLad GitHub Action. `PR
   #6931 <https://github.com/datalad/datalad/pull/6931>`__ (by
   `@thewtex <https://api.github.com/users/thewtex>`__)

-  Fix capitalization of some service names. `PR
   #6936 <https://github.com/datalad/datalad/pull/6936>`__ (by
   `@aqw <https://api.github.com/users/aqw>`__)

-  Command categories in help text are more consistently named. `PR
   #7027 <https://github.com/datalad/datalad/pull/7027>`__ (by
   `@aqw <https://api.github.com/users/aqw>`__)

-  DOC: Add design document on Tests and CI. `PR
   #7195 <https://github.com/datalad/datalad/pull/7195>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  CONTRIBUTING.md was extended with up-to-date information on CI
   logging, changelog and release procedures. `PR
   #7204 <https://github.com/datalad/datalad/pull/7204>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _internal-12:

Internal
--------

-  Allow EnsureDataset constraint to handle Path instances. Fixes
   `#7069 <https://github.com/datalad/datalad/issues/7069>`__ via `PR
   #7133 <https://github.com/datalad/datalad/pull/7133>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  Use ``looseversion.LooseVersion`` as drop-in replacement for
   ``distutils.version.LooseVersion`` Fixes
   `#6307 <https://github.com/datalad/datalad/issues/6307>`__ via `PR
   #6839 <https://github.com/datalad/datalad/pull/6839>`__ (by
   `@effigies <https://api.github.com/users/effigies>`__)

-  Use –pathspec-from-file where possible instead of passing long lists
   of paths to git/git-annex calls. Fixes
   `#6922 <https://github.com/datalad/datalad/issues/6922>`__ via `PR
   #6932 <https://github.com/datalad/datalad/pull/6932>`__ (by
   `@yarikoptic <https://api.github.com/users/yarikoptic>`__)

-  Make clone_dataset() better patchable ny extensions and less
   monolithic. `PR
   #7017 <https://github.com/datalad/datalad/pull/7017>`__ (by
   `@mih <https://api.github.com/users/mih>`__)

-  Remove ``simplejson`` in favor of using ``json``. Fixes
   `#7034 <https://github.com/datalad/datalad/issues/7034>`__ via `PR
   #7035 <https://github.com/datalad/datalad/pull/7035>`__ (by
   `@christian-monch <https://api.github.com/users/christian-monch>`__)

-  Fix an error in the command group names-test. `PR
   #7044 <https://github.com/datalad/datalad/pull/7044>`__ (by
   `@christian-monch <https://api.github.com/users/christian-monch>`__)

-  Move eval_results() into interface.base to simplify imports for
   command implementations. Deprecate use from interface.utils
   accordingly. Fixes
   `#6694 <https://github.com/datalad/datalad/issues/6694>`__ via `PR
   #7170 <https://github.com/datalad/datalad/pull/7170>`__ (by
   `@adswa <https://github.com/adswa>`__)

.. _performance-2:

Performance
-----------

-  Use regular dicts instead of OrderedDicts for speedier operations.
   Fixes `#6566 <https://github.com/datalad/datalad/issues/6566>`__ via
   `PR #7174 <https://github.com/datalad/datalad/pull/7174>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  Reimplement ``get_submodules_()`` without ``get_content_info()`` for
   substantial performance boosts especially for large datasets with few
   subdatasets. Originally proposed in `PR
   #6942 <https://github.com/datalad/datalad/pull/6942>`__ by
   `@mih <https://github.com/mih>`__, fixing
   `#6940 <https://github.com/datalad/datalad/issues/6940>`__. `PR
   #7189 <https://github.com/datalad/datalad/pull/7189>`__ (by
   `@adswa <https://github.com/adswa>`__). Complemented with `PR
   #7220 <https://github.com/datalad/datalad/pull/7220>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__) to avoid ``O(N^2)``
   (instead of ``O(N*log(N))`` performance in some cases.

-  Use –include=\* or –anything instead of –copies 0 to speed up
   get_content_annexinfo. `PR
   #7230 <https://github.com/datalad/datalad/pull/7230>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-15:

Tests
-----

-  Re-enable two now-passing core test on Windows CI. `PR
   #7152 <https://github.com/datalad/datalad/pull/7152>`__ (by
   `@adswa <https://api.github.com/users/adswa>`__)

-  Remove the ``with_testrepos`` decorator and associated tests for it
   Fixes `#6752 <https://github.com/datalad/datalad/issues/6752>`__ via
   `PR #7176 <https://github.com/datalad/datalad/pull/7176>`__ (by
   `@adswa <https://api.github.com/users/adswa>`__)

.. _section-23:

0.17.10 (2022-12-14)
====================

.. _enhancements-and-new-features-4:

Enhancements and New Features
-----------------------------

-  Enhance concurrent invocation behavior of ``ThreadedRunner.run()``.
   If possible invocations are serialized instead of raising *re-enter*
   runtime errors. Deadlock situations are detected and runtime errors
   are raised instead of deadlocking. Fixes
   `#7138 <https://github.com/datalad/datalad/issues/7138>`__ via `PR
   #7201 <https://github.com/datalad/datalad/pull/7201>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  Exceptions bubbling up through CLI are now reported on including
   their chain of **cause**. Fixes
   `#7163 <https://github.com/datalad/datalad/issues/7163>`__ via `PR
   #7210 <https://github.com/datalad/datalad/pull/7210>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _bug-fixes-14:

Bug Fixes
---------

-  BF: read RIA config from stdin instead of temporary file. Fixes
   `#6514 <https://github.com/datalad/datalad/issues/6514>`__ via `PR
   #7147 <https://github.com/datalad/datalad/pull/7147>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  Prevent doomed annex calls on files we already know are untracked.
   Fixes `#7032 <https://github.com/datalad/datalad/issues/7032>`__ via
   `PR #7166 <https://github.com/datalad/datalad/pull/7166>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  Comply to Posix-like clone URL formats on Windows. Fixes
   `#7180 <https://github.com/datalad/datalad/issues/7180>`__ via `PR
   #7181 <https://github.com/datalad/datalad/pull/7181>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  Ensure that paths used in the datalad-url field of .gitmodules are
   posix. Fixes
   `#7182 <https://github.com/datalad/datalad/issues/7182>`__ via `PR
   #7183 <https://github.com/datalad/datalad/pull/7183>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  Bandaids for export-to-figshare to restore functionality. `PR
   #7188 <https://github.com/datalad/datalad/pull/7188>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  Fixes hanging threads when ``close()`` or ``del`` where called in
   ``BatchedCommand`` instances. That could lead to hanging tests if the
   tests used the ``@serve_path_via_http()``-decorator Fixes
   `#6804 <https://github.com/datalad/datalad/issues/6804>`__ via `PR
   #7201 <https://github.com/datalad/datalad/pull/7201>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  Interpret file-URL path components according to the local operating
   system as described in RFC 8089. With this fix,
   ``datalad.network.RI('file:...').localpath`` returns a correct local
   path on Windows if the RI is constructed with a file-URL. Fixes
   `#7186 <https://github.com/datalad/datalad/issues/7186>`__ via `PR
   #7206 <https://github.com/datalad/datalad/pull/7206>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  Fix a bug when retrieving several files from a RIA store via SSH,
   when the annex key does not contain size information. Fixes
   `#7214 <https://github.com/datalad/datalad/issues/7214>`__ via `PR
   #7215 <https://github.com/datalad/datalad/pull/7215>`__ (by
   `@mslw <https://github.com/mslw>`__)

-  Interface-specific (python vs CLI) doc generation for commands and
   their parameters was broken when brackets were used within the
   interface markups. Fixes
   `#7225 <https://github.com/datalad/datalad/issues/7225>`__ via `PR
   #7226 <https://github.com/datalad/datalad/pull/7226>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _documentation-10:

Documentation
-------------

-  Fix documentation of ``Runner.run()`` to not accept strings. Instead,
   encoding must be ensured by the caller. Fixes
   `#7145 <https://github.com/datalad/datalad/issues/7145>`__ via `PR
   #7155 <https://github.com/datalad/datalad/pull/7155>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _internal-13:

Internal
--------

-  Fix import of the ``ls`` command from datalad-deprecated for
   benchmarks. Fixes
   `#7149 <https://github.com/datalad/datalad/issues/7149>`__ via `PR
   #7154 <https://github.com/datalad/datalad/pull/7154>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  Unify definition of parameter choices with ``datalad clean``. Fixes
   `#7026 <https://github.com/datalad/datalad/issues/7026>`__ via `PR
   #7161 <https://github.com/datalad/datalad/pull/7161>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _tests-16:

Tests
-----

-  Fix test failure with old annex. Fixes
   `#7157 <https://github.com/datalad/datalad/issues/7157>`__ via `PR
   #7159 <https://github.com/datalad/datalad/pull/7159>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

-  Re-enable now passing test_path_diff test on Windows. Fixes
   `#3725 <https://github.com/datalad/datalad/issues/3725>`__ via `PR
   #7194 <https://github.com/datalad/datalad/pull/7194>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Use Plaintext keyring backend in tests to avoid the need for
   (interactive) authentication to unlock the keyring during (CI-) test
   runs. Fixes
   `#6623 <https://github.com/datalad/datalad/issues/6623>`__ via `PR
   #7209 <https://github.com/datalad/datalad/pull/7209>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _section-24:

0.17.9 (2022-11-07)
===================

.. _bug-fixes-15:

Bug Fixes
---------

-  Various small fixups ran after looking post-release and trying to
   build Debian package. `PR
   #7112 <https://github.com/datalad/datalad/pull/7112>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  BF: Fix add-archive-contents try-finally statement by defining
   variable earlier. `PR
   #7117 <https://github.com/datalad/datalad/pull/7117>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  Fix RIA file URL reporting in exception handling. `PR
   #7123 <https://github.com/datalad/datalad/pull/7123>`__ (by
   `@adswa <https://github.com/adswa>`__)

-  HTTP download treated ‘429 - too many requests’ as an authentication
   issue and was consequently trying to obtain credentials. Fixes
   `#7129 <https://github.com/datalad/datalad/issues/7129>`__ via `PR
   #7129 <https://github.com/datalad/datalad/pull/7129>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _dependencies-3:

Dependencies
------------

-  Unrestrict pytest and pytest-cov versions. `PR
   #7125 <https://github.com/datalad/datalad/pull/7125>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Remove remaining references to ``nose`` and the implied requirement
   for building the documentation Fixes
   `#7100 <https://github.com/datalad/datalad/issues/7100>`__ via `PR
   #7136 <https://github.com/datalad/datalad/pull/7136>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _internal-14:

Internal
--------

-  Use datalad/release-action. Fixes
   `#7110 <https://github.com/datalad/datalad/issues/7110>`__. `PR
   #7111 <https://github.com/datalad/datalad/pull/7111>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Fix all logging to use %-interpolation and not .format, sort imports
   in touched files, add pylint-ing for % formatting in log messages to
   ``tox -e lint``. `PR
   #7118 <https://github.com/datalad/datalad/pull/7118>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-17:

Tests
-----

-  Increase the upper time limit after which we assume that a process is
   stalling. That should reduce false positives from
   ``datalad.support.tests.test_parallel.py::test_stalling``, without
   impacting the runtime of passing tests. `PR
   #7119 <https://github.com/datalad/datalad/pull/7119>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  XFAIL a check on length of results in test_gracefull_death. `PR
   #7126 <https://github.com/datalad/datalad/pull/7126>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Configure Git to allow for “file” protocol in tests. `PR
   #7130 <https://github.com/datalad/datalad/pull/7130>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _section-25:

0.17.8 (2022-10-24)
===================

.. _bug-fixes-16:

Bug Fixes
---------

-  Prevent adding duplicate entries to .gitmodules. `PR
   #7088 <https://github.com/datalad/datalad/pull/7088>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  [BF] Prevent double yielding of impossible get result Fixes
   `#5537 <https://github.com/datalad/datalad/issues/5537>`__. `PR
   #7093 <https://github.com/datalad/datalad/pull/7093>`__ (by
   `@jsheunis <https://github.com/jsheunis>`__)

-  Stop rendering the output of internal ``subdatset()`` call in the
   results of ``run_procedure()``. Fixes
   `#7091 <https://github.com/datalad/datalad/issues/7091>`__ via `PR
   #7094 <https://github.com/datalad/datalad/pull/7094>`__ (by
   `@mslw <https://github.com/mslw>`__ &
   `@mih <https://github.com/mih>`__)

-  Improve handling of ``--existing reconfigure`` in
   ``create-sibling-ria``: previously, the command would not make the
   underlying ``git init`` call for existing local repositories, leading
   to some configuration updates not being applied. Partially addresses
   https://github.com/datalad/datalad/issues/6967 via
   https://github.com/datalad/datalad/pull/7095 (by @mslw)

-  Ensure subprocess environments have a valid path in
   ``os.environ['PWD']``, even if a Path-like object was given to the
   runner on subprocess creation or invocation. Fixes
   `#7040 <https://github.com/datalad/datalad/issues/7040>`__ via `PR
   #7107 <https://github.com/datalad/datalad/pull/7107>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  Improved reporting when using ``dry-run`` with github-like
   ``create-sibling*`` commands (``-gin``, ``-gitea``, ``-github``,
   ``-gogs``). The result messages will now display names of the
   repositories which would be created (useful for recursive
   operations). `PR
   #7103 <https://github.com/datalad/datalad/pull/7103>`__ (by
   `@mslw <https://github.com/mslw>`__)

.. _section-26:

0.17.7 (2022-10-14)
===================

.. _bug-fixes-17:

Bug Fixes
---------

-  Let ``EnsureChoice`` report the value is failed validating. `PR
   #7067 <https://github.com/datalad/datalad/pull/7067>`__ (by
   `@mih <https://github.com/mih>`__)

-  Avoid writing to stdout/stderr from within datalad sshrun. This could
   lead to broken pipe errors when cloning via SSH and was superfluous
   to begin with. Fixes https://github.com/datalad/datalad/issues/6599
   via https://github.com/datalad/datalad/pull/7072 (by @bpoldrack)

-  BF: lock across threads check/instantiation of Flyweight instances.
   Fixes `#6598 <https://github.com/datalad/datalad/issues/6598>`__ via
   `PR #7075 <https://github.com/datalad/datalad/pull/7075>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _internal-15:

Internal
--------

-  Do not use ``gen4``-metadata methods in ``datalad metadata``-command.
   `PR #7001 <https://github.com/datalad/datalad/pull/7001>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  Revert “Remove chardet version upper limit” (introduced in
   0.17.6~11^2) to bring back upper limit <= 5.0.0 on chardet. Otherwise
   we can get some deprecation warnings from requests `PR
   #7057 <https://github.com/datalad/datalad/pull/7057>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Ensure that ``BatchedCommandError`` is raised if the subprocesses of
   ``BatchedCommand`` fails or raises a ``CommandError``. `PR
   #7068 <https://github.com/datalad/datalad/pull/7068>`__ (by
   `@christian-monch <https://github.com/christian-monch>`__)

-  RF: remove unused code str-ing PurePath. `PR
   #7073 <https://github.com/datalad/datalad/pull/7073>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Update GitHub Actions action versions. `PR
   #7082 <https://github.com/datalad/datalad/pull/7082>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

.. _tests-18:

Tests
-----

-  Fix broken test helpers for result record testing that would falsely
   pass. `PR #7002 <https://github.com/datalad/datalad/pull/7002>`__ (by
   `@bpoldrack <https://github.com/bpoldrack>`__)

.. _section-27:

0.17.6 (2022-09-21)
===================

.. _bug-fixes-18:

Bug Fixes
---------

-  UX: push - provide specific error with details if push failed due to
   permission issue. `PR
   #7011 <https://github.com/datalad/datalad/pull/7011>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Fix datalad –help to not have *Global options* empty with python 3.10
   and list options in “options:” section. `PR
   #7028 <https://github.com/datalad/datalad/pull/7028>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

-  Let ``create`` touch the dataset root, if not saving in parent
   dataset. `PR #7036 <https://github.com/datalad/datalad/pull/7036>`__
   (by `@mih <https://github.com/mih>`__)

-  Let ``get_status_dict()`` use exception message if none is passed.
   `PR #7037 <https://github.com/datalad/datalad/pull/7037>`__ (by
   `@mih <https://github.com/mih>`__)

-  Make choices for ``status|diff --annex`` and
   ``status|diff --untracked`` visible. `PR
   #7039 <https://github.com/datalad/datalad/pull/7039>`__ (by
   `@mih <https://github.com/mih>`__)

-  push: Assume 0 bytes pushed if git-annex does not provide bytesize.
   `PR #7049 <https://github.com/datalad/datalad/pull/7049>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _internal-16:

Internal
--------

-  Use scriv for CHANGELOG generation in release workflow. `PR
   #7009 <https://github.com/datalad/datalad/pull/7009>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

-  Stop using auto. `PR
   #7024 <https://github.com/datalad/datalad/pull/7024>`__ (by
   `@jwodder <https://github.com/jwodder>`__)

.. _tests-19:

Tests
-----

-  Allow for any 2 from first 3 to be consumed in test_gracefull_death.
   `PR #7041 <https://github.com/datalad/datalad/pull/7041>`__ (by
   `@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.17.5 (Fri Sep 02 2022)
========================

Bug Fix
-------

-  BF: blacklist 23.9.0 of keyring as introduces regression
   `#7003 <https://github.com/datalad/datalad/pull/7003>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Make the manpages build reproducible via datalad.source.epoch (to be
   used in Debian packaging)
   `#6997 <https://github.com/datalad/datalad/pull/6997>`__
   (`@lamby <https://github.com/lamby>`__ bot@datalad.org
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: backquote path/drive in Changelog
   `#6997 <https://github.com/datalad/datalad/pull/6997>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

Authors: 3
----------

-  Chris Lamb (`@lamby <https://github.com/lamby>`__)
-  DataLad Bot (bot@datalad.org)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.17.4 (Tue Aug 30 2022)
========================

.. _bug-fix-1:

Bug Fix
-------

-  BF: make logic more consistent for files=[] argument (which is False
   but not None)
   `#6976 <https://github.com/datalad/datalad/pull/6976>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Run pytests in parallel (-n 2) on appveyor
   `#6987 <https://github.com/datalad/datalad/pull/6987>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Add workflow for autogenerating changelog snippets
   `#6981 <https://github.com/datalad/datalad/pull/6981>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  Provide ``/dev/null`` (``b:\nul`` on Windows) instead of empty string
   as a git-repo to avoid reading local repo configuration
   `#6986 <https://github.com/datalad/datalad/pull/6986>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  RF: call_from_parser - move code into “else” to simplify reading etc
   `#6982 <https://github.com/datalad/datalad/pull/6982>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: if early attempt to parse resulted in error, setup subparsers
   `#6980 <https://github.com/datalad/datalad/pull/6980>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Run pytests in parallel (-n 2) on Travis
   `#6915 <https://github.com/datalad/datalad/pull/6915>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Send one character (no newline) to stdout in protocol test to
   guarantee a single “message” and thus a single custom value
   `#6978 <https://github.com/datalad/datalad/pull/6978>`__
   (`@christian-monch <https://github.com/christian-monch>`__)

.. _tests-20:

Tests
-----

-  TST: test_stalling – wait x10 not just x5 time
   `#6995 <https://github.com/datalad/datalad/pull/6995>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _authors-3-1:

Authors: 3
----------

-  Christian Mnch
   (`@christian-monch <https://github.com/christian-monch>`__)
-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.17.3 (Tue Aug 23 2022)
========================

.. _bug-fix-2:

Bug Fix
-------

-  BF: git_ignore_check do not overload possible value of stdout/err if
   present `#6937 <https://github.com/datalad/datalad/pull/6937>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  DOCfix: fix docstring GeneratorStdOutErrCapture to say that treats
   both stdout and stderr identically
   `#6930 <https://github.com/datalad/datalad/pull/6930>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Explain purpose of create-sibling-ria’s –post-update-hook
   `#6958 <https://github.com/datalad/datalad/pull/6958>`__
   (`@mih <https://github.com/mih>`__)
-  ENH+BF: get_parent_paths - make / into sep option and consistently
   use “/” as path separator
   `#6963 <https://github.com/datalad/datalad/pull/6963>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(TEMP): use git-annex from neurodebian -devel to gain fix for bug
   detected with datalad-crawler
   `#6965 <https://github.com/datalad/datalad/pull/6965>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(TST): make tests use *path* helper for Windows “friendliness” of
   the tests `#6955 <https://github.com/datalad/datalad/pull/6955>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(TST): prevent auto-upgrade of “remote” test sibling, do not use
   local path for URL
   `#6957 <https://github.com/datalad/datalad/pull/6957>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Forbid drop operation from symlink’ed annex (e.g. due to being cloned
   with –reckless=ephemeral) to prevent data-loss
   `#6959 <https://github.com/datalad/datalad/pull/6959>`__
   (`@mih <https://github.com/mih>`__)
-  Acknowledge git-config comment chars
   `#6944 <https://github.com/datalad/datalad/pull/6944>`__
   (`@mih <https://github.com/mih>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  Minor tuneups to please updated codespell
   `#6956 <https://github.com/datalad/datalad/pull/6956>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  TST: Add a testcase for #6950
   `#6957 <https://github.com/datalad/datalad/pull/6957>`__
   (`@adswa <https://github.com/adswa>`__)
-  BF+ENH(TST): fix typo in code of wtf filesystems reports
   `#6920 <https://github.com/datalad/datalad/pull/6920>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  DOC: Datalad -> DataLad
   `#6937 <https://github.com/datalad/datalad/pull/6937>`__
   (`@aqw <https://github.com/aqw>`__)
-  BF: fix typo which prevented silently to not show details of
   filesystems `#6930 <https://github.com/datalad/datalad/pull/6930>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(TST): allow for a annex repo version to upgrade if running in
   adjusted branches
   `#6927 <https://github.com/datalad/datalad/pull/6927>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  RF extensions github action to centralize configuration for
   extensions etc, use pytest for crawler
   `#6914 <https://github.com/datalad/datalad/pull/6914>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: travis - mark our directory as safe to interact with as root
   `#6919 <https://github.com/datalad/datalad/pull/6919>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: do not pretend we know what repo version git-annex would upgrade
   to `#6902 <https://github.com/datalad/datalad/pull/6902>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(TST): do not expect log message for guessing Path to be possibly a
   URL on windows
   `#6911 <https://github.com/datalad/datalad/pull/6911>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH(TST): Disable coverage reporting on travis while running pytest
   `#6898 <https://github.com/datalad/datalad/pull/6898>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  RF: just rename internal variable from unclear “op” to “io”
   `#6907 <https://github.com/datalad/datalad/pull/6907>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  DX: Demote loglevel of message on url parameters to DEBUG while
   guessing RI `#6891 <https://github.com/datalad/datalad/pull/6891>`__
   (`@adswa <https://github.com/adswa>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  Fix and expand datalad.runner type annotations
   `#6893 <https://github.com/datalad/datalad/pull/6893>`__
   (`@christian-monch <https://github.com/christian-monch>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  Use pytest to test datalad-metalad in test_extensions-workflow
   `#6892 <https://github.com/datalad/datalad/pull/6892>`__
   (`@christian-monch <https://github.com/christian-monch>`__)
-  Let push honor multiple publication dependencies declared via
   siblings `#6869 <https://github.com/datalad/datalad/pull/6869>`__
   (`@mih <https://github.com/mih>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH: upgrade versioneer from versioneer-0.20.dev0 to
   versioneer-0.23.dev0
   `#6888 <https://github.com/datalad/datalad/pull/6888>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH: introduce typing checking and GitHub workflow
   `#6885 <https://github.com/datalad/datalad/pull/6885>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  RF,ENH(TST): future proof testing of git annex version upgrade + test
   annex init on all supported versions
   `#6880 <https://github.com/datalad/datalad/pull/6880>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH(TST): test against supported git annex repo version 10 + make it
   a full sweep over tests
   `#6881 <https://github.com/datalad/datalad/pull/6881>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: RF f-string uses in logger to %-interpolations
   `#6886 <https://github.com/datalad/datalad/pull/6886>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Merge branch ‘bf-sphinx-5.1.0’ into maint
   `#6883 <https://github.com/datalad/datalad/pull/6883>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(DOC): workaround for #10701 of sphinx in 5.1.0
   `#6883 <https://github.com/datalad/datalad/pull/6883>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Clarify confusing INFO log message from get() on dataset installation
   `#6871 <https://github.com/datalad/datalad/pull/6871>`__
   (`@mih <https://github.com/mih>`__)
-  Protect again failing to load a command interface from an extension
   `#6879 <https://github.com/datalad/datalad/pull/6879>`__
   (`@mih <https://github.com/mih>`__)
-  Support unsetting config via ``datalad -c :<name>``
   `#6864 <https://github.com/datalad/datalad/pull/6864>`__
   (`@mih <https://github.com/mih>`__)
-  Fix DOC string typo in the path within AnnexRepo.annexstatus, and
   replace with proper sphinx reference
   `#6858 <https://github.com/datalad/datalad/pull/6858>`__
   (`@christian-monch <https://github.com/christian-monch>`__)
-  Improved support for saving typechanges
   `#6793 <https://github.com/datalad/datalad/pull/6793>`__
   (`@mih <https://github.com/mih>`__)

Pushed to ``maint``
-------------------

-  BF: Remove duplicate ds key from result record
   (`@adswa <https://github.com/adswa>`__)
-  DOC: fix capitalization of service names
   (`@aqw <https://github.com/aqw>`__)

.. _tests-21:

Tests
-----

-  BF(TST,workaround): just xfail failing archives test on NFS
   `#6912 <https://github.com/datalad/datalad/pull/6912>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

Authors: 5
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  Alex Waite (`@aqw <https://github.com/aqw>`__)
-  Christian Mnch
   (`@christian-monch <https://github.com/christian-monch>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.17.2 (Sat Jul 16 2022)
========================

.. _bug-fix-3:

Bug Fix
-------

-  BF(TST): do proceed to proper test for error being caught for recent
   git-annex on windows with symlinks
   `#6850 <https://github.com/datalad/datalad/pull/6850>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Addressing problem testing against python 3.10 on Travis (skip more
   annex versions)
   `#6842 <https://github.com/datalad/datalad/pull/6842>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  XFAIL test_runner_parametrized_protocol on python3.8 when getting
   duplicate output
   `#6837 <https://github.com/datalad/datalad/pull/6837>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: Make create’s check for procedures work with several again
   `#6841 <https://github.com/datalad/datalad/pull/6841>`__
   (`@adswa <https://github.com/adswa>`__)
-  Support older pytests
   `#6836 <https://github.com/datalad/datalad/pull/6836>`__
   (`@jwodder <https://github.com/jwodder>`__)

.. _authors-3-2:

Authors: 3
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.17.1 (Mon Jul 11 2022)
========================

.. _bug-fix-4:

Bug Fix
-------

-  DOC: minor fix - consistent DataLad (not Datalad) in docs and
   CHANGELOG `#6830 <https://github.com/datalad/datalad/pull/6830>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  DOC: fixup/harmonize Changelog for 0.17.0 a little
   `#6828 <https://github.com/datalad/datalad/pull/6828>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: use –python-match minor option in new datalad-installer release
   to match outside version of Python
   `#6827 <https://github.com/datalad/datalad/pull/6827>`__
   (`@christian-monch <https://github.com/christian-monch>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  Do not quote paths for ssh >= 9
   `#6826 <https://github.com/datalad/datalad/pull/6826>`__
   (`@christian-monch <https://github.com/christian-monch>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  Suppress DeprecationWarning to allow for distutils to be used
   `#6819 <https://github.com/datalad/datalad/pull/6819>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  RM(TST): remove testing of datalad.test which was removed from 0.17.0
   `#6822 <https://github.com/datalad/datalad/pull/6822>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Avoid import of nose-based tests.utils, make skip_if_no_module() and
   skip_if_no_network() allowed at module level
   `#6817 <https://github.com/datalad/datalad/pull/6817>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  BF(TST): use higher level asyncio.run instead of
   asyncio.get_event_loop in test_inside_async
   `#6808 <https://github.com/datalad/datalad/pull/6808>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _authors-3-3:

Authors: 3
----------

-  Christian Mnch
   (`@christian-monch <https://github.com/christian-monch>`__)
-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.17.0 (Thu Jul 7 2022) – pytest migration
==========================================

.. _enhancements-and-new-features-5:

Enhancements and new features
-----------------------------

-  “log” progress bar now reports about starting a specific action as
   well. `#6756 <https://github.com/datalad/datalad/pull/6756>`__ (by
   @yarikoptic)
-  Documentation and behavior of traceback reporting for log messages
   via ``DATALAD_LOG_TRACEBACK`` was improved to yield a more compact
   report. The documentation for this feature has been clarified.
   `#6746 <https://github.com/datalad/datalad/pull/6746>`__ (by @mih)
-  ``datalad unlock`` gained a progress bar.
   `#6704 <https://github.com/datalad/datalad/pull/6704>`__ (by @adswa)
-  When ``create-sibling-gitlab`` is called on non-existing subdatasets
   or paths it now returns an impossible result instead of no feedback
   at all. `#6701 <https://github.com/datalad/datalad/pull/6701>`__ (by
   @adswa)
-  ``datalad wtf`` includes a report on file system types of commonly
   used paths. `#6664 <https://github.com/datalad/datalad/pull/6664>`__
   (by @adswa)
-  Use next generation metadata code in search, if it is available.
   `#6518 <https://github.com/datalad/datalad/pull/6518>`__ (by
   @christian-monch)

Deprecations and removals
-------------------------

-  Remove unused and untested log helpers ``NoProgressLog`` and
   ``OnlyProgressLog``.
   `#6747 <https://github.com/datalad/datalad/pull/6747>`__ (by @mih)
-  Remove unused ``sorted_files()`` helper.
   `#6722 <https://github.com/datalad/datalad/pull/6722>`__ (by @adswa)
-  Discontinued the value ``stdout`` for use with the config variable
   ``datalad.log.target`` as its use would inevitably break special
   remote implementations.
   `#6675 <https://github.com/datalad/datalad/pull/6675>`__ (by
   @bpoldrack)
-  ``AnnexRepo.add_urls()`` is deprecated in favor of
   ``AnnexRepo.add_url_to_file()`` or a direct call to
   ``AnnexRepo.call_annex()``.
   `#6667 <https://github.com/datalad/datalad/pull/6667>`__ (by @mih)
-  ``datalad test`` command and supporting functionality (e.g.,
   ``datalad.test``) were removed.
   `#6273 <https://github.com/datalad/datalad/pull/6273>`__ (by
   @jwodder)

.. _bug-fixes-19:

Bug Fixes
---------

-  ``export-archive`` does not rely on ``normalize_path()`` methods
   anymore and became more robust when called from subdirectories.
   `#6745 <https://github.com/datalad/datalad/pull/6745>`__ (by @adswa)
-  Sanitize keys before checking content availability to ensure that the
   content availability of files with URL- or custom backend keys is
   correctly determined and marked.
   `#6663 <https://github.com/datalad/datalad/pull/6663>`__ (by @adswa)
-  Ensure saving a new subdataset to a superdataset yields a valid
   ``.gitmodules`` record regardless of whether and how a path
   constraint is given to the ``save()`` call. Fixes #6547
   `#6790 <https://github.com/datalad/datalad/pull/6790>`__ (by @mih)
-  ``save`` now repairs annex symlinks broken by a ``git-mv`` operation
   prior recording a new dataset state. Fixes #4967
   `#6795 <https://github.com/datalad/datalad/pull/6795>`__ (by @mih)

.. _documentation-11:

Documentation
-------------

-  API documentation for log helpers, like ``log_progress()`` is now
   included in the renderer documentation.
   `#6746 <https://github.com/datalad/datalad/pull/6746>`__ (by @mih)
-  New design document on progress reporting.
   `#6734 <https://github.com/datalad/datalad/pull/6734>`__ (by @mih)
-  Explain downstream consequences of using ``--fast`` option in
   ``addurls``. `#6684 <https://github.com/datalad/datalad/pull/6684>`__
   (by @jdkent)

.. _internal-17:

Internal
--------

-  Inline code of ``create-sibling-ria`` has been refactored to an
   internal helper to check for siblings with particular names across
   dataset hierarchies in ``datalad-next``, and is reintroduced into
   core to modularize the code base further.
   `#6706 <https://github.com/datalad/datalad/pull/6706>`__ (by @adswa)
-  ``get_initialized_logger`` now lets a given ``logtarget`` take
   precedence over ``datalad.log.target``.
   `#6675 <https://github.com/datalad/datalad/pull/6675>`__ (by
   @bpoldrack)
-  Many uses of deprecated call options were replaced with the
   recommended ones.
   `#6273 <https://github.com/datalad/datalad/pull/6273>`__ (by
   @jwodder)
-  Get rid of ``asyncio`` import by defining few noops methods from
   ``asyncio.protocols.SubprocessProtocol`` directly in
   ``WitlessProtocol``.
   `#6648 <https://github.com/datalad/datalad/pull/6648>`__ (by
   @yarikoptic)
-  Consolidate ``GitRepo.remove()`` and ``AnnexRepo.remove()`` into a
   single implementation.
   `#6783 <https://github.com/datalad/datalad/pull/6783>`__ (by @mih) ##
   Tests
-  Discontinue use of ``with_testrepos`` decorator other than for the
   deprecation cycle for ``nose``.
   `#6690 <https://github.com/datalad/datalad/pull/6690>`__ (by @mih
   @bpoldrack) See
   `#6144 <https://github.com/datalad/datalad/issues/6144>`__ for full
   list of changes.
-  Remove usage of deprecated ``AnnexRepo.add_urls`` in tests.
   `#6683 <https://github.com/datalad/datalad/pull/6683>`__ (by
   @bpoldrack)
-  Minimalistic (adapters, no assert changes, etc) migration from
   ``nose`` to ``pytest``. Support functionality possibly used by
   extensions and relying on ``nose`` helpers is left in place to avoid
   affecting their run time and defer migration of their test setups..
   `#6273 <https://github.com/datalad/datalad/pull/6273>`__ (by
   @jwodder)

Authors: 7
----------

-  Yaroslav Halchenko (@yarikoptic)
-  Michael Hanke (@mih)
-  Benjamin Poldrack (@bpoldrack)
-  Adina Wagner (@adswa)
-  John T. Wodder (@jwodder)
-  Christian Mnch (@christian-monch)
-  James Kent (@jdkent)

0.16.7 (Wed Jul 06 2022)
========================

.. _bug-fix-5:

Bug Fix
-------

-  Fix broken annex symlink after git-mv before saving + fix a race
   condition in ssh copy test
   `#6809 <https://github.com/datalad/datalad/pull/6809>`__
   (`@christian-monch <https://github.com/christian-monch>`__
   `@mih <https://github.com/mih>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  Do not ignore already known status info on submodules
   `#6790 <https://github.com/datalad/datalad/pull/6790>`__
   (`@mih <https://github.com/mih>`__)
-  Fix “common data source” test to use a valid URL (maint-based &
   extended edition)
   `#6788 <https://github.com/datalad/datalad/pull/6788>`__
   (`@mih <https://github.com/mih>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  Upload coverage from extension tests to Codecov
   `#6781 <https://github.com/datalad/datalad/pull/6781>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  Clean up line end handling in GitRepo
   `#6768 <https://github.com/datalad/datalad/pull/6768>`__
   (`@christian-monch <https://github.com/christian-monch>`__)
-  Do not skip file-URL tests on windows
   `#6772 <https://github.com/datalad/datalad/pull/6772>`__
   (`@christian-monch <https://github.com/christian-monch>`__)
-  Fix test errors caused by updated chardet v5 release
   `#6777 <https://github.com/datalad/datalad/pull/6777>`__
   (`@christian-monch <https://github.com/christian-monch>`__)
-  Preserve final trailing slash in ``call_git()`` output
   `#6754 <https://github.com/datalad/datalad/pull/6754>`__
   (`@adswa <https://github.com/adswa>`__
   `@yarikoptic <https://github.com/yarikoptic>`__
   `@christian-monch <https://github.com/christian-monch>`__)

.. _pushed-to-maint-1:

Pushed to ``maint``
-------------------

-  Make sure a subdataset is saved with a complete .gitmodules record
   (`@mih <https://github.com/mih>`__)

.. _authors-5-1:

Authors: 5
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  Christian Mnch
   (`@christian-monch <https://github.com/christian-monch>`__)
-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.16.6 (Tue Jun 14 2022)
========================

.. _bug-fix-6:

Bug Fix
-------

-  Prevent duplicated result rendering when searching in default
   datasets `#6765 <https://github.com/datalad/datalad/pull/6765>`__
   (`@christian-monch <https://github.com/christian-monch>`__)
-  BF(workaround): skip test_ria_postclonecfg on OSX for now
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(workaround to #6759): if saving credential failed, just log error
   and continue `#6762 <https://github.com/datalad/datalad/pull/6762>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Prevent reentry of a runner instance
   `#6737 <https://github.com/datalad/datalad/pull/6737>`__
   (`@christian-monch <https://github.com/christian-monch>`__)

Authors: 2
----------

-  Christian Mnch
   (`@christian-monch <https://github.com/christian-monch>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.16.5 (Wed Jun 08 2022)
========================

.. _bug-fix-7:

Bug Fix
-------

-  BF: push to github - remove datalad-push-default-first config only in
   non-dry run to ensure we push default branch separately in next step
   `#6750 <https://github.com/datalad/datalad/pull/6750>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  In addition to default (system) ssh version, report configured ssh;
   fix ssh version parsing on Windows
   `#6729 <https://github.com/datalad/datalad/pull/6729>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

Authors: 1
----------

-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.16.4 (Thu Jun 02 2022)
========================

.. _bug-fix-8:

Bug Fix
-------

-  BF(TST): RO operations - add test directory into git safe.directory
   `#6726 <https://github.com/datalad/datalad/pull/6726>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  DOC: fixup of docstring for skip_ssh
   `#6727 <https://github.com/datalad/datalad/pull/6727>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  DOC: Set language in Sphinx config to en
   `#6727 <https://github.com/datalad/datalad/pull/6727>`__
   (`@adswa <https://github.com/adswa>`__)
-  BF: Catch KeyErrors from unavailable WTF infos
   `#6712 <https://github.com/datalad/datalad/pull/6712>`__
   (`@adswa <https://github.com/adswa>`__)
-  Add annex.private to ephemeral clones. That would make git-annex not
   assign shared (in git-annex branch) annex uuid.
   `#6702 <https://github.com/datalad/datalad/pull/6702>`__
   (`@bpoldrack <https://github.com/bpoldrack>`__
   `@adswa <https://github.com/adswa>`__)
-  BF: require argcomplete version at least 1.12.3 to test/operate
   correctly `#6693 <https://github.com/datalad/datalad/pull/6693>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Replace Zenodo DOI with JOSS for due credit
   `#6725 <https://github.com/datalad/datalad/pull/6725>`__
   (`@adswa <https://github.com/adswa>`__)

.. _authors-3-4:

Authors: 3
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  Benjamin Poldrack (`@bpoldrack <https://github.com/bpoldrack>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.16.3 (Thu May 12 2022)
========================

.. _bug-fix-9:

Bug Fix
-------

-  No change for a PR to trigger release
   `#6692 <https://github.com/datalad/datalad/pull/6692>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Sanitize keys before checking content availability to ensure correct
   value for keys with URL or custom backend
   `#6665 <https://github.com/datalad/datalad/pull/6665>`__
   (`@adswa <https://github.com/adswa>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  Change a key-value pair in drop result record
   `#6625 <https://github.com/datalad/datalad/pull/6625>`__
   (`@mslw <https://github.com/mslw>`__)
-  Link docs of datalad-next
   `#6677 <https://github.com/datalad/datalad/pull/6677>`__
   (`@mih <https://github.com/mih>`__)
-  Fix ``GitRepo.get_branch_commits_()`` to handle branch names
   conflicts with paths
   `#6661 <https://github.com/datalad/datalad/pull/6661>`__
   (`@mih <https://github.com/mih>`__)
-  OPT: AnnexJsonProtocol - avoid dragging possibly long data around
   `#6660 <https://github.com/datalad/datalad/pull/6660>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Remove two too prominent create() INFO log message that duplicate
   DEBUG log and harmonize some other log messages
   `#6638 <https://github.com/datalad/datalad/pull/6638>`__
   (`@mih <https://github.com/mih>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  Remove unsupported parameter create_sibling_ria(existing=None)
   `#6637 <https://github.com/datalad/datalad/pull/6637>`__
   (`@mih <https://github.com/mih>`__)
-  Add released plugin to .autorc to annotate PRs on when released
   `#6639 <https://github.com/datalad/datalad/pull/6639>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

Authors: 4
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Micha Szczepanik (`@mslw <https://github.com/mslw>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.16.2 (Thu Apr 21 2022)
========================

.. _bug-fix-10:

Bug Fix
-------

-  Demote (to level 1 from DEBUG) and speed-up API doc logging
   (parseParameters)
   `#6635 <https://github.com/datalad/datalad/pull/6635>`__
   (`@mih <https://github.com/mih>`__)
-  Factor out actual data transfer in push
   `#6618 <https://github.com/datalad/datalad/pull/6618>`__
   (`@christian-monch <https://github.com/christian-monch>`__)
-  ENH: include version of datalad in tests teardown Versions: report
   `#6628 <https://github.com/datalad/datalad/pull/6628>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  MNT: Require importlib-metadata >=3.6 for Python < 3.10 for
   entry_points taking kwargs
   `#6631 <https://github.com/datalad/datalad/pull/6631>`__
   (`@effigies <https://github.com/effigies>`__)
-  Factor out credential handling of create-sibling-ghlike
   `#6627 <https://github.com/datalad/datalad/pull/6627>`__
   (`@mih <https://github.com/mih>`__)
-  BF: Fix wrong key name of annex’ JSON records
   `#6624 <https://github.com/datalad/datalad/pull/6624>`__
   (`@bpoldrack <https://github.com/bpoldrack>`__)

.. _pushed-to-maint-2:

Pushed to ``maint``
-------------------

-  Fix typo in changelog (`@mih <https://github.com/mih>`__)
-  [ci skip] minor typo fix
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _authors-5-2:

Authors: 5
----------

-  Benjamin Poldrack (`@bpoldrack <https://github.com/bpoldrack>`__)
-  Chris Markiewicz (`@effigies <https://github.com/effigies>`__)
-  Christian Mnch
   (`@christian-monch <https://github.com/christian-monch>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.16.1 (Fr Apr 8 2022) – April Fools’ Release
=============================================

-  Fixes forgotten changelog in docs

0.16.0 (Fr Apr 8 2022) – Spring cleaning!
=========================================

.. _enhancements-and-new-features-6:

Enhancements and new features
-----------------------------

-  A new set of ``create-sibling-*`` commands reimplements the
   GitHub-platform support of ``create-sibling-github`` and adds support
   to interface three new platforms in a unified fashion: GIN
   (``create-sibling-gin``), GOGS (``create-sibling-gogs``), and Gitea
   (``create-sibling-gitea``). All commands rely on personal access
   tokens only for authentication, allow for specifying one of several
   stored credentials via a uniform ``--credential`` parameter, and
   support a uniform ``--dry-run`` mode for testing without network.
   `#5949 <https://github.com/datalad/datalad/pull/5949>`__ (by @mih)
-  ``create-sibling-github`` now has supports direct specification of
   organization repositories via a ``[<org>/]repo``\ syntax
   `#5949 <https://github.com/datalad/datalad/pull/5949>`__ (by @mih)
-  ``create-sibling-gitlab`` gained a ``--dry-run`` parameter to match
   the corresponding parameters in
   ``create-sibling-{github,gin,gogs,gitea}``
   `#6013 <https://github.com/datalad/datalad/pull/6013>`__ (by @adswa)
-  The ``--new-store-ok`` parameter of ``create-sibling-ria`` only
   creates new RIA stores when explicitly provided
   `#6045 <https://github.com/datalad/datalad/pull/6045>`__ (by @adswa)
-  The default performance of ``status()`` and ``diff()`` commands is
   improved by up to 700% removing file-type evaluation as a default
   operation, and simplifying the type reporting rule
   `#6097 <https://github.com/datalad/datalad/pull/6097>`__ (by @mih)
-  ``drop()`` and ``remove()`` were reimplemented in full,
   conceptualized as the antagonist commands to ``get()`` and
   ``clone()``. A new, harmonized set of parameters
   (``--what ['filecontent', 'allkeys', 'datasets', 'all']``,
   ``--reckless ['modification', 'availability', 'undead', 'kill']``)
   simplifies their API. Both commands include additional safeguards.
   ``uninstall`` is replaced with a thin shim command around ``drop()``
   `#6111 <https://github.com/datalad/datalad/pull/6111>`__ (by @mih)
-  ``add_archive_content()`` was refactored into a dataset method and
   gained progress bars
   `#6105 <https://github.com/datalad/datalad/pull/6105>`__ (by @adswa)
-  The ``datalad`` and ``datalad-archives`` special remotes have been
   reimplemented based on ``AnnexRemote``
   `#6165 <https://github.com/datalad/datalad/pull/6165>`__ (by @mih)
-  The ``result_renderer()`` semantics were decomplexified and
   harmonized. The previous ``default`` result renderer was renamed to
   ``generic``. `#6174 <https://github.com/datalad/datalad/pull/6174>`__
   (by @mih)
-  ``get_status_dict`` learned to include exit codes in the case of
   CommandErrors
   `#5642 <https://github.com/datalad/datalad/pull/5642>`__ (by
   @yarikoptic)
-  ``datalad clone`` can now pass options to ``git-clone``, adding
   support for cloning specific tags or branches, naming siblings other
   names than ``origin``, and exposing ``git clone``\ ’s optimization
   arguments `#6218 <https://github.com/datalad/datalad/pull/6218>`__
   (by @kyleam and @mih)
-  Inactive BatchedCommands are cleaned up
   `#6206 <https://github.com/datalad/datalad/pull/6206>`__ (by
   @jwodder)
-  ``export-archive-ora`` learned to filter files exported to 7z
   archives `#6234 <https://github.com/datalad/datalad/pull/6234>`__ (by
   @mih and @bpinsard)
-  ``datalad run`` learned to glob recursively
   `#6262 <https://github.com/datalad/datalad/pull/6262>`__ (by @AKSoo)
-  The ORA remote learned to recover from interrupted uploads
   `#6267 <https://github.com/datalad/datalad/pull/6267>`__ (by @mih)
-  A new threaded runner with support for timeouts and generator-based
   subprocess communication is introduced and used in ``BatchedCommand``
   and ``AnnexRepo``
   `#6244 <https://github.com/datalad/datalad/pull/6244>`__ (by
   @christian-monch)
-  A new switch allows to enable librarymode and queries for the
   effective API in use
   `#6213 <https://github.com/datalad/datalad/pull/6213>`__ (by @mih)
-  ``run`` and ``rerun`` now support parallel jobs via ``--jobs``
   `#6279 <https://github.com/datalad/datalad/pull/6279>`__ (by @AKSoo)
-  A new ``foreach-dataset`` plumbing command allows to run commands on
   each (sub)dataset, similar to ``git submodule foreach``
   `#5517 <https://github.com/datalad/datalad/pull/5517>`__ (by
   @yarikoptic)
-  The ``dataset`` parameter is not restricted to only locally
   resolvable file-URLs anymore
   `#6276 <https://github.com/datalad/datalad/pull/6276>`__ (by
   @christian-monch)
-  DataLad’s credential system is now able to query ``git-credential``
   by specifying credential type ``git`` in the respective provider
   configuration
   `#5796 <https://github.com/datalad/datalad/pull/5796>`__ (by
   @bpoldrack)
-  DataLad now comes with a git credential helper
   ``git-credential-datalad`` allowing Git to query DataLad’s credential
   system `#5796 <https://github.com/datalad/datalad/pull/5796>`__ (by
   @bpoldrack and @mih)
-  The new runner now allows for multiple threads
   `#6371 <https://github.com/datalad/datalad/pull/6371>`__ (by
   @christian-monch)
-  A new configurationcommand provides an interface to manipulate and
   query the DataLad configuration.
   `#6306 <https://github.com/datalad/datalad/pull/6306>`__ (by @mih)

   -  Unlike the global Python-only datalad.cfg or dataset-specific
      Dataset.config configuration managers, this command offers a
      uniform API across the Python and the command line interfaces.
   -  This command was previously available in the mihextras extension
      as x-configuration, and has been merged into the core package in
      an improved version.
      `#5489 <https://github.com/datalad/datalad/pull/5489>`__ (by @mih)
   -  In its default dump mode, the command provides an annotated list
      of the effective configuration after considering all configuration
      sources, including hints on additional configuration settings and
      their supported values.

-  The command line interface help-reporting has been sped up by ~20%
   `#6370 <https://github.com/datalad/datalad/pull/6370>`__
   `#6378 <https://github.com/datalad/datalad/pull/6378>`__ (by @mih)
-  ``ConfigManager`` now supports reading committed dataset
   configuration in bare repositories. Analog to reading
   ``.datalad/config`` from a worktree, ``blob:HEAD:.datalad/config`` is
   read (e.g., the config committed in the default branch). The support
   includes \`\ ``reload()`` change detection using the gitsha of this
   file. The behavior for non-bare repositories is unchanged.
   `#6332 <https://github.com/datalad/datalad/pull/6332>`__ (by @mih)
-  The CLI help generation has been sped up, and now also supports the
   completion of parameter values for a fixed set of choices
   `#6415 <https://github.com/datalad/datalad/pull/6415>`__ (by @mih)
-  Individual command implementations can now declare a specific
   “on-failure” behavior by defining ``Interface.on_failure`` to be one
   of the supported modes (stop, continue, ignore). Previously, such a
   modification was only possible on a per-call basis.
   `#6430 <https://github.com/datalad/datalad/pull/6430>`__ (by @mih)
-  The ``run`` command changed its default “on-failure” behavior from
   ``continue`` to ``stop``. This change prevents the execution of a
   command in case a declared input can not be obtained. Previously,
   only an error result was yielded (and run eventually yielded a
   non-zero exit code or an ``IncompleteResultsException``), but the
   execution proceeded and potentially saved a dataset modification
   despite incomplete inputs, in case the command succeeded. This
   previous default behavior can still be achieved by calling run with
   the equivalent of ``--on-failure continue``
   `#6430 <https://github.com/datalad/datalad/pull/6430>`__ (by @mih)
-  The \`\ ``run`` command now provides readily executable, API-specific
   instructions how to save the results of a command execution that
   failed expectedly
   `#6434 <https://github.com/datalad/datalad/pull/6434>`__ (by @mih)
-  ``create-sibling --since=^`` mode will now be as fast as
   ``push --since=^`` to figure out for which subdatasets to create
   siblings `#6436 <https://github.com/datalad/datalad/pull/6436>`__ (by
   @yarikoptic)
-  When file names contain illegal characters or reserved file names
   that are incompatible with Windows systems a configurable check for
   ``save`` (``datalad.save.windows-compat-warning``) will either do
   nothing (``none``), emit an incompatibility warning (``warning``,
   default), or cause ``save`` to error (``error``)
   `#6291 <https://github.com/datalad/datalad/pull/6291>`__ (by @adswa)
-  Improve responsiveness of ``datalad drop`` in datasets with a large
   annex. `#6580 <https://github.com/datalad/datalad/pull/6580>`__ (by
   @christian-monch)
-  ``save`` code might operate faster on heavy file trees
   `#6581 <https://github.com/datalad/datalad/pull/6581>`__ (by
   @yarikoptic)
-  Removed a per-file overhead cost for ORA when downloading over HTTP
   `#6609 <https://github.com/datalad/datalad/pull/6609>`__ (by
   @bpoldrack)
-  A new module ``datalad.support.extensions`` offers the utility
   functions ``register_config()`` and ``has_config()`` that allow
   extension developers to announce additional configuration items to
   the central configuration management.
   `#6601 <https://github.com/datalad/datalad/pull/6601>`__ (by @mih)
-  When operating in a dirty dataset, ``export-to-figshare`` now yields
   and impossible result instead of raising a RunTimeError
   `#6543 <https://github.com/datalad/datalad/pull/6543>`__ (by @adswa)
-  Loading DataLad extension packages has been sped-up leading to
   between 2x and 4x faster run times for loading individual extensions
   and reporting help output across all installed extensions.
   `#6591 <https://github.com/datalad/datalad/pull/6591>`__ (by @mih)
-  Introduces the configuration key ``datalad.ssh.executable``. This key
   allows specifying an ssh-client executable that should be used by
   datalad to establish ssh-connections. The default value is ``ssh``
   unless on a Windows system where ``$WINDIR\System32\OpenSSH\ssh.exe``
   exists. In this case, the value defaults to
   ``$WINDIR\System32\OpenSSH\ssh.exe``.
   `#6553 <https://github.com/datalad/datalad/pull/6553>`__ (by
   @christian-monch)
-  create-sibling should perform much faster in case of ``--since``
   specification since would consider only submodules related to the
   changes since that point.
   `#6528 <https://github.com/datalad/datalad/pull/6528>`__ (by
   @yarikoptic)
-  A new configuration setting
   ``datalad.ssh.try-use-annex-bundled-git=yes|no`` can be used to
   influence the default remote git-annex bundle sensing for SSH
   connections. This was previously done unconditionally for any call to
   ``datalad sshrun`` (which is also used for any SSH-related Git or
   git-annex functionality triggered by DataLad-internal processing) and
   could incur a substantial per-call runtime cost. The new default is
   to not perform this sensing, because for, e.g., use as
   GIT_SSH_COMMAND there is no expectation to have a remote git-annex
   installation, and even with an existing git-annex/Git bundle on the
   remote, it is not certain that the bundled Git version is to be
   preferred over any other Git installation in a user’s PATH.
   `#6533 <https://github.com/datalad/datalad/pull/6533>`__ (by @mih)
-  ``run`` now yields a result record immediately after executing a
   command. This allows callers to use the standard
   ``--on-failure switch`` to control whether dataset modifications will
   be saved for a command that exited with an error.
   `#6447 <https://github.com/datalad/datalad/pull/6447>`__ (by @mih)

.. _deprecations-and-removals-1:

Deprecations and removals
-------------------------

-  The ``--pbs-runner`` commandline option (deprecated in ``0.15.0``)
   was removed `#5981 <https://github.com/datalad/datalad/pull/5981>`__
   (by @mih)
-  The dependency to PyGithub was dropped
   `#5949 <https://github.com/datalad/datalad/pull/5949>`__ (by @mih)
-  ``create-sibling-github``\ ’s credential handling was trimmed down to
   only allow personal access tokens, because GitHub discontinued
   user/password based authentication
   `#5949 <https://github.com/datalad/datalad/pull/5949>`__ (by @mih)
-  ``create-sibling-gitlab``\ ’s ``--dryrun`` parameter is deprecated in
   favor or ``--dry-run``
   `#6013 <https://github.com/datalad/datalad/pull/6013>`__ (by @adswa)
-  Internal obsolete ``Gitrepo.*_submodule`` methods were moved to
   ``datalad-deprecated``
   `#6010 <https://github.com/datalad/datalad/pull/6010>`__ (by @mih)
-  ``datalad/support/versions.py`` is unused in DataLad core and removed
   `#6115 <https://github.com/datalad/datalad/pull/6115>`__ (by
   @yarikoptic)
-  Support for the undocumented ``datalad.api.result-renderer`` config
   setting has been dropped
   `#6174 <https://github.com/datalad/datalad/pull/6174>`__ (by @mih)
-  Undocumented use of ``result_renderer=None`` is replaced with
   ``result_renderer='disabled'``
   `#6174 <https://github.com/datalad/datalad/pull/6174>`__ (by @mih)
-  ``remove``\ ’s ``--recursive`` argument has been deprecated
   `#6257 <https://github.com/datalad/datalad/pull/6257>`__ (by @mih)
-  The use of the internal helper ``get_repo_instance()`` is
   discontinued and deprecated
   `#6268 <https://github.com/datalad/datalad/pull/6268>`__ (by @mih)
-  Support for Python 3.6 has been dropped
   (`#6286 <https://github.com/datalad/datalad/pull/6286>`__ (by
   @christian-monch) and
   `#6364 <https://github.com/datalad/datalad/pull/6364>`__ (by
   @yarikoptic))
-  All but one Singularity recipe flavor have been removed due to their
   limited value with the end of life of Singularity Hub
   `#6303 <https://github.com/datalad/datalad/pull/6303>`__ (by @mih)
-  All code in module datalad.cmdline was (re)moved, only
   datalad.cmdline.helpers.get_repo_instanceis kept for a deprecation
   period (by @mih)
-  ``datalad.interface.common_opts.eval_default`` has been deprecated.
   All (command-specific) defaults for common interface parameters can
   be read from ``Interface`` class attributes
   (`#6391 <https://github.com/datalad/datalad/pull/6391>`__ (by @mih)
-  Remove unused and untested ``datalad.interface.utils`` helpers
   ``cls2cmdlinename`` and ``path_is_under``
   `#6392 <https://github.com/datalad/datalad/pull/6392>`__ (by @mih)
-  An unused code path for result rendering was removed from the CLI
   ``main()`` `#6394 <https://github.com/datalad/datalad/pull/6394>`__
   (by @mih)
-  ``create-sibling`` will require now ``"^"`` instead of an empty
   string for since option
   `#6436 <https://github.com/datalad/datalad/pull/6436>`__ (by
   @yarikoptic)
-  ``run`` no longer raises a ``CommandError`` exception for failed
   commands, but yields an ``error`` result that includes a superset of
   the information provided by the exception. This change impacts
   command line usage insofar as the exit code of the underlying command
   is no longer relayed as the exit code of the ``run`` command call –
   although ``run`` continues to exit with a non-zero exit code in case
   of an error. For Python API users, the nature of the raised exception
   changes from ``CommandError`` to ``IncompleteResultsError``, and the
   exception handling is now configurable using the standard
   ``on_failure`` command argument. The original ``CommandError``
   exception remains available via the ``exception`` property of the
   newly introduced result record for the command execution, and this
   result record is available via ``IncompleteResultsError.failed``, if
   such an exception is raised.
   `#6447 <https://github.com/datalad/datalad/pull/6447>`__ (by @mih)
-  Custom cast helpers were removed from datalad core and migrated to a
   standalone repository https://github.com/datalad/screencaster
   `#6516 <https://github.com/datalad/datalad/pull/6516>`__ (by @adswa)
-  The ``bundled`` parameter of ``get_connection_hash()`` is now ignored
   and will be removed with a future release.
   `#6532 <https://github.com/datalad/datalad/pull/6532>`__ (by @mih)
-  ``BaseDownloader.fetch()`` is logging download attempts on DEBUG
   (previously INFO) level to avoid polluting output of higher-level
   commands. `#6564 <https://github.com/datalad/datalad/pull/6564>`__
   (by @mih)

.. _bug-fixes-20:

Bug Fixes
---------

-  ``create-sibling-gitlab`` erroneously overwrote existing sibling
   configurations. A safeguard will now prevent overwriting and exit
   with an error result
   `#6015 <https://github.com/datalad/datalad/pull/6015>`__ (by @adswa)
-  ``create-sibling-gogs`` now relays HTTP500 errors, such as “no space
   left on device”
   `#6019 <https://github.com/datalad/datalad/pull/6019>`__ (by @mih)
-  ``annotate_paths()`` is removed from the last parts of code base that
   still contained it
   `#6128 <https://github.com/datalad/datalad/pull/6128>`__ (by @mih)
-  ``add_archive_content()`` doesn’t crash with ``--key`` and
   ``--use-current-dir`` anymore
   `#6105 <https://github.com/datalad/datalad/pull/6105>`__ (by @adswa)
-  ``run-procedure`` now returns an error result when a non-existent
   procedure name is specified
   `#6143 <https://github.com/datalad/datalad/pull/6143>`__ (by @mslw)
-  A fix for a silent failure of ``download-url --archive`` when
   extracting the archive
   `#6172 <https://github.com/datalad/datalad/pull/6172>`__ (by @adswa)
-  Uninitialized AnnexRepos can now be dropped
   `#6183 <https://github.com/datalad/datalad/pull/6183>`__ (by @mih)
-  Instead of raising an error, the formatters tests are skipped when
   the ``formatters`` module is not found
   `#6212 <https://github.com/datalad/datalad/pull/6212>`__ (by @adswa)
-  ``create-sibling-gin`` does not disable git-annex availability on Gin
   remotes anymore
   `#6230 <https://github.com/datalad/datalad/pull/6230>`__ (by @mih)
-  The ORA special remote messaging is fixed to not break the special
   remote protocol anymore and to better relay messages from exceptions
   to communicate underlying causes
   `#6242 <https://github.com/datalad/datalad/pull/6242>`__ (by @mih)
-  A ``keyring.delete()`` call was fixed to not call an uninitialized
   private attribute anymore
   `#6253 <https://github.com/datalad/datalad/pull/6253>`__ (by
   @bpoldrack)
-  An erroneous placement of result keyword arguments into a
   ``format()`` method instead of ``get_status_dict()`` of
   ``create-sibling-ria`` has been fixed
   `#6256 <https://github.com/datalad/datalad/pull/6256>`__ (by @adswa)
-  ``status``, ``run-procedure``, and ``metadata`` are no longer
   swallowing result-related messages in renderers
   `#6280 <https://github.com/datalad/datalad/pull/6280>`__ (by @mih)
-  ``uninstall`` now recommends the new ``--reckless`` parameter instead
   of the deprecated ``--nocheck`` parameter when reporting hints
   `#6277 <https://github.com/datalad/datalad/pull/6277>`__ (by @adswa)
-  ``download-url`` learned to handle Pathobjects
   `#6317 <https://github.com/datalad/datalad/pull/6317>`__ (by @adswa)
-  Restore default result rendering behavior broken by Key interface
   documentation
   `#6394 <https://github.com/datalad/datalad/pull/6394>`__ (by @mih)
-  Fix a broken check for file presence in the ``ConfigManager`` that
   could have caused a crash in rare cases when a config file is removed
   during the process runtime
   `#6332 <https://github.com/datalad/datalad/pull/6332>`__ (by @mih)
   \`- ``ConfigManager.get_from_source()`` now accesses the correct
   information when using the documented ``source='local'``, avoiding a
   crash `#6332 <https://github.com/datalad/datalad/pull/6332>`__ (by
   @mih)
-  ``run`` no longer let’s the internal call to ``save`` render its
   results unconditionally, but the parameterization f run determines
   the effective rendering format.
   `#6421 <https://github.com/datalad/datalad/pull/6421>`__ (by @mih)
-  Remove an unnecessary and misleading warning from the runner
   `#6425 <https://github.com/datalad/datalad/pull/6425>`__ (by
   @christian-monch)
-  A number of commands stopped to double-report results
   `#6446 <https://github.com/datalad/datalad/pull/6446>`__ (by @adswa)
-  ``create-sibling-ria`` no longer creates an ``annex/objects``
   directory in-store, when called with ``--no-storage-sibling``.
   `#6495 <https://github.com/datalad/datalad/pull/6495>`__ (by
   @bpoldrack )
-  Improve error message when an invalid URL is given to ``clone``.
   `#6500 <https://github.com/datalad/datalad/pull/6500>`__ (by @mih)
-  DataLad declares a minimum version dependency to ``keyring >= 20.0``
   to ensure that token-based authentication can be used.
   `#6515 <https://github.com/datalad/datalad/pull/6515>`__ (by @adswa)
-  ORA special remote tries to obtain permissions when dropping a key
   from a RIA store rather than just failing. Thus having the same
   permissions in the store’s object trees as one directly managed by
   git-annex would have, works just fine now.
   `#6493 <https://github.com/datalad/datalad/pull/6493>`__ (by
   @bpoldrack )
-  ``require_dataset()`` now uniformly raises ``NoDatasetFound`` when no
   dataset was found. Implementations that catch the previously
   documented ``InsufficientArgumentsError`` or the actually raised
   ``ValueError`` will continue to work, because ``NoDatasetFound`` is
   derived from both types.
   `#6521 <https://github.com/datalad/datalad/pull/6521>`__ (by @mih)
-  Keyboard-interactive authentication is now possibly with
   non-multiplexed SSH connections (i.e., when no connection sharing is
   possible, due to lack of socket support, for example on Windows).
   Previously, it was disabled forcefully by DataLad for no valid
   reason. `#6537 <https://github.com/datalad/datalad/pull/6537>`__ (by
   @mih)
-  Remove duplicate exception type in reporting of top-level CLI
   exception handler.
   `#6563 <https://github.com/datalad/datalad/pull/6563>`__ (by @mih)
-  Fixes DataLad’s parsing of git-annex’ reporting on unknown paths
   depending on its version and the value of the ``annex.skipunknown``
   config. `#6550 <https://github.com/datalad/datalad/pull/6550>`__ (by
   @bpoldrack)
-  Fix ORA special remote not properly reporting on HTTP failures.
   `#6535 <https://github.com/datalad/datalad/pull/6535>`__ (by
   @bpoldrack)
-  ORA special remote didn’t show per-file progress bars when
   downloading over HTTP
   `#6609 <https://github.com/datalad/datalad/pull/6609>`__ (by
   @bpoldrack)
-  ``save`` now can commit the change where file becomes a directory
   with a staged for commit file.
   `#6581 <https://github.com/datalad/datalad/pull/6581>`__ (by
   @yarikoptic)
-  ``create-sibling`` will no longer create siblings for not yet saved
   new subdatasets, and will now create sub-datasets nested in the
   subdatasets which did not yet have those siblings.
   `#6603 <https://github.com/datalad/datalad/pull/6603>`__ (by
   @yarikoptic)

.. _documentation-12:

Documentation
-------------

-  A new design document sheds light on result records
   `#6167 <https://github.com/datalad/datalad/pull/6167>`__ (by @mih)
-  The ``disabled`` result renderer mode is documented
   `#6174 <https://github.com/datalad/datalad/pull/6174>`__ (by @mih)
-  A new design document sheds light on the ``datalad`` and
   ``datalad-archives`` special remotes
   `#6181 <https://github.com/datalad/datalad/pull/6181>`__ (by @mih)
-  A new design document sheds light on ``BatchedCommand`` and
   ``BatchedAnnex``
   `#6203 <https://github.com/datalad/datalad/pull/6203>`__ (by
   @christian-monch)
-  A new design document sheds light on standard parameters
   `#6214 <https://github.com/datalad/datalad/pull/6214>`__ (by @adswa)
-  The DataLad project adopted the Contributor Covenant COC v2.1
   `#6236 <https://github.com/datalad/datalad/pull/6236>`__ (by @adswa)
-  Docstrings learned to include Sphinx’ “version added” and
   “deprecated” directives
   `#6249 <https://github.com/datalad/datalad/pull/6249>`__ (by @mih)
-  A design document sheds light on basic docstring handling and
   formatting `#6249 <https://github.com/datalad/datalad/pull/6249>`__
   (by @mih)
-  A new design document sheds light on position versus keyword
   parameter usage
   `#6261 <https://github.com/datalad/datalad/pull/6261>`__ (by
   @yarikoptic)
-  ``create-sibling-gin``\ ’s examples have been improved to suggest
   ``push`` as an additional step to ensure proper configuration
   `#6289 <https://github.com/datalad/datalad/pull/6289>`__ (by @mslw)
-  A new `document <http://docs.datalad.org/credentials.html>`__
   describes the credential system from a user’s perspective
   `#5796 <https://github.com/datalad/datalad/pull/5796>`__ (by
   @bpoldrack)
-  Enhance the `design
   document <http://docs.datalad.org/design/credentials.html>`__ on
   DataLad’s credential system
   `#5796 <https://github.com/datalad/datalad/pull/5796>`__ (by
   @bpoldrack)
-  The documentation of the configuration command now details all
   locations DataLad is reading configuration items from, and their
   respective rules of precedence
   `#6306 <https://github.com/datalad/datalad/pull/6306>`__ (by @mih)
-  API docs for datalad.interface.base are now included in the
   documentation
   `#6378 <https://github.com/datalad/datalad/pull/6378>`__ (by @mih)
-  A new design document is provided that describes the basics of the
   command line interface implementation
   `#6382 <https://github.com/datalad/datalad/pull/6382>`__ (by @mih)
-  The \`\ ``datalad.interface.base.Interface`` class, the basis of all
   DataLad command implementations, has been extensively documented to
   provide an overview of basic principles and customization
   possibilities
   `#6391 <https://github.com/datalad/datalad/pull/6391>`__ (by @mih)
-  ``--since=^`` mode of operation of ``create-sibling`` is documented
   now `#6436 <https://github.com/datalad/datalad/pull/6436>`__ (by
   @yarikoptic)

.. _internal-18:

Internal
--------

-  The internal ``status()`` helper was equipped with docstrings and
   promotes “breadth-first” reporting with a new parameter
   ``reporting_order``
   `#6006 <https://github.com/datalad/datalad/pull/6006>`__ (by @mih)
-  ``AnnexRepo.get_file_annexinfo()`` is introduced for more convenient
   queries for single files and replaces a now deprecated
   ``AnnexRepo.get_file_key()`` to receive information with fewer calls
   to Git `#6104 <https://github.com/datalad/datalad/pull/6104>`__ (by
   @mih)
-  A new ``get_paths_by_ds()`` helper exposes ``status``\ ’ path
   normalization and sorting
   `#6110 <https://github.com/datalad/datalad/pull/6110>`__ (by @mih)
-  ``status`` is optimized with a cache for dataset roots
   `#6137 <https://github.com/datalad/datalad/pull/6137>`__ (by
   @yarikoptic)
-  The internal ``get_func_args_doc()`` helper with Python 2 is removed
   from DataLad core
   `#6175 <https://github.com/datalad/datalad/pull/6175>`__ (by
   @yarikoptic)
-  Further restructuring of the source tree to better reflect the
   internal dependency structure of the code: ``AddArchiveContent`` is
   moved from ``datalad/interface`` to ``datalad/local``
   (`#6188 <https://github.com/datalad/datalad/pull/6188>`__ (by @mih)),
   ``Clean`` is moved from ``datalad/interface`` to ``datalad/local``
   (`#6191 <https://github.com/datalad/datalad/pull/6191>`__ (by @mih)),
   ``Unlock`` is moved from ``datalad/interface`` to ``datalad/local``
   (`#6192 <https://github.com/datalad/datalad/pull/6192>`__ (by @mih)),
   ``DownloadURL`` is moved from ``datalad/interface`` to
   ``datalad/local``
   (`#6217 <https://github.com/datalad/datalad/pull/6217>`__ (by @mih)),
   ``Rerun`` is moved from ``datalad/interface`` to ``datalad/local``
   (`#6220 <https://github.com/datalad/datalad/pull/6220>`__ (by @mih)),
   ``RunProcedure`` is moved from ``datalad/interface`` to
   ``datalad/local``
   (`#6222 <https://github.com/datalad/datalad/pull/6222>`__ (by @mih)).
   The interface command list is restructured and resorted
   `#6223 <https://github.com/datalad/datalad/pull/6223>`__ (by @mih)
-  ``wrapt`` is replaced with functools’ ``wraps``
   `#6190 <https://github.com/datalad/datalad/pull/6190>`__ (by
   @yariktopic)
-  The unmaintained ``appdirs`` library has been replaced with
   ``platformdirs``
   `#6198 <https://github.com/datalad/datalad/pull/6198>`__ (by @adswa)
-  Modelines mismatching the code style in source files were fixed
   `#6263 <https://github.com/datalad/datalad/pull/6263>`__ (by @AKSoo)
-  ``datalad/__init__.py`` has been cleaned up
   `#6271 <https://github.com/datalad/datalad/pull/6271>`__ (by @mih)
-  ``GitRepo.call_git_items`` is implemented with a generator-based
   runner `#6278 <https://github.com/datalad/datalad/pull/6278>`__ (by
   @christian-monch)
-  Separate positional from keyword arguments in the Python API to match
   CLI with ``*``
   `#6176 <https://github.com/datalad/datalad/pull/6176>`__ (by
   @yarikoptic),
   `#6304 <https://github.com/datalad/datalad/pull/6304>`__ (by
   @christian-monch)
-  ``GitRepo.bare`` does not require the ConfigManager anymore
   `#6323 <https://github.com/datalad/datalad/pull/6323>`__ (by @mih)
-  ``_get_dot_git()`` was reimplemented to be more efficient and
   consistent, by testing for common scenarios first and introducing a
   consistently applied ``resolved`` flag for result path reporting
   `#6325 <https://github.com/datalad/datalad/pull/6325>`__ (by @mih)
-  All data files under ``datalad`` are now included when installing
   DataLad `#6336 <https://github.com/datalad/datalad/pull/6336>`__ (by
   @jwodder)
-  Add internal method for non-interactive provider/credential storing
   `#5796 <https://github.com/datalad/datalad/pull/5796>`__ (by
   @bpoldrack)
-  Allow credential classes to have a context set, consisting of a URL
   they are to be used with and a dataset DataLad is operating on,
   allowing to consider “local” and “dataset” config locations
   `#5796 <https://github.com/datalad/datalad/pull/5796>`__ (by
   @bpoldrack)
-  The Interface method ``get_refds_path()`` was deprecated
   `#6387 <https://github.com/datalad/datalad/pull/6387>`__ (by @adswa)
-  ``datalad.interface.base.Interface`` is now an abstract class
   `#6391 <https://github.com/datalad/datalad/pull/6391>`__ (by @mih)
-  Simplified the decision making for result rendering, and reduced code
   complexity `#6394 <https://github.com/datalad/datalad/pull/6394>`__
   (by @mih)
-  Reduce code duplication in ``datalad.support.json_py``
   `#6398 <https://github.com/datalad/datalad/pull/6398>`__ (by @mih)
-  Use public ``ArgumentParser.parse_known_args`` instead of protected
   ``_parse_known_args``
   `#6414 <https://github.com/datalad/datalad/pull/6414>`__ (by
   @yarikoptic)
-  ``add-archive-content`` does not rely on the deprecated
   ``tempfile.mktemp`` anymore, but uses the more secure
   ``tempfile.mkdtemp``
   `#6428 <https://github.com/datalad/datalad/pull/6428>`__ (by @adswa)
-  AnnexRepo’s internal ``annexstatus`` is deprecated. In its place, a
   new test helper assists the few tests that rely on it
   `#6413 <https://github.com/datalad/datalad/pull/6413>`__ (by @adswa)
-  ``config`` has been refactored from ``where[="dataset"]`` to
   ``scope[="branch"]``
   `#5969 <https://github.com/datalad/datalad/pull/5969>`__ (by
   @yarikoptic)
-  Common command arguments are now uniformly and exhaustively passed to
   result renderers and filters for decision making. Previously, the
   presence of a particular argument depended on the respective API and
   circumstances of a command call.
   `#6440 <https://github.com/datalad/datalad/pull/6440>`__ (by @mih)
-  Entrypoint processing for extensions and metadata extractors has been
   consolidated on a uniform helper that is about twice as fast as the
   previous implementations.
   `#6591 <https://github.com/datalad/datalad/pull/6591>`__ (by @mih)

.. _tests-22:

Tests
-----

-  A range of Windows tests pass and were enabled
   `#6136 <https://github.com/datalad/datalad/pull/6136>`__ (by @adswa)
-  Invalid escape sequences in some tests were fixed
   `#6147 <https://github.com/datalad/datalad/pull/6147>`__ (by @mih)
-  A cross-platform compatible HTTP-serving test environment is
   introduced `#6153 <https://github.com/datalad/datalad/pull/6153>`__
   (by @mih)
-  A new helper exposes ``serve_path_via_http`` to the command line to
   deploy an ad-hoc instance of the HTTP server used for internal
   testing, with SSL and auth, if desired.
   `#6169 <https://github.com/datalad/datalad/pull/6169>`__ (by @mih)
-  Windows tests were redistributed across worker runs to harmonize
   runtime `#6200 <https://github.com/datalad/datalad/pull/6200>`__ (by
   @adswa)
-  ``Batchedcommand`` gained a basic test
   `#6203 <https://github.com/datalad/datalad/pull/6203>`__ (by
   @christian-monch)
-  The use of ``with_testrepo`` is discontinued in all core tests
   `#6224 <https://github.com/datalad/datalad/pull/6224>`__ (by @mih)
-  The new ``git-annex.filter.annex.process`` configuration is enabled
   by default on Windows to speed up the test suite
   `#6245 <https://github.com/datalad/datalad/pull/6245>`__ (by @mih)
-  If the available Git version supports it, the test suite now uses
   ``GIT_CONFIG_GLOBAL`` to configure a fake home directory instead of
   overwriting ``HOME`` on OSX
   (`#6251 <https://github.com/datalad/datalad/pull/6251>`__ (by
   @bpoldrack)) and ``HOME`` and ``USERPROFILE`` on Windows
   `#6260 <https://github.com/datalad/datalad/pull/6260>`__ (by @adswa)
-  Windows test timeouts of runners were addressed
   `#6311 <https://github.com/datalad/datalad/pull/6311>`__ (by
   @christian-monch)
-  A handful of Windows tests were fixed
   (`#6352 <https://github.com/datalad/datalad/pull/6352>`__ (by
   @yarikoptic)) or disabled
   (`#6353 <https://github.com/datalad/datalad/pull/6353>`__ (by
   @yarikoptic))
-  ``download-url``\ ’s test under ``http_proxy`` are skipped when a
   session can’t be established
   `#6361 <https://github.com/datalad/datalad/pull/6361>`__ (by
   @yarikoptic)
-  A test for ``datalad clean`` was fixed to be invoked within a dataset
   `#6359 <https://github.com/datalad/datalad/pull/6359>`__ (by
   @yarikoptic)
-  The new datalad.cli.tests have an improved module coverage of 80%
   `#6378 <https://github.com/datalad/datalad/pull/6378>`__ (by @mih)
-  The ``test_source_candidate_subdataset`` has been marked as ``@slow``
   `#6429 <https://github.com/datalad/datalad/pull/6429>`__ (by
   @yarikoptic)
-  Dedicated ``CLI`` benchmarks exist now
   `#6381 <https://github.com/datalad/datalad/pull/6381>`__ (by @mih)
-  Enable code coverage report for subprocesses
   `#6546 <https://github.com/datalad/datalad/pull/6546>`__ (by @adswa)
-  Skip a test on annex>=10.20220127 due to a bug in annex. See
   https://git-annex.branchable.com/bugs/Change_to_annex.largefiles_leaves_repo_modified/

Infra
-----

-  A new issue template using GitHub forms prestructures bug reports
   `#6048 <https://github.com/datalad/datalad/pull/6048>`__ (by
   @Remi-Gau)
-  DataLad and its dependency stack were packaged for Gentoo Linux
   `#6088 <https://github.com/datalad/datalad/pull/6088>`__ (by
   @TheChymera)
-  The readthedocs configuration is modernized to version 2
   `#6207 <https://github.com/datalad/datalad/pull/6207>`__ (by @adswa)
-  The Windows CI setup now runs on Appveyor’s Visual Studio 2022
   configuration
   `#6228 <https://github.com/datalad/datalad/pull/6228>`__ (by @adswa)
-  The ``readthedocs-theme`` and ``Sphinx`` versions were pinned to
   re-enable rendering of bullet points in the documentation
   `#6346 <https://github.com/datalad/datalad/pull/6346>`__ (by @adswa)
-  The PR template was updated with a CHANGELOG template. Future PRs
   should use it to include a summary for the CHANGELOG
   `#6396 <https://github.com/datalad/datalad/pull/6396>`__ (by @mih)

Authors: 11
-----------

-  Michael Hanke (@mih)
-  Yaroslav Halchenko (@yarikoptic)
-  Adina Wagner (@adswa)
-  Remi Gau (@Remi-Gau)
-  Horea Christian (@TheChymera)
-  Micha Szczepanik (@mslw)
-  Christian Mnch (@christian-monch)
-  John T. Wodder (@jwodder)
-  Benjamin Poldrack (@bpoldrack)
-  Sin Kim (@AKSoo)
-  Basile Pinsard (@bpinsard)

--------------

0.15.6 (Sun Feb 27 2022)
========================

.. _bug-fix-11:

Bug Fix
-------

-  BF: do not use BaseDownloader instance wide InterProcessLock -
   resolves stalling or errors during parallel installs
   `#6507 <https://github.com/datalad/datalad/pull/6507>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  release workflow: add -vv to auto invocation
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Fix version incorrectly incremented by release process in CHANGELOGs
   `#6459 <https://github.com/datalad/datalad/pull/6459>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(TST): add another condition to skip under http_proxy set
   `#6459 <https://github.com/datalad/datalad/pull/6459>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _authors-1-1:

Authors: 1
----------

-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.15.5 (Wed Feb 09 2022)
========================

Enhancement
-----------

-  BF: When download-url gets Pathobject as path convert it to a string
   `#6364 <https://github.com/datalad/datalad/pull/6364>`__
   (`@adswa <https://github.com/adswa>`__)

.. _bug-fix-12:

Bug Fix
-------

-  Fix AnnexRepo.whereis key=True mode operation, and add batch mode
   support `#6379 <https://github.com/datalad/datalad/pull/6379>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  DOC: run - adjust description for -i/-o to mention that it could be a
   directory `#6416 <https://github.com/datalad/datalad/pull/6416>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: ORA over HTTP tried to check archive
   `#6355 <https://github.com/datalad/datalad/pull/6355>`__
   (`@bpoldrack <https://github.com/bpoldrack>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: condition access to isatty to have stream eval to True
   `#6360 <https://github.com/datalad/datalad/pull/6360>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: python 3.10 compatibility fixes
   `#6363 <https://github.com/datalad/datalad/pull/6363>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Remove two(!) copies of a test
   `#6374 <https://github.com/datalad/datalad/pull/6374>`__
   (`@mih <https://github.com/mih>`__)
-  Warn just once about incomplete git config
   `#6343 <https://github.com/datalad/datalad/pull/6343>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Make version detection robust to GIT_DIR specification
   `#6341 <https://github.com/datalad/datalad/pull/6341>`__
   (`@effigies <https://github.com/effigies>`__
   `@mih <https://github.com/mih>`__)
-  BF(Q&D): do not crash - issue warning - if template fails to format
   `#6319 <https://github.com/datalad/datalad/pull/6319>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _authors-5-3:

Authors: 5
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  Benjamin Poldrack (`@bpoldrack <https://github.com/bpoldrack>`__)
-  Chris Markiewicz (`@effigies <https://github.com/effigies>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.15.4 (Thu Dec 16 2021)
========================

.. _bug-fix-13:

Bug Fix
-------

-  BF: autorc - replace incorrect releaseTypes with “none”
   `#6320 <https://github.com/datalad/datalad/pull/6320>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Minor enhancement to CONTRIBUTING.md
   `#6309 <https://github.com/datalad/datalad/pull/6309>`__
   (`@bpoldrack <https://github.com/bpoldrack>`__)
-  UX: If a clean repo is dirty after a failed run, give clean-up hints
   `#6112 <https://github.com/datalad/datalad/pull/6112>`__
   (`@adswa <https://github.com/adswa>`__)
-  Stop using distutils
   `#6113 <https://github.com/datalad/datalad/pull/6113>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  BF: RIARemote - set UI backend to annex to make it interactive
   `#6287 <https://github.com/datalad/datalad/pull/6287>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__
   `@bpoldrack <https://github.com/bpoldrack>`__)
-  Fix invalid escape sequences
   `#6293 <https://github.com/datalad/datalad/pull/6293>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  CI: Update environment for windows CI builds
   `#6292 <https://github.com/datalad/datalad/pull/6292>`__
   (`@bpoldrack <https://github.com/bpoldrack>`__)
-  bump the python version used for mac os tests
   `#6288 <https://github.com/datalad/datalad/pull/6288>`__
   (`@christian-monch <https://github.com/christian-monch>`__
   `@bpoldrack <https://github.com/bpoldrack>`__)
-  ENH(UX): log a hint to use ulimit command in case of “Too long”
   exception `#6173 <https://github.com/datalad/datalad/pull/6173>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Report correct HTTP URL for RIA store content
   `#6091 <https://github.com/datalad/datalad/pull/6091>`__
   (`@mih <https://github.com/mih>`__)
-  BF: Don’t overwrite subdataset source candidates
   `#6168 <https://github.com/datalad/datalad/pull/6168>`__
   (`@bpoldrack <https://github.com/bpoldrack>`__)
-  Bump sphinx requirement to bypass readthedocs defaults
   `#6189 <https://github.com/datalad/datalad/pull/6189>`__
   (`@mih <https://github.com/mih>`__)
-  infra: Provide custom prefix to auto-related labels
   `#6151 <https://github.com/datalad/datalad/pull/6151>`__
   (`@adswa <https://github.com/adswa>`__)
-  Remove all usage of exc_str()
   `#6142 <https://github.com/datalad/datalad/pull/6142>`__
   (`@mih <https://github.com/mih>`__)
-  BF: obtain information about annex special remotes also from annex
   journal `#6135 <https://github.com/datalad/datalad/pull/6135>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__
   `@mih <https://github.com/mih>`__)
-  BF: clone tried to save new subdataset despite failing to clone
   `#6140 <https://github.com/datalad/datalad/pull/6140>`__
   (`@bpoldrack <https://github.com/bpoldrack>`__)

.. _tests-23:

Tests
-----

-  RF+BF: use skip_if_no_module helper instead of try/except for libxmp
   and boto `#6148 <https://github.com/datalad/datalad/pull/6148>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  git://github.com -> https://github.com
   `#6134 <https://github.com/datalad/datalad/pull/6134>`__
   (`@mih <https://github.com/mih>`__)

Authors: 6
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  Benjamin Poldrack (`@bpoldrack <https://github.com/bpoldrack>`__)
-  Christian Mnch
   (`@christian-monch <https://github.com/christian-monch>`__)
-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.15.3 (Sat Oct 30 2021)
========================

.. _bug-fix-14:

Bug Fix
-------

-  BF: Don’t make create-sibling recursive by default
   `#6116 <https://github.com/datalad/datalad/pull/6116>`__
   (`@adswa <https://github.com/adswa>`__)
-  BF: Add dashes to ‘force’ option in non-empty directory error message
   `#6078 <https://github.com/datalad/datalad/pull/6078>`__
   (`@DisasterMo <https://github.com/DisasterMo>`__)
-  DOC: Add supported URL types to download-url’s docstring
   `#6098 <https://github.com/datalad/datalad/pull/6098>`__
   (`@adswa <https://github.com/adswa>`__)
-  BF: Retain git-annex error messages & don’t show them if operation
   successful `#6070 <https://github.com/datalad/datalad/pull/6070>`__
   (`@DisasterMo <https://github.com/DisasterMo>`__)
-  Remove uses of ``__full_version__`` and ``datalad.version``
   `#6073 <https://github.com/datalad/datalad/pull/6073>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  BF: ORA shouldn’t crash while handling a failure
   `#6063 <https://github.com/datalad/datalad/pull/6063>`__
   (`@bpoldrack <https://github.com/bpoldrack>`__)
-  DOC: Refine –reckless docstring on usage and wording
   `#6043 <https://github.com/datalad/datalad/pull/6043>`__
   (`@adswa <https://github.com/adswa>`__)
-  BF: archives upon strip - use rmtree which retries etc instead of
   rmdir `#6064 <https://github.com/datalad/datalad/pull/6064>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: do not leave test in a tmp dir destined for removal
   `#6059 <https://github.com/datalad/datalad/pull/6059>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Next wave of exc_str() removals
   `#6022 <https://github.com/datalad/datalad/pull/6022>`__
   (`@mih <https://github.com/mih>`__)

.. _pushed-to-maint-3:

Pushed to ``maint``
-------------------

-  CI: Enable new codecov uploader in Appveyor CI
   (`@adswa <https://github.com/adswa>`__)

.. _internal-19:

Internal
--------

-  UX: Log clone-candidate number and URLs
   `#6092 <https://github.com/datalad/datalad/pull/6092>`__
   (`@adswa <https://github.com/adswa>`__)
-  UX/ENH: Disable reporting, and don’t do superfluous internal
   subdatasets calls
   `#6094 <https://github.com/datalad/datalad/pull/6094>`__
   (`@adswa <https://github.com/adswa>`__)
-  Update codecov action to v2
   `#6072 <https://github.com/datalad/datalad/pull/6072>`__
   (`@jwodder <https://github.com/jwodder>`__)

.. _documentation-13:

Documentation
-------------

-  Design document on URL substitution feature
   `#6065 <https://github.com/datalad/datalad/pull/6065>`__
   (`@mih <https://github.com/mih>`__)

.. _tests-24:

Tests
-----

-  BF(TST): remove reuse of the same tape across unrelated tests
   `#6127 <https://github.com/datalad/datalad/pull/6127>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Fail Travis tests on deprecation warnings
   `#6074 <https://github.com/datalad/datalad/pull/6074>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  Ux get result handling broken
   `#6052 <https://github.com/datalad/datalad/pull/6052>`__
   (`@christian-monch <https://github.com/christian-monch>`__)
-  enable metalad tests again
   `#6060 <https://github.com/datalad/datalad/pull/6060>`__
   (`@christian-monch <https://github.com/christian-monch>`__)

.. _authors-7-1:

Authors: 7
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  Benjamin Poldrack (`@bpoldrack <https://github.com/bpoldrack>`__)
-  Christian Mnch
   (`@christian-monch <https://github.com/christian-monch>`__)
-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Michael Burgardt (`@DisasterMo <https://github.com/DisasterMo>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.15.2 (Wed Oct 06 2021)
========================

.. _bug-fix-15:

Bug Fix
-------

-  BF: Don’t suppress datalad subdatasets output
   `#6035 <https://github.com/datalad/datalad/pull/6035>`__
   (`@DisasterMo <https://github.com/DisasterMo>`__
   `@mih <https://github.com/mih>`__)
-  Honor datalad.runtime.use-patool if set regardless of OS (was Windows
   only) `#6033 <https://github.com/datalad/datalad/pull/6033>`__
   (`@mih <https://github.com/mih>`__)
-  Discontinue usage of deprecated (public) helper
   `#6032 <https://github.com/datalad/datalad/pull/6032>`__
   (`@mih <https://github.com/mih>`__)
-  BF: ProgressHandler - close the other handler if was specified
   `#6020 <https://github.com/datalad/datalad/pull/6020>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  UX: Report GitLab weburl of freshly created projects in the result
   `#6017 <https://github.com/datalad/datalad/pull/6017>`__
   (`@adswa <https://github.com/adswa>`__)
-  Ensure there’s a blank line between the class ``__doc__`` and
   “Parameters” in ``build_doc`` docstrings
   `#6004 <https://github.com/datalad/datalad/pull/6004>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  Large code-reorganization of everything runner-related
   `#6008 <https://github.com/datalad/datalad/pull/6008>`__
   (`@mih <https://github.com/mih>`__)
-  Discontinue exc_str() in all modern parts of the code base
   `#6007 <https://github.com/datalad/datalad/pull/6007>`__
   (`@mih <https://github.com/mih>`__)

.. _tests-25:

Tests
-----

-  TST: Add test to ensure functionality with subdatasets starting with
   a hyphen (-) `#6042 <https://github.com/datalad/datalad/pull/6042>`__
   (`@DisasterMo <https://github.com/DisasterMo>`__)
-  BF(TST): filter away warning from coverage from analysis of stderr of
   –help `#6028 <https://github.com/datalad/datalad/pull/6028>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: disable outdated SSL root certificate breaking chain on
   older/buggy clients
   `#6027 <https://github.com/datalad/datalad/pull/6027>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: start global test_http_server only if not running already
   `#6023 <https://github.com/datalad/datalad/pull/6023>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _authors-5-4:

Authors: 5
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Michael Burgardt (`@DisasterMo <https://github.com/DisasterMo>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.15.1 (Fri Sep 24 2021)
========================

.. _bug-fix-16:

Bug Fix
-------

-  BF: downloader - fail to download even on non-crippled FS if symlink
   exists `#5991 <https://github.com/datalad/datalad/pull/5991>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH: import datalad.api to bind extensions methods for discovery of
   dataset methods
   `#5999 <https://github.com/datalad/datalad/pull/5999>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Restructure cmdline API presentation
   `#5988 <https://github.com/datalad/datalad/pull/5988>`__
   (`@mih <https://github.com/mih>`__)
-  Close file descriptors after process exit
   `#5983 <https://github.com/datalad/datalad/pull/5983>`__
   (`@mih <https://github.com/mih>`__)

.. _pushed-to-maint-4:

Pushed to ``maint``
-------------------

-  Discontinue testing of hirni extension
   (`@mih <https://github.com/mih>`__)

.. _internal-20:

Internal
--------

-  Add debugging information to release step
   `#5980 <https://github.com/datalad/datalad/pull/5980>`__
   (`@jwodder <https://github.com/jwodder>`__)

.. _documentation-14:

Documentation
-------------

-  Coarse description of the credential subsystem’s functionality
   `#5998 <https://github.com/datalad/datalad/pull/5998>`__
   (`@mih <https://github.com/mih>`__)

.. _tests-26:

Tests
-----

-  BF(TST): use sys.executable, mark test_ria_basics.test_url_keys as
   requiring network
   `#5986 <https://github.com/datalad/datalad/pull/5986>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _authors-3-5:

Authors: 3
----------

-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.15.0 (Tue Sep 14 2021) – We miss you Kyle!
============================================

.. _enhancements-and-new-features-7:

Enhancements and new features
-----------------------------

-  Command execution is now performed by a new ``Runner`` implementation
   that is no longer based on the ``asyncio`` framework, which was found
   to exhibit fragile performance in interaction with other
   ``asyncio``-using code, such as Jupyter notebooks. The new
   implementation is based on threads. It also supports the
   specification of “protocols” that were introduced with the switch to
   the ``asyncio`` implementation in 0.14.0.
   (`#5667 <https://github.com/datalad/datalad/issues/5667>`__)

-  ``clone`` now supports arbitrary URL transformations based on regular
   expressions. One or more transformation steps can be defined via
   ``datalad.clone.url-substitute.<label>`` configuration settings. The
   feature can be (and is now) used to support convenience mappings,
   such as ``https://osf.io/q8xnk/`` (displayed in a browser window) to
   ``osf://q8xnk`` (clonable via the ``datalad-osf`` extension.
   (`#5749 <https://github.com/datalad/datalad/issues/5749>`__)

-  Homogenize SSH use and configurability between DataLad and git-annex,
   by instructing git-annex to use DataLad’s ``sshrun`` for SSH calls
   (instead of SSH directly).
   (`#5389 <https://github.com/datalad/datalad/issues/5389>`__)

-  The ORA special remote has received several new features:

   -  It now support a ``push-url`` setting as an alternative to ``url``
      for write access. An analog parameter was also added to
      ``create-sibling-ria``.
      (`#5420 <https://github.com/datalad/datalad/issues/5420>`__,
      `#5428 <https://github.com/datalad/datalad/issues/5428>`__)

   -  Access of RIA stores now performs homogeneous availability checks,
      regardless of access protocol. Before, broken HTTP-based access
      due to misspecified URLs could have gone unnoticed.
      (`#5459 <https://github.com/datalad/datalad/issues/5459>`__,
      `#5672 <https://github.com/datalad/datalad/issues/5672>`__)

   -  Error reporting was introduce to inform about undesirable
      conditions in remote RIA stores.
      (`#5683 <https://github.com/datalad/datalad/issues/5683>`__)

-  ``create-sibling-ria`` now supports ``--alias`` for the specification
   of a convenience dataset alias name in a RIA store.
   (`#5592 <https://github.com/datalad/datalad/issues/5592>`__)

-  Analog to ``git commit``, ``save`` now features an ``--amend`` mode
   to support incremental updates of a dataset state.
   (`#5430 <https://github.com/datalad/datalad/issues/5430>`__)

-  ``run`` now supports a dry-run mode that can be used to inspect the
   result of parameter expansion on the effective command to ease the
   composition of more complicated command lines.
   (`#5539 <https://github.com/datalad/datalad/issues/5539>`__)

-  ``run`` now supports a ``--assume-ready`` switch to avoid the
   (possibly expensive) preparation of inputs and outputs with large
   datasets that have already been readied through other means.
   (`#5431 <https://github.com/datalad/datalad/issues/5431>`__)

-  ``update`` now features ``--how`` and ``--how-subds`` parameters to
   configure how an update shall be performed. Supported modes are
   ``fetch`` (unchanged default), and ``merge`` (previously also
   possible via ``--merge``), but also new strategies like ``reset`` or
   ``checkout``.
   (`#5534 <https://github.com/datalad/datalad/issues/5534>`__)

-  ``update`` has a new ``--follow=parentds-lazy`` mode that only
   performs a fetch operation in subdatasets when the desired commit is
   not yet present. During recursive updates involving many subdatasets
   this can substantially speed up performance.
   (`#5474 <https://github.com/datalad/datalad/issues/5474>`__)

-  DataLad’s command line API can now report the version for individual
   commands via ``datalad <cmd> --version``. The output has been
   homogenized to ``<providing package> <version>``.
   (`#5543 <https://github.com/datalad/datalad/issues/5543>`__)

-  ``create-sibling`` now logs information on an auto-generated sibling
   name, in the case that no ``--name/-s`` was provided.
   (`#5550 <https://github.com/datalad/datalad/issues/5550>`__)

-  ``create-sibling-github`` has been updated to emit result records
   like any standard DataLad command. Previously it was implemented as a
   “plugin”, which did not support all standard API parameters.
   (`#5551 <https://github.com/datalad/datalad/issues/5551>`__)

-  ``copy-file`` now also works with content-less files in datasets on
   crippled filesystems (adjusted mode), when a recent enough git-annex
   (8.20210428 or later) is available.
   (`#5630 <https://github.com/datalad/datalad/issues/5630>`__)

-  ``addurls`` can now be instructed how to behave in the event of file
   name collision via a new parameter ``--on-collision``.
   (`#5675 <https://github.com/datalad/datalad/issues/5675>`__)

-  ``addurls`` reporting now informs which particular subdatasets were
   created. (`#5689 <https://github.com/datalad/datalad/issues/5689>`__)

-  Credentials can now be provided or overwritten via all means
   supported by ``ConfigManager``. Importantly,
   ``datalad.credential.<name>.<field>`` configuration settings and
   analog specification via environment variables are now supported
   (rather than custom environment variables only). Previous
   specification methods are still supported too.
   (`#5680 <https://github.com/datalad/datalad/issues/5680>`__)

-  A new ``datalad.credentials.force-ask`` configuration flag can now be
   used to force re-entry of already known credentials. This simplifies
   credential updates without having to use an approach native to
   individual credential stores.
   (`#5777 <https://github.com/datalad/datalad/issues/5777>`__)

-  Suppression of rendering repeated similar results is now configurable
   via the configuration switches
   ``datalad.ui.suppress-similar-results`` (bool), and
   ``datalad.ui.suppress-similar-results-threshold`` (int).
   (`#5681 <https://github.com/datalad/datalad/issues/5681>`__)

-  The performance of ``status`` and similar functionality when
   determining local file availability has been improved.
   (`#5692 <https://github.com/datalad/datalad/issues/5692>`__)

-  ``push`` now renders a result summary on completion.
   (`#5696 <https://github.com/datalad/datalad/issues/5696>`__)

-  A dedicated info log message indicates when dataset repositories are
   subjected to an annex version upgrade.
   (`#5698 <https://github.com/datalad/datalad/issues/5698>`__)

-  Error reporting improvements:

   -  The ``NoDatasetFound`` exception now provides information for
      which purpose a dataset is required.
      (`#5708 <https://github.com/datalad/datalad/issues/5708>`__)

   -  Wording of the ``MissingExternalDependeny`` error was rephrased to
      account for cases of non-functional installations.
      (`#5803 <https://github.com/datalad/datalad/issues/5803>`__)

   -  ``push`` reports when a ``--to`` parameter specification was
      (likely) forgotten.
      (`#5726 <https://github.com/datalad/datalad/issues/5726>`__)

   -  Detailed information is now given when DataLad fails to obtain a
      lock for credential entry in a timely fashion. Previously only a
      generic debug log message was emitted.
      (`#5884 <https://github.com/datalad/datalad/issues/5884>`__)

   -  Clarified error message when ``create-sibling-gitlab`` was called
      without ``--project``.
      (`#5907 <https://github.com/datalad/datalad/issues/5907>`__)

-  ``add-readme`` now provides a README template with more information
   on the nature and use of DataLad datasets. A README file is no longer
   annex’ed by default, but can be using the new ``--annex`` switch.
   ([#5723][], [#5725][])

-  ``clean`` now supports a ``--dry-run`` mode to inform about cleanable
   content. (`#5738 <https://github.com/datalad/datalad/issues/5738>`__)

-  A new configuration setting ``datalad.locations.locks`` can be used
   to control the placement of lock files.
   (`#5740 <https://github.com/datalad/datalad/issues/5740>`__)

-  ``wtf`` now also reports branch names and states.
   (`#5804 <https://github.com/datalad/datalad/issues/5804>`__)

-  ``AnnexRepo.whereis()`` now supports batch mode.
   (`#5533 <https://github.com/datalad/datalad/issues/5533>`__)

.. _deprecations-and-removals-2:

Deprecations and removals
~~~~~~~~~~~~~~~~~~~~~~~~~

-  The minimum supported git-annex version is now 8.20200309.
   (`#5512 <https://github.com/datalad/datalad/issues/5512>`__)

-  ORA special remote configuration items ``ssh-host``, and
   ``base-path`` are deprecated. They are completely replaced by
   ``ria+<protocol>://`` URL specifications.
   (`#5425 <https://github.com/datalad/datalad/issues/5425>`__)

-  The deprecated ``no_annex`` parameter of ``create()`` was removed
   from the Python API.
   (`#5441 <https://github.com/datalad/datalad/issues/5441>`__)

-  The unused ``GitRepo.pull()`` method has been removed.
   (`#5558 <https://github.com/datalad/datalad/issues/5558>`__)

-  Residual support for “plugins” (a mechanism used before DataLad
   supported extensions) was removed. This includes the configuration
   switches ``datalad.locations.{system,user}-plugins``.
   (`#5554 <https://github.com/datalad/datalad/issues/5554>`__,
   `#5564 <https://github.com/datalad/datalad/issues/5564>`__)

-  Several features and comments have been moved to the
   ``datalad-deprecated`` package. This package must now be installed to
   be able to use keep using this functionality.

   -  The ``publish`` command. Use ``push`` instead.
      (`#5837 <https://github.com/datalad/datalad/issues/5837>`__)

   -  The ``ls`` command.
      (`#5569 <https://github.com/datalad/datalad/issues/5569>`__)

   -  The web UI that is deployable via ``datalad create-sibling --ui``.
      (`#5555 <https://github.com/datalad/datalad/issues/5555>`__)

   -  The “automagic IO” feature.
      (`#5577 <https://github.com/datalad/datalad/issues/5577>`__)

-  ``AnnexRepo.copy_to()`` has been deprecated. The ``push`` command
   should be used instead.
   (`#5560 <https://github.com/datalad/datalad/issues/5560>`__)

-  ``AnnexRepo.sync()`` has been deprecated.
   ``AnnexRepo.call_annex(['sync', ...])`` should be used instead.
   (`#5461 <https://github.com/datalad/datalad/issues/5461>`__)

-  All ``GitRepo.*_submodule()`` methods have been deprecated and will
   be removed in a future release.
   (`#5559 <https://github.com/datalad/datalad/issues/5559>`__)

-  ``create-sibling-github``\ ’s ``--dryrun`` switch was deprecated, use
   ``--dry-run`` instead.
   (`#5551 <https://github.com/datalad/datalad/issues/5551>`__)

-  The ``datalad --pbs-runner`` option has been deprecated, use
   ``condor_run`` (or similar) instead.
   (`#5956 <https://github.com/datalad/datalad/issues/5956>`__)

Fixes
-----

-  Prevent invalid declaration of a publication dependencies for
   ‘origin’ on any auto-detected ORA special remotes, when cloing from a
   RIA store. An ORA remote is now checked whether it actually points to
   the RIA store the clone was made from.
   (`#5415 <https://github.com/datalad/datalad/issues/5415>`__)

-  The ORA special remote implementation has received several fixes:

   -  It can now handle HTTP redirects.
      (`#5792 <https://github.com/datalad/datalad/issues/5792>`__)

   -  Prevents failure when URL-type annex keys contain the ‘/’
      character.
      (`#5823 <https://github.com/datalad/datalad/issues/5823>`__)

   -  Properly support the specification of usernames, passwords and
      ports in ``ria+<protocol>://`` URLs.
      (`#5902 <https://github.com/datalad/datalad/issues/5902>`__)

-  It is now possible to specifically select the default (or generic)
   result renderer via ``datalad -f default`` and with that override a
   ``tailored`` result renderer that may be preconfigured for a
   particular command.
   (`#5476 <https://github.com/datalad/datalad/issues/5476>`__)

-  Starting with 0.14.0, original URLs given to ``clone`` were recorded
   in a subdataset record. This was initially done in a second commit,
   leading to inflation of commits and slowdown in superdatasets with
   many subdatasets. Such subdataset record annotation is now collapsed
   into a single commits.
   (`#5480 <https://github.com/datalad/datalad/issues/5480>`__)

-  ``run`` now longer removes leading empty directories as part of the
   output preparation. This was surprising behavior for commands that do
   not ensure on their own that output directories exist.
   (`#5492 <https://github.com/datalad/datalad/issues/5492>`__)

-  A potentially existing ``message`` property is no longer removed when
   using the ``json`` or ``json_pp`` result renderer to avoid undesired
   withholding of relevant information.
   (`#5536 <https://github.com/datalad/datalad/issues/5536>`__)

-  ``subdatasets`` now reports ``state=present``, rather than
   ``state=clean``, for installed subdatasets to complement
   ``state=absent`` reports for uninstalled dataset.
   (`#5655 <https://github.com/datalad/datalad/issues/5655>`__)

-  ``create-sibling-ria`` now executes commands with a consistent
   environment setup that matches all other command execution in other
   DataLad commands.
   (`#5682 <https://github.com/datalad/datalad/issues/5682>`__)

-  ``save`` no longer saves unspecified subdatasets when called with an
   explicit path (list). The fix required a behavior change of
   ``GitRepo.get_content_info()`` in its interpretation of ``None``
   vs. ``[]`` path argument values that now aligns the behavior of
   ``GitRepo.diff|status()`` with their respective documentation.
   (`#5693 <https://github.com/datalad/datalad/issues/5693>`__)

-  ``get`` now prefers the location of a subdatasets that is recorded in
   a superdataset’s ``.gitmodules`` record. Previously, DataLad tried to
   obtain a subdataset from an assumed checkout of the superdataset’s
   origin. This new default order is (re-)configurable via the
   ``datalad.get.subdataset-source-candidate-<priority-label>``
   configuration mechanism.
   (`#5760 <https://github.com/datalad/datalad/issues/5760>`__)

-  ``create-sibling-gitlab`` no longer skips the root dataset when ``.``
   is given as a path.
   (`#5789 <https://github.com/datalad/datalad/issues/5789>`__)

-  ``siblings`` now rejects a value given to ``--as-common-datasrc``
   that clashes with the respective Git remote.
   (`#5805 <https://github.com/datalad/datalad/issues/5805>`__)

-  The usage synopsis reported by ``siblings`` now lists all supported
   actions. (`#5913 <https://github.com/datalad/datalad/issues/5913>`__)

-  ``siblings`` now renders non-ok results to avoid silent failure.
   (`#5915 <https://github.com/datalad/datalad/issues/5915>`__)

-  ``.gitattribute`` file manipulations no longer leave the file without
   a trailing newline.
   (`#5847 <https://github.com/datalad/datalad/issues/5847>`__)

-  Prevent crash when trying to delete a non-existing keyring credential
   field. (`#5892 <https://github.com/datalad/datalad/issues/5892>`__)

-  git-annex is no longer called with an unconditional ``annex.retry=3``
   configuration. Instead, this parameterization is now limited to
   ``annex get`` and ``annex copy`` calls.
   (`#5904 <https://github.com/datalad/datalad/issues/5904>`__)

.. _tests-27:

Tests
-----

-  ``file://`` URLs are no longer the predominant test case for
   ``AnnexRepo`` functionality. A built-in HTTP server now used in most
   cases. (`#5332 <https://github.com/datalad/datalad/issues/5332>`__)

--------------

0.14.8 (Sun Sep 12 2021)
========================

.. _bug-fix-17:

Bug Fix
-------

-  BF: add-archive-content on .xz and other non-.gz stream compressed
   files `#5930 <https://github.com/datalad/datalad/pull/5930>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(UX): do not keep logging ERROR possibly present in progress
   records `#5936 <https://github.com/datalad/datalad/pull/5936>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Annotate datalad_core as not needing actual data – just uses annex
   whereis `#5971 <https://github.com/datalad/datalad/pull/5971>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: limit CMD_MAX_ARG if obnoxious value is encountered.
   `#5945 <https://github.com/datalad/datalad/pull/5945>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Download session/credentials locking – inform user if locking is
   “failing” to be obtained, fail upon ~5min timeout
   `#5884 <https://github.com/datalad/datalad/pull/5884>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Render siblings()’s non-ok results with the default renderer
   `#5915 <https://github.com/datalad/datalad/pull/5915>`__
   (`@mih <https://github.com/mih>`__)
-  BF: do not crash, just skip whenever trying to delete non existing
   field in the underlying keyring
   `#5892 <https://github.com/datalad/datalad/pull/5892>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Fix argument-spec for ``siblings`` and improve usage synopsis
   `#5913 <https://github.com/datalad/datalad/pull/5913>`__
   (`@mih <https://github.com/mih>`__)
-  Clarify error message re unspecified gitlab project
   `#5907 <https://github.com/datalad/datalad/pull/5907>`__
   (`@mih <https://github.com/mih>`__)
-  Support username, password and port specification in RIA URLs
   `#5902 <https://github.com/datalad/datalad/pull/5902>`__
   (`@mih <https://github.com/mih>`__)
-  BF: take path from SSHRI, test URLs not only on Windows
   `#5881 <https://github.com/datalad/datalad/pull/5881>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH(UX): warn user if keyring returned a “null” keyring
   `#5875 <https://github.com/datalad/datalad/pull/5875>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH(UX): state original purpose in NoDatasetFound exception + detail
   it for get `#5708 <https://github.com/datalad/datalad/pull/5708>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _pushed-to-maint-5:

Pushed to ``maint``
-------------------

-  Merge branch ‘bf-http-headers-agent’ into maint
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  RF(BF?)+DOC: provide User-Agent to entire session headers + use those
   if provided (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _internal-21:

Internal
--------

-  Pass ``--no-changelog`` to ``auto shipit`` if changelog already has
   entry `#5952 <https://github.com/datalad/datalad/pull/5952>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  Add isort config to match current convention + run isort via
   pre-commit (if configured)
   `#5923 <https://github.com/datalad/datalad/pull/5923>`__
   (`@jwodder <https://github.com/jwodder>`__)
-  .travis.yml: use python -m {nose,coverage} invocations, and always
   show combined report
   `#5888 <https://github.com/datalad/datalad/pull/5888>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Add project URLs into the package metadata for convenience links on
   Pypi `#5866 <https://github.com/datalad/datalad/pull/5866>`__
   (`@adswa <https://github.com/adswa>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-28:

Tests
-----

-  BF: do use OBSCURE_FILENAME instead of hardcoded unicode
   `#5944 <https://github.com/datalad/datalad/pull/5944>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(TST): Skip testing for having PID listed if no psutil
   `#5920 <https://github.com/datalad/datalad/pull/5920>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF(TST): Boost version of git-annex to 8.20201129 to test an error
   message `#5894 <https://github.com/datalad/datalad/pull/5894>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _authors-4-1:

Authors: 4
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.14.7 (Tue Aug 03 2021)
========================

.. _bug-fix-18:

Bug Fix
-------

-  UX: When two or more clone URL templates are found, error out more
   gracefully `#5839 <https://github.com/datalad/datalad/pull/5839>`__
   (`@adswa <https://github.com/adswa>`__)
-  BF: http_auth - follow redirect (just 1) to re-authenticate after
   initial attempt
   `#5852 <https://github.com/datalad/datalad/pull/5852>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  addurls Formatter - provide value repr in exception
   `#5850 <https://github.com/datalad/datalad/pull/5850>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH: allow for “patch” level semver for “master” branch
   `#5839 <https://github.com/datalad/datalad/pull/5839>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: Report info from annex JSON error message in CommandError
   `#5809 <https://github.com/datalad/datalad/pull/5809>`__
   (`@mih <https://github.com/mih>`__)
-  RF(TST): do not test for no EASY and pkg_resources in shims
   `#5817 <https://github.com/datalad/datalad/pull/5817>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  http downloaders: Provide custom informative User-Agent, do not claim
   to be “Authenticated access”
   `#5802 <https://github.com/datalad/datalad/pull/5802>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH(UX,DX): inform user with a warning if version is 0+unknown
   `#5787 <https://github.com/datalad/datalad/pull/5787>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  shell-completion: add argcomplete to ‘misc’ extra_depends, log an
   ERROR if argcomplete fails to import
   `#5781 <https://github.com/datalad/datalad/pull/5781>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH (UX): add python-gitlab dependency
   `#5776 <https://github.com/datalad/datalad/pull/5776>`__
   (s.heunis@fz-juelich.de)

.. _internal-22:

Internal
--------

-  BF: Fix reported paths in ORA remote
   `#5821 <https://github.com/datalad/datalad/pull/5821>`__
   (`@adswa <https://github.com/adswa>`__)
-  BF: import importlib.metadata not importlib_metadata whenever
   available `#5818 <https://github.com/datalad/datalad/pull/5818>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _tests-29:

Tests
-----

-  TST: set –allow-unrelated-histories in the mk_push_target setup for
   Windows `#5855 <https://github.com/datalad/datalad/pull/5855>`__
   (`@adswa <https://github.com/adswa>`__)
-  Tests: Allow for version to contain + as a separator and provide more
   information for version related comparisons
   `#5786 <https://github.com/datalad/datalad/pull/5786>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)

.. _authors-4-2:

Authors: 4
----------

-  Adina Wagner (`@adswa <https://github.com/adswa>`__)
-  Michael Hanke (`@mih <https://github.com/mih>`__)
-  Stephan Heunis (`@jsheunis <https://github.com/jsheunis>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.14.6 (Sun Jun 27 2021)
========================

.. _internal-23:

Internal
--------

-  BF: update changelog conversion from .md to .rst (for sphinx)
   `#5757 <https://github.com/datalad/datalad/pull/5757>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__
   `@jwodder <https://github.com/jwodder>`__)

.. _authors-2-1:

Authors: 2
----------

-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.14.5 (Mon Jun 21 2021)
========================

.. _bug-fix-19:

Bug Fix
-------

-  BF(TST): parallel - take longer for producer to produce
   `#5747 <https://github.com/datalad/datalad/pull/5747>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  add –on-failure default value and document it
   `#5690 <https://github.com/datalad/datalad/pull/5690>`__
   (`@christian-monch <https://github.com/christian-monch>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH: harmonize “purpose” statements to imperative form
   `#5733 <https://github.com/datalad/datalad/pull/5733>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  ENH(TST): populate heavy tree with 100 unique keys (not just 1) among
   10,000 `#5734 <https://github.com/datalad/datalad/pull/5734>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: do not use .acquired - just get state from acquire()
   `#5718 <https://github.com/datalad/datalad/pull/5718>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  BF: account for annex now “scanning for annexed” instead of
   “unlocked” files
   `#5705 <https://github.com/datalad/datalad/pull/5705>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  interface: Don’t repeat custom summary for non-generator results
   `#5688 <https://github.com/datalad/datalad/pull/5688>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  RF: just pip install datalad-installer
   `#5676 <https://github.com/datalad/datalad/pull/5676>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  DOC: addurls.extract: Drop mention of removed ‘stream’ parameter
   `#5690 <https://github.com/datalad/datalad/pull/5690>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  Merge pull request #5674 from kyleam/test-addurls-copy-fix
   `#5674 <https://github.com/datalad/datalad/pull/5674>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  Merge pull request #5663 from kyleam/status-ds-equal-path
   `#5663 <https://github.com/datalad/datalad/pull/5663>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  Merge pull request #5671 from kyleam/update-fetch-fail
   `#5671 <https://github.com/datalad/datalad/pull/5671>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  BF: update: Honor –on-failure if fetch fails
   `#5671 <https://github.com/datalad/datalad/pull/5671>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  RF: update: Avoid fetch’s deprecated kwargs
   `#5671 <https://github.com/datalad/datalad/pull/5671>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  CLN: update: Drop an unused import
   `#5671 <https://github.com/datalad/datalad/pull/5671>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  Merge pull request #5664 from kyleam/addurls-better-url-parts-error
   `#5664 <https://github.com/datalad/datalad/pull/5664>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  Merge pull request #5661 from kyleam/sphinx-fix-plugin-refs
   `#5661 <https://github.com/datalad/datalad/pull/5661>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  BF: status: Provide special treatment of “this dataset” path
   `#5663 <https://github.com/datalad/datalad/pull/5663>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  BF: addurls: Provide better placeholder error for special keys
   `#5664 <https://github.com/datalad/datalad/pull/5664>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  RF: addurls: Simply construction of placeholder exception message
   `#5664 <https://github.com/datalad/datalad/pull/5664>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  RF: addurls._get_placeholder_exception: Rename a parameter
   `#5664 <https://github.com/datalad/datalad/pull/5664>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  RF: status: Avoid repeated Dataset.path access
   `#5663 <https://github.com/datalad/datalad/pull/5663>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  DOC: Reference plugins via datalad.api
   `#5661 <https://github.com/datalad/datalad/pull/5661>`__
   (`@kyleam <https://github.com/kyleam>`__)
-  download-url: Set up datalad special remote if needed
   `#5648 <https://github.com/datalad/datalad/pull/5648>`__
   (`@kyleam <https://github.com/kyleam>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)

.. _pushed-to-maint-6:

Pushed to ``maint``
-------------------

-  MNT: Post-release dance (`@kyleam <https://github.com/kyleam>`__)

.. _internal-24:

Internal
--------

-  Switch to versioneer and auto
   `#5669 <https://github.com/datalad/datalad/pull/5669>`__
   (`@jwodder <https://github.com/jwodder>`__
   `@yarikoptic <https://github.com/yarikoptic>`__)
-  MNT: setup.py: Temporarily avoid Sphinx 4
   `#5649 <https://github.com/datalad/datalad/pull/5649>`__
   (`@kyleam <https://github.com/kyleam>`__)

.. _tests-30:

Tests
-----

-  BF(TST): skip testing for showing “Scanning for …” since not shown if
   too quick `#5727 <https://github.com/datalad/datalad/pull/5727>`__
   (`@yarikoptic <https://github.com/yarikoptic>`__)
-  Revert “TST: test_partial_unlocked: Document and avoid recent
   git-annex failure”
   `#5651 <https://github.com/datalad/datalad/pull/5651>`__
   (`@kyleam <https://github.com/kyleam>`__)

.. _authors-4-3:

Authors: 4
----------

-  Christian Mnch
   (`@christian-monch <https://github.com/christian-monch>`__)
-  John T. Wodder II (`@jwodder <https://github.com/jwodder>`__)
-  Kyle Meyer (`@kyleam <https://github.com/kyleam>`__)
-  Yaroslav Halchenko (`@yarikoptic <https://github.com/yarikoptic>`__)

--------------

0.14.4 (May 10, 2021) – .
=========================

.. _fixes-1:

Fixes
-----

-  Following an internal call to ``git-clone``,
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   assumed that the remote name was “origin”, but this may not be the
   case if ``clone.defaultRemoteName`` is configured (available as of
   Git 2.30).
   (`#5572 <https://github.com/datalad/datalad/issues/5572>`__)

-  Several test fixes, including updates for changes in git-annex.
   (`#5612 <https://github.com/datalad/datalad/issues/5612>`__)
   (`#5632 <https://github.com/datalad/datalad/issues/5632>`__)
   (`#5639 <https://github.com/datalad/datalad/issues/5639>`__)

0.14.3 (April 28, 2021) – .
===========================

.. _fixes-2:

Fixes
-----

-  For outputs that include a glob,
   `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   didn’t re-glob after executing the command, which is necessary to
   catch changes if ``--explicit`` or ``--expand={outputs,both}`` is
   specified.
   (`#5594 <https://github.com/datalad/datalad/issues/5594>`__)

-  `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   now gives an error result rather than a warning when an input glob
   doesn’t match.
   (`#5594 <https://github.com/datalad/datalad/issues/5594>`__)

-  The procedure for creating a RIA store checks for an existing
   ria-layout-version file and makes sure its version matches the
   desired version. This check wasn’t done correctly for SSH hosts.
   (`#5607 <https://github.com/datalad/datalad/issues/5607>`__)

-  A helper for transforming git-annex JSON records into DataLad results
   didn’t account for the unusual case where the git-annex record
   doesn’t have a “file” key.
   (`#5580 <https://github.com/datalad/datalad/issues/5580>`__)

-  The test suite required updates for recent changes in PyGithub and
   git-annex.
   (`#5603 <https://github.com/datalad/datalad/issues/5603>`__)
   (`#5609 <https://github.com/datalad/datalad/issues/5609>`__)

.. _enhancements-and-new-features-8:

Enhancements and new features
-----------------------------

-  The DataLad source repository has long had a tools/cmdline-completion
   helper. This functionality is now exposed as a command,
   ``datalad shell-completion``.
   (`#5544 <https://github.com/datalad/datalad/issues/5544>`__)

0.14.2 (April 14, 2021) – .
===========================

.. _fixes-3:

Fixes
-----

-  `push <http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html>`__
   now works bottom-up, pushing submodules first so that hooks on the
   remote can aggregate updated subdataset information.
   (`#5416 <https://github.com/datalad/datalad/issues/5416>`__)

-  `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__
   didn’t ensure that the configuration of subdatasets was reloaded.
   (`#5552 <https://github.com/datalad/datalad/issues/5552>`__)

0.14.1 (April 01, 2021) – .
===========================

.. _fixes-4:

Fixes
-----

-  The recent default branch changes on GitHub’s side can lead to
   “git-annex” being selected over “master” as the default branch on
   GitHub when setting up a sibling with
   `create-sibling-github <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-github.html>`__.
   To work around this, the current branch is now pushed first.
   (`#5010 <https://github.com/datalad/datalad/issues/5010>`__)

-  The logic for reading in a JSON line from git-annex failed if the
   response exceeded the buffer size (256 KB on \*nix systems).

-  Calling
   `unlock <http://datalad.readthedocs.io/en/latest/generated/man/datalad-unlock.html>`__
   with a path of “.” from within an untracked subdataset incorrectly
   aborted, complaining that the “dataset containing given paths is not
   underneath the reference dataset”.
   (`#5458 <https://github.com/datalad/datalad/issues/5458>`__)

-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   didn’t account for the possibility of multiple accessible ORA remotes
   or the fact that none of them may be associated with the RIA store
   being cloned.
   (`#5488 <https://github.com/datalad/datalad/issues/5488>`__)

-  `create-sibling-ria <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-ria.html>`__
   didn’t call ``git update-server-info`` after setting up the remote
   repository and, as a result, the repository couldn’t be fetched until
   something else (e.g., a push) triggered a call to
   ``git update-server-info``.
   (`#5531 <https://github.com/datalad/datalad/issues/5531>`__)

-  The parser for git-config output didn’t properly handle multi-line
   values and got thrown off by unexpected and unrelated lines.
   (`#5509 <https://github.com/datalad/datalad/issues/5509>`__)

-  The 0.14 release introduced regressions in the handling of progress
   bars for git-annex actions, including collapsing progress bars for
   concurrent operations.
   (`#5421 <https://github.com/datalad/datalad/issues/5421>`__)
   (`#5438 <https://github.com/datalad/datalad/issues/5438>`__)

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   failed if the user configured Git’s ``diff.ignoreSubmodules`` to a
   non-default value.
   (`#5453 <https://github.com/datalad/datalad/issues/5453>`__)

-  A interprocess lock is now used to prevent a race between checking
   for an SSH socket’s existence and creating it.
   (`#5466 <https://github.com/datalad/datalad/issues/5466>`__)

-  If a Python procedure script is executable,
   `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__
   invokes it directly rather than passing it to ``sys.executable``. The
   non-executable Python procedures that ship with DataLad now include
   shebangs so that invoking them has a chance of working on file
   systems that present all files as executable.
   (`#5436 <https://github.com/datalad/datalad/issues/5436>`__)

-  DataLad’s wrapper around ``argparse`` failed if an underscore was
   used in a positional argument.
   (`#5525 <https://github.com/datalad/datalad/issues/5525>`__)

.. _enhancements-and-new-features-9:

Enhancements and new features
-----------------------------

-  DataLad’s method for mapping environment variables to configuration
   options (e.g., ``DATALAD_FOO_X__Y`` to ``datalad.foo.x-y``) doesn’t
   work if the subsection name (“FOO”) has an underscore. This
   limitation can be sidestepped with the new
   ``DATALAD_CONFIG_OVERRIDES_JSON`` environment variable, which can be
   set to a JSON record of configuration values.
   (`#5505 <https://github.com/datalad/datalad/issues/5505>`__)

0.14.0 (February 02, 2021) – .
==============================

Major refactoring and deprecations
----------------------------------

-  Git versions below v2.19.1 are no longer supported.
   (`#4650 <https://github.com/datalad/datalad/issues/4650>`__)

-  The minimum git-annex version is still 7.20190503, but, if you’re on
   Windows (or use adjusted branches in general), please upgrade to at
   least 8.20200330 but ideally 8.20210127 to get subdataset-related
   fixes. (`#4292 <https://github.com/datalad/datalad/issues/4292>`__)
   (`#5290 <https://github.com/datalad/datalad/issues/5290>`__)

-  The minimum supported version of Python is now 3.6.
   (`#4879 <https://github.com/datalad/datalad/issues/4879>`__)

-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   is now deprecated in favor of
   `push <http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html>`__.
   It will be removed in the 0.15.0 release at the earliest.

-  A new command runner was added in v0.13. Functionality related to the
   old runner has now been removed: ``Runner``, ``GitRunner``, and
   ``run_gitcommand_on_file_list_chunks`` from the ``datalad.cmd``
   module along with the ``datalad.tests.protocolremote``,
   ``datalad.cmd.protocol``, and ``datalad.cmd.protocol.prefix``
   configuration options.
   (`#5229 <https://github.com/datalad/datalad/issues/5229>`__)

-  The ``--no-storage-sibling`` switch of ``create-sibling-ria`` is
   deprecated in favor of ``--storage-sibling=off`` and will be removed
   in a later release.
   (`#5090 <https://github.com/datalad/datalad/issues/5090>`__)

-  The ``get_git_dir`` static method of ``GitRepo`` is deprecated and
   will be removed in a later release. Use the ``dot_git`` attribute of
   an instance instead.
   (`#4597 <https://github.com/datalad/datalad/issues/4597>`__)

-  The ``ProcessAnnexProgressIndicators`` helper from
   ``datalad.support.annexrepo`` has been removed.
   (`#5259 <https://github.com/datalad/datalad/issues/5259>`__)

-  The ``save`` argument of
   `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__,
   a noop since v0.6.0, has been dropped.
   (`#5278 <https://github.com/datalad/datalad/issues/5278>`__)

-  The ``get_URLS`` method of ``AnnexCustomRemote`` is deprecated and
   will be removed in a later release.
   (`#4955 <https://github.com/datalad/datalad/issues/4955>`__)

-  ``ConfigManager.get`` now returns a single value rather than a tuple
   when there are multiple values for the same key, as very few callers
   correctly accounted for the possibility of a tuple return value.
   Callers can restore the old behavior by passing ``get_all=True``.
   (`#4924 <https://github.com/datalad/datalad/issues/4924>`__)

-  In 0.12.0, all of the ``assure_*`` functions in ``datalad.utils``
   were renamed as ``ensure_*``, keeping the old names around as
   compatibility aliases. The ``assure_*`` variants are now marked as
   deprecated and will be removed in a later release.
   (`#4908 <https://github.com/datalad/datalad/issues/4908>`__)

-  The ``datalad.interface.run`` module, which was deprecated in 0.12.0
   and kept as a compatibility shim for ``datalad.core.local.run``, has
   been removed.
   (`#4583 <https://github.com/datalad/datalad/issues/4583>`__)

-  The ``saver`` argument of ``datalad.core.local.run.run_command``,
   marked as obsolete in 0.12.0, has been removed.
   (`#4583 <https://github.com/datalad/datalad/issues/4583>`__)

-  The ``dataset_only`` argument of the ``ConfigManager`` class was
   deprecated in 0.12 and has now been removed.
   (`#4828 <https://github.com/datalad/datalad/issues/4828>`__)

-  The ``linux_distribution_name``, ``linux_distribution_release``, and
   ``on_debian_wheezy`` attributes in ``datalad.utils`` are no longer
   set at import time and will be removed in a later release. Use
   ``datalad.utils.get_linux_distribution`` instead.
   (`#4696 <https://github.com/datalad/datalad/issues/4696>`__)

-  ``datalad.distribution.clone``, which was marked as obsolete in v0.12
   in favor of ``datalad.core.distributed.clone``, has been removed.
   (`#4904 <https://github.com/datalad/datalad/issues/4904>`__)

-  ``datalad.support.annexrepo.N_AUTO_JOBS``, announced as deprecated in
   v0.12.6, has been removed.
   (`#4904 <https://github.com/datalad/datalad/issues/4904>`__)

-  The ``compat`` parameter of ``GitRepo.get_submodules``, added in
   v0.12 as a temporary compatibility layer, has been removed.
   (`#4904 <https://github.com/datalad/datalad/issues/4904>`__)

-  The long-deprecated (and non-functional) ``url`` parameter of
   ``GitRepo.__init__`` has been removed.
   (`#5342 <https://github.com/datalad/datalad/issues/5342>`__)

.. _fixes-5:

Fixes
-----

-  Cloning onto a system that enters adjusted branches by default (as
   Windows does) did not properly record the clone URL.
   (`#5128 <https://github.com/datalad/datalad/issues/5128>`__)

-  The RIA-specific handling after calling
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   was correctly triggered by ``ria+http`` URLs but not ``ria+https``
   URLs. (`#4977 <https://github.com/datalad/datalad/issues/4977>`__)

-  If the registered commit wasn’t found when cloning a subdataset, the
   failed attempt was left around.
   (`#5391 <https://github.com/datalad/datalad/issues/5391>`__)

-  The remote calls to ``cp`` and ``chmod`` in
   `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__
   were not portable and failed on macOS.
   (`#5108 <https://github.com/datalad/datalad/issues/5108>`__)

-  A more reliable check is now done to decide if configuration files
   need to be reloaded.
   (`#5276 <https://github.com/datalad/datalad/issues/5276>`__)

-  The internal command runner’s handling of the event loop has been
   improved to play nicer with outside applications and scripts that use
   asyncio. (`#5350 <https://github.com/datalad/datalad/issues/5350>`__)
   (`#5367 <https://github.com/datalad/datalad/issues/5367>`__)

.. _enhancements-and-new-features-10:

Enhancements and new features
-----------------------------

-  The subdataset handling for adjusted branches, which is particularly
   important on Windows where git-annex enters an adjusted branch by
   default, has been improved. A core piece of the new approach is
   registering the commit of the primary branch, not its checked out
   adjusted branch, in the superdataset. Note: This means that
   ``git   status`` will always consider a subdataset on an adjusted
   branch as dirty while ``datalad status`` will look more closely and
   see if the tip of the primary branch matches the registered commit.
   (`#5241 <https://github.com/datalad/datalad/issues/5241>`__)

-  The performance of the
   `subdatasets <http://datalad.readthedocs.io/en/latest/generated/man/datalad-subdatasets.html>`__
   command has been improved, with substantial speedups for recursive
   processing of many subdatasets.
   (`#4868 <https://github.com/datalad/datalad/issues/4868>`__)
   (`#5076 <https://github.com/datalad/datalad/issues/5076>`__)

-  Adding new subdatasets via
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   has been sped up.
   (`#4793 <https://github.com/datalad/datalad/issues/4793>`__)

-  `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__,
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__,
   and
   `addurls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-addurls.html>`__
   gained support for parallel operations that can be enabled via the
   ``--jobs`` command-line option or the new
   ``datalad.runtime.max-jobs`` configuration option.
   (`#5022 <https://github.com/datalad/datalad/issues/5022>`__)

-  `addurls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-addurls.html>`__

   -  learned how to read data from standard input.
      (`#4669 <https://github.com/datalad/datalad/issues/4669>`__)
   -  now supports tab-separated input.
      (`#4845 <https://github.com/datalad/datalad/issues/4845>`__)
   -  now lets Python callers pass in a list of records rather than a
      file name.
      (`#5285 <https://github.com/datalad/datalad/issues/5285>`__)
   -  gained a ``--drop-after`` switch that signals to drop a file’s
      content after downloading and adding it to the annex.
      (`#5081 <https://github.com/datalad/datalad/issues/5081>`__)
   -  is now able to construct a tree of files from known checksums
      without downloading content via its new ``--key`` option.
      (`#5184 <https://github.com/datalad/datalad/issues/5184>`__)
   -  records the URL file in the commit message as provided by the
      caller rather than using the resolved absolute path.
      (`#5091 <https://github.com/datalad/datalad/issues/5091>`__)
   -  is now speedier.
      (`#4867 <https://github.com/datalad/datalad/issues/4867>`__)
      (`#5022 <https://github.com/datalad/datalad/issues/5022>`__)

-  `create-sibling-github <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-github.html>`__
   learned how to create private repositories (thanks to Nolan Nichols).
   (`#4769 <https://github.com/datalad/datalad/issues/4769>`__)

-  `create-sibling-ria <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-ria.html>`__
   gained a ``--storage-sibling`` option. When
   ``--storage-sibling=only`` is specified, the storage sibling is
   created without an accompanying Git sibling. This enables using hosts
   without Git installed for storage.
   (`#5090 <https://github.com/datalad/datalad/issues/5090>`__)

-  The download machinery (and thus the ``datalad`` special remote)
   gained support for a new scheme, ``shub://``, which follows the same
   format used by ``singularity run`` and friends. In contrast to the
   short-lived URLs obtained by querying Singularity Hub directly,
   ``shub://`` URLs are suitable for registering with git-annex.
   (`#4816 <https://github.com/datalad/datalad/issues/4816>`__)

-  A provider is now included for https://registry-1.docker.io URLs.
   This is useful for storing an image’s blobs in a dataset and
   registering the URLs with git-annex.
   (`#5129 <https://github.com/datalad/datalad/issues/5129>`__)

-  The ``add-readme`` command now links to the `DataLad
   handbook <http://handbook.datalad.org>`__ rather than
   http://docs.datalad.org.
   (`#4991 <https://github.com/datalad/datalad/issues/4991>`__)

-  New option ``datalad.locations.extra-procedures`` specifies an
   additional location that should be searched for procedures.
   (`#5156 <https://github.com/datalad/datalad/issues/5156>`__)

-  The class for handling configuration values, ``ConfigManager``, now
   takes a lock before writes to allow for multiple processes to modify
   the configuration of a dataset.
   (`#4829 <https://github.com/datalad/datalad/issues/4829>`__)

-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   now records the original, unresolved URL for a subdataset under
   ``submodule.<name>.datalad-url`` in the parent’s .gitmodules,
   enabling later
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
   calls to use the original URL. This is particularly useful for
   ``ria+`` URLs.
   (`#5346 <https://github.com/datalad/datalad/issues/5346>`__)

-  Installing a subdataset now uses custom handling rather than calling
   ``git submodule update --init``. This avoids some locking issues when
   running
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
   in parallel and enables more accurate source URLs to be recorded.
   (`#4853 <https://github.com/datalad/datalad/issues/4853>`__)

-  ``GitRepo.get_content_info``, a helper that gets triggered by many
   commands, got faster by tweaking its ``git ls-files`` call.
   (`#5067 <https://github.com/datalad/datalad/issues/5067>`__)

-  `wtf <http://datalad.readthedocs.io/en/latest/generated/man/datalad-wtf.html>`__
   now includes credentials-related information (e.g. active backends)
   in the its output.
   (`#4982 <https://github.com/datalad/datalad/issues/4982>`__)

-  The ``call_git*`` methods of ``GitRepo`` now have a ``read_only``
   parameter. Callers can set this to ``True`` to promise that the
   provided command does not write to the repository, bypassing the cost
   of some checks and locking.
   (`#5070 <https://github.com/datalad/datalad/issues/5070>`__)

-  New ``call_annex*`` methods in the ``AnnexRepo`` class provide an
   interface for running git-annex commands similar to that of the
   ``GitRepo.call_git*`` methods.
   (`#5163 <https://github.com/datalad/datalad/issues/5163>`__)

-  It’s now possible to register a custom metadata indexer that is
   discovered by
   `search <http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html>`__
   and used to generate an index.
   (`#4963 <https://github.com/datalad/datalad/issues/4963>`__)

-  The ``ConfigManager`` methods ``get``, ``getbool``, ``getfloat``, and
   ``getint`` now return a single value (with same precedence as
   ``git   config --get``) when there are multiple values for the same
   key (in the non-committed git configuration, if the key is present
   there, or in the dataset configuration). For ``get``, the old
   behavior can be restored by specifying ``get_all=True``.
   (`#4924 <https://github.com/datalad/datalad/issues/4924>`__)

-  Command-line scripts are now defined via the ``entry_points``
   argument of ``setuptools.setup`` instead of the ``scripts`` argument.
   (`#4695 <https://github.com/datalad/datalad/issues/4695>`__)

-  Interactive use of ``--help`` on the command-line now invokes a pager
   on more systems and installation setups.
   (`#5344 <https://github.com/datalad/datalad/issues/5344>`__)

-  The ``datalad`` special remote now tries to eliminate some
   unnecessary interactions with git-annex by being smarter about how it
   queries for URLs associated with a key.
   (`#4955 <https://github.com/datalad/datalad/issues/4955>`__)

-  The ``GitRepo`` class now does a better job of handling bare
   repositories, a step towards bare repositories support in DataLad.
   (`#4911 <https://github.com/datalad/datalad/issues/4911>`__)

-  More internal work to move the code base over to the new command
   runner. (`#4699 <https://github.com/datalad/datalad/issues/4699>`__)
   (`#4855 <https://github.com/datalad/datalad/issues/4855>`__)
   (`#4900 <https://github.com/datalad/datalad/issues/4900>`__)
   (`#4996 <https://github.com/datalad/datalad/issues/4996>`__)
   (`#5002 <https://github.com/datalad/datalad/issues/5002>`__)
   (`#5141 <https://github.com/datalad/datalad/issues/5141>`__)
   (`#5142 <https://github.com/datalad/datalad/issues/5142>`__)
   (`#5229 <https://github.com/datalad/datalad/issues/5229>`__)

0.13.7 (January 04, 2021) – .
=============================

.. _fixes-6:

Fixes
-----

-  Cloning from a RIA store on the local file system initialized annex
   in the Git sibling of the RIA source, which is problematic because
   all annex-related functionality should go through the storage
   sibling.
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   now sets ``remote.origin.annex-ignore`` to ``true`` after cloning
   from RIA stores to prevent this.
   (`#5255 <https://github.com/datalad/datalad/issues/5255>`__)

-  `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__
   invoked ``cp`` in a way that was not compatible with macOS.
   (`#5269 <https://github.com/datalad/datalad/issues/5269>`__)

-  Due to a bug in older Git versions (before 2.25), calling
   `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__
   with a file under .git/ (e.g., ``datalad status .git/config``)
   incorrectly reported the file as untracked. A workaround has been
   added. (`#5258 <https://github.com/datalad/datalad/issues/5258>`__)

-  Update tests for compatibility with latest git-annex.
   (`#5254 <https://github.com/datalad/datalad/issues/5254>`__)

.. _enhancements-and-new-features-11:

Enhancements and new features
-----------------------------

-  `copy-file <http://datalad.readthedocs.io/en/latest/generated/man/datalad-copy-file.html>`__
   now aborts if .git/ is in the target directory, adding to its
   existing .git/ safety checks.
   (`#5258 <https://github.com/datalad/datalad/issues/5258>`__)

0.13.6 (December 14, 2020) – .
==============================

.. _fixes-7:

Fixes
-----

-  An assortment of fixes for Windows compatibility.
   (`#5113 <https://github.com/datalad/datalad/issues/5113>`__)
   (`#5119 <https://github.com/datalad/datalad/issues/5119>`__)
   (`#5125 <https://github.com/datalad/datalad/issues/5125>`__)
   (`#5127 <https://github.com/datalad/datalad/issues/5127>`__)
   (`#5136 <https://github.com/datalad/datalad/issues/5136>`__)
   (`#5201 <https://github.com/datalad/datalad/issues/5201>`__)
   (`#5200 <https://github.com/datalad/datalad/issues/5200>`__)
   (`#5214 <https://github.com/datalad/datalad/issues/5214>`__)

-  Adding a subdataset on a system that defaults to using an adjusted
   branch (i.e. doesn’t support symlinks) didn’t properly set up the
   submodule URL if the source dataset was not in an adjusted state.
   (`#5127 <https://github.com/datalad/datalad/issues/5127>`__)

-  `push <http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html>`__
   failed to push to a remote that did not have an ``annex-uuid`` value
   in the local ``.git/config``.
   (`#5148 <https://github.com/datalad/datalad/issues/5148>`__)

-  The default renderer has been improved to avoid a spurious leading
   space, which led to the displayed path being incorrect in some cases.
   (`#5121 <https://github.com/datalad/datalad/issues/5121>`__)

-  `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   showed an uninformative error message when asked to configure an
   unknown remote.
   (`#5146 <https://github.com/datalad/datalad/issues/5146>`__)

-  `drop <http://datalad.readthedocs.io/en/latest/generated/man/datalad-drop.html>`__
   confusingly relayed a suggestion from ``git annex drop`` to use
   ``--force``, an option that does not exist in ``datalad drop``.
   (`#5194 <https://github.com/datalad/datalad/issues/5194>`__)

-  `create-sibling-github <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-github.html>`__
   no longer offers user/password authentication because it is no longer
   supported by GitHub.
   (`#5218 <https://github.com/datalad/datalad/issues/5218>`__)

-  The internal command runner’s handling of the event loop has been
   tweaked to hopefully fix issues with running DataLad from IPython.
   (`#5106 <https://github.com/datalad/datalad/issues/5106>`__)

-  SSH cleanup wasn’t reliably triggered by the ORA special remote on
   failure, leading to a stall with a particular version of git-annex,
   8.20201103. (This is also resolved on git-annex’s end as of
   8.20201127.)
   (`#5151 <https://github.com/datalad/datalad/issues/5151>`__)

.. _enhancements-and-new-features-12:

Enhancements and new features
-----------------------------

-  The credential helper no longer asks the user to repeat tokens or AWS
   keys. (`#5219 <https://github.com/datalad/datalad/issues/5219>`__)

-  The new option ``datalad.locations.sockets`` controls where DataLad
   stores SSH sockets, allowing users to more easily work around file
   system and path length restrictions.
   (`#5238 <https://github.com/datalad/datalad/issues/5238>`__)

0.13.5 (October 30, 2020) – .
=============================

.. _fixes-8:

Fixes
-----

-  SSH connection handling has been reworked to fix cloning on Windows.
   A new configuration option, ``datalad.ssh.multiplex-connections``,
   defaults to false on Windows.
   (`#5042 <https://github.com/datalad/datalad/issues/5042>`__)

-  The ORA special remote and post-clone RIA configuration now provide
   authentication via DataLad’s credential mechanism and better handling
   of HTTP status codes.
   (`#5025 <https://github.com/datalad/datalad/issues/5025>`__)
   (`#5026 <https://github.com/datalad/datalad/issues/5026>`__)

-  By default, if a git executable is present in the same location as
   git-annex, DataLad modifies ``PATH`` when running git and git-annex
   so that the bundled git is used. This logic has been tightened to
   avoid unnecessarily adjusting the path, reducing the cases where the
   adjustment interferes with the local environment, such as special
   remotes in a virtual environment being masked by the system-wide
   variants.
   (`#5035 <https://github.com/datalad/datalad/issues/5035>`__)

-  git-annex is now consistently invoked as “git annex” rather than
   “git-annex” to work around failures on Windows.
   (`#5001 <https://github.com/datalad/datalad/issues/5001>`__)

-  `push <http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html>`__
   called ``git annex sync ...`` on plain git repositories.
   (`#5051 <https://github.com/datalad/datalad/issues/5051>`__)

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   in genernal doesn’t support registering multiple levels of untracked
   subdatasets, but it can now properly register nested subdatasets when
   all of the subdataset paths are passed explicitly (e.g.,
   ``datalad save -d. sub-a sub-a/sub-b``).
   (`#5049 <https://github.com/datalad/datalad/issues/5049>`__)

-  When called with ``--sidecar`` and ``--explicit``,
   `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   didn’t save the sidecar.
   (`#5017 <https://github.com/datalad/datalad/issues/5017>`__)

-  A couple of spots didn’t properly quote format fields when combining
   substrings into a format string.
   (`#4957 <https://github.com/datalad/datalad/issues/4957>`__)

-  The default credentials configured for ``indi-s3`` prevented
   anonymous access.
   (`#5045 <https://github.com/datalad/datalad/issues/5045>`__)

.. _enhancements-and-new-features-13:

Enhancements and new features
-----------------------------

-  Messages about suppressed similar results are now rate limited to
   improve performance when there are many similar results coming
   through quickly.
   (`#5060 <https://github.com/datalad/datalad/issues/5060>`__)

-  `create-sibling-github <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-github.html>`__
   can now be told to replace an existing sibling by passing
   ``--existing=replace``.
   (`#5008 <https://github.com/datalad/datalad/issues/5008>`__)

-  Progress bars now react to changes in the terminal’s width (requires
   tqdm 2.1 or later).
   (`#5057 <https://github.com/datalad/datalad/issues/5057>`__)

0.13.4 (October 6, 2020) – .
============================

.. _fixes-9:

Fixes
-----

-  Ephemeral clones mishandled bare repositories.
   (`#4899 <https://github.com/datalad/datalad/issues/4899>`__)

-  The post-clone logic for configuring RIA stores didn’t consider
   ``https://`` URLs.
   (`#4977 <https://github.com/datalad/datalad/issues/4977>`__)

-  DataLad custom remotes didn’t escape newlines in messages sent to
   git-annex.
   (`#4926 <https://github.com/datalad/datalad/issues/4926>`__)

-  The datalad-archives special remote incorrectly treated file names as
   percent-encoded.
   (`#4953 <https://github.com/datalad/datalad/issues/4953>`__)

-  The result handler didn’t properly escape “%” when constructing its
   message template.
   (`#4953 <https://github.com/datalad/datalad/issues/4953>`__)

-  In v0.13.0, the tailored rendering for specific subtypes of external
   command failures (e.g., “out of space” or “remote not available”) was
   unintentionally switched to the default rendering.
   (`#4966 <https://github.com/datalad/datalad/issues/4966>`__)

-  Various fixes and updates for the NDA authenticator.
   (`#4824 <https://github.com/datalad/datalad/issues/4824>`__)

-  The helper for getting a versioned S3 URL did not support anonymous
   access or buckets with “.” in their name.
   (`#4985 <https://github.com/datalad/datalad/issues/4985>`__)

-  Several issues with the handling of S3 credentials and token
   expiration have been addressed.
   (`#4927 <https://github.com/datalad/datalad/issues/4927>`__)
   (`#4931 <https://github.com/datalad/datalad/issues/4931>`__)
   (`#4952 <https://github.com/datalad/datalad/issues/4952>`__)

.. _enhancements-and-new-features-14:

Enhancements and new features
-----------------------------

-  A warning is now given if the detected Git is below v2.13.0 to let
   users that run into problems know that their Git version is likely
   the culprit.
   (`#4866 <https://github.com/datalad/datalad/issues/4866>`__)

-  A fix to
   `push <http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html>`__
   in v0.13.2 introduced a regression that surfaces when
   ``push.default`` is configured to “matching” and prevents the
   git-annex branch from being pushed. Note that, as part of the fix,
   the current branch is now always pushed even when it wouldn’t be
   based on the configured refspec or ``push.default`` value.
   (`#4896 <https://github.com/datalad/datalad/issues/4896>`__)

-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__

   -  now allows spelling the empty string value of ``--since=`` as
      ``^`` for consistency with
      `push <http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html>`__.
      (`#4683 <https://github.com/datalad/datalad/issues/4683>`__)
   -  compares a revision given to ``--since=`` with ``HEAD`` rather
      than the working tree to speed up the operation.
      (`#4448 <https://github.com/datalad/datalad/issues/4448>`__)

-  `rerun <https://datalad.readthedocs.io/en/latest/generated/man/datalad-rerun.html>`__

   -  emits more INFO-level log messages.
      (`#4764 <https://github.com/datalad/datalad/issues/4764>`__)
   -  provides better handling of adjusted branches and aborts with a
      clear error for cases that are not supported.
      (`#5328 <https://github.com/datalad/datalad/issues/5328>`__)

-  The archives are handled with p7zip, if available, since DataLad
   v0.12.0. This implementation now supports .tgz and .tbz2 archives.
   (`#4877 <https://github.com/datalad/datalad/issues/4877>`__)

0.13.3 (August 28, 2020) – .
============================

.. _fixes-10:

Fixes
-----

-  Work around a Python bug that led to our asyncio-based command runner
   intermittently failing to capture the output of commands that exit
   very quickly.
   (`#4835 <https://github.com/datalad/datalad/issues/4835>`__)

-  `push <http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html>`__
   displayed an overestimate of the transfer size when multiple files
   pointed to the same key.
   (`#4821 <https://github.com/datalad/datalad/issues/4821>`__)

-  When
   `download-url <https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html>`__
   calls ``git annex addurl``, it catches and reports any failures
   rather than crashing. A change in v0.12.0 broke this handling in a
   particular case.
   (`#4817 <https://github.com/datalad/datalad/issues/4817>`__)

.. _enhancements-and-new-features-15:

Enhancements and new features
-----------------------------

-  The wrapper functions returned by decorators are now given more
   meaningful names to hopefully make tracebacks easier to digest.
   (`#4834 <https://github.com/datalad/datalad/issues/4834>`__)

0.13.2 (August 10, 2020) – .
============================

Deprecations
------------

-  The ``allow_quick`` parameter of ``AnnexRepo.file_has_content`` and
   ``AnnexRepo.is_under_annex`` is now ignored and will be removed in a
   later release. This parameter was only relevant for git-annex
   versions before 7.20190912.
   (`#4736 <https://github.com/datalad/datalad/issues/4736>`__)

.. _fixes-11:

Fixes
-----

-  Updates for compatibility with recent git and git-annex releases.
   (`#4746 <https://github.com/datalad/datalad/issues/4746>`__)
   (`#4760 <https://github.com/datalad/datalad/issues/4760>`__)
   (`#4684 <https://github.com/datalad/datalad/issues/4684>`__)

-  `push <http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html>`__
   didn’t sync the git-annex branch when ``--data=nothing`` was
   specified.
   (`#4786 <https://github.com/datalad/datalad/issues/4786>`__)

-  The ``datalad.clone.reckless`` configuration wasn’t stored in
   non-annex datasets, preventing the values from being inherited by
   annex subdatasets.
   (`#4749 <https://github.com/datalad/datalad/issues/4749>`__)

-  Running the post-update hook installed by ``create-sibling --ui``
   could overwrite web log files from previous runs in the unlikely
   event that the hook was executed multiple times in the same second.
   (`#4745 <https://github.com/datalad/datalad/issues/4745>`__)

-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   inspected git’s standard error in a way that could cause an attribute
   error. (`#4775 <https://github.com/datalad/datalad/issues/4775>`__)

-  When cloning a repository whose ``HEAD`` points to a branch without
   commits,
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   tries to find a more useful branch to check out. It unwisely
   considered adjusted branches.
   (`#4792 <https://github.com/datalad/datalad/issues/4792>`__)

-  Since v0.12.0, ``SSHManager.close`` hasn’t closed connections when
   the ``ctrl_path`` argument was explicitly given.
   (`#4757 <https://github.com/datalad/datalad/issues/4757>`__)

-  When working in a dataset in which ``git annex init`` had not yet
   been called, the ``file_has_content`` and ``is_under_annex`` methods
   of ``AnnexRepo`` incorrectly took the “allow quick” code path on file
   systems that did not support it
   (`#4736 <https://github.com/datalad/datalad/issues/4736>`__)

Enhancements
------------

-  `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__
   now assigns version 4 (random) UUIDs instead of version 1 UUIDs that
   encode the time and hardware address.
   (`#4790 <https://github.com/datalad/datalad/issues/4790>`__)

-  The documentation for
   `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__
   now does a better job of describing the interaction between
   ``--dataset`` and ``PATH``.
   (`#4763 <https://github.com/datalad/datalad/issues/4763>`__)

-  The ``format_commit`` and ``get_hexsha`` methods of ``GitRepo`` have
   been sped up.
   (`#4807 <https://github.com/datalad/datalad/issues/4807>`__)
   (`#4806 <https://github.com/datalad/datalad/issues/4806>`__)

-  A better error message is now shown when the ``^`` or ``^.``
   shortcuts for ``--dataset`` do not resolve to a dataset.
   (`#4759 <https://github.com/datalad/datalad/issues/4759>`__)

-  A more helpful error message is now shown if a caller tries to
   download an ``ftp://`` link but does not have ``request_ftp``
   installed.
   (`#4788 <https://github.com/datalad/datalad/issues/4788>`__)

-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   now tries harder to get up-to-date availability information after
   auto-enabling ``type=git`` special remotes.
   (`#2897 <https://github.com/datalad/datalad/issues/2897>`__)

0.13.1 (July 17, 2020) – .
==========================

.. _fixes-12:

Fixes
-----

-  Cloning a subdataset should inherit the parent’s
   ``datalad.clone.reckless`` value, but that did not happen when
   cloning via ``datalad get`` rather than ``datalad install`` or
   ``datalad clone``.
   (`#4657 <https://github.com/datalad/datalad/issues/4657>`__)

-  The default result renderer crashed when the result did not have a
   ``path`` key.
   (`#4666 <https://github.com/datalad/datalad/issues/4666>`__)
   (`#4673 <https://github.com/datalad/datalad/issues/4673>`__)

-  ``datalad push`` didn’t show information about ``git push`` errors
   when the output was not in the format that it expected.
   (`#4674 <https://github.com/datalad/datalad/issues/4674>`__)

-  ``datalad push`` silently accepted an empty string for ``--since``
   even though it is an invalid value.
   (`#4682 <https://github.com/datalad/datalad/issues/4682>`__)

-  Our JavaScript testing setup on Travis grew stale and has now been
   updated. (Thanks to Xiao Gui.)
   (`#4687 <https://github.com/datalad/datalad/issues/4687>`__)

-  The new class for running Git commands (added in v0.13.0) ignored any
   changes to the process environment that occurred after instantiation.
   (`#4703 <https://github.com/datalad/datalad/issues/4703>`__)

.. _enhancements-and-new-features-16:

Enhancements and new features
-----------------------------

-  ``datalad push`` now avoids unnecessary ``git push`` dry runs and
   pushes all refspecs with a single ``git push`` call rather than
   invoking ``git   push`` for each one.
   (`#4692 <https://github.com/datalad/datalad/issues/4692>`__)
   (`#4675 <https://github.com/datalad/datalad/issues/4675>`__)

-  The readability of SSH error messages has been improved.
   (`#4729 <https://github.com/datalad/datalad/issues/4729>`__)

-  ``datalad.support.annexrepo`` avoids calling
   ``datalad.utils.get_linux_distribution`` at import time and caches
   the result once it is called because, as of Python 3.8, the function
   uses ``distro`` underneath, adding noticeable overhead.
   (`#4696 <https://github.com/datalad/datalad/issues/4696>`__)

   Third-party code should be updated to use ``get_linux_distribution``
   directly in the unlikely event that the code relied on the
   import-time call to ``get_linux_distribution`` setting the
   ``linux_distribution_name``, ``linux_distribution_release``, or
   ``on_debian_wheezy`` attributes in \`datalad.utils.

0.13.0 (June 23, 2020) – .
==========================

A handful of new commands, including ``copy-file``, ``push``, and
``create-sibling-ria``, along with various fixes and enhancements

.. _major-refactoring-and-deprecations-1:

Major refactoring and deprecations
----------------------------------

-  The ``no_annex`` parameter of
   `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__,
   which is exposed in the Python API but not the command line, is
   deprecated and will be removed in a later release. Use the new
   ``annex`` argument instead, flipping the value. Command-line callers
   that use ``--no-annex`` are unaffected.
   (`#4321 <https://github.com/datalad/datalad/issues/4321>`__)

-  ``datalad add``, which was deprecated in 0.12.0, has been removed.
   (`#4158 <https://github.com/datalad/datalad/issues/4158>`__)
   (`#4319 <https://github.com/datalad/datalad/issues/4319>`__)

-  The following ``GitRepo`` and ``AnnexRepo`` methods have been
   removed: ``get_changed_files``, ``get_missing_files``, and
   ``get_deleted_files``.
   (`#4169 <https://github.com/datalad/datalad/issues/4169>`__)
   (`#4158 <https://github.com/datalad/datalad/issues/4158>`__)

-  The ``get_branch_commits`` method of ``GitRepo`` and ``AnnexRepo``
   has been renamed to ``get_branch_commits_``.
   (`#3834 <https://github.com/datalad/datalad/issues/3834>`__)

-  The custom ``commit`` method of ``AnnexRepo`` has been removed, and
   ``AnnexRepo.commit`` now resolves to the parent method,
   ``GitRepo.commit``.
   (`#4168 <https://github.com/datalad/datalad/issues/4168>`__)

-  GitPython’s ``git.repo.base.Repo`` class is no longer available via
   the ``.repo`` attribute of ``GitRepo`` and ``AnnexRepo``.
   (`#4172 <https://github.com/datalad/datalad/issues/4172>`__)

-  ``AnnexRepo.get_corresponding_branch`` now returns ``None`` rather
   than the current branch name when a managed branch is not checked
   out. (`#4274 <https://github.com/datalad/datalad/issues/4274>`__)

-  The special UUID for git-annex web remotes is now available as
   ``datalad.consts.WEB_SPECIAL_REMOTE_UUID``. It remains accessible as
   ``AnnexRepo.WEB_UUID`` for compatibility, but new code should use
   ``consts.WEB_SPECIAL_REMOTE_UUID``
   (`#4460 <https://github.com/datalad/datalad/issues/4460>`__).

.. _fixes-13:

Fixes
-----

-  Widespread improvements in functionality and test coverage on Windows
   and crippled file systems in general.
   (`#4057 <https://github.com/datalad/datalad/issues/4057>`__)
   (`#4245 <https://github.com/datalad/datalad/issues/4245>`__)
   (`#4268 <https://github.com/datalad/datalad/issues/4268>`__)
   (`#4276 <https://github.com/datalad/datalad/issues/4276>`__)
   (`#4291 <https://github.com/datalad/datalad/issues/4291>`__)
   (`#4296 <https://github.com/datalad/datalad/issues/4296>`__)
   (`#4301 <https://github.com/datalad/datalad/issues/4301>`__)
   (`#4303 <https://github.com/datalad/datalad/issues/4303>`__)
   (`#4304 <https://github.com/datalad/datalad/issues/4304>`__)
   (`#4305 <https://github.com/datalad/datalad/issues/4305>`__)
   (`#4306 <https://github.com/datalad/datalad/issues/4306>`__)

-  ``AnnexRepo.get_size_from_key`` incorrectly handled file chunks.
   (`#4081 <https://github.com/datalad/datalad/issues/4081>`__)

-  `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__
   would too readily clobber existing paths when called with
   ``--existing=replace``. It now gets confirmation from the user before
   doing so if running interactively and unconditionally aborts when
   running non-interactively.
   (`#4147 <https://github.com/datalad/datalad/issues/4147>`__)

-  `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   (`#4159 <https://github.com/datalad/datalad/issues/4159>`__)

   -  queried the incorrect branch configuration when updating non-annex
      repositories.
   -  didn’t account for the fact that the local repository can be
      configured as the upstream “remote” for a branch.

-  When the caller included ``--bare`` as a ``git init`` option,
   `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__
   crashed creating the bare repository, which is currently unsupported,
   rather than aborting with an informative error message.
   (`#4065 <https://github.com/datalad/datalad/issues/4065>`__)

-  The logic for automatically propagating the ‘origin’ remote when
   cloning a local source could unintentionally trigger a fetch of a
   non-local remote.
   (`#4196 <https://github.com/datalad/datalad/issues/4196>`__)

-  All remaining ``get_submodules()`` call sites that relied on the
   temporary compatibility layer added in v0.12.0 have been updated.
   (`#4348 <https://github.com/datalad/datalad/issues/4348>`__)

-  The custom result summary renderer for
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__,
   which was visible with ``--output-format=tailored``, displayed
   incorrect and confusing information in some cases. The custom
   renderer has been removed entirely.
   (`#4471 <https://github.com/datalad/datalad/issues/4471>`__)

-  The documentation for the Python interface of a command listed an
   incorrect default when the command overrode the value of command
   parameters such as ``result_renderer``.
   (`#4480 <https://github.com/datalad/datalad/issues/4480>`__)

.. _enhancements-and-new-features-17:

Enhancements and new features
-----------------------------

-  The default result renderer learned to elide a chain of results after
   seeing ten consecutive results that it considers similar, which
   improves the display of actions that have many results (e.g., saving
   hundreds of files).
   (`#4337 <https://github.com/datalad/datalad/issues/4337>`__)

-  The default result renderer, in addition to “tailored” result
   renderer, now triggers the custom summary renderer, if any.
   (`#4338 <https://github.com/datalad/datalad/issues/4338>`__)

-  The new command
   `create-sibling-ria <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-ria.html>`__
   provides support for creating a sibling in a `RIA
   store <http://handbook.datalad.org/en/latest/usecases/datastorage_for_institutions.html>`__.
   (`#4124 <https://github.com/datalad/datalad/issues/4124>`__)

-  DataLad ships with a new special remote, git-annex-remote-ora, for
   interacting with `RIA
   stores <http://handbook.datalad.org/en/latest/usecases/datastorage_for_institutions.html>`__
   and a new command
   `export-archive-ora <http://datalad.readthedocs.io/en/latest/generated/man/datalad-export-archive-ora.html>`__
   for exporting an archive from a local annex object store.
   (`#4260 <https://github.com/datalad/datalad/issues/4260>`__)
   (`#4203 <https://github.com/datalad/datalad/issues/4203>`__)

-  The new command
   `push <http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html>`__
   provides an alternative interface to
   `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   for pushing a dataset hierarchy to a sibling.
   (`#4206 <https://github.com/datalad/datalad/issues/4206>`__)
   (`#4581 <https://github.com/datalad/datalad/issues/4581>`__)
   (`#4617 <https://github.com/datalad/datalad/issues/4617>`__)
   (`#4620 <https://github.com/datalad/datalad/issues/4620>`__)

-  The new command
   `copy-file <http://datalad.readthedocs.io/en/latest/generated/man/datalad-copy-file.html>`__
   copies files and associated availability information from one dataset
   to another.
   (`#4430 <https://github.com/datalad/datalad/issues/4430>`__)

-  The command examples have been expanded and improved.
   (`#4091 <https://github.com/datalad/datalad/issues/4091>`__)
   (`#4314 <https://github.com/datalad/datalad/issues/4314>`__)
   (`#4464 <https://github.com/datalad/datalad/issues/4464>`__)

-  The tooling for linking to the `DataLad
   Handbook <http://handbook.datalad.org>`__ from DataLad’s
   documentation has been improved.
   (`#4046 <https://github.com/datalad/datalad/issues/4046>`__)

-  The ``--reckless`` parameter of
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   and
   `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   learned two new modes:

   -  “ephemeral”, where the .git/annex/ of the cloned repository is
      symlinked to the local source repository’s.
      (`#4099 <https://github.com/datalad/datalad/issues/4099>`__)
   -  “shared-{group|all\|…}” that can be used to set up datasets for
      collaborative write access.
      (`#4324 <https://github.com/datalad/datalad/issues/4324>`__)

-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__

   -  learned to handle dataset aliases in RIA stores when given a URL
      of the form ``ria+<protocol>://<storelocation>#~<aliasname>``.
      (`#4459 <https://github.com/datalad/datalad/issues/4459>`__)
   -  now checks ``datalad.get.subdataset-source-candidate-NAME`` to see
      if ``NAME`` starts with three digits, which is taken as a “cost”.
      Sources with lower costs will be tried first.
      (`#4619 <https://github.com/datalad/datalad/issues/4619>`__)

-  `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   (`#4167 <https://github.com/datalad/datalad/issues/4167>`__)

   -  learned to disallow non-fast-forward updates when ``ff-only`` is
      given to the ``--merge`` option.
   -  gained a ``--follow`` option that controls how ``--merge``
      behaves, adding support for merging in the revision that is
      registered in the parent dataset rather than merging in the
      configured branch from the sibling.
   -  now provides a result record for merge events.

-  `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__
   now supports local paths as targets in addition to SSH URLs.
   (`#4187 <https://github.com/datalad/datalad/issues/4187>`__)

-  `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   now

   -  shows a warning if the caller requests to delete a sibling that
      does not exist.
      (`#4257 <https://github.com/datalad/datalad/issues/4257>`__)
   -  phrases its warning about non-annex repositories in a less
      alarming way.
      (`#4323 <https://github.com/datalad/datalad/issues/4323>`__)

-  The rendering of command errors has been improved.
   (`#4157 <https://github.com/datalad/datalad/issues/4157>`__)

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   now

   -  displays a message to signal that the working tree is clean,
      making it more obvious that no results being rendered corresponds
      to a clean state.
      (`#4106 <https://github.com/datalad/datalad/issues/4106>`__)
   -  provides a stronger warning against using ``--to-git``.
      (`#4290 <https://github.com/datalad/datalad/issues/4290>`__)

-  `diff <http://datalad.readthedocs.io/en/latest/generated/man/datalad-diff.html>`__
   and
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   learned about scenarios where they could avoid unnecessary and
   expensive work.
   (`#4526 <https://github.com/datalad/datalad/issues/4526>`__)
   (`#4544 <https://github.com/datalad/datalad/issues/4544>`__)
   (`#4549 <https://github.com/datalad/datalad/issues/4549>`__)

-  Calling
   `diff <http://datalad.readthedocs.io/en/latest/generated/man/datalad-diff.html>`__
   without ``--recursive`` but with a path constraint within a
   subdataset (“/”) now traverses into the subdataset, as “/” would,
   restricting its report to “/”.
   (`#4235 <https://github.com/datalad/datalad/issues/4235>`__)

-  New option ``datalad.annex.retry`` controls how many times git-annex
   will retry on a failed transfer. It defaults to 3 and can be set to 0
   to restore the previous behavior.
   (`#4382 <https://github.com/datalad/datalad/issues/4382>`__)

-  `wtf <http://datalad.readthedocs.io/en/latest/generated/man/datalad-wtf.html>`__
   now warns when the specified dataset does not exist.
   (`#4331 <https://github.com/datalad/datalad/issues/4331>`__)

-  The ``repr`` and ``str`` output of the dataset and repo classes got a
   facelift.
   (`#4420 <https://github.com/datalad/datalad/issues/4420>`__)
   (`#4435 <https://github.com/datalad/datalad/issues/4435>`__)
   (`#4439 <https://github.com/datalad/datalad/issues/4439>`__)

-  The DataLad Singularity container now comes with p7zip-full.

-  DataLad emits a log message when the current working directory is
   resolved to a different location due to a symlink. This is now logged
   at the DEBUG rather than WARNING level, as it typically does not
   indicate a problem.
   (`#4426 <https://github.com/datalad/datalad/issues/4426>`__)

-  DataLad now lets the caller know that ``git annex init`` is scanning
   for unlocked files, as this operation can be slow in some
   repositories.
   (`#4316 <https://github.com/datalad/datalad/issues/4316>`__)

-  The ``log_progress`` helper learned how to set the starting point to
   a non-zero value and how to update the total of an existing progress
   bar, two features needed for planned improvements to how some
   commands display their progress.
   (`#4438 <https://github.com/datalad/datalad/issues/4438>`__)

-  The ``ExternalVersions`` object, which is used to check versions of
   Python modules and external tools (e.g., git-annex), gained an
   ``add`` method that enables DataLad extensions and other third-party
   code to include other programs of interest.
   (`#4441 <https://github.com/datalad/datalad/issues/4441>`__)

-  All of the remaining spots that use GitPython have been rewritten
   without it. Most notably, this includes rewrites of the ``clone``,
   ``fetch``, and ``push`` methods of ``GitRepo``.
   (`#4080 <https://github.com/datalad/datalad/issues/4080>`__)
   (`#4087 <https://github.com/datalad/datalad/issues/4087>`__)
   (`#4170 <https://github.com/datalad/datalad/issues/4170>`__)
   (`#4171 <https://github.com/datalad/datalad/issues/4171>`__)
   (`#4175 <https://github.com/datalad/datalad/issues/4175>`__)
   (`#4172 <https://github.com/datalad/datalad/issues/4172>`__)

-  When ``GitRepo.commit`` splits its operation across multiple calls to
   avoid exceeding the maximum command line length, it now amends to
   initial commit rather than creating multiple commits.
   (`#4156 <https://github.com/datalad/datalad/issues/4156>`__)

-  ``GitRepo`` gained a ``get_corresponding_branch`` method (which
   always returns None), allowing a caller to invoke the method without
   needing to check if the underlying repo class is ``GitRepo`` or
   ``AnnexRepo``.
   (`#4274 <https://github.com/datalad/datalad/issues/4274>`__)

-  A new helper function ``datalad.core.local.repo.repo_from_path``
   returns a repo class for a specified path.
   (`#4273 <https://github.com/datalad/datalad/issues/4273>`__)

-  New ``AnnexRepo`` method ``localsync`` performs a ``git annex sync``
   that disables external interaction and is particularly useful for
   propagating changes on an adjusted branch back to the main branch.
   (`#4243 <https://github.com/datalad/datalad/issues/4243>`__)

0.12.7 (May 22, 2020) – .
=========================

.. _fixes-14:

Fixes
-----

-  Requesting tailored output (``--output=tailored``) from a command
   with a custom result summary renderer produced repeated output.
   (`#4463 <https://github.com/datalad/datalad/issues/4463>`__)

-  A longstanding regression in argcomplete-based command-line
   completion for Bash has been fixed. You can enable completion by
   configuring a Bash startup file to run
   ``eval   "$(register-python-argcomplete datalad)"`` or source
   DataLad’s ``tools/cmdline-completion``. The latter should work for
   Zsh as well.
   (`#4477 <https://github.com/datalad/datalad/issues/4477>`__)

-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   didn’t prevent ``git-fetch`` from recursing into submodules, leading
   to a failure when the registered submodule was not present locally
   and the submodule did not have a remote named ‘origin’.
   (`#4560 <https://github.com/datalad/datalad/issues/4560>`__)

-  `addurls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-addurls.html>`__
   botched path handling when the file name format started with “./” and
   the call was made from a subdirectory of the dataset.
   (`#4504 <https://github.com/datalad/datalad/issues/4504>`__)

-  Double dash options in manpages were unintentionally escaped.
   (`#4332 <https://github.com/datalad/datalad/issues/4332>`__)

-  The check for HTTP authentication failures crashed in situations
   where content came in as bytes rather than unicode.
   (`#4543 <https://github.com/datalad/datalad/issues/4543>`__)

-  A check in ``AnnexRepo.whereis`` could lead to a type error.
   (`#4552 <https://github.com/datalad/datalad/issues/4552>`__)

-  When installing a dataset to obtain a subdataset,
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
   confusingly displayed a message that described the containing dataset
   as “underneath” the subdataset.
   (`#4456 <https://github.com/datalad/datalad/issues/4456>`__)

-  A couple of Makefile rules didn’t properly quote paths.
   (`#4481 <https://github.com/datalad/datalad/issues/4481>`__)

-  With DueCredit support enabled (``DUECREDIT_ENABLE=1``), the query
   for metadata information could flood the output with warnings if
   datasets didn’t have aggregated metadata. The warnings are now
   silenced, with the overall failure of a
   `metadata <http://datalad.readthedocs.io/en/latest/generated/man/datalad-metadata.html>`__
   call logged at the debug level.
   (`#4568 <https://github.com/datalad/datalad/issues/4568>`__)

.. _enhancements-and-new-features-18:

Enhancements and new features
-----------------------------

-  The resource identifier helper learned to recognize URLs with
   embedded Git transport information, such as
   gcrypt::https://example.com.
   (`#4529 <https://github.com/datalad/datalad/issues/4529>`__)

-  When running non-interactively, a more informative error is now
   signaled when the UI backend, which cannot display a question, is
   asked to do so.
   (`#4553 <https://github.com/datalad/datalad/issues/4553>`__)

0.12.6 (April 23, 2020) – .
===========================

.. _major-refactoring-and-deprecations-2:

Major refactoring and deprecations
----------------------------------

-  The value of ``datalad.support.annexrep.N_AUTO_JOBS`` is no longer
   considered. The variable will be removed in a later release.
   (`#4409 <https://github.com/datalad/datalad/issues/4409>`__)

.. _fixes-15:

Fixes
-----

-  Staring with v0.12.0, ``datalad save`` recorded the current branch of
   a parent dataset as the ``branch`` value in the .gitmodules entry for
   a subdataset. This behavior is problematic for a few reasons and has
   been reverted.
   (`#4375 <https://github.com/datalad/datalad/issues/4375>`__)

-  The default for the ``--jobs`` option, “auto”, instructed DataLad to
   pass a value to git-annex’s ``--jobs`` equal to
   ``min(8, max(3, <number   of CPUs>))``, which could lead to issues
   due to the large number of child processes spawned and file
   descriptors opened. To avoid this behavior, ``--jobs=auto`` now
   results in git-annex being called with ``--jobs=1`` by default.
   Configure the new option ``datalad.runtime.max-annex-jobs`` to
   control the maximum value that will be considered when
   ``--jobs='auto'``.
   (`#4409 <https://github.com/datalad/datalad/issues/4409>`__)

-  Various commands have been adjusted to better handle the case where a
   remote’s HEAD ref points to an unborn branch.
   (`#4370 <https://github.com/datalad/datalad/issues/4370>`__)

-  `search <http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html>`__

   -  learned to use the query as a regular expression that restricts
      the keys that are shown for ``--show-keys short``.
      (`#4354 <https://github.com/datalad/datalad/issues/4354>`__)
   -  gives a more helpful message when query is an invalid regular
      expression.
      (`#4398 <https://github.com/datalad/datalad/issues/4398>`__)

-  The code for parsing Git configuration did not follow Git’s behavior
   of accepting a key with no value as shorthand for key=true.
   (`#4421 <https://github.com/datalad/datalad/issues/4421>`__)

-  ``AnnexRepo.info`` needed a compatibility update for a change in how
   git-annex reports file names.
   (`#4431 <https://github.com/datalad/datalad/issues/4431>`__)

-  `create-sibling-github <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-github.html>`__
   did not gracefully handle a token that did not have the necessary
   permissions.
   (`#4400 <https://github.com/datalad/datalad/issues/4400>`__)

.. _enhancements-and-new-features-19:

Enhancements and new features
-----------------------------

-  `search <http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html>`__
   learned to use the query as a regular expression that restricts the
   keys that are shown for ``--show-keys short``.
   (`#4354 <https://github.com/datalad/datalad/issues/4354>`__)

-  ``datalad <subcommand>`` learned to point to the
   `datalad-container <https://github.com/datalad/datalad-container>`__
   extension when a subcommand from that extension is given but the
   extension is not installed.
   (`#4400 <https://github.com/datalad/datalad/issues/4400>`__)
   (`#4174 <https://github.com/datalad/datalad/issues/4174>`__)

0.12.5 (Apr 02, 2020) – a small step for datalad …
==================================================

Fix some bugs and make the world an even better place.

.. _fixes-16:

Fixes
-----

-  Our ``log_progress`` helper mishandled the initial display and step
   of the progress bar.
   (`#4326 <https://github.com/datalad/datalad/issues/4326>`__)

-  ``AnnexRepo.get_content_annexinfo`` is designed to accept
   ``init=None``, but passing that led to an error.
   (`#4330 <https://github.com/datalad/datalad/issues/4330>`__)

-  Update a regular expression to handle an output change in Git
   v2.26.0. (`#4328 <https://github.com/datalad/datalad/issues/4328>`__)

-  We now set ``LC_MESSAGES`` to ‘C’ while running git to avoid failures
   when parsing output that is marked for translation.
   (`#4342 <https://github.com/datalad/datalad/issues/4342>`__)

-  The helper for decoding JSON streams loaded the last line of input
   without decoding it if the line didn’t end with a new line, a
   regression introduced in the 0.12.0 release.
   (`#4361 <https://github.com/datalad/datalad/issues/4361>`__)

-  The clone command failed to git-annex-init a fresh clone whenever it
   considered to add the origin of the origin as a remote.
   (`#4367 <https://github.com/datalad/datalad/issues/4367>`__)

0.12.4 (Mar 19, 2020) – Windows?!
=================================

The main purpose of this release is to have one on PyPi that has no
associated wheel to enable a working installation on Windows
(`#4315 <https://github.com/datalad/datalad/issues/4315>`__).

.. _fixes-17:

Fixes
-----

-  The description of the ``log.outputs`` config switch did not keep up
   with code changes and incorrectly stated that the output would be
   logged at the DEBUG level; logging actually happens at a lower level.
   (`#4317 <https://github.com/datalad/datalad/issues/4317>`__)

0.12.3 (March 16, 2020) – .
===========================

Updates for compatibility with the latest git-annex, along with a few
miscellaneous fixes

.. _major-refactoring-and-deprecations-3:

Major refactoring and deprecations
----------------------------------

-  All spots that raised a ``NoDatasetArgumentFound`` exception now
   raise a ``NoDatasetFound`` exception to better reflect the situation:
   it is the *dataset* rather than the *argument* that is not found. For
   compatibility, the latter inherits from the former, but new code
   should prefer the latter.
   (`#4285 <https://github.com/datalad/datalad/issues/4285>`__)

.. _fixes-18:

Fixes
-----

-  Updates for compatibility with git-annex version 8.20200226.
   (`#4214 <https://github.com/datalad/datalad/issues/4214>`__)

-  ``datalad export-to-figshare`` failed to export if the generated
   title was fewer than three characters. It now queries the caller for
   the title and guards against titles that are too short.
   (`#4140 <https://github.com/datalad/datalad/issues/4140>`__)

-  Authentication was requested multiple times when git-annex launched
   parallel downloads from the ``datalad`` special remote.
   (`#4308 <https://github.com/datalad/datalad/issues/4308>`__)

-  At verbose logging levels, DataLad requests that git-annex display
   debugging information too. Work around a bug in git-annex that
   prevented that from happening.
   (`#4212 <https://github.com/datalad/datalad/issues/4212>`__)

-  The internal command runner looked in the wrong place for some
   configuration variables, including ``datalad.log.outputs``, resulting
   in the default value always being used.
   (`#4194 <https://github.com/datalad/datalad/issues/4194>`__)

-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   failed when trying to publish to a git-lfs special remote for the
   first time.
   (`#4200 <https://github.com/datalad/datalad/issues/4200>`__)

-  ``AnnexRepo.set_remote_url`` is supposed to establish shared SSH
   connections but failed to do so.
   (`#4262 <https://github.com/datalad/datalad/issues/4262>`__)

.. _enhancements-and-new-features-20:

Enhancements and new features
-----------------------------

-  The message provided when a command cannot determine what dataset to
   operate on has been improved.
   (`#4285 <https://github.com/datalad/datalad/issues/4285>`__)

-  The “aws-s3” authentication type now allows specifying the host
   through “aws-s3_host”, which was needed to work around an
   authorization error due to a longstanding upstream bug.
   (`#4239 <https://github.com/datalad/datalad/issues/4239>`__)

-  The xmp metadata extractor now recognizes “.wav” files.

0.12.2 (Jan 28, 2020) – Smoothen the ride
=========================================

Mostly a bugfix release with various robustifications, but also makes
the first step towards versioned dataset installation requests.

.. _major-refactoring-and-deprecations-4:

Major refactoring and deprecations
----------------------------------

-  The minimum required version for GitPython is now 2.1.12.
   (`#4070 <https://github.com/datalad/datalad/issues/4070>`__)

.. _fixes-19:

Fixes
-----

-  The class for handling configuration values, ``ConfigManager``,
   inappropriately considered the current working directory’s dataset,
   if any, for both reading and writing when instantiated with
   ``dataset=None``. This misbehavior is fairly inaccessible through
   typical use of DataLad. It affects ``datalad.cfg``, the top-level
   configuration instance that should not consider repository-specific
   values. It also affects Python users that call ``Dataset`` with a
   path that does not yet exist and persists until that dataset is
   created. (`#4078 <https://github.com/datalad/datalad/issues/4078>`__)

-  `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   saved the dataset when called with ``--merge``, which is unnecessary
   and risks committing unrelated changes.
   (`#3996 <https://github.com/datalad/datalad/issues/3996>`__)

-  Confusing and irrelevant information about Python defaults have been
   dropped from the command-line help.
   (`#4002 <https://github.com/datalad/datalad/issues/4002>`__)

-  The logic for automatically propagating the ‘origin’ remote when
   cloning a local source didn’t properly account for relative paths.
   (`#4045 <https://github.com/datalad/datalad/issues/4045>`__)

-  Various fixes to file name handling and quoting on Windows.
   (`#4049 <https://github.com/datalad/datalad/issues/4049>`__)
   (`#4050 <https://github.com/datalad/datalad/issues/4050>`__)

-  When cloning failed, error lines were not bubbled up to the user in
   some scenarios.
   (`#4060 <https://github.com/datalad/datalad/issues/4060>`__)

.. _enhancements-and-new-features-21:

Enhancements and new features
-----------------------------

-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   (and thus
   `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__)

   -  now propagates the ``reckless`` mode from the superdataset when
      cloning a dataset into it.
      (`#4037 <https://github.com/datalad/datalad/issues/4037>`__)
   -  gained support for ``ria+<protocol>://`` URLs that point to
      `RIA <http://handbook.datalad.org/en/latest/usecases/datastorage_for_institutions.html>`__
      stores.
      (`#4022 <https://github.com/datalad/datalad/issues/4022>`__)
   -  learned to read “@version” from ``ria+`` URLs and install that
      version of a dataset
      (`#4036 <https://github.com/datalad/datalad/issues/4036>`__) and
      to apply URL rewrites configured through Git’s ``url.*.insteadOf``
      mechanism
      (`#4064 <https://github.com/datalad/datalad/issues/4064>`__).
   -  now copies ``datalad.get.subdataset-source-candidate-<name>``
      options configured within the superdataset into the subdataset.
      This is particularly useful for RIA data stores.
      (`#4073 <https://github.com/datalad/datalad/issues/4073>`__)

-  Archives are now (optionally) handled with 7-Zip instead of
   ``patool``. 7-Zip will be used by default, but ``patool`` will be
   used on non-Windows systems if the ``datalad.runtime.use-patool``
   option is set or the ``7z`` executable is not found.
   (`#4041 <https://github.com/datalad/datalad/issues/4041>`__)

0.12.1 (Jan 15, 2020) – Small bump after big bang
=================================================

Fix some fallout after major release.

.. _fixes-20:

Fixes
-----

-  Revert incorrect relative path adjustment to URLs in
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__.
   (`#3538 <https://github.com/datalad/datalad/issues/3538>`__)

-  Various small fixes to internal helpers and test to run on Windows
   (`#2566 <https://github.com/datalad/datalad/issues/2566>`__)
   (`#2534 <https://github.com/datalad/datalad/issues/2534>`__)

0.12.0 (Jan 11, 2020) – Krakatoa
================================

This release is the result of more than a year of development that
includes fixes for a large number of issues, yielding more robust
behavior across a wider range of use cases, and introduces major changes
in API and behavior. It is the first release for which extensive user
documentation is available in a dedicated `DataLad
Handbook <http://handbook.datalad.org>`__. Python 3 (3.5 and later) is
now the only supported Python flavor.

Major changes 0.12 vs 0.11
--------------------------

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   fully replaces
   `add <http://datalad.readthedocs.io/en/latest/generated/man/datalad-add.html>`__
   (which is obsolete now, and will be removed in a future release).

-  A new Git-annex aware
   `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__
   command enables detailed inspection of dataset hierarchies. The
   previously available
   `diff <http://datalad.readthedocs.io/en/latest/generated/man/datalad-diff.html>`__
   command has been adjusted to match
   `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__
   in argument semantics and behavior.

-  The ability to configure dataset procedures prior and after the
   execution of particular commands has been replaced by a flexible
   “hook” mechanism that is able to run arbitrary DataLad commands
   whenever command results are detected that match a specification.

-  Support of the Windows platform has been improved substantially.
   While performance and feature coverage on Windows still falls behind
   Unix-like systems, typical data consumer use cases, and standard
   dataset operations, such as
   `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__
   and
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__,
   are now working. Basic support for data provenance capture via
   `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   is also functional.

-  Support for Git-annex direct mode repositories has been removed,
   following the end of support in Git-annex itself.

-  The semantics of relative paths in command line arguments have
   changed. Previously, a call
   ``datalad save --dataset /tmp/myds some/relpath`` would have been
   interpreted as saving a file at ``/tmp/myds/some/relpath`` into
   dataset ``/tmp/myds``. This has changed to saving
   ``$PWD/some/relpath`` into dataset ``/tmp/myds``. More generally,
   relative paths are now always treated as relative to the current
   working directory, except for path arguments of
   `Dataset <http://docs.datalad.org/en/latest/generated/datalad.api.Dataset.html>`__
   class instance methods of the Python API. The resulting partial
   duplication of path specifications between path and dataset arguments
   is mitigated by the introduction of two special symbols that can be
   given as dataset argument: ``^`` and ``^.``, which identify the
   topmost superdataset and the closest dataset that contains the
   working directory, respectively.

-  The concept of a “core API” has been introduced. Commands situated in
   the module ``datalad.core`` (such as
   `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__,
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__,
   `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__,
   `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__,
   `diff <http://datalad.readthedocs.io/en/latest/generated/man/datalad-diff.html>`__)
   receive additional scrutiny regarding API and implementation, and are
   meant to provide longer-term stability. Application developers are
   encouraged to preferentially build on these commands.

Major refactoring and deprecations since 0.12.0rc6
--------------------------------------------------

-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   has been incorporated into the growing core API. The public
   ``--alternative-source`` parameter has been removed, and a
   ``clone_dataset`` function with multi-source capabilities is provided
   instead. The ``--reckless`` parameter can now take literal mode
   labels instead of just being a binary flag, but backwards
   compatibility is maintained.

-  The ``get_file_content`` method of ``GitRepo`` was no longer used
   internally or in any known DataLad extensions and has been removed.
   (`#3812 <https://github.com/datalad/datalad/issues/3812>`__)

-  The function ``get_dataset_root`` has been replaced by
   ``rev_get_dataset_root``. ``rev_get_dataset_root`` remains as a
   compatibility alias and will be removed in a later release.
   (`#3815 <https://github.com/datalad/datalad/issues/3815>`__)

-  The ``add_sibling`` module, marked obsolete in v0.6.0, has been
   removed. (`#3871 <https://github.com/datalad/datalad/issues/3871>`__)

-  ``mock`` is no longer declared as an external dependency because we
   can rely on it being in the standard library now that our minimum
   required Python version is 3.5.
   (`#3860 <https://github.com/datalad/datalad/issues/3860>`__)

-  `download-url <https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html>`__
   now requires that directories be indicated with a trailing slash
   rather than interpreting a path as directory when it doesn’t exist.
   This avoids confusion that can result from typos and makes it
   possible to support directory targets that do not exist.
   (`#3854 <https://github.com/datalad/datalad/issues/3854>`__)

-  The ``dataset_only`` argument of the ``ConfigManager`` class is
   deprecated. Use ``source="dataset"`` instead.
   (`#3907 <https://github.com/datalad/datalad/issues/3907>`__)

-  The ``--proc-pre`` and ``--proc-post`` options have been removed, and
   configuration values for ``datalad.COMMAND.proc-pre`` and
   ``datalad.COMMAND.proc-post`` are no longer honored. The new result
   hook mechanism provides an alternative for ``proc-post`` procedures.
   (`#3963 <https://github.com/datalad/datalad/issues/3963>`__)

Fixes since 0.12.0rc6
---------------------

-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   crashed when called with a detached HEAD. It now aborts with an
   informative message.
   (`#3804 <https://github.com/datalad/datalad/issues/3804>`__)

-  Since 0.12.0rc6 the call to
   `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   in
   `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   resulted in a spurious warning.
   (`#3877 <https://github.com/datalad/datalad/issues/3877>`__)

-  `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   crashed if it encountered an annex repository that was marked as
   dead. (`#3892 <https://github.com/datalad/datalad/issues/3892>`__)

-  The update of
   `rerun <https://datalad.readthedocs.io/en/latest/generated/man/datalad-rerun.html>`__
   in v0.12.0rc3 for the rewritten
   `diff <http://datalad.readthedocs.io/en/latest/generated/man/datalad-diff.html>`__
   command didn’t account for a change in the output of ``diff``,
   leading to ``rerun --report`` unintentionally including unchanged
   files in its diff values.
   (`#3873 <https://github.com/datalad/datalad/issues/3873>`__)

-  In 0.12.0rc5
   `download-url <https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html>`__
   was updated to follow the new path handling logic, but its calls to
   AnnexRepo weren’t properly adjusted, resulting in incorrect path
   handling when the called from a dataset subdirectory.
   (`#3850 <https://github.com/datalad/datalad/issues/3850>`__)

-  `download-url <https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html>`__
   called ``git annex addurl`` in a way that failed to register a URL
   when its header didn’t report the content size.
   (`#3911 <https://github.com/datalad/datalad/issues/3911>`__)

-  With Git v2.24.0, saving new subdatasets failed due to a bug in that
   Git release.
   (`#3904 <https://github.com/datalad/datalad/issues/3904>`__)

-  With DataLad configured to stop on failure (e.g., specifying
   ``--on-failure=stop`` from the command line), a failing result record
   was not rendered.
   (`#3863 <https://github.com/datalad/datalad/issues/3863>`__)

-  Installing a subdataset yielded an “ok” status in cases where the
   repository was not yet in its final state, making it ineffective for
   a caller to operate on the repository in response to the result.
   (`#3906 <https://github.com/datalad/datalad/issues/3906>`__)

-  The internal helper for converting git-annex’s JSON output did not
   relay information from the “error-messages” field.
   (`#3931 <https://github.com/datalad/datalad/issues/3931>`__)

-  `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__
   reported relative paths that were confusingly not relative to the
   current directory in some cases. It now always reports absolute
   paths. (`#3959 <https://github.com/datalad/datalad/issues/3959>`__)

-  `diff <http://datalad.readthedocs.io/en/latest/generated/man/datalad-diff.html>`__
   inappropriately reported files as deleted in some cases when ``to``
   was a value other than ``None``.
   (`#3999 <https://github.com/datalad/datalad/issues/3999>`__)

-  An assortment of fixes for Windows compatibility.
   (`#3971 <https://github.com/datalad/datalad/issues/3971>`__)
   (`#3974 <https://github.com/datalad/datalad/issues/3974>`__)
   (`#3975 <https://github.com/datalad/datalad/issues/3975>`__)
   (`#3976 <https://github.com/datalad/datalad/issues/3976>`__)
   (`#3979 <https://github.com/datalad/datalad/issues/3979>`__)

-  Subdatasets installed from a source given by relative path will now
   have this relative path used as ‘url’ in their .gitmodules record,
   instead of an absolute path generated by Git.
   (`#3538 <https://github.com/datalad/datalad/issues/3538>`__)

-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   will now correctly interpret ‘~/…’ paths as absolute path
   specifications.
   (`#3958 <https://github.com/datalad/datalad/issues/3958>`__)

-  `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__
   mistakenly reported a directory as a procedure.
   (`#3793 <https://github.com/datalad/datalad/issues/3793>`__)

-  The cleanup for batched git-annex processes has been improved.
   (`#3794 <https://github.com/datalad/datalad/issues/3794>`__)
   (`#3851 <https://github.com/datalad/datalad/issues/3851>`__)

-  The function for adding a version ID to an AWS S3 URL doesn’t support
   URLs with an “s3://” scheme and raises a ``NotImplementedError``
   exception when it encounters one. The function learned to return a
   URL untouched if an “s3://” URL comes in with a version ID.
   (`#3842 <https://github.com/datalad/datalad/issues/3842>`__)

-  A few spots needed to be adjusted for compatibility with git-annex’s
   new ``--sameas``
   `feature <https://git-annex.branchable.com/tips/multiple_remotes_accessing_the_same_data_store/>`__,
   which allows special remotes to share a data store.
   (`#3856 <https://github.com/datalad/datalad/issues/3856>`__)

-  The ``swallow_logs`` utility failed to capture some log messages due
   to an incompatibility with Python 3.7.
   (`#3935 <https://github.com/datalad/datalad/issues/3935>`__)

-  `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__

   -  crashed if ``--inherit`` was passed but the parent dataset did not
      have a remote with a matching name.
      (`#3954 <https://github.com/datalad/datalad/issues/3954>`__)
   -  configured the wrong pushurl and annexurl values in some cases.
      (`#3955 <https://github.com/datalad/datalad/issues/3955>`__)

Enhancements and new features since 0.12.0rc6
---------------------------------------------

-  By default, datasets cloned from local source paths will now get a
   configured remote for any recursively discoverable ‘origin’ sibling
   that is also available from a local path in order to maximize
   automatic file availability across local annexes.
   (`#3926 <https://github.com/datalad/datalad/issues/3926>`__)

-  The new `result hooks
   mechanism <http://handbook.datalad.org/en/latest/basics/101-145-hooks.html>`__
   allows callers to specify, via local Git configuration values,
   DataLad command calls that will be triggered in response to matching
   result records (i.e., what you see when you call a command with
   ``-f json_pp``).
   (`#3903 <https://github.com/datalad/datalad/issues/3903>`__)

-  The command interface classes learned to use a new ``_examples_``
   attribute to render documentation examples for both the Python and
   command-line API.
   (`#3821 <https://github.com/datalad/datalad/issues/3821>`__)

-  Candidate URLs for cloning a submodule can now be generated based on
   configured templates that have access to various properties of the
   submodule, including its dataset ID.
   (`#3828 <https://github.com/datalad/datalad/issues/3828>`__)

-  DataLad’s check that the user’s Git identity is configured has been
   sped up and now considers the appropriate environment variables as
   well. (`#3807 <https://github.com/datalad/datalad/issues/3807>`__)

-  The ``tag`` method of ``GitRepo`` can now tag revisions other than
   ``HEAD`` and accepts a list of arbitrary ``git tag`` options.
   (`#3787 <https://github.com/datalad/datalad/issues/3787>`__)

-  When ``get`` clones a subdataset and the subdataset’s HEAD differs
   from the commit that is registered in the parent, the active branch
   of the subdataset is moved to the registered commit if the registered
   commit is an ancestor of the subdataset’s HEAD commit. This handling
   has been moved to a more central location within ``GitRepo``, and now
   applies to any ``update_submodule(..., init=True)`` call.
   (`#3831 <https://github.com/datalad/datalad/issues/3831>`__)

-  The output of ``datalad -h`` has been reformatted to improve
   readability.
   (`#3862 <https://github.com/datalad/datalad/issues/3862>`__)

-  `unlock <http://datalad.readthedocs.io/en/latest/generated/man/datalad-unlock.html>`__
   has been sped up.
   (`#3880 <https://github.com/datalad/datalad/issues/3880>`__)

-  `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__
   learned to provide and render more information about discovered
   procedures, including whether the procedure is overridden by another
   procedure with the same base name.
   (`#3960 <https://github.com/datalad/datalad/issues/3960>`__)

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   now (`#3817 <https://github.com/datalad/datalad/issues/3817>`__)

   -  records the active branch in the superdataset when registering a
      new subdataset.
   -  calls ``git annex sync`` when saving a dataset on an adjusted
      branch so that the changes are brought into the mainline branch.

-  `subdatasets <http://datalad.readthedocs.io/en/latest/generated/man/datalad-subdatasets.html>`__
   now aborts when its ``dataset`` argument points to a non-existent
   dataset. (`#3940 <https://github.com/datalad/datalad/issues/3940>`__)

-  `wtf <http://datalad.readthedocs.io/en/latest/generated/man/datalad-wtf.html>`__
   now

   -  reports the dataset ID if the current working directory is
      visiting a dataset.
      (`#3888 <https://github.com/datalad/datalad/issues/3888>`__)
   -  outputs entries deterministically.
      (`#3927 <https://github.com/datalad/datalad/issues/3927>`__)

-  The ``ConfigManager`` class

   -  learned to exclude ``.datalad/config`` as a source of
      configuration values, restricting the sources to standard Git
      configuration files, when called with ``source="local"``.
      (`#3907 <https://github.com/datalad/datalad/issues/3907>`__)
   -  accepts a value of “override” for its ``where`` argument to allow
      Python callers to more convenient override configuration.
      (`#3970 <https://github.com/datalad/datalad/issues/3970>`__)

-  Commands now accept a ``dataset`` value of “^.” as shorthand for “the
   dataset to which the current directory belongs”.
   (`#3242 <https://github.com/datalad/datalad/issues/3242>`__)

0.12.0rc6 (Oct 19, 2019) – some releases are better than the others
===================================================================

bet we will fix some bugs and make a world even a better place.

.. _major-refactoring-and-deprecations-5:

Major refactoring and deprecations
----------------------------------

-  DataLad no longer supports Python 2. The minimum supported version of
   Python is now 3.5.
   (`#3629 <https://github.com/datalad/datalad/issues/3629>`__)

-  Much of the user-focused content at http://docs.datalad.org has been
   removed in favor of more up to date and complete material available
   in the `DataLad Handbook <http://handbook.datalad.org>`__. Going
   forward, the plan is to restrict http://docs.datalad.org to technical
   documentation geared at developers.
   (`#3678 <https://github.com/datalad/datalad/issues/3678>`__)

-  `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   used to allow the caller to specify which dataset(s) to update as a
   ``PATH`` argument or via the the ``--dataset`` option; now only the
   latter is supported. Path arguments only serve to restrict which
   subdataset are updated when operating recursively.
   (`#3700 <https://github.com/datalad/datalad/issues/3700>`__)

-  Result records from a
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
   call no longer have a “state” key.
   (`#3746 <https://github.com/datalad/datalad/issues/3746>`__)

-  `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   and
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
   no longer support operating on independent hierarchies of datasets.
   (`#3700 <https://github.com/datalad/datalad/issues/3700>`__)
   (`#3746 <https://github.com/datalad/datalad/issues/3746>`__)

-  The
   `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   update in 0.12.0rc4 for the new path resolution logic broke the
   handling of inputs and outputs for calls from a subdirectory.
   (`#3747 <https://github.com/datalad/datalad/issues/3747>`__)

-  The ``is_submodule_modified`` method of ``GitRepo`` as well as two
   helper functions in gitrepo.py, ``kwargs_to_options`` and
   ``split_remote_branch``, were no longer used internally or in any
   known DataLad extensions and have been removed.
   (`#3702 <https://github.com/datalad/datalad/issues/3702>`__)
   (`#3704 <https://github.com/datalad/datalad/issues/3704>`__)

-  The ``only_remote`` option of ``GitRepo.is_with_annex`` was not used
   internally or in any known extensions and has been dropped.
   (`#3768 <https://github.com/datalad/datalad/issues/3768>`__)

-  The ``get_tags`` method of ``GitRepo`` used to sort tags by committer
   date. It now sorts them by the tagger date for annotated tags and the
   committer date for lightweight tags.
   (`#3715 <https://github.com/datalad/datalad/issues/3715>`__)

-  The ``rev_resolve_path`` substituted ``resolve_path`` helper.
   (`#3797 <https://github.com/datalad/datalad/issues/3797>`__)

.. _fixes-21:

Fixes
-----

-  Correctly handle relative paths in
   `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__.
   (`#3799 <https://github.com/datalad/datalad/issues/3799>`__)
   (`#3102 <https://github.com/datalad/datalad/issues/3102>`__)

-  Do not erroneously discover directory as a procedure.
   (`#3793 <https://github.com/datalad/datalad/issues/3793>`__)

-  Correctly extract version from manpage to trigger use of manpages for
   ``--help``.
   (`#3798 <https://github.com/datalad/datalad/issues/3798>`__)

-  The ``cfg_yoda`` procedure saved all modifications in the repository
   rather than saving only the files it modified.
   (`#3680 <https://github.com/datalad/datalad/issues/3680>`__)

-  Some spots in the documentation that were supposed appear as two
   hyphens were incorrectly rendered in the HTML output en-dashs.
   (`#3692 <https://github.com/datalad/datalad/issues/3692>`__)

-  `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__,
   `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__,
   and
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   treated paths as relative to the dataset even when the string form
   was given, violating the new path handling rules.
   (`#3749 <https://github.com/datalad/datalad/issues/3749>`__)
   (`#3777 <https://github.com/datalad/datalad/issues/3777>`__)
   (`#3780 <https://github.com/datalad/datalad/issues/3780>`__)

-  Providing the “^” shortcut to ``--dataset`` didn’t work properly when
   called from a subdirectory of a subdataset.
   (`#3772 <https://github.com/datalad/datalad/issues/3772>`__)

-  We failed to propagate some errors from git-annex when working with
   its JSON output.
   (`#3751 <https://github.com/datalad/datalad/issues/3751>`__)

-  With the Python API, callers are allowed to pass a string or list of
   strings as the ``cfg_proc`` argument to
   `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__,
   but the string form was mishandled.
   (`#3761 <https://github.com/datalad/datalad/issues/3761>`__)

-  Incorrect command quoting for SSH calls on Windows that rendered
   basic SSH-related functionality (e.g.,
   `sshrun <http://datalad.readthedocs.io/en/latest/generated/man/datalad-sshrun.html>`__)
   on Windows unusable.
   (`#3688 <https://github.com/datalad/datalad/issues/3688>`__)

-  Annex JSON result handling assumed platform-specific paths on Windows
   instead of the POSIX-style that is happening across all platforms.
   (`#3719 <https://github.com/datalad/datalad/issues/3719>`__)

-  ``path_is_under()`` was incapable of comparing Windows paths with
   different drive letters.
   (`#3728 <https://github.com/datalad/datalad/issues/3728>`__)

.. _enhancements-and-new-features-22:

Enhancements and new features
-----------------------------

-  Provide a collection of “public” ``call_git*`` helpers within GitRepo
   and replace use of “private” and less specific
   ``_git_custom_command`` calls.
   (`#3791 <https://github.com/datalad/datalad/issues/3791>`__)

-  `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__
   gained a ``--report-filetype``. Setting it to “raw” can give a
   performance boost for the price of no longer distinguishing symlinks
   that point to annexed content from other symlinks.
   (`#3701 <https://github.com/datalad/datalad/issues/3701>`__)

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   disables file type reporting by
   `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__
   to improve performance.
   (`#3712 <https://github.com/datalad/datalad/issues/3712>`__)

-  `subdatasets <http://datalad.readthedocs.io/en/latest/generated/man/datalad-subdatasets.html>`__
   (`#3743 <https://github.com/datalad/datalad/issues/3743>`__)

   -  now extends its result records with a ``contains`` field that
      lists which ``contains`` arguments matched a given subdataset.
   -  yields an ‘impossible’ result record when a ``contains`` argument
      wasn’t matched to any of the reported subdatasets.

-  `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   now shows more readable output when cloning fails.
   (`#3775 <https://github.com/datalad/datalad/issues/3775>`__)

-  ``SSHConnection`` now displays a more informative error message when
   it cannot start the ``ControlMaster`` process.
   (`#3776 <https://github.com/datalad/datalad/issues/3776>`__)

-  If the new configuration option ``datalad.log.result-level`` is set
   to a single level, all result records will be logged at that level.
   If you’ve been bothered by DataLad’s double reporting of failures,
   consider setting this to “debug”.
   (`#3754 <https://github.com/datalad/datalad/issues/3754>`__)

-  Configuration values from ``datalad -c OPTION=VALUE ...`` are now
   validated to provide better errors.
   (`#3695 <https://github.com/datalad/datalad/issues/3695>`__)

-  `rerun <https://datalad.readthedocs.io/en/latest/generated/man/datalad-rerun.html>`__
   learned how to handle history with merges. As was already the case
   when cherry picking non-run commits, re-creating merges may results
   in conflicts, and ``rerun`` does not yet provide an interface to let
   the user handle these.
   (`#2754 <https://github.com/datalad/datalad/issues/2754>`__)

-  The ``fsck`` method of ``AnnexRepo`` has been enhanced to expose more
   features of the underlying ``git fsck`` command.
   (`#3693 <https://github.com/datalad/datalad/issues/3693>`__)

-  ``GitRepo`` now has a ``for_each_ref_`` method that wraps
   ``git   for-each-ref``, which is used in various spots that used to
   rely on GitPython functionality.
   (`#3705 <https://github.com/datalad/datalad/issues/3705>`__)

-  Do not pretend to be able to work in optimized (``python -O``) mode,
   crash early with an informative message.
   (`#3803 <https://github.com/datalad/datalad/issues/3803>`__)

0.12.0rc5 (September 04, 2019) – .
==================================

Various fixes and enhancements that bring the 0.12.0 release closer.

.. _major-refactoring-and-deprecations-6:

Major refactoring and deprecations
----------------------------------

-  The two modules below have a new home. The old locations still exist
   as compatibility shims and will be removed in a future release.

   -  ``datalad.distribution.subdatasets`` has been moved to
      ``datalad.local.subdatasets``
      (`#3429 <https://github.com/datalad/datalad/issues/3429>`__)
   -  ``datalad.interface.run`` has been moved to
      ``datalad.core.local.run``
      (`#3444 <https://github.com/datalad/datalad/issues/3444>`__)

-  The ``lock`` method of ``AnnexRepo`` and the ``options`` parameter of
   ``AnnexRepo.unlock`` were unused internally and have been removed.
   (`#3459 <https://github.com/datalad/datalad/issues/3459>`__)

-  The ``get_submodules`` method of ``GitRepo`` has been rewritten
   without GitPython. When the new ``compat`` flag is true (the current
   default), the method returns a value that is compatible with the old
   return value. This backwards-compatible return value and the
   ``compat`` flag will be removed in a future release.
   (`#3508 <https://github.com/datalad/datalad/issues/3508>`__)

-  The logic for resolving relative paths given to a command has changed
   (`#3435 <https://github.com/datalad/datalad/issues/3435>`__). The new
   rule is that relative paths are taken as relative to the dataset only
   if a dataset *instance* is passed by the caller. In all other
   scenarios they’re considered relative to the current directory.

   The main user-visible difference from the command line is that using
   the ``--dataset`` argument does *not* result in relative paths being
   taken as relative to the specified dataset. (The undocumented
   distinction between “rel/path” and “./rel/path” no longer exists.)

   All commands under ``datalad.core`` and ``datalad.local``, as well as
   ``unlock`` and ``addurls``, follow the new logic. The goal is for all
   commands to eventually do so.

.. _fixes-22:

Fixes
-----

-  The function for loading JSON streams wasn’t clever enough to handle
   content that included a Unicode line separator like U2028.
   (`#3524 <https://github.com/datalad/datalad/issues/3524>`__)

-  When
   `unlock <http://datalad.readthedocs.io/en/latest/generated/man/datalad-unlock.html>`__
   was called without an explicit target (i.e., a directory or no paths
   at all), the call failed if any of the files did not have content
   present. (`#3459 <https://github.com/datalad/datalad/issues/3459>`__)

-  ``AnnexRepo.get_content_info`` failed in the rare case of a key
   without size information.
   (`#3534 <https://github.com/datalad/datalad/issues/3534>`__)

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   ignored ``--on-failure`` in its underlying call to
   `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__.
   (`#3470 <https://github.com/datalad/datalad/issues/3470>`__)

-  Calling
   `remove <http://datalad.readthedocs.io/en/latest/generated/man/datalad-remove.html>`__
   with a subdirectory displayed spurious warnings about the
   subdirectory files not existing.
   (`#3586 <https://github.com/datalad/datalad/issues/3586>`__)

-  Our processing of ``git-annex --json`` output mishandled info
   messages from special remotes.
   (`#3546 <https://github.com/datalad/datalad/issues/3546>`__)

-  `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__

   -  didn’t bypass the “existing subdataset” check when called with
      ``--force`` as of 0.12.0rc3
      (`#3552 <https://github.com/datalad/datalad/issues/3552>`__)
   -  failed to register the up-to-date revision of a subdataset when
      ``--cfg-proc`` was used with ``--dataset``
      (`#3591 <https://github.com/datalad/datalad/issues/3591>`__)

-  The base downloader had some error handling that wasn’t compatible
   with Python 3.
   (`#3622 <https://github.com/datalad/datalad/issues/3622>`__)

-  Fixed a number of Unicode py2-compatibility issues.
   (`#3602 <https://github.com/datalad/datalad/issues/3602>`__)

-  ``AnnexRepo.get_content_annexinfo`` did not properly chunk file
   arguments to avoid exceeding the command-line character limit.
   (`#3587 <https://github.com/datalad/datalad/issues/3587>`__)

.. _enhancements-and-new-features-23:

Enhancements and new features
-----------------------------

-  New command ``create-sibling-gitlab`` provides an interface for
   creating a publication target on a GitLab instance.
   (`#3447 <https://github.com/datalad/datalad/issues/3447>`__)

-  `subdatasets <http://datalad.readthedocs.io/en/latest/generated/man/datalad-subdatasets.html>`__
   (`#3429 <https://github.com/datalad/datalad/issues/3429>`__)

   -  now supports path-constrained queries in the same manner as
      commands like ``save`` and ``status``
   -  gained a ``--contains=PATH`` option that can be used to restrict
      the output to datasets that include a specific path.
   -  now narrows the listed subdatasets to those underneath the current
      directory when called with no arguments

-  `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__
   learned to accept a plain ``--annex`` (no value) as shorthand for
   ``--annex basic``.
   (`#3534 <https://github.com/datalad/datalad/issues/3534>`__)

-  The ``.dirty`` property of ``GitRepo`` and ``AnnexRepo`` has been
   sped up. (`#3460 <https://github.com/datalad/datalad/issues/3460>`__)

-  The ``get_content_info`` method of ``GitRepo``, used by ``status``
   and commands that depend on ``status``, now restricts its git calls
   to a subset of files, if possible, for a performance gain in
   repositories with many files.
   (`#3508 <https://github.com/datalad/datalad/issues/3508>`__)

-  Extensions that do not provide a command, such as those that provide
   only metadata extractors, are now supported.
   (`#3531 <https://github.com/datalad/datalad/issues/3531>`__)

-  When calling git-annex with ``--json``, we log standard error at the
   debug level rather than the warning level if a non-zero exit is
   expected behavior.
   (`#3518 <https://github.com/datalad/datalad/issues/3518>`__)

-  `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__
   no longer refuses to create a new dataset in the odd scenario of an
   empty .git/ directory upstairs.
   (`#3475 <https://github.com/datalad/datalad/issues/3475>`__)

-  As of v2.22.0 Git treats a sub-repository on an unborn branch as a
   repository rather than as a directory. Our documentation and tests
   have been updated appropriately.
   (`#3476 <https://github.com/datalad/datalad/issues/3476>`__)

-  `addurls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-addurls.html>`__
   learned to accept a ``--cfg-proc`` value and pass it to its
   ``create`` calls.
   (`#3562 <https://github.com/datalad/datalad/issues/3562>`__)

0.12.0rc4 (May 15, 2019) – the revolution is over
=================================================

With the replacement of the ``save`` command implementation with
``rev-save`` the revolution effort is now over, and the set of key
commands for local dataset operations (``create``, ``run``, ``save``,
``status``, ``diff``) is now complete. This new core API is available
from ``datalad.core.local`` (and also via ``datalad.api``, as any other
command).

.. _major-refactoring-and-deprecations-7:

Major refactoring and deprecations
----------------------------------

-  The ``add`` command is now deprecated. It will be removed in a future
   release.

.. _fixes-23:

Fixes
-----

-  Remove hard-coded dependencies on POSIX path conventions in SSH
   support code
   (`#3400 <https://github.com/datalad/datalad/issues/3400>`__)

-  Emit an ``add`` result when adding a new subdataset during
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   (`#3398 <https://github.com/datalad/datalad/issues/3398>`__)

-  SSH file transfer now actually opens a shared connection, if none
   exists yet
   (`#3403 <https://github.com/datalad/datalad/issues/3403>`__)

.. _enhancements-and-new-features-24:

Enhancements and new features
-----------------------------

-  ``SSHConnection`` now offers methods for file upload and download
   (``get()``, ``put()``. The previous ``copy()`` method only supported
   upload and was discontinued
   (`#3401 <https://github.com/datalad/datalad/issues/3401>`__)

0.12.0rc3 (May 07, 2019) – the revolution continues
===================================================

Continues API consolidation and replaces the ``create`` and ``diff``
command with more performant implementations.

.. _major-refactoring-and-deprecations-8:

Major refactoring and deprecations
----------------------------------

-  The previous ``diff`` command has been replaced by the diff variant
   from the
   `datalad-revolution <http://github.com/datalad/datalad-revolution>`__
   extension.
   (`#3366 <https://github.com/datalad/datalad/issues/3366>`__)

-  ``rev-create`` has been renamed to ``create``, and the previous
   ``create`` has been removed.
   (`#3383 <https://github.com/datalad/datalad/issues/3383>`__)

-  The procedure ``setup_yoda_dataset`` has been renamed to ``cfg_yoda``
   (`#3353 <https://github.com/datalad/datalad/issues/3353>`__).

-  The ``--nosave`` of ``addurls`` now affects only added content, not
   newly created subdatasets
   (`#3259 <https://github.com/datalad/datalad/issues/3259>`__).

-  ``Dataset.get_subdatasets`` (deprecated since v0.9.0) has been
   removed. (`#3336 <https://github.com/datalad/datalad/issues/3336>`__)

-  The ``.is_dirty`` method of ``GitRepo`` and ``AnnexRepo`` has been
   replaced by ``.status`` or, for a subset of cases, the ``.dirty``
   property.
   (`#3330 <https://github.com/datalad/datalad/issues/3330>`__)

-  ``AnnexRepo.get_status`` has been replaced by ``AnnexRepo.status``.
   (`#3330 <https://github.com/datalad/datalad/issues/3330>`__)

.. _fixes-24:

Fixes
-----

-  `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__

   -  reported on directories that contained only ignored files
      (`#3238 <https://github.com/datalad/datalad/issues/3238>`__)
   -  gave a confusing failure when called from a subdataset with an
      explicitly specified dataset argument and “.” as a path
      (`#3325 <https://github.com/datalad/datalad/issues/3325>`__)
   -  misleadingly claimed that the locally present content size was
      zero when ``--annex basic`` was specified
      (`#3378 <https://github.com/datalad/datalad/issues/3378>`__)

-  An informative error wasn’t given when a download provider was
   invalid. (`#3258 <https://github.com/datalad/datalad/issues/3258>`__)

-  Calling ``rev-save PATH`` saved unspecified untracked subdatasets.
   (`#3288 <https://github.com/datalad/datalad/issues/3288>`__)

-  The available choices for command-line options that take values are
   now displayed more consistently in the help output.
   (`#3326 <https://github.com/datalad/datalad/issues/3326>`__)

-  The new pathlib-based code had various encoding issues on Python 2.
   (`#3332 <https://github.com/datalad/datalad/issues/3332>`__)

.. _enhancements-and-new-features-25:

Enhancements and new features
-----------------------------

-  `wtf <http://datalad.readthedocs.io/en/latest/generated/man/datalad-wtf.html>`__
   now includes information about the Python version.
   (`#3255 <https://github.com/datalad/datalad/issues/3255>`__)

-  When operating in an annex repository, checking whether git-annex is
   available is now delayed until a call to git-annex is actually
   needed, allowing systems without git-annex to operate on annex
   repositories in a restricted fashion.
   (`#3274 <https://github.com/datalad/datalad/issues/3274>`__)

-  The ``load_stream`` on helper now supports auto-detection of
   compressed files.
   (`#3289 <https://github.com/datalad/datalad/issues/3289>`__)

-  ``create`` (formerly ``rev-create``)

   -  learned to be speedier by passing a path to ``status``
      (`#3294 <https://github.com/datalad/datalad/issues/3294>`__)
   -  gained a ``--cfg-proc`` (or ``-c``) convenience option for running
      configuration procedures (or more accurately any procedure that
      begins with “cfg\_”) in the newly created dataset
      (`#3353 <https://github.com/datalad/datalad/issues/3353>`__)

-  ``AnnexRepo.set_metadata`` now returns a list while
   ``AnnexRepo.set_metadata_`` returns a generator, a behavior which is
   consistent with the ``add`` and ``add_`` method pair.
   (`#3298 <https://github.com/datalad/datalad/issues/3298>`__)

-  ``AnnexRepo.get_metadata`` now supports batch querying of known annex
   files. Note, however, that callers should carefully validate the
   input paths because the batch call will silently hang if given
   non-annex files.
   (`#3364 <https://github.com/datalad/datalad/issues/3364>`__)

-  `status <http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html>`__

   -  now reports a “bytesize” field for files tracked by Git
      (`#3299 <https://github.com/datalad/datalad/issues/3299>`__)
   -  gained a new option ``eval_subdataset_state`` that controls how
      the subdataset state is evaluated. Depending on the information
      you need, you can select a less expensive mode to make ``status``
      faster.
      (`#3324 <https://github.com/datalad/datalad/issues/3324>`__)
   -  colors deleted files “red”
      (`#3334 <https://github.com/datalad/datalad/issues/3334>`__)

-  Querying repository content is faster due to batching of
   ``git   cat-file`` calls.
   (`#3301 <https://github.com/datalad/datalad/issues/3301>`__)

-  The dataset ID of a subdataset is now recorded in the superdataset.
   (`#3304 <https://github.com/datalad/datalad/issues/3304>`__)

-  ``GitRepo.diffstatus``

   -  now avoids subdataset recursion when the comparison is not with
      the working tree, which substantially improves performance when
      diffing large dataset hierarchies
      (`#3314 <https://github.com/datalad/datalad/issues/3314>`__)
   -  got smarter and faster about labeling a subdataset as “modified”
      (`#3343 <https://github.com/datalad/datalad/issues/3343>`__)

-  ``GitRepo.get_content_info`` now supports disabling the file type
   evaluation, which gives a performance boost in cases where this
   information isn’t needed.
   (`#3362 <https://github.com/datalad/datalad/issues/3362>`__)

-  The XMP metadata extractor now filters based on file name to improve
   its performance.
   (`#3329 <https://github.com/datalad/datalad/issues/3329>`__)

0.12.0rc2 (Mar 18, 2019) – revolution!
======================================

.. _fixes-25:

Fixes
-----

-  ``GitRepo.dirty`` does not report on nested empty directories
   (`#3196 <https://github.com/datalad/datalad/issues/3196>`__).

-  ``GitRepo.save()`` reports results on deleted files.

.. _enhancements-and-new-features-26:

Enhancements and new features
-----------------------------

-  Absorb a new set of core commands from the datalad-revolution
   extension:

   -  ``rev-status``: like ``git status``, but simpler and working with
      dataset hierarchies
   -  ``rev-save``: a 2-in-1 replacement for save and add
   -  ``rev-create``: a ~30% faster create

-  JSON support tools can now read and write compressed files.

0.12.0rc1 (Mar 03, 2019) – to boldly go …
=========================================

.. _major-refactoring-and-deprecations-9:

Major refactoring and deprecations
----------------------------------

-  Discontinued support for git-annex direct-mode (also no longer
   supported upstream).

.. _enhancements-and-new-features-27:

Enhancements and new features
-----------------------------

-  Dataset and Repo object instances are now hashable, and can be
   created based on pathlib Path object instances

-  Imported various additional methods for the Repo classes to query
   information and save changes.

0.11.8 (Oct 11, 2019) – annex-we-are-catching-up
================================================

.. _fixes-26:

Fixes
-----

-  Our internal command runner failed to capture output in some cases.
   (`#3656 <https://github.com/datalad/datalad/issues/3656>`__)
-  Workaround in the tests around python in cPython >= 3.7.5 ‘;’ in the
   filename confusing mimetypes
   (`#3769 <https://github.com/datalad/datalad/issues/3769>`__)
   (`#3770 <https://github.com/datalad/datalad/issues/3770>`__)

.. _enhancements-and-new-features-28:

Enhancements and new features
-----------------------------

-  Prepared for upstream changes in git-annex, including support for the
   latest git-annex

   -  7.20190912 auto-upgrades v5 repositories to v7.
      (`#3648 <https://github.com/datalad/datalad/issues/3648>`__)
      (`#3682 <https://github.com/datalad/datalad/issues/3682>`__)
   -  7.20191009 fixed treatment of (larger/smaller)than in
      .gitattributes
      (`#3765 <https://github.com/datalad/datalad/issues/3765>`__)

-  The ``cfg_text2git`` procedure, as well the ``--text-no-annex``
   option of
   `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__,
   now configure .gitattributes so that empty files are stored in git
   rather than annex.
   (`#3667 <https://github.com/datalad/datalad/issues/3667>`__)

0.11.7 (Sep 06, 2019) – python2-we-still-love-you-but-…
=======================================================

Primarily bugfixes with some optimizations and refactorings.

.. _fixes-27:

Fixes
-----

-  `addurls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-addurls.html>`__

   -  now provides better handling when the URL file isn’t in the
      expected format.
      (`#3579 <https://github.com/datalad/datalad/issues/3579>`__)
   -  always considered a relative file for the URL file argument as
      relative to the current working directory, which goes against the
      convention used by other commands of taking relative paths as
      relative to the dataset argument.
      (`#3582 <https://github.com/datalad/datalad/issues/3582>`__)

-  `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__

   -  hard coded “python” when formatting the command for non-executable
      procedures ending with “.py”. ``sys.executable`` is now used.
      (`#3624 <https://github.com/datalad/datalad/issues/3624>`__)
   -  failed if arguments needed more complicated quoting than simply
      surrounding the value with double quotes. This has been resolved
      for systems that support ``shlex.quote``, but note that on Windows
      values are left unquoted.
      (`#3626 <https://github.com/datalad/datalad/issues/3626>`__)

-  `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   now displays an informative error message if a local path is given to
   ``--url`` but ``--name`` isn’t specified.
   (`#3555 <https://github.com/datalad/datalad/issues/3555>`__)

-  `sshrun <http://datalad.readthedocs.io/en/latest/generated/man/datalad-sshrun.html>`__,
   the command DataLad uses for ``GIT_SSH_COMMAND``, didn’t support all
   the parameters that Git expects it to.
   (`#3616 <https://github.com/datalad/datalad/issues/3616>`__)

-  Fixed a number of Unicode py2-compatibility issues.
   (`#3597 <https://github.com/datalad/datalad/issues/3597>`__)

-  `download-url <https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html>`__
   now will create leading directories of the output path if they do not
   exist (`#3646 <https://github.com/datalad/datalad/issues/3646>`__)

.. _enhancements-and-new-features-29:

Enhancements and new features
-----------------------------

-  The
   `annotate-paths <http://docs.datalad.org/en/latest/generated/man/datalad-annotate-paths.html>`__
   helper now caches subdatasets it has seen to avoid unnecessary calls.
   (`#3570 <https://github.com/datalad/datalad/issues/3570>`__)

-  A repeated configuration query has been dropped from the handling of
   ``--proc-pre`` and ``--proc-post``.
   (`#3576 <https://github.com/datalad/datalad/issues/3576>`__)

-  Calls to ``git annex find`` now use ``--in=.`` instead of the alias
   ``--in=here`` to take advantage of an optimization that git-annex (as
   of the current release, 7.20190730) applies only to the former.
   (`#3574 <https://github.com/datalad/datalad/issues/3574>`__)

-  `addurls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-addurls.html>`__
   now suggests close matches when the URL or file format contains an
   unknown field.
   (`#3594 <https://github.com/datalad/datalad/issues/3594>`__)

-  Shared logic used in the setup.py files of DataLad and its extensions
   has been moved to modules in the \_datalad_build_support/ directory.
   (`#3600 <https://github.com/datalad/datalad/issues/3600>`__)

-  Get ready for upcoming git-annex dropping support for direct mode
   (`#3631 <https://github.com/datalad/datalad/issues/3631>`__)

0.11.6 (Jul 30, 2019) – am I the last of 0.11.x?
================================================

Primarily bug fixes to achieve more robust performance

.. _fixes-28:

Fixes
-----

-  Our tests needed various adjustments to keep up with upstream changes
   in Travis and Git.
   (`#3479 <https://github.com/datalad/datalad/issues/3479>`__)
   (`#3492 <https://github.com/datalad/datalad/issues/3492>`__)
   (`#3493 <https://github.com/datalad/datalad/issues/3493>`__)

-  ``AnnexRepo.is_special_annex_remote`` was too selective in what it
   considered to be a special remote.
   (`#3499 <https://github.com/datalad/datalad/issues/3499>`__)

-  We now provide information about unexpected output when git-annex is
   called with ``--json``.
   (`#3516 <https://github.com/datalad/datalad/issues/3516>`__)

-  Exception logging in the ``__del__`` method of ``GitRepo`` and
   ``AnnexRepo`` no longer fails if the names it needs are no longer
   bound. (`#3527 <https://github.com/datalad/datalad/issues/3527>`__)

-  `addurls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-addurls.html>`__
   botched the construction of subdataset paths that were more than two
   levels deep and failed to create datasets in a reliable,
   breadth-first order.
   (`#3561 <https://github.com/datalad/datalad/issues/3561>`__)

-  Cloning a ``type=git`` special remote showed a spurious warning about
   the remote not being enabled.
   (`#3547 <https://github.com/datalad/datalad/issues/3547>`__)

.. _enhancements-and-new-features-30:

Enhancements and new features
-----------------------------

-  For calls to git and git-annex, we disable automatic garbage
   collection due to past issues with GitPython’s state becoming stale,
   but doing so results in a larger .git/objects/ directory that isn’t
   cleaned up until garbage collection is triggered outside of DataLad.
   Tests with the latest GitPython didn’t reveal any state issues, so
   we’ve re-enabled automatic garbage collection.
   (`#3458 <https://github.com/datalad/datalad/issues/3458>`__)

-  `rerun <https://datalad.readthedocs.io/en/latest/generated/man/datalad-rerun.html>`__
   learned an ``--explicit`` flag, which it relays to its calls to
   [run][[]]. This makes it possible to call ``rerun`` in a dirty
   working tree
   (`#3498 <https://github.com/datalad/datalad/issues/3498>`__).

-  The
   `metadata <http://datalad.readthedocs.io/en/latest/generated/man/datalad-metadata.html>`__
   command aborts earlier if a metadata extractor is unavailable.
   (`#3525 <https://github.com/datalad/datalad/issues/3525>`__)

0.11.5 (May 23, 2019) – stability is not overrated
==================================================

Should be faster and less buggy, with a few enhancements.

.. _fixes-29:

Fixes
-----

-  `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__
   (`#3318 <https://github.com/datalad/datalad/issues/3318>`__)

   -  Siblings are no longer configured with a post-update hook unless a
      web interface is requested with ``--ui``.
   -  ``git submodule update --init`` is no longer called from the
      post-update hook.
   -  If ``--inherit`` is given for a dataset without a superdataset, a
      warning is now given instead of raising an error.

-  The internal command runner failed on Python 2 when its ``env``
   argument had unicode values.
   (`#3332 <https://github.com/datalad/datalad/issues/3332>`__)
-  The safeguard that prevents creating a dataset in a subdirectory that
   already contains tracked files for another repository failed on Git
   versions before 2.14. For older Git versions, we now warn the caller
   that the safeguard is not active.
   (`#3347 <https://github.com/datalad/datalad/issues/3347>`__)
-  A regression introduced in v0.11.1 prevented
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   from committing changes under a subdirectory when the subdirectory
   was specified as a path argument.
   (`#3106 <https://github.com/datalad/datalad/issues/3106>`__)
-  A workaround introduced in v0.11.1 made it possible for
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   to do a partial commit with an annex file that has gone below the
   ``annex.largefiles`` threshold. The logic of this workaround was
   faulty, leading to files being displayed as typechanged in the index
   following the commit.
   (`#3365 <https://github.com/datalad/datalad/issues/3365>`__)
-  The resolve_path() helper confused paths that had a semicolon for SSH
   RIs. (`#3425 <https://github.com/datalad/datalad/issues/3425>`__)
-  The detection of SSH RIs has been improved.
   (`#3425 <https://github.com/datalad/datalad/issues/3425>`__)

.. _enhancements-and-new-features-31:

Enhancements and new features
-----------------------------

-  The internal command runner was too aggressive in its decision to
   sleep. (`#3322 <https://github.com/datalad/datalad/issues/3322>`__)
-  The “INFO” label in log messages now retains the default text color
   for the terminal rather than using white, which only worked well for
   terminals with dark backgrounds.
   (`#3334 <https://github.com/datalad/datalad/issues/3334>`__)
-  A short flag ``-R`` is now available for the ``--recursion-limit``
   flag, a flag shared by several subcommands.
   (`#3340 <https://github.com/datalad/datalad/issues/3340>`__)
-  The authentication logic for
   `create-sibling-github <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-github.html>`__
   has been revamped and now supports 2FA.
   (`#3180 <https://github.com/datalad/datalad/issues/3180>`__)
-  New configuration option ``datalad.ui.progressbar`` can be used to
   configure the default backend for progress reporting (“none”, for
   example, results in no progress bars being shown).
   (`#3396 <https://github.com/datalad/datalad/issues/3396>`__)
-  A new progress backend, available by setting datalad.ui.progressbar
   to “log”, replaces progress bars with a log message upon completion
   of an action.
   (`#3396 <https://github.com/datalad/datalad/issues/3396>`__)
-  DataLad learned to consult the `NO_COLOR <https://no-color.org/>`__
   environment variable and the new ``datalad.ui.color`` configuration
   option when deciding to color output. The default value, “auto”,
   retains the current behavior of coloring output if attached to a TTY
   (`#3407 <https://github.com/datalad/datalad/issues/3407>`__).
-  `clean <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clean.html>`__
   now removes annex transfer directories, which is useful for cleaning
   up failed downloads.
   (`#3374 <https://github.com/datalad/datalad/issues/3374>`__)
-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   no longer refuses to clone into a local path that looks like a URL,
   making its behavior consistent with ``git clone``.
   (`#3425 <https://github.com/datalad/datalad/issues/3425>`__)
-  `wtf <http://datalad.readthedocs.io/en/latest/generated/man/datalad-wtf.html>`__

   -  Learned to fall back to the ``dist`` package if ``platform.dist``,
      which has been removed in the yet-to-be-release Python 3.8, does
      not exist.
      (`#3439 <https://github.com/datalad/datalad/issues/3439>`__)
   -  Gained a ``--section`` option for limiting the output to specific
      sections and a ``--decor`` option, which currently knows how to
      format the output as GitHub’s ``<details>`` section.
      (`#3440 <https://github.com/datalad/datalad/issues/3440>`__)

0.11.4 (Mar 18, 2019) – get-ready
=================================

Largely a bug fix release with a few enhancements

Important
---------

-  0.11.x series will be the last one with support for direct mode of
   `git-annex <http://git-annex.branchable.com/>`__ which is used on
   crippled (no symlinks and no locking) filesystems. v7 repositories
   should be used instead.

.. _fixes-30:

Fixes
-----

-  Extraction of .gz files is broken without p7zip installed. We now
   abort with an informative error in this situation.
   (`#3176 <https://github.com/datalad/datalad/issues/3176>`__)

-  Committing failed in some cases because we didn’t ensure that the
   path passed to ``git read-tree --index-output=...`` resided on the
   same filesystem as the repository.
   (`#3181 <https://github.com/datalad/datalad/issues/3181>`__)

-  Some pointless warnings during metadata aggregation have been
   eliminated.
   (`#3186 <https://github.com/datalad/datalad/issues/3186>`__)

-  With Python 3 the LORIS token authenticator did not properly decode a
   response
   (`#3205 <https://github.com/datalad/datalad/issues/3205>`__).

-  With Python 3 downloaders unnecessarily decoded the response when
   getting the status, leading to an encoding error.
   (`#3210 <https://github.com/datalad/datalad/issues/3210>`__)

-  In some cases, our internal command Runner did not adjust the
   environment’s ``PWD`` to match the current working directory
   specified with the ``cwd`` parameter.
   (`#3215 <https://github.com/datalad/datalad/issues/3215>`__)

-  The specification of the pyliblzma dependency was broken.
   (`#3220 <https://github.com/datalad/datalad/issues/3220>`__)

-  `search <http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html>`__
   displayed an uninformative blank log message in some cases.
   (`#3222 <https://github.com/datalad/datalad/issues/3222>`__)

-  The logic for finding the location of the aggregate metadata DB
   anchored the search path incorrectly, leading to a spurious warning.
   (`#3241 <https://github.com/datalad/datalad/issues/3241>`__)

-  Some progress bars were still displayed when stdout and stderr were
   not attached to a tty.
   (`#3281 <https://github.com/datalad/datalad/issues/3281>`__)

-  Check for stdin/out/err to not be closed before checking for
   ``.isatty``.
   (`#3268 <https://github.com/datalad/datalad/issues/3268>`__)

.. _enhancements-and-new-features-32:

Enhancements and new features
-----------------------------

-  Creating a new repository now aborts if any of the files in the
   directory are tracked by a repository in a parent directory.
   (`#3211 <https://github.com/datalad/datalad/issues/3211>`__)

-  `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   learned to replace the ``{tmpdir}`` placeholder in commands with a
   temporary directory.
   (`#3223 <https://github.com/datalad/datalad/issues/3223>`__)

-  `duecredit <https://github.com/duecredit/duecredit>`__ support has
   been added for citing DataLad itself as well as datasets that an
   analysis uses.
   (`#3184 <https://github.com/datalad/datalad/issues/3184>`__)

-  The ``eval_results`` interface helper unintentionally modified one of
   its arguments.
   (`#3249 <https://github.com/datalad/datalad/issues/3249>`__)

-  A few DataLad constants have been added, changed, or renamed
   (`#3250 <https://github.com/datalad/datalad/issues/3250>`__):

   -  ``HANDLE_META_DIR`` is now ``DATALAD_DOTDIR``. The old name should
      be considered deprecated.
   -  ``METADATA_DIR`` now refers to ``DATALAD_DOTDIR/metadata`` rather
      than ``DATALAD_DOTDIR/meta`` (which is still available as
      ``OLDMETADATA_DIR``).
   -  The new ``DATASET_METADATA_FILE`` refers to
      ``METADATA_DIR/dataset.json``.
   -  The new ``DATASET_CONFIG_FILE`` refers to
      ``DATALAD_DOTDIR/config``.
   -  ``METADATA_FILENAME`` has been renamed to
      ``OLDMETADATA_FILENAME``.

0.11.3 (Feb 19, 2019) – read-me-gently
======================================

Just a few of important fixes and minor enhancements.

.. _fixes-31:

Fixes
-----

-  The logic for setting the maximum command line length now works
   around Python 3.4 returning an unreasonably high value for
   ``SC_ARG_MAX`` on Debian systems.
   (`#3165 <https://github.com/datalad/datalad/issues/3165>`__)

-  DataLad commands that are conceptually “read-only”, such as
   ``datalad ls -L``, can fail when the caller lacks write permissions
   because git-annex tries merging remote git-annex branches to update
   information about availability. DataLad now disables
   ``annex.merge-annex-branches`` in some common “read-only” scenarios
   to avoid these failures.
   (`#3164 <https://github.com/datalad/datalad/issues/3164>`__)

.. _enhancements-and-new-features-33:

Enhancements and new features
-----------------------------

-  Accessing an “unbound” dataset method now automatically imports the
   necessary module rather than requiring an explicit import from the
   Python caller. For example, calling ``Dataset.add`` no longer needs
   to be preceded by ``from datalad.distribution.add import Add`` or an
   import of ``datalad.api``.
   (`#3156 <https://github.com/datalad/datalad/issues/3156>`__)

-  Configuring the new variable ``datalad.ssh.identityfile`` instructs
   DataLad to pass a value to the ``-i`` option of ``ssh``.
   (`#3149 <https://github.com/datalad/datalad/issues/3149>`__)
   (`#3168 <https://github.com/datalad/datalad/issues/3168>`__)

0.11.2 (Feb 07, 2019) – live-long-and-prosper
=============================================

A variety of bugfixes and enhancements

.. _major-refactoring-and-deprecations-10:

Major refactoring and deprecations
----------------------------------

-  All extracted metadata is now placed under git-annex by default.
   Previously files smaller than 20 kb were stored in git.
   (`#3109 <https://github.com/datalad/datalad/issues/3109>`__)
-  The function ``datalad.cmd.get_runner`` has been removed.
   (`#3104 <https://github.com/datalad/datalad/issues/3104>`__)

.. _fixes-32:

Fixes
-----

-  Improved handling of long commands:

   -  The code that inspected ``SC_ARG_MAX`` didn’t check that the
      reported value was a sensible, positive number.
      (`#3025 <https://github.com/datalad/datalad/issues/3025>`__)
   -  More commands that invoke ``git`` and ``git-annex`` with file
      arguments learned to split up the command calls when it is likely
      that the command would fail due to exceeding the maximum supported
      length.
      (`#3138 <https://github.com/datalad/datalad/issues/3138>`__)

-  The ``setup_yoda_dataset`` procedure created a malformed
   .gitattributes line.
   (`#3057 <https://github.com/datalad/datalad/issues/3057>`__)
-  `download-url <https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html>`__
   unnecessarily tried to infer the dataset when ``--no-save`` was
   given. (`#3029 <https://github.com/datalad/datalad/issues/3029>`__)
-  `rerun <https://datalad.readthedocs.io/en/latest/generated/man/datalad-rerun.html>`__
   aborted too late and with a confusing message when a ref specified
   via ``--onto`` didn’t exist.
   (`#3019 <https://github.com/datalad/datalad/issues/3019>`__)
-  `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__:

   -  ``run`` didn’t preserve the current directory prefix (“./”) on
      inputs and outputs, which is problematic if the caller relies on
      this representation when formatting the command.
      (`#3037 <https://github.com/datalad/datalad/issues/3037>`__)
   -  Fixed a number of unicode py2-compatibility issues.
      (`#3035 <https://github.com/datalad/datalad/issues/3035>`__)
      (`#3046 <https://github.com/datalad/datalad/issues/3046>`__)
   -  To proceed with a failed command, the user was confusingly
      instructed to use ``save`` instead of ``add`` even though ``run``
      uses ``add`` underneath.
      (`#3080 <https://github.com/datalad/datalad/issues/3080>`__)

-  Fixed a case where the helper class for checking external modules
   incorrectly reported a module as unknown.
   (`#3051 <https://github.com/datalad/datalad/issues/3051>`__)
-  `add-archive-content <https://datalad.readthedocs.io/en/latest/generated/man/datalad-add-archive-content.html>`__
   mishandled the archive path when the leading path contained a
   symlink. (`#3058 <https://github.com/datalad/datalad/issues/3058>`__)
-  Following denied access, the credential code failed to consider a
   scenario, leading to a type error rather than an appropriate error
   message. (`#3091 <https://github.com/datalad/datalad/issues/3091>`__)
-  Some tests failed when executed from a ``git worktree`` checkout of
   the source repository.
   (`#3129 <https://github.com/datalad/datalad/issues/3129>`__)
-  During metadata extraction, batched annex processes weren’t properly
   terminated, leading to issues on Windows.
   (`#3137 <https://github.com/datalad/datalad/issues/3137>`__)
-  `add <http://datalad.readthedocs.io/en/latest/generated/man/datalad-add.html>`__
   incorrectly handled an “invalid repository” exception when trying to
   add a submodule.
   (`#3141 <https://github.com/datalad/datalad/issues/3141>`__)
-  Pass ``GIT_SSH_VARIANT=ssh`` to git processes to be able to specify
   alternative ports in SSH urls

.. _enhancements-and-new-features-34:

Enhancements and new features
-----------------------------

-  `search <http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html>`__
   learned to suggest closely matching keys if there are no hits.
   (`#3089 <https://github.com/datalad/datalad/issues/3089>`__)
-  `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__

   -  gained a ``--group`` option so that the caller can specify the
      file system group for the repository.
      (`#3098 <https://github.com/datalad/datalad/issues/3098>`__)
   -  now understands SSH URLs that have a port in them (i.e. the
      “ssh://[user@]host.xz[:port]/path/to/repo.git/” syntax mentioned
      in ``man git-fetch``).
      (`#3146 <https://github.com/datalad/datalad/issues/3146>`__)

-  Interface classes can now override the default renderer for
   summarizing results.
   (`#3061 <https://github.com/datalad/datalad/issues/3061>`__)
-  `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__:

   -  ``--input`` and ``--output`` can now be shortened to ``-i`` and
      ``-o``.
      (`#3066 <https://github.com/datalad/datalad/issues/3066>`__)
   -  Placeholders such as “{inputs}” are now expanded in the command
      that is shown in the commit message subject.
      (`#3065 <https://github.com/datalad/datalad/issues/3065>`__)
   -  ``interface.run.run_command`` gained an ``extra_inputs`` argument
      so that wrappers like
      `datalad-container <https://github.com/datalad/datalad-container>`__
      can specify additional inputs that aren’t considered when
      formatting the command string.
      (`#3038 <https://github.com/datalad/datalad/issues/3038>`__)
   -  “–” can now be used to separate options for ``run`` and those for
      the command in ambiguous cases.
      (`#3119 <https://github.com/datalad/datalad/issues/3119>`__)

-  The utilities ``create_tree`` and ``ok_file_has_content`` now support
   “.gz” files.
   (`#3049 <https://github.com/datalad/datalad/issues/3049>`__)
-  The Singularity container for 0.11.1 now uses
   `nd_freeze <https://github.com/neurodebian/neurodebian/blob/master/tools/nd_freeze>`__
   to make its builds reproducible.
-  A
   `publications <https://datalad.readthedocs.io/en/latest/publications.html>`__
   page has been added to the documentation.
   (`#3099 <https://github.com/datalad/datalad/issues/3099>`__)
-  ``GitRepo.set_gitattributes`` now accepts a ``mode`` argument that
   controls whether the .gitattributes file is appended to (default) or
   overwritten.
   (`#3115 <https://github.com/datalad/datalad/issues/3115>`__)
-  ``datalad --help`` now avoids using ``man`` so that the list of
   subcommands is shown.
   (`#3124 <https://github.com/datalad/datalad/issues/3124>`__)

0.11.1 (Nov 26, 2018) – v7-better-than-v6
=========================================

Rushed out bugfix release to stay fully compatible with recent
`git-annex <http://git-annex.branchable.com/>`__ which introduced v7 to
replace v6.

.. _fixes-33:

Fixes
-----

-  `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__:
   be able to install recursively into a dataset
   (`#2982 <https://github.com/datalad/datalad/issues/2982>`__)
-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__:
   be able to commit/save changes whenever files potentially could have
   swapped their storage between git and annex
   (`#1651 <https://github.com/datalad/datalad/issues/1651>`__)
   (`#2752 <https://github.com/datalad/datalad/issues/2752>`__)
   (`#3009 <https://github.com/datalad/datalad/issues/3009>`__)
-  [aggregate-metadata][]:

   -  dataset’s itself is now not “aggregated” if specific paths are
      provided for aggregation
      (`#3002 <https://github.com/datalad/datalad/issues/3002>`__). That
      resolves the issue of ``-r`` invocation aggregating all
      subdatasets of the specified dataset as well
   -  also compare/verify the actual content checksum of aggregated
      metadata while considering subdataset metadata for re-aggregation
      (`#3007 <https://github.com/datalad/datalad/issues/3007>`__)

-  ``annex`` commands are now chunked assuming 50% “safety margin” on
   the maximal command line length. Should resolve crashes while
   operating of too many files at ones
   (`#3001 <https://github.com/datalad/datalad/issues/3001>`__)
-  ``run`` sidecar config processing
   (`#2991 <https://github.com/datalad/datalad/issues/2991>`__)
-  no double trailing period in docs
   (`#2984 <https://github.com/datalad/datalad/issues/2984>`__)
-  correct identification of the repository with symlinks in the paths
   in the tests
   (`#2972 <https://github.com/datalad/datalad/issues/2972>`__)
-  re-evaluation of dataset properties in case of dataset changes
   (`#2946 <https://github.com/datalad/datalad/issues/2946>`__)
-  [text2git][] procedure to use ``ds.repo.set_gitattributes``
   (`#2974 <https://github.com/datalad/datalad/issues/2974>`__)
   (`#2954 <https://github.com/datalad/datalad/issues/2954>`__)
-  Switch to use plain ``os.getcwd()`` if inconsistency with env var
   ``$PWD`` is detected
   (`#2914 <https://github.com/datalad/datalad/issues/2914>`__)
-  Make sure that credential defined in env var takes precedence
   (`#2960 <https://github.com/datalad/datalad/issues/2960>`__)
   (`#2950 <https://github.com/datalad/datalad/issues/2950>`__)

.. _enhancements-and-new-features-35:

Enhancements and new features
-----------------------------

-  `shub://datalad/datalad:git-annex-dev <https://singularity-hub.org/containers/5663/view>`__
   provides a Debian buster Singularity image with build environment for
   `git-annex <http://git-annex.branchable.com/>`__.
   ``tools/bisect-git-annex`` provides a helper for running
   ``git bisect`` on git-annex using that Singularity container
   (`#2995 <https://github.com/datalad/datalad/issues/2995>`__)
-  Added ``.zenodo.json`` for better integration with Zenodo for
   citation
-  `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__
   now provides names and help messages with a custom renderer for
   (`#2993 <https://github.com/datalad/datalad/issues/2993>`__)
-  Documentation: point to
   `datalad-revolution <http://github.com/datalad/datalad-revolution>`__
   extension (prototype of the greater DataLad future)
-  `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__

   -  support injecting of a detached command
      (`#2937 <https://github.com/datalad/datalad/issues/2937>`__)

-  ``annex`` metadata extractor now extracts ``annex.key`` metadata
   record. Should allow now to identify uses of specific files etc
   (`#2952 <https://github.com/datalad/datalad/issues/2952>`__)
-  Test that we can install from http://datasets.datalad.org
-  Proper rendering of ``CommandError`` (e.g. in case of “out of space”
   error) (`#2958 <https://github.com/datalad/datalad/issues/2958>`__)

0.11.0 (Oct 23, 2018) – Soon-to-be-perfect
==========================================

`git-annex <http://git-annex.branchable.com/>`__ 6.20180913 (or later)
is now required - provides a number of fixes for v6 mode operations etc.

.. _major-refactoring-and-deprecations-11:

Major refactoring and deprecations
----------------------------------

-  ``datalad.consts.LOCAL_CENTRAL_PATH`` constant was deprecated in
   favor of ``datalad.locations.default-dataset``
   `configuration <http://docs.datalad.org/en/latest/config.html>`__
   variable (`#2835 <https://github.com/datalad/datalad/issues/2835>`__)

Minor refactoring
-----------------

-  ``"notneeded"`` messages are no longer reported by default results
   renderer
-  `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   no longer shows commit instructions upon command failure when
   ``explicit`` is true and no outputs are specified
   (`#2922 <https://github.com/datalad/datalad/issues/2922>`__)
-  ``get_git_dir`` moved into GitRepo
   (`#2886 <https://github.com/datalad/datalad/issues/2886>`__)
-  ``_gitpy_custom_call`` removed from GitRepo
   (`#2894 <https://github.com/datalad/datalad/issues/2894>`__)
-  ``GitRepo.get_merge_base`` argument is now called ``commitishes``
   instead of ``treeishes``
   (`#2903 <https://github.com/datalad/datalad/issues/2903>`__)

.. _fixes-34:

Fixes
-----

-  `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   should not leave the dataset in non-clean state
   (`#2858 <https://github.com/datalad/datalad/issues/2858>`__) and some
   other enhancements
   (`#2859 <https://github.com/datalad/datalad/issues/2859>`__)
-  Fixed chunking of the long command lines to account for decorators
   and other arguments
   (`#2864 <https://github.com/datalad/datalad/issues/2864>`__)
-  Progress bar should not crash the process on some missing progress
   information
   (`#2891 <https://github.com/datalad/datalad/issues/2891>`__)
-  Default value for ``jobs`` set to be ``"auto"`` (not ``None``) to
   take advantage of possible parallel get if in ``-g`` mode
   (`#2861 <https://github.com/datalad/datalad/issues/2861>`__)
-  `wtf <http://datalad.readthedocs.io/en/latest/generated/man/datalad-wtf.html>`__
   must not crash if ``git-annex`` is not installed etc
   (`#2865 <https://github.com/datalad/datalad/issues/2865>`__),
   (`#2865 <https://github.com/datalad/datalad/issues/2865>`__),
   (`#2918 <https://github.com/datalad/datalad/issues/2918>`__),
   (`#2917 <https://github.com/datalad/datalad/issues/2917>`__)
-  Fixed paths (with spaces etc) handling while reporting annex error
   output (`#2892 <https://github.com/datalad/datalad/issues/2892>`__),
   (`#2893 <https://github.com/datalad/datalad/issues/2893>`__)
-  ``__del__`` should not access ``.repo`` but ``._repo`` to avoid
   attempts for reinstantiation etc
   (`#2901 <https://github.com/datalad/datalad/issues/2901>`__)
-  Fix up submodule ``.git`` right in ``GitRepo.add_submodule`` to avoid
   added submodules being non git-annex friendly
   (`#2909 <https://github.com/datalad/datalad/issues/2909>`__),
   (`#2904 <https://github.com/datalad/datalad/issues/2904>`__)
-  `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__
   (`#2905 <https://github.com/datalad/datalad/issues/2905>`__)

   -  now will provide dataset into the procedure if called within
      dataset
   -  will not crash if procedure is an executable without ``.py`` or
      ``.sh`` suffixes

-  Use centralized ``.gitattributes`` handling while setting annex
   backend (`#2912 <https://github.com/datalad/datalad/issues/2912>`__)
-  ``GlobbedPaths.expand(..., full=True)`` incorrectly returned relative
   paths when called more than once
   (`#2921 <https://github.com/datalad/datalad/issues/2921>`__)

.. _enhancements-and-new-features-36:

Enhancements and new features
-----------------------------

-  Report progress on
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   when installing from “smart” git servers
   (`#2876 <https://github.com/datalad/datalad/issues/2876>`__)
-  Stale/unused ``sth_like_file_has_content`` was removed
   (`#2860 <https://github.com/datalad/datalad/issues/2860>`__)
-  Enhancements to
   `search <http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html>`__
   to operate on “improved” metadata layouts
   (`#2878 <https://github.com/datalad/datalad/issues/2878>`__)
-  Output of ``git annex init`` operation is now logged
   (`#2881 <https://github.com/datalad/datalad/issues/2881>`__)
-  New

   -  ``GitRepo.cherry_pick``
      (`#2900 <https://github.com/datalad/datalad/issues/2900>`__)
   -  ``GitRepo.format_commit``
      (`#2902 <https://github.com/datalad/datalad/issues/2902>`__)

-  `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__
   (`#2905 <https://github.com/datalad/datalad/issues/2905>`__)

   -  procedures can now recursively be discovered in subdatasets as
      well. The uppermost has highest priority
   -  Procedures in user and system locations now take precedence over
      those in datasets.

0.10.3.1 (Sep 13, 2018) – Nothing-is-perfect
============================================

Emergency bugfix to address forgotten boost of version in
``datalad/version.py``.

0.10.3 (Sep 13, 2018) – Almost-perfect
======================================

This is largely a bugfix release which addressed many (but not yet all)
issues of working with git-annex direct and version 6 modes, and
operation on Windows in general. Among enhancements you will see the
support of public S3 buckets (even with periods in their names), ability
to configure new providers interactively, and improved ``egrep`` search
backend.

Although we do not require with this release, it is recommended to make
sure that you are using a recent ``git-annex`` since it also had a
variety of fixes and enhancements in the past months.

.. _fixes-35:

Fixes
-----

-  Parsing of combined short options has been broken since DataLad
   v0.10.0. (`#2710 <https://github.com/datalad/datalad/issues/2710>`__)
-  The ``datalad save`` instructions shown by ``datalad run`` for a
   command with a non-zero exit were incorrectly formatted.
   (`#2692 <https://github.com/datalad/datalad/issues/2692>`__)
-  Decompression of zip files (e.g., through
   ``datalad   add-archive-content``) failed on Python 3.
   (`#2702 <https://github.com/datalad/datalad/issues/2702>`__)
-  Windows:

   -  colored log output was not being processed by colorama.
      (`#2707 <https://github.com/datalad/datalad/issues/2707>`__)
   -  more codepaths now try multiple times when removing a file to deal
      with latency and locking issues on Windows.
      (`#2795 <https://github.com/datalad/datalad/issues/2795>`__)

-  Internal git fetch calls have been updated to work around a GitPython
   ``BadName`` issue.
   (`#2712 <https://github.com/datalad/datalad/issues/2712>`__),
   (`#2794 <https://github.com/datalad/datalad/issues/2794>`__)
-  The progress bar for annex file transferring was unable to handle an
   empty file.
   (`#2717 <https://github.com/datalad/datalad/issues/2717>`__)
-  ``datalad add-readme`` halted when no aggregated metadata was found
   rather than displaying a warning.
   (`#2731 <https://github.com/datalad/datalad/issues/2731>`__)
-  ``datalad rerun`` failed if ``--onto`` was specified and the history
   contained no run commits.
   (`#2761 <https://github.com/datalad/datalad/issues/2761>`__)
-  Processing of a command’s results failed on a result record with a
   missing value (e.g., absent field or subfield in metadata). Now the
   missing value is rendered as “N/A”.
   (`#2725 <https://github.com/datalad/datalad/issues/2725>`__).
-  A couple of documentation links in the “Delineation from related
   solutions” were misformatted.
   (`#2773 <https://github.com/datalad/datalad/issues/2773>`__)
-  With the latest git-annex, several known V6 failures are no longer an
   issue. (`#2777 <https://github.com/datalad/datalad/issues/2777>`__)
-  In direct mode, commit changes would often commit annexed content as
   regular Git files. A new approach fixes this and resolves a good
   number of known failures.
   (`#2770 <https://github.com/datalad/datalad/issues/2770>`__)
-  The reporting of command results failed if the current working
   directory was removed (e.g., after an unsuccessful ``install``).
   (`#2788 <https://github.com/datalad/datalad/issues/2788>`__)
-  When installing into an existing empty directory, ``datalad install``
   removed the directory after a failed clone.
   (`#2788 <https://github.com/datalad/datalad/issues/2788>`__)
-  ``datalad run`` incorrectly handled inputs and outputs for paths with
   spaces and other characters that require shell escaping.
   (`#2798 <https://github.com/datalad/datalad/issues/2798>`__)
-  Globbing inputs and outputs for ``datalad run`` didn’t work correctly
   if a subdataset wasn’t installed.
   (`#2796 <https://github.com/datalad/datalad/issues/2796>`__)
-  Minor (in)compatibility with git 2.19 - (no) trailing period in an
   error message now.
   (`#2815 <https://github.com/datalad/datalad/issues/2815>`__)

.. _enhancements-and-new-features-37:

Enhancements and new features
-----------------------------

-  Anonymous access is now supported for S3 and other downloaders.
   (`#2708 <https://github.com/datalad/datalad/issues/2708>`__)
-  A new interface is available to ease setting up new providers.
   (`#2708 <https://github.com/datalad/datalad/issues/2708>`__)
-  Metadata: changes to egrep mode search
   (`#2735 <https://github.com/datalad/datalad/issues/2735>`__)

   -  Queries in egrep mode are now case-sensitive when the query
      contains any uppercase letters and are case-insensitive otherwise.
      The new mode egrepcs can be used to perform a case-sensitive query
      with all lower-case letters.
   -  Search can now be limited to a specific key.
   -  Multiple queries (list of expressions) are evaluated using AND to
      determine whether something is a hit.
   -  A single multi-field query (e.g., ``pa*:findme``) is a hit, when
      any matching field matches the query.
   -  All matching key/value combinations across all (multi-field)
      queries are reported in the query_matched result field.
   -  egrep mode now shows all hits rather than limiting the results to
      the top 20 hits.

-  The documentation on how to format commands for ``datalad run`` has
   been improved.
   (`#2703 <https://github.com/datalad/datalad/issues/2703>`__)
-  The method for determining the current working directory on Windows
   has been improved.
   (`#2707 <https://github.com/datalad/datalad/issues/2707>`__)
-  ``datalad --version`` now simply shows the version without the
   license. (`#2733 <https://github.com/datalad/datalad/issues/2733>`__)
-  ``datalad export-archive`` learned to export under an existing
   directory via its ``--filename`` option.
   (`#2723 <https://github.com/datalad/datalad/issues/2723>`__)
-  ``datalad export-to-figshare`` now generates the zip archive in the
   root of the dataset unless ``--filename`` is specified.
   (`#2723 <https://github.com/datalad/datalad/issues/2723>`__)
-  After importing ``datalad.api``, ``help(datalad.api)`` (or
   ``datalad.api?`` in IPython) now shows a summary of the available
   DataLad commands.
   (`#2728 <https://github.com/datalad/datalad/issues/2728>`__)
-  Support for using ``datalad`` from IPython has been improved.
   (`#2722 <https://github.com/datalad/datalad/issues/2722>`__)
-  ``datalad wtf`` now returns structured data and reports the version
   of each extension.
   (`#2741 <https://github.com/datalad/datalad/issues/2741>`__)
-  The internal handling of gitattributes information has been improved.
   A user-visible consequence is that ``datalad create   --force`` no
   longer duplicates existing attributes.
   (`#2744 <https://github.com/datalad/datalad/issues/2744>`__)
-  The “annex” metadata extractor can now be used even when no content
   is present.
   (`#2724 <https://github.com/datalad/datalad/issues/2724>`__)
-  The ``add_url_to_file`` method (called by commands like
   ``datalad   download-url`` and ``datalad add-archive-content``)
   learned how to display a progress bar.
   (`#2738 <https://github.com/datalad/datalad/issues/2738>`__)

0.10.2 (Jul 09, 2018) – Thesecuriestever
========================================

Primarily a bugfix release to accommodate recent git-annex release
forbidding file:// and http://localhost/ URLs which might lead to
revealing private files if annex is publicly shared.

.. _fixes-36:

Fixes
-----

-  fixed testing to be compatible with recent git-annex (6.20180626)
-  `download-url <https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html>`__
   will now download to current directory instead of the top of the
   dataset

.. _enhancements-and-new-features-38:

Enhancements and new features
-----------------------------

-  do not quote ~ in URLs to be consistent with quote implementation in
   Python 3.7 which now follows RFC 3986
-  `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   support for user-configured placeholder values
-  documentation on native git-annex metadata support
-  handle 401 errors from LORIS tokens
-  ``yoda`` procedure will instantiate ``README.md``
-  ``--discover`` option added to
   `run-procedure <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html>`__
   to list available procedures

0.10.1 (Jun 17, 2018) – OHBM polish
===================================

The is a minor bugfix release.

.. _fixes-37:

Fixes
-----

-  Be able to use backports.lzma as a drop-in replacement for pyliblzma.
-  Give help when not specifying a procedure name in ``run-procedure``.
-  Abort early when a downloader received no filename.
-  Avoid ``rerun`` error when trying to unlock non-available files.

0.10.0 (Jun 09, 2018) – The Release
===================================

This release is a major leap forward in metadata support.

.. _major-refactoring-and-deprecations-12:

Major refactoring and deprecations
----------------------------------

-  Metadata

   -  Prior metadata provided by datasets under ``.datalad/meta`` is no
      longer used or supported. Metadata must be reaggregated using 0.10
      version
   -  Metadata extractor types are no longer auto-guessed and must be
      explicitly specified in ``datalad.metadata.nativetype`` config
      (could contain multiple values)
   -  Metadata aggregation of a dataset hierarchy no longer updates all
      datasets in the tree with new metadata. Instead, only the target
      dataset is updated. This behavior can be changed via the
      –update-mode switch. The new default prevents needless
      modification of (3rd-party) subdatasets.
   -  Neuroimaging metadata support has been moved into a dedicated
      extension: https://github.com/datalad/datalad-neuroimaging

-  Crawler

   -  moved into a dedicated extension:
      https://github.com/datalad/datalad-crawler

-  ``export_tarball`` plugin has been generalized to ``export_archive``
   and can now also generate ZIP archives.
-  By default a dataset X is now only considered to be a super-dataset
   of another dataset Y, if Y is also a registered subdataset of X.

.. _fixes-38:

Fixes
-----

A number of fixes did not make it into the 0.9.x series:

-  Dynamic configuration overrides via the ``-c`` option were not in
   effect.
-  ``save`` is now more robust with respect to invocation in
   subdirectories of a dataset.
-  ``unlock`` now reports correct paths when running in a dataset
   subdirectory.
-  ``get`` is more robust to path that contain symbolic links.
-  symlinks to subdatasets of a dataset are now correctly treated as a
   symlink, and not as a subdataset
-  ``add`` now correctly saves staged subdataset additions.
-  Running ``datalad save`` in a dataset no longer adds untracked
   content to the dataset. In order to add content a path has to be
   given, e.g. ``datalad save .``
-  ``wtf`` now works reliably with a DataLad that wasn’t installed from
   Git (but, e.g., via pip)
-  More robust URL handling in ``simple_with_archives`` crawler
   pipeline.

.. _enhancements-and-new-features-39:

Enhancements and new features
-----------------------------

-  Support for DataLad extension that can contribute API components from
   3rd-party sources, incl. commands, metadata extractors, and test case
   implementations. See
   https://github.com/datalad/datalad-extension-template for a demo
   extension.
-  Metadata (everything has changed!)

   -  Metadata extraction and aggregation is now supported for datasets
      and individual files.
   -  Metadata query via ``search`` can now discover individual files.
   -  Extracted metadata can now be stored in XZ compressed files, is
      optionally annexed (when exceeding a configurable size threshold),
      and obtained on demand (new configuration option
      ``datalad.metadata.create-aggregate-annex-limit``).
   -  Status and availability of aggregated metadata can now be reported
      via ``metadata --get-aggregates``
   -  New configuration option ``datalad.metadata.maxfieldsize`` to
      exclude too large metadata fields from aggregation.
   -  The type of metadata is no longer guessed during metadata
      extraction. A new configuration option
      ``datalad.metadata.nativetype`` was introduced to enable one or
      more particular metadata extractors for a dataset.
   -  New configuration option
      ``datalad.metadata.store-aggregate-content`` to enable the storage
      of aggregated metadata for dataset content (i.e. file-based
      metadata) in contrast to just metadata describing a dataset as a
      whole.

-  ``search`` was completely reimplemented. It offers three different
   modes now:

   -  ‘egrep’ (default): expression matching in a plain string version
      of metadata
   -  ‘textblob’: search a text version of all metadata using a fully
      featured query language (fast indexing, good for keyword search)
   -  ‘autofield’: search an auto-generated index that preserves
      individual fields of metadata that can be represented in a tabular
      structure (substantial indexing cost, enables the most detailed
      queries of all modes)

-  New extensions:

   -  `addurls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-addurls.html>`__,
      an extension for creating a dataset (and possibly subdatasets)
      from a list of URLs.
   -  export_to_figshare
   -  extract_metadata

-  add_readme makes use of available metadata
-  By default the wtf extension now hides sensitive information, which
   can be included in the output by passing ``--senstive=some`` or
   ``--senstive=all``.
-  Reduced startup latency by only importing commands necessary for a
   particular command line call.
-  `create <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html>`__:

   -  ``-d <parent> --nosave`` now registers subdatasets, when possible.
   -  ``--fake-dates`` configures dataset to use fake-dates

-  `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   now provides a way for the caller to save the result when a command
   has a non-zero exit status.
-  ``datalad rerun`` now has a ``--script`` option that can be used to
   extract previous commands into a file.
-  A DataLad Singularity container is now available on `Singularity
   Hub <https://singularity-hub.org/collections/667>`__.
-  More casts have been embedded in the `use case section of the
   documentation <http://docs.datalad.org/en/docs/usecases/index.html>`__.
-  ``datalad --report-status`` has a new value ‘all’ that can be used to
   temporarily re-enable reporting that was disable by configuration
   settings.

0.9.3 (Mar 16, 2018) – pi+0.02 release
======================================

Some important bug fixes which should improve usability

.. _fixes-39:

Fixes
-----

-  ``datalad-archives`` special remote now will lock on acquiring or
   extracting an archive - this allows for it to be used with -J flag
   for parallel operation
-  relax introduced in 0.9.2 demand on git being configured for datalad
   operation - now we will just issue a warning
-  ``datalad ls`` should now list “authored date” and work also for
   datasets in detached HEAD mode
-  ``datalad save`` will now save original file as well, if file was
   “git mv”ed, so you can now ``datalad run git mv old new`` and have
   changes recorded

.. _enhancements-and-new-features-40:

Enhancements and new features
-----------------------------

-  ``--jobs`` argument now could take ``auto`` value which would decide
   on # of jobs depending on the # of available CPUs. ``git-annex`` >
   6.20180314 is recommended to avoid regression with -J.
-  memoize calls to ``RI`` meta-constructor – should speed up operation
   a bit
-  ``DATALAD_SEED`` environment variable could be used to seed Python
   RNG and provide reproducible UUIDs etc (useful for testing and demos)

0.9.2 (Mar 04, 2018) – it is (again) better than ever
=====================================================

Largely a bugfix release with a few enhancements.

.. _fixes-40:

Fixes
-----

-  Execution of external commands (git) should not get stuck when lots
   of both stdout and stderr output, and should not loose remaining
   output in some cases
-  Config overrides provided in the command line (-c) should now be
   handled correctly
-  Consider more remotes (not just tracking one, which might be none)
   while installing subdatasets
-  Compatibility with git 2.16 with some changed behaviors/annotations
   for submodules
-  Fail ``remove`` if ``annex drop`` failed
-  Do not fail operating on files which start with dash (-)
-  URL unquote paths within S3, URLs and DataLad RIs (///)
-  In non-interactive mode fail if authentication/access fails
-  Web UI:

   -  refactored a little to fix incorrect listing of submodules in
      subdirectories
   -  now auto-focuses on search edit box upon entering the page

-  Assure that extracted from tarballs directories have executable bit
   set

.. _enhancements-and-new-features-41:

Enhancements and new features
-----------------------------

-  A log message and progress bar will now inform if a tarball to be
   downloaded while getting specific files (requires git-annex >
   6.20180206)
-  A dedicated ``datalad rerun`` command capable of rerunning entire
   sequences of previously ``run`` commands. **Reproducibility through
   VCS. Use ``run`` even if not interested in ``rerun``**
-  Alert the user if ``git`` is not yet configured but git operations
   are requested
-  Delay collection of previous ssh connections until it is actually
   needed. Also do not require ‘:’ while specifying ssh host
-  AutomagicIO: Added proxying of isfile, lzma.LZMAFile and io.open
-  Testing:

   -  added DATALAD_DATASETS_TOPURL=http://datasets-tests.datalad.org to
      run tests against another website to not obscure access stats
   -  tests run against temporary HOME to avoid side-effects
   -  better unit-testing of interactions with special remotes

-  CONTRIBUTING.md describes how to setup and use ``git-hub`` tool to
   “attach” commits to an issue making it into a PR
-  DATALAD_USE_DEFAULT_GIT env variable could be used to cause DataLad
   to use default (not the one possibly bundled with git-annex) git
-  Be more robust while handling not supported requests by annex in
   special remotes
-  Use of ``swallow_logs`` in the code was refactored away – less
   mysteries now, just increase logging level
-  ``wtf`` plugin will report more information about environment,
   externals and the system

0.9.1 (Oct 01, 2017) – “DATALAD!”(JBTM)
=======================================

Minor bugfix release

.. _fixes-41:

Fixes
-----

-  Should work correctly with subdatasets named as numbers of bool
   values (requires also GitPython >= 2.1.6)
-  Custom special remotes should work without crashing with git-annex >=
   6.20170924

0.9.0 (Sep 19, 2017) – isn’t it a lucky day even though not a Friday?
=====================================================================

.. _major-refactoring-and-deprecations-13:

Major refactoring and deprecations
----------------------------------

-  the ``files`` argument of
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   has been renamed to ``path`` to be uniform with any other command
-  all major commands now implement more uniform API semantics and
   result reporting. Functionality for modification detection of dataset
   content has been completely replaced with a more efficient
   implementation
-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   now features a ``--transfer-data`` switch that allows for a
   disambiguous specification of whether to publish data – independent
   of the selection which datasets to publish (which is done via their
   paths). Moreover,
   `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   now transfers data before repository content is pushed.

.. _fixes-42:

Fixes
-----

-  `drop <http://datalad.readthedocs.io/en/latest/generated/man/datalad-drop.html>`__
   no longer errors when some subdatasets are not installed
-  `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   will no longer report nothing when a Dataset instance was given as a
   source argument, but rather perform as expected
-  `remove <http://datalad.readthedocs.io/en/latest/generated/man/datalad-remove.html>`__
   doesn’t remove when some files of a dataset could not be dropped
-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__

   -  no longer hides error during a repository push
   -  publish behaves “correctly” for ``--since=`` in considering only
      the differences the last “pushed” state
   -  data transfer handling while publishing with dependencies, to
      github

-  improved robustness with broken Git configuration
-  `search <http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html>`__
   should search for unicode strings correctly and not crash
-  robustify git-annex special remotes protocol handling to allow for
   spaces in the last argument
-  UI credentials interface should now allow to Ctrl-C the entry
-  should not fail while operating on submodules named with numerics
   only or by bool (true/false) names
-  crawl templates should not now override settings for ``largefiles``
   if specified in ``.gitattributes``

.. _enhancements-and-new-features-42:

Enhancements and new features
-----------------------------

-  **Exciting new feature**
   `run <http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html>`__
   command to protocol execution of an external command and rerun
   computation if desired. See
   `screencast <http://datalad.org/features.html#reproducible-science>`__
-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   now uses Git for detecting with sundatasets need to be inspected for
   potential changes, instead of performing a complete traversal of a
   dataset tree
-  `add <http://datalad.readthedocs.io/en/latest/generated/man/datalad-add.html>`__
   looks for changes relative to the last committed state of a dataset
   to discover files to add more efficiently
-  `diff <http://datalad.readthedocs.io/en/latest/generated/man/datalad-diff.html>`__
   can now report untracked files in addition to modified files
-  [uninstall][] will check itself whether a subdataset is properly
   registered in a superdataset, even when no superdataset is given in a
   call
-  `subdatasets <http://datalad.readthedocs.io/en/latest/generated/man/datalad-subdatasets.html>`__
   can now configure subdatasets for exclusion from recursive
   installation (``datalad-recursiveinstall`` submodule configuration
   property)
-  precrafted pipelines of [crawl][] now will not override
   ``annex.largefiles`` setting if any was set within ``.gitattribues``
   (e.g. by ``datalad create --text-no-annex``)
-  framework for screencasts: ``tools/cast*`` tools and sample cast
   scripts under ``doc/casts`` which are published at
   `datalad.org/features.html <http://datalad.org/features.html>`__
-  new `project YouTube
   channel <https://www.youtube.com/channel/UCB8-Zf7D0DSzAsREoIt0Bvw>`__
-  tests failing in direct and/or v6 modes marked explicitly

0.8.1 (Aug 13, 2017) – the best birthday gift
=============================================

Bugfixes

.. _fixes-43:

Fixes
-----

-  Do not attempt to
   `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   a not installed sub-dataset
-  In case of too many files to be specified for
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
   or
   `copy_to <http://docs.datalad.org/en/latest/_modules/datalad/support/annexrepo.html?highlight=%22copy_to%22>`__,
   we will make multiple invocations of underlying git-annex command to
   not overfill command line
-  More robust handling of unicode output in terminals which might not
   support it

.. _enhancements-and-new-features-43:

Enhancements and new features
-----------------------------

-  Ship a copy of numpy.testing to facilitate [test][] without requiring
   numpy as dependency. Also allow to pass to command which test(s) to
   run
-  In
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
   and
   `copy_to <http://docs.datalad.org/en/latest/_modules/datalad/support/annexrepo.html?highlight=%22copy_to%22>`__
   provide actual original requested paths, not the ones we deduced need
   to be transferred, solely for knowing the total

0.8.0 (Jul 31, 2017) – it is better than ever
=============================================

A variety of fixes and enhancements

.. _fixes-44:

Fixes
-----

-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   would now push merged ``git-annex`` branch even if no other changes
   were done
-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   should be able to publish using relative path within SSH URI (git
   hook would use relative paths)
-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   should better tollerate publishing to pure git and ``git-annex``
   special remotes

.. _enhancements-and-new-features-44:

Enhancements and new features
-----------------------------

-  `plugin <http://datalad.readthedocs.io/en/latest/generated/man/datalad-plugin.html>`__
   mechanism came to replace
   `export <http://datalad.readthedocs.io/en/latest/generated/man/datalad-export.html>`__.
   See
   `export_tarball <http://docs.datalad.org/en/latest/generated/datalad.plugin.export_tarball.html>`__
   for the replacement of
   `export <http://datalad.readthedocs.io/en/latest/generated/man/datalad-export.html>`__.
   Now it should be easy to extend datalad’s interface with custom
   functionality to be invoked along with other commands.
-  Minimalistic coloring of the results rendering
-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__/``copy_to``
   got progress bar report now and support of ``--jobs``
-  minor fixes and enhancements to crawler (e.g. support of recursive
   removes)

0.7.0 (Jun 25, 2017) – when it works - it is quite awesome!
===========================================================

New features, refactorings, and bug fixes.

.. _major-refactoring-and-deprecations-14:

Major refactoring and deprecations
----------------------------------

-  `add-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-add-sibling.html>`__
   has been fully replaced by the
   `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   command
-  `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__,
   and
   `unlock <http://datalad.readthedocs.io/en/latest/generated/man/datalad-unlock.html>`__
   have been re-written to support the same common API as most other
   commands

.. _enhancements-and-new-features-45:

Enhancements and new features
-----------------------------

-  `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   can now be used to query and configure a local repository by using
   the sibling name ``here``
-  `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   can now query and set annex preferred content configuration. This
   includes ``wanted`` (as previously supported in other commands), and
   now also ``required``
-  New
   `metadata <http://datalad.readthedocs.io/en/latest/generated/man/datalad-metadata.html>`__
   command to interface with datasets/files
   `meta-data <http://docs.datalad.org/en/latest/cmdline.html#meta-data-handling>`__
-  Documentation for all commands is now built in a uniform fashion
-  Significant parts of the documentation of been updated
-  Instantiate GitPython’s Repo instances lazily

.. _fixes-45:

Fixes
-----

-  API documentation is now rendered properly as HTML, and is easier to
   browse by having more compact pages
-  Closed files left open on various occasions (Popen PIPEs, etc)
-  Restored basic (consumer mode of operation) compatibility with
   Windows OS

0.6.0 (Jun 14, 2017) – German perfectionism
===========================================

This release includes a **huge** refactoring to make code base and
functionality more robust and flexible

-  outputs from API commands could now be highly customized. See
   ``--output-format``, ``--report-status``, ``--report-type``, and
   ``--report-type`` options for
   `datalad <http://docs.datalad.org/en/latest/generated/man/datalad.html>`__
   command.
-  effort was made to refactor code base so that underlying functions
   behave as generators where possible
-  input paths/arguments analysis was redone for majority of the
   commands to provide unified behavior

.. _major-refactoring-and-deprecations-15:

Major refactoring and deprecations
----------------------------------

-  ``add-sibling`` and ``rewrite-urls`` were refactored in favor of new
   `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   command which should be used for siblings manipulations
-  ‘datalad.api.alwaysrender’ config setting/support is removed in favor
   of new outputs processing

.. _fixes-46:

Fixes
-----

-  Do not flush manually git index in pre-commit to avoid “Death by the
   Lock” issue
-  Deployed by
   `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   ``post-update`` hook script now should be more robust (tolerate
   directory names with spaces, etc.)
-  A variety of fixes, see `list of pull requests and issues
   closed <https://github.com/datalad/datalad/milestone/41?closed=1>`__
   for more information

.. _enhancements-and-new-features-46:

Enhancements and new features
-----------------------------

-  new
   `annotate-paths <http://docs.datalad.org/en/latest/generated/man/datalad-annotate-paths.html>`__
   plumbing command to inspect and annotate provided paths. Use
   ``--modified`` to summarize changes between different points in the
   history
-  new
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   plumbing command to provide a subset (install a single dataset from a
   URL) functionality of
   `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
-  new
   `diff <http://datalad.readthedocs.io/en/latest/generated/man/datalad-diff.html>`__
   plumbing command
-  new
   `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   command to list or manipulate siblings
-  new
   `subdatasets <http://datalad.readthedocs.io/en/latest/generated/man/datalad-subdatasets.html>`__
   command to list subdatasets and their properties
-  `drop <http://datalad.readthedocs.io/en/latest/generated/man/datalad-drop.html>`__
   and
   `remove <http://datalad.readthedocs.io/en/latest/generated/man/datalad-remove.html>`__
   commands were refactored
-  ``benchmarks/`` collection of `Airspeed
   velocity <https://github.com/spacetelescope/asv/>`__ benchmarks
   initiated. See reports at http://datalad.github.io/datalad/
-  crawler would try to download a new url multiple times increasing
   delay between attempts. Helps to resolve problems with extended
   crawls of Amazon S3
-  `CRCNS <http://crcns.org>`__ crawler pipeline now also fetches and
   aggregates meta-data for the datasets from datacite
-  overall optimisations to benefit from the aforementioned refactoring
   and improve user-experience
-  a few stub and not (yet) implemented commands (e.g. ``move``) were
   removed from the interface
-  Web frontend got proper coloring for the breadcrumbs and some
   additional caching to speed up interactions. See
   http://datasets.datalad.org
-  Small improvements to the online documentation. See e.g. `summary of
   differences between
   git/git-annex/datalad <http://docs.datalad.org/en/latest/related.html#git-git-annex-datalad>`__

0.5.1 (Mar 25, 2017) – cannot stop the progress
===============================================

A bugfix release

.. _fixes-47:

Fixes
-----

-  `add <http://datalad.readthedocs.io/en/latest/generated/man/datalad-add.html>`__
   was forcing addition of files to annex regardless of settings in
   ``.gitattributes``. Now that decision is left to annex by default
-  ``tools/testing/run_doc_examples`` used to run doc examples as tests,
   fixed up to provide status per each example and not fail at once
-  ``doc/examples``

   -  `3rdparty_analysis_workflow.sh <http://docs.datalad.org/en/latest/generated/examples/3rdparty_analysis_workflow.html>`__
      was fixed up to reflect changes in the API of 0.5.0.

-  progress bars

   -  should no longer crash **datalad** and report correct sizes and
      speeds
   -  should provide progress reports while using Python 3.x

.. _enhancements-and-new-features-47:

Enhancements and new features
-----------------------------

-  ``doc/examples``

   -  `nipype_workshop_dataset.sh <http://docs.datalad.org/en/latest/generated/examples/nipype_workshop_dataset.html>`__
      new example to demonstrate how new super- and sub- datasets were
      established as a part of our datasets collection

0.5.0 (Mar 20, 2017) – it’s huge
================================

This release includes an avalanche of bug fixes, enhancements, and
additions which at large should stay consistent with previous behavior
but provide better functioning. Lots of code was refactored to provide
more consistent code-base, and some API breakage has happened. Further
work is ongoing to standardize output and results reporting
(`#1350 <https://github.com/datalad/datalad/issues/1350>`__)

Most notable changes
--------------------

-  requires `git-annex <http://git-annex.branchable.com/>`__ >=
   6.20161210 (or better even >= 6.20161210 for improved functionality)
-  commands should now operate on paths specified (if any), without
   causing side-effects on other dirty/staged files
-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__

   -  ``-a`` is deprecated in favor of ``-u`` or ``--all-updates`` so
      only changes known components get saved, and no new files
      automagically added
   -  ``-S`` does no longer store the originating dataset in its commit
      message

-  `add <http://datalad.readthedocs.io/en/latest/generated/man/datalad-add.html>`__

   -  can specify commit/save message with ``-m``

-  `add-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-add-sibling.html>`__
   and
   `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__

   -  now take the name of the sibling (remote) as a ``-s`` (``--name``)
      option, not a positional argument
   -  ``--publish-depends`` to setup publishing data and code to
      multiple repositories (e.g. github + webserve) should now be
      functional see `this
      comment <https://github.com/datalad/datalad/issues/335#issuecomment-277240733>`__
   -  got ``--publish-by-default`` to specify what refs should be
      published by default
   -  got ``--annex-wanted``, ``--annex-groupwanted`` and
      ``--annex-group`` settings which would be used to instruct annex
      about preferred content.
      `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
      then will publish data using those settings if ``wanted`` is set.
   -  got ``--inherit`` option to automagically figure out url/wanted
      and other git/annex settings for new remote sub-dataset to be
      constructed

-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__

   -  got ``--skip-failing`` refactored into ``--missing`` option which
      could use new feature of
      `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__
      ``--inherit``

.. _fixes-48:

Fixes
-----

-  More consistent interaction through ssh - all ssh connections go
   through
   `sshrun <http://datalad.readthedocs.io/en/latest/generated/man/datalad-sshrun.html>`__
   shim for a “single point of authentication”, etc.
-  More robust
   `ls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-ls.html>`__
   operation outside of the datasets
-  A number of fixes for direct and v6 mode of annex

.. _enhancements-and-new-features-48:

Enhancements and new features
-----------------------------

-  New
   `drop <http://datalad.readthedocs.io/en/latest/generated/man/datalad-drop.html>`__
   and
   `remove <http://datalad.readthedocs.io/en/latest/generated/man/datalad-remove.html>`__
   commands
-  `clean <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clean.html>`__

   -  got ``--what`` to specify explicitly what cleaning steps to
      perform and now could be invoked with ``-r``

-  ``datalad`` and ``git-annex-remote*`` scripts now do not use
   setuptools entry points mechanism and rely on simple import to
   shorten start up time
-  `Dataset <http://docs.datalad.org/en/latest/generated/datalad.api.Dataset.html>`__
   is also now using `Flyweight
   pattern <https://en.wikipedia.org/wiki/Flyweight_pattern>`__, so the
   same instance is reused for the same dataset
-  progressbars should not add more empty lines

Internal refactoring
--------------------

-  Majority of the commands now go through ``_prep`` for arguments
   validation and pre-processing to avoid recursive invocations

0.4.1 (Nov 10, 2016) – CA release
=================================

Requires now GitPython >= 2.1.0

.. _fixes-49:

Fixes
-----

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__

   -  to not save staged files if explicit paths were provided

-  improved (but not yet complete) support for direct mode
-  `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   to not crash if some sub-datasets are not installed
-  do not log calls to ``git config`` to avoid leakage of possibly
   sensitive settings to the logs

.. _enhancements-and-new-features-49:

Enhancements and new features
-----------------------------

-  New `rfc822-compliant
   metadata <http://docs.datalad.org/en/latest/metadata.html#rfc822-compliant-meta-data>`__
   format
-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__

   -  -S to save the change also within all super-datasets

-  `add <http://datalad.readthedocs.io/en/latest/generated/man/datalad-add.html>`__
   now has progress-bar reporting
-  `create-sibling-github <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-github.html>`__
   to create a :term:``sibling`` of a dataset on github
-  `OpenfMRI <http://openfmri.org>`__ crawler and datasets were enriched
   with URLs to separate files where also available from openfmri s3
   bucket (if upgrading your datalad datasets, you might need to run
   ``git annex enableremote datalad`` to make them available)
-  various enhancements to log messages
-  web interface

   -  populates “install” box first thus making UX better over slower
      connections

0.4 (Oct 22, 2016) – Paris is waiting
=====================================

Primarily it is a bugfix release but because of significant refactoring
of the
`install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
and
`get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
implementation, it gets a new minor release.

.. _fixes-50:

Fixes
-----

-  be able to
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
   or
   `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   while providing paths while being outside of a dataset
-  remote annex datasets get properly initialized
-  robust detection of outdated
   `git-annex <http://git-annex.branchable.com/>`__

.. _enhancements-and-new-features-50:

Enhancements and new features
-----------------------------

-  interface changes

   -  `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
      ``--recursion-limit=existing`` to not recurse into not-installed
      subdatasets
   -  `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
      ``-n`` to possibly install sub-datasets without getting any data
   -  `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
      ``--jobs|-J`` to specify number of parallel jobs for annex
      `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
      call could use (ATM would not work when data comes from archives)

-  more (unit-)testing
-  documentation: see http://docs.datalad.org/en/latest/basics.html for
   basic principles and useful shortcuts in referring to datasets
-  various webface improvements: breadcrumb paths, instructions how to
   install dataset, show version from the tags, etc.

0.3.1 (Oct 1, 2016) – what a wonderful week
===========================================

Primarily bugfixes but also a number of enhancements and core
refactorings

.. _fixes-51:

Fixes
-----

-  do not build manpages and examples during installation to avoid
   problems with possibly previously outdated dependencies
-  `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   can be called on already installed dataset (with ``-r`` or ``-g``)

.. _enhancements-and-new-features-51:

Enhancements and new features
-----------------------------

-  complete overhaul of datalad configuration settings handling (see
   `Configuration
   documentation <http://docs.datalad.org/config.html>`__), so majority
   of the environment. Now uses git format and stores persistent
   configuration settings under ``.datalad/config`` and local within
   ``.git/config`` variables we have used were renamed to match
   configuration names
-  `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__
   does not now by default upload web front-end
-  `export <http://datalad.readthedocs.io/en/latest/generated/man/datalad-export.html>`__
   command with a plug-in interface and ``tarball`` plugin to export
   datasets
-  in Python, ``.api`` functions with rendering of results in command
   line got a \_-suffixed sibling, which would render results as well in
   Python as well (e.g., using ``search_`` instead of ``search`` would
   also render results, not only output them back as Python objects)
-  `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__

   -  ``--jobs`` option (passed to ``annex get``) for parallel downloads
   -  total and per-download (with git-annex >= 6.20160923) progress
      bars (note that if content is to be obtained from an archive, no
      progress will be reported yet)

-  `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   ``--reckless`` mode option
-  `search <http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html>`__

   -  highlights locations and fieldmaps for better readability
   -  supports ``-d^`` or ``-d///`` to point to top-most or centrally
      installed meta-datasets
   -  “complete” paths to the datasets are reported now
   -  ``-s`` option to specify which fields (only) to search

-  various enhancements and small fixes to
   `meta-data <http://docs.datalad.org/en/latest/cmdline.html#meta-data-handling>`__
   handling,
   `ls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-ls.html>`__,
   custom remotes, code-base formatting, downloaders, etc
-  completely switched to ``tqdm`` library (``progressbar`` is no longer
   used/supported)

0.3 (Sep 23, 2016) – winter is coming
=====================================

Lots of everything, including but not limited to

-  enhanced index viewer, as the one on http://datasets.datalad.org
-  initial new data providers support:
   `Kaggle <https://www.kaggle.com>`__,
   `BALSA <http://balsa.wustl.edu>`__,
   `NDA <http://data-archive.nimh.nih.gov>`__,
   `NITRC <https://www.nitrc.org>`__
-  initial `meta-data support and
   management <http://docs.datalad.org/en/latest/cmdline.html#meta-data-handling>`__
-  new and/or improved crawler pipelines for
   `BALSA <http://balsa.wustl.edu>`__, `CRCNS <http://crcns.org>`__,
   `OpenfMRI <http://openfmri.org>`__
-  refactored
   `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   command, now with separate
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
-  some other commands renaming/refactoring (e.g.,
   `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__)
-  datalad
   `search <http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html>`__
   would give you an option to install datalad’s super-dataset under
   ~/datalad if ran outside of a dataset

0.2.3 (Jun 28, 2016) – busy OHBM
--------------------------------

New features and bugfix release

-  support of /// urls to point to http://datasets.datalad.org
-  variety of fixes and enhancements throughout

0.2.2 (Jun 20, 2016) – OHBM we are coming!
------------------------------------------

New feature and bugfix release

-  greatly improved documentation
-  publish command API RFing allows for custom options to annex, and
   uses –to REMOTE for consistent with annex invocation
-  variety of fixes and enhancements throughout

0.2.1 (Jun 10, 2016)
--------------------

-  variety of fixes and enhancements throughout

0.2 (May 20, 2016)
==================

Major RFing to switch from relying on rdf to git native submodules etc

0.1 (Oct 14, 2015)
==================

Release primarily focusing on interface functionality including initial
publishing
