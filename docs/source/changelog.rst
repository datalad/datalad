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

0.13.6 (December 14, 2020) – .
------------------------------

Fixes
~~~~~

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
   tweaked to hopefully fix issues with runnning DataLad from IPython.
   (`#5106 <https://github.com/datalad/datalad/issues/5106>`__)

-  SSH cleanup wasn’t reliably triggered by the ORA special remote on
   failure, leading to a stall with a particular version of git-annex,
   8.20201103. (This is also resolved on git-annex’s end as of
   8.20201127.)
   (`#5151 <https://github.com/datalad/datalad/issues/5151>`__)

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  The credential helper no longer asks the user to repeat tokens or AWS
   keys. (`#5219 <https://github.com/datalad/datalad/issues/5219>`__)

-  The new option ``datalad.locations.sockets`` controls where Datalad
   stores SSH sockets, allowing users to more easily work around file
   system and path length restrictions.
   (`#5238 <https://github.com/datalad/datalad/issues/5238>`__)

0.13.5 (October 30, 2020) – .
-----------------------------

.. _fixes-1:

Fixes
~~~~~

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

.. _enhancements-and-new-features-1:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
----------------------------

.. _fixes-2:

Fixes
~~~~~

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

.. _enhancements-and-new-features-2:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
   emits more INFO-level log messages.
   (`#4764 <https://github.com/datalad/datalad/issues/4764>`__)

-  The archives are handled with p7zip, if available, since DataLad
   v0.12.0. This implementation now supports .tgz and .tbz2 archives.
   (`#4877 <https://github.com/datalad/datalad/issues/4877>`__)

0.13.3 (August 28, 2020) – .
----------------------------

.. _fixes-3:

Fixes
~~~~~

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

.. _enhancements-and-new-features-3:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  The wrapper functions returned by decorators are now given more
   meaningful names to hopefully make tracebacks easier to digest.
   (`#4834 <https://github.com/datalad/datalad/issues/4834>`__)

0.13.2 (August 10, 2020) – .
----------------------------

Deprecations
~~~~~~~~~~~~

-  The ``allow_quick`` parameter of ``AnnexRepo.file_has_content`` and
   ``AnnexRepo.is_under_annex`` is now ignored and will be removed in a
   later release. This parameter was only relevant for git-annex
   versions before 7.20190912.
   (`#4736 <https://github.com/datalad/datalad/issues/4736>`__)

.. _fixes-4:

Fixes
~~~~~

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
~~~~~~~~~~~~

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
--------------------------

.. _fixes-5:

Fixes
~~~~~

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

.. _enhancements-and-new-features-4:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  ``datalad push`` now avoids unnecessary ``git push`` dry runs and
   pushes all refspecs with a single ``git push`` call rather than
   invoking ``git push`` for each one.
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
--------------------------

A handful of new commands, including ``copy-file``, ``push``, and
``create-sibling-ria``, along with various fixes and enhancements

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

.. _fixes-6:

Fixes
~~~~~

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

.. _enhancements-and-new-features-5:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
   -  “shared-{group|all|…}” that can be used to set up datasets for
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
-------------------------

.. _fixes-7:

Fixes
~~~~~

-  Requesting tailored output (``--output=tailored``) from a command
   with a custom result summary renderer produced repeated output.
   (`#4463 <https://github.com/datalad/datalad/issues/4463>`__)

-  A longstanding regression in argcomplete-based command-line
   completion for Bash has been fixed. You can enable completion by
   configuring a Bash startup file to run
   ``eval "$(register-python-argcomplete datalad)"`` or source DataLad’s
   ``tools/cmdline-completion``. The latter should work for Zsh as well.
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

.. _enhancements-and-new-features-6:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  The resource identifier helper learned to recognize URLs with
   embedded Git transport information, such as
   gcrypt::https://example.com.
   (`#4529 <https://github.com/datalad/datalad/issues/4529>`__)

-  When running non-interactively, a more informative error is now
   signaled when the UI backend, which cannot display a question, is
   asked to do so.
   (`#4553 <https://github.com/datalad/datalad/issues/4553>`__)

0.12.6 (April 23, 2020) – .
---------------------------

.. _major-refactoring-and-deprecations-1:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  The value of ``datalad.support.annexrep.N_AUTO_JOBS`` is no longer
   considered. The variable will be removed in a later release.
   (`#4409 <https://github.com/datalad/datalad/issues/4409>`__)

.. _fixes-8:

Fixes
~~~~~

-  Staring with v0.12.0, ``datalad save`` recorded the current branch of
   a parent dataset as the ``branch`` value in the .gitmodules entry for
   a subdataset. This behavior is problematic for a few reasons and has
   been reverted.
   (`#4375 <https://github.com/datalad/datalad/issues/4375>`__)

