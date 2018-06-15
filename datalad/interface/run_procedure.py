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
from datalad.support.exceptions import InsufficientArgumentsError

from datalad.utils import assure_list

# bound dataset methods
from datalad.interface.run import Run

lgr = logging.getLogger('datalad.interface.run_procedures')


def _get_file_match(dir, name='*'):
    targets = (name, ('[!_]*.py'), ('[!_]*.sh'))
    lgr.debug("Looking for procedure '%s' in '%s'", name, dir)
    for target in targets:
        for m in iglob(op.join(dir, target)):
            m_bn = op.basename(m)
            if name == '*' or m_bn == name or m_bn.startswith('{}.'.format(name)):
                yield m


def _get_procedure_implementation(name='*', ds=None):
    ds = ds if isinstance(ds, Dataset) else Dataset(ds) if ds else None
    # 1. check dataset for procedure
    if ds is not None and ds.is_installed():
        # could be more than one
        dirs = assure_list(ds.config.obtain('datalad.locations.dataset-procedures'))
        for dir in dirs:
            # TODO `get` dirs if necessary
            for m in _get_file_match(op.join(ds.path, dir), name):
                yield m
    # 2. check system and user account for procedure
    for loc in (cfg.obtain('datalad.locations.user-procedures'),
                cfg.obtain('datalad.locations.system-procedures')):
        for dir in assure_list(loc):
            for m in _get_file_match(dir, name):
                yield m
    # 3. check extensions for procedure
    # delay heavy import until here
    from pkg_resources import iter_entry_points
    from pkg_resources import resource_isdir
    from pkg_resources import resource_filename
    for entry_point in iter_entry_points('datalad.extensions'):
        # use of '/' here is OK wrt to platform compatibility
        if resource_isdir(entry_point.module_name, 'resources/procedures'):
            for m in _get_file_match(
                    resource_filename(
                        entry_point.module_name,
                        'resources/procedures'),
                    name):
                yield m
    # 4. at last check datalad itself for procedure
    for m in _get_file_match(
            resource_filename('datalad', 'resources/procedures'),
            name):
        yield m


def _guess_exec(script_file):
    # TODO check for exec permission and rely on interpreter
    if os.stat(script_file).st_mode & stat.S_IEXEC:
        return ('executable', u'"{script}" "{ds}" {args}')
    elif script_file.endswith('.sh'):
        return (u'bash_script', u'bash "{script}" "{ds}" {args}')
    elif script_file.endswith('.py'):
        return (u'python_script', u'python "{script}" "{ds}" {args}')
    else:
        return None


@build_doc
class RunProcedure(Interface):
    """Run prepared procedures (DataLad scripts) on a dataset

    *Concept*

    A "procedure" is an algorithm with the purpose to process a dataset in a
    particular way. Procedures can be useful in a wide range of scenarios,
    like adjusting dataset configuration in a uniform fashion, populating
    a dataset with particular content, or automating other routine tasks,
    such as synchronizing dataset content with certain siblings.

    Implementations of some procedures are shipped together with DataLad,
    but additional procedures can be provided by 1) any DataLad extension,
    2) any dataset, 3) a local user, or 4) a local system administrator.
    DataLad will look for procedures in the following locations and order:

    Directories identified by the configuration settings

    - 'datalad.locations.dataset-procedures'
    - 'datalad.locations.user-procedures' (determined by
      appdirs.user_config_dir; defaults to '$HOME/.config/datalad/procedures'
      on GNU/Linux systems)
    - 'datalad.locations.system-procedures' (determined by
      appdirs.site_config_dir; defaults to '/etc/xdg/datalad/procedures' on
      GNU/Linux systems)

    and subsequently in the 'resources/procedures/' directories of any
    installed extension, and, lastly, of the DataLad installation itself.

    Each configuration setting can occur multiple times to indicate multiple
    directories to be searched. If a procedure matching a given name is found
    (filename without a possible extension), the search is aborted and this
    implementation will be executed. This makes it possible for individual
    datasets, users, or machines to override externally provided procedures
    (enabling the implementation of cutomizable processing "hooks").


    *Procedure implementation*

    A procedure can be any executable. Executables must have the appropriate
    permissions and, in the case of a script, must contain an appropriate
    "shebang" line. If a procedure is not executable, but its filename ends
    with '.py', it is automatically executed by the 'python' interpreter
    (whichever version is available in the present environment). Likewise,
    procedure implementations ending on '.sh' are executed via 'bash'.

    Procedures can implement any argument handling, but must be capable
    of taking at least one positional argument (the absolute path to the
    dataset they shall operate on).


    *Customize other commands with procedures*

    On execution of any commands, DataLad inspects two additional
    configuration settings:

    - 'datalad.<name>.proc-pre'

    - 'datalad.<name>.proc-post'

    where '<name>' is the name of a DataLad command. Using this mechanism
    DataLad can be instructed to run one or more procedures before or
    after the execution of a given command. For example, configuring
    a set of metadata types in any newly created dataset can be achieved
    via:

      % datalad -c 'datalad.create.proc-post=cfg_metadatatypes xmp image' create -d myds

    As procedures run on datasets, it is necessary to explicitly identify
    the target dataset via the -d (--dataset) option.
    """
    _params_ = dict(
        spec=Parameter(
            args=("spec",),
            metavar='NAME [ARGS]',
            nargs=REMAINDER,
            doc="""Name and possibly additional arguments of the
            to-be-executed procedure."""),
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="PATH",
            doc="""specify the dataset to run the procedure on.
            An attempt is made to identify the dataset based on the current
            working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        discover=Parameter(
            args=('--discover',),
            action='store_true',
            doc="""if given, all configured paths are searched for procedures
            and one result record per discovered procedure is yielded, but
            no procedure is executed"""),
    )

    @staticmethod
    @datasetmethod(name='run_procedure')
    @eval_results
    def __call__(
            spec=None,
            dataset=None,
            discover=False):
        if not spec and not discover:
            raise InsufficientArgumentsError('requires at least a procedure name')

        ds = require_dataset(
            dataset, check_installed=False,
            purpose='run a procedure') if dataset else None

        if discover:
            reported = set()
            for m in _get_procedure_implementation('*', ds=ds):
                if m in reported:
                    continue
                cmd_type, cmd_tmpl = _guess_exec(m)
                res = get_status_dict(
                    action='run_procedure',
                    path=m,
                    type='file',
                    logger=lgr,
                    refds=ds.path if ds else None,
                    status='ok',
                    procedure_type=cmd_type,
                    procedure_callfmt=cmd_tmpl,
                    message=cmd_type)
                reported.add(m)
                yield res
            return

        if not isinstance(spec, (tuple, list)):
            # maybe coming from config
            import shlex
            spec = shlex.split(spec)
        name = spec[0]
        args = spec[1:]

        try:
            # get the first match an run with it
            procedure_file = next(_get_procedure_implementation(name, ds=ds))
        except StopIteration:
            # TODO error result
            raise ValueError("Cannot find procedure with name '%s'", name)

        cmd_type, cmd_tmpl = _guess_exec(procedure_file)
        if cmd_tmpl is None:
            raise ValueError(
                "No idea how to execute procedure %s. Missing 'execute' permissions?",
                procedure_file)
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
                explicit=True,
                inputs=None,
                outputs=None,
                # pass through here
                on_failure='ignore',
        ):
            yield r
