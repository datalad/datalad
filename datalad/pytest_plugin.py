# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""DataLad pytest plugin for extensions.

This plugin provides shared pytest configuration for DataLad and its extensions.
It registers custom markers, filterwarnings, and other pytest configuration
that extensions can inherit automatically.

For DataLad extensions, simply install DataLad and the plugin will be
automatically activated via the pytest11 entry point.

The fixtures for testing DataLad itself are in datalad.conftest, which is
loaded as a regular conftest.py file when testing DataLad, but this plugin
provides the configuration that extensions can inherit.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest

# Deprecated datalad APIs still used by specific extensions.
# Each entry maps a warning message pattern to the set of extension
# top-level packages allowed to trigger it without error.
# Once an extension is fixed, remove it from the set; once the set is
# empty, remove the whole entry.
_EXTENSION_DEPRECATION_ALLOWLIST: dict[str, set[str]] = {
    # datalad-neuroimaging, datalad-deprecated use datalad.interface.utils.eval_results
    r"datalad\.interface\.utils\.eval_results is obsolete": {
        "datalad_neuroimaging",
        "datalad_deprecated",
    },
    # datalad-neuroimaging uses datalad.interface.run_procedure
    r"RunProcedure has been moved": {
        "datalad_neuroimaging",
    },
    # datalad-deprecated uses datalad.cmdline
    r"All of datalad\.cmdline is deprecated": {
        "datalad_deprecated",
    },
    # datalad-crawler uses assure_list, assure_bool, etc. from datalad.utils
    r"assure_\w+ is deprecated": {
        "datalad_crawler",
    },
}


def _get_extension_package(module_name: str) -> str | None:
    """Return the datalad extension top-level package, or None for datalad itself."""
    top = module_name.split(".")[0]
    return top if top.startswith("datalad_") else None


def _get_extension_package_from_path(path: Path) -> str | None:
    """Return the datalad extension package detected from a file path."""
    for part in path.parts:
        if part.startswith("datalad_"):
            return part
    return None


def _add_allowlist_filters(extension_package: str) -> None:
    """Add ignore filters for deprecations allowlisted for the given extension.

    Filters are prepended (highest priority) so they override the
    ``error::DeprecationWarning:^datalad`` base filter.
    """
    for pattern, allowed in _EXTENSION_DEPRECATION_ALLOWLIST.items():
        if extension_package in allowed:
            warnings.filterwarnings(
                "ignore", message=pattern, category=DeprecationWarning
            )


