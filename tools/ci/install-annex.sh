#!/bin/bash
#
# An ultimate helper to use to setup a CI with some git-annex installation
# Arguments:
#  First argument would be which "schema" would it be.
#  Some schemas might like additional arguments (ATM annotated in comments for cases)
#
# This script
# - needs to be "source"d since some schemas would need to modify env vars
# - might use "sudo" for some operations
# - might exit with 0 if e.g. specific installation "is not needed" (e.g. devel annex == default annex)

function setup_neurodebian_devel() {
  # configure
  sed -e 's,/debian ,/debian-devel ,g' /etc/apt/sources.list.d/neurodebian.sources.list | sudo tee /etc/apt/sources.list.d/neurodebian-devel.sources.list
  sudo apt-get update
}

scenario="${1:-conda-forge}"

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
  deb-url)  # expects: URL
    (
    shift
    url="$1"  # expects URL
    wget -O "$_TMPDIR/git-annex.deb" "$url"
    sudo dpkg -i "$_TMPDIR/git-annex.deb"
    )
    ;;
  snapshot)
    _ANNEXDIR="$_TMPDIR/git-annex.linux"
    echo "I: downloading and extracting under $_ANNEXDIR"
    tar -C "$_TMPDIR" -xzf <(
      wget -q -O- https://downloads.kitenet.net/git-annex/linux/current/git-annex-standalone-amd64.tar.gz
    )
    export PATH="$_ANNEXDIR:$PATH"
    unset _ANNEXDIR
    ;;
  conda-forge|conda-forge-last)  # optional: version
    _miniconda_script=Miniconda3-latest-Linux-x86_64.sh
    shift
    _conda_annex_version=${1:+=}${1:-}  # will include = prefix is specified
    case "$scenario" in
      conda-forge-last)
        if hash git-annex; then
          echo "W: git annex already installed.  In this case this setup has no sense" >&2
          exit 1
        fi
        # We are interested only to get git-annex into our environment
        # So to not interfer with "system wide" Python etc, we will add miniconda at the
        # end of the path
        export PATH="$PATH:$_TMPDIR/miniconda/bin";;
      conda-forge)
        export PATH="$_TMPDIR/miniconda/bin:$PATH";;
      *)
        echo "E: internal error - $scenario is unknown"
        exit 1;;
    esac

    wget -O "$_TMPDIR/${_miniconda_script}" \
      "${ANACONDA_URL:-https://repo.anaconda.com/miniconda/}${_miniconda_script}"
    HOME="$_TMPDIR" bash "$_TMPDIR/${_miniconda_script}" -b -p "$_TMPDIR/miniconda"
    unset _miniconda_script
    "$_TMPDIR/miniconda/bin/conda" install -c conda-forge -y git-annex${_conda_annex_version}
    ;;
  *)
    echo "Unknown git-annex installation scheme $scenario"
esac
