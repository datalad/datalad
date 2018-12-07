# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Thin wrapper around `run` from DataLad core"""

__docformat__ = 'restructuredtext'


import logging

# take everything from run, all we want to be is a thin variant
from datalad.interface.run import (
    Run,
    build_doc,
    eval_results,
)
from .dataset import (
    RevolutionDataset as Dataset,
    datasetmethod,
)
from .revsave import RevSave

lgr = logging.getLogger('datalad.revolution.run')


def _save_outputs(ds, to_save, msg):
    """Helper to save results after command execution is completed"""
    return RevSave.__call__(
        to_save,
        message=msg,
        # need to convert any incoming dataset into a revolutionary one
        dataset=Dataset(ds.path),
        recursive=True,
        return_type='generator')


@build_doc
class RevRun(Run):
    __doc__ = Run.__doc__

    @staticmethod
    @datasetmethod(name='rev_run')
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
        if cmd:
            for r in run_command(cmd, dataset=dataset,
                                 inputs=inputs, outputs=outputs,
                                 expand=expand,
                                 explicit=explicit,
                                 message=message,
                                 sidecar=sidecar,
                                 saver=_save_outputs):
                yield r
        else:
            lgr.warning("No command given")


# required inputs for fork below only!
from datalad.interface.run import (
    get_command_pwds,
    require_dataset,
    normalize_command,
    GlobbedPaths,
    prepare_inputs,
    format_command,
    _execute_command,
    json,
    anything2bool,
    _format_cmd_shorty,
    relpath,
    opj,
    op,
    dump2stream,
    _install_and_reglob,
    _unlock_or_remove,
    get_status_dict,
)

# ATTM this function is an interim fork of -core's
# interface.run.run_command as of 3f2c450e09e59f0861b59ecfecc44d4794c86986
# for the purpose of making things run on windows
# edit with care and a later merge in mind
def run_command(cmd, dataset=None, inputs=None, outputs=None, expand=None,
                explicit=False, message=None, sidecar=None,
                extra_info=None,
                rerun_info=None, rerun_outputs=None,
                inject=False,
                saver=_save_outputs):
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
    saver : callable, optional
        Must take a dataset instance, a list of paths to save, and a
        message string as arguments and must record any changes done
        to any content matching an entry in the path list. Must yield
        result dictionaries as a generator.

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

    outputs_to_save = outputs.expand(full=True) if explicit else '.'
    if not rerun_info and cmd_exitcode:
        if outputs_to_save:
            msg_path = relpath(opj(ds.repo.path, ds.repo.get_git_dir(ds.repo),
                                   "COMMIT_EDITMSG"))
            with open(msg_path, "w") as ofh:
                ofh.write(msg)
            lgr.info("The command had a non-zero exit code. "
                     "If this is expected, you can save the changes with "
                     "'datalad save -r -F %s .'",
                     msg_path)
        raise exc
    elif outputs_to_save:
        for r in saver(ds, outputs_to_save, msg):
            yield r
