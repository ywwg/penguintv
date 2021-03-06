# -*- coding: utf-8 -*-
# Written by Owen Williams
# see LICENSE for license information

import os,sys,time, pwd, os.path
import subprocess
import string
import urllib
import string
import locale
import gettext
import shutil
import logging

VERSION="4.5.1"

try:
	from sqlite3 import OperationalError as OperationalError
except:
	from pysqlite2.dbapi2 import OperationalError as OperationalError

try:
	import hildon
	logging.debug("Detected hildon environment")
	RUNNING_HILDON = True
except:
	RUNNING_HILDON = False

try:
	if RUNNING_HILDON:
		DO_GTK_CHECKS = False
	else:
		import gtk
		DO_GTK_CHECKS = True
except:
	DO_GTK_CHECKS = False



#locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

RUNNING_SUGAR = os.environ.has_key('SUGAR_PENGUINTV')

if RUNNING_SUGAR:
	#I do this in case we're running in a python environment that has lucene
	#and/or gconf but we want to pretend they aren't there
	HAS_LUCENE = False
	HAS_SEARCH = False
	HAS_XAPIAN = False
	HAS_GCONF = False
	HAS_GNOMEVFS = False
	HAS_PYXML = False
	HAS_STATUS_ICON = False
	HAS_MOZILLA = True
	HAS_WEBKIT = True
	#HAS_GSTREAMER = True
	#I'm having trouble building gst for jhbuild, so detect this
	try:
		import pygst
		pygst.require("0.10")
		import gst
		HAS_GSTREAMER = True
	except:
		HAS_GSTREAMER = False
else:
	if DO_GTK_CHECKS:
		try:
			import webkit
			HAS_WEBKIT = True
		except:
			HAS_WEBKIT = False

		#don't even bother if we have webkit, save the memory
		HAS_MOZILLA = False
		if not HAS_WEBKIT:
			try:
				import gtk
				import gtkmozembed
				HAS_MOZILLA = True
			except:
				try:
					from ptvmozembed import gtkmozembed
					logging.info("Using PenguinTV-built gtkmozembed")
					HAS_MOZILLA = True
				except:
					HAS_MOZILLA = False

		if not HAS_WEBKIT and not HAS_MOZILLA:
			try:
				import gtkhtml2
				HAS_GTKHTML = True
			except:
				logging.error("No valid html renderers found, aborting.  (Need python-webkit, or gtkmozembed, or gtkhtml2")
				sys.exit(1)



	HAS_SEARCH = False

	try:
		import xapian
		HAS_XAPIAN = True
		HAS_SEARCH = True
	except:
		HAS_XAPIAN = False
	try:
		import PyLucene
		HAS_LUCENE = True
		HAS_SEARCH = True
	except:
		HAS_LUCENE = False

	try:
		import gconf
		HAS_GCONF = True
	except:
		try:
			from gnome import gconf
			HAS_GCONF = True
		except:
			HAS_GCONF = False

	if DO_GTK_CHECKS:
		try:
			import gnomevfs
			HAS_GNOMEVFS = True
		except:
			try:
				from gnome import gnomevfs
				HAS_GNOMEVFS = True
			except:
				HAS_GNOMEVFS = False

	try:
		from xml.sax.handler import ContentHandler
		HAS_PYXML = True
	except:
		try:
			from xml.sax.saxutils import DefaultHandler
			HAS_PYXML = True
		except:
			HAS_PYXML = False

	if DO_GTK_CHECKS and not RUNNING_HILDON:
		if gtk.pygtk_version >= (2, 10, 0):
			HAS_STATUS_ICON = True
		else:
			HAS_STATUS_ICON = False

	try:
		import pynotify
		HAS_PYNOTIFY = True
	except:
		HAS_PYNOTIFY = False

	try:
		import pygst
		pygst.require("0.10")
		import gst
		HAS_GSTREAMER = True
	except:
		HAS_GSTREAMER = False

	try:
		import dbus
		HAS_DBUS = True
	except:
		HAS_DBUS = False

