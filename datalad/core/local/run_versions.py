# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Version capture for datalad run records"""

__docformat__ = 'restructuredtext'

import json
import logging
import os
import re
import shlex
import shutil
from pathlib import Path

from datalad.config import anything2bool
from datalad.support.external_versions import external_versions

lgr = logging.getLogger('datalad.core.local.run_versions')

# Injected versions file path (relative to dataset root, inside .git)
INJECTED_VERSIONS_FILE = '.git/datalad/run_versions.json'


def capture_versions(cmd, versions_spec, ds):
    """Capture versions for a run record.

    Parameters
    ----------
    cmd : str
        The command being run
    versions_spec : str or None
        The --versions argument value, or None for default.
        Use 'auto' to detect, 'none' to disable, or comma-separated
        specs like 'cmd:python,py:numpy'.
    ds : Dataset
        The dataset being operated on

    Returns
    -------
    dict
        Dictionary mapping version names to version strings.
        Keys use prefixes: 'cmd:' for CLI tools, 'py:' for Python packages.
    """
    result = {}

    # Get config values
    default = ds.config.get('datalad.run.versions.default', default='auto')
    include = _get_config_list(ds, 'datalad.run.versions.include', default=['py:datalad'])
    exclude = set(_get_config_list(ds, 'datalad.run.versions.exclude', default=[]))
    strict = anything2bool(ds.config.get('datalad.run.versions.strict', default=False))

    # Determine effective versions_spec
    if versions_spec is None:
        versions_spec = default

    # Handle 'none' - disable version capture
    if versions_spec == 'none':
        return result

    # Parse versions_spec into specs and custom commands
    specs, custom_commands = _parse_versions_spec(versions_spec, ds)

    # Handle 'auto' - detect tools from command
    if 'auto' in specs:
        specs.discard('auto')
        detected = _detect_tools_from_command(cmd)
        specs.update(detected)

    # Add configured includes
    specs.update(include)

    # Remove excludes
    specs -= exclude

    # Capture each version
    for name in sorted(specs):
        try:
            ver = _get_version(name, custom_commands)
            if ver is not None:
                result[name] = str(ver)
            elif strict:
                raise RuntimeError(f"Failed to capture version for {name}")
            else:
                lgr.debug("Could not capture version for %s", name)
        except Exception as e:
            if strict:
                raise RuntimeError(f"Failed to capture version for {name}: {e}") from e
            lgr.warning("Version capture failed for %s: %s", name, e)

    return result


def _get_config_list(ds, key, default=None):
    """Get a config value that may be a list (multi-value)."""
    val = ds.config.get(key, default=None)
    if val is None:
        return default if default is not None else []
    # Config returns a single value or tuple for multi-value
    if isinstance(val, (list, tuple)):
        return list(val)
    # Single value - could be comma-separated
    return [v.strip() for v in val.split(',') if v.strip()]


def _parse_versions_spec(versions_spec, ds):
    """Parse --versions argument.

    Parameters
    ----------
    versions_spec : str
        The versions argument value. Reserved keywords: 'auto', 'none'.
        All other specs must have prefix: 'cmd:' for CLI tools,
        'py:' for Python packages. Use '@path' to load from JSON file.
    ds : Dataset
        The dataset (for resolving @file paths)

    Returns
    -------
    tuple
        (set of version specs to capture, dict of custom commands)
    """
    specs = set()
    custom_commands = {}

    if not versions_spec:
        return specs, custom_commands

    # Handle @file syntax
    if versions_spec.startswith('@'):
        file_path = versions_spec[1:]
        if not os.path.isabs(file_path):
            file_path = os.path.join(ds.path, file_path)
        try:
            with open(file_path) as f:
                file_specs = json.load(f)
            # File format: {"cmd:tool": "custom command", "py:package": null}
            for name, cmd in file_specs.items():
                _validate_version_spec(name)
                specs.add(name)
                if cmd:
                    custom_commands[name] = cmd
        except Exception as e:
            lgr.warning("Failed to load version specs from %s: %s", file_path, e)
        return specs, custom_commands

    # Parse comma-separated list
    for item in versions_spec.split(','):
        item = item.strip()
        if not item:
            continue

        if item in ('auto', 'none'):
            # Reserved keywords
            specs.add(item)
        elif item.startswith('cmd:') and item.count(':') >= 2:
            # Custom command: cmd:tool:command
            parts = item.split(':', 2)
            name = f"cmd:{parts[1]}"
            custom_commands[name] = parts[2]
            specs.add(name)
        elif item.startswith('cmd:') or item.startswith('py:'):
            # Standard prefixed spec
            specs.add(item)
        else:
            lgr.warning(
                "Invalid version spec '%s': must be 'auto', 'none', "
                "or have prefix 'cmd:' or 'py:'", item
            )

    return specs, custom_commands


