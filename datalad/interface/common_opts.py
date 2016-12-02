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

from datalad.support.param import Parameter
from datalad.support.constraints import EnsureInt, EnsureNone, EnsureStr


dataset_description = Parameter(
    args=("-D", "--description",),
    constraints=EnsureStr() | EnsureNone(),
    doc="""short description of this dataset instance that humans can use to
    identify the repository/location, e.g. "Precious data on my laptop.""")

recursion_flag = Parameter(
    args=("-r", "--recursive",),
    action="store_true",
    doc="""if set, recurse into potential subdataset""")

recursion_limit = Parameter(
    args=("--recursion-limit",),
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
    doc="""if set, traverse and save stats corresponding to the change
    within super-datasets""")

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
    doc="""by default all modifications to a dataset are immediately saved. Given
    this option will disable this behavior.""")

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
    constraints=EnsureInt() | EnsureNone(),
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
    doc="""add a dependency such that the given exsiting sibling is
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

