#!/bin/bash
cd $(dirname $0)
./rationality.py > /dev/null
scp rationality.epub ikeran.org:ikeran.org/
scp rationality.mobi ikeran.org:ikeran.org/