def _validate_version_spec(name):
    """Validate that a version spec has proper prefix."""
    if name in ('auto', 'none'):
        return
    if not (name.startswith('cmd:') or name.startswith('py:')):
        lgr.warning(
            "Version spec '%s' should have prefix 'cmd:' or 'py:'", name
        )


def _detect_tools_from_command(cmd):
    """Auto-detect executable tools from a command string.

    Parameters
    ----------
    cmd : str
        The command string

    Returns
    -------
    set
        Set of cmd:tool specs detected from the command
    """
    detected = set()

    # Shell builtins and trivial commands to ignore
    ignore = {
        'cd', 'echo', 'printf', 'export', 'set', 'unset', 'source', '.',
        'true', 'false', 'test', '[', '[[', 'read', 'eval', 'exec',
        'exit', 'return', 'break', 'continue', 'shift', 'wait',
        'ls', 'cat', 'head', 'tail', 'wc', 'sort', 'uniq', 'cut',
        'tr', 'tee', 'touch', 'mkdir', 'rm', 'cp', 'mv', 'ln',
        'chmod', 'chown', 'pwd', 'basename', 'dirname', 'realpath',
    }

    # Try to parse the command
    try:
        # Split by common shell operators to get pipeline segments
        # This is a simple heuristic, not a full shell parser
        segments = re.split(r'[|&;]|\|\||&&', cmd)

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            # Handle subshells and command substitution simply
            segment = re.sub(r'\$\([^)]*\)', '', segment)
            segment = re.sub(r'`[^`]*`', '', segment)
            segment = segment.lstrip('(').rstrip(')')

            # Try to get the first word (the executable)
            try:
                tokens = shlex.split(segment)
            except ValueError:
                # shlex failed, try simple split
                tokens = segment.split()

            if not tokens:
                continue

            # Skip variable assignments at the start
            while tokens and '=' in tokens[0] and not tokens[0].startswith('='):
                tokens = tokens[1:]

            if not tokens:
                continue

            exe = tokens[0]

            # Skip if it's a path to a script we can't identify
            if exe.startswith('./') or exe.startswith('/'):
                exe = os.path.basename(exe)

            # Skip shell builtins and trivial commands
            if exe in ignore:
                continue

            # Skip if it looks like an option
            if exe.startswith('-'):
                continue

            # Add as cmd:tool
            detected.add(f'cmd:{exe}')

    except Exception as e:
        lgr.debug("Failed to parse command for tool detection: %s", e)

    return detected


def _get_version(name, custom_commands=None):
    """Get version for a single tool/package.

    Parameters
    ----------
    name : str
        Name with prefix: 'cmd:tool' for CLI tools, 'py:package' for Python.
    custom_commands : dict, optional
        Custom version commands keyed by name

    Returns
    -------
    str or None
        Version string, or None if not found
    """
    custom_commands = custom_commands or {}

    # Check for custom command
    if name in custom_commands:
        return _run_custom_version_command(custom_commands[name])

    # Determine the key for external_versions
    # external_versions uses: 'cmd:tool' for CLI, unprefixed for Python
    if name.startswith('py:'):
        ev_key = name[3:]  # Strip 'py:' prefix for external_versions
    else:
        ev_key = name  # 'cmd:*' is used as-is

    # Try external_versions
    ver = external_versions[ev_key]
    if ver is not None and str(ver) != 'UNKNOWN':
        return str(ver)

    # For cmd:* that aren't registered, try probing
    if name.startswith('cmd:') and ver is None:
        tool = name[4:]  # Remove 'cmd:' prefix
        return _probe_unknown_command(tool)

    return None


