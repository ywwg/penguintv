try:
	from Pyrex.Distutils import build_ext
	BUILD_MOZ=True
except:
	print "pyrex not found, mozilla building disabled"
	BUILD_MOZ=False


from distutils.core import setup
from distutils.extension import Extension
import sys,os
from penguintv import subProcess as my_subProcess
import subprocess #<-- ^-- oh god the buggy possibilities
import locale, gettext
from penguintv.utils import GlobDirectoryWalker, _mkdir
locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

#From the Democracy Player
def getCommandOutput(cmd, warnOnStderr = True, warnOnReturnCode = True):
    """Wait for a command and return its output.  Check for common errors and
    raise an exception if one of these occurs.
    """

    p = subprocess.Popen(cmd, shell=True, close_fds = True,
            stdout=subprocess.PIPE, stderr = subprocess.PIPE)
    p.wait()
    stderr = p.stderr.read()
    if warnOnStderr and stderr != '':
        raise RuntimeError("%s outputted the following error:\n%s" % 
                (cmd, stderr))
    if warnOnReturnCode and p.returncode != 0:
        raise RuntimeError("%s had non-zero return code %d" % 
                (cmd, p.returncode))
    return p.stdout.read()
    
#From the Democracy Player
def parsePkgConfig(command, components, options_dict = None):
    """Helper function to parse compiler/linker arguments from 
    pkg-config/mozilla-config and update include_dirs, library_dirs, etc.

    We return a dict with the following keys, which match up with keyword
    arguments to the setup function: include_dirs, library_dirs, libraries,
    extra_compile_args.

    Command is the command to run (pkg-config, mozilla-config, etc).
    Components is a string that lists the components to get options for.

    If options_dict is passed in, we add options to it, instead of starting
    from scratch.
    """

    if options_dict is None:
        options_dict = {
            'include_dirs' : [],
            'library_dirs' : [],
            'libraries' : [],
            'extra_compile_args' : []
        }
    commandLine = "%s --cflags --libs %s" % (command, components)
    output = getCommandOutput(commandLine).strip()
    for comp in output.split():
        prefix, rest = comp[:2], comp[2:]
        if prefix == '-I':
            options_dict['include_dirs'].append(rest)
        elif prefix == '-L':
            options_dict['library_dirs'].append(rest)
        elif prefix == '-l':
            options_dict['libraries'].append(rest)
        else:
            options_dict['extra_compile_args'].append(comp)
    return options_dict

try:
	from pysqlite2 import dbapi2 as sqlite
except:
	sys.exit("Need pysqlite version 2 or higher (http://pysqlite.org/)")
	
try:
	import pycurl
except:
	sys.exit("Need pycurl (http://pycurl.sourceforge.net/)")
	
try:
	import gtkhtml2
except:
	sys.exit("Need gtkhtml2 python bindings")
	
try:
	import gnome
except:
	sys.exit("Need gnome python bindings")
	
try:
	import gnomevfs
except:
	sys.exit("Need gnome-vfs python bindings")	
	
try:
	from xml.sax import saxutils
	test = saxutils.DefaultHandler
except:
	sys.exit("Need python-xml")
	
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

if BUILD_MOZ:
	in_f = file("share/penguintv.schema.in")
	out_f = open("share/penguintv.schema","w")
	line=" "
	while len(line)>0:
		line = in_f.readline()
		line = line.replace("$$RENDERRER$$","GTKHTML")  ##DEMOCRACY MOZ IS EXPERIMENTAL AND SLOW
		out_f.write(line)

	out_f.close()

	#From Democracy Player
	#### MozillaBrowser Extension ####
	mozilla_browser_options = parsePkgConfig("pkg-config" , 
	        "gtk+-2.0 glib-2.0 pygtk-2.0")
	try:
		parsePkgConfig("mozilla-config", "string dom gtkembedmoz necko xpcom",
	        mozilla_browser_options)
		# mozilla-config doesn't get gtkembedmoz one for some reason
		mozilla_browser_options['libraries'].append('gtkembedmoz') 
		# Running mozilla-config with no components should get us the path to the
		# mozilla libraries (nessecary to import gtkmozembed.so)
		mozilla_lib_path = parsePkgConfig('mozilla-config', '')['library_dirs']
		mozilla_browser_ext = Extension("penguintv.democracy_moz.MozillaBrowser",
		        [ os.path.join("penguintv/democracy_moz",'MozillaBrowser.pyx'),
		          os.path.join("penguintv/democracy_moz",'MozillaBrowserXPCOM.cc'),
		        ],
		        runtime_library_dirs=mozilla_lib_path,
		        **mozilla_browser_options)
		
		setup(name = "PenguinTV", 
			version = utils.VERSION,
			description      = 'GNOME-compatible podcast and videoblog reader',
			author           = 'Owen Williams',
			author_email     = 'ywwg@usa.net',
			url              = 'http://penguintv.sourceforge.net',
			license          = 'GPL',
			scripts          = ['PenguinTV'],
			data_files       = [('share/penguintv',		['share/penguintv.glade','share/defaultsubs.opml','share/penguintvicon.png']),
								('share/pixmaps',		['share/penguintvicon.png']),
								('share/applications',	['penguintv.desktop'])]+locales,
			packages = ["penguintv", "penguintv/ptvbittorrent", "penguintv/democracy_moz"],
			ext_modules = [mozilla_browser_ext],
			cmdclass = {
		        'build_ext': build_ext}
			)
	except:
		BUILD_MOZ=False
	
if BUILD_MOZ==False:
	in_f = file("share/penguintv.schema.in")
	out_f = open("share/penguintv.schema","w")
	line=" "
	while len(line)>0:
		line = in_f.readline()
		line = line.replace("$$RENDERRER$$","GTKHTML")
		out_f.write(line)

	out_f.close()
	setup(name = "PenguinTV", 
	version = utils.VERSION,
	description      = 'GNOME-compatible podcast and videoblog reader',
	author           = 'Owen Williams',
	author_email     = 'ywwg@usa.net',
	url              = 'http://penguintv.sourceforge.net',
	license          = 'GPL',
	scripts          = ['PenguinTV'],
	data_files       = [('share/penguintv',		['share/penguintv.glade','share/defaultsubs.opml','share/penguintvicon.png']),
						('share/pixmaps',		['share/penguintvicon.png']),
						('share/applications',	['penguintv.desktop'])]+locales,
	packages = ["penguintv", "penguintv/ptvbittorrent"])

if "install" in sys.argv:
	sp = my_subProcess.subProcess('''GCONF_CONFIG_SOURCE=$(gconftool-2 --get-default-source) gconftool-2 --makefile-install-rule share/penguintv.schema''')
	if sp.read() != 0:
		print sp.outdata
		print "There was an error installing the gconf schema"
		sys.exit(1)
	else:
		print sp.outdata
		
	if  BUILD_MOZ:
		print """By default, penguintv will use the gtkhtml renderrer.  If you want to use mozilla instead, run the command:
gconftool-2 -s -t string /apps/penguintv/renderrer DEMOCRACY_MOZ
Please note that the mozilla renderrer is experimental"""



