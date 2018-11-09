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

from argparse import REMAINDER
import glob
import os.path as op
from os.path import join as opj
from os.path import normpath
from os.path import relpath
from os.path import isabs

from six.moves import shlex_quote

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
from datalad.support.param import Parameter
from datalad.support.json_py import dump2stream

from datalad.distribution.add import Add
from datalad.distribution.get import Get
from datalad.distribution.install import Install
from datalad.distribution.remove import Remove
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.unlock import Unlock

from datalad.utils import assure_bytes
from datalad.utils import chpwd
# Rename get_dataset_pwds for the benefit of containers_run.
from datalad.utils import get_dataset_pwds as get_command_pwds
from datalad.utils import getpwd
from datalad.utils import partition
from datalad.utils import SequenceFormatter

lgr = logging.getLogger('datalad.interface.run')


def _format_cmd_shorty(cmd):
    """Get short string representation from a cmd argument list"""
    cmd_shorty = (' '.join(cmd) if isinstance(cmd, list) else cmd)
    cmd_shorty = '{}{}'.format(
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
    dataset that run is invoked on. "{inputs}" and "{outputs}" represent the
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
    _params_ = dict(
        cmd=Parameter(
            args=("cmd",),
            nargs=REMAINDER,
            metavar='COMMAND',
            doc="command for execution"),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to record the command results in.
            An attempt is made to identify the dataset based on the current
            working directory. If a dataset is given, the command will be
            executed in the root directory of this dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        inputs=Parameter(
            args=("--input",),
            dest="inputs",
            metavar=("PATH"),
            action='append',
            doc="""A dependency for the run. Before running the command, the
            content of this file will be retrieved. A value of "." means "run
            :command:`datalad get .`". The value can also be a glob. [CMD: This
            option can be given more than once. CMD]"""),
        outputs=Parameter(
            args=("--output",),
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
            metavar=("WHICH"),
            doc="""Expand globs when storing inputs and/or outputs in the
            commit message.""",
            constraints=EnsureNone() | EnsureChoice("inputs", "outputs", "both")),
        explicit=Parameter(
            args=("--explicit",),
            action="store_true",
            doc="""Consider the specification of inputs and outputs to be
            explicit. Don't warn if the repository is dirty, and only save
            modifications to the listed outputs."""),
        message=save_message_opt,
        sidecar=Parameter(
            args=('--sidecar',),
            metavar="yes|no",
            doc="""By default, the configuration variable
            'datalad.run.record-sidecar' determines whether a record with
            information on a command's execution is placed into a separate
            record file instead of the commit message (default: off). This
            option can be used to override the configured behavior on a
            case-by-case basis. Sidecar files are placed into the dataset's
            '.datalad/runinfo' directory (customizable via the
            'datalad.run.record-directory' configuration variable).""",
            constraints=EnsureNone() | EnsureBool()),
        rerun=Parameter(
            args=('--rerun',),
            action='store_true',
            doc="""re-run the command recorded in the last saved change (if any).
            Note: This option is deprecated since version 0.9.2 and
            will be removed in a later release. Use `datalad rerun`
            instead."""),
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
            sidecar=None,
            rerun=False):
        if rerun:
            if cmd:
                lgr.warning("Ignoring provided command in --rerun mode")
            lgr.warning("The --rerun option is deprecated since version 0.9.2. "
                        "Use `datalad rerun` instead.")
            from datalad.interface.rerun import Rerun
            for r in Rerun.__call__(dataset=dataset, message=message):
                yield r
        else:
            if cmd:
                for r in run_command(cmd, dataset=dataset,
                                     inputs=inputs, outputs=outputs,
                                     expand=expand,
                                     explicit=explicit,
                                     message=message,
                                     sidecar=sidecar):
                    yield r
            else:
                lgr.warning("No command given")


class GlobbedPaths(object):
    """Helper for inputs and outputs.

    Parameters
    ----------
    patterns : list of str
        Call `glob.glob` with each of these patterns. "." is considered as
        datalad's special "." path argument; it is not passed to glob and is
        always left unexpanded. Each set of glob results is sorted
        alphabetically.
    pwd : str, optional
        Glob in this directory.
    expand : bool, optional
       Whether the `paths` property returns unexpanded or expanded paths.
    """

    def __init__(self, patterns, pwd=None, expand=False):
        self.pwd = pwd or getpwd()
        self._expand = expand

        if patterns is None:
            self._maybe_dot = []
            self._paths = {"patterns": [], "sub_patterns": {}}
        else:
            patterns, dots = partition(patterns, lambda i: i.strip() == ".")
            self._maybe_dot = ["."] if list(dots) else []
            self._paths = {
                "patterns": [relpath(p, start=pwd) if isabs(p) else p
                             for p in patterns],
                "sub_patterns": {}}

    def __bool__(self):
        return bool(self._maybe_dot or self.expand())

    __nonzero__ = __bool__  # py2

    def _get_sub_patterns(self, pattern):
        """Extract sub-patterns from the leading path of `pattern`.

        The right-most path component is successively peeled off until there
        are no patterns left.
        """
        if pattern in self._paths["sub_patterns"]:
            return self._paths["sub_patterns"][pattern]

        head, tail = op.split(pattern)
        if not tail:
            # Pattern ended with a separator. Take the first directory as the
            # base.
            head, tail = op.split(head)

        sub_patterns = []
        seen_magic = glob.has_magic(tail)
        while head:
            new_head, tail = op.split(head)
            if seen_magic and not glob.has_magic(head):
                break
            elif not seen_magic and glob.has_magic(tail):
                seen_magic = True

            if seen_magic:
                sub_patterns.append(head + op.sep)
            head = new_head
        self._paths["sub_patterns"][pattern] = sub_patterns
        return sub_patterns

    def _expand_globs(self):
        def normalize_hits(hs):
            return [relpath(h) + ("" if op.basename(h) else op.sep)
                    for h in sorted(hs)]

        expanded = []
        with chpwd(self.pwd):
            for pattern in self._paths["patterns"]:
                hits = glob.glob(pattern)
                if hits:
                    expanded.extend(normalize_hits(hits))
                else:
                    lgr.debug("No matching files found for '%s'", pattern)
                    # We didn't find a hit for the complete pattern. If we find
                    # a sub-pattern hit, that may mean we have an uninstalled
                    # subdataset.
                    for sub_pattern in self._get_sub_patterns(pattern):
                        sub_hits = glob.glob(sub_pattern)
                        if sub_hits:
                            expanded.extend(normalize_hits(sub_hits))
                            break
                    # ... but we still want to retain the original pattern
                    # because we don't know for sure at this point, and it
                    # won't bother the "install, reglob" routine.
                    expanded.extend([pattern])
        return expanded

    def expand(self, full=False, dot=True, refresh=False):
        """Return paths with the globs expanded.

        Parameters
        ----------
        full : bool, optional
            Return full paths rather than paths relative to `pwd`.
        dot : bool, optional
            Include the "." pattern if it was specified.
        refresh : bool, optional
            Run glob regardless of whether there are cached values. This is
            useful if there may have been changes on the file system.
        """
        maybe_dot = self._maybe_dot if dot else []
        if not self._paths["patterns"]:
            return maybe_dot + []

        if refresh or "expanded" not in self._paths:
            paths = self._expand_globs()
            self._paths["expanded"] = paths
        else:
            paths = self._paths["expanded"]

        if full:
            if refresh or "expanded_full" not in self._paths:
                paths = [opj(self.pwd, p) for p in paths]
                self._paths["expanded_full"] = paths
            else:
                paths = self._paths["expanded_full"]

        return maybe_dot + paths

    @property
    def paths(self):
        """Return paths relative to `pwd`.

        Globs are expanded if `expand` was set to true during instantiation.
        """
        if self._expand:
            return self.expand()
        return self._maybe_dot + self._paths["patterns"]


def _install_and_reglob(dset, gpaths):
    """Install globbed subdatasets and repeat.

    Parameters
    ----------
    dset : Dataset
    gpaths : GlobbedPaths object

    Returns
    -------
    Generator with the results of the `install` calls.
    """
    def glob_dirs():
        return list(map(op.dirname, gpaths.expand(refresh=True)))

    dirs, dirs_new = [], glob_dirs()
    while dirs != dirs_new:
        for res in dset.install(dirs_new,
                                result_xfm=None, return_type='generator',
                                on_failure="ignore"):
            if res.get("state") == "absent":
                lgr.debug("Skipping install of non-existent path: %s",
                          res["path"])
            else:
                yield res
        dirs, dirs_new = dirs_new, glob_dirs()


def prepare_inputs(dset, inputs):
    """Prepare `inputs` for running a command.

    This consists of installing required subdatasets and getting the input
    files.

    Parameters
    ----------
    dset : Dataset
    inputs : GlobbedPaths object

    Returns
    -------
    Generator with the result records.
    """
    if inputs:
        lgr.info('Making sure inputs are available (this may take some time)')
        for res in _install_and_reglob(dset, inputs):
            yield res
        for res in dset.get(inputs.expand(full=True), on_failure="ignore"):
            if res.get("state") == "absent":
                lgr.warning("Input does not exist: %s", res["path"])
            else:
                yield res


def _unlock_or_remove(dset, paths):
    """Unlock `paths` if content is present; remove otherwise.

    Parameters
    ----------
    dset : Dataset
    paths : list of string
        Absolute paths of dataset files.

    Returns
    -------
    Generator with result records.
    """
    existing = []
    for path in paths:
        if op.exists(path) or op.lexists(path):
            existing.append(path)
        else:
            # Avoid unlock's warning because output files may not exist in
            # common cases (e.g., when rerunning with --onto).
            lgr.debug("Filtered out non-existing path: %s", path)

    if existing:
        for res in dset.unlock(existing, on_failure="ignore"):
            if res["status"] == "impossible":
                if "no content" in res["message"]:
                    for rem_res in dset.remove(res["path"],
                                               check=False, save=False):
                        yield rem_res
                    continue
            yield res


def normalize_command(command):
    """Convert `command` to the string representation.
    """
    if isinstance(command, list):
        if len(command) == 1:
            # This is either a quoted compound shell command or a simple
            # one-item command. Pass it as is.
            command = command[0]
        else:
            command = " ".join(shlex_quote(c) for c in command)
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
        kwds[name] = list(map(shlex_quote, io_val.expand(dot=False)))
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
                rerun_info=None, rerun_outputs=None,
                inject=False):
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
    rerun_outputs : list, optional
        Outputs, in addition to those in `outputs`, determined automatically
        from a previous run. This is used internally by `rerun`.
    inject : bool, optional
        Record results as if a command was run, skipping input and output
        preparation and command execution. In this mode, the caller is
        responsible for ensuring that the state of the working tree is
        appropriate for recording the command's results.

    Yields
    ------
    Result records for the run.
    """
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

    # not needed ATM
    #refds_path = ds.path

    lgr.debug('tracking command output underneath %s', ds)

    if not (rerun_info or inject):  # Rerun already takes care of this.
        # For explicit=True, we probably want to check whether any inputs have
        # modifications. However, we can't just do is_dirty(..., path=inputs)
        # because we need to consider subdatasets and untracked files.
        if not explicit and ds.repo.dirty:
            yield get_status_dict(
                'run',
                ds=ds,
                status='impossible',
                message=('unsaved modifications present, '
                         'cannot detect changes by command'))
            return

    cmd = normalize_command(cmd)

    inputs = GlobbedPaths(inputs, pwd=pwd,
                          expand=expand in ["inputs", "both"])
    outputs = GlobbedPaths(outputs, pwd=pwd,
                           expand=expand in ["outputs", "both"])

    if not inject:
        for res in prepare_inputs(ds, inputs):
            yield res

        if outputs:
            for res in _install_and_reglob(ds, outputs):
                yield res
            for res in _unlock_or_remove(ds, outputs.expand(full=True)):
                yield res

        if rerun_outputs is not None:
            # These are files we need to unlock/remove for a rerun that aren't
            # included in the explicit outputs. Unlike inputs/outputs, these are
            # full paths, so we can pass them directly to unlock.
            for res in _unlock_or_remove(ds, rerun_outputs):
                yield res

        try:
            cmd_expanded = format_command(ds, cmd,
                                          pwd=pwd,
                                          dspath=ds.path,
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

        cmd_exitcode, exc = _execute_command(
            cmd_expanded, pwd,
            expected_exit=rerun_info.get("exit", 0) if rerun_info else None)
    else:
        # If an inject=True caller wants to override the exit code, they can do
        # so in extra_info.
        cmd_exitcode = 0
        exc = None
    # amend commit message with `run` info:
    # - pwd if inside the dataset
    # - the command itself
    # - exit code of the command
    run_info = {
        'cmd': cmd,
        'exit': cmd_exitcode,
        'chain': rerun_info["chain"] if rerun_info else [],
        'inputs': inputs.paths,
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
        record_path = op.join(ds.path, record_dir, record_id)
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
        message if message is not None else _format_cmd_shorty(cmd),
        '"{}"'.format(record_id) if use_sidecar else record)
    msg = assure_bytes(msg)

    outputs_to_save = outputs.expand(full=True) if explicit else '.'
    if not rerun_info and cmd_exitcode:
        if outputs_to_save:
            msg_path = relpath(opj(ds.repo.path, ds.repo.get_git_dir(ds.repo),
                                   "COMMIT_EDITMSG"))
            with open(msg_path, "wb") as ofh:
                ofh.write(msg)
            lgr.info("The command had a non-zero exit code. "
                     "If this is expected, you can save the changes with "
                     "'datalad save -r -F %s .'",
                     msg_path)
        raise exc
    elif outputs_to_save:
        for r in ds.add(outputs_to_save, recursive=True, message=msg):
            yield r
