import sys, os, logging

started = False
def start():
	global started
	started = True
	try:
		import pycurl
	except:
		logging.warning("Trying to load bundled pycurl libraries")
		os.environ['LD_LIBRARY_PATH'] += ':./lib'
		os.environ['PYTHONPATH'] += ':./site-packages'
		import pycurl #if it fails now, let it fail
	os.environ['SUGAR_PENGUINTV'] = '1'

if not started: start()

import gtk, gobject
from ptv.penguintv import penguintv

from sugar.activity.Activity import Activity

class PenguinTVActivity(Activity):
	def __init__(self):
		Activity.__init__(self)
		app = penguintv.PenguinTVApp()    # Instancing of the GUI
		app.main_window.Show(self)
		app.post_show_init()
		self.connect('destroy',self.do_quit, app)
	
	def do_quit(self, event, app):
		app.do_quit()
		del app
