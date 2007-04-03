# Written by Owen Williams
# see LICENSE for license information
import os,sys,time, pwd, os.path
import subprocess
import string
import fnmatch
import urllib
import HTMLParser
import string
import locale
import gettext

import gtk

from subprocess import Popen, PIPE, STDOUT

locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

RUNNING_SUGAR = os.environ.has_key('SUGAR_PENGUINTV')

if RUNNING_SUGAR:
	#I do this in case we're running in a python environment that has lucene
	#and/or gconf but we want to pretend they aren't there
	HAS_LUCENE = False
	HAS_GCONF = False
	HAS_GNOMEVFS = False
	HAS_PYXML = False
	HAS_STATUS_ICON = False
	HAS_MOZILLA = True
	HAS_GSTREAMER = True
else:
	try:
		import gtkmozembed
		HAS_MOZILLA = True
	except:
		HAS_MOZILLA = False

	try:
		import PyLucene
		HAS_LUCENE = True
	except:
		HAS_LUCENE = False
		
	try:
		import gconf
		HAS_GCONF = True
	except:
		HAS_GCONF = False
		
	try:
		import gnomevfs
		HAS_GNOMEVFS = True
	except:
		HAS_GNOMEVFS = False
		
	try:
		from xml.sax.saxutils import DefaultHandler
		HAS_PYXML = True
	except:
		HAS_PYXML = False
		
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
	
VERSION="2.89"
#DEBUG
#_USE_KDE_OVERRIDE=False
HAS_LUCENE = False
#HAS_PYXML = False
#HAS_STATUS_ICON = False
#HAS_GNOMEVFS = False
#HAS_MOZILLA=False

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
	h, t = os.path.split(os.path.split(os.path.abspath(sys.argv[0]))[0])
	return h
	
def get_glade_prefix():
	import utils
	for p in (os.path.join(GetPrefix(),"share","penguintv"),
		  os.path.join(GetPrefix(),"share"),
		  os.path.join(os.path.split(os.path.abspath(sys.argv[0]))[0],"share"),
		  os.path.join(GetPrefix(),"share","sugar","activities","ptv","share"),
		  os.path.join(os.path.split(os.path.split(utils.__file__)[0])[0],'share')):
		try:
			os.stat(os.path.join(p,"penguintv.glade"))
			return p
		except:
			continue
	return None
	
