# Import functions to be tested with _ suffix and name the suite after the
# original function so we could easily benchmark it e.g. by
#    asv run --python=same -b get_parent_paths
# without need to discover what benchmark to use etc

import random

from datalad.support.path import get_filtered_paths_
from datalad.support.path import get_parent_paths as get_parent_paths_

from ..common import SuprocBenchmarks


class get_parent_paths(SuprocBenchmarks):

    def setup(self):
        # prepare some more or less realistic with a good number of paths
        # and some hierarchy of submodules
        self.nfiles = 40  # per each construct
        self.nsubmod = 30  # at two levels
        self.toplevel_submods = ['submod%d' % i for i in range(self.nsubmod)]
        self.posixpaths = \
            ['file%d' % i for i in range(self.nfiles)] + \
            ['subdir/anotherfile%d' % i for i in range(self.nfiles)]
        for submod in range(self.nsubmod):
            self.posixpaths += \
                ['submod%d/file%d' % (submod, i) for i in range(self.nfiles)] + \
                ['subdir/submod%d/file%d' % (submod, i) for i in range(self.nfiles)] + \
                ['submod/sub%d/file%d' % (submod, i) for i in range(self.nfiles)]

    def time_no_submods(self):
        assert get_parent_paths_(self.posixpaths, [], True) == []

    def time_one_submod_toplevel(self):
        get_parent_paths_(self.posixpaths, ['submod9'], True)

    def time_one_submod_subdir(self):
        get_parent_paths_(self.posixpaths, ['subdir/submod9'], True)

    def time_allsubmods_toplevel_only(self):
        get_parent_paths_(self.posixpaths, self.toplevel_submods, True)

    def time_allsubmods_toplevel(self):
        get_parent_paths_(self.posixpaths, self.toplevel_submods)


class get_filtered_paths(SuprocBenchmarks):
    # The same paths as used by GitRepo.get_submodules_ when a dataset has
    # many files and the caller limits the result to some directories

    def setup(self):
        rng = random.Random(0)
        self.paths = ['d%d/s%d/f%d.txt' % (i // 100, i // 10, i)
                      for i in range(8000)]
        rng.shuffle(self.paths)
        self.filters = ['d%d' % i for i in range(0, 80, 4)]
        self.deep_paths = ['a%d/b%d/c%d/f%d' % (i % 5, i % 25, i % 125, i)
                           for i in range(2000)]
        self.deep_filters = sorted(
            {'a%d/b%d/c%d' % (i % 5, i % 25, i % 125) for i in range(250)})
        self.small_paths = ['a/b', 'a/c', 'b/d', 'c']
        self.small_filters = ['a', 'b']

    def time_many_paths_dir_filters(self):
        list(get_filtered_paths_(self.paths, self.filters,
                                 include_within_path=True))

    def time_many_paths_dir_filters_not_within(self):
        list(get_filtered_paths_(self.paths, self.filters,
                                 include_within_path=False))

    def time_deep_filters(self):
        list(get_filtered_paths_(self.deep_paths, self.deep_filters,
                                 include_within_path=True))

    def time_few_paths(self):
        list(get_filtered_paths_(self.small_paths, self.small_filters,
                                 include_within_path=True))
