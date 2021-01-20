REM authorize access with these keys
copy C:\Users\appveyor\.ssh\id_rsa.pub c:\Users\appveyor\.ssh\authorized_keys
REM OpenSSH server setup
appveyor DownloadFile https://github.com/PowerShell/Win32-OpenSSH/releases/download/v7.6.1.0p1-Beta/OpenSSH-Win32.zip -FileName C:\DLTMP\openssh.zip
7z x -o"C:\DLTMP" C:\DLTMP\openssh.zip
REM install
powershell.exe -ExecutionPolicy Bypass -File C:\DLTMP\OpenSSH-Win32\install-sshd.ps1
REM configure service
powershell.exe New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
REM fire up service
net start sshd
REM deploy standard SSH config
copy tools\ci\appveyor_ssh_config c:\Users\appveyor\.ssh\config
