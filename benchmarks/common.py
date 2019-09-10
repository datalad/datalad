# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers for benchmarks of DataLad"""

import os
import sys
import tarfile
import tempfile
import timeit
import os.path as op
from glob import glob

from datalad.utils import (
    create_tree,
    chpwd,
    getpwd,
    get_tempfile_kwargs,
    rmtree,
)

from datalad.api import (
    Dataset,
    create_test_dataset,
)

############
# Monkey patches

# Robust is_interactive.  Should be not needed since 0.11.4
# https://github.com/datalad/datalad/pull/3268
def _is_stream_tty(stream):
    try:
        # TODO: check on windows if hasattr check would work correctly and
        # add value:
        return stream.isatty()
    except ValueError as exc:
        # Who knows why it is a ValueError, but let's try to be specific
        # If there is a problem with I/O - non-interactive, otherwise reraise
        if "I/O" in str(exc):
            return False
        raise


def is_interactive():
    """Return True if all in/outs are tty"""
    return all(_is_stream_tty(s) for s in (sys.stdin, sys.stdout, sys.stderr))


class SuprocBenchmarks(object):
    # manually set a number since otherwise takes way too long!
    # see https://github.com/spacetelescope/asv/issues/497
    #number = 3
    # although seems to work ok with a timer which accounts for subprocesses

    # custom timer so we account for subprocess times
    timer = timeit.default_timer

    _monkey_patched = False

    def __init__(self):
        if not self._monkey_patched:
            # monkey patch things if needed
            # ASV started to close one of the std streams since some point
            # which caused our is_interactive to fail.  We need to provide
            # more robust version
            from datalad.support.external_versions import external_versions
            # comparing to 0.12.1  since the returned version is "loose"
            # so fails correctly identify rc as pre .0
            if external_versions['datalad'] < '0.12.1':
                from datalad import utils
                from datalad.interface import ls
                utils.is_interactive = is_interactive
                ls.is_interactive = is_interactive
            SuprocBenchmarks._monkey_patched = True
        self.remove_paths = []

    def _cleanup(self):
        if not self.remove_paths:
            return  # Nothing TODO
        self.log("Cleaning up %d paths: %s",
                 len(self.remove_paths), ', '.join(self.remove_paths))
        while self.remove_paths:
            path = self.remove_paths.pop()
            #if op.lexists(path):
            #    rmtree(path)

    def teardown(self):
        self._cleanup()

    def __del__(self):
        # We will at least try
        # self.log("%s is being __del__'ed", self.__class__)
        try:
            self._cleanup()
        except:
            pass

    def log(self, msg, *args):
        """Consistent benchmarks logging"""
        # print("BM: "+ str(msg % tuple(args)))


