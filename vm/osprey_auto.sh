#!/bin/bash

# Sleep to allow startup to finish
sleep 30


while true
do
	# Run Osprey
	cd /usr/bin/osprey/osprey/
  python3 osprey.py
  if [ $? -eq 0 ]
  then
    echo "Osprey ran successfully."
  else
    echo "Osprey error" >&2
    exit
  fi

done


