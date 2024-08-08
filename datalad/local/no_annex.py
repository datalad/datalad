# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""configure which dataset parts to never put in the annex"""


__docformat__ = 'restructuredtext'

from datalad.interface.base import (
    Interface,
    build_doc,
)


@build_doc
class NoAnnex(Interface):
    """Configure a dataset to never put some content into the dataset's annex

    This can be useful in mixed datasets that also contain textual data, such
    as source code, which can be efficiently and more conveniently managed
    directly in Git.

    Patterns generally look like this::

      code/*

    which would match all file in the code directory. In order to match all
    files under ``code/``, including all its subdirectories use such a
    pattern::

      code/**

    Note that this command works incrementally, hence any existing configuration
    (e.g. from a previous plugin run) is amended, not replaced.
    """
    from datalad.distribution.dataset import (
        EnsureDataset,
        datasetmethod,
    )
    from datalad.interface.base import eval_results
    from datalad.support.constraints import EnsureNone
    from datalad.support.param import Parameter

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to configure. If no dataset is given,
            an attempt is made to identify the dataset based on the current
            working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        pattern=Parameter(
            args=("--pattern",),
            nargs='+',
            doc="""list of path patterns. Any content whose path is matching
            any pattern will not be annexed when added to a dataset, but
            instead will be tracked directly in Git. Path pattern have to be
            relative to the directory given by the `ref_dir` option. By
            default, patterns should be relative to the root of the dataset."""),
        ref_dir=Parameter(
            args=("--ref-dir",),
            doc="""Relative path (within the dataset) to the directory that is
            to be configured. All patterns are interpreted relative to this
            path, and configuration is written to a ``.gitattributes`` file in
            this directory."""),
        makedirs=Parameter(
            args=("--makedirs",),
            action='store_true',
            doc="""If set, any missing directories will be created in order to
            be able to place a file into ``--ref-dir``."""),
    )

    @staticmethod
    @datasetmethod(name='no_annex')
    @eval_results
    # TODO*: make dataset, pattern into kwargs after *,?
    def __call__(dataset, pattern, ref_dir='.', makedirs=False):
        # could be extended to accept actual largefile expressions
        from os import makedirs as makedirsfx
        from os.path import (
            exists,
            isabs,
        )
        from os.path import join as opj

        from datalad.distribution.dataset import require_dataset
        from datalad.support.annexrepo import AnnexRepo
        from datalad.utils import ensure_list

        pattern = ensure_list(pattern)
        ds = require_dataset(dataset, check_installed=True,
                             purpose='no_annex configuration')

        res_kwargs = dict(
            path=ds.path,
            type='dataset',
            action='no_annex',
        )

        # all the ways we refused to cooperate
        if not isinstance(ds.repo, AnnexRepo):
            yield dict(
                res_kwargs,
                status='notneeded',
                message='dataset has no annex')
            return
        if any(isabs(p) for p in pattern):
            yield dict(
                res_kwargs,
                status='error',
                message=('path pattern for `no_annex` configuration must be relative paths: %s',
                         pattern))
            return
        if isabs(ref_dir):
            yield dict(
                res_kwargs,
                status='error',
                message=('`ref_dir` for `no_annex` configuration must be a relative path: %s',
                         ref_dir))
            return

        gitattr_dir = opj(ds.path, ref_dir)
        if not exists(gitattr_dir):
            if makedirs:
                makedirsfx(gitattr_dir)
            else:
                yield dict(
                    res_kwargs,
                    status='error',
                    message='target directory for `no_annex` does not exist (consider makedirs=True)')
                return

        gitattr_file = opj(gitattr_dir, '.gitattributes')
        ds.repo.set_gitattributes(
            [(p, {'annex.largefiles': 'nothing'}) for p in pattern],
            attrfile=gitattr_file)
        yield dict(res_kwargs, status='ok')

        yield from ds.save(
            gitattr_file,
            to_git=True,
            message="[DATALAD] exclude paths from annex'ing",
            result_filter=None,
            result_xfm=None,
            return_type='generator',
            result_renderer='disabled',
        )
