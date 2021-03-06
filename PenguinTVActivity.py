import sys, os, logging
import gtk, gobject
from sugar.activity import activity

import hulahop

#need to set things up before we import penguintv

activity_root = activity.get_bundle_path()
	
#chdir here so that relative RPATHs line up ('./lib')
os.chdir(activity_root) 
	
#append to sys.path for the python packages
sys.path = [activity_root,] + sys.path

try:
	import pycurl
except:
	logging.warning("Trying to load bundled pycurl libraries")
	
	#append to sys.path for the python packages
	sys.path.append(os.path.join(activity_root, 'site-packages'))
	
	#try again. if it fails now, let it fail
	import pycurl 
os.environ['SUGAR_PENGUINTV'] = '1' #set up variable so that utils knows we are running_sugar

from penguintv import penguintv

class PenguinTVActivity(activity.Activity):
	def __init__(self, handle):
		activity.Activity.__init__(self, handle)
		app = penguintv.PenguinTVApp(self)
		self.set_title('News Reader')
		toolbox = activity.ActivityToolbox(self)
		
		#toolbox.add_toolbar(_('Feeds'), app.main_window.toolbar)
		app.connect('app-loaded', self.add_toolbar, toolbox)
		#gobject.idle_add(self.add_toolbar, toolbox, app)
		
		self.set_toolbox(toolbox)
		toolbox.show()
		self.connect('destroy',self.do_quit, app)
	
	def do_quit(self, event, app):
		app.do_quit()
		logging.info('deleting app now')
		del app
		
	def add_toolbar(self, app, toolbox):
		toolbox.add_toolbar(_('Feeds'), app.main_window.toolbar)
		

if __name__ == '__main__': # Here starts the dynamic part of the program

	def do_quit(self, event, app):
		app.do_quit()

	window = gtk.Window()
	gtk.gdk.threads_init()
	app = penguintv.PenguinTVApp(window)
	window.connect('delete-event', do_quit, app)
	gtk.main()
	
def main(): #another way to run the program

	def do_quit(self, event, app):
		app.do_quit()

	window = gtk.Window()
	gtk.gdk.threads_init()
	app = penguintv.PenguinTVApp(window)
	window.connect('delete-event', do_quit, app)
	gtk.main()
