# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run prepared procedures (DataLad scripts) on a dataset"""

__docformat__ = 'restructuredtext'


import logging
import os
import os.path as op
import stat
import sys
from argparse import REMAINDER
from glob import iglob

import datalad.support.ansi_colors as ac
from datalad import cfg
from datalad.core.local.run import Run
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.results import get_status_dict
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import (
    InsufficientArgumentsError,
    NoDatasetFound,
)
from datalad.support.param import Parameter
from datalad.utils import (
    ensure_list,
    guard_for_format,
    join_cmdline,
    quote_cmdlinearg,
    split_cmdline,
)

if sys.version_info < (3, 9):
    from importlib_resources import (
        as_file,
        files,
    )
else:
    from importlib.resources import (
        as_file,
        files,
    )

lgr = logging.getLogger('datalad.local.run_procedures')


def _get_file_match(dir, name='*'):
    targets = (name, ('[!_]*.py'), ('[!_]*.sh'))
    lgr.debug("Looking for procedure '%s' in '%s'", name, dir)
    for target in targets:
        for m in iglob(op.join(dir, target)):
            m_bn = op.basename(m)
            if name == '*':
                report_name = m_bn[:-3] if m_bn.endswith('.py') or \
                                           m_bn.endswith('.sh') \
                                        else m_bn
                yield m, report_name
            elif m_bn == name or m_bn.startswith('{}.'.format(name)):
                yield m, name


def _get_proc_config(name, ds=None):
    """get configuration of named procedure

    Figures call format string and help message for a given procedure name,
    based on dataset.

    Returns
    -------
    tuple
      (call format string, help string) or possibly None for either value,
      if there's nothing configured
    """
    # figure what ConfigManager to ask
    cm = cfg if ds is None else ds.config
    # ConfigManager may not be up-to-date, particularly if we are in a
    # subdataset due to recursion in `_get_procedure_implementation` where
    # outside caller operates (and reloads) on superdataset only. With
    # force=False, this shouldn't be expensive.
    cm.reload()
    # ConfigManager might return a tuple for different reasons.
    # The config might have been defined multiple times in the same location
    # (within .datalad/config for example) or there are multiple values for
    # it on different levels of git-config (system, user, repo). git-config
    # in turn does report such things ordered from most general to most
    # specific configuration. We do want the most specific one here, so
    # config.get(), which returns the last entry, works here.
    # TODO: At this point we cannot determine whether it was actually
    # configured to yield several values by the very same config, in which
    # case we should actually issue a warning, since we then have no idea
    # of a priority. But ConfigManager isn't able yet to tell us or to
    # restrict the possibility to define multiple values to particular items
    v = cm.get('datalad.procedures.{}.call-format'.format(name), None)
    h = cm.get('datalad.procedures.{}.help'.format(name), None)
    return v, h


