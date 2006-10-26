import gtk, gobject
from ptv.penguintv import penguintv
import sys

from sugar.activity.Activity import Activity

class PenguinTVActivity(Activity):
	def __init__(self):
		Activity.__init__(self)
		app = penguintv.PenguinTVApp("/home/owen/src/olpc/sugar/sugar-jhbuild/build/share/sugar/activities/ptv/log")    # Instancing of the GUI
		app.main_window.Show(self)
		gobject.idle_add(app.post_show_init) #lets window appear first)
		self.connect('destroy',self.do_quit, app)
	
	def do_quit(self, event, app):
		app.do_quit()
		del app
