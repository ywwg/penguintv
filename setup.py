#!/usr/bin/env python
#this file is a catastrophe. I'm sorry.

import sys,os
from penguintv import subProcess as my_subProcess
import subprocess

try:
	from sugar.activity import bundlebuilder
	HAS_SUGAR = True
except:
	HAS_SUGAR = False
	
if HAS_SUGAR:
	try:
		print "Building OLPC version"

		sp = my_subProcess.subProcess("cp -f share/penguintv.glade.olpc share/penguintv.glade")
		if sp.read() != 0:
			print "There was an error symlinking the glade file"
			sys.exit(1)

		bundlebuilder.start("NewsReader", manifest='MANIFEST-OLPC')
	except Exception, e:
		print "problem building for OLPC:", e
		sys.exit(1)
	sys.exit(0)
	
print "Building desktop version"

sp = my_subProcess.subProcess("cp -f share/penguintv.glade.desktop share/penguintv.glade")
if sp.read() != 0:
	print "There was an error symlinking the glade file"
	sys.exit(1)

BUILD_MOZ=False

from distutils.core import setup
from distutils.extension import Extension

import locale, gettext
from penguintv.utils import GlobDirectoryWalker, _mkdir
locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

missing_something = []

try:
	import gtkmozembed
except:
	missing_something.append("Need gtkmozembed, usually provided by a package like python-gnome2-extras or gnome-python2-gtkmozembed")

try:
	import sqlite3
except:
	try:
		from pysqlite2 import dbapi2 as sqlite
	except:
		missing_something.append("Need pysqlite version 2 or higher (http://pysqlite.org/)")
	
try:
	import pycurl
except:
	missing_something.append("Need pycurl (http://pycurl.sourceforge.net/)")
	
#try:
#	import gnome
#except:
#	missing_something.append("Need gnome python bindings")
	
try:
	from xml.sax import saxutils
	test = saxutils.DefaultHandler
except:
	missing_something.append("Need python-xml")
	

code = subprocess.call(["which","msgfmt"])
if code != 0:
	missing_something.append("Need gettext")
	
if len(missing_something) > 0:
	sys.exit("\n".join(missing_something))
	
from penguintv import utils

locales = []
if "build" in sys.argv or "install" in sys.argv:
	
	for f in GlobDirectoryWalker("./po", "*.po"):	
		this_locale = os.path.basename(f)	
		this_locale = this_locale[0:this_locale.rfind('.')]
		_mkdir("./mo/"+this_locale+"/LC_MESSAGES")
		msgfmt_line = "msgfmt "+f+" -o ./mo/"+this_locale+"/LC_MESSAGES/penguintv.mo"
		print msgfmt_line
		locales.append(('share/locale/'+this_locale+'/LC_MESSAGES', ['mo/'+this_locale+'/LC_MESSAGES/penguintv.mo']))
		sp = my_subProcess.subProcess(msgfmt_line)
		if sp.read() != 0:
			print "There was an error building the MO file for locale "+this_locale
			sys.exit(1)

data_files       = [('share/penguintv',		['share/penguintv.glade','share/defaultsubs.opml','share/penguintvicon.png','share/gtkhtml.css','share/mozilla.css','share/mozilla-planet.css','share/mozilla-planet-hildon.css']),
					('share/pixmaps',		['share/penguintvicon.png']),
					('share/penguintv/pixmaps', ['share/pixmaps/ev_online.png', 'share/pixmaps/ev_offline.png'])]
data_files += locales
					
if utils.RUNNING_HILDON:
	data_files += [('share/themes/default/images/', ['share/penguintvicon.png']),
					  ('share/applications/hildon/',['penguintv-hildon.desktop'])]
	scripts = ['ptv']
else:
	data_files.append(('share/applications',	['penguintv.desktop']))
	scripts = ['PenguinTV']

setup(name = "PenguinTV", 
version = utils.VERSION,
description      = 'GNOME-compatible podcast and videoblog reader',
author           = 'Owen Williams',
author_email     = 'owen-penguintv@ywwg.com',
url              = 'http://penguintv.sourceforge.net',
license          = 'GPL',
scripts          = scripts,
data_files = data_files,
packages = ["penguintv", 
			"penguintv/ptvbittorrent", 
			"penguintv/trayicon",
			"penguintv/ajax"])

if "install" in sys.argv:
	print "checking for mozilla linking problems..."
	sp = my_subProcess.subProcess('''./postinst''')
	if sp.read() != 0:
		print sp.outdata
		print "There was an error fixing mozilla linking problems"
		sys.exit(1)
	else:
		print sp.outdata

	sp = my_subProcess.subProcess('''GCONF_CONFIG_SOURCE=$(gconftool-2 --get-default-source) gconftool-2 --makefile-install-rule share/penguintv.schema''')
	if sp.read() != 0:
		print sp.outdata
		print "There was an error installing the gconf schema"
		sys.exit(1)
	else:
		print sp.outdata
		
print ""
something_disabled = False	
	
try:
	import gconf
except:
	print "WARNING: gconf not installed or not installed correctly: Gconf support will be disabled"
	something_disabled = True
	
try:
	import pygst
	pygst.require("0.10")
	import gst	
except:
	print "WARNING: gstreamer .10 or greater not installed or not installed correctly: Built-in player will be disabled"
	something_disabled = True
	
if something_disabled:
	print """If anything above was disabled and you install that library, PenguinTV will detect it automatically
	and re-enable support.  You do not have to reinstall PenguinTV to enable support for these features"""
	
#if utils.RUNNING_HILDON:
#	sp = my_subProcess.subProcess('''maemo-select-menu-location penguintv-hildon.desktop Internet''')
#	if sp.read() != 0:
#		print sp.outdata
#		print "There was an error setting the category"
#		sys.exit(1)
	
