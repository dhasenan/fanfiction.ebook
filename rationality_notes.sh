#!/bin/bash
SAVE_DIR=$HOME/.books/methods_of_rationality/notes/
mkdir -p "$SAVE_DIR"
cd "$SAVE_DIR"

PREVIOUS=$(ls | sort | tail -n 1)
CURRENT=$(date "+%y-%m-%d")
if [ -f "$CURRENT" ]; then
	echo "Already downloaded for today"
	exit
fi
wget http://www.fanfiction.net/u/2269863/Less_Wrong -O "$CURRENT"

if [[ -n "$PREVIOUS" ]]; then
	# see if the old one's different
	if diff -q "$PREVIOUS" "$CURRENT"; then
		# diff f1 f1 is 'true'; diff f1 f2 is 'false'
		echo "$CURRENT is the same as $PREVIOUS; deleting $CURRENT"
		rm $CURRENT
	else
		echo "$CURRENT is not the same as $PREVIOUS; leaving $CURRENT"
	fi
else
	echo "No previous file; keeping $CURRENT"
fi