def pytest_configure(config):
    """Register datalad custom markers and pytest configuration.

    This allows datalad extensions to inherit markers and configuration
    without duplicating them in their own tox.ini/pytest.ini files.
    """
    # Register all custom markers used by datalad and extensions
    markers = [
        "fail_slow: marks tests that are known to fail slowly",
        "githubci_osx: marks tests for GitHub CI on macOS",
        "githubci_win: marks tests for GitHub CI on Windows",
        "integration: marks integration tests",
        "known_failure: marks tests with known failures",
        "known_failure_githubci_osx: marks tests with known failures on GitHub CI macOS",
        "known_failure_githubci_win: marks tests with known failures on GitHub CI Windows",
        "known_failure_osx: marks tests with known failures on macOS",
        "known_failure_windows: marks tests with known failures on Windows",
        "network: marks tests requiring network access",
        "osx: marks macOS-specific tests",
        "probe_known_failure: marks tests to probe if known failure is resolved",
        "serve_path_via_http: marks tests that serve paths via HTTP",
        "skip_if_adjusted_branch: skip test on adjusted branches",
        "skip_if_no_network: skip test when network is unavailable",
        "skip_if_on_windows: skip test on Windows",
        "skip_if_root: skip test when running as root",
        "skip_known_failure: skip tests with known failures",
        "skip_nomultiplex_ssh: skip when multiplex SSH unavailable",
        "skip_ssh: skip SSH-related tests",
        "skip_wo_symlink_capability: skip without symlink capability",
        "slow: marks slow tests (>10 seconds)",
        "turtle: marks very slow tests (>2 minutes)",
        "usecase: marks tests from user-reported use cases",
        "windows: marks Windows-specific tests",
        "with_config: marks tests with configuration",
        "with_fake_cookies_db: marks tests with fake cookies database",
        "with_memory_keyring: marks tests with memory keyring",
        "with_sameas_remotes: marks tests with sameas remotes",
        "with_testrepos: marks tests with test repositories",
        "without_http_proxy: marks tests without HTTP proxy",
        "ai_generated: marks tests generated by AI assistants",
    ]
    for marker in markers:
        config.addinivalue_line("markers", marker)

    # Register python_files pattern to ensure assertion rewriting for utils_pytest.py
    # This was previously in tox.ini as: python_files = test_*.py *_test.py utils_pytest.py
    # The first two patterns are pytest defaults, we only need to add utils_pytest.py
    config.addinivalue_line("python_files", "utils_pytest.py")

    # Register filter warnings
    # These can be overridden in extension-specific tox.ini/pytest.ini if needed
    filterwarnings = [
        "error::DeprecationWarning:^datalad",
        # TODO: https://github.com/datalad/datalad/issues/7435
        "ignore:pkg_resources is deprecated:DeprecationWarning:",
        "error:.*yield tests:pytest.PytestCollectionWarning",
        "ignore:distutils Version classes are deprecated:DeprecationWarning",
        # workaround for https://github.com/datalad/datalad/issues/6307
        "ignore:The distutils package is deprecated",
        # sent fix upstream: https://github.com/HTTPretty/HTTPretty/pull/9
        "ignore:datetime.datetime.utcnow\\(\\) is deprecated:DeprecationWarning:httpretty",
    ]
    for warning in filterwarnings:
        config.addinivalue_line("filterwarnings", warning)


def pytest_ignore_collect(collection_path: Path) -> bool:
    """Customize which files pytest collects.

    Skip old nose code and handle doctest collection carefully.
    """
    # Skip old nose code and the tests for it:
    # Note, that this is not only about executing tests but also importing those
    # files to begin with.
    if collection_path.name == "test_tests_utils.py":
        return True
    if collection_path.parts[-3:] == ("datalad", "tests", "utils.py"):
        return True
    # When pytest is told to run doctests, by default it will import every
    # source file in its search, but a number of datalad source file have
    # undesirable side effects when imported.  This hook should ensure that
    # only `test_*.py` files, `utils_pytest.py` files, and `*.py` files
    # containing doctests are imported during test collection.
    if collection_path.name.startswith("test_") or collection_path.is_dir():
        return False
    if collection_path.name == "utils_pytest.py":
        return False  # Allow utils_pytest.py to be collected
    if collection_path.suffix != ".py":
        return True
    return not any(
        re.match(r"^\s*>>>", ln) for ln in collection_path.read_text("utf-8").splitlines()
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_collectstart(collector):
    """During collection, suppress allowlisted deprecations per-extension.

    Module imports happen during collection, so deprecated API usage (e.g.
    decorators, module-level imports) triggers DeprecationWarnings here.
    We save/restore the filter list around each Module so that ignores
    only apply to the extension that owns that module.
    """
    if not isinstance(collector, pytest.Module):
        yield
        return

    ext_pkg = _get_extension_package_from_path(collector.path)
    if not ext_pkg:
        yield
        return

    saved = warnings.filters[:]
    _add_allowlist_filters(ext_pkg)
    yield
    warnings.filters[:] = saved


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_protocol(item, nextitem):
    """During test execution, suppress allowlisted deprecations per-extension.

    ``trylast=True`` ensures we run inside the ``_pytest.warnings`` plugin's
    ``catch_warnings()`` context, so our filters are cleaned up automatically.
    """
    ext_pkg = (
        _get_extension_package(item.module.__name__)
        or _get_extension_package_from_path(item.path)
    )
    if ext_pkg:
        _add_allowlist_filters(ext_pkg)
    yield
