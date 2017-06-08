# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers for benchmarks of DataLad"""

import timeit


class SuprocBenchmarks(object):
    # manually set a number since otherwise takes way too long!
    # see https://github.com/spacetelescope/asv/issues/497
    #number = 3
    # although seems to work ok with a timer which accounts for subprocesses

    # custom timer so we account for subprocess times
    timer = timeit.default_timer


