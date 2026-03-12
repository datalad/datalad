# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for version capture in `datalad run`"""

import json
import os
import pytest

from datalad.api import run
from datalad.core.local.run import run_command
from datalad.core.local.run_versions import (
    INJECTED_VERSIONS_FILE,
    _detect_tools_from_command,
    _extract_version_from_string,
    _get_config_list,
    _get_version,
    _parse_versions_spec,
    capture_versions,
    check_stale_injected_file,
    read_injected_versions,
)
from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_repo_status,
    eq_,
    ok_,
    with_tempfile,
    with_tree,
)


@pytest.mark.ai_generated
class TestDetectToolsFromCommand:
    """Tests for _detect_tools_from_command function"""

    def test_simple_command(self):
        detected = _detect_tools_from_command("python script.py")
        assert "cmd:python" in detected

    def test_pipeline(self):
        detected = _detect_tools_from_command("cat file.txt | grep pattern | sort")
        # cat, grep, sort are in ignore list, but let's check pipeline parsing
        # Actually they're in ignore list, so won't be detected
        assert "cmd:cat" not in detected
        assert "cmd:grep" not in detected

    def test_complex_command(self):
        detected = _detect_tools_from_command(
            "python script.py && git commit -m 'msg'"
        )
        assert "cmd:python" in detected
        assert "cmd:git" in detected

    def test_with_path(self):
        detected = _detect_tools_from_command("/usr/bin/python script.py")
        assert "cmd:python" in detected

    def test_relative_path(self):
        detected = _detect_tools_from_command("./myscript.sh arg1")
        # Should extract basename
        assert "cmd:myscript.sh" in detected

    def test_variable_assignment(self):
        detected = _detect_tools_from_command("VAR=value python script.py")
        assert "cmd:python" in detected
        assert "cmd:VAR=value" not in detected

    def test_empty_command(self):
        detected = _detect_tools_from_command("")
        eq_(detected, set())

    def test_shell_builtin_ignored(self):
        detected = _detect_tools_from_command("echo hello")
        assert "cmd:echo" not in detected


@pytest.mark.ai_generated
class TestExtractVersionFromString:
    """Tests for _extract_version_from_string function"""

    def test_semver(self):
        eq_(_extract_version_from_string("Python 3.12.0"), "3.12.0")

    def test_with_v_prefix(self):
        eq_(_extract_version_from_string("v1.2.3"), "1.2.3")

    def test_with_suffix(self):
        eq_(_extract_version_from_string("git version 2.43.0-rc1"), "2.43.0-rc1")

    def test_major_minor_only(self):
        eq_(_extract_version_from_string("tool 1.2"), "1.2")

    def test_no_version(self):
        eq_(_extract_version_from_string("no version here"), None)


@pytest.mark.ai_generated
class TestParseVersionsSpec:
    """Tests for _parse_versions_spec function"""

    @with_tempfile(mkdir=True)
    def test_auto(self, path=None):
        ds = Dataset(path).create()
        specs, custom = _parse_versions_spec("auto", ds)
        assert "auto" in specs
        eq_(custom, {})

    @with_tempfile(mkdir=True)
    def test_none_string(self, path=None):
        ds = Dataset(path).create()
        # 'none' is a reserved keyword
        specs, custom = _parse_versions_spec("none", ds)
        assert "none" in specs

    @with_tempfile(mkdir=True)
    def test_explicit_list(self, path=None):
        ds = Dataset(path).create()
        # Now requires py: prefix for Python packages
        specs, custom = _parse_versions_spec("cmd:python,py:numpy,py:pandas", ds)
        assert "cmd:python" in specs
        assert "py:numpy" in specs
        assert "py:pandas" in specs

    @with_tempfile(mkdir=True)
    def test_unprefixed_rejected(self, path=None):
        ds = Dataset(path).create()
        # Unprefixed names (not auto/none) should be rejected with warning
        specs, custom = _parse_versions_spec("numpy", ds)
        # Should NOT be added since it lacks prefix
        assert "numpy" not in specs

    @with_tempfile(mkdir=True)
    def test_custom_command(self, path=None):
        ds = Dataset(path).create()
        specs, custom = _parse_versions_spec(
            "cmd:mytool:mytool --show-version", ds
        )
        assert "cmd:mytool" in specs
        eq_(custom["cmd:mytool"], "mytool --show-version")

    @with_tempfile(mkdir=True)
    def test_from_file(self, path=None):
        ds = Dataset(path).create()
        # Create a versions.json file with proper prefixes
        versions_file = os.path.join(path, "versions.json")
        with open(versions_file, "w") as f:
            json.dump({"cmd:python": None, "py:numpy": None}, f)

        specs, custom = _parse_versions_spec("@versions.json", ds)
        assert "cmd:python" in specs
        assert "py:numpy" in specs


