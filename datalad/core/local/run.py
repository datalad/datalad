# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run arbitrary commands and track how they modify a dataset"""

__docformat__ = 'restructuredtext'


import json
import logging
import os
import os.path as op
import warnings
from argparse import REMAINDER
from pathlib import Path
from tempfile import mkdtemp

import datalad
import datalad.support.ansi_colors as ac
from datalad.config import anything2bool
from datalad.core.local.save import Save
from datalad.core.local.status import Status
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.distribution.get import Get
from datalad.distribution.install import Install
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    jobs_opt,
    save_message_opt,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import (
    eval_results,
    generic_result_renderer,
)
from datalad.local.unlock import Unlock
from datalad.support.constraints import (
    EnsureBool,
    EnsureChoice,
    EnsureNone,
)
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
)
from datalad.support.globbedpaths import GlobbedPaths
from datalad.support.json_py import dump2stream
from datalad.support.param import Parameter
from datalad.ui import ui
from datalad.utils import (
    SequenceFormatter,
    chpwd,
    ensure_list,
    ensure_unicode,
    get_dataset_root,
    getpwd,
    join_cmdline,
    quote_cmdlinearg,
)

lgr = logging.getLogger('datalad.core.local.run')


def _format_cmd_shorty(cmd):
    """Get short string representation from a cmd argument list"""
    cmd_shorty = (join_cmdline(cmd) if isinstance(cmd, list) else cmd)
    cmd_shorty = u'{}{}'.format(
        cmd_shorty[:40],
        '...' if len(cmd_shorty) > 40 else '')
    return cmd_shorty


assume_ready_opt = Parameter(
    args=("--assume-ready",),
    constraints=EnsureChoice(None, "inputs", "outputs", "both"),
    doc="""Assume that inputs do not need to be retrieved and/or outputs do not
    need to unlocked or removed before running the command. This option allows
    you to avoid the expense of these preparation steps if you know that they
    are unnecessary.""")


