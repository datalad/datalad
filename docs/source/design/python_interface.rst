.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_python_interface:

**************************
Datalad's python interface
**************************

.. topic:: Specification scope and status

   This is a proposal, intended for discussion of its general aim. Will be
   converted into a specification, once there's a sense of agreement on the
   goals.


I want to try and discuss an approach on our (python-) interface and general
architecture here. I think we kinda boxed ourselves into an unpleasant corner
and I want to get out of it ASAP, since I believe things will get ever more dire
otherwise. One major point to me is, that required design changes become ever
more complicated as pretty much everything "needs" deprecation cycles. WRT
design changes that means it's much more work and would require to maintain two
different architectures at the same time. With several such changes that's
simply not doable and maintainable and I don't see us getting much further that
way. If I think of proper support for bare repos, several worktrees, sparse
checkouts, different flavors of adjusted branches and so on, I don't see any of
that happening w/o major changes in design (properly representing the actually
different notions of "a worktree" and "a repository" for example, which right
now is one and the same thing in datalad). But we are currently not
realistically able to do such changes and particularly the idea that the `*Repo`
classes are part of the "public" interface is a major obstacle. However, this is
*NOT* about the ultimate architecture, on the contrary it's about enabling us to
constantly refactor most of the code base. There are several and more general
aspects to this:


1. What exactly is considered "public" interface is far from being well-defined
   to begin with. Obviously the CLI is, the `api`/`coreapi` modules are and the
   `Dataset` class is, too. However, there is no clear concept of what else is
   part of it and therefore needs proper deprecation cycles and what isn't (and
   we are free to change anytime). The `*Repo` classes originally were not
   intended to be anything other than internal, but we do consider them "public"
   ATM, since the `Dataset.repo` property makes them available and it is
   "public". In my view that argument is flawed for two reasons. First, this
   confuses two different concepts of "public". The one relevant is "what third
   party can/should access", the other one being a C-like idea of public,
   protected, etc. as indicated by `_`, `__` prefixes in python. The latter
   concept actually is about class inheritance not about what kind of user has
   access. Furthermore it can't be (entirely) enforced in python and ultimately
   by that logic everything is public since one can import any class from
   equally "public" modules. This is no concept, but a quite arbitrary choice in
   my view. Since we can't really hide things, the important thing here is to
   have clear concept of what we consider to be the public interface and
   document it properly. Add a dedicated section to the docs, that declares what
   can be relied on, what can be expected to come with a deprecation if needed,
   and make clear that everything else is subject to sudden, unannounced change.

   In my view, that interface should be in-line with the CLI. datalad is not a
   GitPython like module. Not every convenience we may have for dealing with
   repos needs to be part of that. For the command line user we basically say:
   "These are the commands we provide. In addition you may want to use
   git/git-annex directly."
   We should do the same in the python interface, I think. That means datalad's
   python interface is made of:

   - `datalad.api` (proper deprecation)
   - `datalad.coreapi` (particularly stable)
   - `Dataset` (due to dynamic binding a mix of the above)
   - `call_git/annex` functions to provide a python user with a way to call
     git+git-annex directly and consistently in code that uses datalad. These
     should either be part of the `Dataset` class (easy) or we come up with an
     idea of how  to build a "semi-command", that is a function in `coreapi`
     that is also bound to `Dataset`. Just like a command but w/o command line
     exposure.
   - Probably an additional abstraction lay below command implementations but
     above the `*Repos`. This would then supposed to be used by command
     implementations/extensions/`Dataset`-methods.
     See below for that. (proper deprecation cycle)
   - That's it. Everything else is internal and can change anytime w/o warning.

   This should go in a dedicated section in the docs and probably be linked to
   from the extension-template's README.


