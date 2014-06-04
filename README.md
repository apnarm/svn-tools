SVN Tools
=========

Some of our tools for working with SVN.

diff.cgi
--------

A CGI script that shows SVN diffs in HTML format. It can show local changes,
or differences between trunk and a specified branch.

svnprompt.sh
------------

Displays the current working directory relative to SVN.
Has no effect when the directory is not inside an SVN checkout.

Demonstration:

    [vagrant@rbutcher-vm ~]$ cd checkout
    [PLAT-376]$ ls
    bin  code  config  dist  doco  html  test  tools  upgrade  wsgi
    [PLAT-376]$ cd code
    [PLAT-376/code]$
