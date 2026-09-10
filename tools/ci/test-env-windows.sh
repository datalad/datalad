#!/bin/bash
#
# Provision a Windows (GitHub-hosted) runner for the datalad test suite:
# NTFS long-path support, a short TMP/TEMP scratch dir (generated test
# paths can still hit MAX_PATH-related limits even with long paths
# enabled), and a local SSH server for DATALAD_TESTS_SSH-gated tests to
# talk to.
#
# This is run under Git-Bash (test.yml's `defaults.run.shell`, which is
# bash on every OS here -- see that file), which is why plain Windows
# executables (reg.exe, dism.exe, sc.exe, icacls.exe) rather than
# PowerShell cmdlets are used throughout: it keeps this script one
# ordinary, shellcheck-able bash script instead of a second script in a
# second language. It mirrors what AppVeyor's Windows workers used to do
# (tools/ci/appveyor_ssh2localhost.bat), but installs OpenSSH Server via
# the Windows feature the runner image already carries instead of
# downloading an old (2018) third-party OpenSSH-Win32 build.
set -eo pipefail

# Remove Windows' 260-char path length limit.
reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem" \
  /v LongPathsEnabled /t REG_DWORD /d 1 /f

# Globally enable git-annex's fast per-file `add` path on Windows (needs
# git-annex >= 8.20211117); see
# https://git-annex.branchable.com/bugs/Windows__58___substantial_per-file_cost_for___96__add__96__/
git config --system filter.annex.process "git-annex filter-process"

# A short, top-level scratch dir keeps generated test paths well under
# Windows' path-length limits even with LongPathsEnabled.
mkdir -p /c/DLTMP
{
  echo "TMP=C:\\DLTMP"
  echo "TEMP=C:\\DLTMP"
} >> "$GITHUB_ENV"

# --- SSH server, for DATALAD_TESTS_SSH ---

dism.exe /Online /NoRestart /Add-Capability /CapabilityName:OpenSSH.Server~~~~0.0.1.0
sc.exe config sshd start=auto
net start sshd

mkdir -p ~/.ssh
ssh-keygen -f ~/.ssh/id_rsa -N ""
cp ~/.ssh/id_rsa.pub ~/.ssh/authorized_keys
cp tools/ci/appveyor_ssh_config ~/.ssh/config

# Windows' OpenSSH server refuses an authorized_keys file that is writable
# by anyone but the owner and Administrators; Git-Bash's HOME is
# %USERPROFILE% here, so the two paths below refer to the same directory.
icacls "$USERPROFILE\\.ssh" /inheritance:r
icacls "$USERPROFILE\\.ssh" /grant:r \
  "${USERNAME}:(OI)(CI)F" \
  "BUILTIN\\Administrators:(OI)(CI)F" \
  "NT AUTHORITY\\SYSTEM:(OI)(CI)F"

# "datalad-test"/"datalad-test2" are the hostnames the test suite connects
# to (see tools/ci/appveyor_ssh_config and DATALAD_TESTS_SSH); AppVeyor
# provided these via its `hosts:` config section, GitHub Actions has no
# equivalent so point them at localhost via the hosts file instead.
printf '\n127.0.0.1 datalad-test\n127.0.0.1 datalad-test2\n' \
  >> /c/Windows/System32/drivers/etc/hosts

# Verify the setup before tests rely on it.
ssh -o StrictHostKeyChecking=no localhost exit
ssh -o StrictHostKeyChecking=no datalad-test exit
ssh -o StrictHostKeyChecking=no datalad-test2 exit