-  The default for the ``--jobs`` option, “auto”, instructed DataLad to
   pass a value to git-annex’s ``--jobs`` equal to
   ``min(8, max(3, <number of CPUs>))``, which could lead to issues due
   to the large number of child processes spawned and file descriptors
   opened. To avoid this behavior, ``--jobs=auto`` now results in
   git-annex being called with ``--jobs=1`` by default. Configure the
   new option ``datalad.runtime.max-annex-jobs`` to control the maximum
   value that will be considered when ``--jobs='auto'``.
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

.. _enhancements-and-new-features-7:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
--------------------------------------------------

￼ Fix some bugs and make the world an even better place.

.. _fixes-9:

Fixes
~~~~~

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
---------------------------------

￼ The main purpose of this release is to have one on PyPi that has no
associated wheel to enable a working installation on Windows
(`#4315 <https://github.com/datalad/datalad/issues/4315>`__).

.. _fixes-10:

Fixes
~~~~~

-  The description of the ``log.outputs`` config switch did not keep up
   with code changes and incorrectly stated that the output would be
   logged at the DEBUG level; logging actually happens at a lower level.
   (`#4317 <https://github.com/datalad/datalad/issues/4317>`__)

0.12.3 (March 16, 2020) – .
---------------------------

Updates for compatibility with the latest git-annex, along with a few
miscellaneous fixes

.. _major-refactoring-and-deprecations-2:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  All spots that raised a ``NoDatasetArgumentFound`` exception now
   raise a ``NoDatasetFound`` exception to better reflect the situation:
   it is the *dataset* rather than the *argument* that is not found. For
   compatibility, the latter inherits from the former, but new code
   should prefer the latter.
   (`#4285 <https://github.com/datalad/datalad/issues/4285>`__)

.. _fixes-11:

Fixes
~~~~~

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

.. _enhancements-and-new-features-8:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  The message provided when a command cannot determine what dataset to
   operate on has been improved.
   (`#4285 <https://github.com/datalad/datalad/issues/4285>`__)

-  The “aws-s3” authentication type now allows specifying the host
   through “aws-s3_host”, which was needed to work around an
   authorization error due to a longstanding upstream bug.
   (`#4239 <https://github.com/datalad/datalad/issues/4239>`__)

-  The xmp metadata extractor now recognizes “.wav” files.

0.12.2 (Jan 28, 2020) – Smoothen the ride
-----------------------------------------

Mostly a bugfix release with various robustifications, but also makes
the first step towards versioned dataset installation requests.

.. _major-refactoring-and-deprecations-3:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  The minimum required version for GitPython is now 2.1.12.
   (`#4070 <https://github.com/datalad/datalad/issues/4070>`__)

.. _fixes-12:

Fixes
~~~~~

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

.. _enhancements-and-new-features-9:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-------------------------------------------------

Fix some fallout after major release.

.. _fixes-13:

Fixes
~~~~~

-  Revert incorrect relative path adjustment to URLs in
   `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__.
   (`#3538 <https://github.com/datalad/datalad/issues/3538>`__)

-  Various small fixes to internal helpers and test to run on Windows
   (`#2566 <https://github.com/datalad/datalad/issues/2566>`__)
   (`#2534 <https://github.com/datalad/datalad/issues/2534>`__)

0.12.0 (Jan 11, 2020) – Krakatoa
--------------------------------

This release is the result of more than a year of development that
includes fixes for a large number of issues, yielding more robust
behavior across a wider range of use cases, and introduces major changes
in API and behavior. It is the first release for which extensive user
documentation is available in a dedicated `DataLad
Handbook <http://handbook.datalad.org>`__. Python 3 (3.5 and later) is
now the only supported Python flavor.

Major changes 0.12 vs 0.11
~~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  `clone <http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html>`__
   has been incorporated into the growing core API. The public
   ``--alternative-source`` parameter has been removed, and a
   ``clone_dataset`` function with multi-source capabilities is provided
   instead. The ``--reckless`` parameter can now take literal mode
   labels instead of just beeing a binary flag, but backwards
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
~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-------------------------------------------------------------------

bet we will fix some bugs and make a world even a better place.

.. _major-refactoring-and-deprecations-4:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

.. _fixes-14:

Fixes
~~~~~

-  Correctly handle relative paths in
   `publish <http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html>`__.
   (`#3799 <https://github.com/datalad/datalad/issues/3799>`__)
   (`#3102 <https://github.com/datalad/datalad/issues/3102>`__)

-  Do not errorneously discover directory as a procedure.
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

