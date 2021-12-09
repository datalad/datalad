REM Install git-annex
appveyor DownloadFile https://datasets.datalad.org/datalad/packages/windows/git-annex-installer_8.20211117_x64.exe -FileName C:\DLTMP\git-annex-installer.exe
REM 7z is preinstalled in all images
REM Extract directly into system Git installation
7z x -aoa -o"C:\\Program Files\Git" C:\DLTMP\git-annex-installer.exe
