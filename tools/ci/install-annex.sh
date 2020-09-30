#!/bin/bash
#
# An ultimate helper to use to setup a CI with some git-annex installation
# Arguments:
#  First argument would be which "schema" would it be.
#  Some schemas might like additional arguments.
#
# This script
# - needs to be "source"d since some schemas would need to modify env vars
# - might use "sudo" for some operations
# - might exit with 0 if e.g. specific installation "is not needed" (e.g. devel annex == default annex)

function _show_schemes() {
  _schemes_doc=(
    "autobuild  # Linux, macOS"
    "brew  # macOS"
    "conda-forge [version]  # Linux"
    "conda-forge-last [version]  # Linux"
    "datalad-extensions-build  # Linux, macOS"
    "deb-url URL  # Linux"
    "neurodebian  # Linux"
    "neurodebian-devel  # Linux"
    "snapshot  # Linux, macOS"
  )
  for s in "${_schemes_doc[@]}"; do
    echo "    $s"
  done

}

function _usage() {
    cat >&2 <<EOF
usage: source $0 [--help] [--adjust-bashrc] [SCHEME [ARGS...]]

*Options*
  --adjust-bashrc
    If the scheme tweaks PATH, prepend a snippet to ~/.bashrc that exports that
    path.  Note: This should be positiioned before SCHEME.
  --help
    Display this help and exit.

  SCHEME
    Type of git-annex installation (default "conda-forge").

$(_show_schemes)
EOF
}

function setup_neurodebian_devel() {
  # configure
  sed -e 's,/debian ,/debian-devel ,g' /etc/apt/sources.list.d/neurodebian.sources.list | sudo tee /etc/apt/sources.list.d/neurodebian-devel.sources.list
  sudo apt-get update
}

function install_from_dmg() {
  hdiutil attach "$1"
  rsync -a /Volumes/git-annex/git-annex.app /Applications/
  hdiutil detach /Volumes/git-annex/
  _annex_bin=/Applications/git-annex.app/Contents/MacOS
  export PATH="$_annex_bin:$PATH"
}

_conda_annex_version=
scenario="conda-forge"
adjust_bashrc=
url=
while [ $# != 0 ]; do
    case "$1" in
        --adjust-bashrc)
            adjust_bashrc=1
            shift
            ;;
        --help)
            _usage
            exit 0
            ;;
        -*)
            _usage
            exit 1
            ;;
        *)
            scenario="$1"
            shift
            case "$scenario" in
                neurodebian|neurodebian-devel|autobuild|snapshot|datalad-extensions-build|brew)
                    ;;
                conda-forge|conda-forge-last)
                    if [ -n "$1" ]; then
                        _conda_annex_version="=$1"
                        shift
                    fi
                    ;;
                deb-url)
                    url="${1?deb-url scheme requires URL}"
                    shift
                    ;;
                *)
                    echo "Unknown git-annex installation scheme '$scenario'" >&2
                    echo "Known schemes:" >&2
                    _show_schemes >&2
                    exit 1
                    ;;
            esac
            if [ -n "$1" ]; then
                # There are unexpected arguments left over.
                _usage
                exit 1
            fi
            ;;
    esac
done

_this_dir=$(dirname "$0")

# Most common location of installation - /usr/bin
_annex_bin=/usr/bin

_PATH_OLD="$PATH"

# we do not want to `cd` anywhere but all temp stuff should get unique temp prefix
_TMPDIR=$(mktemp -d "${TMPDIR:-/tmp}/ga-XXXXXXX")
echo "I: top directory $_TMPDIR"