if RUNNING_HILDON:
	#having a status icon causes tons of problems (causes hildonn UI to crash)
	HAS_STATUS_ICON = False
	HAS_MOZILLA = False
	HAS_GNOMEVFS = False

#DEBUG
#_USE_KDE_OVERRIDE=False
# Lucene sucks, forget it
HAS_LUCENE = False
##disable while still unstable
#HAS_XAPIAN = False
if not HAS_XAPIAN:
	HAS_SEARCH = False

if HAS_XAPIAN:
	logging.info("Using Xapian search engine")
elif HAS_LUCENE:
	logging.info("Using Lucene search engine")
else:
	logging.info("xapian or lucene not found, search disabled")

# Pynotify is still broken, forget it
#HAS_PYNOTIFY = False
#HAS_PYXML = False
#HAS_STATUS_ICON = False
#HAS_GNOMEVFS = False
#HAS_MOZILLA=False

#too buggy, disable for release
ENABLE_ARTICLESYNC=True

def get_home():
	if RUNNING_SUGAR:
		import sugar.env
		return os.path.join(sugar.env.get_profile_path(), 'penguintv')
	else:
		return os.path.join(os.getenv('HOME'), ".penguintv")

def format_size(size):
	if size > 1073741824:
		return "%.2f GB" % (float(size)/1073741824)
	elif size > 1048576:
		return str(int(round(size/1048576)))+ " MB"
	elif size > 1024:
		return str(int(round(size/1024)))+" KB"
	else:
		return str(size)+" bytes"

def GetPrefix():
	if os.environ.has_key('PTV_PREFIX'):
		h, t = os.path.split(os.environ['PTV_PREFIX'])
		return h
	h, t = os.path.split(os.path.split(os.path.abspath(sys.argv[0]))[0])
	return h

_glade_prefix = None
_share_prefix = None

def get_share_prefix():
	global _share_prefix

	if _share_prefix is not None:
		return _share_prefix

	get_glade_prefix()
	return _share_prefix

def get_glade_prefix():
	global _glade_prefix
	global _share_prefix
	if _glade_prefix is not None:
		return _glade_prefix

	logging.debug("finding glade prefix")

	import utils
	for p in (os.path.join(GetPrefix(),"share","penguintv","glade"),
		  os.path.join(GetPrefix(),"share","glade"),
		  os.path.join(os.path.split(os.path.abspath(sys.argv[0]))[0],"share"),
		  os.path.join(GetPrefix(),"share","sugar","activities","ptv","share"),
		  os.path.join(os.path.split(os.path.split(utils.__file__)[0])[0],'share','glade'),
		  "/usr/share/penguintv/glade"):
		try:
			os.stat(os.path.join(p,"dialogs.glade"))
			logging.debug("glade prefix found: %s" % (p,))
			_glade_prefix = p
			_share_prefix = '/'.join(p.split('/')[0:-1])
			return _glade_prefix
		except:
			continue
	return None

def get_image_path(filename):
	for p in (get_share_prefix(),
			  os.path.join(GetPrefix(), 'share', 'pixmaps'),
			  os.path.join(GetPrefix(), 'share'), #in case the install is still in the source dirs
			  os.path.join(get_share_prefix(), 'pixmaps')):
		try:
			icon_file = os.path.join(p, filename)
			os.stat(icon_file)
			return icon_file
		except Exception, e:
			continue
		logging.error("icon not found:" + filename)
		raise e
	return icon_file

def hours(n):  #this func copyright Bram Cohen
    if n == -1:
        return '<unknown>'
    if n == 0:
        return _('complete!')
    n = long(n)
    h, r = divmod(n, 60 * 60)
    m, sec = divmod(r, 60)
    if h > 1000000:
        return '<unknown>'
    if h > 0:
        return '%d:%02d:%02d' % (h, m, sec)
    else:
        return '%d:%02d' % (m, sec)

def is_known_media(filename):
	if os.path.isdir(filename):
		for root,dirs,files in os.walk(filename):
			for f in files:
				try:
					return desktop_has_file_handler(f)
				except:
					pass
		return False

	try:
		return desktop_has_file_handler(filename)
	except:
		return False

