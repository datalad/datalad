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
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureBool


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

jobs_opt = Parameter(
    args=("-J", "--jobs"),
    metavar="NJOBS",
    constraints=EnsureInt() | EnsureNone(),
    doc="""how many parallel jobs (where possible) to use.""")

verbose = Parameter(
    args=("-v", "--verbose",),
    action="store_true",
    doc="""print out more detailed information while executing a command""")