@build_doc
class Run(Interface):
    """Run an arbitrary shell command and record its impact on a dataset.

    It is recommended to craft the command such that it can run in the root
    directory of the dataset that the command will be recorded in. However,
    as long as the command is executed somewhere underneath the dataset root,
    the exact location will be recorded relative to the dataset root.

    If the executed command did not alter the dataset in any way, no record of
    the command execution is made.

    If the given command errors, a `CommandError` exception with the same exit
    code will be raised, and no modifications will be saved. A command
    execution will not be attempted, by default, when an error occurred during
    input or output preparation. This default ``stop`` behavior can be
    overridden via [CMD: --on-failure ... CMD][PY: `on_failure=...` PY].

    *Command format*

    || REFLOW >>
    A few placeholders are supported in the command via Python format
    specification. "{pwd}" will be replaced with the full path of the current
    working directory. "{dspath}" will be replaced with the full path of the
    dataset that run is invoked on. "{tmpdir}" will be replaced with the full
    path of a temporary directory. "{inputs}" and "{outputs}" represent the
    values specified by [CMD: --input and --output CMD][PY: `inputs` and
    `outputs` PY]. If multiple values are specified, the values will be joined
    by a space. The order of the values will match that order from the command
    line, with any globs expanded in alphabetical order (like bash). Individual
    values can be accessed with an integer index (e.g., "{inputs[0]}").
    << REFLOW ||

    || REFLOW >>
    Note that the representation of the inputs or outputs in the formatted
    command string depends on whether the command is given as a list of
    arguments or as a string[CMD:  (quotes surrounding the command) CMD]. The
    concatenated list of inputs or outputs will be surrounded by quotes when
    the command is given as a list but not when it is given as a string. This
    means that the string form is required if you need to pass each input as a
    separate argument to a preceding script (i.e., write the command as
    "./script {inputs}", quotes included). The string form should also be used
    if the input or output paths contain spaces or other characters that need
    to be escaped.
    << REFLOW ||

    To escape a brace character, double it (i.e., "{{" or "}}").

    Custom placeholders can be added as configuration variables under
    "datalad.run.substitutions".  As an example:

      Add a placeholder "name" with the value "joe"::

        % datalad configuration --scope branch set datalad.run.substitutions.name=joe
        % datalad save -m "Configure name placeholder" .datalad/config

      Access the new placeholder in a command::

        % datalad run "echo my name is {name} >me"
    """
    _examples_ = [
        dict(text="Run an executable script and record the impact on a dataset",
             code_py="run(message='run my script', cmd='code/script.sh')",
             code_cmd="datalad run -m 'run my script' 'code/script.sh'"),
        dict(text="Run a command and specify a directory as a dependency "
                  "for the run. The contents of the dependency will be retrieved "
                  "prior to running the script",
             code_cmd="datalad run -m 'run my script' -i 'data/*' "
             "'code/script.sh'",
             code_py="""\
             run(cmd='code/script.sh', message='run my script',
                 inputs=['data/*'])"""),
        dict(text="Run an executable script and specify output files of the "
                  "script to be unlocked prior to running the script",
             code_py="""\
             run(cmd='code/script.sh', message='run my script',
                 inputs=['data/*'], outputs=['output_dir'])""",
             code_cmd="""\
             datalad run -m 'run my script' -i 'data/*' \\
             -o 'output_dir/*' 'code/script.sh'"""),
        dict(text="Specify multiple inputs and outputs",
             code_py="""\
             run(cmd='code/script.sh',
                 message='run my script',
                 inputs=['data/*', 'datafile.txt'],
                 outputs=['output_dir', 'outfile.txt'])""",
             code_cmd="""\
             datalad run -m 'run my script' -i 'data/*' \\
             -i 'datafile.txt' -o 'output_dir/*' -o \\
             'outfile.txt' 'code/script.sh'"""),
        dict(text="Use ** to match any file at any directory depth recursively. "
                  "Single * does not check files within matched directories.",
             code_py="""\
             run(cmd='code/script.sh',
                 message='run my script',
                 inputs=['data/**/*.dat'],
                 outputs=['output_dir/**'])""",
             code_cmd="""\
             datalad run -m 'run my script' -i 'data/**/*.dat' \\
             -o 'output_dir/**' 'code/script.sh'""")
    ]

    result_renderer = "tailored"
    # make run stop immediately on non-success results.
    # this prevents command execution after failure to obtain inputs of prepare
    # outputs. but it can be overriding via the common 'on_failure' parameter
    # if needed.
    on_failure = 'stop'

    _params_ = dict(
        cmd=Parameter(
            args=("cmd",),
            nargs=REMAINDER,
            metavar='COMMAND',
            doc="""command for execution. A leading '--' can be used to
            disambiguate this command from the preceding options to
            DataLad."""),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to record the command results in.
            An attempt is made to identify the dataset based on the current
            working directory. If a dataset is given, the command will be
            executed in the root directory of this dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        inputs=Parameter(
            args=("-i", "--input"),
            dest="inputs",
            metavar=("PATH"),
            action='append',
            doc="""A dependency for the run. Before running the command, the
            content for this relative path will be retrieved. A value of "." means "run
            :command:`datalad get .`". The value can also be a glob. [CMD: This
            option can be given more than once. CMD]"""),
        outputs=Parameter(
            args=("-o", "--output"),
            dest="outputs",
            metavar=("PATH"),
            action='append',
            doc="""Prepare this relative path to be an output file of the command. A
            value of "." means "run :command:`datalad unlock .`" (and will fail
            if some content isn't present). For any other value, if the content
            of this file is present, unlock the file. Otherwise, remove it. The
            value can also be a glob. [CMD: This option can be given more than
            once. CMD]"""),
        expand=Parameter(
            args=("--expand",),
            doc="""Expand globs when storing inputs and/or outputs in the
            commit message.""",
            constraints=EnsureChoice(None, "inputs", "outputs", "both")),
        assume_ready=assume_ready_opt,
        explicit=Parameter(
            args=("--explicit",),
            action="store_true",
            doc="""Consider the specification of inputs and outputs to be
            explicit. Don't warn if the repository is dirty, and only save
            modifications to the listed outputs."""),
        message=save_message_opt,
        sidecar=Parameter(
            args=('--sidecar',),
            metavar="{yes|no}",
            doc="""By default, the configuration variable
            'datalad.run.record-sidecar' determines whether a record with
            information on a command's execution is placed into a separate
            record file instead of the commit message (default: off). This
            option can be used to override the configured behavior on a
            case-by-case basis. Sidecar files are placed into the dataset's
            '.datalad/runinfo' directory (customizable via the
            'datalad.run.record-directory' configuration variable).""",
            constraints=EnsureNone() | EnsureBool()),
        dry_run=Parameter(
            # Leave out common -n short flag to avoid confusion with
            # `containers-run [-n|--container-name]`.
            args=("--dry-run",),
            doc="""Do not run the command; just display details about the
            command execution. A value of "basic" reports a few important
            details about the execution, including the expanded command and
            expanded inputs and outputs. "command" displays the expanded
            command only. Note that input and output globs underneath an
            uninstalled dataset will be left unexpanded because no subdatasets
            will be installed for a dry run.""",
            constraints=EnsureChoice(None, "basic", "command")),
        jobs=jobs_opt
    )
    _params_['jobs']._doc += """\
        NOTE: This option can only parallelize input retrieval (get) and output
        recording (save). DataLad does NOT parallelize your scripts for you.
    """

    @staticmethod
    @datasetmethod(name='run')
    @eval_results
    def __call__(
            cmd=None,
            *,
            dataset=None,
            inputs=None,
            outputs=None,
            expand=None,
            assume_ready=None,
            explicit=False,
            message=None,
            sidecar=None,
            dry_run=None,
            jobs=None):
        for r in run_command(cmd, dataset=dataset,
                             inputs=inputs, outputs=outputs,
                             expand=expand,
                             assume_ready=assume_ready,
                             explicit=explicit,
                             message=message,
                             sidecar=sidecar,
                             dry_run=dry_run,
                             jobs=jobs):
            yield r

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        dry_run = kwargs.get("dry_run")
        if dry_run and "dry_run_info" in res:
            if dry_run == "basic":
                _display_basic(res)
            elif dry_run == "command":
                ui.message(res["dry_run_info"]["cmd_expanded"])
            else:
                raise ValueError(f"Unknown dry-run mode: {dry_run!r}")
        else:
            if kwargs.get("on_failure") == "stop" and \
               res.get("action") == "run" and res.get("status") == "error":
                msg_path = res.get("msg_path")
                if msg_path:
                    ds_path = res["path"]
                    if datalad.get_apimode() == 'python':
                        help = f"\"Dataset('{ds_path}').save(path='.', " \
                               "recursive=True, message_file='%s')\""
                    else:
                        help = "'datalad save -d . -r -F %s'"
                    lgr.info(
                        "The command had a non-zero exit code. "
                        "If this is expected, you can save the changes with "
                        f"{help}",
                        # shorten to the relative path for a more concise
                        # message
                        Path(msg_path).relative_to(ds_path))
            generic_result_renderer(res)


