#!/usr/bin/env python2.5

# this file is for building a maemo deb file ONLY

import glob
import os, os.path
import sys
import tarfile
import shutil
import subprocess
from subprocess import Popen, PIPE, STDOUT

import packaging.py2deb as py2deb

__modname__ = "penguintv"
__version__ = "3.7"
__build__ = "1" # Result is "0.5.8-1"

PREFIX="/usr/"

#changelog="".join(open("CHANGELOG","r").readlines())

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
p.depends = "python2.5, python2.5-pycurl, python2.5-xml, gconf2, python2.5-gnome, python2.5-gobject, python2.5-gtk2, python2.5-gstreamer, python2.5-gnome-extras, python2.5-imaging"
p.section="user/communication"
p.arch="any"
p.urgency="low"
p.distribution="diablo"
p.repository="extras-devel"
p.postinst = "packaging/postinst"
#p.changelog=changelog

def pipedlist(glob_arg):
	glob_list = glob.glob(glob_arg)
	glob_list = [f for f in glob_list if os.path.isfile(f)]
	return ["%s|%s" % (l[0], l[1]) for l in zip(glob_list, [os.path.split(f)[-1] for f in glob_list])]

p[PREFIX + "lib/python2.5/site-packages/penguintv"] = pipedlist('penguintv/*.py')
p[PREFIX + "lib/python2.5/site-packages/penguintv/ptvbittorrent"] = pipedlist('penguintv/ptvbittorrent/*.py')
p[PREFIX + "lib/python2.5/site-packages/penguintv/trayicon"] = pipedlist('penguintv/trayicon/*.py')
p[PREFIX + "lib/python2.5/site-packages/penguintv/ajax"] = pipedlist('penguintv/ajax/*.py')
p[PREFIX + "lib/python2.5/site-packages/penguintv/amazon"] = pipedlist('penguintv/amazon/*.py')
p[PREFIX + "bin"] = ["bin/PenguinTV|PenguinTV"]
p[PREFIX + 'share/applications/hildon'] = ['penguintv-hildon.desktop']
p[PREFIX + 'share/dbus-1/services'] = ['share/penguintv.service|penguintv.service']
p[PREFIX + 'share/pixmaps'] = ['share/pixmaps/ev_online.png|ev_online.png', 
							   'share/pixmaps/ev_offline.png|ev_offline.png', 
							   'share/pixmaps/throbber.gif|throbber.gif']
p[PREFIX + 'share/penguintv'] = ['share/penguintv.glade|penguintv.glade', 
								 'share/defaultsubs.opml|defaultsubs.opml',
								 'share/penguintvicon.png|penguintvicon.png',
								 'share/mozilla.css|mozilla.css',
								 'share/mozilla-planet.css|mozilla-planet.css',
								 'share/mozilla-planet-hildon.css|mozilla-planet-hildon.css']
p[PREFIX + 'share/icons/hicolor/scalable/hildon'] = ["share/penguintvicon.png|penguintvicon.png"]
p[PREFIX + 'share/icons/hicolor/64x64/hildon'] = ["share/pixmaps/64x64/penguintvicon.png|penguintvicon.png"]
p[PREFIX + 'share/icons/hicolor/40x40/hildon'] = ["share/pixmaps/40x40/penguintvicon.png|penguintvicon.png"]
p[PREFIX + 'share/icons/hicolor/26x26/hildon'] = ["share/pixmaps/26x26/penguintvicon.png|penguintvicon.png"]

print p
print p.generate(__version__,__build__,tar=True,dsc=True,changes=True,build=False,src=True)

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
