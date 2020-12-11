#!/usr/bin/env python3
__python_requires__ = "~= 3.6"
import argparse
import json
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
from urllib.request import Request, urlopen
from zipfile import ZipFile

log = logging.getLogger("datalad.install")


def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)-8s] %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        level=logging.INFO,
    )
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
    scm_conda_forge = schemata.add_parser("conda-forge", help="Linux, macOS only")
    scm_conda_forge.add_argument("-b", "--batch", action="store_true")
    scm_conda_forge.add_argument("--path-miniconda")
    scm_conda_forge.add_argument("version", nargs="?")
    scm_conda_forge_last = schemata.add_parser(
        "conda-forge-last", help="Linux, macOS only"
    )
    scm_conda_forge_last.add_argument("-b", "--batch", action="store_true")
    scm_conda_forge_last.add_argument("--path-miniconda")
    scm_conda_forge_last.add_argument("version", nargs="?")
    schemata.add_parser("datalad-git-annex-build", help="Linux, macOS only")
    scm_deb_url = schemata.add_parser("deb-url", help="Linux only")
    scm_deb_url.add_argument("url")
    schemata.add_parser("neurodebian", help="Linux only")
    schemata.add_parser("neurodebian-devel", help="Linux only")
    schemata.add_parser("snapshot", help="Linux, macOS only")
    scm_miniconda = schemata.add_parser(
        "miniconda", help="Install just Miniconda; Linux, macOS only"
    )
    scm_miniconda.add_argument("-b", "--batch", action="store_true")
    scm_miniconda.add_argument("--path-miniconda")
    scm_datalad = schemata.add_parser(
        "datalad", help="Install Datalad via Miniconda; Linux, macOS only"
    )
    scm_datalad.add_argument("-b", "--batch", action="store_true")
    scm_datalad.add_argument("--path-miniconda")
    args = parser.parse_args()
    if args.env_write_file is not None:
        with open(args.env_write_file, "w"):
            # Force file to exist and start out empty
            pass
    installer = GitAnnexInstaller(
        adjust_bashrc=args.adjust_bashrc, env_write_file=args.env_write_file,
    )
    if args.schema is None:
        installer.install_via_conda_forge()
    elif args.schema == "autobuild":
        installer.install_via_autobuild()
    elif args.schema == "brew":
        installer.install_via_brew()
    elif args.schema == "conda-forge":
        installer.install_via_conda_forge(
            args.version, miniconda_path=args.path_miniconda, batch=args.batch
        )
    elif args.schema == "conda-forge-last":
        installer.install_via_conda_forge_last(
            args.version, miniconda_path=args.path_miniconda, batch=args.batch
        )
    elif args.schema == "datalad-git-annex-build":
        installer.install_via_datalad_git_annex_build()
    elif args.schema == "deb-url":
        installer.install_via_deb_url(args.url)
    elif args.schema == "neurodebian":
        installer.install_via_neurodebian()
    elif args.schema == "neurodebian-devel":
        installer.install_via_neurodebian_devel()
    elif args.schema == "snapshot":
        installer.install_via_snapshot()
    elif args.schema == "miniconda":
        miniconda_path = args.path_miniconda
        if miniconda_path is None:
            miniconda_path = os.path.join(tempfile.mkdtemp(prefix="ga-"), "miniconda")
        installer.install_miniconda(miniconda_path, batch=args.batch)
    elif args.schema == "datalad":
        miniconda_path = args.path_miniconda
        if miniconda_path is None:
            miniconda_path = os.path.join(tempfile.mkdtemp(prefix="ga-"), "miniconda")
        installer.install_datalad(miniconda_path, batch=args.batch)
    else:
        raise RuntimeError(f"Invalid schema: {args.schema}")