def _display_basic(res):
    ui.message(ac.color_word("Dry run information", ac.MAGENTA))

    def fmt_line(key, value, multiline=False):
        return (" {key}:{sep}{value}"
                .format(key=ac.color_word(key, ac.BOLD),
                        sep=os.linesep + "  " if multiline else " ",
                        value=value))

    dry_run_info = res["dry_run_info"]
    lines = [fmt_line("location", dry_run_info["pwd_full"])]

    # TODO: Inputs and outputs could be pretty long. These may be worth
    # truncating.
    inputs = dry_run_info["inputs"]
    if inputs:
        lines.append(fmt_line("expanded inputs", inputs,
                              multiline=True))
    outputs = dry_run_info["outputs"]
    if outputs:
        lines.append(fmt_line("expanded outputs", outputs,
                              multiline=True))

    cmd = res["run_info"]["cmd"]
    cmd_expanded = dry_run_info["cmd_expanded"]
    lines.append(fmt_line("command", cmd, multiline=True))
    if cmd != cmd_expanded:
        lines.append(fmt_line("expanded command", cmd_expanded,
                              multiline=True))

    ui.message(os.linesep.join(lines))


def get_command_pwds(dataset):
    """Return the current directory for the dataset.

    Parameters
    ----------
    dataset : Dataset

    Returns
    -------
    A tuple, where the first item is the absolute path of the pwd and the
    second is the pwd relative to the dataset's path.
    """
    # Follow path resolution logic describe in gh-3435.
    if isinstance(dataset, Dataset):  # Paths relative to dataset.
        pwd = dataset.path
        rel_pwd = op.curdir
    else:                             # Paths relative to current directory.
        pwd = getpwd()
        # Pass pwd to get_dataset_root instead of os.path.curdir to handle
        # repos whose leading paths have a symlinked directory (see the
        # TMPDIR="/var/tmp/sym link" test case).
        if not dataset:
            dataset = get_dataset_root(pwd)

        if dataset:
            rel_pwd = op.relpath(pwd, dataset)
        else:
            rel_pwd = pwd  # and leave handling to caller
    return pwd, rel_pwd


