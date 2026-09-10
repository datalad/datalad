# Set up a local SSH server on a Windows CI runner so that
# DATALAD_TESTS_SSH-gated tests (which SSH to "datalad-test"/"datalad-test2",
# see tools/ci/appveyor_ssh_config) have something to talk to.
#
# This mirrors what AppVeyor's Windows workers used to do
# (tools/ci/appveyor_ssh2localhost.bat), but uses the OpenSSH Server optional
# capability that already ships with the Windows Server image GitHub Actions
# windows-* runners are built from, instead of downloading and installing an
# old (2018) third-party OpenSSH-Win32 build.
$ErrorActionPreference = "Stop"

Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

$sshDir = "$env:USERPROFILE\.ssh"
New-Item -ItemType Directory -Force -Path $sshDir | Out-Null

ssh-keygen -f "$sshDir\id_rsa" -N '""'
Copy-Item "$sshDir\id_rsa.pub" "$sshDir\authorized_keys"
Copy-Item tools\ci\appveyor_ssh_config "$sshDir\config"

# Windows' OpenSSH server refuses an authorized_keys file that is writable by
# anyone but the owner and Administrators -- reset its ACL explicitly, since
# files created by New-Item/Copy-Item inherit broader permissions by default.
icacls $sshDir /inheritance:r | Out-Null
icacls $sshDir /grant:r "${env:USERNAME}:(OI)(CI)F" "BUILTIN\Administrators:(OI)(CI)F" "NT AUTHORITY\SYSTEM:(OI)(CI)F" | Out-Null

# "datalad-test"/"datalad-test2" are the hostnames the test suite connects
# to (see tools/ci/appveyor_ssh_config and DATALAD_TESTS_SSH); AppVeyor
# provided these via its `hosts:` config section, GitHub Actions has no
# equivalent so point them at localhost via the hosts file instead.
Add-Content -Path "$env:SystemRoot\System32\drivers\etc\hosts" `
    -Value "`r`n127.0.0.1 datalad-test`r`n127.0.0.1 datalad-test2"

# Verify the setup before tests rely on it.
ssh -o StrictHostKeyChecking=no localhost exit
ssh -o StrictHostKeyChecking=no datalad-test exit
ssh -o StrictHostKeyChecking=no datalad-test2 exit
