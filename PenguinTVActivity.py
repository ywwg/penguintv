import gtk, gobject
from ptv.penguintv import penguintv
import sys, os, logging

from sugar.activity.Activity import Activity

def start():
	try:
		import pycurl
	except:
		logging.warning("Trying to load bundled pycurl libraries")
		os.environ['LD_LIBRARY_PATH'] += ':./lib'
		os.environ['PYTHONPATH'] += ':./site-packages'
		import pycurl #if it fails now, let it fail

class PenguinTVActivity(Activity):
	def __init__(self):
		Activity.__init__(self)
		app = penguintv.PenguinTVApp()    # Instancing of the GUI
		app.main_window.Show(self)
		gobject.idle_add(app.post_show_init) #lets window appear first)
		self.connect('destroy',self.do_quit, app)
	
	def do_quit(self, event, app):
		app.do_quit()
		del app
