import sys, os, logging
import gtk, gobject
from gettext import gettext as _
from sugar.activity.Activity import Activity

#need to set things up before we import penguintv
try:
	import pycurl
except:
	logging.warning("Trying to load bundled pycurl libraries")
	
	path = os.path.join(os.path.abspath(sys.argv[0]), "activities", "ptv.activity")
	
	os.environ['LD_LIBRARY_PATH'] += ':'+os.path.join(path, 'lib')
	os.environ['PYTHONPATH'] += ':'+os.path.join(path, 'site-packages')
	import pycurl #if it fails now, let it fail
os.environ['SUGAR_PENGUINTV'] = '1' #set up variable so that utils knows we are running_sugar

from ptv.penguintv import penguintv

class PenguinTVActivity(Activity):
	def __init__(self):
		Activity.__init__(self)
		
		self.set_title(_('News Reader'))
		app = penguintv.PenguinTVApp()
		app.main_window.Show(self)
		
		toolbox = activity.ActivityToolbox(self)
		toolbox.add_toolbar(_('Menu'), app.main_window.toolbar)
		self.set_toolbox(toolbox)
		toolbox.show()
        
		app.post_show_init()
		self.connect('destroy',self.do_quit, app)
	
	def do_quit(self, event, app):
		app.do_quit()
		del app
