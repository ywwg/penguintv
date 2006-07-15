#no moz
from distutils.core import setup
from distutils.extension import Extension
import sys,os
from penguintv import subProcess as my_subProcess
import subprocess #<-- ^-- oh god the buggy possibilities
import locale, gettext
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

from penguintv import utils

in_f = file("share/penguintv.schema.in")
out_f = open("share/penguintv.schema","w")
line=" "
while len(line)>0:
	line = in_f.readline()
	line = line.replace("$$RENDERRER$$","GTKHTML")
	out_f.write(line)
out_f.close()

from penguintv.utils import GlobDirectoryWalker,_mkdir
import os.path

locales = []
if "build" in sys.argv or "install" in sys.argv:
	for file in GlobDirectoryWalker("./po", "*.po"):	
		this_locale = os.path.basename(file)	
		this_locale = this_locale[0:this_locale.rfind('.')]
		_mkdir("./mo/"+this_locale+"/LC_MESSAGES")
		msgfmt_line = "msgfmt "+file+" -o ./mo/"+this_locale+"/LC_MESSAGES/penguintv.mo"
		print msgfmt_line
		locales.append(('share/locale/'+this_locale+'/LC_MESSAGES', ['mo/'+this_locale+'/LC_MESSAGES/penguintv.mo']))
		sp = my_subProcess.subProcess(msgfmt_line)
		if sp.read() != 0:
			print "There was an error installing the PO file for locale "+this_locale
			sys.exit(1)
			
print locales

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


	