def _get_procedure_implementation(name='*', ds=None):
    """get potential procedures: path, name, configuration, and a help message

    The order of consideration is user-level, system-level, extra locations, dataset,
    datalad extensions, datalad. Therefore local definitions/configurations take
    precedence over ones, that come from outside (via a datalad-extension or a
    dataset with its .datalad/config). If a dataset had precedence (as it was
    before), the addition (or just an update) of a (sub-)dataset would otherwise
    surprisingly cause you to execute code different from what you defined
    within ~/.gitconfig or your local repository's .git/config.
    So, local definitions take precedence over remote ones and more specific
    ones over more general ones.

    Yields
    ------
    tuple
      path, name, format string, help message
    """

    ds = ds if isinstance(ds, Dataset) else Dataset(ds) if ds else None

    # 1. check system and user account for procedure
    for loc in (cfg.obtain('datalad.locations.user-procedures'),
                cfg.obtain('datalad.locations.system-procedures'),
                cfg.get('datalad.locations.extra-procedures', get_all=True)):
        for dir in ensure_list(loc):
            for m, n in _get_file_match(dir, name):
                yield (m, n,) + _get_proc_config(n)
    # 2. check dataset for procedure
    if ds is not None and ds.is_installed():
        # could be more than one
        dirs = ensure_list(
                ds.config.obtain('datalad.locations.dataset-procedures'))
        for dir in dirs:
            # TODO `get` dirs if necessary
            for m, n in _get_file_match(op.join(ds.path, dir), name):
                yield (m, n,) + _get_proc_config(n, ds=ds)
        # 2.1. check subdatasets recursively
        for subds in ds.subdatasets(return_type='generator',
                                    result_xfm='datasets',
                                    result_renderer='disabled'):
            for m, n, f, h in _get_procedure_implementation(name=name, ds=subds):
                yield m, n, f, h

    # 3. check extensions for procedure
    from datalad.support.entrypoints import iter_entrypoints

    for epname, epmodule, _ in iter_entrypoints('datalad.extensions'):
        res = files(epmodule) / "resources" / "procedures"
        if res.is_dir():
            with as_file(res) as p:
                for m, n in _get_file_match(p, name):
                    yield (m, n,) + _get_proc_config(n)
    # 4. at last check datalad itself for procedure
    with as_file(files("datalad") / "resources" / "procedures") as p:
        for m, n in _get_file_match(p, name):
            yield (m, n,) + _get_proc_config(n)


