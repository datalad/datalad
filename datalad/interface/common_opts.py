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

add_to_superdataset = Parameter(
    args=("--add-to-super",),
    doc="""add the new dataset as a component to a super dataset""",
    action="store_true")

git_opts = Parameter(
    args=("--git-opts",),
    metavar='STRING',
    constraints=EnsureStr() | EnsureNone(),
    doc="""option string to be passed to :command:`git` calls""")

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
