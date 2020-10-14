#!/bin/bash

# Needed to be ran while in the cpython git source base
#   http://github.com/python/cpython
# and it will create a directory with "-builds" suffix added,
# and virtualenv under datalad's venvs/build-$ver created
# unless another location is specified with VIRTUALENV_PATH
# (remove it first if you want to reinit it).
#
# Bisection command and args could be provided, so overall e.g.
# to find where fix was implemented:
# (git)lena:~/proj/misc/cpython[tags/v3.8.0a1^0]git
# $> git bisect start
# $> git bisect new v3.8.0
# $> git bisect old v3.8.0a1
# Bisecting: 1017 revisions left to test after this (roughly 10 steps)
# [3880f263d2994fb1eba25835dddccb0cf696fdf0] bpo-36933: Remove sys.set_coroutine_wrapper (marked for removal in 3.8) (GH-13577)
# $> git bisect run ~/proj/datalad/datalad-master/tools/ci/bisect-python.sh python ~/proj/datalad/datalad-master/datalad/support/tests/test_parallel.py
# $> git bisect run ~/proj/datalad/datalad-master/tools/ci/bisect-python.sh bash -c 'python3 ~/proj/datalad/datalad-master/datalad/support/tests/test_parallel.py || exit 1'

set -eu
export PS4='> '

_cpython_src=$(pwd)
_datalad_src=$(dirname "$0")
_datalad_src=$(readlink -f "${_datalad_src}/../..")

echo "Python source: $_cpython_src   DataLad: $_datalad_src"
if [ -e "${_cpython_src}/configure" ] && [ -e "${_datalad_src}/setup.py" ]; then
  _ver=$(git -C "$_cpython_src" describe)

  _destdir="${_cpython_src}-builds/${_ver}"
  _python="${_destdir}/usr/local/bin/python3"

  if [ ! -e "${_python}" ]; then
  (
      cd "${_cpython_src}"
      chronic git clean -dfx
      PATH=/usr/lib/ccache:$PATH chronic ./configure || exit 125
      PATH=/usr/lib/ccache:$PATH chronic make -j8 install DESTDIR="${_destdir}" || exit 125
  )
  else
    echo "SKIP: $_python is already there, skipping building python"
  fi

  # create virtualenv
  _venv_d="${VIRTUALENV_PATH:-${_datalad_src}/venvs/build-${_ver}}";
  if [ ! -e "${_venv_d}" ]; then
    chronic virtualenv --python="${_python}" "${_venv_d}" || exit 125

    source "${_venv_d}/bin/activate"
    chronic pip3 install -e "${_datalad_src}/.[devel]" || exit 125
  else
    source "${_venv_d}/bin/activate"
    echo "SKIP: $_venv_d already there, skipping virtualenv + pip call"
  fi

  echo "All ready:
  build:   $_destdir
  venv:    ${_venv_d}
  source:  source \"${_venv_d}/bin/activate\"
  python:  $(which python3)
  ver:     $(python3 --version)
  datalad: $(git -C "${_datalad_src}" describe)
"
  if [ "$#" != 0 ]; then
    echo "INFO: running bisection command $*"
    bash -c "$*"
  else
    echo "INFO: no bisection command given"
  fi
else
  echo "ERROR: no needed sources were found" >&2
  exit 125
fi