def _dset_arg_kludge(arg):
    if isinstance(arg, Dataset):
        warnings.warn("Passing dataset instance is deprecated; "
                      "pass path as a string instead",
                      DeprecationWarning)
        arg = arg.path
    return arg


def _is_nonexistent_path(result):
    return (result.get("action") == "get" and
            result.get("status") == "impossible" and
            result.get("message") == "path does not exist")


def _install_and_reglob(dset_path, gpaths):
    """Install globbed subdatasets and repeat.

    Parameters
    ----------
    dset_path : str
    gpaths : GlobbedPaths object

    Returns
    -------
    Generator with the results of the `install` calls.
    """
    dset_path = _dset_arg_kludge(dset_path)

    def glob_dirs():
        return [d for d in map(op.dirname, gpaths.expand(refresh=True))
                # d could be an empty string because there are relative paths.
                if d]

    install = Install()
    dirs, dirs_new = [], glob_dirs()
    while dirs_new and dirs != dirs_new:
        for res in install(dataset=dset_path,
                           path=dirs_new,
                           result_xfm=None,
                           result_renderer='disabled',
                           return_type='generator',
                           on_failure='ignore'):
            if _is_nonexistent_path(res):
                lgr.debug("Skipping install of non-existent path: %s",
                          res["path"])
            else:
                yield res
        dirs, dirs_new = dirs_new, glob_dirs()


def prepare_inputs(dset_path, inputs, extra_inputs=None, jobs=None):
    """Prepare `inputs` for running a command.

    This consists of installing required subdatasets and getting the input
    files.

    Parameters
    ----------
    dset_path : str
    inputs : GlobbedPaths object
    extra_inputs : GlobbedPaths object, optional

    Returns
    -------
    Generator with the result records.
    """
    dset_path = _dset_arg_kludge(dset_path)

    gps = list(filter(bool, [inputs, extra_inputs]))
    if gps:
        lgr.info('Making sure inputs are available (this may take some time)')

    get = Get()
    for gp in gps:
        for res in _install_and_reglob(dset_path, gp):
            yield res
        if gp.misses:
            ds = Dataset(dset_path)
            for miss in gp.misses:
                yield get_status_dict(
                    action="run", ds=ds, status="error",
                    message=("Input did not match existing file: %s",
                             miss))
        yield from get(dataset=dset_path,
                       path=gp.expand_strict(),
                       on_failure='ignore',
                       result_renderer='disabled',
                       return_type='generator',
                       jobs=jobs)


def _unlock_or_remove(dset_path, paths, remove=False):
    """Unlock `paths` if content is present; remove otherwise.

    Parameters
    ----------
    dset_path : str
    paths : list of string
        Absolute paths of dataset files.
    remove : bool, optional
        If enabled, always remove instead of performing an availability test.

    Returns
    -------
    Generator with result records.
    """
    dset_path = _dset_arg_kludge(dset_path)

    existing = []
    for path in paths:
        if op.exists(path) or op.lexists(path):
            existing.append(path)
        else:
            # Avoid unlock's warning because output files may not exist in
            # common cases (e.g., when rerunning with --onto).
            lgr.debug("Filtered out non-existing path: %s", path)

    if not existing:
        return

    to_remove = []
    if remove:
        # when we force-remove, we use status to discover matching content
        # and let unlock's remove fallback handle these results
        to_remove = Status()(
            dataset=dset_path,
            path=existing,
            eval_subdataset_state='commit',
            untracked='no',
            annex='no',
            on_failure="ignore",
            # no rendering here, the relevant results are yielded below
            result_renderer='disabled',
            return_type='generator',
            # we only remove files, no subdatasets or directories
            result_filter=lambda x: x.get('type') in ('file', 'symlink'),
        )
    else:
        # Note: If Unlock() is given a directory (including a subdataset)
        # as a path, files without content present won't be reported, so
        # those cases aren't being covered by the "remove if not present"
        # logic below.
        for res in Unlock()(dataset=dset_path,
                            path=existing,
                            on_failure='ignore',
                            result_renderer='disabled',
                            return_type='generator'):
            if res["status"] == "impossible" and res["type"] == "file" \
               and "cannot unlock" in res["message"]:
                to_remove.append(res)
                continue
            yield res
    # Avoid `datalad remove` because it calls git-rm underneath, which will
    # remove leading directories if no other files remain. See gh-5486.
    for res in to_remove:
        try:
            os.unlink(res["path"])
        except OSError as exc:
            ce = CapturedException(exc)
            yield dict(res, action="run.remove", status="error",
                       message=("Removing file failed: %s", ce),
                       exception=ce)
        else:
            yield dict(res, action="run.remove", status="ok",
                       message="Removed file")


