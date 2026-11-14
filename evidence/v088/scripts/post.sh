#!/bin/bash
# 대국이 끝난 뒤: 홀드아웃 3초, 저자 퍼즐·역사 국면 3초, 역사 국면 10초 (기준 vs 선택적, 두 개씩 병렬)
S=/home/claude/v087/scripts/run_suite.py; B=/home/claude/v087/unz; N=/home/claude/v087/snap/s5
cd /home/claude/v087/res
pair() { # name suite seconds filter
  python3 -I $S $B $2 $1_base.json $3 '{}' $4 > $1_base.log 2>&1 &
  python3 -I $S $N $2 $1_new.json $3 '{"selective":true}' $4 > $1_new.log 2>&1 &
  wait
}
pair hold3 suite.json 3 suite=ecm,iq4
pair s2_3 suite2.json 3 suite=li_dev,li_hol,hist
pair hist10 suite2.json 10 suite=hist
touch post.done