@pytest.mark.ai_generated
class TestGetVersion:
    """Tests for _get_version function"""

    def test_datalad_version(self):
        ver = _get_version("py:datalad")
        ok_(ver is not None)

    def test_python_version(self):
        ver = _get_version("cmd:python")
        ok_(ver is not None)
        # Should be a version string like "3.x.y"
        assert ver.startswith("3.")

    def test_unknown_package(self):
        ver = _get_version("py:nonexistent_package_xyz")
        eq_(ver, None)


@pytest.mark.ai_generated
class TestInjectedVersionsFile:
    """Tests for injected versions file handling"""

    @with_tempfile(mkdir=True)
    def test_check_stale_no_file(self, path=None):
        ds = Dataset(path).create()
        # No stale file
        ok_(not check_stale_injected_file(ds))

    @with_tempfile(mkdir=True)
    def test_check_stale_with_file(self, path=None):
        ds = Dataset(path).create()
        # Create stale file
        injected_path = os.path.join(path, INJECTED_VERSIONS_FILE)
        os.makedirs(os.path.dirname(injected_path), exist_ok=True)
        with open(injected_path, "w") as f:
            json.dump({"cmd:test": "1.0"}, f)
        # Should detect stale file
        ok_(check_stale_injected_file(ds))

    @with_tempfile(mkdir=True)
    def test_read_injected_no_file(self, path=None):
        ds = Dataset(path).create()
        eq_(read_injected_versions(ds), None)

    @with_tempfile(mkdir=True)
    def test_read_injected_with_file(self, path=None):
        ds = Dataset(path).create()
        # Create injected file
        injected_path = os.path.join(path, INJECTED_VERSIONS_FILE)
        os.makedirs(os.path.dirname(injected_path), exist_ok=True)
        with open(injected_path, "w") as f:
            json.dump({"cmd:container": "1.0", "container:image": "test"}, f)

        versions = read_injected_versions(ds)
        eq_(versions["cmd:container"], "1.0")
        eq_(versions["container:image"], "test")
        # File should be deleted
        ok_(not os.path.exists(injected_path))


@pytest.mark.ai_generated
class TestCaptureVersions:
    """Tests for capture_versions function"""

    @with_tempfile(mkdir=True)
    def test_capture_auto(self, path=None):
        ds = Dataset(path).create()
        versions = capture_versions("python script.py", "auto", ds)
        # Should include py:datalad (from default include)
        assert "py:datalad" in versions
        # May include cmd:python if detected and available
        # (depends on environment)

    @with_tempfile(mkdir=True)
    def test_capture_none(self, path=None):
        ds = Dataset(path).create()
        versions = capture_versions("python script.py", "none", ds)
        eq_(versions, {})

    @with_tempfile(mkdir=True)
    def test_capture_explicit(self, path=None):
        ds = Dataset(path).create()
        versions = capture_versions(
            "python script.py", "py:datalad,cmd:python", ds
        )
        assert "py:datalad" in versions
        # cmd:python should be captured if python is available
        if "cmd:python" in versions:
            assert versions["cmd:python"].startswith("3.")


@pytest.mark.ai_generated
class TestRunWithVersions:
    """Integration tests for run with version capture"""

    @with_tree(tree={"script.py": "print('hello')"})
    def test_run_captures_versions(self, path=None):
        ds = Dataset(path).create(force=True)
        ds.save()
        # Run with auto version capture
        results = list(run_command(
            "echo hello",
            dataset=ds,
            versions="auto",
        ))
        # Check that versions were captured in run_info
        run_result = [r for r in results if r.get("action") == "run"][0]
        run_info = run_result.get("run_info", {})
        # py:datalad should be in versions (from default include)
        assert "versions" in run_info
        assert "py:datalad" in run_info["versions"]

    @with_tree(tree={"script.py": "print('hello')"})
    def test_run_versions_none(self, path=None):
        ds = Dataset(path).create(force=True)
        ds.save()
        # Run with version capture disabled
        results = list(run_command(
            "echo hello",
            dataset=ds,
            versions="none",
        ))
        run_result = [r for r in results if r.get("action") == "run"][0]
        run_info = run_result.get("run_info", {})
        # versions should be empty or not present
        versions = run_info.get("versions", {})
        eq_(versions, {})

    @with_tree(tree={"script.py": "print('hello')"})
    def test_run_with_extra_info_versions(self, path=None):
        ds = Dataset(path).create(force=True)
        ds.save()
        # Run with extra_info containing versions (simulating extension)
        results = list(run_command(
            "echo hello",
            dataset=ds,
            versions="auto",
            extra_info={"versions": {"container:image": "test:latest"}},
        ))
        run_result = [r for r in results if r.get("action") == "run"][0]
        run_info = run_result.get("run_info", {})
        # Should have both captured and extra versions
        assert "versions" in run_info
        assert "py:datalad" in run_info["versions"]
        assert run_info["versions"]["container:image"] == "test:latest"
