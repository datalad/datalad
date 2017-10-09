FROM neurodebian:jessie

MAINTAINER DataLad Team <team@datalad.org>

ARG DEBIAN_FRONTEND=noninteractive
# Update packages and install the minimal set of tools
RUN apt-get update && \
    apt-get install -y eatmydata
# Now install all needed goodness for its depends and purge  so we could work from out of git
RUN eatmydata apt-get install -y datalad nuitka && dpkg --purge datalad nuitka
# Helper tools
RUN eatmydata apt-get install -y python-pip vim less git

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
RUN pip install -U pip --force-reinstall
# now we should be able to install datalad
RUN pip install -e '.[full]'

# Actually build
RUN tools/nuitka/build_nuitka

# TODO: test the generated binary tarball within another clean docker env

CMD ["/bin/bash"]
