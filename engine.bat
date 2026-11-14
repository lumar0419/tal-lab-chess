@echo off
rem Windows용: 체스 GUI(Arena, Cute Chess 등)에 이 파일을 엔진으로 등록하세요.
rem 'python'이 안 되면 아래 줄의 python 을 py -3 으로 바꾸세요.
python "%~dp0uci.py" %*
