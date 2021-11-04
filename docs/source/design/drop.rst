.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_drop:

***********************
Drop dataset components
***********************

.. topic:: Specification scope and status

   This specification is a proposal, subject to review and further discussion.
   It is now partially implemented in the `drop` command.

§1 The :command:`drop` command is the antagonist of :command:`get`. Whatever a
`drop` can do, should be undoable by a subsequent :command:`get` (given
unchanged remote availability).

§2 Like :command:`get`, :command:`drop` primarily operates on a mandatory path
specification (to discover relevant files and sudatasets to operate on).

§3 :command:`drop` has ``--what`` parameter that serves as an extensible
"mode-switch" to cover all relevant scenarios, like 'drop all file content in
the work-tree' (e.g. ``--what files``, default, `#5858
<https://github.com/datalad/datalad/issues/5858>`__), 'drop all keys from any
branch' (i.e. ``--what allkeys``, `#2328
<https://github.com/datalad/datalad/issues/2328>`__), but also '"drop" AKA
uninstall entire subdataset hierarchies' (e.g. ``--what all``), or drop
preferred content (``--what preferred-content``, `#3122
<https://github.com/datalad/datalad/issues/3122>`__).

§4 :command:`drop` prevents data loss by default (`#4750
<https://github.com/datalad/datalad/issues/4750>`__). Like :command:`get` it
features a ``--reckless`` "mode-switch" to disable some or all potentially slow
safety mechnism, i.e. 'key available in sufficient number of other remotes',
'main or all branches pushed to remote(s)' (`#1142
<https://github.com/datalad/datalad/issues/1142>`__), 'only check availability
of keys associated with the worktree, but not other branches'. "Reckless
operation" can be automatic, when following a reckless :command:`get` (`#4744
<https://github.com/datalad/datalad/issues/4744>`__).

§5 :command:`drop` properly manages annex lifetime information, e.g. by announcing
an annex as ``dead`` on removal of a repository (`#3887
<https://github.com/datalad/datalad/issues/3887>`__).

§6 Like :command:`get`, drop supports parallization `#1953
<https://github.com/datalad/datalad/issues/1953>`__ 

§7 `datalad drop` is not intended to be a comprehensive frontend to `git annex
drop` (e.g. limited support for e.g. `#1482
<https://github.com/datalad/datalad/issues/1482>`__ outside standard use cases
like `#2328 <https://github.com/datalad/datalad/issues/2328>`__).

.. note::
  It is understood that the current `uninstall` command is largely or
  completely made obsolete by this :command:`drop` concept.

§8 Given the development in `#5842
<https://github.com/datalad/datalad/issues/5842>`__  towards the complete
obsolescence of `remove` it becomes necessary to import one of its proposed
features:

§9 :command:`drop` should be able to recognize a botched attempt to delete a
dataset with a plain rm -rf, and act on it in a meaningful way, even if it is
just hinting at chmod + rm -rf.


Use cases
=========

The following use cases operate in the dataset hierarchy depicted below::

  super
  ├── dir
  │   ├── fileD1
  │   └── fileD2
  ├── fileS1
  ├── fileS2
  ├── subA
  │   ├── fileA
  │   ├── subsubC
  │   │   ├── fileC
  │   └── subsubD
  └── subB
      └── fileB

Unless explicitly stated, all command are assumed to be executed in the root of `super`.

- U1: ``datalad drop fileS1``

   Drops the file content of `file1` (as currently done by :command:`drop`)

- U2: ``datalad drop dir``

   Drop all file content in the directory (``fileD{1,2}``; as currently done by
   :command:`drop`

- U3: ``datalad drop subB``

   Drop all file content from the entire `subB` (`fileB`)

- U4: ``datalad drop subB --what all``

   Same as above (default ``--what files``), because it is not operating in the
   context of a superdataset (no automatic upward lookups). Possibly hint at
   next usage pattern).

- U5: ``datalad drop -d . subB --what all``

  Drop all from the superdataset under this path. I.e. drop all from the
  subdataset and drop the subdataset itself (AKA uninstall)

- U6: ``datalad drop subA --what all``

  Error: "``subA`` contains subdatasets, forgot --recursive?"

- U7: ``datalad drop -d . subA -r --what all``

  Drop all content from the subdataset (``fileA``) and its subdatasets
  (``fileC``), uninstall the subdataset (``subA``) and its subdatasets
  (``subsubC``, ``subsubD``)

- U8: ``datalad drop subA -r --what all``

  Same as above, but keep ``subA`` installed

- U9: ``datalad drop sub-A -r``

   Drop all content from the subdataset and its subdatasets (``fileA``,
   ``fileC``)

- U10: ``datalad drop . -r --what all``

  Drops all file content and subdatasets, but leaves the superdataset
  repository behind

- U11: ``datalad drop -d . subB``

  Does nothing and hints at alternative usage, see
  https://github.com/datalad/datalad/issues/5832#issuecomment-889656335

- U12: ``cd .. && datalad drop super/dir``

  Like :command:`get`, errors because the execution is not associated with a
  dataset. This avoids complexities, when the given `path`'s point to multiple
  (disjoint) datasets. It is understood that it could be done, but it is
  intentionally not done. `datalad -C super drop dir` or `datalad drop -d super
  super/dir` would work.
