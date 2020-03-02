#!/bin/bash

set -eu
date
#http_proxy= DATALAD_TESTS_SSH=1 DATALAD_LOG_LEVEL=1 DATALAD_LOG_OUTPUTS=1 python -m nose -s -v datalad/distribution/tests/test_publish.py:test_publish_depends
http_proxy= DATALAD_TESTS_SSH=1 DATALAD_LOG_LEVEL=1 DATALAD_LOG_OUTPUTS=1 python -m nose -s -v ../datalad/distribution/tests/test_publish.py:test_publish_depends >| /tmp/nose-log.log 2>&1 & \
while ! grep enableremote.*target2 < /tmp/nose-log.log; do sleep 1; done; echo "GOT THERE! "; date; ps auxw -H; 

echo "Waiting"
date
wait

