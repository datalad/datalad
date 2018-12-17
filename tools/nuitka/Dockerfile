FROM neurodebian:buster

MAINTAINER DataLad Team <team@datalad.org>

ARG DEBIAN_FRONTEND=noninteractive
# Update packages and install the minimal set of tools
RUN sed -e  's,^deb ,deb-src ,g' /etc/apt/sources.list > /etc/apt/sources.list.d/sources.list
RUN apt-get update && \
    apt-get install -y eatmydata python-pip vim less git && \
    eatmydata apt-get install -y datalad nuitka && dpkg --purge datalad nuitka && \
    eatmydata apt-get build-dep -y datalad nuitka && \
    rm -rf /var/lib/apt/*

WORKDIR /root

# Install nuitka from git, we need bleeding edge atm
RUN git clone http://git.nuitka.net/Nuitka.git nuitka && \
    cd nuitka && \
    git checkout factory && \
    pip install -e .

# Prepare sources for datalad
RUN  git clone git://github.com/datalad/datalad && \
     cd datalad && \
     git remote add gh-yarikoptic git://github.com/yarikoptic/datalad && \
     git fetch gh-yarikoptic && \
     git checkout enh-nuitka

WORKDIR /root/datalad
# ATM pip freaks out with obnoxious message 
#  of parse error at "'__placeh'". So we better upgrade pip while at it
#  see https://github.com/pypa/pip/issues/3659
# RUN pip install -U pip --force-reinstall
# now we should be able to install datalad
RUN pip install -e '.[full]'

# Actually build
RUN tools/nuitka/build_nuitka

# TODO: test the generated binary tarball within another clean docker env

CMD ["/bin/bash"]
