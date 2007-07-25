# a lite, read-only version of penguintv for olpc

import sys, os, logging
import threading
import time

import gtk, gobject
import dbus

from sugar.activity import activity
from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.palette import Palette

import hulahop

#need to set things up before we import penguintv

#where are we?
activity_root = activity.get_bundle_path()
	
#chdir here so that relative RPATHs line up ('./lib')
os.chdir(activity_root) 

#if user has desktop penguintv installed, don't use it
sys.path = [activity_root,] + sys.path

from penguintv import ptvDB, PlanetViewLite, EntryFormatter

try:
	import pycurl
except:
	logging.warning("Trying to load bundled pycurl libraries")
	
	#append to sys.path for the python packages
	sys.path.append(os.path.join(activity_root, 'site-packages'))
	
	#try again. if it fails now, let it fail
	import pycurl 
os.environ['SUGAR_PENGUINTV'] = '1' #set up variable so that utils knows we are running_sugar

class NewsReaderLite(activity.Activity):
	def __init__(self, handle):
		activity.Activity.__init__(self, handle)
		self.set_title('News Reader')
		toolbox = activity.ActivityToolbox(self)
	
		#toolbox.add_toolbar(_('Feeds'), self._load_toolbar)
		self.set_toolbox(toolbox)
		toolbox.show()
		logging.debug("Loading DB")
		self._db = ptvDB.ptvDB()
		self._update_thread = None
		self.set_canvas(self._build_ui())
		
		self.connect('destroy', self.do_quit)
		
		gobject.idle_add(self._post_show_init)
		
	def do_quit(self, event):
		logging.debug("telling update thread to go away")
		if self._update_thread:
			self._update_thread.goAway()
		
	def _build_ui(self):
		logging.debug("Loading UI")
		vbox = gtk.VBox()
		
		self._feedlist = gtk.ListStore(int, str)
		combo = gtk.ComboBox(self._feedlist)
		cell = gtk.CellRendererText()
		combo.pack_start(cell, True)
		combo.add_attribute(cell, 'text', 1)
		combo.connect("changed", self._on_combo_select)
		
		self._feed_viewer_dock = gtk.VBox()
		
		vbox.pack_start(combo, False)
		vbox.pack_start(self._feed_viewer_dock, True)
		
		self._feed_viewer = PlanetViewLite.PlanetViewLite(self._feed_viewer_dock, self, self._db)
		
		vbox.show_all()
		logging.debug("Done loading UI")
		return vbox
		
	def _post_show_init(self):
		self.update_feedlist()
		logging.debug("Updated list")
		
		#DBUS
		bus = dbus.SessionBus()
		dubus = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/dbus')
		dubus_methods = dbus.Interface(dubus, 'org.freedesktop.DBus')
		if not dubus_methods.NameHasOwner('com.ywwg.PenguinTV'):
			logging.debug("No other News Reader found, starting polling thread")
			self._update_thread = _threaded_db(self._polling_callback)
			self._update_thread.start()
		else:
			logging.debug("Detected other News Reader, not starting polling thread")
		
		return False
		
	def _polling_callback(self, args, cancelled=False):
		pass
		
	def update_feedlist(self):
		assert self._db is not None
		
		feedlist = self._db.get_feedlist()
		self._feedlist.clear()
		for feed_id, title in feedlist:
			self._feedlist.append((feed_id, title))
			
	def _on_combo_select(self, combo):
		active = combo.get_active()
		
		self._feed_viewer.populate_entries(self._feedlist[active][0])
		
	def display_status_message(self, msg):
		logging.info(msg)
		
	def _load_toolbar(self):
		#TODO
		toolbar = gtk.Toolbar()
		
		# Add Feed Palette
		button = ToolButton('gtk-add')
		toolbar.insert(button, -1)
		
		#vbox = gtk.VBox()
		#label = gtk.Label("Add a url")
		
		
		palette = Palette(_('Add Feed'))
		palette.set_content(content)
		button.set_palette(palette)

	
		button.show()
		return toolbar
		
class _threaded_db(threading.Thread):
	def __init__(self, polling_callback):
		threading.Thread.__init__(self)
		self.__isDying = False
		self._db = None
		self._poll_timeout = 5*60
		self._polling_callback = polling_callback
			
	def run(self):
		""" Until told to quit, retrieve the next task and execute
			it, calling the callback if any.  """
		if self._db == None:
			self._db = ptvDB.ptvDB(self._polling_callback)

		while self.__isDying == False:
			logging.debug("Polling")
			self._db.poll_multiple(ptvDB.A_AUTOTUNE)
			if self.__isDying:
				break
			time.sleep(self._poll_timeout)
					
	def get_db(self):
		return self._db
		
	def goAway(self):
		""" Exit the run loop next time through."""
		self.__isDying = True