class SampleDatasetBenchmarksBase(SuprocBenchmarks):
    """
    Setup a sample hierarchy of datasets to be used
    """

    timeout = 3600
    # need to assure that we are working in a different repository now
    # see https://github.com/datalad/datalad/issues/1512
    # might not be sufficient due to side effects between tests and
    # thus getting into the same situation
    ds_count = 0

    # Creating in CWD so things get removed when ASV is done
    #  https://asv.readthedocs.io/en/stable/writing_benchmarks.html
    # that is where it would be run and cleaned up after

    # Subclasses should define
    dsname = None

    @property
    def tarfile(self):
        return '%s.tar' % self.dsname

    def create_test_dataset(self, path):
        """An abstract method to be implemented in subclasses.

        Should return a path to the sample dataset
        """
        raise NotImplementedError()

    # Apparently asv "identifies" setup_cache by its location in the code,
    # so we cannot take advantage from delegation!  Derived classes
    # will need to have a new setup_cache to just call _setup_cache
    # actually doing the work delegating to their create_test_dataset
    def setup_cache(self):
        raise NotImplementedError()
        # in subclasses should be
        # return self._setup_cache()

    def _setup_cache(self):
        self.log("%s.setup_cache for %s ran in %s", self, self.dsname, getpwd())
        # according to https://asv.readthedocs.io/en/stable/writing_benchmarks.html
        # setup_cache is executed in a temporary directory.
        # yoh thought to use some "guaranteed to be temp" directory but
        # it is hard/impossible to then store it across instances.
        # So all code below assumes that PWD is already a sensible one to create
        # temp structures in
        dspath = self.dsname
        # Will store into a tarfile since otherwise install -r is way too slow
        # to be invoked for every benchmark
        self.create_test_dataset(dspath)
        with tarfile.open(self.tarfile, "w") as tar:
            # F.CK -- Python tarfile can't later extract those because key dirs are
            # read-only.  For now just a workaround - make it all writeable
            from datalad.utils import rotree
            rotree(self.dsname, ro=False, chmod_files=False)
            tar.add(self.dsname, recursive=True)
        rmtree(self.dsname)

    def setup(self):
        self.log("%s.setup ran in %s, existing paths: %s", self, getpwd(), glob('*'))

        tempdir = tempfile.mkdtemp(
            **get_tempfile_kwargs({}, prefix="bm")
        )
        self.remove_paths.append(tempdir)
        with tarfile.open(self.tarfile) as tar:
            tar.extractall(tempdir)

        # TODO -- remove this abomination after https://github.com/datalad/datalad/issues/1512 is fixed
        epath = op.join(tempdir, self.dsname)
        epath_unique = epath + str(self.__class__.ds_count)
        os.rename(epath, epath_unique)
        self.__class__.ds_count += 1
        self.ds = Dataset(epath_unique)
        self.repo = self.ds.repo

        self.paths_level0 = paths = sorted(glob('*'))
        assert len(paths) >= 2
        self.half_paths_level0 = paths[:len(paths) // 2]

        self.log("Finished setup for %s", tempdir)


class SavedDataset(object):
    """Class to mix-in to assure that created dataset is saved and not dirty.

    In a mix-in should come first among classes so its .create_test_dataset
    is called before the actual one producing a dataset
    """

    def create_test_dataset(self, path):
        super(SavedDataset, self).create_test_dataset(path)
        ds = Dataset(path)
        assert ds.repo.dirty  # Otherwise no sense to mix this class in
        ds.save('.')
        assert not ds.repo.dirty  # we should be all clean

    # This mix-in shouldn't bother with setup_cache since just a mix-in


class Sample222Dataset(SampleDatasetBenchmarksBase):
    """Our benchmark setup which uses create_test_dataset with 2/-2/-2
    configuration.
    """

    dsname = 'testds1'

    def create_test_dataset(self, path):
        create_test_dataset(
            path
            , spec='2/-2/-2'
            , seed=0
        )

    def setup_cache(self):
        return self._setup_cache()


class Heavy1Dataset(SampleDatasetBenchmarksBase):
    """Setup a relatively heavy dataset in number of files. It will loosely
    mimic having a collection of .fsf files and corresponding .feat directories.
    Ending up with ~1,000 files, some of which are text some annexed.
    """

    dsname = 'testds-heavy1'

    def create_test_dataset(self, path):
        from datalad.distribution.dataset import require_dataset

        ds = Dataset(path).create()
        # place .dat to to annex
        ds.repo.set_gitattributes([
            ('*.dat', {'annex.largefiles': "anything"})])

        git_attributes_file = op.join(ds.path, '.gitattributes')
        ds.save(
            git_attributes_file,
            message="Instruct annex to add text files to Git")

        # Initiate initial one with following feat directories
        self._create_tree(path, range(10))
        # Dataset is not saved on purpose so we could implement benchmarks.
        # Mix-in SavedDataset

    def setup_cache(self):
        return self._setup_cache()

    def _create_tree(
            self,
            path,
            feat_indexes=range(10),
            subdirs=('logs', 'reg', 'reg_standard', 'stats', 'custom_timing_files'),
            files_indexes=range(10),
            txt_content_fmt="content{file_index}",
            fsf_content_fmt="design for {feat_index}",
            seed=0
            ):
        """

        Parameters
        ----------
        path
        feat_indexes: iterable of int, optional
          List of indexes for feat directories. If already exists, might then
          be "rewritten"
        files_indexes: iterable of int, optional
          Which "indexed" files within subdirectories to create
        subdirs: iterable of str
          Subdirectories within each .feat one.
        seed: None or int
          If None - no reseeding will be done
        """
        import numpy as np
        if seed is not None:
            np.random.seed(seed)

        tree = {}
        for feat_index in feat_indexes:
            # 50/50 in binary vs text files. All small
            subtree = {}
            for subdir in subdirs:
                subsubtree = {}
                for file_index in files_indexes:
                    prefix = "file%03d." % file_index
                    subsubtree[prefix + 'txt'] = txt_content_fmt.format(**locals())
                    subsubtree[prefix + 'dat'] = np.random.bytes(file_index)  # grow in size, since why not?
                subtree[subdir] = subsubtree
            tree.update(
                {'sub-%03d.fsf' % feat_index: fsf_content_fmt.format(**locals()),
                 'sub-%03d.feat' % feat_index: subtree}
            )
            create_tree(path, tree)


class Heavy1SavedDataset(SavedDataset, Heavy1Dataset):
    dsname = Heavy1Dataset.dsname + '-saved'

    def setup_cache(self):
        return self._setup_cache()
