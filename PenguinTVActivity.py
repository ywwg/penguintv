import sys, os, logging
import gtk, gobject
from sugar.activity.Activity import Activity

#need to set things up before we import penguintv

try:
	import pycurl
except:
	logging.warning("Trying to load bundled pycurl libraries")
	
	#import ourselves so we can get __file__
	import PenguinTVActivity
	
	#where the hell are we?
	activity_root = os.path.split(PenguinTVActivity.__file__)[0]
	
	#chdir here so that relative RPATHs line up ('./lib')
	os.chdir(activity_root) 
	
	#append to sys.path for the python packages
	sys.path.append(os.path.join(activity_root, 'site-packages'))
	
	#try again. if it fails now, let it fail
	import pycurl 
os.environ['SUGAR_PENGUINTV'] = '1' #set up variable so that utils knows we are running_sugar

from penguintv import penguintv

class PenguinTVActivity(Activity):
	def __init__(self):
		Activity.__init__(self)
		app = penguintv.PenguinTVApp(self)
		self.set_title('PenguinTV')
		self.connect('destroy',self.do_quit, app)
	
	def do_quit(self, event, app):
		app.do_quit()
		logging.info('deleting app now')
		del app

if __name__ == '__main__': # Here starts the dynamic part of the program

	def do_quit(self, event, app):
		app.do_quit()

	window = gtk.Window()
	gtk.gdk.threads_init()
	app = penguintv.PenguinTVApp()
	app.main_window.Show(window)
	gobject.idle_add(app.post_show_init)
	window.connect('delete-event', do_quit, app)
	gtk.main()
	
def main(): #another way to run the program

	def do_quit(self, event, app):
		app.do_quit()

	window = gtk.Window()
	gtk.gdk.threads_init()
	app = penguintv.PenguinTVApp()
	app.main_window.Show(window)
	gobject.idle_add(app.post_show_init)
	window.connect('delete-event', do_quit, app)
	gtk.main()
