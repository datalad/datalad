.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_reset:

************************************
Reset a dataset to a target revision
************************************

.. topic:: Specification scope and status

   This specification is a proposal, subject to review and further discussion.
   A new command :command:`reset` is introduced to enable correct `git reset --hard`
   behavior on an adjusted branch. Recursive operation (``--recursive``/``--follow``)
   allows reset across the dataset hierarchy on both normal and adjusted branches.

§1 The :command:`reset` command discards local divergence and sets a dataset to
a target revision. On a normal branch ``datalad reset <target>`` is equivalent
to ``git reset --hard <target>``; the command exists to do the same thing
*correctly* on git-annex *adjusted* branches.

§2 On adjusted branches (the default on Windows / crippled filesystems) a plain
``git reset`` operates on the disposable adjusted *view* and leaves the
*corresponding* branch -- the real history -- untouched, so the discarded
commits can be resurrected by the next ``git annex sync`` (`#7772
<https://github.com/datalad/datalad/issues/7772>`__). The destroyed view further
prevents new work being committed and leads to its permanent loss via
``datalad save`` (`#7872 <https://github.com/datalad/datalad/issues/7872>`__).
:command:`reset` instead resets the corresponding branch, reconciles git-annex's
``synced/<branch>`` ref, and regenerates the adjusted view, so a discard stays a
discard.

This is the governing principle for the whole specification: **whatever happens
to a normal branch happens to the corresponding branch, after which
``synced/<branch>`` is reconciled and the adjusted view is regenerated.** It
applies uniformly to every target and mode below, so the rest of this document
-- the use cases included -- describes only the normal-branch behavior. The one
exception is a target that does not move history (e.g. plain ``HEAD``): there
only the working tree changes, so the adjusted case is a plain ``git reset
--hard`` on the view, with no corresponding-branch checkout and no re-adjust.

§3 :command:`reset` performs a **hard** reset only; there is no mode flag, and
``datalad reset <target>`` always resets ``HEAD``, the index, and the working
tree to ``<target>``. This is a deliberate scope choice, not a temporary
limitation. ``git reset``'s ``--soft`` and ``--mixed`` modes differ from
``--hard`` only in *where they leave the undone changes* -- in the **staging
area** (index) -- but DataLad does not expose a staging area: :command:`save`
goes straight from the working tree to history (it is ``git add`` + ``git
commit`` fused). Soft and mixed therefore have no place in the DataLad model.
(Their interaction with git-annex's locked/unlocked file representation in the
index is also unexplored, and out of scope for this command.)

§4 The positional ``TARGET`` (default ``HEAD``) is any commit-ish: a SHA, a
branch, a tag, a remote-tracking ref (e.g. ``origin/main``), ``HEAD``, or
``HEAD~N`` (the latter under ``--recursive`` only with ``--follow=parentds``,
see §12).

§5 ``HEAD~N`` drops exactly *N* real commits on both normal and adjusted
branches (an *N=N* rule, no off-by-one). On an adjusted branch the relative ref
is resolved on the corresponding branch, where the git-annex "adjusting"
commit(s) that sit on top of the real history do not exist -- so it is never
skewed by them, nor by how many of them there are at the time.

§6 With a dirty working tree, :command:`reset` matches ``git reset --hard``: it
discards **tracked** modifications (and anything staged) but **keeps
untracked** files (it is not ``git clean``). This differs from
:command:`update`'s ``--how=reset``, which refuses on a dirty tree (see §13).

§7 Annexed content is never deleted: ``git reset`` does not touch
``.git/annex/objects``, so content stays recoverable until ``git annex
unused``/gc, on both branch types.

§8 In recursive operation (``--recursive``) the default resolves ``TARGET``
**independently in each dataset** -- a local operation with no cross-dataset
following. ``HEAD`` means each dataset's own ``HEAD`` (i.e. discard each
dataset's tracked changes in place); ``origin/main`` means each dataset's own
``origin/main``. This presumes a ``TARGET`` that names a *current state* present
in every dataset (``HEAD``, a branch, a tag, a remote-tracking ref); a *history
coordinate* -- a SHA or ``HEAD~N`` -- has no such per-dataset meaning and is
instead handled by ``--follow=parentds`` (§9, detailed in §11--§12).

§9 ``--follow=parentds`` opts into the alternative: the superdataset resets to
``TARGET``, and each subdataset resets to the revision the (reset) super
*records* for it. The superdataset is reset first, so the recorded revisions
are current. Use this to reconcile an intentionally out-of-sync hierarchy to
the superdataset's pins.