def normalize_command(command):
    """Convert `command` to the string representation.
    """
    if isinstance(command, list):
        command = list(map(ensure_unicode, command))
        if len(command) == 1 and command[0] != "--":
            # This is either a quoted compound shell command or a simple
            # one-item command. Pass it as is.
            #
            # FIXME: This covers the predominant command-line case, but, for
            # Python API callers, it means values like ["./script with spaces"]
            # requires additional string-like escaping, which is inconsistent
            # with the handling of multi-item lists (and subprocess's
            # handling). Once we have a way to detect "running from Python API"
            # (discussed in gh-2986), update this.
            command = command[0]
        else:
            if command and command[0] == "--":
                # Strip disambiguation marker. Note: "running from Python API"
                # FIXME from below applies to this too.
                command = command[1:]
            command = join_cmdline(command)
    else:
        command = ensure_unicode(command)
    return command


def format_command(dset, command, **kwds):
    """Plug in placeholders in `command`.

    Parameters
    ----------
    dset : Dataset
    command : str or list

    `kwds` is passed to the `format` call. `inputs` and `outputs` are converted
    to GlobbedPaths if necessary.

    Returns
    -------
    formatted command (str)
    """
    command = normalize_command(command)
    sfmt = SequenceFormatter()

    for k, v in dset.config.items("datalad.run.substitutions"):
        sub_key = k.replace("datalad.run.substitutions.", "")
        if sub_key not in kwds:
            kwds[sub_key] = v

    for name in ["inputs", "outputs"]:
        io_val = kwds.pop(name, None)
        if not isinstance(io_val, GlobbedPaths):
            io_val = GlobbedPaths(io_val, pwd=kwds.get("pwd"))
        kwds[name] = list(map(quote_cmdlinearg, io_val.expand(dot=False)))
    return sfmt.format(command, **kwds)


def _get_substitutions(dset):
    """Get substitution mapping

    Parameters
    ----------
    dset : Dataset
      Providing the to-be-queried configuration.

    Returns
    -------
    dict
      Mapping substitution keys to their values.
    """
    return {
        k.replace("datalad.run.substitutions.", ""): v
        for k, v in dset.config.items("datalad.run.substitutions")
    }


def _format_iospecs(specs, **kwargs):
    """Expand substitutions in specification lists.

    The expansion is generally a format() call on each items, using
    the kwargs as substitution mapping. A special case is, however,
    a single-item specification list that exclusively contains a
    plain substitution reference, i.e., ``{subst}``, that matches
    a kwargs-key (minus the brace chars), whose value is a list.
    In this case the entire specification list is substituted for
    the list in kwargs, which is returned as such. This enables
    the replace/re-use sequences, e.g. --inputs '{outputs}'

    Parameters
    ----------
    specs: list(str) or None
      Specification items to format.
    **kwargs:
      Placeholder key-value mapping to apply to specification items.

    Returns
    -------
    list
      All formatted items.
    """
    if not specs:
        return
    elif len(specs) == 1 and specs[0] \
            and specs[0][0] == '{' and specs[0][-1] == '}' \
            and isinstance(kwargs.get(specs[0][1:-1]), list):
        return kwargs[specs[0][1:-1]]
    return [
        s.format(**kwargs) for s in specs
    ]


def _execute_command(command, pwd):
    from datalad.cmd import WitlessRunner

    exc = None
    cmd_exitcode = None
    runner = WitlessRunner(cwd=pwd)
    try:
        lgr.info("== Command start (output follows) =====")
        runner.run(
            # command is always a string
            command
        )
    except CommandError as e:
        exc = e
        cmd_exitcode = e.code
    lgr.info("== Command exit (modification check follows) =====")
    return cmd_exitcode or 0, exc


