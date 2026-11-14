#!/bin/bash
# batch.sh <engine> <seconds> <filter> name=json name=json ...  (두 개씩 병렬)
E=$1; T=$2; F=$3; shift 3
S=/home/claude/v087/scripts/run_suite.py
cd /home/claude/v087/res
while [ $# -gt 0 ]; do
  n1=${1%%=*}; o1=${1#*=}; shift
  python3 -I $S $E suite.json $n1.json $T "$o1" $F > $n1.log 2>&1 &
  if [ $# -gt 0 ]; then n2=${1%%=*}; o2=${1#*=}; shift; python3 -I $S $E suite.json $n2.json $T "$o2" $F > $n2.log 2>&1 & fi
  wait
done
touch /home/claude/v087/res/batch.done
