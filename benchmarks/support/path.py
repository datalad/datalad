# Import functions to be tested with _ suffix and name the suite after the
# original function so we could easily benchmark it e.g. by
#    asv run --python=same -b get_parent_paths
# without need to discover what benchmark to use etc

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
