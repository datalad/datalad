# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Snakemake wrapper"""

__docformat__ = 'restructuredtext'


import logging
from argparse import (
    REMAINDER,
)

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.support.constraints import (
    EnsureNone,
)
from datalad.support.param import Parameter
from datalad.distribution.dataset import (
    require_dataset,
)
from datalad.utils import (
    ensure_list,
)

from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
)

lgr = logging.getLogger('datalad.local.snakemake')


@build_doc
class SnakeMake(Interface):
    """
    """
    _params_ = dict(
        dataset=Parameter(
            # not really needed on the cmdline, but for PY to resolve relative
            # paths
            args=("-d", "--dataset"),
            doc="""""",
            constraints=EnsureDataset() | EnsureNone()),
        smargs=Parameter(
            args=("smargs",),
            metavar='SNAKEMAKE ARGUMENTS',
            nargs=REMAINDER,
            doc="""Start with '--' before any snakemake argument to ensure
            such arguments are not processed by DataLad."""),
    )

    @staticmethod
    @datasetmethod(name='snakemake')
    @eval_results
    def __call__(
            smargs=None,
            dataset=None):
        sm_args = ensure_list(smargs)
        # DataLad's argparse setup is too funky to understand
        # it is safe to prepend '--' to the args that should
        # actually reach snakemake (incl. --help and --version)
        # otherwise there is a chance that DataLad is very smart and
        # rejects stuff, even though we declare REMAINDER...
        if sm_args and sm_args[0] == '--':
            sm_args = sm_args[1:]
        sm_argv = ['snakemake']
        sm_argv.extend(sm_args)

        # we need to inject a dataset handle into snakemake
        ds = require_dataset(dataset, check_installed=True,
                             purpose='snakemake data IO')

        # import the patches for snakemake
        from .snakemake_monkeypatch import DataLadSnakeMakeIOFile
        from unittest.mock import patch
        # inject a new file abstraction and patch that one with a
        # dataset instance. This is within a context manager, so should
        # be a safe approach, even when other snakemake commands are around.
        # we also patch sys.argv, because snakemake ignores the argv argument
        # of the entrypoint
        with patch('snakemake.io._IOFile', DataLadSnakeMakeIOFile), \
                patch('snakemake.io._IOFile._datalad_dataset', ds), \
                patch('sys.argv', sm_argv):
            # we go in the same way snakemake cmdline does
            from pkg_resources import load_entry_point
            sm = load_entry_point('snakemake', 'console_scripts', 'snakemake')
            # snakemake produces no return value, but uses sys.exit extensively
            try:
                sm()
            except SystemExit as e:
                # we don't want snakemake to kill datalad (think persistent
                # python session), so catch, report, return
                if e.code:
                    yield dict(
                        action='snakemake',
                        status='error',
                        exitcode=e.code,
                        message=('snakemake exited with code %i', e.code)
                    )
                    return
        yield dict(
            action='snakemake',
            status='ok',
        )