2. We have pretty much nothing that deserves the term "architecture" from my
   POV. Command implementations go directly down to the `*Repo` classes. So,
   it's highest level straight down to almost lowest level. Even if there was no
   need for a design change - this is far from clean code principles.
   It requires to have the full complexity in mind while reading/writing the
   highest level things, it makes introducing layers in between hard, and it
   causes a good chunk of testing problems in my view. In an ideal world one
   would want to have several layers, that communicate via appropriate data
   structures and only "one level" up/down. "Testable" code would mean, that we
   can test the logic at any level w/o first creating the lowest level entities,
   and asserting things based on executing the highest level on it, but have
   actual *units* that can be fed with their input data structures and assert
   what they yield upwards. And that's what we largely do: Almost every test
   starts with creating/cloning a repository. The actual point of unit testing
   is to not do that over and over. You'd want to rely on that part being tested
   and everywhere else just start with a defined "result record" or whatever.
   I think that the lack of architecture is a big contributor to the mess that
   is our test battery (and it's runtime!).
   As mentioned in the beginning, I think that representing concepts like
   worktrees/checkouts, (adjusted) branches, etc. is essential to get to cleaner
   and better maintainable code. That requires a high-level abstraction layer
   that commands (and therefore extensions) use and absolute freedom underneath.

3. Reiterating myself: There is no ultimate architecture, we need to be able
   constantly refactor the internal code base. I'm not about to propose the
   "right" architecture by any means. I simply want to get out of the situation
   where any meaningful change requires deprecation cycles during which several,
   different designs need to work at the same time and every change sparks a
   discussion about breakage. The largest part of the code base should be
   changeable at anytime and with no need to worry about "breakage". What is
   meant to be internal has to be treated as such.

So, what do we do?

One big shot radically breaking the status quo seems unlikely to work out on
several fronts (including simply agreeing ;-) ).

I think:

- agree on a general "interface definition" (see 1.)
- document it (incl. extensions-template repo)
- introduce a "non-public" `Dataset` property `_vcs` (or similar) holding an
  instance of a respective class `VCS`. This is supposed to become the
  additional layer, I mentioned in 1. Command implementations and `Dataset`
  methods are supposed to go through this. And it is the highest layer, that
  henceforth promises deprecation cycles. Direct calls to something deeper down
  are gonna break sooner or later w/o warning. In a first step this class will
  be largely empty, of course. It gets the `repo` property from `Dataset` for
  now and `Dataset.repo` refers to it.
  It will doubtlessly take some time to figure out, what should go into this
  class in what shape, but even if it would just proxy the `*Repo` methods for
  now, it already serves the purpose of having that layer, that can - by
  changing the implementation at that level - provide the shims to connect to
  any changed design underneath, while everything else doesn't require such.
  Say, we need `Dataset._vcs.is_annex` to replace the omnipresent
  `isinstance(Dataset.repo, AnnexRepo)`. Such a method could right now simply do
  that `isinstance` test and in that sense seem to be a pointless proxy. But if
  we were to decide that `AnnexRepo` is validated differently or is not derived
  from `GitRepo` anymore or whatever else, we change `VCS.is_annex`. No change
  to a command, extension or other third-party code. Conceptionally (and by
  name) it should not represent any particular concept of a VCS (like a
  repository, worktree or whatever) in order to not get into a situation where
  future changes make it unclear and confusing. Its notion has to be quite
  abstract.
- Have directly in `Dataset` declared `call_git/annex` methods (that for now are
  simply proxies of course via `._vcs`). If one wants to be fancy we might be
  able to create the mentioned "semi-command" idea, but I think this is simple
  and straightforward.
- With the above, we can then make sure, that all commands in core and our
  extensions actually go through it.
- Then it would be time to actually deprecate `Dataset.repo` with a proper
  `DeprecationWarning`. Earlier isn't going to work, because even our own code
  base would spam the user with those warnings. However, the documentation of
  "don't use this" should come ASAP.
- Actually shaping that `VCS` class will take time. Ideally one would want to
  see high-level functionality that is used across commands and is somewhat
  abstracted from "what exact kind of repo am I on?" (I think we thought about a
  unified interface across repo flavors several times anyway). A possible route
  could be, what @mih did in his PR about caching `*Repo` results via a command
  specific `StaticRepo`. That kind of RF'ing could help to get a better
  understanding what it is, that a command actually needs and wants to do/know
  when invoking those methods (that is regardless of what I think of that
  particular way of caching).

I started drafting this in #5797.


WDYT @datalad/developers? Agree in general or not? Suggestions for a (slightly)
different approach?
