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
	
try:
	import hildon
	HAS_HILDON = True
except:
	HAS_HILDON = False
	
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
elif HAS_HILDON:
	print "Building hildon version"
	sp = my_subProcess.subProcess("cp -f share/penguintv.glade.hildon share/penguintv.glade")
	if sp.read() != 0:
		print "There was an error copying the glade file"
		sys.exit(1)
else:
	print "Building desktop version"

	sp = my_subProcess.subProcess("cp -f share/penguintv.glade.desktop share/penguintv.glade")
	if sp.read() != 0:
		print "There was an error copying the glade file"
		sys.exit(1)

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
	#maybe we built gtkmozembed for maemo with build-deb.sh
	try:
		from penguintv.ptvmozembed import gtkmozembed
	except:
		print "WARNING:  gtkmozembed not found.  This is usually provided by a package like python-gnome2-extras or gnome-python2-gtkmozembed"
		print "          PenguinTV will still run without gtkmozembed, but the experience isn't as good."
		#if HAS_HILDON:
		#	missing_something.append("On Maemo, gtkmozembed is created by running ./build_maemo_deb.sh and creating a package")

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
	
try:
	import Image
except:
	missing_something.append("Need python imaging (http://www.pythonware.com/products/pil/)")
	
#try:
#	import gnome
#except:
#	missing_something.append("Need gnome python bindings")
	
#try:
#	from xml.sax import saxutils
#	test = saxutils.DefaultHandler
#except:
#	missing_something.append("Need python-xml")

#moz_lib_dir = ""
#if os.environ.has_key('MOZILLA_FIVE_HOME'):
#	moz_lib_dir = os.environ['MOZILLA_FIVE_HOME']
#else:
#	for moz in ("xulrunner-gtkmozembed", "firefox-gtkmozembed", "mozilla-gtkmozembed"):
#		sp = my_subProcess.subProcess("pkg-config --silence-errors --libs-only-L %s | sed 's/ //g'" % moz)
#		lib_dir = sp.read()
#		if lib_dir != 0:
#			lib_dir = lib_dir.replace("-L", "")
#			try:
#				os.stat(lib_dir)
#				moz_lib_dir = lib_dir
#				break
#			except:
#				pass
#				
#if moz_lib_dir == "":
#	if os.path.isfile("/usr/lib/libgtkembedmoz.so.0") and \
#	   os.path.isdir("/usr/lib/microb-engine"):
#		moz_lib_dir = "/usr/lib/microb-engine"
#
#if moz_lib_dir == "":
#	cmd = "ldd " + gtkmozembed.__file__ + "|grep libgtkembedmoz"
#	p = subprocess.Popen(cmd, shell=True, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#	retval = p.wait()
#	stderr = p.stderr.read()
#	if retval == 0:
#		line = p.stdout.read()
#		lib_dir = line[line.find("/"):line.rfind("libgtkembedmoz.so")]
#		try:
#			os.stat(lib_dir)
#			moz_lib_dir = lib_dir
#		except:
#			pass
#				
#if moz_lib_dir == "":
#	print "Couldn't locate mozilla home.  Please set MOZILLA_FIVE_HOME and run setup again"
#	sys.exit(1)
#else:
#	print "Setting default MOZILLA_FIVE_HOME to", moz_lib_dir
	
code = subprocess.call(["which","msgfmt"])
if code != 0:
	HAVE_GETTEXT = False
	print "Need gettext to generate translations -- disabling translations."
	#missing_something.append("Need gettext")
else:
	HAVE_GETTEXT = True
	
if len(missing_something) > 0:
	sys.exit("\n".join(missing_something))

try:
	os.stat("./bin")
except:
	try:
		os.mkdir("./bin")
	except:
		print "Error creating ./bin directory for script"
		sys.exit(1)
f = open("PenguinTV.in", "r")
f2 = open("./bin/PenguinTV", "w")
for line in f.readlines():
	#f2.write(line.replace("##MOZ_LIB_DIR##", moz_lib_dir))
	f2.write(line)
f2.close()
f.close()
os.chmod("./bin/PenguinTV", 0775)
	
from penguintv import utils

locales = []
if HAVE_GETTEXT:
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

data_files       = [('share/penguintv',		['share/penguintv.glade','share/defaultsubs.opml','share/penguintvicon.png','share/mozilla.css','share/gtkhtml.css','share/mozilla-planet.css','share/mozilla-planet-hildon.css']),
					('share/penguintv/glade', ['share/glade/dialogs.glade']),
					('share/pixmaps',		['share/penguintvicon.png']),
					('share/icons/hicolor/scalable/hildon', ['share/penguintvicon.png']),
					('share/icons/hicolor/64x64/hildon', ['share/pixmaps/64x64/penguintvicon.png']),
					('share/icons/hicolor/40x40/hildon', ['share/pixmaps/40x40/penguintvicon.png']),
					('share/icons/hicolor/26x26/hildon', ['share/pixmaps/26x26/penguintvicon.png']),
					('share/penguintv/pixmaps', ['share/pixmaps/ev_online.png', 'share/pixmaps/ev_offline.png', 'share/pixmaps/throbber.gif']),
					('share/dbus-1/services', ['share/penguintv.service'])]
data_files += locales
					
if utils.RUNNING_HILDON:
	data_files += [('share/applications/hildon/',['penguintv-hildon.desktop']),
					('share/icons/hicolor/scalable/hildon', ['share/penguintvicon.png']),
					('share/icons/hicolor/64x64/hildon', ['share/pixmaps/64x64/penguintvicon.png']),
					('share/icons/hicolor/40x40/hildon', ['share/pixmaps/40x40/penguintvicon.png']),
					('share/icons/hicolor/26x26/hildon', ['share/pixmaps/26x26/penguintvicon.png']),
					('share/penguintv/glade', ['share/glade/hildon.glade', 'share/glade/hildon_dialogs.glade', 
											   'share/glade/hildon_dialog_add_feed.glade','share/glade/hildon_planet.glade']),]
else:
	data_files += [('share/applications',	['penguintv.desktop']),
					('share/icons/hicolor/scalable/apps', ['share/penguintvicon.png']),
					('share/icons/hicolor/64x64/apps', ['share/pixmaps/64x64/penguintvicon.png']),
					('share/icons/hicolor/40x40/apps', ['share/pixmaps/40x40/penguintvicon.png']),
					('share/icons/hicolor/26x26/apps', ['share/pixmaps/26x26/penguintvicon.png']),
					('share/penguintv/glade', ['share/glade/desktop.glade',
											   'share/glade/standard.glade', 'share/glade/widescreen.glade', 'share/glade/dialog_add_feed.glade', 'share/glade/extra_dialogs.glade', 
											   'share/glade/planet.glade', 'share/glade/vertical.glade']),]

setup(name = "PenguinTV", 
version = utils.VERSION,
description      = 'GNOME-compatible podcast and videoblog reader',
author           = 'Owen Williams',
author_email     = 'owen-penguintv@ywwg.com',
url              = 'http://penguintv.sourceforge.net',
license          = 'GPL',
scripts          = ['bin/PenguinTV'],
data_files = data_files,
packages = ["penguintv", 
			"penguintv/ptvbittorrent", 
			"penguintv/trayicon",
			"penguintv/ajax",
			"penguintv/amazon",
			"penguintv/BeautifulSoup"])

if "install" in sys.argv:
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
	try:
		from gnome import gconf
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

if "build" in sys.argv:
	print "You can run ./bin/PenguinTV to run PenguinTV"
