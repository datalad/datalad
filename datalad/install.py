#!/usr/bin/python3
__python_requires__ = "~= 3.6"
import argparse
from contextlib import contextmanager
from glob import glob
import logging
import os
import os.path
from pathlib import Path
import platform
from shlex import quote
import shutil
import subprocess
import sys
import tempfile

DOWNLOAD_LATEST_ARTIFACT = (
    Path(__file__).parent / "tools" / "ci" / "download-latest-artifact"
)

log = logging.getLogger("datalad.install")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adjust-bashrc",
        action="store_true",
        help="If the scheme tweaks PATH, prepend a snippet to ~/.bashrc that exports that path.",
    )
    parser.add_argument(
        "-E",
        "--env-write-file",
        help="Write modified environment variables to this file",
    )
    schemata = parser.add_subparsers(
        title="schema",
        dest="schema",
        description='Type of git-annex installation (default "conda-forge")',
    )
    schemata.add_parser("autobuild", help="Linux, macOS only")
    schemata.add_parser("brew", help="macOS only")
    scm_conda_forge = schemata.add_parser("conda-forge", help="Linux only")
    scm_conda_forge.add_argument("version", nargs="?")
    scm_conda_forge_last = schemata.add_parser("conda-forge-last", help="Linux only")
    scm_conda_forge_last.add_argument("version", nargs="?")
    schemata.add_parser("datalad-extensions-build", help="Linux, macOS only")
    scm_deb_url = schemata.add_parser("deb-url", help="Linux only")
    scm_deb_url.add_argument("url")
    schemata.add_parser("neurodebian", help="Linux only")
    schemata.add_parser("neurodebian-devel", help="Linux only")
    schemata.add_parser("snapshot", help="Linux, macOS only")
    args = parser.parse_args()
    if args.schema is None:
        args.schema = "conda-forge"
    if args.env_write_file is not None:
        with open(args.env_write_file, "w"):
            # Force file to exist and start out empty
            pass
    installer = GitAnnexInstaller(
        adjust_bashrc=args.adjust_bashrc, env_write_file=args.env_write_file,
    )
    if args.schema == "autobuild":
        installer.install_via_autobuild()
    elif args.schema == "brew":
        installer.install_via_brew()
    elif args.schema == "conda-forge":
        installer.install_via_conda_forge(args.version)
    elif args.schema == "conda-forge-last":
        installer.install_via_conda_forge_last(args.version)
    elif args.schema == "datalad-extensions-build":
        installer.install_via_datalad_extensions_build()
    elif args.schema == "deb-url":
        installer.install_via_deb_url(args.url)
    elif args.schema == "neurodebian":
        installer.install_via_neurodebian()
    elif args.schema == "neurodebian-devel":
        installer.install_via_neurodebian_devel()
    elif args.schema == "snapshot":
        installer.install_via_snapshot()
    else:
        raise RuntimeError(f"Invalid schema: {args.schema}")