def get_play_command_for(filename):
	known_players={
	        'audacious':'--enqueue',
	        'totem':'--enqueue',
					'xine':'--enqueue',
					'mplayer': '-enqueue',
					'banshee': '--enqueue'}

	if is_kde():
		try:
			mime_magic = kio.KMimeMagic()
			mimetype = str(mime_magic.findFileType(filename).mimeType())
			#mimetype = str(kio.KMimeType.findByPath(filename).defaultMimeType())
			service = kio.KServiceTypeProfile.preferredService(mimetype,"Application")
			if service is None: #no service, so we use kfmclient and kde should launch a helper window
				logging.info("unknown type, using kfmclient")
				return "kfmclient exec "
			full_qual_prog = str(service.exec_()).replace("%U","").strip()
		except:
			logging.info("error getting type, using kfmclient")
			return "kfmclient exec "
	else:
		return "xdg-open "
	try:
		path, program = os.path.split(full_qual_prog)
	except:
		program = full_qual_prog

	if known_players.has_key(program):
		return full_qual_prog+" "+known_players[program]
	return full_qual_prog

def get_dated_dir(t=None):
	if t is None:
		t = time.localtime()
	today = time.strftime("%Y-%m-%d", t)
	return today

#http://www.faqts.com/knowledge_base/view.phtml/aid/2682
class GlobDirectoryWalker:
    # a forward iterator that traverses a directory tree

	def __init__(self, directory, pattern="*"):
		self.stack = [directory]
		self.pattern = pattern
		self.files = []
		self.index = 0

	def __getitem__(self, index):
		import fnmatch
		while 1:
			try:
				file = self.files[self.index]
				self.index = self.index + 1
			except IndexError:
				# pop next directory from stack
				try:
					while True:
						self.directory = self.stack.pop()
						self.index = 0
						self.files = os.listdir(self.directory) #loops if we have a problem listing the directory
						break #but if it works we break
				except OSError, e:
					continue #evil... but it works
			else:
				# got a filename
				fullname = os.path.join(self.directory, file)
				if os.path.isdir(fullname) and not os.path.islink(fullname):
					self.stack.append(fullname)
				if fnmatch.fnmatch(file, self.pattern):
					return fullname
#usage:
#for file in GlobDirectoryWalker(".", "*.py"):
#    print file

def deltree(path):
#adapted and corrected from: http://aspn.activestate.com/ASPN/docs/ActivePython/2.2/PyWin32/Recursive_directory_deletes_and_special_files.html
	for file in os.listdir(path):
		file_or_dir = os.path.join(path,file)
		if os.path.isdir(file_or_dir) and not os.path.islink(file_or_dir):
			deltree(file_or_dir) #it's a directory reucursive call to function again
		else:
			os.remove(file_or_dir) #it's a file, delete it
	os.rmdir(path) #delete the directory here


#http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/82465
def _mkdir(newdir):
	"""works the way a good mkdir should :)
        - already exists, silently complete
        - regular file in the way, raise an exception
        - parent directory(ies) does not exist, make them as well
    """
	if os.path.isdir(newdir):
		pass
	elif os.path.isfile(newdir):
		raise OSError("a file with the same name as the desired " \
					  "dir, '%s', already exists." % newdir)
	else:
		head, tail = os.path.split(newdir)
		if head and not os.path.isdir(head):
			_mkdir(head)
		#print "_mkdir %s" % repr(newdir)
		if tail:
			os.mkdir(newdir)


def my_quote(s):
	"""Replaces some problematic characters with html equivalent if necessary"""
	#right now just & to &amp;, but not &amp; to &amp;amp;
	#instead of doing this with logic, just "unquote" the amps and then requote them
	s=string.replace(s,"&amp;","&")
	s=string.replace(s,"&","&amp;")
	return s

def make_pathsafe(s):
	unsafe=('<','>',':','"','/','\\','|')
	for c in unsafe:
		s=string.replace(s,c,'_')
	return s

def get_hyphen():
	if RUNNING_HILDON:
		return "--"
	else:
		return "&#8211;"

