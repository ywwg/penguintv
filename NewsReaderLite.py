# a lite, read-only version of penguintv for olpc

import sys, os, logging
import threading
import time

logging.basicConfig(level=logging.DEBUG)

import gtk, gobject, gtk.glade
import dbus

from sugar.activity import activity
from sugar.graphics.toolbutton import ToolButton
#from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox
from sugar.graphics.palette import Palette

import hulahop

#need to set things up before we import penguintv

#where are we?
activity_root = activity.get_bundle_path()
	
#chdir here so that relative RPATHs line up ('./lib')
os.chdir(activity_root) 

#if user has desktop penguintv installed, don't use it
sys.path = [activity_root,] + sys.path

os.environ['SUGAR_PENGUINTV'] = '1' #set up variable so that utils knows we are running_sugar

from penguintv import ptvDB
from penguintv import PlanetViewLite
from penguintv import EntryFormatter
from penguintv import AddFeedDialog
from penguintv import utils
from penguintv import ptvDbus

try:
	import pycurl
except:
	logging.warning("Trying to load bundled pycurl libraries")
	
	#append to sys.path for the python packages
	sys.path.append(os.path.join(activity_root, 'site-packages'))
	
	#try again. if it fails now, let it fail
	import pycurl 

class NewsReaderLite(activity.Activity):
	def __init__(self, handle):
		activity.Activity.__init__(self, handle)
		self.set_title('News Reader')
		
		self.glade_prefix = utils.get_glade_prefix()
		self._session_tag = self._get_session_tag()

		toolbox = activity.ActivityToolbox(self)
		self.set_toolbox(toolbox)
		toolbox.show()

		logging.debug("Loading DB")
		self._db = ptvDB.ptvDB()
		self._db.maybe_initialize_db()
		self._update_thread = None
		self.set_canvas(self._build_ui())
		
		self.connect('destroy', self.do_quit)
		
		gobject.idle_add(self._post_show_init, toolbox)
		
	def add_feed(self, url, title):
		logging.debug("please insert feed " + url + " title")
		new_feed_id = self._db.get_feed_id_by_url(url)
		if new_feed_id > -1:
			for feed_id, title in self._feedlist:
				if new_feed_id == feed_id:
					#we already have it
					return
			#else just update the feedlist
		else:
			#add the feed, poll it, get the title, etc
			#this is blocking, but that's ok by me
			new_feed_id = self._db.insertURL(url)
			self._db.poll_feed(new_feed_id)
			title = self._db.get_feed_title(new_feed_id)
		self._db.add_tag_for_feed(new_feed_id, self._session_tag)
		self.update_feedlist()
		
	def update_feedlist(self):
		assert self._db is not None
		#print self._session_tag
		#feedlist = self._db.get_feeds_for_tag(self._session_tag)
		#print feedlist
		feedlist = self._db.get_feedlist()
		self._feedlist.clear()
		for feed_id, title in feedlist:
			#print feed_id
			#title = self._db.get_feed_title(feed_id)
			logging.debug("appending %i %s" % (feed_id,title))
			self._feedlist.append((feed_id, title))

	def display_status_message(self, msg):
		logging.info(msg)
		
	def do_quit(self, event):
		logging.debug("telling update thread to go away")
		if self._update_thread:
			self._update_thread.goAway()
			
	def _get_session_tag(self):
		return self._activity_id

	def _load_toolbar(self):
		toolbar = gtk.Toolbar()
		
		# Add Feed Palette
		button = ToolButton('gtk-add')
		toolbar.insert(button, -1)
		button.show()
		
		add_feed_dialog = AddFeedDialog.AddFeedDialog(gtk.glade.XML(os.path.join(self.glade_prefix, 'penguintv.glade'), "window_add_feed",'penguintv'), self) #MAGIC
		#content = add_feed_dialog.extract_content()
		#content.show_all()
		
		button.connect('clicked', add_feed_dialog.show)
		
		#palette = Palette(_('Subscribe to Feed'))
		#palette.set_content(content)
		#button.set_palette(palette)
		
		self._feedlist = gtk.ListStore(int, str)
		combo = gtk.ComboBox(self._feedlist)
		cell = gtk.CellRendererText()
		combo.pack_start(cell, True)
		combo.add_attribute(cell, 'text', 1)
		combo.connect("changed", self._on_combo_select)
		
		toolcombo = ToolComboBox(combo)
		toolbar.insert(toolcombo, -1)
		toolcombo.show_all()
	
		toolbar.show()
		return toolbar
			
	def _build_ui(self):
		logging.debug("Loading UI")
		vbox = gtk.VBox()
		
		#self._feedlist = gtk.ListStore(int, str)
		#combo = gtk.ComboBox(self._feedlist)
		#cell = gtk.CellRendererText()
		#combo.pack_start(cell, True)
		#combo.add_attribute(cell, 'text', 1)
		#combo.connect("changed", self._on_combo_select)
		#
		self._feed_viewer_dock = gtk.VBox()
		#
		#vbox.pack_start(combo, False)
		vbox.pack_start(self._feed_viewer_dock, True)
		
		self._feed_viewer = PlanetViewLite.PlanetViewLite(self._feed_viewer_dock, self, self._db)
		
		vbox.show_all()
		logging.debug("Done loading UI")
		return vbox
		
	def _post_show_init(self, toolbox):
		#DBUS
		bus = dbus.SessionBus()
		dubus = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/dbus')
		dubus_methods = dbus.Interface(dubus, 'org.freedesktop.DBus')
		if not dubus_methods.NameHasOwner('com.ywwg.PenguinTV'):
			logging.debug("No other News Reader found, starting polling thread")
			self._update_thread = _threaded_db(self._polling_callback)
			self._update_thread.start()
			
			#init dbus
			name = dbus.service.BusName("com.ywwg.PenguinTV", bus=bus)
			ptv_dbus = ptvDbus.ptvDbus(self, name)
		else:
			logging.debug("Detected other News Reader, not starting polling thread")
		
		print "adding toolbar I think"
		toolbox.add_toolbar(_('Feeds'), self._load_toolbar())

		self.update_feedlist()
		logging.debug("Updated list")
		print "updated list"
		return False
		
	def _on_combo_select(self, combo):
		active = combo.get_active()
		
		self._feed_viewer.populate_entries(self._feedlist[active][0])
		
	def _polling_callback(self, args, cancelled=False):
		pass
		
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

