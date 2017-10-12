# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utilities for test repositories
"""


import os
import tempfile

from .. import _TEMP_PATHS_GENERATED
from ..utils import get_tempfile_kwargs

from ...utils import better_wraps
from ...utils import optional_args




# decorator replacing "with_testrepos":
# - delivers instances of TestRepo* classes instead of paths
# - call assertions (TestRepo*.assert_intact())
#   before and optionally afterwards
# - create new one every time, so we can have defined dirty states?
#   => combine with the option above: If the test is not supposed to change
#   anything, assert_unchanged is triggered and it is okay to use an existing
#   instance
# - no 'network' flavor, but just 'serve_path_via_http' instead?


# Should there be remote location available to install/clone from?
# => needs to be optional, since cloning would loose untracked/staged things
#    as well as other branches. So it's possibly not reasonable for some of
#    the test repos


# - a location for annexed "remote" content
# (see remote_file_fd, remote_file_path)



# TODO: - Our actual tests could instantiate Items (without creating them!) to
#         represent changes and then just call assert_intact() to test for
#         everything without the need to think of everything when writing the
#         test.
#       - That way, we can have helper functions for such assertions like:
#         take that file from the TestRepo and those changes I specified and
#         test, whether or not those changes and those changes only actually
#         apply. This would just copy the Item from TestRepo, inject the changes
#         and call assert_intact()


##################


# TODO: some standard "remote" files; classes like ItemInfoFile?
#################### OLD: #########################################

# we need a local file, that is supposed to be treated as a remote file via
# file-scheme URL
remote_file_fd, remote_file_path = \
    tempfile.mkstemp(**get_tempfile_kwargs({}, prefix='testrepo'))
# to be removed upon teardown
_TEMP_PATHS_GENERATED.append(remote_file_path)
with open(remote_file_path, "w") as f:
    f.write("content to be annex-addurl'd")
# OS-level descriptor needs to be closed!
os.close(remote_file_fd)
###################################################################

@optional_args
def with_testrepos_new(t, read_only=False, selector='all'):
    # selector: regex again?
    # based on class names or name/keyword strings?

    # TODO: if possible provide a signature that's (temporarily) compatible with
    # old one to ease RF'ing

    # TODO: if assert_intact fails and readonly == True, re-create for other tests

    @better_wraps(t)
    def new_func(*arg, **kw):
        pass

# TODO: known_failure_XXX needs opt_arg 'testrepo' to pass the TestRepo
# class(es) the test does fail on.