def get_icon_filename():
	try:
		icon_file = GetPrefix()+"/share/pixmaps/penguintvicon.png"
		os.stat(icon_file)
	except:
		try:
			icon_file = GetPrefix()+"/share/penguintvicon.png" #in case the install is still in the source dirs
			os.stat(icon_file)
		except:
			try:
				icon_file = get_glade_prefix()+"/penguintvicon.png"
				os.stat(icon_file)
			except Exception, e:
				print "icon not found"
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
	known_players={ 'totem':'--enqueue',
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
				print "unknown type, using kfmclient"
				return "kfmclient exec "
			full_qual_prog = str(service.exec_()).replace("%U","").strip()
		except:
			print "error getting type, using kfmclient"
			return "kfmclient exec "
	else: #GNOME -- notice how short and sweet this is in comparison :P
		if HAS_GNOMEVFS:
			try:
				mimetype = gnomevfs.get_mime_type(urllib.quote(filename)) #fix for penny arcade filenames
				full_qual_prog = gnomevfs.mime_get_default_application(mimetype)[2]
			except:
				print "unknown type, using gnome-open"
				return "gnome-open "
		else:
			# :(
			return "echo "
	try:
		path, program = os.path.split(full_qual_prog)
	except:
		program = full_qual_prog
	
	if known_players.has_key(program):
		return full_qual_prog+" "+known_players[program]
	return full_qual_prog
				
def get_dated_dir():
	today = time.strftime("%Y-%m-%d")
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


def my_quote(str):
	"""Replaces some problematic characters with html equivalent if necessary"""
	#right now just & to &amp;, but not &amp; to &amp;amp;
	#instead of doing this with logic, just "unquote" the amps and then requote them
	str=string.replace(str,"&amp;","&")
	str=string.replace(str,"&","&amp;")
	return str
	
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
	
commands={	'play:':_("Open"),
			'download:':_("Download"),
			'downloadqueue:':_("Download And Open"),
			'pause:':_("Pause"),
			'cancel:':_("Cancel"),
			'file://':_("Open File"),
			'delete:':_("Delete"),
			'resume:':_("Resume"),
			'clear:':_("Cancel"),
			'stop:':_("Stop"),
			'tryresume:':("Try Resume")	}
	
def html_command(command,arg):
	"""returns something like '<a href="play:%s">Open</a>' for all the commands I have.
	Dictionary has keys of commands, and returns located strings"""
	
	#a couple special cases
	if command == "redownload":
		return '<a href="download:'+str(arg)+'">'+_("Re-Download")+"</a>"
		
	if command == "retry":
		return '<a href="download:'+str(arg)+'">'+_("Retry")+'</a>'
	
	return '<a href="'+command+str(arg)+'">'+commands[command]+'</a>'
	
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
			handler = gnomevfs.mime_get_default_application(gnomevfs.get_mime_type(urllib.quote(filename))) #PA fix
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
	print mimetype
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

#http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52281
class StrippingParser(HTMLParser.HTMLParser):

    # These are the HTML tags that we will leave intact
    #valid_tags = ('b', 'a', 'i', 'br', 'p')
    valid_tags = ('b', 'i', 'p')

    from htmlentitydefs import entitydefs # replace entitydefs from sgmllib
    
    def __init__(self):
        HTMLParser.HTMLParser.__init__(self)
        self.result = ""
        self.endTagList = [] 
        
    def handle_data(self, data):
        if data:
            self.result = self.result + data

    def handle_charref(self, name):
        self.result = "%s&#%s;" % (self.result, name)
        
    def handle_entityref(self, name):
        if self.entitydefs.has_key(name): 
            x = ';'
        else:
            # this breaks unstandard entities that end with ';'
            x = ''
        self.result = "%s&%s%s" % (self.result, name, x)
    
    def handle_starttag(self, tag, attrs):
        """ Delete all tags except for legal ones """
        if tag in self.valid_tags:
            self.result = self.result + '<' + tag
            for k, v in attrs:
                if string.lower(k[0:2]) != 'on' and string.lower(v[0:10]) != 'javascript':
                    self.result = '%s %s="%s"' % (self.result, k, v)
            endTag = '</%s>' % tag
            self.endTagList.insert(0,endTag)    
            self.result = self.result + '>'
                
    def handle_endtag(self, tag):
        if tag in self.valid_tags:
            self.result = "%s</%s>" % (self.result, tag)
            remTag = '</%s>' % tag
            self.endTagList.remove(remTag)

    def cleanup(self):
        """ Append missing closing tags """
        for j in range(len(self.endTagList)):
                self.result = self.result + self.endTagList[j]    
        
#usage:
#def strip(s):
#    """ Strip illegal HTML tags from string s """
#    parser = StrippingParser()
#    parser.feed(s)
#    parser.close()
#    parser.cleanup()
#    return parser.result

class AltParser(HTMLParser.HTMLParser):
	def __init__(self):
		HTMLParser.HTMLParser.__init__(self)
		self.alt_tags={}
		self.head_end=False
		
	def handle_starttag(self, tag, attrs):
		"""Signal when we get to a tag."""
		if tag=='link':
			attr_dic = {}
			for attr in attrs:
				attr_dic[attr[0]] = attr[1]
			try:
				if attr_dic['rel'] == 'alternate':
					if attr_dic['type'] in ['application/atom+xml','application/rss+xml','text/xml']:
						self.alt_tags[attr_dic['type']] = attr_dic['href']
			except:
				pass

	def handle_endtag(self, tag):
		if tag == 'head':
			self.head_end=True

		
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
	
	"""returns free disk space in kilobytes for 
	   the disk that contains file f, defaulting to root.  
	   Returns 0 on error"""
	
	os.stat(f) #if this fails it will raise exactly the right error
	
	cmd = "df -k " + f
	
	p = Popen(cmd, shell=True, 
		      stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
						 
	lines = p.stdout.readlines()
	
	try:
		return int(lines[1].split()[3]) * 1024
	except:
		return 0
		
def get_disk_total(f="/"):
	
	"""returns total disk space in kilobytes for 
	   the disk that contains file f, defaulting to root.
	   Returns 0 on error"""
	
	os.stat(f) #if this fails it will raise exactly the right error
	
	cmd = "df -k " + f
	
	p = Popen(cmd, shell=True, 
		      stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
						 
	lines = p.stdout.readlines()
	
	try:
		return int(lines[1].split()[1]) * 1024
	except:
		return 0
		
def init_gtkmozembed():
	"""We need to set up mozilla with set_comp_path in order for it not to 
	crash.  The fun part is not hardcoding that path since we have no way
	of getting it from the module itself.  good luck with this"""

	assert HAS_MOZILLA
	return True
	cmd = "ldd " + gtkmozembed.__file__ + "  | grep xpcom.so"
	p = subprocess.Popen(cmd, shell=True, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	retval = p.wait()
	stderr = p.stderr.read()
	if len(stderr) > 1 or retval != 0:
		return False
	ldd_output = p.stdout.read()
	comp_path = os.path.split(ldd_output.split()[2])[0]
	gtkmozembed.set_comp_path(comp_path)
	return True
	
def get_pynotify_ok():
	return False
	if not HAS_PYNOTIFY:
		return False

	# first get what package config reports
	cmd = "pkg-config notify-python --modversion"
	p = subprocess.Popen(cmd, shell=True, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	retval = p.wait()
	stderr = p.stderr.read()
	if len(stderr) > 1 or retval != 0:
		return False
	major,minor,rev = p.stdout.read().split('.')
	
	major = int(major)
	minor = int(minor)
	rev = int(rev)

	# if it's bad, return false
	if minor < 1:
		return False
	if minor == 1 and rev == 0:
		return False

	# if it's good, check to see it's not lying about prefix
	cmd = "pkg-config notify-python --variable=prefix"
	p = subprocess.Popen(cmd, shell=True, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	retval = p.wait()
	stderr = p.stderr.read()
	if len(stderr) > 1 or retval != 0:
		return False
	pkgconfig_prefix = p.stdout.read().strip()
	
	try:
		dirname = os.path.split(pynotify.__file__)[0]
		f = open(os.path.join(dirname, "_pynotify.la"))
	except:
		return False
	
	libdir_line = ""
	
	for line in f.readlines():
		if line[0:6] == "libdir":
			libdir_line = line.split("=")[1][1:-1]
			break
	f.close()
	
	libdir_line = libdir_line.strip()
	
	if len(libdir_line) == 0:
		return False
	
	if pkgconfig_prefix not in libdir_line:
		return False

	return True
	
if is_kde():
	import kio