def _guess_exec(script_file):
    try:
        is_exec = os.stat(script_file).st_mode & stat.S_IEXEC
    except OSError as e:
        from errno import ENOENT
        if e.errno == ENOENT and op.islink(script_file):
            # broken symlink
            # does not exist; there's nothing to detect at all
            return {'type': None, 'template': None, 'state': 'absent'}
        else:
            raise e

    # on some FS the executable bit might not be all that reliable
    # but a procedure might nevertheless be supported.
    # go by extension with "known" interpreters first, and only then
    # try to execute something that looks executable
    if script_file.endswith('.sh'):
        return {'type': u'bash_script',
                'template': u'bash {script} {ds} {args}',
                'state': 'executable'}
    elif script_file.endswith('.py'):
        ex = quote_cmdlinearg(sys.executable)
        return {'type': u'python_script',
                'template': u'%s {script} {ds} {args}' % ex,
                'state': 'executable'}
    elif is_exec and not os.path.isdir(script_file):
        return {'type': u'executable',
                'template': u'{script} {ds} {args}',
                'state': 'executable'}
    else:
        return {'type': None, 'template': None, 'state': None}


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
    2) any (sub-)dataset, 3) a local user, or 4) a local system administrator.
    DataLad will look for procedures in the following locations and order:

    Directories identified by the configuration settings

    - 'datalad.locations.user-procedures' (determined by
      platformdirs.user_config_dir; defaults to '$HOME/.config/datalad/procedures'
      on GNU/Linux systems)
    - 'datalad.locations.system-procedures' (determined by
      platformdirs.site_config_dir; defaults to '/etc/xdg/datalad/procedures' on
      GNU/Linux systems)
    - 'datalad.locations.dataset-procedures'

    and subsequently in the 'resources/procedures/' directories of any
    installed extension, and, lastly, of the DataLad installation itself.

    Please note that a dataset that defines
    'datalad.locations.dataset-procedures' provides its procedures to
    any dataset it is a subdataset of. That way you can have a collection of
    such procedures in a dedicated dataset and install it as a subdataset into
    any dataset you want to use those procedures with. In case of a naming
    conflict with such a dataset hierarchy, the dataset you're calling
    run-procedures on will take precedence over its subdatasets and so on.

    Each configuration setting can occur multiple times to indicate multiple
    directories to be searched. If a procedure matching a given name is found
    (filename without a possible extension), the search is aborted and this
    implementation will be executed. This makes it possible for individual
    datasets, users, or machines to override externally provided procedures
    (enabling the implementation of customizable processing "hooks").


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

    For further customization there are two configuration settings per procedure
    available:

    - 'datalad.procedures.<NAME>.call-format'
      fully customizable format string to determine how to execute procedure
      NAME (see also datalad-run).
      It currently requires to include the following placeholders:

      - '{script}': will be replaced by the path to the procedure
      - '{ds}': will be replaced by the absolute path to the dataset the
        procedure shall operate on
      - '{args}': (not actually required) will be replaced by
        [CMD: all additional arguments passed into run-procedure after NAME CMD]
        [PY: all but the first element of `spec` if `spec` is a list or tuple PY]
        As an example the default format string for a call to a python script is:
        "python {script} {ds} {args}"
    - 'datalad.procedures.<NAME>.help'
      will be shown on `datalad run-procedure --help-proc NAME` to provide a
      description and/or usage info for procedure NAME
    """
    _params_ = dict(
        spec=Parameter(
            args=("spec",),
            metavar='NAME [ARGS]',
            nargs=REMAINDER,
            doc="""Name and possibly additional arguments of the to-be-executed
            procedure. [PY: Can also be a dictionary coming from
            run-procedure(discover=True).][CMD: Note, that all options
            to run-procedure need to be put before NAME, since all
            ARGS get assigned to NAME CMD]"""),
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
        help_proc=Parameter(
            args=('--help-proc',),
            action='store_true',
            doc="""if given, get a help message for procedure NAME from config
            setting datalad.procedures.NAME.help"""
        )
    )

    _examples_ = [
        dict(text="Find out which procedures are available on the current system",
             code_py="run_procedure(discover=True)",
             code_cmd="datalad run-procedure --discover"),
        dict(text="Run the 'yoda' procedure in the current dataset",
             code_py="run_procedure(spec='cfg_yoda', recursive=True)",
             code_cmd="datalad run-procedure cfg_yoda"),
    ]

    result_renderer = 'tailored'

    @staticmethod
    @datasetmethod(name='run_procedure')
    @eval_results
    def __call__(
            spec=None,
            *,
            dataset=None,
            discover=False,
            help_proc=False):
        if not spec and not discover:
            raise InsufficientArgumentsError('requires at least a procedure name')
        if help_proc and not spec:
            raise InsufficientArgumentsError('requires a procedure name')

        try:
            ds = require_dataset(
                dataset, check_installed=False,
                purpose='run a procedure')
        except NoDatasetFound:
            ds = None

        if discover:
            # specific path of procedures that were already reported
            reported = set()
            # specific names of procedure for which an active one has been
            # found
            active = set()
            for m, cmd_name, cmd_tmpl, cmd_help in \
                    _get_procedure_implementation('*', ds=ds):
                if m in reported:
                    continue
                ex = _guess_exec(m)
                # configured template (call-format string) takes precedence:
                if cmd_tmpl:
                    ex['template'] = cmd_tmpl
                if ex['state'] is None:
                    # doesn't seem like a match
                    lgr.debug("%s does not look like a procedure, ignored.", m)
                    continue
                state = 'overridden' if cmd_name in active else ex['state']
                message = ex['type'] if ex['type'] else 'unknown type'
                message += ' ({})'.format(state) if state != 'executable' else ''
                res = get_status_dict(
                    action='discover_procedure',
                    path=m,
                    type='file',
                    logger=lgr,
                    refds=ds.path if ds else None,
                    status='ok',
                    state=state,
                    procedure_name=cmd_name,
                    procedure_type=ex['type'],
                    procedure_callfmt=ex['template'],
                    procedure_help=cmd_help,
                    message=message)
                reported.add(m)
                if state == 'executable':
                    active.add(cmd_name)
                yield res
            return


        if isinstance(spec, dict):
            # Skip getting procedure implementation if called with a
            # dictionary (presumably coming from --discover)
            procedure_file = spec['path']
            cmd_name = spec['procedure_name']
            cmd_tmpl = spec['procedure_callfmt']
            cmd_help = spec['procedure_help']

            name = cmd_name
            args = []

        else:

            if not isinstance(spec, (tuple, list)):
                # maybe coming from config
                spec = split_cmdline(spec)
            name = spec[0]
            args = spec[1:]

            try:
                # get the first match an run with it
                procedure_file, cmd_name, cmd_tmpl, cmd_help = \
                    next(_get_procedure_implementation(name, ds=ds))
            except StopIteration:
                raise ValueError("Cannot find procedure with name '%s'" % name)

        ex = _guess_exec(procedure_file)
        # configured template (call-format string) takes precedence:
        if cmd_tmpl:
            ex['template'] = cmd_tmpl

        if help_proc:
            if cmd_help:
                res = get_status_dict(
                        action='procedure_help',
                        path=procedure_file,
                        type='file',
                        logger=lgr,
                        refds=ds.path if ds else None,
                        status='ok',
                        state=ex['state'],
                        procedure_name=cmd_name,
                        procedure_type=ex['type'],
                        procedure_callfmt=ex['template'],
                        message=cmd_help)
            else:
                res = get_status_dict(
                        action='procedure_help',
                        path=procedure_file,
                        type='file',
                        logger=lgr,
                        refds=ds.path if ds else None,
                        status='impossible',
                        state=ex['state'],
                        procedure_name=cmd_name,
                        procedure_type=ex['type'],
                        procedure_callfmt=ex['template'],
                        message="No help available for '%s'" % name)

            yield res
            return

        if not ex['template']:
            raise ValueError("No idea how to execute procedure %s. "
                             "Missing 'execute' permissions?" % procedure_file)

        cmd = ex['template'].format(
            script=guard_for_format(quote_cmdlinearg(procedure_file)),
            ds=guard_for_format(quote_cmdlinearg(ds.path)) if ds else '',
            args=join_cmdline(args) if args else '')
        lgr.info(u"Running procedure %s", name)
        lgr.debug(u'Full procedure command: %r', cmd)
        for r in Run.__call__(
                cmd=cmd,
                dataset=ds,
                explicit=True,
                inputs=None,
                outputs=None,
                # pass through here
                on_failure='ignore',
                return_type='generator',
                result_renderer='disabled'
        ):
            yield r

        if ds:
            # the procedure ran and we have to anticipate that it might have
            # changed the dataset config, so we need to trigger an unforced
            # reload.
            # we have to do this despite "being done here", because
            # run_procedure() runs in the same process and reuses dataset (config
            # manager) instances, and the next interaction with a dataset should
            # be able to count on an up-to-date config
            ds.config.reload()

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.interface.utils import generic_result_renderer
        from datalad.ui import ui

        if res['status'] != 'ok' or 'procedure' not in res.get('action', ''):
            # it's not our business
            generic_result_renderer(res)
            return

        if kwargs.get('discover', None):
            ui.message('{name} ({path}){msg}'.format(
                # bold-faced name, if active
                name=ac.color_word(res['procedure_name'], ac.BOLD)
                if res['state'] == 'executable' else res['procedure_name'],
                path=res['path'],
                msg=' [{}]'.format(
                    res['message'][0] % res['message'][1:]
                    if isinstance(res['message'], tuple) else res['message'])
                if 'message' in res else ''
            ))

        elif kwargs.get('help_proc', None):
            ui.message('{name} ({path}){help}'.format(
                name=ac.color_word(res['procedure_name'], ac.BOLD),
                path=op.relpath(
                    res['path'],
                    res['refds'])
                if res.get('refds', None) else res['path'],
                help='{nl}{msg}'.format(
                    nl=os.linesep,
                    msg=res['message'][0] % res['message'][1:]
                    if isinstance(res['message'], tuple) else res['message'])
                if 'message' in res else ''
            ))

        else:
            generic_result_renderer(res)
