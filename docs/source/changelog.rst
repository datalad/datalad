.. This file is auto-converted from CHANGELOG.md (make update-changelog) -- do not edit

Change log
**********
::

    ____            _             _                   _ 
   |  _ \    __ _  | |_    __ _  | |       __ _    __| |
   | | | |  / _` | | __|  / _` | | |      / _` |  / _` |
   | |_| | | (_| | | |_  | (_| | | |___  | (_| | | (_| |
   |____/   \__,_|  \__|  \__,_| |_____|  \__,_|  \__,_|
                                              Change Log

This is a high level and scarce summary of the changes between releases.
We would recommend to consult log of the `DataLad git
repository <http://github.com/datalad/datalad>`__ for more details.

0.11.5 (May 23, 2019) – stability is not overrated
--------------------------------------------------

Should be faster and less buggy, with a few enhancements.

Fixes
~~~~~

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

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
---------------------------------

Largely a bug fix release with a few enhancements

Important
~~~~~~~~~

-  0.11.x series will be the last one with support for direct mode of
   `git-annex <http://git-annex.branchable.com/>`__ which is used on
   crippled (no symlinks and no locking) filesystems. v7 repositories
   should be used instead.

.. _fixes-1:

Fixes
~~~~~

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

.. _enhancements-and-new-features-1:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
--------------------------------------

Just a few of important fixes and minor enhancements.

.. _fixes-2:

Fixes
~~~~~

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

.. _enhancements-and-new-features-2:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
---------------------------------------------

A variety of bugfixes and enhancements

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  All extracted metadata is now placed under git-annex by default.
   Previously files smaller than 20 kb were stored in git.
   (`#3109 <https://github.com/datalad/datalad/issues/3109>`__)
-  The function ``datalad.cmd.get_runner`` has been removed.
   (`#3104 <https://github.com/datalad/datalad/issues/3104>`__)

.. _fixes-3:

Fixes
~~~~~

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

.. _enhancements-and-new-features-3:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-----------------------------------------

Rushed out bugfix release to stay fully compatible with recent
`git-annex <http://git-annex.branchable.com/>`__ which introduced v7 to
replace v6.

.. _fixes-4:

Fixes
~~~~~

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
   operating ot too many files at ones
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

.. _enhancements-and-new-features-4:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
------------------------------------------

`git-annex <http://git-annex.branchable.com/>`__ 6.20180913 (or later)
is now required - provides a number of fixes for v6 mode operations etc.

.. _major-refactoring-and-deprecations-1:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  ``datalad.consts.LOCAL_CENTRAL_PATH`` constant was deprecated in
   favor of ``datalad.locations.default-dataset``
   `configuration <http://docs.datalad.org/en/latest/config.html>`__
   variable (`#2835 <https://github.com/datalad/datalad/issues/2835>`__)

Minor refactoring
~~~~~~~~~~~~~~~~~

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

.. _fixes-5:

Fixes
~~~~~

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

.. _enhancements-and-new-features-5:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
--------------------------------------------

Emergency bugfix to address forgotten boost of version in
``datalad/version.py``.

0.10.3 (Sep 13, 2018) – Almost-perfect
--------------------------------------

This is largely a bugfix release which addressed many (but not yet all)
issues of working with git-annex direct and version 6 modes, and
operation on Windows in general. Among enhancements you will see the
support of public S3 buckets (even with periods in their names), ability
to configure new providers interactively, and improved ``egrep`` search
backend.

Although we do not require with this release, it is recommended to make
sure that you are using a recent ``git-annex`` since it also had a
variety of fixes and enhancements in the past months.

.. _fixes-6:

Fixes
~~~~~

-  Parsing of combined short options has been broken since DataLad
   v0.10.0. (`#2710 <https://github.com/datalad/datalad/issues/2710>`__)
-  The ``datalad save`` instructions shown by ``datalad run`` for a
   command with a non-zero exit were incorrectly formatted.
   (`#2692 <https://github.com/datalad/datalad/issues/2692>`__)
-  Decompression of zip files (e.g., through
   ``datalad add-archive-content``) failed on Python 3.
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
-  The progess bar for annex file transferring was unable to handle an
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

.. _enhancements-and-new-features-6:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
   A user-visible consequence is that ``datalad create --force`` no
   longer duplicates existing attributes.
   (`#2744 <https://github.com/datalad/datalad/issues/2744>`__)
-  The “annex” metadata extractor can now be used even when no content
   is present.
   (`#2724 <https://github.com/datalad/datalad/issues/2724>`__)
-  The ``add_url_to_file`` method (called by commands like
   ``datalad download-url`` and ``datalad add-archive-content``) learned
   how to display a progress bar.
   (`#2738 <https://github.com/datalad/datalad/issues/2738>`__)

0.10.2 (Jul 09, 2018) – Thesecuriestever
----------------------------------------

Primarily a bugfix release to accommodate recent git-annex release
forbidding file:// and http://localhost/ URLs which might lead to
revealing private files if annex is publicly shared.

.. _fixes-7:

Fixes
~~~~~

-  fixed testing to be compatible with recent git-annex (6.20180626)
-  `download-url <https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html>`__
   will now download to current directory instead of the top of the
   dataset

.. _enhancements-and-new-features-7:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-----------------------------------

The is a minor bugfix release.

.. _fixes-8:

Fixes
~~~~~

-  Be able to use backports.lzma as a drop-in replacement for pyliblzma.
-  Give help when not specifying a procedure name in ``run-procedure``.
-  Abort early when a downloader received no filename.
-  Avoid ``rerun`` error when trying to unlock non-available files.

0.10.0 (Jun 09, 2018) – The Release
-----------------------------------

This release is a major leap forward in metadata support.

.. _major-refactoring-and-deprecations-2:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

.. _fixes-9:

Fixes
~~~~~

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
   given, e.g. ``datalad save .``
-  ``wtf`` now works reliably with a DataLad that wasn’t installed from
   Git (but, e.g., via pip)
-  More robust URL handling in ``simple_with_archives`` crawler
   pipeline.

.. _enhancements-and-new-features-8:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Support for DataLad extension that can contribute API components from
   3rd-party sources, incl. commands, metadata extractors, and test case
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

   -  addurls, an extension for creating a dataset (and possibly
      subdatasets) from a list of URLs.
   -  export_to_figshare
   -  extract_metadata

-  add_readme makes use of available metadata
-  By default the wtf extension now hides sensitive information, which
   can be included in the output by passing ``--senstive=some`` or
   ``--senstive=all``.
-  Reduced startup latency by only importing commands necessary for a
   particular command line call.
-  ``datalad create -d <parent> --nosave`` now registers subdatasets,
   when possible.
-  ``datalad run`` now provides a way for the caller to save the result
   when a command has a non-zero exit status.
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
--------------------------------------

Some important bug fixes which should improve usability

.. _fixes-10:

Fixes
~~~~~

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

.. _enhancements-and-new-features-9:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  ``--jobs`` argument now could take ``auto`` value which would decide
   on # of jobs depending on the # of available CPUs. ``git-annex`` >
   6.20180314 is recommended to avoid regression with -J.
-  memoize calls to ``RI`` meta-constructor – should speed up operation
   a bit
-  ``DATALAD_SEED`` environment variable could be used to seed Python
   RNG and provide reproducible UUIDs etc (useful for testing and demos)

0.9.2 (Mar 04, 2018) – it is (again) better than ever
-----------------------------------------------------

Largely a bugfix release with a few enhancements.

.. _fixes-11:

Fixes
~~~~~

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

.. _enhancements-and-new-features-10:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
---------------------------------------

Minor bugfix release

.. _fixes-12:

Fixes
~~~~~

-  Should work correctly with subdatasets named as numbers of bool
   values (requires also GitPython >= 2.1.6)
-  Custom special remotes should work without crashing with git-annex >=
   6.20170924

0.9.0 (Sep 19, 2017) – isn’t it a lucky day even though not a Friday?
---------------------------------------------------------------------

.. _major-refactoring-and-deprecations-3:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

.. _fixes-13:

Fixes
~~~~~

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

.. _enhancements-and-new-features-11:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
   looks for changes relative to the last commited state of a dataset to
   discover files to add more efficiently
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
---------------------------------------------

Bugfixes

.. _fixes-14:

Fixes
~~~~~

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

.. _enhancements-and-new-features-12:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
---------------------------------------------

A variety of fixes and enhancements

.. _fixes-15:

Fixes
~~~~~

-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   would now push merged ``git-annex`` branch even if no other changes
   were done
-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   should be able to publish using relative path within SSH URI (git
   hook would use relative paths)
-  `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   should better tollerate publishing to pure git and ``git-annex``
   special remotes

.. _enhancements-and-new-features-13:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-----------------------------------------------------------

New features, refactorings, and bug fixes.

.. _major-refactoring-and-deprecations-4:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  `add-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-add-sibling.html>`__
   has been fully replaced by the
   `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   command
-  `create-sibling <http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html>`__,
   and
   `unlock <http://datalad.readthedocs.io/en/latest/generated/man/datalad-unlock.html>`__
   have been re-written to support the same common API as most other
   commands

.. _enhancements-and-new-features-14:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

.. _fixes-16:

Fixes
~~~~~

-  API documentation is now rendered properly as HTML, and is easier to
   browse by having more compact pages
-  Closed files left open on various occasions (Popen PIPEs, etc)
-  Restored basic (consumer mode of operation) compatibility with
   Windows OS

0.6.0 (Jun 14, 2017) – German perfectionism
-------------------------------------------

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

.. _major-refactoring-and-deprecations-5:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  ``add-sibling`` and ``rewrite-urls`` were refactored in favor of new
   `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   command which should be used for siblings manipulations
-  ‘datalad.api.alwaysrender’ config setting/support is removed in favor
   of new outputs processing

.. _fixes-17:

Fixes
~~~~~

-  Do not flush manually git index in pre-commit to avoid “Death by the
   Lock” issue
-  Deployed by
   `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__
   ``post-update`` hook script now should be more robust (tolerate
   directory names with spaces, etc.)
-  A variety of fixes, see `list of pull requests and issues
   closed <https://github.com/datalad/datalad/milestone/41?closed=1>`__
   for more information

.. _enhancements-and-new-features-15:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-  a few stub and not (yet) implemented commands (e.g. ``move``) were
   removed from the interface
-  Web frontend got proper coloring for the breadcrumbs and some
   additional caching to speed up interactions. See
   http://datasets.datalad.org
-  Small improvements to the online documentation. See e.g. `summary of
   differences between
   git/git-annex/datalad <http://docs.datalad.org/en/latest/related.html#git-git-annex-datalad>`__

0.5.1 (Mar 25, 2017) – cannot stop the progress
-----------------------------------------------

A bugfix release

.. _fixes-18:

Fixes
~~~~~

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

.. _enhancements-and-new-features-16:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  ``doc/examples``

   -  `nipype_workshop_dataset.sh <http://docs.datalad.org/en/latest/generated/examples/nipype_workshop_dataset.html>`__
      new example to demonstrate how new super- and sub- datasets were
      established as a part of our datasets collection

0.5.0 (Mar 20, 2017) – it’s huge
--------------------------------

This release includes an avalanche of bug fixes, enhancements, and
additions which at large should stay consistent with previous behavior
but provide better functioning. Lots of code was refactored to provide
more consistent code-base, and some API breakage has happened. Further
work is ongoing to standardize output and results reporting
(`#1350 <https://github.com/datalad/datalad/issues/1350>`__)

Most notable changes
~~~~~~~~~~~~~~~~~~~~

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

.. _fixes-19:

Fixes
~~~~~

-  More consistent interaction through ssh - all ssh connections go
   through
   `sshrun <http://datalad.readthedocs.io/en/latest/generated/man/datalad-sshrun.html>`__
   shim for a “single point of authentication”, etc.
-  More robust
   `ls <http://datalad.readthedocs.io/en/latest/generated/man/datalad-ls.html>`__
   operation outside of the datasets
-  A number of fixes for direct and v6 mode of annex

.. _enhancements-and-new-features-17:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~

-  Majority of the commands now go through ``_prep`` for arguments
   validation and pre-processing to avoid recursive invocations

0.4.1 (Nov 10, 2016) – CA release
---------------------------------

Requires now GitPython >= 2.1.0

.. _fixes-20:

Fixes
~~~~~

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__

   -  to not save staged files if explicit paths were provided

-  improved (but not yet complete) support for direct mode
-  `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   to not crash if some sub-datasets are not installed
-  do not log calls to ``git config`` to avoid leakage of possibly
   sensitive settings to the logs

.. _enhancements-and-new-features-18:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-------------------------------------

Primarily it is a bugfix release but because of significant refactoring
of the
`install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
and
`get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
implementation, it gets a new minor release.

.. _fixes-21:

Fixes
~~~~~

-  be able to
   `get <http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html>`__
   or
   `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   while providing paths while being outside of a dataset
-  remote annex datasets get properly initialized
-  robust detection of outdated
   `git-annex <http://git-annex.branchable.com/>`__

.. _enhancements-and-new-features-19:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-------------------------------------------

Primarily bugfixes but also a number of enhancements and core
refactorings

.. _fixes-22:

Fixes
~~~~~

-  do not build manpages and examples during installation to avoid
   problems with possibly previously outdated dependencies
-  `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   can be called on already installed dataset (with ``-r`` or ``-g``)

.. _enhancements-and-new-features-20:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-------------------------------------

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

New features and bugfix release

-  support of /// urls to point to http://datasets.datalad.org
-  variety of fixes and enhancements throughout

0.2.2 (Jun 20, 2016) – OHBM we are coming!
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

New feature and bugfix release

-  greately improved documentation
-  publish command API RFing allows for custom options to annex, and
   uses –to REMOTE for consistent with annex invocation
-  variety of fixes and enhancements throughout

0.2.1 (Jun 10, 2016)
~~~~~~~~~~~~~~~~~~~~

-  variety of fixes and enhancements throughout

0.2 (May 20, 2016)
------------------

Major RFing to switch from relying on rdf to git native submodules etc

0.1 (Oct 14, 2015)
------------------

Release primarily focusing on interface functionality including initial
publishing