def _prep_worktree(ds_path, pwd, globbed,
                   assume_ready=None, remove_outputs=False,
                   rerun_outputs=None,
                   jobs=None):
    """
    Yields
    ------
    dict
      Result records
    """
    # ATTN: For correct path handling, all dataset commands call should be
    # unbound. They should (1) receive a string dataset argument, (2) receive
    # relative paths, and (3) happen within a chpwd(pwd) context.
    with chpwd(pwd):
        for res in prepare_inputs(
                ds_path,
                [] if assume_ready in ["inputs", "both"]
                else globbed['inputs'],
                # Ignore --assume-ready for extra_inputs. It's an unexposed
                # implementation detail that lets wrappers sneak in inputs.
                extra_inputs=globbed['extra_inputs'],
                jobs=jobs):
            yield res

        if assume_ready not in ["outputs", "both"]:
            if globbed['outputs']:
                for res in _install_and_reglob(
                        ds_path, globbed['outputs']):
                    yield res
                for res in _unlock_or_remove(
                        ds_path,
                        globbed['outputs'].expand_strict()
                        if not remove_outputs
                        # when force-removing, exclude declared inputs
                        else set(
                            globbed['outputs'].expand_strict()).difference(
                                globbed['inputs'].expand_strict()),
                        remove=remove_outputs):
                    yield res

            if rerun_outputs is not None:
                for res in _unlock_or_remove(ds_path, rerun_outputs):
                    yield res


def _create_record(run_info, sidecar_flag, ds):
    """
    Returns
    -------
    str or None, str or None
      The first value is either the full run record in JSON serialized form,
      or content-based ID hash, if the record was written to a file. In that
      latter case, the second value is the path to the record sidecar file,
      or None otherwise.
    """
    record = json.dumps(run_info, indent=1, sort_keys=True, ensure_ascii=False)
    if sidecar_flag is None:
        use_sidecar = ds.config.get(
            'datalad.run.record-sidecar', default=False)
        use_sidecar = anything2bool(use_sidecar)
    else:
        use_sidecar = sidecar_flag

    record_id = None
    record_path = None
    if use_sidecar:
        # record ID is hash of record itself
        from hashlib import md5
        record_id = md5(record.encode('utf-8')).hexdigest()  # nosec
        record_dir = ds.config.get(
            'datalad.run.record-directory',
            default=op.join('.datalad', 'runinfo'))
        record_path = ds.pathobj / record_dir / record_id
        if not op.lexists(record_path):
            # go for compression, even for minimal records not much difference,
            # despite offset cost
            # wrap in list -- there is just one record
            dump2stream([run_info], record_path, compressed=True)
    return record_id or record, record_path


