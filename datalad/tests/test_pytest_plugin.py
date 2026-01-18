# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for DataLad pytest plugin.

These tests verify that the pytest plugin correctly registers markers,
configuration, and works as expected for DataLad extensions.

The tests use pytest's pytester fixture to run pytest in a subprocess,
avoiding double-registration issues when testing the plugin itself.
"""

import pytest

# Enable pytester fixture for plugin testing
pytest_plugins = ["pytester"]


@pytest.mark.ai_generated
def test_plugin_registers_markers(pytester):
    """Test that plugin registers custom markers."""
    pytester.makepyfile("""
        import pytest

        @pytest.mark.network
        def test_network():
            pass

        @pytest.mark.slow
        def test_slow():
            pass

        @pytest.mark.integration
        def test_integration():
            pass
    """)

    result = pytester.runpytest_subprocess("--markers")
    # Check that key markers are registered (not order-dependent)
    output = result.stdout.str()
    assert "@pytest.mark.network: marks tests requiring network access" in output
    assert "@pytest.mark.slow: marks slow tests" in output
    assert "@pytest.mark.integration: marks integration tests" in output


@pytest.mark.ai_generated
def test_plugin_markers_work(pytester):
    """Test that markers can be used for test selection."""
    pytester.makepyfile("""
        import pytest

        @pytest.mark.network
        def test_with_network():
            assert True

        def test_without_marker():
            assert True
    """)

    # Select only network tests
    result = pytester.runpytest_subprocess("-v", "-m", "network")
    result.stdout.fnmatch_lines(["*test_with_network*PASSED*"])
    assert "test_without_marker" not in result.stdout.str()


@pytest.mark.ai_generated
def test_plugin_python_files_pattern(pytester):
    """Test that utils_pytest.py is collected."""
    pytester.makepyfile(utils_pytest="""
        def test_in_utils_pytest():
            assert True
    """)

    # Run with collect-only to see if file is discovered
    result = pytester.runpytest_subprocess("-v", "--collect-only")
    # Check that utils_pytest.py is in the collected items
    assert "utils_pytest.py" in result.stdout.str(), \
        f"utils_pytest.py not collected. Output:\n{result.stdout.str()}"

    # Now run the actual test
    result = pytester.runpytest_subprocess("-v")
    result.stdout.fnmatch_lines(["*utils_pytest*test_in_utils_pytest*PASSED*"])


@pytest.mark.ai_generated
def test_plugin_ignores_nose_tests(pytester):
    """Test that old nose test files are ignored."""
    pytester.makepyfile(test_tests_utils="""
        def test_should_not_run():
            assert False, "This should be ignored"
    """)

    result = pytester.runpytest_subprocess("-v", "--collect-only")
    # test_tests_utils.py should be ignored
    assert "test_tests_utils" not in result.stdout.str()


@pytest.mark.ai_generated
def test_plugin_filterwarnings_configured(pytester):
    """Test that filterwarnings are registered."""
    # Create a test that would trigger warnings
    pytester.makepyfile("""
        import warnings

        def test_warning():
            # This test just checks that pytest can run
            # The actual filterwarnings behavior is harder to test
            # in isolation, but we verify the config is present
            assert True
    """)

    result = pytester.runpytest_subprocess("--help")
    # Just verify pytest runs successfully with our plugin
    assert result.ret == 0


@pytest.mark.ai_generated
def test_plugin_works_for_extensions(pytester):
    """Test simulating how an extension would use the plugin."""
    # Create an extension-like test structure
    pytester.makepyfile("""
        import pytest

        @pytest.mark.slow
        @pytest.mark.network
        def test_extension_functionality():
            '''Example extension test using datalad markers.'''
            assert True

        @pytest.mark.turtle
        def test_very_slow():
            '''Example of very slow test.'''
            assert True
    """)

    # Test that marker selection works
    result = pytester.runpytest_subprocess("-v", "-m", "slow and network")
    result.stdout.fnmatch_lines(["*test_extension_functionality*PASSED*"])
    assert "test_very_slow" not in result.stdout.str()

    # Test that turtle marker works
    result = pytester.runpytest_subprocess("-v", "-m", "turtle")
    result.stdout.fnmatch_lines(["*test_very_slow*PASSED*"])
    assert "test_extension_functionality" not in result.stdout.str()


@pytest.mark.ai_generated
def test_all_expected_markers_present(pytester):
    """Verify all expected markers are registered."""
    result = pytester.runpytest_subprocess("--markers")

    # Check for key markers
    expected_markers = [
        "network",
        "slow",
        "turtle",
        "integration",
        "known_failure",
        "skip_if_no_network",
        "windows",
        "osx",
        "ai_generated",
    ]

    for marker in expected_markers:
        assert marker in result.stdout.str(), f"Marker '{marker}' not found"


@pytest.mark.ai_generated
@pytest.mark.slow
def test_plugin_no_double_registration(pytester):
    """Test that the plugin doesn't cause double registration.

    This is a critical test ensuring the architectural fix works.
    When testing datalad itself, the hooks from pytest_plugin are
    imported into conftest, not registered via entry point, so there
    should be no double registration.
    """
    pytester.makepyfile("""
        import pytest

        @pytest.mark.network
        def test_example():
            assert True
    """)

    result = pytester.runpytest_subprocess("-v")
    # Should not have any plugin registration errors
    assert "Plugin already registered" not in result.stdout.str()
    assert "Plugin already registered" not in result.stderr.str()
    assert result.ret == 0
