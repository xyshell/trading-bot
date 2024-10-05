#!/bin/bash

clear
echo "****************************************************************************************"
echo "                                         TradingBot                                     "
echo "****************************************************************************************"
echo

echo "-------------------------------------- Git Status --------------------------------------"
echo

git status

if [ -z "$1" ]; then
    echo "DONE"
    exit 0
fi

if [ "$1" == "pkg" ]; then
    echo
    echo "-------------------------------------- Packaging --------------------------------------"
    echo
    
    rm -rf build tradingbot.egg-info
    rm -f dist/*.whl
    python -m build -w
    rm -rf build tradingbot.egg-info
fi

echo "DONE"