class GitAnnexInstaller:
    def __init__(self, adjust_bashrc=False, env_write_file=None):
        self.pathline = None
        self.annex_bin = "/usr/bin"
        self.adjust_bashrc = adjust_bashrc
        self.env_write_file = Path(env_write_file)

    def addpath(self, p, last=False):
        if self.pathline is not None:
            raise RuntimeError("addpath() called more than once")
        if not last:
            newpath = f'{quote(p)}:"$PATH"'
        else:
            newpath = f'"$PATH":{quote(p)}'
        self.pathline = f"export PATH={newpath}"
        if self.env_write_file is not None:
            with self.env_write_file.open("a") as fp:
                print(self.pathline, file=fp)

    def install_via_neurodebian(self):
        # TODO: use nd_freeze_install for an arbitrary version specified
        # we assume neurodebian is generally configured
        subprocess.run(
            ["sudo", "apt-get", "install", "git-annex-standalone"], check=True,
        )
        self.post_install()

    def install_via_neurodebian_devel(self):
        # if debian-devel is not setup -- set it up
        r = subprocess.run(
            ["apt-cache", "policy", "git-annex-standalone"],
            stdout=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
        if "/debian-devel " not in r.stdout:
            # configure
            with open("/etc/apt/sources.list.d/neurodebian.sources.list") as fp:
                srclist = fp.read()
            srclist = srclist.replace("/debian ", "/debian-devel ")
            subprocess.run(
                [
                    "sudo",
                    "tee",
                    "/etc/apt/sources.list.d/neurodebian-devel.sources.list",
                ],
                input=srclist,
                universal_newlines=True,
                check=True,
            )
            subprocess.run(["sudo", "apt-get", "update"], check=True)
        # check versions
        # devel:
        r = subprocess.run(
            ["apt-cache", "policy", "git-annex-standalone"],
            stdout=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
        policy = r.stdout
        devel_annex_version = None
        current_annex_version = None
        prev = None
        for line in policy.splitlines():
            if "/debian-devel " in line:
                assert prev is not None
                if "ndall" in prev:
                    assert devel_annex_version is None
                    devel_annex_version = prev.split()[0]
            if "***" in line:
                assert current_annex_version is None
                current_annex_version = line.split()[1]
            prev = line
        assert devel_annex_version is not None, "Could not find devel annex version"
        assert current_annex_version is not None, "Could not find current annex version"
        if (
            subprocess.run(
                [
                    "dpkg",
                    "--compare-versions",
                    devel_annex_version,
                    "gt",
                    current_annex_version,
                ]
            ).returncode
            == 0
        ):
            subprocess.run(
                [
                    "sudo",
                    "apt-get",
                    "install",
                    f"git-annex-standalone={devel_annex_version}",
                ],
                check=True,
            )
        else:
            log.info(
                "devel version %s is not newer than installed %s",
                devel_annex_version,
                current_annex_version,
            )
        self.post_install()

    def install_via_deb_url(self, url):
        with tempfile.TemporaryDirectory() as tmpdir:
            debpath = os.path.join(tmpdir, "git-annex.deb")
            subprocess.run(["wget", "-O", debpath, url], check=True)
            subprocess.run(["sudo", "dpkg", "-i", debpath], check=True)
        self.post_install()

    def install_via_autobuild(self):
        systype = platform.system()
        if systype == "Linux":
            self._install_via_autobuild_or_snapshot_linux("autobuild/amd64")
        elif systype == "Darwin":
            self._install_via_autobuild_or_snapshot_macos(
                "autobuild/x86_64-apple-yosemite"
            )
        else:
            raise RuntimeError(f"E: Unsupported OS: {systype}")

    def install_via_snapshot(self):
        systype = platform.system()
        if systype == "Linux":
            self._install_via_autobuild_or_snapshot_linux("linux/current")
        elif systype == "Darwin":
            self._install_via_autobuild_or_snapshot_macos("OSX/current/10.10_Yosemite")
        else:
            raise RuntimeError(f"E: Unsupported OS: {systype}")

    def _install_via_autobuild_or_snapshot_linux(self, subpath):
        tmpdir = tempfile.mkdtemp(prefix="ga-")
        self.annex_bin = os.path.join(tmpdir, "git-annex.linux")
        log.info("downloading and extracting under %s", self.annex_bin)
        wget = subprocess.Popen(
            [
                "wget",
                "-q",
                "-O-",
                f"https://downloads.kitenet.net/git-annex/{subpath}/git-annex-standalone-amd64.tar.gz",
            ],
            stdout=subprocess.PIPE,
        )
        tar = subprocess.Popen(["tar", "-C", tmpdir, "-xzf"], stdin=wget.stdout)
        wget.stdout.close()
        tar.communicate()
        wget.wait()
        if wget.returncode != 0:
            sys.exit(f"wget failed with exit code {wget.returncode}")
        if tar.returncode != 0:
            sys.exit(f"tar failed with exit code {tar.returncode}")
        self.addpath(self.annex_bin)
        self.post_install()

    def _install_via_autobuild_or_snapshot_macos(self, subpath):
        with tempfile.TemporaryDirectory() as tmpdir:
            dmgpath = os.path.join(tmpdir, "git-annex.dmg")
            subprocess.run(
                [
                    "wget",
                    "-q",
                    "-O",
                    dmgpath,
                    f"https://downloads.kitenet.net/git-annex/{subpath}/git-annex.dmg",
                ],
                check=True,
            )
            self._install_from_dmg(dmgpath)
        self.post_install()

    def install_via_conda_forge(self, version=None):
        tmpdir = tempfile.mkdtemp(prefix="ga-")
        self.annex_bin = os.path.join(tmpdir, "annex-bin")
        self.addpath(self.annex_bin)
        self._install_via_conda(version, tmpdir)

    def install_via_conda_forge_last(self, version=None):
        tmpdir = tempfile.mkdtemp(prefix="ga-")
        self.annex_bin = os.path.join(tmpdir, "annex-bin")
        if shutil.which("git-annex") is not None:
            log.warning(
                "git annex already installed.  In this case this setup has no sense"
            )
            sys.exit(1)
        # We are interested only to get git-annex into our environment
        # So as to not interfere with "system wide" Python etc, we will add
        # miniconda at the end of the path
        self.addpath(self.annex_bin, last=True)
        self._install_via_conda(version, tmpdir)

    def _install_via_conda(self, version, tmpdir):
        miniconda_script = "Miniconda3-latest-Linux-x86_64.sh"
        conda_bin = os.path.join(tmpdir, "miniconda", "bin")
        # We will symlink git-annex only under a dedicated directory, so it could be
        # used with default Python etc. If names changed here, possibly adjust
        # hardcoded duplicates below where we establish relative symlinks.
        log.info("downloading and running miniconda installer")
        subprocess.run(
            [
                "wget",
                "-q",
                "-O",
                os.path.join(tmpdir, miniconda_script),
                (
                    os.environ.get("ANACONDA_URL")
                    or "https://repo.anaconda.com/miniconda/"
                )
                + miniconda_script,
            ],
            check=True,
        )
        subprocess.run(
            [
                "bash",
                os.path.join(tmpdir, miniconda_script),
                "-b",
                "-p",
                os.path.join(tmpdir, "miniconda"),
            ],
            env=dict(os.environ, HOME=tmpdir),
            check=True,
        )
        subprocess.run(
            [
                os.path.join(conda_bin, "conda"),
                "install",
                "-q",
                "-c",
                "conda-forge",
                "-y",
                f"git-annex{version}",
            ],
            check=True,
        )
        if self.annex_bin != conda_bin:
            os.makedirs(self.annex_bin, exist_ok=True)
            with dirchanged(self.annex_bin):
                for fname in glob("../miniconda/bin/git-annex*"):
                    os.symlink(fname, os.path.basename(fname))
        self.post_install()

    def install_via_datalad_extensions_build(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            systype = platform.system()
            if systype == "Linux":
                subprocess.run(
                    [str(DOWNLOAD_LATEST_ARTIFACT)],
                    env=dict(os.environ, TARGET_PATH=tmpdir),
                    check=True,
                )
                (debpath,) = Path(tmpdir).glob("*.deb")
                subprocess.run(["sudo", "dpkg", "-i", str(debpath)], check=True)
            elif systype == "Darwin":
                subprocess.run(
                    [str(DOWNLOAD_LATEST_ARTIFACT)],
                    env=dict(
                        os.environ,
                        TARGET_PATH=tmpdir,
                        TARGET_ARTIFACT="git-annex-macos-dmg",
                    ),
                    check=True,
                )
                (dmgpath,) = Path(tmpdir).glob("*.dmg")
                self._install_from_dmg(dmgpath)
            else:
                raise RuntimeError(f"E: Unsupported OS: {systype}")
        self.post_install()

    def install_via_brew(self):
        subprocess.run(["brew", "install", "git-annex"], check=True)
        self.annex_bin = "/usr/local/bin"
        self.post_install()

    def _install_from_dmg(self, dmgpath):
        subprocess.run(["hdiutil", "attach", str(dmgpath)], check=True)
        subprocess.run(
            ["rsync", "-a", "/Volumes/git-annex/git-annex.app", "/Applications/"],
            check=True,
        )
        subprocess.run(["hdiutil", "detach", "/Volumes/git-annex/"], check=True)
        self.annex_bin = "/Applications/git-annex.app/Contents/MacOS"
        self.addpath(self.annex_bin)

    def post_install(self):
        if self.adjust_bashrc and self.pathline is not None:
            # If PATH was changed, we need to make it available to SSH commands.
            # Note: Prepending is necessary. SSH commands load .bashrc, but many
            # distributions (including Debian and Ubuntu) come with a snippet
            # to exit early in that case.
            bashrc = Path.home() / ".bashrc"
            contents = bashrc.read_text()
            bashrc.write_text(self.pathline + "\n" + contents)
            log.info("Adjusted first line of ~/.bashrc:")
            log.info("%s", self.pathline)
        # Rudimentary test of installation and inform user about location
        for binname in ["git-annex", "git-annex-shell"]:
            if not os.access(os.path.join(self.annex_bin, binname), os.X_OK):
                raise RuntimeError(f"Cannot execute {binname}")
        log.info("git-annex is available under %r", self.annex_bin)


@contextmanager
def dirchanged(dirpath):
    """
    ``dirchanged(dirpath)`` returns a context manager.  On entry, it stores the
    current working directory path and then changes the current directory to
    ``dirpath``.  On exit, it changes the current directory back to the stored
    path.
    """
    olddir = os.getcwd()
    os.chdir(dirpath)
    try:
        yield
    finally:
        os.chdir(olddir)


if __name__ == "__main__":
    main()