class GitAnnexInstaller:
    def __init__(self, adjust_bashrc=False, env_write_file=None):
        self.pathline = None
        self.annex_bin = "/usr/bin"
        self.adjust_bashrc = adjust_bashrc
        if env_write_file is None:
            self.env_write_file = None
        else:
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
        if current_annex_version is None or (
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
            download_file(url, debpath)
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
        gzfile = os.path.join(tmpdir, "git-annex-standalone-amd64.tar.gz")
        download_file(
            f"https://downloads.kitenet.net/git-annex/{subpath}/git-annex-standalone-amd64.tar.gz",
            gzfile,
        )
        subprocess.run(["tar", "-C", tmpdir, "-xzf", gzfile], check=True)
        self.addpath(self.annex_bin)
        self.post_install()

    def _install_via_autobuild_or_snapshot_macos(self, subpath):
        with tempfile.TemporaryDirectory() as tmpdir:
            dmgpath = os.path.join(tmpdir, "git-annex.dmg")
            download_file(
                f"https://downloads.kitenet.net/git-annex/{subpath}/git-annex.dmg",
                dmgpath,
            )
            self._install_from_dmg(dmgpath)
        self.post_install()

    def install_via_conda_forge(self, version=None, miniconda_path=None, batch=False):
        tmpdir = tempfile.mkdtemp(prefix="ga-")
        self.annex_bin = os.path.join(tmpdir, "annex-bin")
        self.addpath(self.annex_bin)
        self._install_via_conda(version, tmpdir, miniconda_path, batch)

    def install_via_conda_forge_last(
        self, version=None, miniconda_path=None, batch=False
    ):
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
        self._install_via_conda(version, tmpdir, miniconda_path, batch)

    def _install_via_conda(self, version, tmpdir, miniconda_path=None, batch=False):
        if miniconda_path is None:
            miniconda_path = os.path.join(tmpdir, "miniconda")
        conda_bin = os.path.join(miniconda_path, "bin")
        # We will symlink git-annex only under a dedicated directory, so it could be
        # used with default Python etc. If names changed here, possibly adjust
        # hardcoded duplicates below where we establish relative symlinks.
        self.install_miniconda(miniconda_path, batch=batch)
        subprocess.run(
            [
                os.path.join(conda_bin, "conda"),
                "install",
                "-q",
                "-c",
                "conda-forge",
                "-y",
                f"git-annex={version}" if version is not None else "git-annex",
            ],
            check=True,
        )
        if self.annex_bin != conda_bin:
            annex_bin = Path(self.annex_bin)
            annex_bin.mkdir(parents=True, exist_ok=True)
            for p in Path(conda_bin).glob("git-annex*"):
                (annex_bin / p.name).symlink_to(p.resolve())
        self.post_install()

    def install_miniconda(self, miniconda_path, batch=False):
        systype = platform.system()
        if systype == "Linux":
            miniconda_script = "Miniconda3-latest-Linux-x86_64.sh"
        elif systype == "Darwin":
            miniconda_script = "Miniconda3-latest-MacOSX-x86_64.sh"
        else:
            raise RuntimeError(f"E: Unsupported OS: {systype}")
        log.info("Downloading and running miniconda installer")
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = os.path.join(tmpdir, miniconda_script)
            download_file(
                (
                    os.environ.get("ANACONDA_URL")
                    or "https://repo.anaconda.com/miniconda/"
                )
                + miniconda_script,
                script_path,
            )
            log.info("Installing miniconda in %s", miniconda_path)
            args = ["-p", str(miniconda_path), "-s"]
            if batch:
                args.append("-b")
            subprocess.run(["bash", script_path] + args, check=True)

    def install_datalad(self, miniconda_path, batch=False):
        self.install_miniconda(miniconda_path, batch)
        subprocess.run(
            [
                os.path.join(miniconda_path, "bin", "conda"),
                "install",
                "-q",
                "-c",
                "conda-forge",
                "-y",
                "datalad",
            ],
            check=True,
        )

    def install_via_datalad_git_annex_build(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            systype = platform.system()
            if systype == "Linux":
                download_latest_git_annex("ubuntu", tmpdir)
                (debpath,) = Path(tmpdir).glob("*.deb")
                subprocess.run(["sudo", "dpkg", "-i", str(debpath)], check=True)
            elif systype == "Darwin":
                download_latest_git_annex("macos", tmpdir)
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


def download_file(url, path, headers=None):
    if headers is None:
        headers = {}
    req = Request(url, headers=headers)
    with urlopen(req) as r:
        with open(path, "wb") as fp:
            shutil.copyfileobj(r, fp)


def download_latest_git_annex(ostype, target_path: Path):
    repo = "datalad/git-annex"
    branch = "master"
    workflow = f"build-{ostype}.yaml"
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        r = subprocess.run(
            ["git", "config", "hub.oauthtoken"],
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        if r.returncode != 0 or not r.stdout.strip():
            raise RuntimeError(
                "GitHub OAuth token not set.  Set via GITHUB_TOKEN environment"
                " variable or hub.oauthtoken Git config option."
            )
        token = r.stdout.strip()

    def apicall(url):
        req = Request(url, headers={"Authorization": f"Bearer {token}"})
        with urlopen(req) as r:
            return json.load(r)

    jobs_url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs"
        f"?status=success&branch={branch}"
    )
    log.info("Getting artifacts_url from %s", jobs_url)
    jobs = apicall(jobs_url)
    try:
        artifacts_url = jobs["workflow_runs"][0]["artifacts_url"]
    except LookupError:
        log.exception("Unable to get artifacts_url")
        raise
    log.info("Getting archive download URL from %s", artifacts_url)
    artifacts = apicall(artifacts_url)
    if artifacts["total_count"] < 1:
        raise RuntimeError("No artifacts found!")
    elif artifacts["total_count"] > 1:
        raise RuntimeError("Too many artifacts found!")
    else:
        archive_download_url = artifacts["artifacts"][0]["archive_download_url"]
    log.info("Downloading artifact package from %s", archive_download_url)
    target_path.mkdir(parents=True, exist_ok=True)
    artifact_path = target_path / ".artifact.zip"
    download_file(
        archive_download_url,
        artifact_path,
        headers={"Authorization": f"Bearer {token}"},
    )
    with ZipFile(str(artifact_path)) as zipf:
        zipf.extractall(str(target_path))
    artifact_path.unlink()


if __name__ == "__main__":
    main()