def uniquer(seq, idfun=None):
	if not seq:
		return []
	if idfun is None:
		def idfun(x): return x
	seen = {}
	result = []
	for item in seq:
		marker = idfun(item)
		# in old Python versions:
		# if seen.has_key(marker)
		# but in new ones:
		if marker in seen: continue
		seen[marker] = 1
		result.append(item)
	return result

def is_kde():
	"""Returns true if the user is running a full KDE desktop, or if it has been overridden for debug
		purposes"""
	try:
		if _USE_KDE_OVERRIDE == True:
			return True
	except:
		return False

	return os.environ.has_key('KDE_FULL_SESSION')

def desktop_has_file_handler(filename):
	"""Returns true if the desktop has a file handler for this
		filetype."""
	if is_kde():
		# If KDE can't handle the file, we'll use kfmclient exec to run the file,
		# and KDE will show a dialog asking for the program
		# to use anyway.
		return True
	else:
		if HAS_GNOMEVFS:
			# Otherwise, use GNOMEVFS to find the appropriate handler
			handler = gnomevfs.mime_get_default_application(gnomevfs.get_mime_type(urllib.quote(str(filename)))) #PA fix #Nerdist fix, urllib prefers strings over unicode
			if handler is not None:
				return True
			return False
		else: #FIXME: olpc doesn't know what the fuck... pretend yes and let error get caught later
			return True

def is_file_media(filename):
	"""Returns true if this is a media file (audio or video) and false if it is any other type of file"""
	if is_kde():
		mime_magic = kio.KMimeMagic()
		mimetype = str(mime_magic.findFileType(filename).mimeType())
	elif HAS_GNOMEVFS:
		mimetype = gnomevfs.get_mime_type(urllib.quote(filename))
	else:
		return False
	valid_mimes=['video','audio','mp4','realmedia','m4v','mov']
	for mime in valid_mimes:
		if mime in mimetype:
			return True
	return False

#http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/440481
#class MLStripper(HTMLParser.HTMLParser):
#	def __init__(self):
#		self.reset()
#		self.fed = []
#	def handle_data(self, d):
#		self.fed.append(d)
#	def get_fed_data(self):
#		return ''.join(self.fed)



#usage:
#def strip(s):
#    """ Strip illegal HTML tags from string s """
#    parser = StrippingParser()
#    parser.feed(s)
#    parser.close()
#    parser.cleanup()
#    return parser.result

##http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/457667
##I know this is very bad, but damn if it doesn't work
#import __main__
#
#class SuperGlobal:
#
#    def __getattr__(self, name):
#        return __main__.__dict__.get(name, None)
#
#    def __setattr__(self, name, value):
#        __main__.__dict__[name] = value
#
#    def __delattr__(self, name):
#        if __main__.__dict__.has_key(name):
#            del  __main__.__dict__[name]

#thanks http://www.peterbe.com/plog/html-entity-fixer
#from htmlentitydefs import entitydefs
#import re
#_unicode = re.compile('^&#(.*);$')
#_entities_pared = {}
#for entity in entitydefs:
#	if len(_unicode.findall(entitydefs[entity]))==0:
#		try:
#			_entities_pared[entity]=unicode(entitydefs[entity]) #this weeds out some more naughty characters
#		except:
#			pass

_my_entities = {'amp': u'&', 'lt': u'<', 'gt': u'>', 'quot': u'"'}
def html_entity_unfixer(text):
	"""replace html-encoded html with regular html.  I don't use htmlentitydefs because it causes utf problems"""
	for entity in _my_entities.keys():
		text = text.replace("&"+entity+";", _my_entities[entity])
	return text

#def lucene_escape(text):
#	#+ - & | ! ( ) { } [ ] ^ " ~ * ? : \\
#	escape_chars="""+-&|!(){}[]^"~*?:\\"""
#	text = text.replace(

def get_disk_free(f="/"):

	"""returns free disk space in bytes for
	   the disk that contains file f, defaulting to root.
	   Returns 0 on error"""

	stats = os.statvfs(f) #if this fails it will raise exactly the right error

	return stats.f_bsize * stats.f_bavail


