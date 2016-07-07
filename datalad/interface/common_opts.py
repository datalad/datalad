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

dataset_description = Parameter(
    args=("-D", "--description",),
    doc="""short description of this dataset instance that humans can use to
    identify the repository/location, e.g. "Precious data on my laptop.""")

git_opts = Parameter(
    args=("--git-opts",),
    doc="""options string to be passed to :cmd:`git` calls""")

annex_opts = Parameter(
    args=("--annex-opts",),
    doc="""options string to be passed to :cmd:`git annex` calls""")

annex_init_opts = Parameter(
    args=("--annex-init-opts",),
    doc="""options string to be passed to :cmd:`git annex init` calls""")

