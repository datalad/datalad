# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run prepared procedures (DataLad scripts) on a dataset"""

__docformat__ = 'restructuredtext'


import logging

from glob import iglob
from argparse import REMAINDER
import os
import os.path as op
import stat

from datalad import cfg
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict

from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.distribution.dataset import datasetmethod

from datalad.utils import assure_list

# bound dataset methods
from datalad.interface.run import Run

lgr = logging.getLogger('datalad.interface.run_procedures')


def _get_file_match(name, dir):
    targets = (name, ('[!_]*.py'), ('[!_]*.sh'))
    lgr.debug("Looking for procedure '%s' in '%s'", name, dir)
    for target in targets:
        for m in iglob(op.join(dir, target)):
            m_bn = op.basename(m)
            if m_bn == name or m_bn.startswith('{}.'.format(name)):
                return m


def _get_procedure_implementation(name, ds=None):
    ds = ds if isinstance(ds, Dataset) else Dataset(ds) if ds else None
    # 1. check dataset for procedure
    if ds is not None and ds.is_installed():
        # could be more than one
        dirs = assure_list(ds.config.obtain('datalad.locations.dataset-procedures'))
        for dir in dirs:
            # TODO `get` dirs if necessary
            m = _get_file_match(name, op.join(ds.path, dir))
            if m:
                return m
    # 2. check system and user account for procedure
    for loc in (cfg.obtain('datalad.locations.user-procedures'),
                cfg.obtain('datalad.locations.system-procedures')):
        for dir in assure_list(loc):
            m = _get_file_match(name, dir)
            if m:
                return m
    # 3. check extensions for procedure
    # delay heavy import until here
    from pkg_resources import iter_entry_points
    from pkg_resources import resource_isdir
    from pkg_resources import resource_filename
    for entry_point in iter_entry_points('datalad.extensions'):
        # use of '/' here is OK wrt to platform compatibility
        if resource_isdir(entry_point.module_name, 'resources/procedures'):
            m = _get_file_match(
                name,
                resource_filename(
                    entry_point.module_name,
                    'resources/procedures'))
            if m:
                return m
    # 4. at last check datalad itself for procedure
    return _get_file_match(
        name,
        resource_filename('datalad', 'resources/procedures'))


def _guess_exec(script_file):
    # TODO check for exec permission and rely on interpreter
    if os.stat(script_file).st_mode & stat.S_IEXEC:
        return u'"{script}" "{ds}" {args}'
    elif script_file.endswith('.sh'):
        return u'bash "{script}" "{ds}" {args}'
    elif script_file.endswith('.py'):
        return u'python "{script}" "{ds}" {args}'
    raise ValueError("NO IDEA")


@build_doc
class RunProcedure(Interface):
    """
    DO stuff
    datalad.locations.dataset-procedures
    datalad.locations.user-procedures
    datalad.locations.system-procedures
    """
    _params_ = dict(
        spec=Parameter(
            args=("spec",),
            metavar='NAME [ARGS]',
            nargs=REMAINDER,
            doc=""),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to record the command results in.
            An attempt is made to identify the dataset based on the current
            working directory. If a dataset is given, the command will be
            executed in the root directory of this dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='run_procedure')
    @eval_results
    def __call__(
            spec,
            dataset=None):
        if not isinstance(spec, (tuple, list)):
            # maybe coming from config
            import shlex
            spec = shlex.split(spec)
        name = spec[0]
        args = spec[1:]
        procedure_file = _get_procedure_implementation(name, ds=dataset)
        if not procedure_file:
            # TODO error result
            raise ValueError("Cannot find procedure with name '%s'", name)

        ds = require_dataset(
            dataset, check_installed=False,
            purpose='run a procedure') if dataset else None

        cmd_tmpl = _guess_exec(procedure_file)
        cmd = cmd_tmpl.format(
            script=procedure_file,
            ds=ds.path if ds else '',
            args=u' '.join(u'"{}"'.format(a) for a in args) if args else '')
        lgr.debug('Attempt to run procedure {} as: {}'.format(
            name,
            cmd))
        for r in Run.__call__(
                cmd=cmd,
                dataset=ds,
                # See gh-2593 for discussion on run feature extension
                #explicit=True,
                #inputs=None,
                #outputs=None,
                # pass through here
                on_failure='ignore',
        ):
            yield r
