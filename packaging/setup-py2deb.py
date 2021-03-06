#!/usr/bin/env python2.5

# this file is for building a maemo deb file ONLY

import glob
import os, os.path
import sys
import tarfile
import shutil
import subprocess
from subprocess import Popen, PIPE, STDOUT

#import packaging.py2deb as py2deb
import py2deb

__modname__ = "penguintv"
__version__ = "3.9.4"
__build__ = "2" # Result is "0.5.8-1"

PREFIX="/usr/"

changelog="".join(open("ChangeLog","r").readlines())

print "Building hildon version"
cmd = "cp -f share/penguintv.glade.hildon share/penguintv.glade"
p = subprocess.Popen(cmd, shell=True, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
retval = p.wait()
stderr = p.stderr.read()
if len(stderr) > 1 or retval > 0:
	print "There was an error copying the glade file?"
	sys.exit(1)

p=py2deb.Py2deb(__modname__)
p.description="A full-featured RSS reader with built-in podcast support"
p.author="Owen Williams"
p.mail="owen-maemo@ywwg.com"
p.depends = "python2.5, python2.5-pycurl, python2.5-xml, gconf2, python2.5-gnome, python2.5-gobject, python2.5-gtk2, python2.5-gtkhtml, python2.5-gstreamer, python2.5-imaging"
p.section="user/network"
p.arch="any"
p.urgency="low"
p.distribution="diablo"
p.repository="extras-devel"
p.postinst = "packaging/postinst"
p.build_depends = "debhelper (>= 5), python2.5, python2.5-dev, python2.5-imaging, python2.5-numeric, gnupg, python2.5-gstreamer, libosso-gnomevfs2-dev, libgtkmozembed-dev, python2.5-gtk2-dev, libgtk2.0-dev, python2.5-setuptools"

def pipedlist(glob_arg):
	glob_list = glob.glob(glob_arg)
	glob_list = [f for f in glob_list if os.path.isfile(f)]
	return ["%s|%s" % (l[0], l[1]) for l in zip(glob_list, [os.path.split(f)[-1] for f in glob_list])]

p[PREFIX + "lib/python2.5/site-packages/penguintv"] = pipedlist('penguintv/*.py')
p[PREFIX + "lib/python2.5/site-packages/penguintv/ptvbittorrent"] = pipedlist('penguintv/ptvbittorrent/*.py')
p[PREFIX + "lib/python2.5/site-packages/penguintv/trayicon"] = pipedlist('penguintv/trayicon/*.py')
p[PREFIX + "lib/python2.5/site-packages/penguintv/ajax"] = pipedlist('penguintv/ajax/*.py')
p[PREFIX + "lib/python2.5/site-packages/penguintv/amazon"] = pipedlist('penguintv/amazon/*.py')
p[PREFIX + "lib/python2.5/site-packages/penguintv/ptvmozembed"] = ["penguintv/ptvmozembed/__init__.py|__init__.py"]
p[PREFIX + "lib/python2.5/site-packages/penguintv/BeautifulSoup"] = pipedlist('penguintv/BeautifulSoup/*.py')
p[PREFIX + "bin"] = ["bin/PenguinTV|PenguinTV"]
p[PREFIX + 'share/applications/hildon'] = ['penguintv-hildon.desktop']
p[PREFIX + 'share/dbus-1/services'] = ['share/penguintv.service|penguintv.service']
p[PREFIX + 'share/penguintv/pixmaps'] = ['share/pixmaps/throbber.gif|throbber.gif']
p[PREFIX + 'share/penguintv'] = ['share/defaultsubs.opml|defaultsubs.opml',
								 'share/penguintvicon.png|penguintvicon.png',
								 'share/mozilla-planet-hildon.css|mozilla-planet-hildon.css',
								 'share/gtkhtml.css|gtkhtml.css']
p[PREFIX + 'share/penguintv/glade'] = pipedlist('share/glade/hildon*.glade') + ['share/glade/dialogs.glade|dialogs.glade']
p[PREFIX + 'share/icons/hicolor/scalable/hildon'] = ["share/penguintvicon.png|penguintvicon.png"]
p[PREFIX + 'share/icons/hicolor/64x64/hildon'] = ["share/pixmaps/64x64/penguintvicon.png|penguintvicon.png"]
p[PREFIX + 'share/icons/hicolor/40x40/hildon'] = ["share/pixmaps/40x40/penguintvicon.png|penguintvicon.png"]
p[PREFIX + 'share/icons/hicolor/26x26/hildon'] = ["share/pixmaps/26x26/penguintvicon.png|penguintvicon.png"]

print p
print p.generate(__version__,__build__,tar=True,dsc=True,changes=True,build=False,src=True,changelog=changelog) #changelog=changelog

print "Here begins the build of the .deb file"
builddir = os.path.join("deb-build", "%s-%s" % (__modname__, __version__))
try:
	shutil.rmtree(builddir)
except:
	pass

os.makedirs(builddir)

for f in glob.glob("deb-build/%s_%s-%s*" % (__modname__, __version__, __build__)):
	print "removing previously-build %s" % f
	os.remove(f)

tarball = tarfile.open("%s_%s-%s.tar.gz" % (__modname__, __version__, __build__))
tarball.extractall(builddir)
