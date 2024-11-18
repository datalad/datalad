# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Common interface options

"""

__docformat__ = 'restructuredtext'

from datalad.interface.results import known_result_xfms
from datalad.support.constraints import (
    EnsureBool,
    EnsureCallable,
    EnsureChoice,
    EnsureInt,
    EnsureNone,
    EnsureStr,
    EnsureStrPrefix,
)
from datalad.support.param import Parameter

location_description = Parameter(
    args=("-D", "--description",),
    constraints=EnsureStr() | EnsureNone(),
    doc="""short description to use for a dataset location. Its primary
    purpose is to help humans to identify a dataset copy (e.g., "mike's dataset
    on lab server"). Note that when a dataset is published, this information
    becomes available on the remote side.""")

recursion_flag = Parameter(
    args=("-r", "--recursive",),
    action="store_true",
    doc="""if set, recurse into potential subdatasets""")

recursion_limit = Parameter(
    args=("-R", "--recursion-limit",),
    metavar="LEVELS",
    constraints=EnsureInt() | EnsureNone(),
    doc="""limit recursion into subdatasets to the given number of levels""")

contains = Parameter(
    args=('--contains',),
    metavar='PATH',
    action='append',
    doc="""limit to the subdatasets containing the
    given path. If a root path of a subdataset is given, the last
    considered dataset will be the subdataset itself.[CMD:  This
    option can be given multiple times CMD][PY:  Can be a list with
    multiple paths PY], in which case datasets that
    contain any of the given paths will be considered.""",
    constraints=EnsureStr() | EnsureNone())

fulfilled = Parameter(
    args=("--fulfilled",),
    doc="""DEPRECATED: use [CMD: --state CMD][PY: `state` PY]
    instead. If given, must be a boolean flag indicating whether
    to consider either only locally present or absent datasets.
    By default all subdatasets are considered regardless of their
    status.""",
    constraints=EnsureBool() | EnsureNone())

dataset_state = Parameter(
    args=("--state",),
    doc="""indicate which (sub)datasets to consider: either only locally present,
    absent, or any of those two kinds.
    """,
    # yoh: intentionally left out the description of default since might be
    # command specific
    constraints=EnsureChoice('present', 'absent', 'any'))

shared_access_opt = Parameter(
    args=('--shared-access',),
    metavar='MODE',
    doc="""configure shared access to a dataset, see `git init --shared`
    documentation for complete details on the supported scenarios. Possible
    values include: 'false', 'true', 'group', and 'all'""")

super_datasets_flag = Parameter(
    args=("-S", "--super-datasets",),
    action="store_true",
    doc="""if set, save a change in a dataset also in its superdataset""")

git_opts = Parameter(
    args=("--git-opts",),
    metavar='STRING',
    constraints=EnsureStr() | EnsureNone(),
    doc="""option string to be passed to :command:`git` calls""")

git_clone_opts = Parameter(
    args=("--git-clone-opts",),
    metavar='STRING',
    constraints=EnsureStr() | EnsureNone(),
    doc="""option string to be passed to :command:`git clone` calls""")

annex_opts = Parameter(
    args=("--annex-opts",),
    metavar='STRING',
    constraints=EnsureStr() | EnsureNone(),
    doc="""option string to be passed to :command:`git annex` calls""")

annex_init_opts = Parameter(
    args=("--annex-init-opts",),
    metavar='STRING',
    constraints=EnsureStr() | EnsureNone(),
    doc="""option string to be passed to :command:`git annex init` calls""")

annex_add_opts = Parameter(
    args=("--annex-add-opts",),
    metavar='STRING',
    constraints=EnsureStr() | EnsureNone(),
    doc="""option string to be passed to :command:`git annex add` calls""")

annex_get_opts = Parameter(
    args=("--annex-get-opts",),
    metavar='STRING',
    constraints=EnsureStr() | EnsureNone(),
    doc="""option string to be passed to :command:`git annex get` calls""")

annex_copy_opts = Parameter(
    args=("--annex-copy-opts",),
    metavar='STRING',
    constraints=EnsureStr() | EnsureNone(),
    doc="""option string to be passed to :command:`git annex copy` calls""")

allow_dirty = Parameter(
    args=("--allow-dirty",),
    action="store_true",
    doc="""flag that operating on a dirty repository (uncommitted or untracked content) is ok""")

if_dirty_opt = Parameter(
    args=("--if-dirty",),
    choices=('fail', 'save-before', 'ignore'),
    doc="""desired behavior if a dataset with unsaved changes is discovered:
    'fail' will trigger an error and further processing is aborted;
    'save-before' will save all changes prior any further action;
    'ignore' let's datalad proceed as if the dataset would not have unsaved
    changes.""")

nosave_opt = Parameter(
    args=("--nosave",),
    dest='save',
    action="store_false",
    doc="""by default all modifications to a dataset are immediately saved. Giving
    this option will disable this behavior.""")

save_message_opt = Parameter(
    args=("-m", "--message",),
    metavar='MESSAGE',
    doc="""a description of the state or the changes made to a dataset.""",
    constraints=EnsureStr() | EnsureNone())

message_file_opt = Parameter(
    args=("-F", "--message-file"),
    doc="""take the commit message from this file. This flag is
    mutually exclusive with -m.""",
    constraints=EnsureStr() | EnsureNone())

reckless_opt = Parameter(
    args=("--reckless",),
    # if no specific mode is given, set to auto
    const='auto',
    nargs='?',
    # boolean types only for backward compatibility
    constraints=
    EnsureChoice(None, True, False, 'auto', 'ephemeral') | \
    EnsureStrPrefix('shared-'),
    metavar='auto|ephemeral|shared-...',
    doc="""Obtain a dataset or subdatset and set it up in a potentially
    unsafe way for performance, or access reasons.
    Use with care, any dataset is marked as 'untrusted'.
    The reckless mode is stored in a dataset's local configuration under
    'datalad.clone.reckless', and will be inherited to any of its subdatasets.
    Supported modes are:
    ['auto']: hard-link files between local clones. In-place
    modification in any clone will alter original annex content.
    ['ephemeral']: symlink annex to origin's annex and discard local
    availability info via git-annex-dead 'here' and declares this annex private.
    Shares an annex between origin and clone w/o git-annex being aware of it.
    In case of a change in origin you need to update the clone before you're
    able to save new content on your end.
    Alternative to 'auto' when hardlinks are not an option, or number of consumed
    inodes needs to be minimized. Note that this mode can only be used with clones from
    non-bare repositories or a RIA store! Otherwise two different annex object tree
    structures (dirhashmixed vs dirhashlower) will be used simultaneously, and annex keys
    using the respective other structure will be inaccessible.
    ['shared-<mode>']: set up repository and annex permission to enable multi-user
    access. This disables the standard write protection of annex'ed files.
    <mode> can be any value support by 'git init --shared=', such as 'group', or
    'all'.""")

jobs_opt = Parameter(
    args=("-J", "--jobs"),
    metavar="NJOBS",
    default='auto',
    constraints=EnsureInt() | EnsureNone() | EnsureChoice('auto'),
    doc="""how many parallel jobs (where possible) to use. "auto" corresponds
    to the number defined by 'datalad.runtime.max-annex-jobs' configuration
    item""")

verbose = Parameter(
    args=("-v", "--verbose",),
    action="store_true",
    doc="""print out more detailed information while executing a command""")


as_common_datasrc = Parameter(
    args=("--as-common-datasrc",),
    metavar='NAME',
    doc="""configure the created sibling as a common data source of the
    dataset that can be automatically used by all consumers of the
    dataset (technical: git-annex auto-enabled special remote)""")


publish_depends = Parameter(
    args=("--publish-depends",),
    metavar='SIBLINGNAME',
    doc="""add a dependency such that the given existing sibling is
    always published prior to the new sibling. This equals setting a
    configuration item 'remote.SIBLINGNAME.datalad-publish-depends'.
    [PY: Multiple dependencies can be given as a list of sibling names
    PY][CMD: This option can be given more than once to configure multiple
    dependencies CMD]""",
    action='append',
    constraints=EnsureStr() | EnsureNone())

publish_by_default = Parameter(
    args=("--publish-by-default",),
    metavar='REFSPEC',
    doc="""add a refspec to be published to this sibling by default if nothing
    specified.""",
    constraints=EnsureStr() | EnsureNone(),
    action='append')

annex_wanted_opt = Parameter(
    args=("--annex-wanted",),
    metavar='EXPR',
    doc="""expression to specify 'wanted' content for the repository/sibling.
    See https://git-annex.branchable.com/git-annex-wanted/ for more
    information""",
    constraints=EnsureStr() | EnsureNone())

annex_required_opt = Parameter(
    args=("--annex-required",),
    metavar='EXPR',
    doc="""expression to specify 'required' content for the repository/sibling.
    See https://git-annex.branchable.com/git-annex-required/ for more
    information""",
    constraints=EnsureStr() | EnsureNone())

annex_group_opt = Parameter(
    args=("--annex-group",),
    metavar='EXPR',
    doc="""expression to specify a group for the repository.
    See https://git-annex.branchable.com/git-annex-group/ for more
    information""",
    constraints=EnsureStr() | EnsureNone())

annex_groupwanted_opt = Parameter(
    args=("--annex-groupwanted",),
    metavar='EXPR',
    doc="""expression for the groupwanted.
    Makes sense only if [PY: annex_wanted PY][CMD: --annex-wanted CMD]="groupwanted"
    and annex-group is given too.
    See https://git-annex.branchable.com/git-annex-groupwanted/ for more information""",
    constraints=EnsureStr() | EnsureNone())


