     ____            _             _                   _ 
    |  _ \    __ _  | |_    __ _  | |       __ _    __| |
    | | | |  / _` | | __|  / _` | | |      / _` |  / _` |
    | |_| | | (_| | | |_  | (_| | | |___  | (_| | | (_| |
    |____/   \__,_|  \__|  \__,_| |_____|  \__,_|  \__,_|
                                               Change Log

This is a very high level and scarce summary of the changes between releases.
We would recommend to consult log of the [DataLad git repository](http://github.com/datalad/datalad)
for more details ATM.

## 0.4.1 (Oct ??, 2016) -- will be better than ever

???

### Fixes

???

### Enhancements and new features

???


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


[Kaggle]: https://www.kaggle.com
[BALSA]: http://balsa.wustl.edu
[NDA]: http://data-archive.nimh.nih.gov
[NITRC]: https://www.nitrc.org
[CRCNS]: http://crcns.org
[FCON1000]: http://fcon_1000.projects.nitrc.org
[OpenfMRI]: http://openfmri.org

[git-annex]: http://git-annex.branchable.com/ 
[meta-data support and management]: http://docs.datalad.org/en/latest/cmdline.html#meta-data-handling
[meta-data]: http://docs.datalad.org/en/latest/cmdline.html#meta-data-handling
[install]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-install.html
[ls]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-ls.html
[get]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-get.html
[create-sibling]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-create-sibling.html
[search]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-search.html
[export]: http://datalad.readthedocs.io/en/latest/generated/man/datalad-export.html
[Configuration documentation]: http://docs.datalad.org/config.html
