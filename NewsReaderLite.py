# a lite, read-only version of penguintv for olpc


#TODO: need to make entire sessions (url lists) share with buddies, not just
#current feed

import sys, os, logging
import threading
import time

logging.basicConfig(level=logging.DEBUG)

import gtk, gobject, gtk.glade
import dbus

import telepathy
import telepathy.client

from sugar.activity import activity
from sugar.graphics.toolbutton import ToolButton
#from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox
from sugar.graphics.palette import Palette

from sugar.presence import presenceservice
from sugar.presence.tubeconn import TubeConnection


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
from penguintv import PlanetView
from penguintv import EntryFormatter
from penguintv import AddFeedDialog
from penguintv import utils
from penguintv import NRLTube
from penguintv import ptvDbus

#try:
#	import pycurl
#except:
#	logging.warning("Trying to load bundled pycurl libraries")
#	
#	#append to sys.path for the python packages
#	sys.path.append(os.path.join(activity_root, 'site-packages'))
#	
#	#try again. if it fails now, let it fail
#	import pycurl 

class NewsReaderLite(activity.Activity):

	__gsignals__ = {
		'feed-polled': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT]))
		}

	def __init__(self, handle):
		activity.Activity.__init__(self, handle)
		self.set_title('News Reader')
		
		self.glade_prefix = utils.get_glade_prefix()
		self._session_tag = self._get_session_tag()
		
		logging.debug("Activity ID: %s" % (str(self._session_tag),))

		toolbox = activity.ActivityToolbox(self)
		self.set_toolbox(toolbox)
		toolbox.show()

		logging.debug("Loading DB")
		self._db = ptvDB.ptvDB()
		self._db.maybe_initialize_db()
		self._update_thread = None
		self.set_canvas(self._build_ui())
		
		#self.connect('destroy', self.do_quit)
		self.newsreader_tube = None #shared activity
		self.initiating = None # I initiated the activity
		
		# get the Presence Service
		self.pservice = presenceservice.get_instance()
		# Buddy object for you
		self.owner = self.pservice.get_owner()

		self.connect('shared', self._shared_cb)
		self.connect('joined', self._joined_cb)
		self.connect('feed-polled', self._feed_polled_cb)
		
		gobject.idle_add(self._post_show_init, toolbox)
		
	def _shared_cb(self, activity):
		logging.debug('My activity was shared')
		self.initiating = True
		self._sharing_setup()

		logging.debug('This is my activity: making a tube...')
		id = self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferDBusTube(
			NRLTube.SERVICE, {})

	def _sharing_setup(self):
		if self._shared_activity is None:
			logging.error('Failed to share or join activity')
			return

		self.conn = self._shared_activity.telepathy_conn
		self.tubes_chan = self._shared_activity.telepathy_tubes_chan
		self.text_chan = self._shared_activity.telepathy_text_chan

		self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal(
			'NewTube', self._new_tube_cb)

	def _list_tubes_reply_cb(self, tubes):
		for tube_info in tubes:
			self._new_tube_cb(*tube_info)

	def _list_tubes_error_cb(self, e):
		logging.error('ListTubes() failed: %s', e)

	def _joined_cb(self, activity):
		if not self._shared_activity:
			return

		logging.debug('Joined an existing shared activity')
		self.initiating = False
		self._sharing_setup()

		logging.debug('This is not my activity: waiting for a tube...')
		self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
			reply_handler=self._list_tubes_reply_cb,
			error_handler=self._list_tubes_error_cb)

	def _new_tube_cb(self, id, initiator, type, service, params, state):
		logging.debug('New tube: ID=%d initator=%d type=%d service=%s '
					 'params=%r state=%d', id, initiator, type, service,
					 params, state)
		if (type == telepathy.TUBE_TYPE_DBUS and
			service == NRLTube.SERVICE):
			if state == telepathy.TUBE_STATE_LOCAL_PENDING:
				self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].AcceptDBusTube(id)
			tube_conn = TubeConnection(self.conn,
				self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES],
				id, group_iface=self.text_chan[telepathy.CHANNEL_INTERFACE_GROUP])
			self.newsreader_tube = NRLTube.NRLTube(self, tube_conn, self.initiating, self._get_buddy)

	def _get_buddy(self, cs_handle):
		"""Get a Buddy from a channel specific handle."""
		logging.debug('Trying to find owner of handle %u...', cs_handle)
		group = self.text_chan[telepathy.CHANNEL_INTERFACE_GROUP]
		my_csh = group.GetSelfHandle()
		logging.debug('My handle in that group is %u', my_csh)
		if my_csh == cs_handle:
			handle = self.conn.GetSelfHandle()
			logging.debug('CS handle %u belongs to me, %u', cs_handle, handle)
		elif group.GetGroupFlags() & telepathy.CHANNEL_GROUP_FLAG_CHANNEL_SPECIFIC_HANDLES:
			handle = group.GetHandleOwners([cs_handle])[0]
			logging.debug('CS handle %u belongs to %u', cs_handle, handle)
		else:
			handle = cs_handle
			logging.debug('non-CS handle %u belongs to itself', handle)
			# XXX: deal with failure to get the handle owner
			assert handle != 0
		return self.pservice.get_buddy_by_telepathy_handle(
			self.conn.service_name, self.conn.object_path, handle)

	def add_feed(self, url, title):
		new_feed_id = self._db.get_feed_id_by_url(url)
		if new_feed_id > -1:
			for feed_id, title, url in self._feedlist:
				if new_feed_id == feed_id:
					#we already have it
					self.select_feed(feed_id)
					return feed_id
			#else just update the feedlist
		else:
			#add the feed, poll it, get the title, etc
			#this is blocking, but that's ok by me
			new_feed_id = self._db.insertURL(url)
			self._db.poll_feed(new_feed_id)
			title = self._db.get_feed_title(new_feed_id)
		self._db.add_tag_for_feed(new_feed_id, self._session_tag)
		self.update_feedlist()
		self.select_feed(new_feed_id)
		return new_feed_id
		
	def remove_feed(self, position):		
		self._db.delete_feed(self._feedlist[position][0])
		self.update_feedlist()
		if position >= len(self._feedlist):
			position = len(self._feedlist) - 1
		self._combo.set_active(position)

	def select_feed(self, feed_id):
		try:
			active = self._combo.get_active()
			index = [f[0] for f in self._feedlist].index(feed_id)
			if active == index:
				logging.debug("not reselecting the same feed")
				return
			self._combo.set_active(index)
		except:
			logging.warning("Feed not found, " + str(feed_id))
			
	def select_by_url(self, url, title):
		assert url is not None
		assert title is not None
		assert self._db is not None
			
		feed_id = self.add_feed(url, title)
		self.select_feed(feed_id)
			
	def get_current_feed(self):
		active = self._combo.get_active()
		if active == -1:
			return (None, None)
		return (self._feedlist[active][1], self._feedlist[active][2])
		
	def update_feedlist(self):
		assert self._db is not None
		print self._session_tag
		feedlist = self._db.get_feeds_for_tag(self._session_tag)
		#print feedlist
		#feedlist = self._db.get_feedlist()
		self._feedlist.clear()
		for feed_id in feedlist:
			#print feed_id
			feed_info = self._db.get_feed_info(feed_id)
			self._feedlist.append((feed_id, feed_info['title'], feed_info['url']))
			
		self._update_unsubscribed_feeds()

	def display_status_message(self, msg):
		logging.info(msg)
		
	#def do_quit(self, event):
	def destroy(self):
		logging.debug("QUITTING NOW")
		if self._update_thread is not None:
			logging.debug("telling update thread to go away")
			self._update_thread.goAway()
			while threading.activeCount() > 1:
				logging.info(threading.enumerate())
				logging.info(str(threading.activeCount())+" threads active...")
				time.sleep(1)
		else:
			logging.debug("Not in charge of update thread, letting it live")
			
		activity.Activity.destroy(self)
			
	def _get_session_tag(self):
		return self._activity_id

	def _load_toolbar(self):
		toolbar = gtk.Toolbar()
		
		# Remove Feed Palette
		remove_button = ToolButton(icon_name='list-remove')
		vbox = gtk.VBox()
		label = gtk.Label(_('Really delete feed?'))
		vbox.pack_start(label)
		hbox = gtk.HBox()
		expander_label = gtk.Label(' ')
		hbox.pack_start(expander_label)
		#b = gtk.Button(icon_name='stock-remove')
		b = ToolButton(icon_name='list-remove')
		#b.set_use_stock(True)
		b.connect('clicked', self._on_remove_feed_activate)
		hbox.pack_start(b, False)
		vbox.pack_start(hbox)
		palette = Palette(_('Remove Feed?'))
		palette.set_content(vbox)
		vbox.show_all()
		remove_button.set_palette(palette)
		toolbar.insert(remove_button, -1)
		remove_button.show()
		
		# Add Feed Palette
		button = ToolButton(icon_name='list-add')
		toolbar.insert(button, -1)
		button.show()
		
		self._add_feed_dialog = AddFeedDialog.AddFeedDialog(gtk.glade.XML(os.path.join(self.glade_prefix, 'penguintv.glade'), "window_add_feed",'penguintv'), self) #MAGIC
		content = self._add_feed_dialog.extract_content()
		content.show_all()
		
		#button.connect('clicked', self._add_feed_dialog.show)
		
		palette = Palette(_('Subscribe to Feed'))
		palette.set_content(content)
		button.set_palette(palette)
		
		self._feedlist = gtk.ListStore(int, str, str)
		self._combo = gtk.ComboBox(self._feedlist)
		cell = gtk.CellRendererText()
		self._combo.pack_start(cell, True)
		self._combo.add_attribute(cell, 'text', 1)
		self._combo.connect("changed", self._on_combo_select)
		
		toolcombo = ToolComboBox(self._combo)
		toolbar.insert(toolcombo, -1)
		toolcombo.show_all()
	
		toolbar.show()
		return toolbar
		
	def _update_unsubscribed_feeds(self):
		# get a list of all feeds from DB
		
		db_feedlist = self._db.get_feedlist()
		
		# remove any feeds that we are subscribed to
		unsub_feedlist = []
		idlist = [f[0] for f in self._feedlist]
		for row in db_feedlist:
			if row[0] not in idlist:
				unsub_feedlist.append(row)
				
		# reinit add_feed_dialog with this new list
		self._add_feed_dialog.set_existing_feeds(unsub_feedlist)
			
	def _build_ui(self):
		logging.debug("Loading UI")
		vbox = gtk.VBox()
		
		self._feed_viewer_dock = gtk.VBox()

		vbox.pack_start(self._feed_viewer_dock, True)
		
		self._feed_viewer = PlanetView.PlanetView(self._feed_viewer_dock, self, self._db, self.glade_prefix)
		
		vbox.show_all()
		logging.debug("Done loading UI")
		return vbox
		
	def _post_show_init(self, toolbox):
		#DBUS
		bus = dbus.SessionBus()
		dubus = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/dbus')
		dubus_methods = dbus.Interface(dubus, 'org.freedesktop.DBus')
		if not dubus_methods.NameHasOwner('com.ywwg.NewsReaderLite'):
			logging.debug("No other News Reader found, starting polling thread")
			self._update_thread = _threaded_db(self._polling_callback)
			self._update_thread.setDaemon(True)
			self._update_thread.start()
			
			#init dbus
			name = dbus.service.BusName("com.ywwg.NewsReaderLite", bus=bus)
			ptv_dbus = ptvDbus.ptvDbus(self, name)
		else:
			logging.debug("Detected other News Reader, not starting polling thread")
		
		toolbox.add_toolbar(_('Feeds'), self._load_toolbar())

		self.update_feedlist()
		self._combo.set_active(0)
		logging.debug("Updated list")
		return False
		
	def _on_remove_feed_activate(self, event):
		# get feed id of current selection
		active = self._combo.get_active()		
		self.remove_feed(active)
		self._feed_viewer.display_item(None)

	def _on_combo_select(self, combo):
		active = combo.get_active()
		if active >= 0 and len(self._feedlist) > 0:
			feed_id = self._feedlist[active][0]
			if feed_id != self._feed_viewer.get_current_feed_id():
				logging.debug("NRL: populating entries, changing feed")
				self._feed_viewer.populate_entries(feed_id)
				if self.newsreader_tube is not None:
					self.newsreader_tube.ChangeFeed(self._feedlist[active][2], self._feedlist[active][1])
			else:
				logging.debug("NRL: same damn feed, not tubing")
		
	def _polling_callback(self, args, cancelled=False):
		feed_id,update_data, total = args
		
		#self._threaded_emit('feed-polled', feed_id)
		gobject.idle_add(self._feed_polled_cb, feed_id)
		
	def _feed_polled_cb(self, feed_id):
		self._feed_viewer.populate_if_selected(feed_id)
		return False

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
			for i in range(0, self._poll_timeout / 2):
				if self.__isDying:
					logging.debug("Quitting DB")
					break
				time.sleep(2)
		logging.debug("db finishing")	
		self._db.finish()
					
	def get_db(self):
		return self._db
		
	def goAway(self):
		""" Exit the run loop next time through."""
		self.__isDying = True
