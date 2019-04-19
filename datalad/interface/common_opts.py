# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureInt, EnsureNone, EnsureStr
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureCallable


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
    doc="""if set, recurse into potential subdataset""")

recursion_limit = Parameter(
    args=("-R", "--recursion-limit",),
    metavar="LEVELS",
    constraints=EnsureInt() | EnsureNone(),
    doc="""limit recursion into subdataset to the given number of levels""")

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
    action="store_true",
    doc="""Set up the dataset to be able to obtain content in the
    cheapest/fastest possible way, even if this poses a potential
    risk the data integrity (e.g. hardlink files from a local clone
    of the dataset). Use with care, and limit to "read-only" use
    cases. With this flag the installed dataset will be marked as
    untrusted.""")

jobs_opt = Parameter(
    args=("-J", "--jobs"),
    metavar="NJOBS",
    default='auto',
    constraints=EnsureInt() | EnsureNone() | EnsureChoice('auto'),
    doc="""how many parallel jobs (where possible) to use.""")

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

merge_native_opt = Parameter(
    args=('--merge-native',),
    metavar='MODE',
    doc="""merge procedure to use when a dataset provides
    native metadata in some format. Such a dataset has to
    indicate the type of native metadata via its
    configuration setting ``datalad.metadata.nativetype``.
    Multiple different types of metadata are supported. Merging
    is performed in the order in which they are configured.
    Custom DataLad metadata always takes precedence over
    native metadata. Merge procedure modes are semantically
    identical to the corresponding manipulation arguments of
    [PY: `metadata()` PY][CMD: the 'metadata' command CMD].
    Setting the mode to 'none' disables merging of native
    metadata.""",
    constraints=EnsureChoice('init', 'add', 'reset', 'none'))

reporton_opt = Parameter(
    args=('--reporton',),
    metavar='TYPE',
    doc="""choose on what type result to report on: 'datasets',
    'files', 'all' (both datasets and files), or 'none' (no report).""",
    constraints=EnsureChoice('all', 'datasets', 'files', 'none'))
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
        doc="""format of return value rendering on stdout""",
        constraints=EnsureChoice('default', 'json', 'json_pp', 'tailored') | EnsureNone()),
    on_failure=Parameter(
        doc="""behavior to perform on failure: 'ignore' any failure is reported,
        but does not cause an exception; 'continue' if any failure occurs an
        exception will be raised at the end, but processing other actions will
        continue for as long as possible; 'stop': processing will stop on first
        failure and an exception is raised. A failure is any result with status
        'impossible' or 'error'. Raised exception is an IncompleteResultsError
        that carries the result dictionaries of the failures in its `failed`
        attribute.""",
        constraints=EnsureChoice('ignore', 'continue', 'stop')),
    proc_pre=Parameter(
        doc="""DataLad procedure to run prior to the main command. The argument
        a list of lists with procedure names and optional arguments.
        Procedures are called in the order their are given in this list.
        It is important to provide the respective target dataset to run a procedure
        on as the `dataset` argument of the main command."""),
    proc_post=Parameter(
        doc="""Like `proc_pre`, but procedures are executed after the main command
        has finished."""),
)

eval_defaults = dict(
    return_type='list',
    result_filter=None,
    result_renderer=None,
    result_xfm=None,
    on_failure='continue',
    proc_pre=None,
    proc_post=None,
)