inherit_opt = Parameter(
    args=("--inherit",),
    action="store_true",
    doc="""if sibling is missing, inherit settings (git config, git annex
    wanted/group/groupwanted) from its super-dataset""")

missing_sibling_opt = Parameter(
    args=("--missing",),
    constraints=EnsureChoice('fail', 'inherit', 'skip'),  # may be inherit-skip
    metavar='MODE',
    doc="""action to perform, if a sibling does not exist in a given dataset.
    By default it would fail the run ('fail' setting).  With 'inherit' a
    'create-sibling' with '--inherit-settings' will be used to create sibling
    on the remote. With 'skip' - it simply will be skipped.""")

with_plugin_opt = Parameter(
    args=('--with-plugin',),
    nargs='*',
    action='append',
    metavar='PLUGINSPEC',
    doc="""DataLad plugin to run in addition. PLUGINSPEC is a list
    comprised of a plugin name plus optional `key=value` pairs with arguments
    for the plugin call (see `plugin` command documentation for details).
    [PY: PLUGINSPECs must be wrapped in list where each item configures
    one plugin call. Plugins are called in the order defined by this list.
    PY][CMD: This option can be given more than once to run multiple plugins
    in the order in which they are given. CMD]""")

# define parameters to be used by eval_results to tune behavior
# Note: This is done outside eval_results in order to be available when building
# docstrings for the decorated functions
# TODO: May be we want to move them to be part of the classes _params. Depends
# on when and how eval_results actually has to determine the class.
# Alternatively build a callable class with these to even have a fake signature
# that matches the parameters, so they can be evaluated and defined the exact
# same way.