def run_command(cmd, dataset=None, inputs=None, outputs=None, expand=None,
                assume_ready=None, explicit=False, message=None, sidecar=None,
                dry_run=False, jobs=None,
                extra_info=None,
                rerun_info=None,
                extra_inputs=None,
                rerun_outputs=None,
                inject=False,
                parametric_record=False,
                remove_outputs=False,
                skip_dirtycheck=False,
                yield_expanded=None):
    """Run `cmd` in `dataset` and record the results.

    `Run.__call__` is a simple wrapper over this function. Aside from backward
    compatibility kludges, the only difference is that `Run.__call__` doesn't
    expose all the parameters of this function. The unexposed parameters are
    listed below.

    Parameters
    ----------
    extra_info : dict, optional
        Additional information to dump with the json run record. Any value
        given here will take precedence over the standard run key. Warning: To
        avoid collisions with future keys added by `run`, callers should try to
        use fairly specific key names and are encouraged to nest fields under a
        top-level "namespace" key (e.g., the project or extension name).
    rerun_info : dict, optional
        Record from a previous run. This is used internally by `rerun`.
    extra_inputs : list, optional
        Inputs to use in addition to those specified by `inputs`. Unlike
        `inputs`, these will not be injected into the {inputs} format field.
    rerun_outputs : list, optional
        Outputs, in addition to those in `outputs`, determined automatically
        from a previous run. This is used internally by `rerun`.
    inject : bool, optional
        Record results as if a command was run, skipping input and output
        preparation and command execution. In this mode, the caller is
        responsible for ensuring that the state of the working tree is
        appropriate for recording the command's results.
    parametric_record : bool, optional
        If enabled, substitution placeholders in the input/output specification
        are retained verbatim in the run record. This enables using a single
        run record for multiple different re-runs via individual
        parametrization.
    remove_outputs : bool, optional
        If enabled, all declared outputs will be removed prior command
        execution, except for paths that are also declared inputs.
    skip_dirtycheck : bool, optional
        If enabled, a check for dataset modifications is unconditionally
        disabled, even if other parameters would indicate otherwise. This
        can be used by callers that already performed analog verififcations
        to avoid duplicate processing.
    yield_expanded : {'inputs', 'outputs', 'both'}, optional
        Include a 'expanded_%s' item into the run result with the exanded list
        of paths matching the inputs and/or outputs specification,
        respectively.


    Yields
    ------
    Result records for the run.
    """
    if not cmd:
        lgr.warning("No command given")
        return

    specs = {
        k: ensure_list(v) for k, v in (('inputs', inputs),
                                       ('extra_inputs', extra_inputs),
                                       ('outputs', outputs))
    }

    rel_pwd = rerun_info.get('pwd') if rerun_info else None
    if rel_pwd and dataset:
        # recording is relative to the dataset
        pwd = op.normpath(op.join(dataset.path, rel_pwd))
        rel_pwd = op.relpath(pwd, dataset.path)
    else:
        pwd, rel_pwd = get_command_pwds(dataset)

    ds = require_dataset(
        dataset, check_installed=True,
        purpose='track command outcomes')
    ds_path = ds.path

    lgr.debug('tracking command output underneath %s', ds)

    # skip for callers that already take care of this
    if not (skip_dirtycheck or rerun_info or inject):
        # For explicit=True, we probably want to check whether any inputs have
        # modifications. However, we can't just do is_dirty(..., path=inputs)
        # because we need to consider subdatasets and untracked files.
        # MIH: is_dirty() is gone, but status() can do all of the above!
        if not explicit and ds.repo.dirty:
            yield get_status_dict(
                'run',
                ds=ds,
                status='impossible',
                message=(
                    'clean dataset required to detect changes from command; '
                    'use `datalad status` to inspect unsaved changes'))
            return

    # everything below expects the string-form of the command
    cmd = normalize_command(cmd)
    # pull substitutions from config
    cmd_fmt_kwargs = _get_substitutions(ds)
    # amend with unexpanded dependency/output specifications, which might
    # themselves contain substitution placeholder
    for n, val in specs.items():
        if val:
            cmd_fmt_kwargs[n] = val

    # apply the substitution to the IO specs
    expanded_specs = {
        k: _format_iospecs(v, **cmd_fmt_kwargs) for k, v in specs.items()
    }
    # try-expect to catch expansion issues in _format_iospecs() which
    # expands placeholders in dependency/output specification before
    # globbing
    try:
        globbed = {
            k: GlobbedPaths(
                v,
                pwd=pwd,
                expand=expand in (
                    # extra_inputs follow same expansion rules as `inputs`.
                    ["both"] + (['outputs'] if k == 'outputs' else ['inputs'])
                ))
            for k, v in expanded_specs.items()
        }
    except KeyError as exc:
        yield get_status_dict(
            'run',
            ds=ds,
            status='impossible',
            message=(
                'input/output specification has an unrecognized '
                'placeholder: %s', exc))
        return

    if not (inject or dry_run):
        yield from _prep_worktree(
            ds_path, pwd, globbed,
            assume_ready=assume_ready,
            remove_outputs=remove_outputs,
            rerun_outputs=rerun_outputs,
            jobs=None)
    else:
        # If an inject=True caller wants to override the exit code, they can do
        # so in extra_info.
        cmd_exitcode = 0
        exc = None

    # prepare command formatting by extending the set of configurable
    # substitutions with the essential components
    cmd_fmt_kwargs.update(
        pwd=pwd,
        dspath=ds_path,
        # Check if the command contains "{tmpdir}" to avoid creating an
        # unnecessary temporary directory in most but not all cases.
        tmpdir=mkdtemp(prefix="datalad-run-") if "{tmpdir}" in cmd else "",
        # the following override any matching non-glob substitution
        # values
        inputs=globbed['inputs'],
        outputs=globbed['outputs'],
    )
    try:
        cmd_expanded = format_command(ds, cmd, **cmd_fmt_kwargs)
    except KeyError as exc:
        yield get_status_dict(
            'run',
            ds=ds,
            status='impossible',
            message=('command has an unrecognized placeholder: %s',
                     exc))
        return

    # amend commit message with `run` info:
    # - pwd if inside the dataset
    # - the command itself
    # - exit code of the command
    run_info = {
        'cmd': cmd,
        # rerun does not handle any prop being None, hence all
        # the `or/else []`
        'chain': rerun_info["chain"] if rerun_info else [],
    }
    # for all following we need to make sure that the raw
    # specifications, incl. any placeholders make it into
    # the run-record to enable "parametric" re-runs
    # ...except when expansion was requested
    for k, v in specs.items():
        run_info[k] = globbed[k].paths \
            if expand in ["both"] + (
                ['outputs'] if k == 'outputs' else ['inputs']) \
            else (v if parametric_record
                  else expanded_specs[k]) or []

    if rel_pwd is not None:
        # only when inside the dataset to not leak information
        run_info['pwd'] = rel_pwd
    if ds.id:
        run_info["dsid"] = ds.id
    if extra_info:
        run_info.update(extra_info)

    if dry_run:
        yield get_status_dict(
            "run [dry-run]", ds=ds, status="ok", message="Dry run",
            run_info=run_info,
            dry_run_info=dict(
                cmd_expanded=cmd_expanded,
                pwd_full=pwd,
                **{k: globbed[k].expand() for k in ('inputs', 'outputs')},
            )
        )
        return

    if not inject:
        cmd_exitcode, exc = _execute_command(cmd_expanded, pwd)
        run_info['exit'] = cmd_exitcode

    # Re-glob to capture any new outputs.
    #
    # TODO: If a warning or error is desired when an --output pattern doesn't
    # have a match, this would be the spot to do it.
    if explicit or expand in ["outputs", "both"]:
        # also for explicit mode we have to re-glob to be able to save all
        # matching outputs
        globbed['outputs'].expand(refresh=True)
        if expand in ["outputs", "both"]:
            run_info["outputs"] = globbed['outputs'].paths

    # create the run record, either as a string, or written to a file
    # depending on the config/request
    record, record_path = _create_record(run_info, sidecar, ds)

    # abbreviate version of the command for illustrative purposes
    cmd_shorty = _format_cmd_shorty(cmd_expanded)

    # compose commit message
    msg = u"""\
[DATALAD RUNCMD] {}

=== Do not change lines below ===
{}
^^^ Do not change lines above ^^^
"""
    msg = msg.format(
        message if message is not None else cmd_shorty,
        '"{}"'.format(record) if record_path else record)

    outputs_to_save = globbed['outputs'].expand_strict() if explicit else None
    if outputs_to_save is not None and record_path:
        outputs_to_save.append(record_path)
    do_save = outputs_to_save is None or outputs_to_save
    msg_path = None
    if not rerun_info and cmd_exitcode:
        if do_save:
            repo = ds.repo
            # must record path to be relative to ds.path to meet
            # result record semantics (think symlink resolution, etc)
            msg_path = ds.pathobj / \
                repo.dot_git.relative_to(repo.pathobj) / "COMMIT_EDITMSG"
            msg_path.write_text(msg)

    expected_exit = rerun_info.get("exit", 0) if rerun_info else None
    if cmd_exitcode and expected_exit != cmd_exitcode:
        status = "error"
    else:
        status = "ok"

    run_result = get_status_dict(
        "run", ds=ds,
        status=status,
        # use the abbrev. command as the message to give immediate clarity what
        # completed/errors in the generic result rendering
        message=cmd_shorty,
        run_info=run_info,
        # use the same key that `get_status_dict()` would/will use
        # to record the exit code in case of an exception
        exit_code=cmd_exitcode,
        exception=exc,
        # Provide msg_path and explicit outputs so that, under
        # on_failure='stop', callers can react to a failure and then call
        # save().
        msg_path=str(msg_path) if msg_path else None,
    )
    if record_path:
        # we the record is in a sidecar file, report its ID
        run_result['record_id'] = record
    for s in ('inputs', 'outputs'):
        # this enables callers to further inspect the outputs without
        # performing globbing again. Together with remove_outputs=True
        # these would be guaranteed to be the outcome of the executed
        # command. in contrast to `outputs_to_save` this does not
        # include aux file, such as the run record sidecar file.
        # calling .expand_strict() again is largely reporting cached
        # information
        # (format: relative paths)
        if yield_expanded in (s, 'both'):
            run_result[f'expanded_{s}'] = globbed[s].expand_strict()
    yield run_result

    if do_save:
        with chpwd(pwd):
            for r in Save.__call__(
                    dataset=ds_path,
                    path=outputs_to_save,
                    recursive=True,
                    message=msg,
                    jobs=jobs,
                    return_type='generator',
                    # we want this command and its parameterization to be in full
                    # control about the rendering of results, hence we must turn
                    # off internal rendering
                    result_renderer='disabled',
                    on_failure='ignore'):
                yield r