§10 The default mode is deliberately **not** named ``sibling`` (as in
:command:`update`): :command:`reset` is primarily a local operation that
resolves the user's target per dataset, which *generalizes*
:command:`update`'s sibling semantics (they coincide only for tracking-ref
targets such as ``origin/main``). The meaningful axis is parent-authority
(``--follow=parentds``) versus each-dataset-resolves-the-target (default), so
the default is left unnamed -- it is the absence of following.

§11 A raw commit SHA is a parent-history coordinate with no meaning under
per-dataset local resolution. A SHA ``TARGET`` combined with ``--recursive``
therefore requires ``--follow=parentds`` to be set explicitly; otherwise the
command refuses with an ``impossible`` result whose message hints that, to
reset each subdataset to the revision the super records, the user should add
``--follow=parentds``.

§12 A relative target (``HEAD~N``) is, like a SHA (§11), a coordinate in *this*
dataset's history, so under ``--recursive`` it likewise requires
``--follow=parentds`` -- the superdataset resolves it and each subdataset
follows the recorded revision; without it the command refuses with the same
hint. Plain ``HEAD`` (no offset) is exempt: it moves no history and is resolved
per dataset in the default mode (each dataset discards its own working-tree
changes, see §8).

§13 :command:`reset` shares its reset engine with :command:`update`'s
``--how=reset`` (both must reset the corresponding branch and reconcile
``synced/`` on adjusted branches). The shared engine is a *pure* hard reset:
it always discards, like ``git reset --hard``, and does not inspect the working
tree. :command:`update` keeps its stricter contract of refusing a dirty tree by
guarding for that itself, before delegating to the engine; :command:`reset`
does not (§6), so :command:`update`'s behavior is unchanged.

Use cases
=========

The use cases below operate on a superdataset `super` with one subdataset
`sub`; `super` has a sibling ``origin``. Unless stated otherwise, commands are
run in the root of `super`. Per the governing principle (§2), only the
normal-branch behavior is stated; on an adjusted branch the same applies to the
corresponding branch, with the view regenerated. U1-U3 are specifically the new
capability on an adjusted branch -- on a normal branch the same behavior is
achieved with ``git reset --hard``.

- U1: ``datalad reset origin/main`` (adjusted branch)

  Reset the current branch to the sibling's branch, discarding local commits
  (equivalent to ``git reset --hard origin/main``).

- U2: ``datalad reset`` (adjusted branch)

  Default ``TARGET`` is ``HEAD``: discard tracked uncommitted/staged changes,
  keeping untracked files and all commits.

- U3: ``datalad reset HEAD~2`` (adjusted branch)

  Drop the last two commits of the current branch.

- U4: ``datalad reset HEAD -r``

  Discard tracked changes in `super` and `sub`; each dataset stays on its own
  ``HEAD`` (`sub`'s local commits are kept).

- U5: ``datalad reset HEAD -r --follow=parentds``

  Leave `super` where it is and reset `sub` to the revision `super` records for
  it -- discarding `sub`'s committed divergence to snap it back to the pin.

- U6: ``datalad reset <SHA> -r``

  Error: a raw SHA has no per-subdataset meaning; the message hints at adding
  ``--follow=parentds``.

- U7: ``datalad reset <SHA> -r --follow=parentds``

  Reset `super` to ``<SHA>`` and reset `sub` to the revision that commit records
  for it.

- U8: ``datalad reset HEAD~1 -r --follow=parentds``

  Reset `super` to its ``HEAD~1`` and reset `sub` to the revision that commit
  records for it -- as in U7, since a relative ref is, like a SHA, a coordinate
  in `super`'s history. (Without ``--follow=parentds`` this is refused, just
  like the bare-SHA U6.)

- U9: ``datalad reset origin/main -r``

  Each dataset resets to its own ``origin/main`` (the target is resolved locally
  in `super` and in `sub`).

- U10: ``datalad reset <branch> -r``

  Each dataset resets to its own local ``<branch>`` (default per-dataset
  resolution, as in U9). This brings an entire superdataset hierarchy onto a
  shared working branch in a single command -- useful in the nested git-worktree
  workflow, where the branch produced in each worktree otherwise has to be
  shipped back by hand, one dataset at a time (see the `git-worktree workflow
  post <https://blog.datalad.org/posts/git-worktree-workflow/>`__).
