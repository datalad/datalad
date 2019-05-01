# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Benchmarks of the basic repos (Git/Annex) functionality"""

from .common import (
    SampleSuperDatasetBenchmarks,
    SuprocBenchmarks,
)


# TODO: probably SampleSuperDatasetBenchmarks is not the best for these benchmarks
#       but we are yet to make it parametric so we could sweep through a set
#       of typical scenarios
class gitrepo(SampleSuperDatasetBenchmarks):

    def time_get_content_info(self):
        info = self.repo.get_content_info()
        assert isinstance(info, dict)   # just so we do not end up with a generator