def _run_custom_version_command(cmd):
    """Run a custom version command and return output.

    Parameters
    ----------
    cmd : str
        Shell command to run

    Returns
    -------
    str or None
        First line of output, or None on failure
    """
    from datalad.cmd import (
        StdOutErrCapture,
        WitlessRunner,
    )

    runner = WitlessRunner()
    try:
        out = runner.run(['sh', '-c', cmd], protocol=StdOutErrCapture)
        output = out['stdout'].strip()
        if output:
            # Return first non-empty line
            for line in output.splitlines():
                line = line.strip()
                if line:
                    return line
    except Exception as e:
        lgr.debug("Custom version command failed: %s: %s", cmd, e)

    return None


def _probe_unknown_command(tool):
    """Try common version flags for an unknown command-line tool.

    Parameters
    ----------
    tool : str
        Name of the tool (without cmd: prefix)

    Returns
    -------
    str or None
        Version string, or None if probing failed
    """
    from datalad.cmd import (
        StdOutErrCapture,
        WitlessRunner,
    )

    # Check if tool exists
    if not shutil.which(tool):
        lgr.debug("Tool not found in PATH: %s", tool)
        return None

    runner = WitlessRunner()

    # Common version flags to try
    version_flags = ['--version', '-version', '-V', 'version', '-v']

    for flag in version_flags:
        try:
            cmd = [tool, flag] if flag != 'version' else [tool, flag]
            out = runner.run(cmd, protocol=StdOutErrCapture)

            # Check both stdout and stderr (some tools output to stderr)
            output = out['stdout'] or out['stderr']
            if output:
                output = output.strip()
                # Try to extract version from first line
                first_line = output.splitlines()[0].strip()
                if first_line:
                    # Try to extract version number pattern
                    version = _extract_version_from_string(first_line)
                    if version:
                        return version
                    # Fall back to full first line if it's reasonable
                    if len(first_line) < 100:
                        return first_line

        except Exception as e:
            lgr.log(5, "Probing %s %s failed: %s", tool, flag, e)
            continue

    return None


def _extract_version_from_string(s):
    """Try to extract a version number from a string.

    Parameters
    ----------
    s : str
        String that may contain a version number

    Returns
    -------
    str or None
        Extracted version string, or None
    """
    # Common patterns:
    # "tool version 1.2.3"
    # "tool v1.2.3"
    # "tool 1.2.3"
    # "1.2.3"
    patterns = [
        r'[vV]?(\d+\.\d+(?:\.\d+)?(?:[-+.]\w+)*)',  # semver-like
        r'(\d+\.\d+)',  # major.minor
    ]

    for pattern in patterns:
        match = re.search(pattern, s)
        if match:
            return match.group(1)

    return None


def check_stale_injected_file(ds):
    """Check for pre-existing injected versions file.

    Parameters
    ----------
    ds : Dataset
        The dataset

    Returns
    -------
    bool
        True if stale file was found (and should be ignored)
    """
    path = Path(ds.path) / INJECTED_VERSIONS_FILE
    if path.exists():
        lgr.warning(
            "Stale %s found (exists before run), ignoring. "
            "Remove manually if not needed.",
            path
        )
        return True
    return False


def read_injected_versions(ds):
    """Read and remove injected versions file if present.

    Parameters
    ----------
    ds : Dataset
        The dataset

    Returns
    -------
    dict or None
        Versions dict from the file, or None if not present
    """
    path = Path(ds.path) / INJECTED_VERSIONS_FILE
    if not path.exists():
        return None

    try:
        with open(path) as f:
            versions = json.load(f)
        path.unlink()  # Delete after reading
        lgr.debug("Read injected versions from %s: %s", path, versions)
        return versions
    except Exception as e:
        lgr.warning("Failed to read injected versions from %s: %s", path, e)
        return None
