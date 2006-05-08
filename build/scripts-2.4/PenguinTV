#!/usr/bin/python
#
# Copyright (c) 2005 Owen Williams
# You may use and distribute this software under the terms of the
# GNU General Public License, version 2 or later
#

import signal
import os
import sys
import time
import pygtk
import gettext
pygtk.require("2.0")
import gtk

gettext.install('penguintv', '/usr/share/locale', unicode=1)
_=gettext.gettext

def find_penguintv_lib():
    if os.environ.has_key("PENGUINTV_LIB"):
        return os.environ["PENGUINTV_LIB"]
    for d in sys.path:
        sd = os.path.join(d, 'penguintv')
        if os.path.isdir(sd):
            return sd
    print sys.argv[0]
    h, t = os.path.split(os.path.split(os.path.abspath(sys.argv[0]))[0])
    if t == 'bin':
        libdir = os.path.join(h, 'lib')
        fp = os.path.join(libdir, 'penguintv')
        if os.path.isdir(fp):
            return libdir
    raise "FileNotFoundError", "couldn't find penguintv library dir"

sys.path.insert(0, find_penguintv_lib())

import penguintv
import utils

penguintv.main()