.. _enhancements-and-new-features-10:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
   ``git for-each-ref``, which is used in various spots that used to
   rely on GitPython functionality.
   (`#3705 <https://github.com/datalad/datalad/issues/3705>`__)

-  Do not pretend to be able to work in optimized (``python -O``) mode,
   crash early with an informative message.
   (`#3803 <https://github.com/datalad/datalad/issues/3803>`__)

0.12.0rc5 (September 04, 2019) – .
----------------------------------

Various fixes and enhancements that bring the 0.12.0 release closer.

.. _major-refactoring-and-deprecations-5:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

.. _fixes-15:

Fixes
~~~~~

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

.. _enhancements-and-new-features-11:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-------------------------------------------------

With the replacement of the ``save`` command implementation with
``rev-save`` the revolution effort is now over, and the set of key
commands for local dataset operations (``create``, ``run``, ``save``,
``status``, ``diff``) is now complete. This new core API is available
from ``datalad.core.local`` (and also via ``datalad.api``, as any other
command). ￼ ### Major refactoring and deprecations

-  The ``add`` command is now deprecated. It will be removed in a future
   release.

.. _fixes-16:

Fixes
~~~~~

-  Remove hard-coded dependencies on POSIX path conventions in SSH
   support code
   (`#3400 <https://github.com/datalad/datalad/issues/3400>`__)

-  Emit an ``add`` result when adding a new subdataset during
   `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__
   (`#3398 <https://github.com/datalad/datalad/issues/3398>`__)

-  SSH file transfer now actually opens a shared connection, if none
   exists yet
   (`#3403 <https://github.com/datalad/datalad/issues/3403>`__)

