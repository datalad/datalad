# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""[obsolete: use `siblings add`]
"""

__docformat__ = 'restructuredtext'


from datalad.utils import assure_list


# TODO the only reason this function is still here is that #1544
# isn't merged yet -- which removes the only remaining usage
def _check_deps(repo, deps):
    """Check if all `deps` remotes are known to the `repo`

    Raises
    ------
    ValueError
      if any of the deps is an unknown remote
    """
    unknown_deps = set(assure_list(deps)).difference(repo.get_remotes())
    if unknown_deps:
        raise ValueError(
            'unknown sibling(s) specified as publication dependency: %s'
            % unknown_deps)
