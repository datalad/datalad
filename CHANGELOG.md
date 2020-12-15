     ____            _             _                   _ 
    |  _ \    __ _  | |_    __ _  | |       __ _    __| |
    | | | |  / _` | | __|  / _` | | |      / _` |  / _` |
    | |_| | | (_| | | |_  | (_| | | |___  | (_| | | (_| |
    |____/   \__,_|  \__|  \__,_| |_____|  \__,_|  \__,_|
                                               Change Log

This is a high level and scarce summary of the changes between releases.
We would recommend to consult log of the 
[DataLad git repository](http://github.com/datalad/datalad) for more details.

## 0.13.6 (December 14, 2020) -- .

### Fixes

- An assortment of fixes for Windows compatibility.  ([#5113][]) ([#5119][])
  ([#5125][]) ([#5127][]) ([#5136][]) ([#5201][]) ([#5200][]) ([#5214][])

- Adding a subdataset on a system that defaults to using an adjusted
  branch (i.e. doesn't support symlinks) didn't properly set up the
  submodule URL if the source dataset was not in an adjusted state.
  ([#5127][])

- [push][] failed to push to a remote that did not have an
  `annex-uuid` value in the local `.git/config`.  ([#5148][])

- The default renderer has been improved to avoid a spurious leading
  space, which led to the displayed path being incorrect in some
  cases.  ([#5121][])

- [siblings][] showed an uninformative error message when asked to
  configure an unknown remote.  ([#5146][])

- [drop][] confusingly relayed a suggestion from `git annex drop` to
  use `--force`, an option that does not exist in `datalad drop`.
  ([#5194][])

- [create-sibling-github][] no longer offers user/password
  authentication because it is no longer supported by GitHub.
  ([#5218][])

- The internal command runner's handling of the event loop has been
  tweaked to hopefully fix issues with runnning DataLad from IPython.
  ([#5106][])

- SSH cleanup wasn't reliably triggered by the ORA special remote on
  failure, leading to a stall with a particular version of git-annex,
  8.20201103.  (This is also resolved on git-annex's end as of
  8.20201127.)  ([#5151][])

### Enhancements and new features

- The credential helper no longer asks the user to repeat tokens or
  AWS keys.  ([#5219][])

- The new option `datalad.locations.sockets` controls where Datalad
  stores SSH sockets, allowing users to more easily work around file
  system and path length restrictions.  ([#5238][])

## 0.13.5 (October 30, 2020) -- .

### Fixes

- SSH connection handling has been reworked to fix cloning on Windows.
  A new configuration option, `datalad.ssh.multiplex-connections`,
  defaults to false on Windows.  ([#5042][])

- The ORA special remote and post-clone RIA configuration now provide
  authentication via DataLad's credential mechanism and better
  handling of HTTP status codes.  ([#5025][]) ([#5026][])

- By default, if a git executable is present in the same location as
  git-annex, DataLad modifies `PATH` when running git and git-annex so
  that the bundled git is used.  This logic has been tightened to
  avoid unnecessarily adjusting the path, reducing the cases where the
  adjustment interferes with the local environment, such as special
  remotes in a virtual environment being masked by the system-wide
  variants.  ([#5035][])

- git-annex is now consistently invoked as "git annex" rather than
  "git-annex" to work around failures on Windows.  ([#5001][])

- [push][] called `git annex sync ...` on plain git repositories.
  ([#5051][])

- [save][] in genernal doesn't support registering multiple levels of
  untracked subdatasets, but it can now properly register nested
  subdatasets when all of the subdataset paths are passed explicitly
  (e.g., `datalad save -d. sub-a sub-a/sub-b`).  ([#5049][])

- When called with `--sidecar` and `--explicit`, [run][] didn't save
  the sidecar.  ([#5017][])

- A couple of spots didn't properly quote format fields when combining
  substrings into a format string.  ([#4957][])

- The default credentials configured for `indi-s3` prevented anonymous
  access.  ([#5045][])

### Enhancements and new features

- Messages about suppressed similar results are now rate limited to
  improve performance when there are many similar results coming
  through quickly.  ([#5060][])

- [create-sibling-github][] can now be told to replace an existing
  sibling by passing `--existing=replace`.  ([#5008][])

- Progress bars now react to changes in the terminal's width (requires
  tqdm 2.1 or later).  ([#5057][])


## 0.13.4 (October 6, 2020) -- .

### Fixes

- Ephemeral clones mishandled bare repositories.  ([#4899][])

- The post-clone logic for configuring RIA stores didn't consider
  `https://` URLs.  ([#4977][])

- DataLad custom remotes didn't escape newlines in messages sent to
  git-annex.  ([#4926][])

- The datalad-archives special remote incorrectly treated file names
  as percent-encoded.  ([#4953][])

- The result handler didn't properly escape "%" when constructing its
  message template.  ([#4953][])

- In v0.13.0, the tailored rendering for specific subtypes of external
  command failures (e.g., "out of space" or "remote not available")
  was unintentionally switched to the default rendering.  ([#4966][])

- Various fixes and updates for the NDA authenticator.  ([#4824][])

- The helper for getting a versioned S3 URL did not support anonymous
  access or buckets with "." in their name.  ([#4985][])

- Several issues with the handling of S3 credentials and token
  expiration have been addressed.  ([#4927][]) ([#4931][]) ([#4952][])

### Enhancements and new features

- A warning is now given if the detected Git is below v2.13.0 to let
  users that run into problems know that their Git version is likely
  the culprit.  ([#4866][])

- A fix to [push][] in v0.13.2 introduced a regression that surfaces
  when `push.default` is configured to "matching" and prevents the
  git-annex branch from being pushed.  Note that, as part of the fix,
  the current branch is now always pushed even when it wouldn't be
  based on the configured refspec or `push.default` value. ([#4896][])

- [publish][]
  - now allows spelling the empty string value of `--since=` as `^`
    for consistency with [push][].  ([#4683][])
  - compares a revision given to `--since=` with `HEAD` rather than
    the working tree to speed up the operation.  ([#4448][])

- [rerun][] emits more INFO-level log messages.  ([#4764][])

- The archives are handled with p7zip, if available, since DataLad
  v0.12.0.  This implementation now supports .tgz and .tbz2 archives.
  ([#4877][])


## 0.13.3 (August 28, 2020) -- .

### Fixes

- Work around a Python bug that led to our asyncio-based command
  runner intermittently failing to capture the output of commands that
  exit very quickly.  ([#4835][])

- [push][] displayed an overestimate of the transfer size when
  multiple files pointed to the same key.  ([#4821][])

- When [download-url][] calls `git annex addurl`, it catches and
  reports any failures rather than crashing.  A change in v0.12.0
  broke this handling in a particular case.  ([#4817][])

### Enhancements and new features

- The wrapper functions returned by decorators are now given more
  meaningful names to hopefully make tracebacks easier to digest.
  ([#4834][])


## 0.13.2 (August 10, 2020) -- .

### Deprecations

- The `allow_quick` parameter of `AnnexRepo.file_has_content` and
  `AnnexRepo.is_under_annex` is now ignored and will be removed in a
  later release.  This parameter was only relevant for git-annex
  versions before 7.20190912.  ([#4736][])

### Fixes

- Updates for compatibility with recent git and git-annex releases.
  ([#4746][]) ([#4760][]) ([#4684][])

- [push][] didn't sync the git-annex branch when `--data=nothing` was
  specified.  ([#4786][])

- The `datalad.clone.reckless` configuration wasn't stored in
  non-annex datasets, preventing the values from being inherited by
  annex subdatasets.  ([#4749][])

- Running the post-update hook installed by `create-sibling --ui`
  could overwrite web log files from previous runs in the unlikely
  event that the hook was executed multiple times in the same second.
  ([#4745][])

- [clone][] inspected git's standard error in a way that could cause
  an attribute error.  ([#4775][])

- When cloning a repository whose `HEAD` points to a branch without
  commits, [clone][] tries to find a more useful branch to check out.
  It unwisely considered adjusted branches.  ([#4792][])

- Since v0.12.0, `SSHManager.close` hasn't closed connections when the
  `ctrl_path` argument was explicitly given.  ([#4757][])

- When working in a dataset in which `git annex init` had not yet been
  called, the `file_has_content` and `is_under_annex` methods of
  `AnnexRepo` incorrectly took the "allow quick" code path on file
  systems that did not support it ([#4736][])

### Enhancements

- [create][] now assigns version 4 (random) UUIDs instead of version 1
  UUIDs that encode the time and hardware address.  ([#4790][])

- The documentation for [create][] now does a better job of describing
  the interaction between `--dataset` and `PATH`.  ([#4763][])

- The `format_commit` and `get_hexsha` methods of `GitRepo` have been
  sped up.  ([#4807][]) ([#4806][])

- A better error message is now shown when the `^` or `^.` shortcuts
  for `--dataset` do not resolve to a dataset.  ([#4759][])

- A more helpful error message is now shown if a caller tries to
  download an `ftp://` link but does not have `request_ftp` installed.
  ([#4788][])

- [clone][] now tries harder to get up-to-date availability
  information after auto-enabling `type=git` special remotes.  ([#2897][])


## 0.13.1 (July 17, 2020) -- .

### Fixes

- Cloning a subdataset should inherit the parent's
  `datalad.clone.reckless` value, but that did not happen when cloning
  via `datalad get` rather than `datalad install` or `datalad clone`.
  ([#4657][])

- The default result renderer crashed when the result did not have a
  `path` key.  ([#4666][]) ([#4673][])

- `datalad push` didn't show information about `git push` errors when
  the output was not in the format that it expected.  ([#4674][])

- `datalad push` silently accepted an empty string for `--since` even
  though it is an invalid value.  ([#4682][])

- Our JavaScript testing setup on Travis grew stale and has now been
  updated.  (Thanks to Xiao Gui.)  ([#4687][])

- The new class for running Git commands (added in v0.13.0) ignored
  any changes to the process environment that occurred after
  instantiation.  ([#4703][])

### Enhancements and new features

- `datalad push` now avoids unnecessary `git push` dry runs and pushes
  all refspecs with a single `git push` call rather than invoking `git
  push` for each one.  ([#4692][]) ([#4675][])

- The readability of SSH error messages has been improved.  ([#4729][])

- `datalad.support.annexrepo` avoids calling
  `datalad.utils.get_linux_distribution` at import time and caches the
  result once it is called because, as of Python 3.8, the function
  uses `distro` underneath, adding noticeable overhead.  ([#4696][])

  Third-party code should be updated to use `get_linux_distribution`
  directly in the unlikely event that the code relied on the
  import-time call to `get_linux_distribution` setting the
  `linux_distribution_name`, `linux_distribution_release`, or
  `on_debian_wheezy` attributes in `datalad.utils.


## 0.13.0 (June 23, 2020) -- .

A handful of new commands, including `copy-file`, `push`, and
`create-sibling-ria`, along with various fixes and enhancements

### Major refactoring and deprecations

- The `no_annex` parameter of [create][], which is exposed in the
  Python API but not the command line, is deprecated and will be
  removed in a later release.  Use the new `annex` argument instead,
  flipping the value.  Command-line callers that use `--no-annex` are
  unaffected.  ([#4321][])

- `datalad add`, which was deprecated in 0.12.0, has been removed.
  ([#4158][]) ([#4319][])

- The following `GitRepo` and `AnnexRepo` methods have been removed:
  `get_changed_files`, `get_missing_files`, and `get_deleted_files`.
  ([#4169][]) ([#4158][])

- The `get_branch_commits` method of `GitRepo` and `AnnexRepo` has
  been renamed to `get_branch_commits_`.  ([#3834][])

- The custom `commit` method of `AnnexRepo` has been removed, and
  `AnnexRepo.commit` now resolves to the parent method,
  `GitRepo.commit`.  ([#4168][])

- GitPython's `git.repo.base.Repo` class is no longer available via
  the `.repo` attribute of `GitRepo` and `AnnexRepo`.  ([#4172][])

- `AnnexRepo.get_corresponding_branch` now returns `None` rather than
  the current branch name when a managed branch is not checked out.
  ([#4274][])

- The special UUID for git-annex web remotes is now available as
  `datalad.consts.WEB_SPECIAL_REMOTE_UUID`.  It remains accessible as
  `AnnexRepo.WEB_UUID` for compatibility, but new code should use
  `consts.WEB_SPECIAL_REMOTE_UUID` ([#4460][]).

### Fixes

- Widespread improvements in functionality and test coverage on
  Windows and crippled file systems in general.  ([#4057][])
  ([#4245][]) ([#4268][]) ([#4276][]) ([#4291][]) ([#4296][])
  ([#4301][]) ([#4303][]) ([#4304][]) ([#4305][]) ([#4306][])

- `AnnexRepo.get_size_from_key` incorrectly handled file chunks.
  ([#4081][])

- [create-sibling][] would too readily clobber existing paths when
  called with `--existing=replace`.  It now gets confirmation from the
  user before doing so if running interactively and unconditionally
  aborts when running non-interactively.  ([#4147][])

- [update][]  ([#4159][])
  - queried the incorrect branch configuration when updating non-annex
    repositories.
  - didn't account for the fact that the local repository can be
    configured as the upstream "remote" for a branch.

- When the caller included `--bare` as a `git init` option, [create][]
  crashed creating the bare repository, which is currently
  unsupported, rather than aborting with an informative error message.
  ([#4065][])

- The logic for automatically propagating the 'origin' remote when
  cloning a local source could unintentionally trigger a fetch of a
  non-local remote.  ([#4196][])

- All remaining `get_submodules()` call sites that relied on the
  temporary compatibility layer added in v0.12.0 have been updated.
  ([#4348][])

- The custom result summary renderer for [get][], which was visible
  with `--output-format=tailored`, displayed incorrect and confusing
  information in some cases.  The custom renderer has been removed
  entirely.  ([#4471][])

- The documentation for the Python interface of a command listed an
  incorrect default when the command overrode the value of command
  parameters such as `result_renderer`.  ([#4480][])

### Enhancements and new features

- The default result renderer learned to elide a chain of results
  after seeing ten consecutive results that it considers similar,
  which improves the display of actions that have many results (e.g.,
  saving hundreds of files).  ([#4337][])

- The default result renderer, in addition to "tailored" result
  renderer, now triggers the custom summary renderer, if any.  ([#4338][])

- The new command [create-sibling-ria][] provides support for creating
  a sibling in a [RIA store][handbook-scalable-datastore]. ([#4124][])

- DataLad ships with a new special remote, git-annex-remote-ora, for
  interacting with [RIA stores][handbook-scalable-datastore] and a new
  command [export-archive-ora][] for exporting an archive from a local
  annex object store.  ([#4260][]) ([#4203][])

- The new command [push][] provides an alternative interface to
  [publish][] for pushing a dataset hierarchy to a sibling.
  ([#4206][]) ([#4581][]) ([#4617][]) ([#4620][])

- The new command [copy-file][] copies files and associated
  availability information from one dataset to another.  ([#4430][])

- The command examples have been expanded and improved.  ([#4091][])
  ([#4314][]) ([#4464][])

- The tooling for linking to the [DataLad Handbook][handbook] from
  DataLad's documentation has been improved.  ([#4046][])

- The `--reckless` parameter of [clone][] and [install][] learned two
  new modes:
  - "ephemeral", where the .git/annex/ of the cloned repository is
    symlinked to the local source repository's.  ([#4099][])
  - "shared-{group|all|...}" that can be used to set up datasets for
    collaborative write access.  ([#4324][])

- [clone][]
  - learned to handle dataset aliases in RIA stores when given a URL
    of the form `ria+<protocol>://<storelocation>#~<aliasname>`.
    ([#4459][])
  - now checks `datalad.get.subdataset-source-candidate-NAME` to see
    if `NAME` starts with three digits, which is taken as a "cost".
    Sources with lower costs will be tried first.  ([#4619][])

- [update][]  ([#4167][])
  - learned to disallow non-fast-forward updates when `ff-only` is
    given to the `--merge` option.
  - gained a `--follow` option that controls how `--merge` behaves,
    adding support for merging in the revision that is registered in
    the parent dataset rather than merging in the configured branch
    from the sibling.
  - now provides a result record for merge events.

- [create-sibling][] now supports local paths as targets in addition
  to SSH URLs.  ([#4187][])

- [siblings][] now
  - shows a warning if the caller requests to delete a sibling that
    does not exist.  ([#4257][])
  - phrases its warning about non-annex repositories in a less
    alarming way.  ([#4323][])

- The rendering of command errors has been improved.  ([#4157][])

- [save][] now
  - displays a message to signal that the working tree is clean,
    making it more obvious that no results being rendered corresponds
    to a clean state.  ([#4106][])
  - provides a stronger warning against using `--to-git`.  ([#4290][])

- [diff][] and [save][] learned about scenarios where they could avoid
  unnecessary and expensive work.  ([#4526][]) ([#4544][]) ([#4549][])

- Calling [diff][] without `--recursive` but with a path constraint
  within a subdataset ("<subdataset>/<path>") now traverses into the
  subdataset, as "<subdataset>/" would, restricting its report to
  "<subdataset>/<path>".  ([#4235][])

- New option `datalad.annex.retry` controls how many times git-annex
  will retry on a failed transfer.  It defaults to 3 and can be set to
  0 to restore the previous behavior.  ([#4382][])

- [wtf][] now warns when the specified dataset does not exist.
  ([#4331][])

- The `repr` and `str` output of the dataset and repo classes got a
  facelift.  ([#4420][]) ([#4435][]) ([#4439][])

- The DataLad Singularity container now comes with p7zip-full.

- DataLad emits a log message when the current working directory is
  resolved to a different location due to a symlink.  This is now
  logged at the DEBUG rather than WARNING level, as it typically does
  not indicate a problem.  ([#4426][])

- DataLad now lets the caller know that `git annex init` is scanning
  for unlocked files, as this operation can be slow in some
  repositories.  ([#4316][])

- The `log_progress` helper learned how to set the starting point to a
  non-zero value and how to update the total of an existing progress
  bar, two features needed for planned improvements to how some
  commands display their progress.  ([#4438][])

- The `ExternalVersions` object, which is used to check versions of
  Python modules and external tools (e.g., git-annex), gained an `add`
  method that enables DataLad extensions and other third-party code to
  include other programs of interest.  ([#4441][])

- All of the remaining spots that use GitPython have been rewritten
  without it.  Most notably, this includes rewrites of the `clone`,
  `fetch`, and `push` methods of `GitRepo`.  ([#4080][]) ([#4087][])
  ([#4170][]) ([#4171][]) ([#4175][]) ([#4172][])

- When `GitRepo.commit` splits its operation across multiple calls to
  avoid exceeding the maximum command line length, it now amends to
  initial commit rather than creating multiple commits.  ([#4156][])

- `GitRepo` gained a `get_corresponding_branch` method (which always
   returns None), allowing a caller to invoke the method without
   needing to check if the underlying repo class is `GitRepo` or
   `AnnexRepo`.  ([#4274][])

- A new helper function `datalad.core.local.repo.repo_from_path`
  returns a repo class for a specified path.  ([#4273][])

- New `AnnexRepo` method `localsync` performs a `git annex sync` that
  disables external interaction and is particularly useful for
  propagating changes on an adjusted branch back to the main branch.
  ([#4243][])


## 0.12.7 (May 22, 2020) -- .

### Fixes

- Requesting tailored output (`--output=tailored`) from a command with
  a custom result summary renderer produced repeated output. ([#4463][])

- A longstanding regression in argcomplete-based command-line
  completion for Bash has been fixed.  You can enable completion by
  configuring a Bash startup file to run `eval
  "$(register-python-argcomplete datalad)"` or source DataLad's
  `tools/cmdline-completion`.  The latter should work for Zsh as well.
  ([#4477][])

- [publish][] didn't prevent `git-fetch` from recursing into
  submodules, leading to a failure when the registered submodule was
  not present locally and the submodule did not have a remote named
  'origin'.  ([#4560][])

- [addurls][] botched path handling when the file name format started
  with "./" and the call was made from a subdirectory of the dataset.
  ([#4504][])

- Double dash options in manpages were unintentionally escaped.
  ([#4332][])

- The check for HTTP authentication failures crashed in situations
  where content came in as bytes rather than unicode.  ([#4543][])

- A check in `AnnexRepo.whereis` could lead to a type error.  ([#4552][])

- When installing a dataset to obtain a subdataset, [get][]
  confusingly displayed a message that described the containing
  dataset as "underneath" the subdataset.  ([#4456][])

- A couple of Makefile rules didn't properly quote paths.  ([#4481][])

- With DueCredit support enabled (`DUECREDIT_ENABLE=1`), the query for
  metadata information could flood the output with warnings if
  datasets didn't have aggregated metadata.  The warnings are now
  silenced, with the overall failure of a [metadata][] call logged at
  the debug level.  ([#4568][])

### Enhancements and new features

- The resource identifier helper learned to recognize URLs with
  embedded Git transport information, such as
  gcrypt::https://example.com.  ([#4529][])

- When running non-interactively, a more informative error is now
  signaled when the UI backend, which cannot display a question, is
  asked to do so.  ([#4553][])


## 0.12.6 (April 23, 2020) -- .

### Major refactoring and deprecations

- The value of `datalad.support.annexrep.N_AUTO_JOBS` is no longer
  considered.  The variable will be removed in a later release.
  ([#4409][])

### Fixes

- Staring with v0.12.0, `datalad save` recorded the current branch of
  a parent dataset as the `branch` value in the .gitmodules entry for
  a subdataset.  This behavior is problematic for a few reasons and
  has been reverted.  ([#4375][])

- The default for the `--jobs` option, "auto", instructed DataLad to
  pass a value to git-annex's `--jobs` equal to `min(8, max(3, <number
  of CPUs>))`, which could lead to issues due to the large number of
  child processes spawned and file descriptors opened.  To avoid this
  behavior, `--jobs=auto` now results in git-annex being called with
  `--jobs=1` by default.  Configure the new option
  `datalad.runtime.max-annex-jobs` to control the maximum value that
  will be considered when `--jobs='auto'`.  ([#4409][])

- Various commands have been adjusted to better handle the case where
  a remote's HEAD ref points to an unborn branch.  ([#4370][])

- [search]
  - learned to use the query as a regular expression that restricts
    the keys that are shown for `--show-keys short`. ([#4354][])
  - gives a more helpful message when query is an invalid regular
    expression.  ([#4398][])

- The code for parsing Git configuration did not follow Git's behavior
  of accepting a key with no value as shorthand for key=true.  ([#4421][])

- `AnnexRepo.info` needed a compatibility update for a change in how
  git-annex reports file names.  ([#4431][])

- [create-sibling-github][] did not gracefully handle a token that did
  not have the necessary permissions.  ([#4400][])

### Enhancements and new features

- [search] learned to use the query as a regular expression that
  restricts the keys that are shown for `--show-keys short`. ([#4354][])

- `datalad <subcommand>` learned to point to the [datalad-container][]
  extension when a subcommand from that extension is given but the
  extension is not installed.  ([#4400][]) ([#4174][])


## 0.12.5 (Apr 02, 2020) -- a small step for datalad ...
￼
Fix some bugs and make the world an even better place.

### Fixes

- Our `log_progress` helper mishandled the initial display and step of
  the progress bar.  ([#4326][])

- `AnnexRepo.get_content_annexinfo` is designed to accept `init=None`,
  but passing that led to an error.  ([#4330][])

- Update a regular expression to handle an output change in Git
  v2.26.0.  ([#4328][])

- We now set `LC_MESSAGES` to 'C' while running git to avoid failures
  when parsing output that is marked for translation.  ([#4342][])

- The helper for decoding JSON streams loaded the last line of input
  without decoding it if the line didn't end with a new line, a
  regression introduced in the 0.12.0 release.  ([#4361][])

- The clone command failed to git-annex-init a fresh clone whenever
  it considered to add the origin of the origin as a remote.  ([#4367][])


## 0.12.4 (Mar 19, 2020) -- Windows?!
￼
The main purpose of this release is to have one on PyPi that has no
associated wheel to enable a working installation on Windows ([#4315][]).

### Fixes

- The description of the `log.outputs` config switch did not keep up
  with code changes and incorrectly stated that the output would be
  logged at the DEBUG level; logging actually happens at a lower
  level.  ([#4317][])

## 0.12.3 (March 16, 2020) -- .

Updates for compatibility with the latest git-annex, along with a few
miscellaneous fixes

### Major refactoring and deprecations

- All spots that raised a `NoDatasetArgumentFound` exception now raise
  a `NoDatasetFound` exception to better reflect the situation: it is
  the _dataset_ rather than the _argument_ that is not found.  For
  compatibility, the latter inherits from the former, but new code
  should prefer the latter.  ([#4285][])

### Fixes

- Updates for compatibility with git-annex version 8.20200226. ([#4214][])

- `datalad export-to-figshare` failed to export if the generated title
  was fewer than three characters.  It now queries the caller for the
  title and guards against titles that are too short.  ([#4140][])

- Authentication was requested multiple times when git-annex launched
  parallel downloads from the `datalad` special remote. ([#4308][])

- At verbose logging levels, DataLad requests that git-annex display
  debugging information too.  Work around a bug in git-annex that
  prevented that from happening.  ([#4212][])

- The internal command runner looked in the wrong place for some
  configuration variables, including `datalad.log.outputs`, resulting
  in the default value always being used.  ([#4194][])

- [publish][] failed when trying to publish to a git-lfs special
  remote for the first time.  ([#4200][])

- `AnnexRepo.set_remote_url` is supposed to establish shared SSH
  connections but failed to do so.  ([#4262][])

### Enhancements and new features

- The message provided when a command cannot determine what dataset to
  operate on has been improved.  ([#4285][])

- The "aws-s3" authentication type now allows specifying the host
  through "aws-s3_host", which was needed to work around an
  authorization error due to a longstanding upstream bug.  ([#4239][])

- The xmp metadata extractor now recognizes ".wav" files.


## 0.12.2 (Jan 28, 2020) -- Smoothen the ride

Mostly a bugfix release with various robustifications, but also makes
the first step towards versioned dataset installation requests.

### Major refactoring and deprecations

- The minimum required version for GitPython is now 2.1.12. ([#4070][])

### Fixes

- The class for handling configuration values, `ConfigManager`,
  inappropriately considered the current working directory's dataset,
  if any, for both reading and writing when instantiated with
  `dataset=None`.  This misbehavior is fairly inaccessible through
  typical use of DataLad.  It affects `datalad.cfg`, the top-level
  configuration instance that should not consider repository-specific
  values.  It also affects Python users that call `Dataset` with a
  path that does not yet exist and persists until that dataset is
  created. ([#4078][])

- [update][] saved the dataset when called with `--merge`, which is
  unnecessary and risks committing unrelated changes.  ([#3996][])

- Confusing and irrelevant information about Python defaults have been
  dropped from the command-line help.  ([#4002][])

- The logic for automatically propagating the 'origin' remote when
  cloning a local source didn't properly account for relative paths.
  ([#4045][])

- Various fixes to file name handling and quoting on Windows.
  ([#4049][]) ([#4050][])

- When cloning failed, error lines were not bubbled up to the user in
  some scenarios.  ([#4060][])

### Enhancements and new features

- [clone][] (and thus [install][])
  - now propagates the `reckless` mode from the superdataset when
    cloning a dataset into it.  ([#4037][])
  - gained support for `ria+<protocol>://` URLs that point to
    [RIA][handbook-scalable-datastore] stores.  ([#4022][])
  - learned to read "@version" from `ria+` URLs and install that
    version of a dataset ([#4036][]) and to apply URL rewrites
    configured through Git's `url.*.insteadOf` mechanism ([#4064][]).
  - now copies `datalad.get.subdataset-source-candidate-<name>`
    options configured within the superdataset into the subdataset.
    This is particularly useful for RIA data stores. ([#4073][])

- Archives are now (optionally) handled with 7-Zip instead of
  `patool`.  7-Zip will be used by default, but `patool` will be used
  on non-Windows systems if the `datalad.runtime.use-patool` option is
  set or the `7z` executable is not found.  ([#4041][])


## 0.12.1 (Jan 15, 2020) -- Small bump after big bang

Fix some fallout after major release.

### Fixes

- Revert incorrect relative path adjustment to URLs in [clone][]. ([#3538][])

- Various small fixes to internal helpers and test to run on Windows
  ([#2566][]) ([#2534][])

## 0.12.0 (Jan 11, 2020) -- Krakatoa

This release is the result of more than a year of development that includes
fixes for a large number of issues, yielding more robust behavior across a
wider range of use cases, and introduces major changes in API and behavior. It
is the first release for which extensive user documentation is available in a
dedicated [DataLad Handbook][handbook].  Python 3 (3.5 and later) is now the
only supported Python flavor.

### Major changes 0.12 vs 0.11

- [save][] fully replaces [add][] (which is obsolete now, and will be removed
  in a future release).

- A new Git-annex aware [status][] command enables detailed inspection of dataset
  hierarchies. The previously available [diff][] command has been adjusted to
  match [status][] in argument semantics and behavior.

- The ability to configure dataset procedures prior and after the execution of
  particular commands has been replaced by a flexible "hook" mechanism that is able
  to run arbitrary DataLad commands whenever command results are detected that match
  a specification.

- Support of the Windows platform has been improved substantially. While performance
  and feature coverage on Windows still falls behind Unix-like systems, typical data
  consumer use cases, and standard dataset operations, such as [create][] and [save][],
  are now working. Basic support for data provenance capture via [run][] is also
  functional.

- Support for Git-annex direct mode repositories has been removed, following the
  end of support in Git-annex itself.

- The semantics of relative paths in command line arguments have changed. Previously,
  a call `datalad save --dataset /tmp/myds some/relpath` would have been interpreted
  as saving a file at `/tmp/myds/some/relpath` into dataset `/tmp/myds`. This has
  changed to saving `$PWD/some/relpath` into dataset `/tmp/myds`. More generally,
  relative paths are now always treated as relative to the current working directory,
  except for path arguments of [Dataset][] class instance methods of the Python API.
  The resulting partial duplication of path specifications between path and dataset
  arguments is mitigated by the introduction of two special symbols that can be given
  as dataset argument: `^` and `^.`, which identify the topmost superdataset and the
  closest dataset that contains the working directory, respectively.

- The concept of a "core API" has been introduced. Commands situated in the module
  `datalad.core` (such as [create][], [save][], [run][], [status][], [diff][])
  receive additional scrutiny regarding API and implementation, and are
  meant to provide longer-term stability. Application developers are encouraged to
  preferentially build on these commands.

### Major refactoring and deprecations since 0.12.0rc6

- [clone][] has been incorporated into the growing core API. The public
  `--alternative-source` parameter has been removed, and a `clone_dataset`
  function with multi-source capabilities is provided instead. The
  `--reckless` parameter can now take literal mode labels instead of just
  beeing a binary flag, but backwards compatibility is maintained.

- The `get_file_content` method of `GitRepo` was no longer used
  internally or in any known DataLad extensions and has been removed.
  ([#3812][])

- The function `get_dataset_root` has been replaced by
  `rev_get_dataset_root`.  `rev_get_dataset_root` remains as a
  compatibility alias and will be removed in a later release.  ([#3815][])

- The `add_sibling` module, marked obsolete in v0.6.0, has been
  removed.  ([#3871][])

- `mock` is no longer declared as an external dependency because we
   can rely on it being in the standard library now that our minimum
   required Python version is 3.5. ([#3860][])

- [download-url][] now requires that directories be indicated with a
  trailing slash rather than interpreting a path as directory when it
  doesn't exist.  This avoids confusion that can result from typos and
  makes it possible to support directory targets that do not exist.
  ([#3854][])

- The `dataset_only` argument of the `ConfigManager` class is
  deprecated.  Use `source="dataset"` instead.  ([#3907][])

- The `--proc-pre` and `--proc-post` options have been removed, and
  configuration values for `datalad.COMMAND.proc-pre` and
  `datalad.COMMAND.proc-post` are no longer honored.  The new result
  hook mechanism provides an alternative for `proc-post`
  procedures. ([#3963][])

### Fixes since 0.12.0rc6

- [publish][] crashed when called with a detached HEAD.  It now aborts
  with an informative message.  ([#3804][])

- Since 0.12.0rc6 the call to [update][] in [siblings][] resulted in a
  spurious warning.  ([#3877][])

- [siblings][] crashed if it encountered an annex repository that was
  marked as dead.  ([#3892][])

- The update of [rerun][] in v0.12.0rc3 for the rewritten [diff][]
  command didn't account for a change in the output of `diff`, leading
  to `rerun --report` unintentionally including unchanged files in its
  diff values.  ([#3873][])

- In 0.12.0rc5 [download-url][] was updated to follow the new path
  handling logic, but its calls to AnnexRepo weren't properly
  adjusted, resulting in incorrect path handling when the called from
  a dataset subdirectory.  ([#3850][])

- [download-url][] called `git annex addurl` in a way that failed to
  register a URL when its header didn't report the content size.
  ([#3911][])

- With Git v2.24.0, saving new subdatasets failed due to a bug in that
  Git release.  ([#3904][])

- With DataLad configured to stop on failure (e.g., specifying
  `--on-failure=stop` from the command line), a failing result record
  was not rendered.  ([#3863][])

- Installing a subdataset yielded an "ok" status in cases where the
  repository was not yet in its final state, making it ineffective for
  a caller to operate on the repository in response to the result.
  ([#3906][])

- The internal helper for converting git-annex's JSON output did not
  relay information from the "error-messages" field.  ([#3931][])

- [run-procedure][] reported relative paths that were confusingly not
  relative to the current directory in some cases.  It now always
  reports absolute paths. ([#3959][])

- [diff][] inappropriately reported files as deleted in some cases
  when `to` was a value other than `None`.  ([#3999][])

- An assortment of fixes for Windows compatibility.  ([#3971][]) ([#3974][])
  ([#3975][]) ([#3976][]) ([#3979][])

- Subdatasets installed from a source given by relative path will now
  have this relative path used as 'url' in their .gitmodules record,
  instead of an absolute path generated by Git. ([#3538][])

- [clone][] will now correctly interpret '~/...' paths as absolute path
  specifications. ([#3958][])

- [run-procedure][] mistakenly reported a directory as a procedure.
  ([#3793][])

- The cleanup for batched git-annex processes has been improved.
  ([#3794][]) ([#3851][])

- The function for adding a version ID to an AWS S3 URL doesn't
  support URLs with an "s3://" scheme and raises a
  `NotImplementedError` exception when it encounters one.  The
  function learned to return a URL untouched if an "s3://" URL comes
  in with a version ID.  ([#3842][])

- A few spots needed to be adjusted for compatibility with git-annex's
  new `--sameas` [feature][gx-sameas], which allows special remotes to
  share a data store. ([#3856][])

- The `swallow_logs` utility failed to capture some log messages due
  to an incompatibility with Python 3.7.  ([#3935][])

- [siblings][]
  - crashed if `--inherit` was passed but the parent dataset did not
    have a remote with a matching name.  ([#3954][])
  - configured the wrong pushurl and annexurl values in some
    cases. ([#3955][])

### Enhancements and new features since 0.12.0rc6

- By default, datasets cloned from local source paths will now get a
  configured remote for any recursively discoverable 'origin' sibling that
  is also available from a local path in order to maximize automatic file
  availability across local annexes. ([#3926][])

- The new [result hooks mechanism][hooks] allows callers to specify,
  via local Git configuration values, DataLad command calls that will
  be triggered in response to matching result records (i.e., what you
  see when you call a command with `-f json_pp`).  ([#3903][])

- The command interface classes learned to use a new `_examples_`
  attribute to render documentation examples for both the Python and
  command-line API.  ([#3821][])

- Candidate URLs for cloning a submodule can now be generated based on
  configured templates that have access to various properties of the
  submodule, including its dataset ID.  ([#3828][])

- DataLad's check that the user's Git identity is configured has been
  sped up and now considers the appropriate environment variables as
  well.  ([#3807][])

- The `tag` method of `GitRepo` can now tag revisions other than
  `HEAD` and accepts a list of arbitrary `git tag` options.
  ([#3787][])

- When `get` clones a subdataset and the subdataset's HEAD differs
  from the commit that is registered in the parent, the active branch
  of the subdataset is moved to the registered commit if the
  registered commit is an ancestor of the subdataset's HEAD commit.
  This handling has been moved to a more central location within
  `GitRepo`, and now applies to any `update_submodule(..., init=True)`
  call.  ([#3831][])

- The output of `datalad -h` has been reformatted to improve
  readability.  ([#3862][])

- [unlock][] has been sped up.  ([#3880][])

- [run-procedure][] learned to provide and render more information
  about discovered procedures, including whether the procedure is
  overridden by another procedure with the same base name.  ([#3960][])

- [save][] now ([#3817][])
  - records the active branch in the superdataset when registering a
    new subdataset.
  - calls `git annex sync` when saving a dataset on an adjusted branch
    so that the changes are brought into the mainline branch.

- [subdatasets][] now aborts when its `dataset` argument points to a
  non-existent dataset.  ([#3940][])

- [wtf][] now
  - reports the dataset ID if the current working directory is
    visiting a dataset.  ([#3888][])
  - outputs entries deterministically.  ([#3927][])

- The `ConfigManager` class
  - learned to exclude ``.datalad/config`` as a source of
    configuration values, restricting the sources to standard Git
    configuration files, when called with `source="local"`.
    ([#3907][])
  - accepts a value of "override" for its `where` argument to allow
    Python callers to more convenient override configuration.
    ([#3970][])

- Commands now accept a `dataset` value of "^."  as shorthand for "the
  dataset to which the current directory belongs".  ([#3242][])

## 0.12.0rc6 (Oct 19, 2019) -- some releases are better than the others

bet we will fix some bugs and make a world even a better place.

### Major refactoring and deprecations

- DataLad no longer supports Python 2.  The minimum supported version
  of Python is now 3.5.  ([#3629][])

- Much of the user-focused content at http://docs.datalad.org has been
  removed in favor of more up to date and complete material available
  in the [DataLad Handbook][handbook].  Going forward, the plan is to
  restrict http://docs.datalad.org to technical documentation geared
  at developers.  ([#3678][])

- [update][] used to allow the caller to specify which dataset(s) to
  update as a `PATH` argument or via the the `--dataset` option; now
  only the latter is supported.  Path arguments only serve to restrict
  which subdataset are updated when operating recursively.
  ([#3700][])

- Result records from a [get][] call no longer have a "state" key.
  ([#3746][])

- [update][] and [get][] no longer support operating on independent
  hierarchies of datasets.  ([#3700][]) ([#3746][])

- The [run][] update in 0.12.0rc4 for the new path resolution logic
  broke the handling of inputs and outputs for calls from a
  subdirectory.  ([#3747][])

- The `is_submodule_modified` method of `GitRepo` as well as two
  helper functions in gitrepo.py, `kwargs_to_options` and
  `split_remote_branch`, were no longer used internally or in any
  known DataLad extensions and have been removed.  ([#3702][])
  ([#3704][])

- The `only_remote` option of `GitRepo.is_with_annex` was not used
  internally or in any known extensions and has been dropped.
  ([#3768][])

- The `get_tags` method of `GitRepo` used to sort tags by committer
  date.  It now sorts them by the tagger date for annotated tags and
  the committer date for lightweight tags.  ([#3715][])

- The `rev_resolve_path` substituted `resolve_path` helper. ([#3797][])


### Fixes

- Correctly handle relative paths in [publish][]. ([#3799][]) ([#3102][])

- Do not errorneously discover directory as a procedure. ([#3793][])

- Correctly extract version from manpage to trigger use of manpages for
  `--help`. ([#3798][])

- The `cfg_yoda` procedure saved all modifications in the repository
  rather than saving only the files it modified.  ([#3680][])

- Some spots in the documentation that were supposed appear as two
  hyphens were incorrectly rendered in the HTML output en-dashs.
  ([#3692][])

- [create][], [install][], and [clone][] treated paths as relative to
  the dataset even when the string form was given, violating the new
  path handling rules.  ([#3749][]) ([#3777][]) ([#3780][])

- Providing the "^" shortcut to `--dataset` didn't work properly when
  called from a subdirectory of a subdataset.  ([#3772][])

- We failed to propagate some errors from git-annex when working with
  its JSON output.  ([#3751][])

- With the Python API, callers are allowed to pass a string or list of
  strings as the `cfg_proc` argument to [create][], but the string
  form was mishandled.  ([#3761][])

- Incorrect command quoting for SSH calls on Windows that rendered
  basic SSH-related functionality (e.g., [sshrun][]) on Windows
  unusable.  ([#3688][])

- Annex JSON result handling assumed platform-specific paths on Windows
  instead of the POSIX-style that is happening across all platforms.
  ([#3719][])

- `path_is_under()` was incapable of comparing Windows paths with different
  drive letters.  ([#3728][])

### Enhancements and new features

- Provide a collection of "public" `call_git*` helpers within GitRepo
  and replace use of "private" and less specific `_git_custom_command`
  calls.  ([#3791][])

- [status][] gained a `--report-filetype`.  Setting it to "raw" can
  give a performance boost for the price of no longer distinguishing
  symlinks that point to annexed content from other symlinks.
  ([#3701][])

- [save][] disables file type reporting by [status][] to improve
  performance.  ([#3712][])

- [subdatasets][] ([#3743][])
  - now extends its result records with a `contains` field that lists
    which `contains` arguments matched a given subdataset.
  - yields an 'impossible' result record when a `contains` argument
    wasn't matched to any of the reported subdatasets.

- [install][] now shows more readable output when cloning fails.
  ([#3775][])

- `SSHConnection` now displays a more informative error message when
  it cannot start the `ControlMaster` process.  ([#3776][])

- If the new configuration option `datalad.log.result-level` is set to
  a single level, all result records will be logged at that level.  If
  you've been bothered by DataLad's double reporting of failures,
  consider setting this to "debug".  ([#3754][])

- Configuration values from `datalad -c OPTION=VALUE ...` are now
  validated to provide better errors.  ([#3695][])

- [rerun][] learned how to handle history with merges.  As was already
  the case when cherry picking non-run commits, re-creating merges may
  results in conflicts, and `rerun` does not yet provide an interface
  to let the user handle these.  ([#2754][])

- The `fsck` method of `AnnexRepo` has been enhanced to expose more
  features of the underlying `git fsck` command.  ([#3693][])

- `GitRepo` now has a `for_each_ref_` method that wraps `git
  for-each-ref`, which is used in various spots that used to rely on
  GitPython functionality.  ([#3705][])

- Do not pretend to be able to work in optimized (`python -O`) mode,
  crash early with an informative message. ([#3803][])

## 0.12.0rc5 (September 04, 2019) -- .

Various fixes and enhancements that bring the 0.12.0 release closer.

### Major refactoring and deprecations

- The two modules below have a new home.  The old locations still
  exist as compatibility shims and will be removed in a future
  release.
  - `datalad.distribution.subdatasets` has been moved to
    `datalad.local.subdatasets` ([#3429][])
  - `datalad.interface.run` has been moved to `datalad.core.local.run`
    ([#3444][])

- The `lock` method of `AnnexRepo` and the `options` parameter of
  `AnnexRepo.unlock` were unused internally and have been removed.
  ([#3459][])

- The `get_submodules` method of `GitRepo` has been rewritten without
  GitPython.  When the new `compat` flag is true (the current
  default), the method returns a value that is compatible with the old
  return value.  This backwards-compatible return value and the
  `compat` flag will be removed in a future release.  ([#3508][])

- The logic for resolving relative paths given to a command has
  changed ([#3435][]).  The new rule is that relative paths are taken
  as relative to the dataset only if a dataset _instance_ is passed by
  the caller.  In all other scenarios they're considered relative to
  the current directory.

  The main user-visible difference from the command line is that using
  the `--dataset` argument does _not_ result in relative paths being
  taken as relative to the specified dataset.  (The undocumented
  distinction between "rel/path" and "./rel/path" no longer exists.)

  All commands under `datalad.core` and `datalad.local`, as well as
  `unlock` and `addurls`, follow the new logic.  The goal is for all
  commands to eventually do so.

### Fixes

- The function for loading JSON streams wasn't clever enough to handle
  content that included a Unicode line separator like
  U2028. ([#3524][])

- When [unlock][] was called without an explicit target (i.e., a
  directory or no paths at all), the call failed if any of the files
  did not have content present.  ([#3459][])

- `AnnexRepo.get_content_info` failed in the rare case of a key
  without size information.  ([#3534][])

- [save][] ignored `--on-failure` in its underlying call to
  [status][].  ([#3470][])

- Calling [remove][] with a subdirectory displayed spurious warnings
  about the subdirectory files not existing.  ([#3586][])

- Our processing of `git-annex --json` output mishandled info messages
  from special remotes.  ([#3546][])

- [create][]
  - didn't bypass the "existing subdataset" check when called with
    `--force` as of 0.12.0rc3 ([#3552][])
  - failed to register the up-to-date revision of a subdataset when
    `--cfg-proc` was used with `--dataset` ([#3591][])

- The base downloader had some error handling that wasn't compatible
  with Python 3.  ([#3622][])

- Fixed a number of Unicode py2-compatibility issues. ([#3602][])

- `AnnexRepo.get_content_annexinfo` did not properly chunk file
  arguments to avoid exceeding the command-line character limit.
  ([#3587][])

### Enhancements and new features

- New command `create-sibling-gitlab` provides an interface for
  creating a publication target on a GitLab instance.  ([#3447][])

- [subdatasets][]  ([#3429][])
  - now supports path-constrained queries in the same manner as
    commands like `save` and `status`
  - gained a `--contains=PATH` option that can be used to restrict the
    output to datasets that include a specific path.
  - now narrows the listed subdatasets to those underneath the current
    directory when called with no arguments

- [status][] learned to accept a plain `--annex` (no value) as
  shorthand for `--annex basic`.  ([#3534][])

- The `.dirty` property of `GitRepo` and `AnnexRepo` has been sped up.
  ([#3460][])

- The `get_content_info` method of `GitRepo`, used by `status` and
  commands that depend on `status`, now restricts its git calls to a
  subset of files, if possible, for a performance gain in repositories
  with many files.  ([#3508][])

- Extensions that do not provide a command, such as those that provide
  only metadata extractors, are now supported.  ([#3531][])

- When calling git-annex with `--json`, we log standard error at the
  debug level rather than the warning level if a non-zero exit is
  expected behavior.  ([#3518][])

- [create][] no longer refuses to create a new dataset in the odd
  scenario of an empty .git/ directory upstairs.  ([#3475][])

- As of v2.22.0 Git treats a sub-repository on an unborn branch as a
  repository rather than as a directory.  Our documentation and tests
  have been updated appropriately.  ([#3476][])

- [addurls][] learned to accept a `--cfg-proc` value and pass it to
  its `create` calls.  ([#3562][])

## 0.12.0rc4 (May 15, 2019) -- the revolution is over

With the replacement of the `save` command implementation with `rev-save`
the revolution effort is now over, and the set of key commands for
local dataset operations (`create`, `run`, `save`, `status`, `diff`) is
 now complete. This new core API is available from `datalad.core.local`
(and also via `datalad.api`, as any other command).
￼
### Major refactoring and deprecations

- The `add` command is now deprecated. It will be removed in a future
  release.

### Fixes

- Remove hard-coded dependencies on POSIX path conventions in SSH support
  code ([#3400][])

- Emit an `add` result when adding a new subdataset during [save][] ([#3398][])

- SSH file transfer now actually opens a shared connection, if none exists
  yet ([#3403][])

### Enhancements and new features

- `SSHConnection` now offers methods for file upload and dowload (`get()`,
  `put()`. The previous `copy()` method only supported upload and was
  discontinued ([#3401][])


## 0.12.0rc3 (May 07, 2019) -- the revolution continues
￼
Continues API consolidation and replaces the `create` and `diff` command
with more performant implementations.

### Major refactoring and deprecations

- The previous `diff` command has been replaced by the diff variant
  from the [datalad-revolution][] extension.  ([#3366][])

- `rev-create` has been renamed to `create`, and the previous `create`
  has been removed.  ([#3383][])

- The procedure `setup_yoda_dataset` has been renamed to `cfg_yoda`
  ([#3353][]).

- The `--nosave` of `addurls` now affects only added content, not
  newly created subdatasets ([#3259][]).

- `Dataset.get_subdatasets` (deprecated since v0.9.0) has been
  removed.  ([#3336][])

- The `.is_dirty` method of `GitRepo` and `AnnexRepo` has been
  replaced by `.status` or, for a subset of cases, the `.dirty`
  property.  ([#3330][])

- `AnnexRepo.get_status` has been replaced by `AnnexRepo.status`.
  ([#3330][])

### Fixes

- [status][]
  - reported on directories that contained only ignored files ([#3238][])
  - gave a confusing failure when called from a subdataset with an
    explicitly specified dataset argument and "." as a path ([#3325][])
  - misleadingly claimed that the locally present content size was
    zero when `--annex basic` was specified ([#3378][])

- An informative error wasn't given when a download provider was
  invalid.  ([#3258][])

- Calling `rev-save PATH` saved unspecified untracked subdatasets.
  ([#3288][])

- The available choices for command-line options that take values are
  now displayed more consistently in the help output.  ([#3326][])

- The new pathlib-based code had various encoding issues on Python 2.
  ([#3332][])

### Enhancements and new features

- [wtf][] now includes information about the Python version.  ([#3255][])

- When operating in an annex repository, checking whether git-annex is
  available is now delayed until a call to git-annex is actually
  needed, allowing systems without git-annex to operate on annex
  repositories in a restricted fashion.  ([#3274][])

- The `load_stream` on helper now supports auto-detection of
  compressed files.  ([#3289][])

- `create` (formerly `rev-create`)
  - learned to be speedier by passing a path to `status` ([#3294][])
  - gained a `--cfg-proc` (or `-c`) convenience option for running
    configuration procedures (or more accurately any procedure that
    begins with "cfg_") in the newly created dataset ([#3353][])

- `AnnexRepo.set_metadata` now returns a list while
  `AnnexRepo.set_metadata_` returns a generator, a behavior which is
  consistent with the `add` and `add_` method pair.  ([#3298][])

- `AnnexRepo.get_metadata` now supports batch querying of known annex
   files.  Note, however, that callers should carefully validate the
   input paths because the batch call will silently hang if given
   non-annex files.  ([#3364][])

- [status][]
  - now reports a "bytesize" field for files tracked by Git ([#3299][])
  - gained a new option `eval_subdataset_state` that controls how the
    subdataset state is evaluated.  Depending on the information you
    need, you can select a less expensive mode to make `status`
    faster.  ([#3324][])
  - colors deleted files "red" ([#3334][])

- Querying repository content is faster due to batching of `git
  cat-file` calls.  ([#3301][])

- The dataset ID of a subdataset is now recorded in the superdataset.
  ([#3304][])

- `GitRepo.diffstatus`
  - now avoids subdataset recursion when the comparison is not with
    the working tree, which substantially improves performance when
    diffing large dataset hierarchies  ([#3314][])
  - got smarter and faster about labeling a subdataset as "modified"
    ([#3343][])

- `GitRepo.get_content_info` now supports disabling the file type
  evaluation, which gives a performance boost in cases where this
  information isn't needed.  ([#3362][])

- The XMP metadata extractor now filters based on file name to improve
  its performance.  ([#3329][])

## 0.12.0rc2 (Mar 18, 2019) -- revolution!

### Fixes

- `GitRepo.dirty` does not report on nested empty directories ([#3196][]).

- `GitRepo.save()` reports results on deleted files.

### Enhancements and new features

- Absorb a new set of core commands from the datalad-revolution extension:
  - `rev-status`: like `git status`, but simpler and working with dataset
     hierarchies
  - `rev-save`: a 2-in-1 replacement for save and add
  - `rev-create`: a ~30% faster create

- JSON support tools can now read and write compressed files.


## 0.12.0rc1 (Mar 03, 2019) -- to boldly go ...

### Major refactoring and deprecations

- Discontinued support for git-annex direct-mode (also no longer
  supported upstream).

### Enhancements and new features

- Dataset and Repo object instances are now hashable, and can be
  created based on pathlib Path object instances

- Imported various additional methods for the Repo classes to query
  information and save changes.


## 0.11.8 (Oct 11, 2019) -- annex-we-are-catching-up

### Fixes

- Our internal command runner failed to capture output in some cases.
  ([#3656][])
- Workaround in the tests around python in cPython >= 3.7.5 ';' in
  the filename confusing mimetypes ([#3769][]) ([#3770][])

### Enhancements and new features

- Prepared for upstream changes in git-annex, including support for
  the latest git-annex
  - 7.20190912 auto-upgrades v5 repositories to v7.  ([#3648][]) ([#3682][])
  - 7.20191009 fixed treatment of (larger/smaller)than in .gitattributes ([#3765][])

- The `cfg_text2git` procedure, as well the `--text-no-annex` option
  of [create][], now configure .gitattributes so that empty files are
  stored in git rather than annex.  ([#3667][])


## 0.11.7 (Sep 06, 2019) -- python2-we-still-love-you-but-...

Primarily bugfixes with some optimizations and refactorings.

### Fixes

- [addurls][]
  - now provides better handling when the URL file isn't in the
    expected format.  ([#3579][])
  - always considered a relative file for the URL file argument as
    relative to the current working directory, which goes against the
    convention used by other commands of taking relative paths as
    relative to the dataset argument.  ([#3582][])

- [run-procedure][]
  - hard coded "python" when formatting the command for non-executable
    procedures ending with ".py".  `sys.executable` is now used.
    ([#3624][])
  - failed if arguments needed more complicated quoting than simply
    surrounding the value with double quotes.  This has been resolved
    for systems that support `shlex.quote`, but note that on Windows
    values are left unquoted. ([#3626][])

- [siblings][] now displays an informative error message if a local
  path is given to `--url` but `--name` isn't specified.  ([#3555][])

- [sshrun][], the command DataLad uses for `GIT_SSH_COMMAND`, didn't
  support all the parameters that Git expects it to.  ([#3616][])

- Fixed a number of Unicode py2-compatibility issues. ([#3597][])

- [download-url][] now will create leading directories of the output path
  if they do not exist ([#3646][])

### Enhancements and new features

- The [annotate-paths][] helper now caches subdatasets it has seen to
  avoid unnecessary calls.  ([#3570][])

- A repeated configuration query has been dropped from the handling of
  `--proc-pre` and `--proc-post`.  ([#3576][])

- Calls to `git annex find` now use `--in=.` instead of the alias
  `--in=here` to take advantage of an optimization that git-annex (as
  of the current release, 7.20190730) applies only to the
  former. ([#3574][])

- [addurls][] now suggests close matches when the URL or file format
  contains an unknown field.  ([#3594][])

- Shared logic used in the setup.py files of Datalad and its
  extensions has been moved to modules in the _datalad_build_support/
  directory.  ([#3600][])

- Get ready for upcoming git-annex dropping support for direct mode
  ([#3631][])


## 0.11.6 (Jul 30, 2019) -- am I the last of 0.11.x?

Primarily bug fixes to achieve more robust performance

### Fixes

- Our tests needed various adjustments to keep up with upstream
  changes in Travis and Git. ([#3479][]) ([#3492][]) ([#3493][])

- `AnnexRepo.is_special_annex_remote` was too selective in what it
  considered to be a special remote.  ([#3499][])

- We now provide information about unexpected output when git-annex is
  called with `--json`.  ([#3516][])

- Exception logging in the `__del__` method of `GitRepo` and
  `AnnexRepo` no longer fails if the names it needs are no longer
  bound.  ([#3527][])

- [addurls][] botched the construction of subdataset paths that were
  more than two levels deep and failed to create datasets in a
  reliable, breadth-first order.  ([#3561][])

- Cloning a `type=git` special remote showed a spurious warning about
  the remote not being enabled.  ([#3547][])

### Enhancements and new features

- For calls to git and git-annex, we disable automatic garbage
  collection due to past issues with GitPython's state becoming stale,
  but doing so results in a larger .git/objects/ directory that isn't
  cleaned up until garbage collection is triggered outside of DataLad.
  Tests with the latest GitPython didn't reveal any state issues, so
  we've re-enabled automatic garbage collection.  ([#3458][])

- [rerun][] learned an `--explicit` flag, which it relays to its calls
  to [run][[]].  This makes it possible to call `rerun` in a dirty
  working tree ([#3498][]).

- The [metadata][] command aborts earlier if a metadata extractor is
  unavailable.  ([#3525][])

## 0.11.5 (May 23, 2019) -- stability is not overrated

Should be faster and less buggy, with a few enhancements.

### Fixes

- [create-sibling][]  ([#3318][])
  - Siblings are no longer configured with a post-update hook unless a
    web interface is requested with `--ui`.
  - `git submodule update --init` is no longer called from the
    post-update hook.
  - If `--inherit` is given for a dataset without a superdataset, a
    warning is now given instead of raising an error.
- The internal command runner failed on Python 2 when its `env`
  argument had unicode values.  ([#3332][])
- The safeguard that prevents creating a dataset in a subdirectory
  that already contains tracked files for another repository failed on
  Git versions before 2.14.  For older Git versions, we now warn the
  caller that the safeguard is not active.  ([#3347][])
- A regression introduced in v0.11.1 prevented [save][] from committing
  changes under a subdirectory when the subdirectory was specified as
  a path argument.  ([#3106][])
- A workaround introduced in v0.11.1 made it possible for [save][] to
  do a partial commit with an annex file that has gone below the
  `annex.largefiles` threshold.  The logic of this workaround was
  faulty, leading to files being displayed as typechanged in the index
  following the commit.  ([#3365][])
- The resolve_path() helper confused paths that had a semicolon for
  SSH RIs.  ([#3425][])
- The detection of SSH RIs has been improved.  ([#3425][])

### Enhancements and new features

- The internal command runner was too aggressive in its decision to
  sleep.  ([#3322][])
- The "INFO" label in log messages now retains the default text color
  for the terminal rather than using white, which only worked well for
  terminals with dark backgrounds.  ([#3334][])
- A short flag `-R` is now available for the `--recursion-limit` flag,
  a flag shared by several subcommands.  ([#3340][])
- The authentication logic for [create-sibling-github][] has been
  revamped and now supports 2FA.  ([#3180][])
- New configuration option `datalad.ui.progressbar` can be used to
  configure the default backend for progress reporting ("none", for
  example, results in no progress bars being shown).  ([#3396][])
- A new progress backend, available by setting datalad.ui.progressbar
  to "log", replaces progress bars with a log message upon completion
  of an action.  ([#3396][])
- DataLad learned to consult the [NO_COLOR][] environment variable and
  the new `datalad.ui.color` configuration option when deciding to
  color output.  The default value, "auto", retains the current
  behavior of coloring output if attached to a TTY ([#3407][]).
- [clean][] now removes annex transfer directories, which is useful
  for cleaning up failed downloads. ([#3374][])
- [clone][] no longer refuses to clone into a local path that looks
  like a URL, making its behavior consistent with `git clone`.
  ([#3425][])
- [wtf][]
  - Learned to fall back to the `dist` package if `platform.dist`,
    which has been removed in the yet-to-be-release Python 3.8, does
    not exist.  ([#3439][])
  - Gained a `--section` option for limiting the output to specific
    sections and a `--decor` option, which currently knows how to
    format the output as GitHub's `<details>` section.  ([#3440][])

## 0.11.4 (Mar 18, 2019) -- get-ready

Largely a bug fix release with a few enhancements

### Important

- 0.11.x series will be the last one with support for direct mode of [git-annex][]
  which is used on crippled (no symlinks and no locking) filesystems.
  v7 repositories should be used instead.

### Fixes

- Extraction of .gz files is broken without p7zip installed.  We now
  abort with an informative error in this situation.  ([#3176][])

- Committing failed in some cases because we didn't ensure that the
  path passed to `git read-tree --index-output=...` resided on the
  same filesystem as the repository.  ([#3181][])

- Some pointless warnings during metadata aggregation have been
  eliminated.  ([#3186][])

- With Python 3 the LORIS token authenticator did not properly decode
  a response ([#3205][]).

- With Python 3 downloaders unnecessarily decoded the response when
  getting the status, leading to an encoding error.  ([#3210][])

- In some cases, our internal command Runner did not adjust the
  environment's `PWD` to match the current working directory specified
  with the `cwd` parameter.  ([#3215][])

- The specification of the pyliblzma dependency was broken.  ([#3220][])

- [search] displayed an uninformative blank log message in some
  cases.  ([#3222][])

- The logic for finding the location of the aggregate metadata DB
  anchored the search path incorrectly, leading to a spurious warning.
  ([#3241][])

- Some progress bars were still displayed when stdout and stderr were
  not attached to a tty.  ([#3281][])

- Check for stdin/out/err to not be closed before checking for `.isatty`.
  ([#3268][])

### Enhancements and new features

- Creating a new repository now aborts if any of the files in the
  directory are tracked by a repository in a parent directory.
  ([#3211][])

- [run] learned to replace the `{tmpdir}` placeholder in commands with
  a temporary directory.  ([#3223][])
 
- [duecredit][] support has been added for citing DataLad itself as
  well as datasets that an analysis uses.  ([#3184][])

- The `eval_results` interface helper unintentionally modified one of
  its arguments.  ([#3249][])

- A few DataLad constants have been added, changed, or renamed ([#3250][]):
  - `HANDLE_META_DIR` is now `DATALAD_DOTDIR`.  The old name should be
     considered deprecated.
  - `METADATA_DIR` now refers to `DATALAD_DOTDIR/metadata` rather than
    `DATALAD_DOTDIR/meta` (which is still available as
    `OLDMETADATA_DIR`).
  - The new `DATASET_METADATA_FILE` refers to `METADATA_DIR/dataset.json`.
  - The new `DATASET_CONFIG_FILE` refers to `DATALAD_DOTDIR/config`.
  - `METADATA_FILENAME` has been renamed to `OLDMETADATA_FILENAME`.

## 0.11.3 (Feb 19, 2019) -- read-me-gently

Just a few of important fixes and minor enhancements.

### Fixes

- The logic for setting the maximum command line length now works
  around Python 3.4 returning an unreasonably high value for
  `SC_ARG_MAX` on Debian systems. ([#3165][])

- DataLad commands that are conceptually "read-only", such as
  `datalad ls -L`, can fail when the caller lacks write permissions
  because git-annex tries merging remote git-annex branches to update
  information about availability. DataLad now disables
  `annex.merge-annex-branches` in some common "read-only" scenarios to
  avoid these failures. ([#3164][])

### Enhancements and new features

- Accessing an "unbound" dataset method now automatically imports the
  necessary module rather than requiring an explicit import from the
  Python caller. For example, calling `Dataset.add` no longer needs to
  be preceded by `from datalad.distribution.add import Add` or an
  import of `datalad.api`. ([#3156][])

- Configuring the new variable `datalad.ssh.identityfile` instructs
  DataLad to pass a value to the `-i` option of `ssh`. ([#3149][])
  ([#3168][])

## 0.11.2 (Feb 07, 2019) -- live-long-and-prosper

A variety of bugfixes and enhancements

### Major refactoring and deprecations

- All extracted metadata is now placed under git-annex by default.
  Previously files smaller than 20 kb were stored in git. ([#3109][])
- The function `datalad.cmd.get_runner` has been removed. ([#3104][])

### Fixes

- Improved handling of long commands:
  - The code that inspected `SC_ARG_MAX` didn't check that the
    reported value was a sensible, positive number. ([#3025][])
  - More commands that invoke `git` and `git-annex` with file
    arguments learned to split up the command calls when it is likely
    that the command would fail due to exceeding the maximum supported
    length. ([#3138][])
- The `setup_yoda_dataset` procedure created a malformed
  .gitattributes line. ([#3057][])
- [download-url][] unnecessarily tried to infer the dataset when
  `--no-save` was given. ([#3029][])
- [rerun][] aborted too late and with a confusing message when a ref
  specified via `--onto` didn't exist. ([#3019][])
- [run][]:
  - `run` didn't preserve the current directory prefix ("./") on
     inputs and outputs, which is problematic if the caller relies on
     this representation when formatting the command. ([#3037][])
  - Fixed a number of unicode py2-compatibility issues. ([#3035][]) ([#3046][])
  - To proceed with a failed command, the user was confusingly
    instructed to use `save` instead of `add` even though `run` uses
    `add` underneath. ([#3080][])
- Fixed a case where the helper class for checking external modules
  incorrectly reported a module as unknown. ([#3051][])
- [add-archive-content][] mishandled the archive path when the leading
  path contained a symlink. ([#3058][])
- Following denied access, the credential code failed to consider a
  scenario, leading to a type error rather than an appropriate error
  message. ([#3091][])
- Some tests failed when executed from a `git worktree` checkout of the
  source repository. ([#3129][])
- During metadata extraction, batched annex processes weren't properly
  terminated, leading to issues on Windows. ([#3137][])
- [add][] incorrectly handled an "invalid repository" exception when
  trying to add a submodule. ([#3141][])
- Pass `GIT_SSH_VARIANT=ssh` to git processes to be able to specify
  alternative ports in SSH urls

### Enhancements and new features

- [search][] learned to suggest closely matching keys if there are no
  hits. ([#3089][])
- [create-sibling][]
  - gained a `--group` option so that the caller can specify the file
    system group for the repository. ([#3098][])
  - now understands SSH URLs that have a port in them (i.e. the
    "ssh://[user@]host.xz[:port]/path/to/repo.git/" syntax mentioned
    in `man git-fetch`). ([#3146][])
- Interface classes can now override the default renderer for
  summarizing results. ([#3061][])
- [run][]:
  - `--input` and `--output` can now be shortened to `-i` and `-o`.
    ([#3066][])
  - Placeholders such as "{inputs}" are now expanded in the command
    that is shown in the commit message subject. ([#3065][])
  - `interface.run.run_command` gained an `extra_inputs` argument so
    that wrappers like [datalad-container][] can specify additional inputs
    that aren't considered when formatting the command string. ([#3038][])
  - "--" can now be used to separate options for `run` and those for
    the command in ambiguous cases. ([#3119][])
- The utilities `create_tree` and `ok_file_has_content` now support
  ".gz" files. ([#3049][])
- The Singularity container for 0.11.1 now uses [nd_freeze][] to make
  its builds reproducible.
- A [publications][] page has been added to the documentation. ([#3099][])
- `GitRepo.set_gitattributes` now accepts a `mode` argument that
  controls whether the .gitattributes file is appended to (default) or
  overwritten. ([#3115][])
- `datalad --help` now avoids using `man` so that the list of
  subcommands is shown.  ([#3124][])

## 0.11.1 (Nov 26, 2018) -- v7-better-than-v6

Rushed out bugfix release to stay fully compatible with recent
[git-annex][] which introduced v7 to replace v6.

### Fixes

- [install][]: be able to install recursively into a dataset ([#2982][])
- [save][]: be able to commit/save changes whenever files potentially
  could have swapped their storage between git and annex
  ([#1651][]) ([#2752][]) ([#3009][])
- [aggregate-metadata][]:
  - dataset's itself is now not "aggregated" if specific paths are
    provided for aggregation ([#3002][]). That resolves the issue of
    `-r` invocation aggregating all subdatasets of the specified dataset
    as well
  - also compare/verify the actual content checksum of aggregated metadata
    while considering subdataset metadata for re-aggregation ([#3007][])
- `annex` commands are now chunked assuming 50% "safety margin" on the
  maximal command line length. Should resolve crashes while operating
  ot too many files at ones ([#3001][])
- `run` sidecar config processing ([#2991][])
- no double trailing period in docs ([#2984][])
- correct identification of the repository with symlinks in the paths
  in the tests ([#2972][])
- re-evaluation of dataset properties in case of dataset changes ([#2946][])
- [text2git][] procedure to use `ds.repo.set_gitattributes`
  ([#2974][]) ([#2954][])
- Switch to use plain `os.getcwd()` if inconsistency with env var
  `$PWD` is detected ([#2914][])
- Make sure that credential defined in env var takes precedence
  ([#2960][]) ([#2950][])

### Enhancements and new features

- [shub://datalad/datalad:git-annex-dev](https://singularity-hub.org/containers/5663/view)
  provides a Debian buster Singularity image with build environment for
  [git-annex][]. `tools/bisect-git-annex` provides a helper for running
  `git bisect` on git-annex using that Singularity container ([#2995][])
- Added `.zenodo.json` for better integration with Zenodo for citation
- [run-procedure][] now provides names and help messages with a custom
  renderer for ([#2993][])
- Documentation: point to [datalad-revolution][] extension (prototype of
  the greater DataLad future)
- [run][]
  - support injecting of a detached command ([#2937][])
- `annex` metadata extractor now extracts `annex.key` metadata record.
  Should allow now to identify uses of specific files etc ([#2952][])
- Test that we can install from http://datasets.datalad.org
- Proper rendering of `CommandError` (e.g. in case of "out of space"
  error) ([#2958][])


## 0.11.0 (Oct 23, 2018) -- Soon-to-be-perfect

[git-annex][] 6.20180913 (or later) is now required - provides a number of
fixes for v6 mode operations etc.

### Major refactoring and deprecations

- `datalad.consts.LOCAL_CENTRAL_PATH` constant was deprecated in favor
  of `datalad.locations.default-dataset` [configuration][] variable
  ([#2835][])

### Minor refactoring

- `"notneeded"` messages are no longer reported by default results
  renderer
- [run][] no longer shows commit instructions upon command failure when
  `explicit` is true and no outputs are specified ([#2922][])
- `get_git_dir` moved into GitRepo ([#2886][])
- `_gitpy_custom_call` removed from GitRepo ([#2894][])
- `GitRepo.get_merge_base` argument is now called `commitishes` instead
  of `treeishes` ([#2903][])

### Fixes

- [update][] should not leave the dataset in non-clean state ([#2858][])
  and some other enhancements ([#2859][])
- Fixed chunking of the long command lines to account for decorators
  and other arguments ([#2864][])
- Progress bar should not crash the process on some missing progress
  information ([#2891][])
- Default value for `jobs` set to be `"auto"` (not `None`) to take
  advantage of possible parallel get if in `-g` mode ([#2861][])
- [wtf][] must not crash if `git-annex` is not installed etc ([#2865][]),
  ([#2865][]), ([#2918][]), ([#2917][])
- Fixed paths (with spaces etc) handling while reporting annex error
  output ([#2892][]), ([#2893][])
- `__del__` should not access `.repo` but `._repo` to avoid attempts
  for reinstantiation etc ([#2901][])
- Fix up submodule `.git` right in `GitRepo.add_submodule` to avoid
  added submodules being non git-annex friendly ([#2909][]), ([#2904][])
- [run-procedure][] ([#2905][])
  - now will provide dataset into the procedure if called within dataset
  - will not crash if procedure is an executable without `.py` or `.sh`
    suffixes
- Use centralized `.gitattributes` handling while setting annex backend
  ([#2912][])
- `GlobbedPaths.expand(..., full=True)` incorrectly returned relative
   paths when called more than once ([#2921][])

### Enhancements and new features

- Report progress on [clone][] when installing from "smart" git servers
  ([#2876][])
- Stale/unused `sth_like_file_has_content` was removed ([#2860][])
- Enhancements to [search][] to operate on "improved" metadata layouts
  ([#2878][])
- Output of `git annex init` operation is now logged ([#2881][])
- New
  - `GitRepo.cherry_pick` ([#2900][])
  - `GitRepo.format_commit` ([#2902][])
- [run-procedure][] ([#2905][])
  - procedures can now recursively be discovered in subdatasets as well.
    The uppermost has highest priority
  - Procedures in user and system locations now take precedence over
    those in datasets.

## 0.10.3.1 (Sep 13, 2018) -- Nothing-is-perfect

Emergency bugfix to address forgotten boost of version in
`datalad/version.py`.

## 0.10.3 (Sep 13, 2018) -- Almost-perfect

This is largely a bugfix release which addressed many (but not yet all)
issues of working with git-annex direct and version 6 modes, and operation
on Windows in general.  Among enhancements you will see the
support of public S3 buckets (even with periods in their names),
ability to configure new providers interactively, and improved `egrep`
search backend.

Although we do not require with this release, it is recommended to make
sure that you are using a recent `git-annex` since it also had a variety
of fixes and enhancements in the past months.

### Fixes

- Parsing of combined short options has been broken since DataLad
  v0.10.0. ([#2710][])
- The `datalad save` instructions shown by `datalad run` for a command
  with a non-zero exit were incorrectly formatted. ([#2692][])
- Decompression of zip files (e.g., through `datalad
  add-archive-content`) failed on Python 3.  ([#2702][])
- Windows:
  - colored log output was not being processed by colorama.  ([#2707][])
  - more codepaths now try multiple times when removing a file to deal
    with latency and locking issues on Windows.  ([#2795][])
- Internal git fetch calls have been updated to work around a
  GitPython `BadName` issue.  ([#2712][]), ([#2794][])
- The progess bar for annex file transferring was unable to handle an
  empty file.  ([#2717][])
- `datalad add-readme` halted when no aggregated metadata was found
  rather than displaying a warning.  ([#2731][])
- `datalad rerun` failed if `--onto` was specified and the history
  contained no run commits.  ([#2761][])
- Processing of a command's results failed on a result record with a
  missing value (e.g., absent field or subfield in metadata).  Now the
  missing value is rendered as "N/A".  ([#2725][]).
- A couple of documentation links in the "Delineation from related
  solutions" were misformatted.  ([#2773][])
- With the latest git-annex, several known V6 failures are no longer
  an issue.  ([#2777][])
- In direct mode, commit changes would often commit annexed content as
  regular Git files.  A new approach fixes this and resolves a good
  number of known failures.  ([#2770][])
- The reporting of command results failed if the current working
  directory was removed (e.g., after an unsuccessful `install`). ([#2788][])
- When installing into an existing empty directory, `datalad install`
  removed the directory after a failed clone.  ([#2788][])
- `datalad run` incorrectly handled inputs and outputs for paths with
  spaces and other characters that require shell escaping.  ([#2798][])
- Globbing inputs and outputs for `datalad run` didn't work correctly
  if a subdataset wasn't installed.  ([#2796][])
- Minor (in)compatibility with git 2.19 - (no) trailing period
  in an error message now. ([#2815][])

### Enhancements and new features

- Anonymous access is now supported for S3 and other downloaders.  ([#2708][])
- A new interface is available to ease setting up new providers.  ([#2708][])
- Metadata: changes to egrep mode search  ([#2735][])
  - Queries in egrep mode are now case-sensitive when the query
    contains any uppercase letters and are case-insensitive otherwise.
    The new mode egrepcs can be used to perform a case-sensitive query
    with all lower-case letters.
  - Search can now be limited to a specific key.
  - Multiple queries (list of expressions) are evaluated using AND to
    determine whether something is a hit.
  - A single multi-field query (e.g., `pa*:findme`) is a hit, when any
    matching field matches the query.
  - All matching key/value combinations across all (multi-field)
    queries are reported in the query_matched result field.
  - egrep mode now shows all hits rather than limiting the results to
    the top 20 hits.
- The documentation on how to format commands for `datalad run` has
  been improved.  ([#2703][])
- The method for determining the current working directory on Windows
  has been improved.  ([#2707][])
- `datalad --version` now simply shows the version without the
  license.  ([#2733][])
- `datalad export-archive` learned to export under an existing
  directory via its `--filename` option.  ([#2723][])
- `datalad export-to-figshare` now generates the zip archive in the
  root of the dataset unless `--filename` is specified.  ([#2723][])
- After importing `datalad.api`, `help(datalad.api)` (or
  `datalad.api?` in IPython) now shows a summary of the available
  DataLad commands.  ([#2728][])
- Support for using `datalad` from IPython has been improved.  ([#2722][])
- `datalad wtf` now returns structured data and reports the version of
  each extension.  ([#2741][])
- The internal handling of gitattributes information has been
  improved.  A user-visible consequence is that `datalad create
  --force` no longer duplicates existing attributes.  ([#2744][])
- The "annex" metadata extractor can now be used even when no content
  is present.  ([#2724][])
- The `add_url_to_file` method (called by commands like `datalad
  download-url` and `datalad add-archive-content`) learned how to
  display a progress bar.  ([#2738][])


## 0.10.2 (Jul 09, 2018) -- Thesecuriestever

Primarily a bugfix release to accommodate recent git-annex release
forbidding file:// and http://localhost/ URLs which might lead to
revealing private files if annex is publicly shared.

### Fixes

- fixed testing to be compatible with recent git-annex (6.20180626)
- [download-url][] will now download to current directory instead of the
  top of the dataset

### Enhancements and new features

- do not quote ~ in URLs to be consistent with quote implementation in
  Python 3.7 which now follows RFC 3986
- [run][] support for user-configured placeholder values
- documentation on native git-annex metadata support
- handle 401 errors from LORIS tokens
- `yoda` procedure will instantiate `README.md`
- `--discover` option added to [run-procedure][] to list available
  procedures

## 0.10.1 (Jun 17, 2018) -- OHBM polish

The is a minor bugfix release.

### Fixes

- Be able to use backports.lzma as a drop-in replacement for pyliblzma.
- Give help when not specifying a procedure name in `run-procedure`.
- Abort early when a downloader received no filename.
- Avoid `rerun` error when trying to unlock non-available files.

## 0.10.0 (Jun 09, 2018) -- The Release

This release is a major leap forward in metadata support.

### Major refactoring and deprecations

- Metadata
  - Prior metadata provided by datasets under `.datalad/meta` is no
    longer used or supported. Metadata must be reaggregated using 0.10
    version
  - Metadata extractor types are no longer auto-guessed and must be
    explicitly specified in `datalad.metadata.nativetype` config
    (could contain multiple values)
  - Metadata aggregation of a dataset hierarchy no longer updates all
    datasets in the tree with new metadata. Instead, only the target
    dataset is updated. This behavior can be changed via the --update-mode
    switch. The new default prevents needless modification of (3rd-party)
    subdatasets.
  - Neuroimaging metadata support has been moved into a dedicated extension:
    https://github.com/datalad/datalad-neuroimaging
- Crawler
  - moved into a dedicated extension:
    https://github.com/datalad/datalad-crawler
- `export_tarball` plugin has been generalized to `export_archive` and
  can now also generate ZIP archives.
- By default a dataset X is now only considered to be a super-dataset of
  another dataset Y, if Y is also a registered subdataset of X.

### Fixes

A number of fixes did not make it into the 0.9.x series:

- Dynamic configuration overrides via the `-c` option were not in effect.
- `save` is now more robust with respect to invocation in subdirectories
  of a dataset.
- `unlock` now reports correct paths when running in a dataset subdirectory.
- `get` is more robust to path that contain symbolic links.
- symlinks to subdatasets of a dataset are now correctly treated as a symlink,
  and not as a subdataset
- `add` now correctly saves staged subdataset additions.
- Running `datalad save` in a dataset no longer adds untracked content to the
  dataset. In order to add content a path has to be given, e.g. `datalad save .`
- `wtf` now works reliably with a DataLad that wasn't installed from Git (but,
  e.g., via pip)
- More robust URL handling in `simple_with_archives` crawler pipeline.

### Enhancements and new features

- Support for DataLad extension that can contribute API components from 3rd-party sources,
  incl. commands, metadata extractors, and test case implementations.
  See https://github.com/datalad/datalad-extension-template for a demo extension.
- Metadata (everything has changed!)
  - Metadata extraction and aggregation is now supported for datasets and individual
    files.
  - Metadata query via `search` can now discover individual files.
  - Extracted metadata can now be stored in XZ compressed files, is optionally
    annexed (when exceeding a configurable size threshold), and obtained on
    demand (new configuration option `datalad.metadata.create-aggregate-annex-limit`).
  - Status and availability of aggregated metadata can now be reported via
    `metadata --get-aggregates`
  - New configuration option `datalad.metadata.maxfieldsize` to exclude too large
    metadata fields from aggregation.
  - The type of metadata is no longer guessed during metadata extraction. A new
    configuration option `datalad.metadata.nativetype` was introduced to enable
    one or more particular metadata extractors for a dataset.
  - New configuration option `datalad.metadata.store-aggregate-content` to enable
    the storage of aggregated metadata for dataset content (i.e. file-based metadata)
    in contrast to just metadata describing a dataset as a whole.
- `search` was completely reimplemented. It offers three different modes now:
  - 'egrep' (default): expression matching in a plain string version of metadata
  - 'textblob': search a text version of all metadata using a fully featured
     query language (fast indexing, good for keyword search)
  - 'autofield': search an auto-generated index that preserves individual fields
     of metadata that can be represented in a tabular structure (substantial
     indexing cost, enables the most detailed queries of all modes)
- New extensions:
  - [addurls][], an extension for creating a dataset (and possibly subdatasets)
    from a list of URLs.
  - export_to_figshare
  - extract_metadata
- add_readme makes use of available metadata
- By default the wtf extension now hides sensitive information, which can be
  included in the output by passing `--senstive=some` or `--senstive=all`.
- Reduced startup latency by only importing commands necessary for a particular
  command line call.
- [create][]:
  - `-d <parent> --nosave` now registers subdatasets, when possible.
  - `--fake-dates` configures dataset to use fake-dates
- [run][] now provides a way for the caller to save the result when a
  command has a non-zero exit status.
- `datalad rerun` now has a `--script` option that can be used to extract
  previous commands into a file.
- A DataLad Singularity container is now available on
  [Singularity Hub](https://singularity-hub.org/collections/667).
- More casts have been embedded in the [use case section of the documentation](http://docs.datalad.org/en/docs/usecases/index.html).
- `datalad --report-status` has a new value 'all' that can be used to
  temporarily re-enable reporting that was disable by configuration settings.


## 0.9.3 (Mar 16, 2018) -- pi+0.02 release

Some important bug fixes which should improve usability

### Fixes

- `datalad-archives` special remote now will lock on acquiring or
  extracting an archive - this allows for it to be used with -J flag
  for parallel operation
- relax introduced in 0.9.2 demand on git being configured for datalad
  operation - now we will just issue a warning
- `datalad ls` should now list "authored date" and work also for datasets
  in detached HEAD mode
- `datalad save` will now save original file as well, if file was
  "git mv"ed, so you can now `datalad run git mv old new` and have
  changes recorded

### Enhancements and new features

- `--jobs` argument now could take `auto` value which would decide on
  # of jobs depending on the # of available CPUs.
  `git-annex` > 6.20180314 is recommended to avoid regression with -J.
- memoize calls to `RI` meta-constructor -- should speed up operation a
  bit
- `DATALAD_SEED` environment variable could be used to seed Python RNG
  and provide reproducible UUIDs etc (useful for testing and demos)


## 0.9.2 (Mar 04, 2018) -- it is (again) better than ever

Largely a bugfix release with a few enhancements.

### Fixes

- Execution of external commands (git) should not get stuck when
  lots of both stdout and stderr output, and should not loose remaining
  output in some cases
- Config overrides provided in the command line (-c) should now be
  handled correctly
- Consider more remotes (not just tracking one, which might be none)
  while installing subdatasets
- Compatibility with git 2.16 with some changed behaviors/annotations
  for submodules
- Fail `remove` if `annex drop` failed
- Do not fail operating on files which start with dash (-)
- URL unquote paths within S3, URLs and DataLad RIs (///)
- In non-interactive mode fail if authentication/access fails
- Web UI:
  - refactored a little to fix incorrect listing of submodules in
    subdirectories
  - now auto-focuses on search edit box upon entering the page
- Assure that extracted from tarballs directories have executable bit set

### Enhancements and new features

- A log message and progress bar will now inform if a tarball to be
  downloaded while getting specific files
  (requires git-annex > 6.20180206)
- A dedicated `datalad rerun` command capable of rerunning entire
  sequences of previously `run` commands.
  **Reproducibility through VCS. Use `run` even if not interested in `rerun`**
- Alert the user if `git` is not yet configured but git operations
  are requested
- Delay collection of previous ssh connections until it is actually
  needed.  Also do not require ':' while specifying ssh host
- AutomagicIO: Added proxying of isfile, lzma.LZMAFile and io.open
- Testing:
  - added DATALAD_DATASETS_TOPURL=http://datasets-tests.datalad.org to
    run tests against another website to not obscure access stats
  - tests run against temporary HOME to avoid side-effects
  - better unit-testing of interactions with special remotes
- CONTRIBUTING.md describes how to setup and use `git-hub` tool to
  "attach" commits to an issue making it into a PR
- DATALAD_USE_DEFAULT_GIT env variable could be used to cause DataLad
  to use default (not the one possibly bundled with git-annex) git
- Be more robust while handling not supported requests by annex in
  special remotes
- Use of `swallow_logs` in the code was refactored away -- less
  mysteries now, just increase logging level
- `wtf` plugin will report more information about environment, externals
  and the system


## 0.9.1 (Oct 01, 2017) -- "DATALAD!"(JBTM)

Minor bugfix release

### Fixes

- Should work correctly with subdatasets named as numbers of bool
  values (requires also GitPython >= 2.1.6)
- Custom special remotes should work without crashing with 
  git-annex >= 6.20170924


## 0.9.0 (Sep 19, 2017) -- isn't it a lucky day even though not a Friday?

### Major refactoring and deprecations

- the `files` argument of [save][] has been renamed to `path` to be uniform with
  any other command
- all major commands now implement more uniform API semantics and result reporting.
  Functionality for modification detection of dataset content has been completely replaced
  with a more efficient implementation
- [publish][] now features a `--transfer-data` switch that allows for a
  disambiguous specification of whether to publish data -- independent of
  the selection which datasets to publish (which is done via their paths).
  Moreover, [publish][] now transfers data before repository content is pushed.

### Fixes

- [drop][] no longer errors when some subdatasets are not installed
- [install][] will no longer report nothing when a Dataset instance was
  given as a source argument, but rather perform as expected
- [remove][] doesn't remove when some files of a dataset could not be dropped
- [publish][] 
  - no longer hides error during a repository push
  - publish behaves "correctly" for `--since=` in considering only the
    differences the last "pushed" state
  - data transfer handling while publishing with dependencies, to github
- improved robustness with broken Git configuration
- [search][] should search for unicode strings correctly and not crash
- robustify git-annex special remotes protocol handling to allow for spaces in
  the last argument
- UI credentials interface should now allow to Ctrl-C the entry
- should not fail while operating on submodules named with
  numerics only or by bool (true/false) names
- crawl templates should not now override settings for `largefiles` if 
  specified in `.gitattributes`


### Enhancements and new features

- **Exciting new feature** [run][] command to protocol execution of an external 
  command and rerun computation if desired. 
  See [screencast](http://datalad.org/features.html#reproducible-science)
- [save][] now uses Git for detecting with sundatasets need to be inspected for
  potential changes, instead of performing a complete traversal of a dataset tree
- [add][] looks for changes relative to the last commited state of a dataset
  to discover files to add more efficiently
- [diff][] can now report untracked files in addition to modified files
- [uninstall][] will check itself whether a subdataset is properly registered in a
  superdataset, even when no superdataset is given in a call
- [subdatasets][] can now configure subdatasets for exclusion from recursive
  installation (`datalad-recursiveinstall` submodule configuration property)
- precrafted pipelines of [crawl][] now will not override `annex.largefiles`
  setting if any was set within `.gitattribues` (e.g. by `datalad create --text-no-annex`)
- framework for screencasts: `tools/cast*` tools and sample cast scripts under
  `doc/casts` which are published at [datalad.org/features.html](http://datalad.org/features.html)
- new [project YouTube channel](https://www.youtube.com/channel/UCB8-Zf7D0DSzAsREoIt0Bvw) 
- tests failing in direct and/or v6 modes marked explicitly

## 0.8.1 (Aug 13, 2017) -- the best birthday gift

Bugfixes

### Fixes

- Do not attempt to [update][] a not installed sub-dataset
- In case of too many files to be specified for [get][] or [copy_to][], we
  will make multiple invocations of underlying git-annex command to not
  overfill command line
- More robust handling of unicode output in terminals which might not support it

### Enhancements and new features

- Ship a copy of numpy.testing to facilitate [test][] without requiring numpy
  as dependency. Also allow to pass to command which test(s) to run
- In [get][] and [copy_to][] provide actual original requested paths, not the
  ones we deduced need to be transferred, solely for knowing the total


## 0.8.0 (Jul 31, 2017) -- it is better than ever

A variety of fixes and enhancements

### Fixes

- [publish][] would now push merged `git-annex` branch even if no other changes
  were done
- [publish][] should be able to publish using relative path within SSH URI
  (git hook would use relative paths)
- [publish][] should better tollerate publishing to pure git and `git-annex` 
  special remotes 

### Enhancements and new features

- [plugin][] mechanism came to replace [export][]. See [export_tarball][] for the
  replacement of [export][].  Now it should be easy to extend datalad's interface
  with custom functionality to be invoked along with other commands.
- Minimalistic coloring of the results rendering
- [publish][]/`copy_to` got progress bar report now and support of `--jobs`
- minor fixes and enhancements to crawler (e.g. support of recursive removes)


## 0.7.0 (Jun 25, 2017) -- when it works - it is quite awesome!

New features, refactorings, and bug fixes.

### Major refactoring and deprecations

- [add-sibling][] has been fully replaced by the [siblings][] command
- [create-sibling][], and [unlock][] have been re-written to support the
  same common API as most other commands

### Enhancements and new features

- [siblings][] can now be used to query and configure a local repository by
  using the sibling name ``here``
- [siblings][] can now query and set annex preferred content configuration. This
  includes ``wanted`` (as previously supported in other commands), and now
  also ``required``
- New [metadata][] command to interface with datasets/files [meta-data][] 
- Documentation for all commands is now built in a uniform fashion
- Significant parts of the documentation of been updated
- Instantiate GitPython's Repo instances lazily

### Fixes

- API documentation is now rendered properly as HTML, and is easier to browse by
  having more compact pages
- Closed files left open on various occasions (Popen PIPEs, etc)
- Restored basic (consumer mode of operation) compatibility with Windows OS 


## 0.6.0 (Jun 14, 2017) -- German perfectionism

This release includes a **huge** refactoring to make code base and functionality
more robust and flexible

- outputs from API commands could now be highly customized.  See
  `--output-format`, `--report-status`, `--report-type`, and `--report-type`
  options for [datalad][] command.
- effort was made to refactor code base so that underlying functions behave as
  generators where possible
- input paths/arguments analysis was redone for majority of the commands to provide
  unified behavior

### Major refactoring and deprecations

- `add-sibling` and `rewrite-urls` were refactored in favor of new [siblings][]
  command which should be used for siblings manipulations
- 'datalad.api.alwaysrender' config setting/support is removed in favor of new
  outputs processing

### Fixes

- Do not flush manually git index in pre-commit to avoid "Death by the Lock" issue
- Deployed by [publish][] `post-update` hook script now should be more robust
  (tolerate directory names with spaces, etc.)
- A variety of fixes, see
  [list of pull requests and issues closed](https://github.com/datalad/datalad/milestone/41?closed=1)
  for more information

### Enhancements and new features

- new [annotate-paths][] plumbing command to inspect and annotate provided
  paths.  Use `--modified` to summarize changes between different points in
  the history
- new [clone][] plumbing command to provide a subset (install a single dataset
  from a URL) functionality of [install][]
- new [diff][] plumbing command
- new [siblings][] command to list or manipulate siblings
- new [subdatasets][] command to list subdatasets and their properties
- [drop][] and [remove][] commands were refactored
- `benchmarks/` collection of [Airspeed velocity](https://github.com/spacetelescope/asv/)
  benchmarks initiated.  See reports at http://datalad.github.io/datalad/
- crawler would try to download a new url multiple times increasing delay between
  attempts.  Helps to resolve problems with extended crawls of Amazon S3
- [CRCNS][] crawler pipeline now also fetches and aggregates meta-data for the
  datasets from datacite
- overall optimisations to benefit from the aforementioned refactoring and
  improve user-experience
- a few stub and not (yet) implemented commands (e.g. `move`) were removed from
  the interface
- Web frontend got proper coloring for the breadcrumbs and some additional
  caching to speed up interactions.  See http://datasets.datalad.org
- Small improvements to the online documentation.  See e.g.
  [summary of differences between git/git-annex/datalad](http://docs.datalad.org/en/latest/related.html#git-git-annex-datalad)

## 0.5.1 (Mar 25, 2017) -- cannot stop the progress

A bugfix release

### Fixes

- [add][] was forcing addition of files to annex regardless of settings
  in `.gitattributes`.  Now that decision is left to annex by default
- `tools/testing/run_doc_examples` used to run
  doc examples as tests, fixed up to provide status per each example
  and not fail at once
- `doc/examples`
  - [3rdparty_analysis_workflow.sh](http://docs.datalad.org/en/latest/generated/examples/3rdparty_analysis_workflow.html)
    was fixed up to reflect changes in the API of 0.5.0.
- progress bars
  - should no longer crash **datalad** and report correct sizes and speeds
  - should provide progress reports while using Python 3.x

### Enhancements and new features

- `doc/examples`
  - [nipype_workshop_dataset.sh](http://docs.datalad.org/en/latest/generated/examples/nipype_workshop_dataset.html)
    new example to demonstrate how new super- and sub- datasets were established
    as a part of our datasets collection


## 0.5.0 (Mar 20, 2017) -- it's huge

This release includes an avalanche of bug fixes, enhancements, and
additions which at large should stay consistent with previous behavior
but provide better functioning.  Lots of code was refactored to provide
more consistent code-base, and some API breakage has happened.  Further
work is ongoing to standardize output and results reporting
([#1350][])

### Most notable changes

- requires [git-annex][] >= 6.20161210 (or better even >= 6.20161210 for
  improved functionality)
- commands should now operate on paths specified (if any), without
  causing side-effects on other dirty/staged files
- [save][]
    - `-a` is deprecated in favor of `-u` or `--all-updates`
      so only changes known components get saved, and no new files
      automagically added
    - `-S` does no longer store the originating dataset in its commit
       message
- [add][]
    - can specify commit/save message with `-m`
- [add-sibling][] and [create-sibling][]
    - now take the name of the sibling (remote) as a `-s` (`--name`)
      option, not a positional argument
    - `--publish-depends` to setup publishing data and code to multiple
      repositories (e.g. github + webserve) should now be functional
      see [this comment](https://github.com/datalad/datalad/issues/335#issuecomment-277240733)
    - got `--publish-by-default` to specify what refs should be published
      by default
    - got `--annex-wanted`, `--annex-groupwanted` and `--annex-group`
      settings which would be used to instruct annex about preferred
      content. [publish][] then will publish data using those settings if
      `wanted` is set.
    - got `--inherit` option to automagically figure out url/wanted and
      other git/annex settings for new remote sub-dataset to be constructed
- [publish][]
    - got `--skip-failing` refactored into `--missing` option
      which could use new feature of [create-sibling][] `--inherit`

### Fixes

- More consistent interaction through ssh - all ssh connections go
  through [sshrun][] shim for a "single point of authentication", etc.
- More robust [ls][] operation outside of the datasets
- A number of fixes for direct and v6 mode of annex

### Enhancements and new features

- New [drop][] and [remove][] commands
- [clean][]
    - got `--what` to specify explicitly what cleaning steps to perform
      and now could be invoked with `-r`
- `datalad` and `git-annex-remote*` scripts now do not use setuptools
  entry points mechanism and rely on simple import to shorten start up time
- [Dataset][] is also now using [Flyweight pattern][], so the same instance is
  reused for the same dataset
- progressbars should not add more empty lines

### Internal refactoring

- Majority of the commands now go through `_prep` for arguments validation
  and pre-processing to avoid recursive invocations


## 0.4.1 (Nov 10, 2016) -- CA release

Requires now GitPython >= 2.1.0

### Fixes

- [save][]
     - to not save staged files if explicit paths were provided
- improved (but not yet complete) support for direct mode
- [update][] to not crash if some sub-datasets are not installed
- do not log calls to `git config` to avoid leakage of possibly 
  sensitive settings to the logs

### Enhancements and new features

- New [rfc822-compliant metadata][] format
- [save][]
    - -S to save the change also within all super-datasets
- [add][] now has progress-bar reporting
- [create-sibling-github][] to create a :term:`sibling` of a dataset on
  github
- [OpenfMRI][] crawler and datasets were enriched with URLs to separate
  files where also available from openfmri s3 bucket
  (if upgrading your datalad datasets, you might need to run
  `git annex enableremote datalad` to make them available)
- various enhancements to log messages
- web interface
    - populates "install" box first thus making UX better over slower
      connections


## 0.4 (Oct 22, 2016) -- Paris is waiting

Primarily it is a bugfix release but because of significant refactoring
of the [install][] and [get][] implementation, it gets a new minor release. 

### Fixes

- be able to [get][] or [install][] while providing paths while being 
  outside of a dataset
- remote annex datasets get properly initialized
- robust detection of outdated [git-annex][]

### Enhancements and new features

- interface changes
    - [get][] `--recursion-limit=existing` to not recurse into not-installed
       subdatasets
    - [get][] `-n` to possibly install sub-datasets without getting any data
    - [install][] `--jobs|-J` to specify number of parallel jobs for annex 
      [get][] call could use (ATM would not work when data comes from archives)
- more (unit-)testing
- documentation: see http://docs.datalad.org/en/latest/basics.html
  for basic principles and useful shortcuts in referring to datasets
- various webface improvements:  breadcrumb paths, instructions how
  to install dataset, show version from the tags, etc.

## 0.3.1 (Oct 1, 2016) -- what a wonderful week

Primarily bugfixes but also a number of enhancements and core
refactorings

### Fixes

- do not build manpages and examples during installation to avoid
  problems with possibly previously outdated dependencies
- [install][] can be called on already installed dataset (with `-r` or
  `-g`)

### Enhancements and new features

- complete overhaul of datalad configuration settings handling
  (see [Configuration documentation][]), so majority of the environment.
  Now uses git format and stores persistent configuration settings under
  `.datalad/config` and local within `.git/config`
  variables we have used were renamed to match configuration names
- [create-sibling][] does not now by default upload web front-end
- [export][] command with a plug-in interface and `tarball` plugin to export
  datasets
- in Python, `.api` functions with rendering of results in command line
  got a _-suffixed sibling, which would render results as well in Python
  as well (e.g., using `search_` instead of `search` would also render
  results, not only output them back as Python objects)
- [get][]
    - `--jobs` option (passed to `annex get`) for parallel downloads
    - total and per-download (with git-annex >= 6.20160923) progress bars
      (note that if content is to be obtained from an archive, no progress
      will be reported yet)
- [install][] `--reckless` mode option
- [search][]
    - highlights locations and fieldmaps for better readability
    - supports `-d^` or `-d///` to point to top-most or centrally
      installed meta-datasets
    - "complete" paths to the datasets are reported now
    - `-s` option to specify which fields (only) to search
- various enhancements and small fixes to [meta-data][] handling, [ls][],
  custom remotes, code-base formatting, downloaders, etc
- completely switched to `tqdm` library (`progressbar` is no longer
  used/supported)


## 0.3 (Sep 23, 2016) -- winter is coming

Lots of everything, including but not limited to

- enhanced index viewer, as the one on http://datasets.datalad.org
- initial new data providers support: [Kaggle][], [BALSA][], [NDA][], [NITRC][]
- initial [meta-data support and management][]
- new and/or improved crawler pipelines for [BALSA][], [CRCNS][], [OpenfMRI][]
- refactored [install][] command, now with separate [get][]
- some other commands renaming/refactoring (e.g., [create-sibling][])
- datalad [search][] would give you an option to install datalad's 
  super-dataset under ~/datalad if ran outside of a dataset

### 0.2.3 (Jun 28, 2016) -- busy OHBM

New features and bugfix release

- support of /// urls to point to http://datasets.datalad.org
- variety of fixes and enhancements throughout

### 0.2.2 (Jun 20, 2016) -- OHBM we are coming!

New feature and bugfix release

- greately improved documentation
- publish command API RFing allows for custom options to annex, and uses
  --to REMOTE for consistent with annex invocation
- variety of fixes and enhancements throughout

### 0.2.1 (Jun 10, 2016)

- variety of fixes and enhancements throughout

## 0.2 (May 20, 2016)

Major RFing to switch from relying on rdf to git native submodules etc

## 0.1 (Oct 14, 2015)

Release primarily focusing on interface functionality including initial
publishing

[git-annex]: http://git-annex.branchable.com/
[gx-sameas]: https://git-annex.branchable.com/tips/multiple_remotes_accessing_the_same_data_store/
[duecredit]: https://github.com/duecredit/duecredit

[Kaggle]: https://www.kaggle.com
[BALSA]: http://balsa.wustl.edu
[NDA]: http://data-archive.nimh.nih.gov
[NITRC]: https://www.nitrc.org
[CRCNS]: http://crcns.org
[FCON1000]: http://fcon_1000.projects.nitrc.org
[OpenfMRI]: http://openfmri.org

[Configuration documentation]: http://docs.datalad.org/config.html

[Dataset]: http://docs.datalad.org/en/latest/generated/datalad.api.Dataset.html
[Sibling]: http://docs.datalad.org/en/latest/glossary.html

[rfc822-compliant metadata]: http://docs.datalad.org/en/latest/metadata.html#rfc822-compliant-meta-data
[meta-data support and management]: http://docs.datalad.org/en/latest/cmdline.html#meta-data-handling
[meta-data]: http://docs.datalad.org/en/latest/cmdline.html#meta-data-handling

[add-archive-content]: https://datalad.readthedocs.io/en/latest/generated/man/datalad-add-archive-content.html
[add-sibling]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-add-sibling.html
[add]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-add.html
[addurls]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-addurls.html
[annotate-paths]: http://docs.datalad.org/en/latest/generated/man/datalad-annotate-paths.html
[clean]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-clean.html
[clone]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html
[configuration]: http://docs.datalad.org/en/latest/config.html
[copy-file]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-copy-file.html
[copy_to]: http://docs.datalad.org/en/latest/_modules/datalad/support/annexrepo.html?highlight=%22copy_to%22
[create]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-create.html
[create-sibling-github]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-github.html
[create-sibling-ria]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-ria.html
[create-sibling]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html
[datalad]: http://docs.datalad.org/en/latest/generated/man/datalad.html
[datalad-container]: https://github.com/datalad/datalad-container
[datalad-revolution]: http://github.com/datalad/datalad-revolution
[download-url]: https://datalad.readthedocs.io/en/latest/generated/man/datalad-download-url.html
[diff]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-diff.html
[drop]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-drop.html
[export-archive-ora]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-export-archive-ora.html
[export]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-export.html
[export_tarball]: http://docs.datalad.org/en/latest/generated/datalad.plugin.export_tarball.html
[get]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html
[install]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html
[ls]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-ls.html
[metadata]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-metadata.html
[nd_freeze]: https://github.com/neurodebian/neurodebian/blob/master/tools/nd_freeze
[plugin]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-plugin.html
[publications]: https://datalad.readthedocs.io/en/latest/publications.html
[publish]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html
[push]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-push.html
[remove]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-remove.html
[rerun]: https://datalad.readthedocs.io/en/latest/generated/man/datalad-rerun.html
[run]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html
[run-procedure]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-run-procedure.html
[save]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html
[search]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html
[siblings]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html
[sshrun]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-sshrun.html
[status]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-status.html
[subdatasets]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-subdatasets.html
[unlock]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-unlock.html
[update]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html
[wtf]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-wtf.html

[handbook]: http://handbook.datalad.org
[handbook-scalable-datastore]: http://handbook.datalad.org/en/latest/usecases/datastorage_for_institutions.html
[hooks]: http://handbook.datalad.org/en/latest/basics/101-145-hooks.html
[Flyweight pattern]: https://en.wikipedia.org/wiki/Flyweight_pattern
[NO_COLOR]: https://no-color.org/

[#1350]: https://github.com/datalad/datalad/issues/1350
[#1651]: https://github.com/datalad/datalad/issues/1651
[#2534]: https://github.com/datalad/datalad/issues/2534
[#2566]: https://github.com/datalad/datalad/issues/2566
[#2692]: https://github.com/datalad/datalad/issues/2692
[#2702]: https://github.com/datalad/datalad/issues/2702
[#2703]: https://github.com/datalad/datalad/issues/2703
[#2707]: https://github.com/datalad/datalad/issues/2707
[#2708]: https://github.com/datalad/datalad/issues/2708
[#2710]: https://github.com/datalad/datalad/issues/2710
[#2712]: https://github.com/datalad/datalad/issues/2712
[#2717]: https://github.com/datalad/datalad/issues/2717
[#2722]: https://github.com/datalad/datalad/issues/2722
[#2723]: https://github.com/datalad/datalad/issues/2723
[#2724]: https://github.com/datalad/datalad/issues/2724
[#2725]: https://github.com/datalad/datalad/issues/2725
[#2728]: https://github.com/datalad/datalad/issues/2728
[#2731]: https://github.com/datalad/datalad/issues/2731
[#2733]: https://github.com/datalad/datalad/issues/2733
[#2735]: https://github.com/datalad/datalad/issues/2735
[#2738]: https://github.com/datalad/datalad/issues/2738
[#2741]: https://github.com/datalad/datalad/issues/2741
[#2744]: https://github.com/datalad/datalad/issues/2744
[#2752]: https://github.com/datalad/datalad/issues/2752
[#2754]: https://github.com/datalad/datalad/issues/2754
[#2761]: https://github.com/datalad/datalad/issues/2761
[#2770]: https://github.com/datalad/datalad/issues/2770
[#2773]: https://github.com/datalad/datalad/issues/2773
[#2777]: https://github.com/datalad/datalad/issues/2777
[#2788]: https://github.com/datalad/datalad/issues/2788
[#2794]: https://github.com/datalad/datalad/issues/2794
[#2795]: https://github.com/datalad/datalad/issues/2795
[#2796]: https://github.com/datalad/datalad/issues/2796
[#2798]: https://github.com/datalad/datalad/issues/2798
[#2815]: https://github.com/datalad/datalad/issues/2815
[#2835]: https://github.com/datalad/datalad/issues/2835
[#2858]: https://github.com/datalad/datalad/issues/2858
[#2859]: https://github.com/datalad/datalad/issues/2859
[#2860]: https://github.com/datalad/datalad/issues/2860
[#2861]: https://github.com/datalad/datalad/issues/2861
[#2864]: https://github.com/datalad/datalad/issues/2864
[#2865]: https://github.com/datalad/datalad/issues/2865
[#2876]: https://github.com/datalad/datalad/issues/2876
[#2878]: https://github.com/datalad/datalad/issues/2878
[#2881]: https://github.com/datalad/datalad/issues/2881
[#2886]: https://github.com/datalad/datalad/issues/2886
[#2891]: https://github.com/datalad/datalad/issues/2891
[#2892]: https://github.com/datalad/datalad/issues/2892
[#2893]: https://github.com/datalad/datalad/issues/2893
[#2894]: https://github.com/datalad/datalad/issues/2894
[#2897]: https://github.com/datalad/datalad/issues/2897
[#2900]: https://github.com/datalad/datalad/issues/2900
[#2901]: https://github.com/datalad/datalad/issues/2901
[#2902]: https://github.com/datalad/datalad/issues/2902
[#2903]: https://github.com/datalad/datalad/issues/2903
[#2904]: https://github.com/datalad/datalad/issues/2904
[#2905]: https://github.com/datalad/datalad/issues/2905
[#2909]: https://github.com/datalad/datalad/issues/2909
[#2912]: https://github.com/datalad/datalad/issues/2912
[#2914]: https://github.com/datalad/datalad/issues/2914
[#2917]: https://github.com/datalad/datalad/issues/2917
[#2918]: https://github.com/datalad/datalad/issues/2918
[#2921]: https://github.com/datalad/datalad/issues/2921
[#2922]: https://github.com/datalad/datalad/issues/2922
[#2937]: https://github.com/datalad/datalad/issues/2937
[#2946]: https://github.com/datalad/datalad/issues/2946
[#2950]: https://github.com/datalad/datalad/issues/2950
[#2952]: https://github.com/datalad/datalad/issues/2952
[#2954]: https://github.com/datalad/datalad/issues/2954
[#2958]: https://github.com/datalad/datalad/issues/2958
[#2960]: https://github.com/datalad/datalad/issues/2960
[#2972]: https://github.com/datalad/datalad/issues/2972
[#2974]: https://github.com/datalad/datalad/issues/2974
[#2982]: https://github.com/datalad/datalad/issues/2982
[#2984]: https://github.com/datalad/datalad/issues/2984
[#2991]: https://github.com/datalad/datalad/issues/2991
[#2993]: https://github.com/datalad/datalad/issues/2993
[#2995]: https://github.com/datalad/datalad/issues/2995
[#3001]: https://github.com/datalad/datalad/issues/3001
[#3002]: https://github.com/datalad/datalad/issues/3002
[#3007]: https://github.com/datalad/datalad/issues/3007
[#3009]: https://github.com/datalad/datalad/issues/3009
[#3019]: https://github.com/datalad/datalad/issues/3019
[#3025]: https://github.com/datalad/datalad/issues/3025
[#3029]: https://github.com/datalad/datalad/issues/3029
[#3035]: https://github.com/datalad/datalad/issues/3035
[#3037]: https://github.com/datalad/datalad/issues/3037
[#3038]: https://github.com/datalad/datalad/issues/3038
[#3046]: https://github.com/datalad/datalad/issues/3046
[#3049]: https://github.com/datalad/datalad/issues/3049
[#3051]: https://github.com/datalad/datalad/issues/3051
[#3057]: https://github.com/datalad/datalad/issues/3057
[#3058]: https://github.com/datalad/datalad/issues/3058
[#3061]: https://github.com/datalad/datalad/issues/3061
[#3065]: https://github.com/datalad/datalad/issues/3065
[#3066]: https://github.com/datalad/datalad/issues/3066
[#3080]: https://github.com/datalad/datalad/issues/3080
[#3089]: https://github.com/datalad/datalad/issues/3089
[#3091]: https://github.com/datalad/datalad/issues/3091
[#3098]: https://github.com/datalad/datalad/issues/3098
[#3099]: https://github.com/datalad/datalad/issues/3099
[#3102]: https://github.com/datalad/datalad/issues/3102
[#3104]: https://github.com/datalad/datalad/issues/3104
[#3106]: https://github.com/datalad/datalad/issues/3106
[#3109]: https://github.com/datalad/datalad/issues/3109
[#3115]: https://github.com/datalad/datalad/issues/3115
[#3119]: https://github.com/datalad/datalad/issues/3119
[#3124]: https://github.com/datalad/datalad/issues/3124
[#3129]: https://github.com/datalad/datalad/issues/3129
[#3137]: https://github.com/datalad/datalad/issues/3137
[#3138]: https://github.com/datalad/datalad/issues/3138
[#3141]: https://github.com/datalad/datalad/issues/3141
[#3146]: https://github.com/datalad/datalad/issues/3146
[#3149]: https://github.com/datalad/datalad/issues/3149
[#3156]: https://github.com/datalad/datalad/issues/3156
[#3164]: https://github.com/datalad/datalad/issues/3164
[#3165]: https://github.com/datalad/datalad/issues/3165
[#3168]: https://github.com/datalad/datalad/issues/3168
[#3176]: https://github.com/datalad/datalad/issues/3176
[#3180]: https://github.com/datalad/datalad/issues/3180
[#3181]: https://github.com/datalad/datalad/issues/3181
[#3184]: https://github.com/datalad/datalad/issues/3184
[#3186]: https://github.com/datalad/datalad/issues/3186
[#3196]: https://github.com/datalad/datalad/issues/3196
[#3205]: https://github.com/datalad/datalad/issues/3205
[#3210]: https://github.com/datalad/datalad/issues/3210
[#3211]: https://github.com/datalad/datalad/issues/3211
[#3215]: https://github.com/datalad/datalad/issues/3215
[#3220]: https://github.com/datalad/datalad/issues/3220
[#3222]: https://github.com/datalad/datalad/issues/3222
[#3223]: https://github.com/datalad/datalad/issues/3223
[#3238]: https://github.com/datalad/datalad/issues/3238
[#3241]: https://github.com/datalad/datalad/issues/3241
[#3242]: https://github.com/datalad/datalad/issues/3242
[#3249]: https://github.com/datalad/datalad/issues/3249
[#3250]: https://github.com/datalad/datalad/issues/3250
[#3255]: https://github.com/datalad/datalad/issues/3255
[#3258]: https://github.com/datalad/datalad/issues/3258
[#3259]: https://github.com/datalad/datalad/issues/3259
[#3268]: https://github.com/datalad/datalad/issues/3268
[#3274]: https://github.com/datalad/datalad/issues/3274
[#3281]: https://github.com/datalad/datalad/issues/3281
[#3288]: https://github.com/datalad/datalad/issues/3288
[#3289]: https://github.com/datalad/datalad/issues/3289
[#3294]: https://github.com/datalad/datalad/issues/3294
[#3298]: https://github.com/datalad/datalad/issues/3298
[#3299]: https://github.com/datalad/datalad/issues/3299
[#3301]: https://github.com/datalad/datalad/issues/3301
[#3304]: https://github.com/datalad/datalad/issues/3304
[#3314]: https://github.com/datalad/datalad/issues/3314
[#3318]: https://github.com/datalad/datalad/issues/3318
[#3322]: https://github.com/datalad/datalad/issues/3322
[#3324]: https://github.com/datalad/datalad/issues/3324
[#3325]: https://github.com/datalad/datalad/issues/3325
[#3326]: https://github.com/datalad/datalad/issues/3326
[#3329]: https://github.com/datalad/datalad/issues/3329
[#3330]: https://github.com/datalad/datalad/issues/3330
[#3332]: https://github.com/datalad/datalad/issues/3332
[#3334]: https://github.com/datalad/datalad/issues/3334
[#3336]: https://github.com/datalad/datalad/issues/3336
[#3340]: https://github.com/datalad/datalad/issues/3340
[#3343]: https://github.com/datalad/datalad/issues/3343
[#3347]: https://github.com/datalad/datalad/issues/3347
[#3353]: https://github.com/datalad/datalad/issues/3353
[#3362]: https://github.com/datalad/datalad/issues/3362
[#3364]: https://github.com/datalad/datalad/issues/3364
[#3365]: https://github.com/datalad/datalad/issues/3365
[#3366]: https://github.com/datalad/datalad/issues/3366
[#3374]: https://github.com/datalad/datalad/issues/3374
[#3378]: https://github.com/datalad/datalad/issues/3378
[#3383]: https://github.com/datalad/datalad/issues/3383
[#3396]: https://github.com/datalad/datalad/issues/3396
[#3398]: https://github.com/datalad/datalad/issues/3398
[#3400]: https://github.com/datalad/datalad/issues/3400
[#3401]: https://github.com/datalad/datalad/issues/3401
[#3403]: https://github.com/datalad/datalad/issues/3403
[#3407]: https://github.com/datalad/datalad/issues/3407
[#3425]: https://github.com/datalad/datalad/issues/3425
[#3429]: https://github.com/datalad/datalad/issues/3429
[#3435]: https://github.com/datalad/datalad/issues/3435
[#3439]: https://github.com/datalad/datalad/issues/3439
[#3440]: https://github.com/datalad/datalad/issues/3440
[#3444]: https://github.com/datalad/datalad/issues/3444
[#3447]: https://github.com/datalad/datalad/issues/3447
[#3458]: https://github.com/datalad/datalad/issues/3458
[#3459]: https://github.com/datalad/datalad/issues/3459
[#3460]: https://github.com/datalad/datalad/issues/3460
[#3470]: https://github.com/datalad/datalad/issues/3470
[#3475]: https://github.com/datalad/datalad/issues/3475
[#3476]: https://github.com/datalad/datalad/issues/3476
[#3479]: https://github.com/datalad/datalad/issues/3479
[#3492]: https://github.com/datalad/datalad/issues/3492
[#3493]: https://github.com/datalad/datalad/issues/3493
[#3498]: https://github.com/datalad/datalad/issues/3498
[#3499]: https://github.com/datalad/datalad/issues/3499
[#3508]: https://github.com/datalad/datalad/issues/3508
[#3516]: https://github.com/datalad/datalad/issues/3516
[#3518]: https://github.com/datalad/datalad/issues/3518
[#3524]: https://github.com/datalad/datalad/issues/3524
[#3525]: https://github.com/datalad/datalad/issues/3525
[#3527]: https://github.com/datalad/datalad/issues/3527
[#3531]: https://github.com/datalad/datalad/issues/3531
[#3534]: https://github.com/datalad/datalad/issues/3534
[#3538]: https://github.com/datalad/datalad/issues/3538
[#3546]: https://github.com/datalad/datalad/issues/3546
[#3547]: https://github.com/datalad/datalad/issues/3547
[#3552]: https://github.com/datalad/datalad/issues/3552
[#3555]: https://github.com/datalad/datalad/issues/3555
[#3561]: https://github.com/datalad/datalad/issues/3561
[#3562]: https://github.com/datalad/datalad/issues/3562
[#3570]: https://github.com/datalad/datalad/issues/3570
[#3574]: https://github.com/datalad/datalad/issues/3574
[#3576]: https://github.com/datalad/datalad/issues/3576
[#3579]: https://github.com/datalad/datalad/issues/3579
[#3582]: https://github.com/datalad/datalad/issues/3582
[#3586]: https://github.com/datalad/datalad/issues/3586
[#3587]: https://github.com/datalad/datalad/issues/3587
[#3591]: https://github.com/datalad/datalad/issues/3591
[#3594]: https://github.com/datalad/datalad/issues/3594
[#3597]: https://github.com/datalad/datalad/issues/3597
[#3600]: https://github.com/datalad/datalad/issues/3600
[#3602]: https://github.com/datalad/datalad/issues/3602
[#3616]: https://github.com/datalad/datalad/issues/3616
[#3622]: https://github.com/datalad/datalad/issues/3622
[#3624]: https://github.com/datalad/datalad/issues/3624
[#3626]: https://github.com/datalad/datalad/issues/3626
[#3629]: https://github.com/datalad/datalad/issues/3629
[#3631]: https://github.com/datalad/datalad/issues/3631
[#3646]: https://github.com/datalad/datalad/issues/3646
[#3648]: https://github.com/datalad/datalad/issues/3648
[#3656]: https://github.com/datalad/datalad/issues/3656
[#3667]: https://github.com/datalad/datalad/issues/3667
[#3678]: https://github.com/datalad/datalad/issues/3678
[#3680]: https://github.com/datalad/datalad/issues/3680
[#3682]: https://github.com/datalad/datalad/issues/3682
[#3688]: https://github.com/datalad/datalad/issues/3688
[#3692]: https://github.com/datalad/datalad/issues/3692
[#3693]: https://github.com/datalad/datalad/issues/3693
[#3695]: https://github.com/datalad/datalad/issues/3695
[#3700]: https://github.com/datalad/datalad/issues/3700
[#3701]: https://github.com/datalad/datalad/issues/3701
[#3702]: https://github.com/datalad/datalad/issues/3702
[#3704]: https://github.com/datalad/datalad/issues/3704
[#3705]: https://github.com/datalad/datalad/issues/3705
[#3712]: https://github.com/datalad/datalad/issues/3712
[#3715]: https://github.com/datalad/datalad/issues/3715
[#3719]: https://github.com/datalad/datalad/issues/3719
[#3728]: https://github.com/datalad/datalad/issues/3728
[#3743]: https://github.com/datalad/datalad/issues/3743
[#3746]: https://github.com/datalad/datalad/issues/3746
[#3747]: https://github.com/datalad/datalad/issues/3747
[#3749]: https://github.com/datalad/datalad/issues/3749
[#3751]: https://github.com/datalad/datalad/issues/3751
[#3754]: https://github.com/datalad/datalad/issues/3754
[#3761]: https://github.com/datalad/datalad/issues/3761
[#3765]: https://github.com/datalad/datalad/issues/3765
[#3768]: https://github.com/datalad/datalad/issues/3768
[#3769]: https://github.com/datalad/datalad/issues/3769
[#3770]: https://github.com/datalad/datalad/issues/3770
[#3772]: https://github.com/datalad/datalad/issues/3772
[#3775]: https://github.com/datalad/datalad/issues/3775
[#3776]: https://github.com/datalad/datalad/issues/3776
[#3777]: https://github.com/datalad/datalad/issues/3777
[#3780]: https://github.com/datalad/datalad/issues/3780
[#3787]: https://github.com/datalad/datalad/issues/3787
[#3791]: https://github.com/datalad/datalad/issues/3791
[#3793]: https://github.com/datalad/datalad/issues/3793
[#3794]: https://github.com/datalad/datalad/issues/3794
[#3797]: https://github.com/datalad/datalad/issues/3797
[#3798]: https://github.com/datalad/datalad/issues/3798
[#3799]: https://github.com/datalad/datalad/issues/3799
[#3803]: https://github.com/datalad/datalad/issues/3803
[#3804]: https://github.com/datalad/datalad/issues/3804
[#3807]: https://github.com/datalad/datalad/issues/3807
[#3812]: https://github.com/datalad/datalad/issues/3812
[#3815]: https://github.com/datalad/datalad/issues/3815
[#3817]: https://github.com/datalad/datalad/issues/3817
[#3821]: https://github.com/datalad/datalad/issues/3821
[#3828]: https://github.com/datalad/datalad/issues/3828
[#3831]: https://github.com/datalad/datalad/issues/3831
[#3834]: https://github.com/datalad/datalad/issues/3834
[#3842]: https://github.com/datalad/datalad/issues/3842
[#3850]: https://github.com/datalad/datalad/issues/3850
[#3851]: https://github.com/datalad/datalad/issues/3851
[#3854]: https://github.com/datalad/datalad/issues/3854
[#3856]: https://github.com/datalad/datalad/issues/3856
[#3860]: https://github.com/datalad/datalad/issues/3860
[#3862]: https://github.com/datalad/datalad/issues/3862
[#3863]: https://github.com/datalad/datalad/issues/3863
[#3871]: https://github.com/datalad/datalad/issues/3871
[#3873]: https://github.com/datalad/datalad/issues/3873
[#3877]: https://github.com/datalad/datalad/issues/3877
[#3880]: https://github.com/datalad/datalad/issues/3880
[#3888]: https://github.com/datalad/datalad/issues/3888
[#3892]: https://github.com/datalad/datalad/issues/3892
[#3903]: https://github.com/datalad/datalad/issues/3903
[#3904]: https://github.com/datalad/datalad/issues/3904
[#3906]: https://github.com/datalad/datalad/issues/3906
[#3907]: https://github.com/datalad/datalad/issues/3907
[#3911]: https://github.com/datalad/datalad/issues/3911
[#3926]: https://github.com/datalad/datalad/issues/3926
[#3927]: https://github.com/datalad/datalad/issues/3927
[#3931]: https://github.com/datalad/datalad/issues/3931
[#3935]: https://github.com/datalad/datalad/issues/3935
[#3940]: https://github.com/datalad/datalad/issues/3940
[#3954]: https://github.com/datalad/datalad/issues/3954
[#3955]: https://github.com/datalad/datalad/issues/3955
[#3958]: https://github.com/datalad/datalad/issues/3958
[#3959]: https://github.com/datalad/datalad/issues/3959
[#3960]: https://github.com/datalad/datalad/issues/3960
[#3963]: https://github.com/datalad/datalad/issues/3963
[#3970]: https://github.com/datalad/datalad/issues/3970
[#3971]: https://github.com/datalad/datalad/issues/3971
[#3974]: https://github.com/datalad/datalad/issues/3974
[#3975]: https://github.com/datalad/datalad/issues/3975
[#3976]: https://github.com/datalad/datalad/issues/3976
[#3979]: https://github.com/datalad/datalad/issues/3979
[#3996]: https://github.com/datalad/datalad/issues/3996
[#3999]: https://github.com/datalad/datalad/issues/3999
[#4002]: https://github.com/datalad/datalad/issues/4002
[#4022]: https://github.com/datalad/datalad/issues/4022
[#4036]: https://github.com/datalad/datalad/issues/4036
[#4037]: https://github.com/datalad/datalad/issues/4037
[#4041]: https://github.com/datalad/datalad/issues/4041
[#4045]: https://github.com/datalad/datalad/issues/4045
[#4046]: https://github.com/datalad/datalad/issues/4046
[#4049]: https://github.com/datalad/datalad/issues/4049
[#4050]: https://github.com/datalad/datalad/issues/4050
[#4057]: https://github.com/datalad/datalad/issues/4057
[#4060]: https://github.com/datalad/datalad/issues/4060
[#4064]: https://github.com/datalad/datalad/issues/4064
[#4065]: https://github.com/datalad/datalad/issues/4065
[#4070]: https://github.com/datalad/datalad/issues/4070
[#4073]: https://github.com/datalad/datalad/issues/4073
[#4078]: https://github.com/datalad/datalad/issues/4078
[#4080]: https://github.com/datalad/datalad/issues/4080
[#4081]: https://github.com/datalad/datalad/issues/4081
[#4087]: https://github.com/datalad/datalad/issues/4087
[#4091]: https://github.com/datalad/datalad/issues/4091
[#4099]: https://github.com/datalad/datalad/issues/4099
[#4106]: https://github.com/datalad/datalad/issues/4106
[#4124]: https://github.com/datalad/datalad/issues/4124
[#4140]: https://github.com/datalad/datalad/issues/4140
[#4147]: https://github.com/datalad/datalad/issues/4147
[#4156]: https://github.com/datalad/datalad/issues/4156
[#4157]: https://github.com/datalad/datalad/issues/4157
[#4158]: https://github.com/datalad/datalad/issues/4158
[#4159]: https://github.com/datalad/datalad/issues/4159
[#4167]: https://github.com/datalad/datalad/issues/4167
[#4168]: https://github.com/datalad/datalad/issues/4168
[#4169]: https://github.com/datalad/datalad/issues/4169
[#4170]: https://github.com/datalad/datalad/issues/4170
[#4171]: https://github.com/datalad/datalad/issues/4171
[#4172]: https://github.com/datalad/datalad/issues/4172
[#4174]: https://github.com/datalad/datalad/issues/4174
[#4175]: https://github.com/datalad/datalad/issues/4175
[#4187]: https://github.com/datalad/datalad/issues/4187
[#4194]: https://github.com/datalad/datalad/issues/4194
[#4196]: https://github.com/datalad/datalad/issues/4196
[#4200]: https://github.com/datalad/datalad/issues/4200
[#4203]: https://github.com/datalad/datalad/issues/4203
[#4206]: https://github.com/datalad/datalad/issues/4206
[#4212]: https://github.com/datalad/datalad/issues/4212
[#4214]: https://github.com/datalad/datalad/issues/4214
[#4235]: https://github.com/datalad/datalad/issues/4235
[#4239]: https://github.com/datalad/datalad/issues/4239
[#4243]: https://github.com/datalad/datalad/issues/4243
[#4245]: https://github.com/datalad/datalad/issues/4245
[#4257]: https://github.com/datalad/datalad/issues/4257
[#4260]: https://github.com/datalad/datalad/issues/4260
[#4262]: https://github.com/datalad/datalad/issues/4262
[#4268]: https://github.com/datalad/datalad/issues/4268
[#4273]: https://github.com/datalad/datalad/issues/4273
[#4274]: https://github.com/datalad/datalad/issues/4274
[#4276]: https://github.com/datalad/datalad/issues/4276
[#4285]: https://github.com/datalad/datalad/issues/4285
[#4290]: https://github.com/datalad/datalad/issues/4290
[#4291]: https://github.com/datalad/datalad/issues/4291
[#4296]: https://github.com/datalad/datalad/issues/4296
[#4301]: https://github.com/datalad/datalad/issues/4301
[#4303]: https://github.com/datalad/datalad/issues/4303
[#4304]: https://github.com/datalad/datalad/issues/4304
[#4305]: https://github.com/datalad/datalad/issues/4305
[#4306]: https://github.com/datalad/datalad/issues/4306
[#4308]: https://github.com/datalad/datalad/issues/4308
[#4314]: https://github.com/datalad/datalad/issues/4314
[#4315]: https://github.com/datalad/datalad/issues/4315
[#4316]: https://github.com/datalad/datalad/issues/4316
[#4317]: https://github.com/datalad/datalad/issues/4317
[#4319]: https://github.com/datalad/datalad/issues/4319
[#4321]: https://github.com/datalad/datalad/issues/4321
[#4323]: https://github.com/datalad/datalad/issues/4323
[#4324]: https://github.com/datalad/datalad/issues/4324
[#4326]: https://github.com/datalad/datalad/issues/4326
[#4328]: https://github.com/datalad/datalad/issues/4328
[#4330]: https://github.com/datalad/datalad/issues/4330
[#4331]: https://github.com/datalad/datalad/issues/4331
[#4332]: https://github.com/datalad/datalad/issues/4332
[#4337]: https://github.com/datalad/datalad/issues/4337
[#4338]: https://github.com/datalad/datalad/issues/4338
[#4342]: https://github.com/datalad/datalad/issues/4342
[#4348]: https://github.com/datalad/datalad/issues/4348
[#4354]: https://github.com/datalad/datalad/issues/4354
[#4361]: https://github.com/datalad/datalad/issues/4361
[#4367]: https://github.com/datalad/datalad/issues/4367
[#4370]: https://github.com/datalad/datalad/issues/4370
[#4375]: https://github.com/datalad/datalad/issues/4375
[#4382]: https://github.com/datalad/datalad/issues/4382
[#4398]: https://github.com/datalad/datalad/issues/4398
[#4400]: https://github.com/datalad/datalad/issues/4400
[#4409]: https://github.com/datalad/datalad/issues/4409
[#4420]: https://github.com/datalad/datalad/issues/4420
[#4421]: https://github.com/datalad/datalad/issues/4421
[#4426]: https://github.com/datalad/datalad/issues/4426
[#4430]: https://github.com/datalad/datalad/issues/4430
[#4431]: https://github.com/datalad/datalad/issues/4431
[#4435]: https://github.com/datalad/datalad/issues/4435
[#4438]: https://github.com/datalad/datalad/issues/4438
[#4439]: https://github.com/datalad/datalad/issues/4439
[#4441]: https://github.com/datalad/datalad/issues/4441
[#4448]: https://github.com/datalad/datalad/issues/4448
[#4456]: https://github.com/datalad/datalad/issues/4456
[#4459]: https://github.com/datalad/datalad/issues/4459
[#4460]: https://github.com/datalad/datalad/issues/4460
[#4463]: https://github.com/datalad/datalad/issues/4463
[#4464]: https://github.com/datalad/datalad/issues/4464
[#4471]: https://github.com/datalad/datalad/issues/4471
[#4477]: https://github.com/datalad/datalad/issues/4477
[#4480]: https://github.com/datalad/datalad/issues/4480
[#4481]: https://github.com/datalad/datalad/issues/4481
[#4504]: https://github.com/datalad/datalad/issues/4504
[#4526]: https://github.com/datalad/datalad/issues/4526
[#4529]: https://github.com/datalad/datalad/issues/4529
[#4543]: https://github.com/datalad/datalad/issues/4543
[#4544]: https://github.com/datalad/datalad/issues/4544
[#4549]: https://github.com/datalad/datalad/issues/4549
[#4552]: https://github.com/datalad/datalad/issues/4552
[#4553]: https://github.com/datalad/datalad/issues/4553
[#4560]: https://github.com/datalad/datalad/issues/4560
[#4568]: https://github.com/datalad/datalad/issues/4568
[#4581]: https://github.com/datalad/datalad/issues/4581
[#4617]: https://github.com/datalad/datalad/issues/4617
[#4619]: https://github.com/datalad/datalad/issues/4619
[#4620]: https://github.com/datalad/datalad/issues/4620
[#4657]: https://github.com/datalad/datalad/issues/4657
[#4666]: https://github.com/datalad/datalad/issues/4666
[#4673]: https://github.com/datalad/datalad/issues/4673
[#4674]: https://github.com/datalad/datalad/issues/4674
[#4675]: https://github.com/datalad/datalad/issues/4675
[#4682]: https://github.com/datalad/datalad/issues/4682
[#4683]: https://github.com/datalad/datalad/issues/4683
[#4684]: https://github.com/datalad/datalad/issues/4684
[#4687]: https://github.com/datalad/datalad/issues/4687
[#4692]: https://github.com/datalad/datalad/issues/4692
[#4696]: https://github.com/datalad/datalad/issues/4696
[#4703]: https://github.com/datalad/datalad/issues/4703
[#4729]: https://github.com/datalad/datalad/issues/4729
[#4736]: https://github.com/datalad/datalad/issues/4736
[#4745]: https://github.com/datalad/datalad/issues/4745
[#4746]: https://github.com/datalad/datalad/issues/4746
[#4749]: https://github.com/datalad/datalad/issues/4749
[#4757]: https://github.com/datalad/datalad/issues/4757
[#4759]: https://github.com/datalad/datalad/issues/4759
[#4760]: https://github.com/datalad/datalad/issues/4760
[#4763]: https://github.com/datalad/datalad/issues/4763
[#4764]: https://github.com/datalad/datalad/issues/4764
[#4775]: https://github.com/datalad/datalad/issues/4775
[#4786]: https://github.com/datalad/datalad/issues/4786
[#4788]: https://github.com/datalad/datalad/issues/4788
[#4790]: https://github.com/datalad/datalad/issues/4790
[#4792]: https://github.com/datalad/datalad/issues/4792
[#4806]: https://github.com/datalad/datalad/issues/4806
[#4807]: https://github.com/datalad/datalad/issues/4807
[#4817]: https://github.com/datalad/datalad/issues/4817
[#4821]: https://github.com/datalad/datalad/issues/4821
[#4824]: https://github.com/datalad/datalad/issues/4824
[#4834]: https://github.com/datalad/datalad/issues/4834
[#4835]: https://github.com/datalad/datalad/issues/4835
[#4866]: https://github.com/datalad/datalad/issues/4866
[#4877]: https://github.com/datalad/datalad/issues/4877
[#4896]: https://github.com/datalad/datalad/issues/4896
[#4899]: https://github.com/datalad/datalad/issues/4899
[#4926]: https://github.com/datalad/datalad/issues/4926
[#4927]: https://github.com/datalad/datalad/issues/4927
[#4931]: https://github.com/datalad/datalad/issues/4931
[#4952]: https://github.com/datalad/datalad/issues/4952
[#4953]: https://github.com/datalad/datalad/issues/4953
[#4957]: https://github.com/datalad/datalad/issues/4957
[#4966]: https://github.com/datalad/datalad/issues/4966
[#4977]: https://github.com/datalad/datalad/issues/4977
[#4985]: https://github.com/datalad/datalad/issues/4985
[#5001]: https://github.com/datalad/datalad/issues/5001
[#5008]: https://github.com/datalad/datalad/issues/5008
[#5017]: https://github.com/datalad/datalad/issues/5017
[#5025]: https://github.com/datalad/datalad/issues/5025
[#5026]: https://github.com/datalad/datalad/issues/5026
[#5035]: https://github.com/datalad/datalad/issues/5035
[#5042]: https://github.com/datalad/datalad/issues/5042
[#5045]: https://github.com/datalad/datalad/issues/5045
[#5049]: https://github.com/datalad/datalad/issues/5049
[#5051]: https://github.com/datalad/datalad/issues/5051
[#5057]: https://github.com/datalad/datalad/issues/5057
[#5060]: https://github.com/datalad/datalad/issues/5060
[#5106]: https://github.com/datalad/datalad/issues/5106
[#5113]: https://github.com/datalad/datalad/issues/5113
[#5119]: https://github.com/datalad/datalad/issues/5119
[#5121]: https://github.com/datalad/datalad/issues/5121
[#5125]: https://github.com/datalad/datalad/issues/5125
[#5127]: https://github.com/datalad/datalad/issues/5127
[#5136]: https://github.com/datalad/datalad/issues/5136
[#5146]: https://github.com/datalad/datalad/issues/5146
[#5148]: https://github.com/datalad/datalad/issues/5148
[#5151]: https://github.com/datalad/datalad/issues/5151
[#5194]: https://github.com/datalad/datalad/issues/5194
[#5200]: https://github.com/datalad/datalad/issues/5200
[#5201]: https://github.com/datalad/datalad/issues/5201
[#5214]: https://github.com/datalad/datalad/issues/5214
[#5218]: https://github.com/datalad/datalad/issues/5218
[#5219]: https://github.com/datalad/datalad/issues/5219
[#5238]: https://github.com/datalad/datalad/issues/5238