.. _enhancements-and-new-features-12:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  ``SSHConnection`` now offers methods for file upload and dowload
   (``get()``, ``put()``. The previous ``copy()`` method only supported
   upload and was discontinued
   (`#3401 <https://github.com/datalad/datalad/issues/3401>`__)

0.12.0rc3 (May 07, 2019) – the revolution continues
---------------------------------------------------

￼ Continues API consolidation and replaces the ``create`` and ``diff``
command with more performant implementations.

.. _major-refactoring-and-deprecations-6:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

.. _fixes-17:

Fixes
~~~~~

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

.. _enhancements-and-new-features-13:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
   ``git cat-file`` calls.
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
--------------------------------------

.. _fixes-18:

Fixes
~~~~~

-  ``GitRepo.dirty`` does not report on nested empty directories
   (`#3196 <https://github.com/datalad/datalad/issues/3196>`__).

-  ``GitRepo.save()`` reports results on deleted files.

.. _enhancements-and-new-features-14:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Absorb a new set of core commands from the datalad-revolution
   extension:

   -  ``rev-status``: like ``git status``, but simpler and working with
      dataset hierarchies
   -  ``rev-save``: a 2-in-1 replacement for save and add
   -  ``rev-create``: a ~30% faster create

-  JSON support tools can now read and write compressed files.

0.12.0rc1 (Mar 03, 2019) – to boldly go …
-----------------------------------------

.. _major-refactoring-and-deprecations-7:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Discontinued support for git-annex direct-mode (also no longer
   supported upstream).

.. _enhancements-and-new-features-15:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Dataset and Repo object instances are now hashable, and can be
   created based on pathlib Path object instances

-  Imported various additional methods for the Repo classes to query
   information and save changes.

0.11.8 (Oct 11, 2019) – annex-we-are-catching-up
------------------------------------------------

.. _fixes-19:

Fixes
~~~~~

-  Our internal command runner failed to capture output in some cases.
   (`#3656 <https://github.com/datalad/datalad/issues/3656>`__)
-  Workaround in the tests around python in cPython >= 3.7.5 ‘;’ in the
   filename confusing mimetypes
   (`#3769 <https://github.com/datalad/datalad/issues/3769>`__)
   (`#3770 <https://github.com/datalad/datalad/issues/3770>`__)

.. _enhancements-and-new-features-16:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
-------------------------------------------------------

Primarily bugfixes with some optimizations and refactorings.

.. _fixes-20:

Fixes
~~~~~

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

.. _enhancements-and-new-features-17:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

-  Shared logic used in the setup.py files of Datalad and its extensions
   has been moved to modules in the \_datalad_build_support/ directory.
   (`#3600 <https://github.com/datalad/datalad/issues/3600>`__)

-  Get ready for upcoming git-annex dropping support for direct mode
   (`#3631 <https://github.com/datalad/datalad/issues/3631>`__)

0.11.6 (Jul 30, 2019) – am I the last of 0.11.x?
------------------------------------------------

Primarily bug fixes to achieve more robust performance

.. _fixes-21:

Fixes
~~~~~

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

.. _enhancements-and-new-features-18:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
--------------------------------------------------

Should be faster and less buggy, with a few enhancements.

.. _fixes-22:

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

.. _enhancements-and-new-features-19:

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

.. _fixes-23:

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

.. _enhancements-and-new-features-20:

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

.. _fixes-24:

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

.. _enhancements-and-new-features-21:

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

.. _major-refactoring-and-deprecations-8:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  All extracted metadata is now placed under git-annex by default.
   Previously files smaller than 20 kb were stored in git.
   (`#3109 <https://github.com/datalad/datalad/issues/3109>`__)
-  The function ``datalad.cmd.get_runner`` has been removed.
   (`#3104 <https://github.com/datalad/datalad/issues/3104>`__)

.. _fixes-25:

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

.. _enhancements-and-new-features-22:

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

.. _fixes-26:

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

.. _enhancements-and-new-features-23:

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

.. _major-refactoring-and-deprecations-9:

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

.. _fixes-27:

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

.. _enhancements-and-new-features-24:

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

.. _fixes-28:

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

.. _enhancements-and-new-features-25:

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

.. _fixes-29:

Fixes
~~~~~

-  fixed testing to be compatible with recent git-annex (6.20180626)
-  `download-url <https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html>`__
   will now download to current directory instead of the top of the
   dataset

.. _enhancements-and-new-features-26:

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

.. _fixes-30:

Fixes
~~~~~

-  Be able to use backports.lzma as a drop-in replacement for pyliblzma.
-  Give help when not specifying a procedure name in ``run-procedure``.
-  Abort early when a downloader received no filename.
-  Avoid ``rerun`` error when trying to unlock non-available files.

0.10.0 (Jun 09, 2018) – The Release
-----------------------------------

This release is a major leap forward in metadata support.

.. _major-refactoring-and-deprecations-10:

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

.. _fixes-31:

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
   given, e.g. \ ``datalad save .``
-  ``wtf`` now works reliably with a DataLad that wasn’t installed from
   Git (but, e.g., via pip)
-  More robust URL handling in ``simple_with_archives`` crawler
   pipeline.

.. _enhancements-and-new-features-27:

Enhancements and new features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
--------------------------------------

Some important bug fixes which should improve usability

.. _fixes-32:

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

.. _enhancements-and-new-features-28:

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

.. _fixes-33:

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

.. _enhancements-and-new-features-29:

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

.. _fixes-34:

Fixes
~~~~~

-  Should work correctly with subdatasets named as numbers of bool
   values (requires also GitPython >= 2.1.6)
-  Custom special remotes should work without crashing with git-annex >=
   6.20170924

0.9.0 (Sep 19, 2017) – isn’t it a lucky day even though not a Friday?
---------------------------------------------------------------------

.. _major-refactoring-and-deprecations-11:

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

.. _fixes-35:

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

.. _enhancements-and-new-features-30:

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

.. _fixes-36:

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

.. _enhancements-and-new-features-31:

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

.. _fixes-37:

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

.. _enhancements-and-new-features-32:

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

.. _major-refactoring-and-deprecations-12:

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

.. _enhancements-and-new-features-33:

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

.. _fixes-38:

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

.. _major-refactoring-and-deprecations-13:

Major refactoring and deprecations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  ``add-sibling`` and ``rewrite-urls`` were refactored in favor of new
   `siblings <http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html>`__
   command which should be used for siblings manipulations
-  ‘datalad.api.alwaysrender’ config setting/support is removed in favor
   of new outputs processing

.. _fixes-39:

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

.. _enhancements-and-new-features-34:

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
-  a few stub and not (yet) implemented commands (e.g. ``move``) were
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

.. _fixes-40:

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

.. _enhancements-and-new-features-35:

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

.. _fixes-41:

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

.. _enhancements-and-new-features-36:

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

.. _fixes-42:

Fixes
~~~~~

-  `save <http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html>`__

   -  to not save staged files if explicit paths were provided

-  improved (but not yet complete) support for direct mode
-  `update <http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html>`__
   to not crash if some sub-datasets are not installed
-  do not log calls to ``git config`` to avoid leakage of possibly
   sensitive settings to the logs

.. _enhancements-and-new-features-37:

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

.. _fixes-43:

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

.. _enhancements-and-new-features-38:

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

.. _fixes-44:

Fixes
~~~~~

-  do not build manpages and examples during installation to avoid
   problems with possibly previously outdated dependencies
-  `install <http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html>`__
   can be called on already installed dataset (with ``-r`` or ``-g``)

.. _enhancements-and-new-features-39:

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
