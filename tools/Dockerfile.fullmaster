FROM neurodebian:latest

RUN apt-get -y update
RUN apt-get -y install eatmydata
RUN eatmydata apt-get -y install gnupg wget locales
RUN echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen
RUN locale-gen

ENV DEBIAN_FRONTEND=noninteractive
RUN eatmydata apt-get -y install --no-install-recommends git git-annex-standalone python3-pip

RUN eatmydata apt-get -y install --no-install-recommends python3-setuptools python3-wheel less rsync git-remote-gcrypt aria2 libexempi3

# just for scrapy
RUN eatmydata apt-get -y install --no-install-recommends python3-twisted

# little dance because pip cannot handle this url plus [full] in one go
RUN wget https://github.com/datalad/datalad/archive/master.zip
RUN pip3 install --system master.zip[full]
RUN rm -f master.zip

# clean up
RUN apt-get clean

RUN git config --global user.name "Docker Datalad"
RUN git config --global user.email "docker-datalad@example.com"

ENTRYPOINT ["datalad"]
