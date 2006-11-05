import sys, os, logging
import gtk, gobject
from sugar.activity.Activity import Activity

#need to set things up before we import penguintv

try:
	import pycurl
except:
	logging.warning("Trying to load bundled pycurl libraries")
	
	import PenguinTVActivity
	activity_root = os.path.split(PenguinTVActivity.__file__)[0]
	if os.environ.has_key('LD_RUN_PATH'):
		os.environ['LD_RUN_PATH'] += ':'+os.path.join(activity_root, 'lib')
	else:
		os.environ['LD_RUN_PATH'] = os.path.join(activity_root, 'lib')
	sys.path.append(os.path.join(activity_root, 'site-packages'))
	#os.environ['PYTHONPATH'] += ':'+os.path.join(activity_root, 'site-packages')
	import pycurl #if it fails now, let it fail
os.environ['SUGAR_PENGUINTV'] = '1' #set up variable so that utils knows we are running_sugar

from penguintv import penguintv

class PenguinTVActivity(Activity):
	def __init__(self):
		Activity.__init__(self)
		app = penguintv.PenguinTVApp()
		app.main_window.Show(self)
		app.post_show_init()
		self.connect('destroy',self.do_quit, app)
	
	def do_quit(self, event, app):
		app.do_quit()
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
