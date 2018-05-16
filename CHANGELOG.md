     ____            _             _                   _ 
    |  _ \    __ _  | |_    __ _  | |       __ _    __| |
    | | | |  / _` | | __|  / _` | | |      / _` |  / _` |
    | |_| | | (_| | | |_  | (_| | | |___  | (_| | | (_| |
    |____/   \__,_|  \__|  \__,_| |_____|  \__,_|  \__,_|
                                               Change Log

This is a high level and scarce summary of the changes between releases.
We would recommend to consult log of the 
[DataLad git repository](http://github.com/datalad/datalad) for more details.

## 0.10.0 (??? ??, 2018) -- The Release

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
  - addurls, an extension for creating a dataset (and possibly subdatasets)
    from a list of URLs.
  - export_to_figshare
  - extract_metadata
- add_readme makes use of available metadata
- By default the wtf extension now hides sensitive information, which can be
  included in the output by passing `--senstive=some` or `--senstive=all`.
- Reduced startup latency by only importing commands necessary for a particular
  command line call.
- `datalad create -d <parent> --nosave` now registers subdatasets, when possible.
- `datalad run` now provides a way for the caller to save the result when a
  command has a non-zero exit status.
- `datalad rerun` now has a `--script` option that can be used to extract
  previous commands into a file.
- A DataLad Singularity container is now available on
  [Singularity Hub](https://singularity-hub.org/collections/667).
- More casts have been embedded in the [use case section of the documentation](http://docs.datalad.org/en/docs/usecases/index.html).
- `datalad --report-status` has a new value 'all' that can be used to
  temporarily re-enable reporting that was disable by configuration settings.

## 0.9.4 (??? ??, 2018) -- will be better than ever

bet we will fix some bugs and make a world even a better place.

### Major refactoring and deprecations

- hopefully none

### Fixes

?

### Enhancements and new features

?


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


## 0.9.2 (Mar 04, 2017) -- it is (again) better than ever

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


# 0.9.1 (Oct 01, 2017) -- "DATALAD!"(JBTM)

Minor bugfix release

### Fixes

- Should work correctly with subdatasets named as numbers of bool
  values (requires also GitPython >= 2.1.6)
- Custom special remotes should work without crashing with 
  git-annex >= 6.20170924


## 0.9.0 (Sep 19, 2017) -- isn't it a lucky day even though not a Friday?

### Major refactoring and deprecations

- the `files` argument of [save] has been renamed to `path` to be uniform with
  any other command
- all major commands now implement more uniform API semantics and result reporting.
  Functionality for modification detection of dataset content has been completely replaced
  with a more efficient implementation
- [publish] now features a `--transfer-data` switch that allows for a
  disambiguous specification of whether to publish data -- independent of
  the selection which datasets to publish (which is done via their paths).
  Moreover, [publish] now transfers data before repository content is pushed.

### Fixes

- [drop] no longer errors when some subdatasets are not installed
- [install] will no longer report nothing when a Dataset instance was
  given as a source argument, but rather perform as expected
- [remove] doesn't remove when some files of a dataset could not be dropped
- [publish] 
  - no longer hides error during a repository push
  - publish behaves "correctly" for `--since=` in considering only the
    differences the last "pushed" state
  - data transfer handling while publishing with dependencies, to github
- improved robustness with broken Git configuration
- [search] should search for unicode strings correctly and not crash
- robustify git-annex special remotes protocol handling to allow for spaces in
  the last argument
- UI credentials interface should now allow to Ctrl-C the entry
- should not fail while operating on submodules named with
  numerics only or by bool (true/false) names
- [crawl] templates should not now override settings for `largefiles` if 
  specified in `.gitattributes`


### Enhancements and new features

- **Exciting new feature** [run] command to protocol execution of an external 
  command and rerun computation if desired. 
  See [screencast](http://datalad.org/features.html#reproducible-science)
- [save] now uses Git for detecting with sundatasets need to be inspected for
  potential changes, instead of performing a complete traversal of a dataset tree
- [add] looks for changes relative to the last commited state of a dataset
  to discover files to add more efficiently
- [diff] can now report untracked files in addition to modified files
- [uninstall] will check itself whether a subdataset is properly registered in a
  superdataset, even when no superdataset is given in a call
- [subdatasets] can now configure subdatasets for exclusion from recursive
  installation (`datalad-recursiveinstall` submodule configuration property)
- precrafted pipelines of [crawl] now will not override `annex.largefiles`
  setting if any was set within `.gitattribues` (e.g. by `datalad create --text-no-annex`)
- framework for screencasts: `tools/cast*` tools and sample cast scripts under
  `doc/casts` which are published at [datalad.org/features.html](http://datalad.org/features.html)
- new [project YouTube channel](https://www.youtube.com/channel/UCB8-Zf7D0DSzAsREoIt0Bvw) 
- tests failing in direct and/or v6 modes marked explicitly

## 0.8.1 (Aug 13, 2017) -- the best birthday gift

Bugfixes

### Fixes

- Do not attempt to [update] a not installed sub-dataset
- In case of too many files to be specified for [get] or [copy_to], we
  will make multiple invocations of underlying git-annex command to not
  overfill command line
- More robust handling of unicode output in terminals which might not support it

### Enhancements and new features

- Ship a copy of numpy.testing to facilitate [test] without requiring numpy
  as dependency. Also allow to pass to command which test(s) to run
- In [get] and [copy_to] provide actual original requested paths, not the
  ones we deduced need to be transferred, solely for knowing the total


## 0.8.0 (Jul 31, 2017) -- it is better than ever

A variety of fixes and enhancements

### Fixes

- [publish] would now push merged `git-annex` branch even if no other changes
  were done
- [publish] should be able to publish using relative path within SSH URI
  (git hook would use relative paths)
- [publish] should better tollerate publishing to pure git and `git-annex` 
  special remotes 

### Enhancements and new features

- [plugin] mechanism came to replace [export]. See [export_tarball] for the
  replacement of [export].  Now it should be easy to extend datalad's interface
  with custom functionality to be invoked along with other commands.
- Minimalistic coloring of the results rendering
- [publish]/`copy_to` got progress bar report now and support of `--jobs`
- minor fixes and enhancements to crawler (e.g. support of recursive removes)


## 0.7.0 (Jun 25, 2017) -- when it works - it is quite awesome!

New features, refactorings, and bug fixes.

### Major refactoring and deprecations

- [add-sibling] has been fully replaced by the [siblings] command
- [create-sibling], and [unlock] have been re-written to support the
  same common API as most other commands

### Enhancements and new features

- [siblings] can now be used to query and configure a local repository by
  using the sibling name ``here``
- [siblings] can now query and set annex preferred content configuration. This
  includes ``wanted`` (as previously supported in other commands), and now
  also ``required``
- New [metadata] command to interface with datasets/files [meta-data] 
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
  options for [datalad] command.
- effort was made to refactor code base so that underlying functions behave as
  generators where possible
- input paths/arguments analysis was redone for majority of the commands to provide
  unified behavior

### Major refactoring and deprecations

- `add-sibling` and `rewrite-urls` were refactored in favor of new [siblings]
  command which should be used for siblings manipulations
- 'datalad.api.alwaysrender' config setting/support is removed in favor of new
  outputs processing

### Fixes

- Do not flush manually git index in pre-commit to avoid "Death by the Lock" issue
- Deployed by [publish] `post-update` hook script now should be more robust
  (tolerate directory names with spaces, etc.)
- A variety of fixes, see
  [list of pull requests and issues closed](https://github.com/datalad/datalad/milestone/41?closed=1)
  for more information

### Enhancements and new features

- new [annotate-paths] plumbing command to inspect and annotate provided
  paths.  Use `--modified` to summarize changes between different points in
  the history
- new [clone] plumbing command to provide a subset (install a single dataset
  from a URL) functionality of [install]
- new [diff] plumbing command
- new [siblings] command to list or manipulate siblings
- new [subdatasets] command to list subdatasets and their properties
- [drop] and [remove] commands were refactored
- `benchmarks/` collection of [Airspeed velocity](https://github.com/spacetelescope/asv/)
  benchmarks initiated.  See reports at http://datalad.github.io/datalad/
- crawler would try to download a new url multiple times increasing delay between
  attempts.  Helps to resolve problems with extended crawls of Amazon S3
- [CRCNS] crawler pipeline now also fetches and aggregates meta-data for the
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

- [add] was forcing addition of files to annex regardless of settings
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
(see [PR 1350])

### Most notable changes

- requires [git-annex] >= 6.20161210 (or better even >= 6.20161210 for
  improved functionality)
- commands should now operate on paths specified (if any), without
  causing side-effects on other dirty/staged files
- [save]
    - `-a` is deprecated in favor of `-u` or `--all-updates`
      so only changes known components get saved, and no new files
      automagically added
    - `-S` does no longer store the originating dataset in its commit
       message
- [add]
    - can specify commit/save message with `-m`
- [add-sibling] and [create-sibling]
    - now take the name of the sibling (remote) as a `-s` (`--name`)
      option, not a positional argument
    - `--publish-depends` to setup publishing data and code to multiple
      repositories (e.g. github + webserve) should now be functional
      see [this comment](https://github.com/datalad/datalad/issues/335#issuecomment-277240733)
    - got `--publish-by-default` to specify what refs should be published
      by default
    - got `--annex-wanted`, `--annex-groupwanted` and `--annex-group`
      settings which would be used to instruct annex about preferred
      content. [publish] then will publish data using those settings if
      `wanted` is set.
    - got `--inherit` option to automagically figure out url/wanted and
      other git/annex settings for new remote sub-dataset to be constructed
- [publish]
    - got `--skip-failing` refactored into `--missing` option
      which could use new feature of [create-sibling] `--inherit`

### Fixes

- More consistent interaction through ssh - all ssh connections go
  through [sshrun] shim for a "single point of authentication", etc.
- More robust [ls] operation outside of the datasets
- A number of fixes for direct and v6 mode of annex

### Enhancements and new features

- New [drop] and [remove] commands
- [clean]
    - got `--what` to specify explicitly what cleaning steps to perform
      and now could be invoked with `-r`
- `datalad` and `git-annex-remote*` scripts now do not use setuptools
  entry points mechanism and rely on simple import to shorten start up time
- [Dataset] is also now using [Flyweight pattern], so the same instance is
  reused for the same dataset
- progressbars should not add more empty lines

### Internal refactoring

- Majority of the commands now go through `_prep` for arguments validation
  and pre-processing to avoid recursive invocations


## 0.4.1 (Nov 10, 2016) -- CA release

Requires now GitPython >= 2.1.0

### Fixes

- [save]
     - to not save staged files if explicit paths were provided
- improved (but not yet complete) support for direct mode
- [update] to not crash if some sub-datasets are not installed
- do not log calls to `git config` to avoid leakage of possibly 
  sensitive settings to the logs

### Enhancements and new features

- New [rfc822-compliant metadata] format
- [save]
    - -S to save the change also within all super-datasets
- [add] now has progress-bar reporting
- [create-sibling-github] to create a :term:`sibling` of a dataset on
  github
- [OpenfMRI] crawler and datasets were enriched with URLs to separate
  files where also available from openfmri s3 bucket
  (if upgrading your datalad datasets, you might need to run
  `git annex enableremote datalad` to make them available)
- various enhancements to log messages
- web interface
    - populates "install" box first thus making UX better over slower
      connections


## 0.4 (Oct 22, 2016) -- Paris is waiting

Primarily it is a bugfix release but because of significant refactoring
of the [install] and [get] implementation, it gets a new minor release. 

### Fixes

- be able to [get] or [install] while providing paths while being 
  outside of a dataset
- remote annex datasets get properly initialized
- robust detection of outdated [git-annex]

### Enhancements and new features

- interface changes
    - [get] `--recursion-limit=existing` to not recurse into not-installed
       subdatasets
    - [get] `-n` to possibly install sub-datasets without getting any data
    - [install] `--jobs|-J` to specify number of parallel jobs for annex 
      [get] call could use (ATM would not work when data comes from archives)
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
- [install] can be called on already installed dataset (with `-r` or
  `-g`)

### Enhancements and new features

- complete overhaul of datalad configuration settings handling
  (see [Configuration documentation]), so majority of the environment.
  Now uses git format and stores persistent configuration settings under
  `.datalad/config` and local within `.git/config`
  variables we have used were renamed to match configuration names
- [create-sibling] does not now by default upload web front-end
- [export] command with a plug-in interface and `tarball` plugin to export
  datasets
- in Python, `.api` functions with rendering of results in command line
  got a _-suffixed sibling, which would render results as well in Python
  as well (e.g., using `search_` instead of `search` would also render
  results, not only output them back as Python objects)
- [get]
    - `--jobs` option (passed to `annex get`) for parallel downloads
    - total and per-download (with git-annex >= 6.20160923) progress bars
      (note that if content is to be obtained from an archive, no progress
      will be reported yet)
- [install] `--reckless` mode option
- [search]
    - highlights locations and fieldmaps for better readability
    - supports `-d^` or `-d///` to point to top-most or centrally
      installed meta-datasets
    - "complete" paths to the datasets are reported now
    - `-s` option to specify which fields (only) to search
- various enhancements and small fixes to [meta-data] handling, [ls],
  custom remotes, code-base formatting, downloaders, etc
- completely switched to `tqdm` library (`progressbar` is no longer
  used/supported)


## 0.3 (Sep 23, 2016) -- winter is coming

Lots of everything, including but not limited to

- enhanced index viewer, as the one on http://datasets.datalad.org
- initial new data providers support: [Kaggle], [BALSA], [NDA], [NITRC]
- initial [meta-data support and management]
- new and/or improved crawler pipelines for [BALSA], [CRCNS], [OpenfMRI]
- refactored [install] command, now with separate [get]
- some other commands renaming/refactoring (e.g., [create-sibling])
- datalad [search] would give you an option to install datalad's 
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

[add-sibling]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-add-sibling.html
[add]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-add.html
[annotate-paths]: http://docs.datalad.org/en/latest/generated/man/datalad-annotate-paths.html
[clean]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-clean.html
[clone]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-clone.html
[copy_to]: http://docs.datalad.org/en/latest/_modules/datalad/support/annexrepo.html?highlight=%22copy_to%22
[create-sibling-github]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling-github.html
[create-sibling]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html
[datalad]: http://docs.datalad.org/en/latest/generated/man/datalad.html
[drop]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-drop.html
[export]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-export.html
[export_tarball]: http://docs.datalad.org/en/latest/generated/datalad.plugin.export_tarball.html
[get]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html
[install]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html
[ls]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-ls.html
[metadata]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-metadata.html
[plugin]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-plugin.html
[publish]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-publish.html
[remove]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-remove.html
[run]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-run.html
[save]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-save.html
[search]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html
[siblings]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-siblings.html
[sshrun]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-sshrun.html
[update]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-update.html

[Flyweight pattern]: https://en.wikipedia.org/wiki/Flyweight_pattern

[PR 1350]: https://github.com/datalad/datalad/pull/1350
