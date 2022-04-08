.. _man_datalad-update:

datalad update
==============

Synopsis
--------
::

  datalad update [-h] [-s SIBLING] [--merge [ALLOWED]] [--how
      [{fetch|merge|ff-only|reset|checkout}]] [--how-subds
      [{fetch|merge|ff-only|reset|checkout}]] [--follow
      {sibling|parentds|parentds-lazy}] [-d DATASET] [-r] [-R LEVELS]
      [--fetch-all] [--reobtain-data] [--version] [PATH ...]

Description
-----------
Update a dataset from a sibling.

*Examples*

Update from a particular sibling::

   % datalad update -s <siblingname>

Update from a particular sibling and merge the changes from a
configured or matching branch from the sibling (see --follow for details)::

   % datalad update --how=merge -s <siblingname>

Update from the sibling 'origin', traversing into subdatasets. For
subdatasets, merge the revision registered in the parent dataset into
the current branch::

   % datalad update -s origin --how=merge --follow=parentds -r

Fetch and merge the remote tracking branch into the current dataset.
Then update each subdataset by resetting its current branch to the
revision registered in the parent dataset, fetching only if the
revision isn't already present::

   % datalad update --how=merge --how-subds=reset--follow=parentds-lazy -r




Options
-------
PATH
~~~~
constrain to-be-updated subdatasets to the given path for recursive operation. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-s** *SIBLING*, **-\\-sibling** *SIBLING*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
name of the sibling to update from. When unspecified, updates from all siblings are fetched. If there is more than one sibling and changes will be brought into the working tree (as requested via --merge, --how, or --how-subds), a sibling will be chosen based on the configured remote for the current branch. Constraints: value must be a string

**-\\-merge** [ALLOWED]
~~~~~~~~~~~~~~~~~~~~~~~
merge obtained changes from the sibling. This is a subset of the functionality that can be achieved via the newer --how. --merge or --merge=any is equivalent to --how=merge. --merge=ff-only is equivalent to --how=ff-only. Constraints: value must be convertible to type bool, or value must be one of ('any', 'ff- only') [Default: False]

**-\\-how** [{fetch|merge|ff-only|reset|checkout}]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how to update the dataset. The default ("fetch") simply fetches the changes from the sibling but doesn't incorporate them into the working tree. A value of "merge" or "ff-only" merges in changes, with the latter restricting the allowed merges to fast-forwards. "reset" incorporates the changes with 'git reset --hard <target>', staying on the current branch but discarding any changes that aren't shared with the target. "checkout", on the other hand, runs 'git checkout <target>', switching from the current branch to a detached state. When --recursive is specified, this action will also apply to subdatasets unless overridden by --how-subds. Constraints: value must be one of ('fetch', 'merge', 'ff-only', 'reset', 'checkout')

**-\\-how-subds** [{fetch|merge|ff-only|reset|checkout}]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Override the behavior of --how in subdatasets. Constraints: value must be one of ('fetch', 'merge', 'ff-only', 'reset', 'checkout')

**-\\-follow** {sibling|parentds|parentds-lazy}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
source of updates for subdatasets. For 'sibling', the update will be done by merging in a branch from the (specified or inferred) sibling. The branch brought in will either be the current branch's configured branch, if it points to a branch that belongs to the sibling, or a sibling branch with a name that matches the current branch. For 'parentds', the revision registered in the parent dataset of the subdataset is merged in. 'parentds-lazy' is like 'parentds', but prevents fetching from a subdataset's sibling if the registered revision is present in the subdataset. Note that the current dataset is always updated according to 'sibling'. This option has no effect unless a merge is requested and --recursive is specified. Constraints: value must be one of ('sibling', 'parentds', 'parentds-lazy') [Default: 'sibling']

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to update. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-\\-fetch-all**
~~~~~~~~~~~~~~~~~
this option has no effect and will be removed in a future version. When no siblings are given, an all-sibling update will be performed.

**-\\-reobtain-data**
~~~~~~~~~~~~~~~~~~~~~
if enabled, file content that was present before an update will be re-obtained in case a file was changed by the update.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