case "$scenario" in
  neurodebian)  # TODO: use nd_freeze_install for an arbitrary version specified
    # we assume neurodebian is generally configured
    sudo apt-get install git-annex-standalone
    ;;
  neurodebian-devel)
    # if debian-devel is not setup -- set it up
    apt-cache policy git-annex-standalone | grep -q '/debian-devel ' \
    || setup_neurodebian_devel
    # check versions
    # devel:
    devel_annex_version=$(apt-cache policy git-annex-standalone | grep -B1 '/debian-devel ' | awk '/ndall/{print $1;}')
    current_annex_version=$(apt-cache policy git-annex-standalone | awk '/\*\*\*/{print $2}')

    if dpkg --compare-versions "$devel_annex_version" gt "$current_annex_version"; then
        sudo apt-get install "git-annex-standalone=$devel_annex_version"
    else
        echo "I: devel version $devel_annex_version is not newer than installed $current_annex_version"
        exit 0
    fi
    ;;
  deb-url)
    (
    wget -O "$_TMPDIR/git-annex.deb" "$url"
    sudo dpkg -i "$_TMPDIR/git-annex.deb"
    )
    ;;
  autobuild|snapshot)
    case "$(uname)" in
        Linux)
            _annex_bin="$_TMPDIR/git-annex.linux"
            echo "I: downloading and extracting under $_annex_bin"
            case "$scenario" in
                autobuild)
                    _subpath=autobuild/amd64
                    ;;
                snapshot)
                    _subpath=linux/current
                    ;;
                *)
                    echo "E: internal error: scenario '$scenario' should not reach here" >&2
                    exit 1
                    ;;
            esac
            tar -C "$_TMPDIR" -xzf <(
              wget -q -O- https://downloads.kitenet.net/git-annex/$_subpath/git-annex-standalone-amd64.tar.gz
            )
            export PATH="${_annex_bin}:$PATH"
            ;;
        Darwin)
            case "$scenario" in
                autobuild)
                    _subpath=autobuild/x86_64-apple-yosemite
                    ;;
                snapshot)
                    _subpath=OSX/current/10.10_Yosemite
                    ;;
                *)
                    echo "E: internal error: scenario '$scenario' should not reach here" >&2
                    exit 1
                    ;;
            esac
            wget -q -O "$_TMPDIR/git-annex.dmg" https://downloads.kitenet.net/git-annex/$_subpath/git-annex.dmg
            install_from_dmg "$_TMPDIR"/*.dmg
            ;;
        *)
            echo "E: Unsupported OS: $(uname)"
            exit 1
            ;;
    esac
    ;;
  conda-forge|conda-forge-last)
    _miniconda_script=Miniconda3-latest-Linux-x86_64.sh
    _conda_bin="$_TMPDIR/miniconda/bin"
    # we will symlink git-annex only under a didicated directory, so it could be
    # used with default Python etc. If names changed here, possibly adjust hardcoded
    # duplicates below where we establish relative symlinks
    _annex_bin="$_TMPDIR/annex-bin"
    case "$scenario" in
      conda-forge-last)
        if hash git-annex; then
          echo "W: git annex already installed.  In this case this setup has no sense" >&2
          exit 1
        fi
        # We are interested only to get git-annex into our environment
        # So to not interfer with "system wide" Python etc, we will add miniconda at the
        # end of the path
        export PATH="$PATH:${_annex_bin}";;
      conda-forge)
        export PATH="${_annex_bin}:$PATH";;
      *)
        echo "E: internal error - $scenario is unknown"
        exit 1;;
    esac

    echo "I: downloading and running miniconda installer"
    wget -q  -O "$_TMPDIR/${_miniconda_script}" \
      "${ANACONDA_URL:-https://repo.anaconda.com/miniconda/}${_miniconda_script}"
    HOME="$_TMPDIR" bash "$_TMPDIR/${_miniconda_script}" -b -p "$_TMPDIR/miniconda"
    "${_conda_bin}/conda" install -q -c conda-forge -y "git-annex${_conda_annex_version}"

    if [[ "$_annex_bin" != "$_conda_bin" ]]; then
      mkdir -p "$_annex_bin"
      (
        cd "$_annex_bin" || exit 1
        ln -s ../miniconda/bin/git-annex* .
      )
    fi
    unset _miniconda_script
    unset _conda_bin
    unset _conda_annex_version
    ;;
  datalad-extensions-build)
    case "$(uname)" in
      Linux)
        TARGET_PATH="$_TMPDIR" "$_this_dir/download-latest-artifact"
        sudo dpkg -i "$_TMPDIR"/*.deb
        ;;
      Darwin)
        TARGET_PATH="$_TMPDIR" TARGET_ARTIFACT=git-annex-macos-dmg "$_this_dir/download-latest-artifact"
        install_from_dmg "$_TMPDIR"/*.dmg
        ;;
      *)
        echo "E: Unsupported OS: $(uname)"
        exit 1
        ;;
    esac
    ;;
  brew)
    brew install git-annex
    _annex_bin=/usr/local/bin
    ;;
  *)
    echo "E: internal error: '$scenario' should be handled above" >&2
    exit 1
esac

if [ -n "$adjust_bashrc" ]; then
    # If PATH was changed, we need to make it available to SSH commands.
    # Note: Prepending is necessary. SSH commands load .bashrc, but many
    # distributions (including Debian and Ubuntu) come with a snippet to exit
    # early in that case.
    if [ "$PATH" != "$_PATH_OLD" ]; then
        perl -pli -e 'print "PATH=\"$ENV{PATH}\"" if $. == 1' ~/.bashrc
        echo "I: Adjusted first line of ~/.bashrc:"
        head -n1 ~/.bashrc
    fi
fi

# Rudimentary test of installation and inform user about location
test -x "${_annex_bin}/git-annex"
test -x "${_annex_bin}/git-annex-shell"
echo "I: git-annex is available under '${_annex_bin}'"

unset _annex_bin
unset _show_schemes
unset _this_dir
