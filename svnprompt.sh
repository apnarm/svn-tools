#!/bin/sh
#
# Displays the current working directory relative to SVN.
# Has no effect when the directory is not inside an SVN checkout.
#
# Demonstration:
#
# [vagrant@rbutcher-vm ~]$ cd checkout
# [PLAT-376]$ ls
# bin  code  config  dist  doco  html  test  tools  upgrade  wsgi
# [PLAT-376]$ cd code
# [PLAT-376/code]$
#

function prompt {

    urlparent=`grep :// .svn/entries 2>/dev/null | head -1`
    testpath=`pwd`

    while [ -e "$testpath/.svn/entries" ]
    do
        url="$urlparent"
        urlparent=`dirname "$url"`
        root=`cd $testpath; pwd`
        testpath="$root/.."
    done

    if [ "$root" == "" ]
    then
        echo "$1\$ "
    else
        current=`pwd`
        relative="${current#$root}"
        svnname=`basename "$url"`
        echo "[$svnname$relative]$ "
    fi

}

export PS1="\$(prompt \"[\u@\h \W]\")"
