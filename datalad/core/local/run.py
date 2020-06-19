# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run arbitrary commands and track how they modify a dataset"""

__docformat__ = 'restructuredtext'


import logging
import json
import warnings

from argparse import REMAINDER
import os.path as op
from os.path import join as opj
from os.path import normpath
from os.path import relpath
from tempfile import mkdtemp

from datalad.core.local.save import Save
from datalad.distribution.get import Get
from datalad.distribution.install import Install
from datalad.distribution.remove import Remove
from datalad.interface.unlock import Unlock

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import save_message_opt

from datalad.config import anything2bool

from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureBool
from datalad.support.exceptions import CommandError
from datalad.support.globbedpaths import GlobbedPaths
from datalad.support.param import Parameter
from datalad.support.json_py import dump2stream

from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod

from datalad.utils import assure_bytes
from datalad.utils import assure_unicode
from datalad.utils import chpwd
from datalad.utils import get_dataset_root
from datalad.utils import getpwd
from datalad.utils import SequenceFormatter
from datalad.utils import quote_cmdlinearg

lgr = logging.getLogger('datalad.core.local.run')


def _format_cmd_shorty(cmd):
    """Get short string representation from a cmd argument list"""
    cmd_shorty = (' '.join(cmd) if isinstance(cmd, list) else cmd)
    cmd_shorty = u'{}{}'.format(
        cmd_shorty[:40],
        '...' if len(cmd_shorty) > 40 else '')
    return cmd_shorty


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
    code will be raised, and no modifications will be saved.

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

        % git config --file=.datalad/config datalad.run.substitutions.name joe
        % datalad add -m "Configure name placeholder" .datalad/config

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
             'outfile.txt' 'code/script.sh'""")
    ]

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
            content of this file will be retrieved. A value of "." means "run
            :command:`datalad get .`". The value can also be a glob. [CMD: This
            option can be given more than once. CMD]"""),
        outputs=Parameter(
            args=("-o", "--output"),
            dest="outputs",
            metavar=("PATH"),
            action='append',
            doc="""Prepare this file to be an output file of the command. A
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
    )

    @staticmethod
    @datasetmethod(name='run')
    @eval_results
    def __call__(
            cmd=None,
            dataset=None,
            inputs=None,
            outputs=None,
            expand=None,
            explicit=False,
            message=None,
            sidecar=None):
        for r in run_command(cmd, dataset=dataset,
                             inputs=inputs, outputs=outputs,
                             expand=expand,
                             explicit=explicit,
                             message=message,
                             sidecar=sidecar):
            yield r


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
            rel_pwd = relpath(pwd, dataset)
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
                           result_xfm=None, return_type='generator',
                           on_failure="ignore"):
            if _is_nonexistent_path(res):
                lgr.debug("Skipping install of non-existent path: %s",
                          res["path"])
            else:
                yield res
        dirs, dirs_new = dirs_new, glob_dirs()


def prepare_inputs(dset_path, inputs, extra_inputs=None):
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
        for res in get(dataset=dset_path, path=gp.expand(), on_failure="ignore"):
            if _is_nonexistent_path(res):
                # MIH why just a warning if given inputs are not valid?
                lgr.warning("Input does not exist: %s", res["path"])
            else:
                yield res


def _unlock_or_remove(dset_path, paths):
    """Unlock `paths` if content is present; remove otherwise.

    Parameters
    ----------
    dset_path : str
    paths : list of string
        Absolute paths of dataset files.

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

    if existing:
        remove = Remove()
        for res in Unlock()(dataset=dset_path, path=existing,
                            on_failure="ignore"):
            if res["status"] == "impossible":
                if "cannot unlock" in res["message"]:
                    for rem_res in remove(dataset=dset_path,
                                          path=res["path"],
                                          check=False, save=False):
                        yield rem_res
                    continue
            yield res


def normalize_command(command):
    """Convert `command` to the string representation.
    """
    if isinstance(command, list):
        command = list(map(assure_unicode, command))
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
            command = " ".join(quote_cmdlinearg(c) for c in command)
    else:
        command = assure_unicode(command)
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


def _execute_command(command, pwd, expected_exit=None):
    from datalad.cmd import Runner

    exc = None
    cmd_exitcode = None
    runner = Runner(cwd=pwd)
    try:
        lgr.info("== Command start (output follows) =====")
        runner.run(
            command,
            # immediate output
            log_online=True,
            # not yet sure what we should do with the command output
            # IMHO `run` itself should be very silent and let the command talk
            log_stdout=False,
            log_stderr=False,
            expect_stderr=True,
            expect_fail=True,
            # TODO stdin
        )
    except CommandError as e:
        # strip our own info from the exception. The original command output
        # went to stdout/err -- we just have to exitcode in the same way
        exc = e
        cmd_exitcode = e.code

        if expected_exit is not None and expected_exit != cmd_exitcode:
            # we failed in a different way during a rerun.  This can easily
            # happen if we try to alter a locked file
            #
            # TODO add the ability to `git reset --hard` the dataset tree on failure
            # we know that we started clean, so we could easily go back, needs gh-1424
            # to be able to do it recursively
            raise exc

    lgr.info("== Command exit (modification check follows) =====")
    return cmd_exitcode or 0, exc


def run_command(cmd, dataset=None, inputs=None, outputs=None, expand=None,
                explicit=False, message=None, sidecar=None,
                extra_info=None,
                rerun_info=None,
                extra_inputs=None,
                rerun_outputs=None,
                inject=False,
                saver=None):
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
    saver : None
        This is obsolete and ignored. It will be removed in a later release.

    Yields
    ------
    Result records for the run.
    """
    if not cmd:
        lgr.warning("No command given")
        return
    if saver:
        warnings.warn("`saver` argument is ignored "
                      "and will be removed in a future release",
                      DeprecationWarning)

    rel_pwd = rerun_info.get('pwd') if rerun_info else None
    if rel_pwd and dataset:
        # recording is relative to the dataset
        pwd = normpath(opj(dataset.path, rel_pwd))
        rel_pwd = relpath(pwd, dataset.path)
    else:
        pwd, rel_pwd = get_command_pwds(dataset)

    ds = require_dataset(
        dataset, check_installed=True,
        purpose='tracking outcomes of a command')
    ds_path = ds.path

    lgr.debug('tracking command output underneath %s', ds)

    if not (rerun_info or inject):  # Rerun already takes care of this.
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

    cmd = normalize_command(cmd)

    inputs = GlobbedPaths(inputs, pwd=pwd,
                          expand=expand in ["inputs", "both"])
    extra_inputs = GlobbedPaths(extra_inputs, pwd=pwd,
                                # Follow same expansion rules as `inputs`.
                                expand=expand in ["inputs", "both"])
    outputs = GlobbedPaths(outputs, pwd=pwd,
                           expand=expand in ["outputs", "both"])

    # ATTN: For correct path handling, all dataset commands call should be
    # unbound. They should (1) receive a string dataset argument, (2) receive
    # relative paths, and (3) happen within a chpwd(pwd) context.
    if not inject:
        with chpwd(pwd):
            for res in prepare_inputs(ds_path, inputs, extra_inputs):
                yield res

            if outputs:
                for res in _install_and_reglob(ds_path, outputs):
                    yield res
                for res in _unlock_or_remove(ds_path, outputs.expand()):
                    yield res

            if rerun_outputs is not None:
                for res in _unlock_or_remove(ds_path, rerun_outputs):
                    yield res
    else:
        # If an inject=True caller wants to override the exit code, they can do
        # so in extra_info.
        cmd_exitcode = 0
        exc = None

    try:
        cmd_expanded = format_command(
            ds, cmd,
            pwd=pwd,
            dspath=ds_path,
            # Check if the command contains "{tmpdir}" to avoid creating an
            # unnecessary temporary directory in most but not all cases.
            tmpdir=mkdtemp(prefix="datalad-run-") if "{tmpdir}" in cmd else "",
            inputs=inputs,
            outputs=outputs)
    except KeyError as exc:
        yield get_status_dict(
            'run',
            ds=ds,
            status='impossible',
            message=('command has an unrecognized placeholder: %s',
                     exc))
        return

    if not inject:
        cmd_exitcode, exc = _execute_command(
            cmd_expanded, pwd,
            expected_exit=rerun_info.get("exit", 0) if rerun_info else None)


    # amend commit message with `run` info:
    # - pwd if inside the dataset
    # - the command itself
    # - exit code of the command
    run_info = {
        'cmd': cmd,
        'exit': cmd_exitcode,
        'chain': rerun_info["chain"] if rerun_info else [],
        'inputs': inputs.paths,
        'extra_inputs': extra_inputs.paths,
        'outputs': outputs.paths,
    }
    if rel_pwd is not None:
        # only when inside the dataset to not leak information
        run_info['pwd'] = rel_pwd
    if ds.id:
        run_info["dsid"] = ds.id
    if extra_info:
        run_info.update(extra_info)

    record = json.dumps(run_info, indent=1, sort_keys=True, ensure_ascii=False)

    if sidecar is None:
        use_sidecar = ds.config.get('datalad.run.record-sidecar', default=False)
        # If ConfigManager gets the ability to say "return single value",
        # update this code to use that.
        if isinstance(use_sidecar, tuple):
            # Use same precedence as 'git config'.
            use_sidecar = use_sidecar[-1]
        use_sidecar = anything2bool(use_sidecar)
    else:
        use_sidecar = sidecar


    if use_sidecar:
        # record ID is hash of record itself
        from hashlib import md5
        record_id = md5(record.encode('utf-8')).hexdigest()
        record_dir = ds.config.get('datalad.run.record-directory', default=op.join('.datalad', 'runinfo'))
        record_path = op.join(ds_path, record_dir, record_id)
        if not op.lexists(record_path):
            # go for compression, even for minimal records not much difference, despite offset cost
            # wrap in list -- there is just one record
            dump2stream([run_info], record_path, compressed=True)

    # compose commit message
    msg = u"""\
[DATALAD RUNCMD] {}

=== Do not change lines below ===
{}
^^^ Do not change lines above ^^^
"""
    msg = msg.format(
        message if message is not None else _format_cmd_shorty(cmd_expanded),
        '"{}"'.format(record_id) if use_sidecar else record)

    outputs_to_save = outputs.expand() if explicit else None
    do_save = outputs_to_save is None or outputs_to_save
    if not rerun_info and cmd_exitcode:
        if do_save:
            repo = ds.repo
            msg_path = relpath(opj(str(repo.dot_git), "COMMIT_EDITMSG"))
            with open(msg_path, "wb") as ofh:
                ofh.write(assure_bytes(msg))
            lgr.info("The command had a non-zero exit code. "
                     "If this is expected, you can save the changes with "
                     "'datalad save -d . -r -F %s'",
                     msg_path)
        raise exc
    elif do_save:
        with chpwd(pwd):
            for r in Save.__call__(
                    dataset=ds_path,
                    path=outputs_to_save,
                    recursive=True,
                    message=msg,
                    return_type='generator'):
                yield r
