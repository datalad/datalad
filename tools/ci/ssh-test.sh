#!/usr/bin/env bash

echo "DEBUG: test connection ..."
ssh -v localhost exit
# don't wait for travis to timeout:
exit 1