def get_disk_total(f="/"):

	"""returns total disk space in bytes for
	   the disk that contains file f, defaulting to root.
	   Returns 0 on error"""

	stats = os.statvfs(f) #if this fails it will raise exactly the right error

	return stats.f_bsize * stats.f_blocks

def init_gtkmozembed():
	"""We need to set up mozilla with set_comp_path in order for it not to
	crash.  The fun part is not hardcoding that path since we have no way
	of getting it from the module itself.  good luck with this"""

	logging.info("initializing mozilla")
	assert HAS_MOZILLA

	#new, easy behavior
	if os.path.exists('/usr/lib/xulrunner-1.9'):
		gtkmozembed.set_comp_path('/usr/lib/xulrunner-1.9')
		return

	#old, disgusting behavior
	if not os.environ.has_key('MOZILLA_FIVE_HOME'):
		return False
	moz_path = os.environ['MOZILLA_FIVE_HOME']
	cmd = "ldd " + moz_path + '/libxpcom.so  | grep "not found"'
	p = subprocess.Popen(cmd, shell=True, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	retval = p.wait()
	stderr = p.stderr.read()
	stdout = p.stdout.read()
	if len(stderr) > 1 or len(stdout) > 0:
		print """***ERROR initializing mozilla.  PenguinTV may crash shortly.
You may need to export LD_LIBRARY_PATH=$MOZILLA_FIVE_HOME
"""
		return False

	_init_mozilla_proxy()

	logging.info("initializing mozilla in " + str(moz_path))
	gtkmozembed.set_comp_path(moz_path)

	return True

def _init_mozilla_proxy():
	if RUNNING_SUGAR:
		# don't even try
		return

	home = os.path.join(os.getenv('HOME'), ".penguintv")
	_mkdir(os.path.join(home, "gecko"))

	sys_proxy = {}
	sys_proxy['host'] = ""
	sys_proxy['port'] = 0
	sys_proxy['type'] = 0
	sys_proxy['autoconfig_url'] = ""
	# get system proxy prefs if any
	#if True:
	#	sys_proxy['host'] = "6.2.7.2"
	#	sys_proxy['port'] = 8080
	#	sys_proxy['type'] = 1
	#	sys_proxy['autoconfig_url'] = "testing"
	if HAS_GCONF:
		# get gnome http proxy preferences
		conf = gconf.client_get_default()
		use_proxy = conf.get_bool("/system/http_proxy/use_http_proxy")
		if use_proxy:
			sys_proxy['host'] = conf.get_string("/system/http_proxy/host")
			sys_proxy['port'] = conf.get_int("/system/http_proxy/port")
			sys_proxy['type'] = 1
	else:
		# get most-recently modified moz prefs.
		prefs_files = []
		for f in GlobDirectoryWalker(os.path.join(os.getenv('HOME'), ".mozilla"), "prefs.js"):
			prefs_files.append((os.stat(f).st_mtime, f))
		if len(prefs_files) != 0:
			prefs_files.sort()
			prefs_files.reverse()
			source_prefs = prefs_files[0][1]
			sys_proxy = _get_proxy_prefs(source_prefs)

	# check against current settings
	try:
		os.stat(os.path.join(home, "gecko", "prefs.js"))
		cur_proxy = _get_proxy_prefs(os.path.join(home, "gecko", "prefs.js"))
		if sys_proxy == cur_proxy:
			logging.info("gecko proxy settings up to date")
			return
	except:
		pass

	try:
		logging.info("updating gecko proxy settings")
		f = open(os.path.join(home, "gecko", "prefs.js"), "w")
		f.write("""# Mozilla User Preferences

	/* Do not edit this file.
	 *
	 * If you make changes to this file while the application is running,
	 * the changes will be overwritten when the application exits.
	 *
	 * To make a manual change to preferences, you can visit the URL about:config
	 * For more information, see http://www.mozilla.org/unix/customizing.html#prefs
	 */

	user_pref("network.proxy.type", %d);
	user_pref("network.proxy.http", "%s");
	user_pref("network.proxy.http_port", %d);
	user_pref("network.proxy.autoconfig_url", "%s");
	""" % (sys_proxy['type'], sys_proxy['host'], sys_proxy['port'], sys_proxy['autoconfig_url']))
		f.close()
	except:
		logging.warning("couldn't create prefs.js, proxy server connections may not work")

def _get_proxy_prefs(filename):
	def isNumber(x):
		try:
			float(x)
			return True
		except:
			return False

	proxy = {}
	proxy['host'] = ""
	proxy['port'] = 0
	proxy['type'] = 0
	proxy['autoconfig_url'] = ""

	try:
		f = open(filename, "r")
	except:
		logging.warning("couldn't open gecko preferences file " + filename)
		return proxy

	for line in f.readlines():
		if 'network' in line:
			if '"network.proxy.http"' in line:
				proxy['host'] = line.split('"')[3]
			elif '"network.proxy.autoconfig_url"' in line:
				proxy['autoconfig_url'] = line.split('"')[3]
			elif '"network.proxy.http_port"' in line:
				proxy['port'] = int("".join([c for c in line.split('"')[2] if isNumber(c)]))
			elif '"network.proxy.type"' in line:
				proxy['type'] = int("".join([c for c in line.split('"')[2] if isNumber(c)]))

	f.close()
	return proxy

def get_pynotify_ok():
	if not HAS_PYNOTIFY:
		#print "pynotify not found, using fallback notifications"
		return False

	# first get what package config reports

	cmd = "pkg-config notify-python --modversion"
	p = subprocess.Popen(cmd, shell=True, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	retval = p.wait()
	stderr = p.stderr.read()
	if len(stderr) > 1 or retval != 0:
		logging.warning("trouble getting notify-python version from pkg-config, using fallback notifications")
		return False
	major,minor,rev = p.stdout.read().split('.')

	major = int(major)
	minor = int(minor)
	rev = int(rev)

	# if it's bad, return false
	if minor < 1:
		logging.info("pynotify too old, using fallback notifications")
		return False
	if minor == 1 and rev == 0:
		logging.info("pynotify too old, using fallback notifications")
		return False

#	# if it's good, check to see it's not lying about prefix
#	cmd = "pkg-config notify-python --variable=prefix"
#	p = subprocess.Popen(cmd, shell=True, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#	retval = p.wait()
#	stderr = p.stderr.read()
#	if len(stderr) > 1 or retval != 0:
#		logging.info("trouble getting notify-python prefix from pkg-config, using fallback notifications")
#		return False
#	pkgconfig_prefix = p.stdout.read().strip()
#
#	try:
#		dirname = os.path.split(pynotify.__file__)[0]
#		f = open(os.path.join(dirname, "_pynotify.la"))
#	except:
#		logging.info("trouble opening _pynotify.la, using fallback notifications")
#		return False
#
#	libdir_line = ""
#
#	for line in f.readlines():
#		if line[0:6] == "libdir":
#			libdir_line = line.split("=")[1][1:-1]
#			break
#	f.close()
#
#	libdir_line = libdir_line.strip()
#
#	if len(libdir_line) == 0:
#		logging.info("trouble reading _pynotify.la, using fallback notifications")
#		return False
#
#	if pkgconfig_prefix not in libdir_line:
#		logging.info("pkgconfig does not agree with _pynotify.la, using fallback notifications")
#		return False
#
#	logging.info("Using pynotify notifications")
	return True

def db_except(default_retval=None):
	def annotate(func):
		def _exec_cb(self, *args, **kwargs):
			try:
				return func(self, *args, **kwargs)
			except OperationalError:
				logging.debug("DB Exception")
				self._handle_db_exception()
				return _exec_cb(self, *args, **kwargs)
		return _exec_cb
	return annotate

if is_kde():
	import kio

def _pickle_method(method):
  func_name = method.im_func.__name__
  obj = method.im_self
  cls = method.im_class
  return _unpickle_method, (func_name, obj, cls)

def _unpickle_method(func_name, obj, cls):
  for cls in cls.mro():
    try:
      func = cls.__dict__[func_name]
    except KeyError:
      pass
    else:
      break
  return func.__get__(obj, cls)

import copy_reg
import types
copy_reg.pickle(types.MethodType, _pickle_method, _unpickle_method)