eval_params = dict(
    return_type=Parameter(
        doc="""return value behavior switch. If 'item-or-list' a single
        value is returned instead of a one-item return value list, or a
        list in case of multiple return values. `None` is return in case
        of an empty list.""",
        default='list',
        constraints=EnsureChoice('generator', 'list', 'item-or-list')),
    result_filter=Parameter(
        doc="""if given, each to-be-returned
        status dictionary is passed to this callable, and is only
        returned if the callable's return value does not
        evaluate to False or a ValueError exception is raised. If the given
        callable supports `**kwargs` it will additionally be passed the
        keyword arguments of the original API call.""",
        constraints=EnsureCallable() | EnsureNone()),
    result_xfm=Parameter(
        doc="""if given, each to-be-returned result
        status dictionary is passed to this callable, and its return value
        becomes the result instead. This is different from
        `result_filter`, as it can perform arbitrary transformation of the
        result value. This is mostly useful for top-level command invocations
        that need to provide the results in a particular format. Instead of
        a callable, a label for a pre-crafted result transformation can be
        given.""",
        constraints=EnsureChoice(*list(known_result_xfms.keys())) | EnsureCallable() | EnsureNone()),
    result_renderer=Parameter(
        doc="""select rendering mode command results.
        'tailored' enables a command-specific rendering style that is typically
        tailored to human consumption, if there is one for a specific
        command, or otherwise falls back on the the 'generic' result renderer;
        'generic' renders each result in one line  with key info like action,
        status, path, and an optional message);
        'json' a complete JSON line serialization of the full result record;
        'json_pp' like 'json', but pretty-printed spanning multiple lines;
        'disabled' turns off result rendering entirely;
        '<template>' reports any value(s) of any result properties in any
        format indicated by the template (e.g. '{path}', compare with JSON
        output for all key-value choices). The template syntax follows the
        Python "format() language". It is possible to report individual
        dictionary values, e.g. '{metadata[name]}'. If a 2nd-level key contains
        a colon, e.g. 'music:Genre', ':' must be substituted by '#' in the
        template, like so: '{metadata[music#Genre]}'.""",
        default='tailored'),
    on_failure=Parameter(
        doc="""behavior to perform on failure: 'ignore' any failure is reported,
        but does not cause an exception; 'continue' if any failure occurs an
        exception will be raised at the end, but processing other actions will
        continue for as long as possible; 'stop': processing will stop on first
        failure and an exception is raised. A failure is any result with status
        'impossible' or 'error'. Raised exception is an IncompleteResultsError
        that carries the result dictionaries of the failures in its `failed`
        attribute.""",
        default='continue',
        constraints=EnsureChoice('ignore', 'continue', 'stop')),
)

eval_defaults = {
    k: p.cmd_kwargs.get('default', None)
    for k, p in eval_params.items()
}
"""\
.. deprecated:: 0.16
   This variable will be removed in a future release. The default values for
   all Parameters (possibly overriding by command-specific settings) are now
   available as :class:`Interface` attributes.
"""
