#!/usr/bin/env python
# Written by Owen Williams
# using pieces from Straw
# see LICENSE for license information

#states:
DEFAULT            = 1
MANUAL_SEARCH      = 2
TAG_SEARCH         = 3
MAJOR_DB_OPERATION      = 4
DONE_MAJOR_DB_OPERATION = 5

#memory profiling:

#import code
#from sizer import scanner
##objs = scanner.Objects()
##code.interact(local = {'objs': objs})
##from sizer import formatting

#import urlparse loaded as needed
try:
	from sqlite3 import OperationalError as OperationalError
	import sqlite3 as sqlite
except:
	from pysqlite2.dbapi2 import OperationalError as OperationalError
	from pysqlite2 import dbapi2 as sqlite
import threading
import sys, os, os.path

import logging
#import traceback

logging.basicConfig(level=logging.DEBUG)

import urllib

import time
import string
import subprocess
import getopt
#socket.setdefaulttimeout(30.0)
try:
	set
except:
	from sets import Set as set

import pygtk
pygtk.require('2.0')
import gtk
import gtk.glade
import gobject
import locale
import gettext
try:
	import dbus
	import dbus.service
	HAS_DBUS = True
except:
	HAS_DBUS = False

#locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

DOWNLOAD_ERROR=0
DOWNLOAD_PROGRESS=1
DOWNLOAD_WARNING=2
DOWNLOAD_QUEUED=3

import utils
import ptvDB
if HAS_DBUS:
	import ptvDbus
import MediaManager
import Player
import UpdateTasksManager
import Downloader
import ArticleSync
if HAS_DBUS:
	import Poller

import PreferencesDialog
import MainWindow, FeedList

if utils.RUNNING_HILDON:
	HAS_GNOME = False
else:
	try:
		import gnome
		import gnome.ui
		HAS_GNOME=True
	except:
		HAS_GNOME=False

if utils.HAS_STATUS_ICON:
	import PtvTrayIcon
	
if utils.RUNNING_HILDON:
	#FIXME: should do something
	import hildon
	import HildonListener
	import osso
#	HAS_DBUS = False
if not utils.RUNNING_HILDON:
	import webbrowser
	import gc

CANCEL=0
PAUSE=1

REFRESH_SPECIFIED=0
REFRESH_AUTO=1
REFRESH_NEVER=2

LOCAL=0
REMOTE=1

if utils.RUNNING_SUGAR or utils.RUNNING_HILDON:
	AUTO_REFRESH_FREQUENCY=30*60*1000
else:
	AUTO_REFRESH_FREQUENCY=5*60*1000


class PenguinTVApp(gobject.GObject):

	__gsignals__ = {
		'feed-polled': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_INT, gobject.TYPE_PYOBJECT])),
		'feed-added': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_INT, gobject.TYPE_BOOLEAN])),
		'feed-removed': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_INT])),
		'feed-name-changed': (gobject.SIGNAL_RUN_FIRST, 
							gobject.TYPE_NONE,
							([gobject.TYPE_INT, gobject.TYPE_STRING, gobject.TYPE_STRING])),
		'entry-updated': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_INT, gobject.TYPE_INT])),
		'entries-viewed': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_PYOBJECT])),
		'entries-unviewed': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_PYOBJECT])),
		'render-ops-updated': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([])),
		'notify-tags-changed': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([])),
		# the integer here is really just so I can avoid a circular codepath
		# in tag editor ng
		'tags-changed': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_INT])),                        
		'download-finished': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_PYOBJECT])),
		'app-loaded': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([])),
		'setting-changed':(gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
						   ([gobject.TYPE_INT, gobject.TYPE_STRING, gobject.TYPE_PYOBJECT])),
		'state-changed':(gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
						   ([gobject.TYPE_INT, gobject.TYPE_PYOBJECT])),
		'online-status-changed':(gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
						   ([gobject.TYPE_BOOLEAN])),
		'new-database': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_PYOBJECT])), 
	}

	def __init__(self, window=None, playlist=None):
		gobject.GObject.__init__(self)
		self._for_import = []
		self.__importing = False
		self._app_loaded = False
		self._remote_poller = None
		self._remote_poller_pid = 0
		self._exiting=0
		
		if HAS_DBUS:
			#if we can get a dbus object, and it's using
			#our database, penguintv is already running
			bus = dbus.SessionBus()
			dubus = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/dbus')
			dubus_methods = dbus.Interface(dubus, 'org.freedesktop.DBus')
			if dubus_methods.NameHasOwner('com.ywwg.PenguinTV'):
				remote_object = bus.get_object("com.ywwg.PenguinTV", "/PtvApp")
				remote_app = dbus.Interface(remote_object, "com.ywwg.PenguinTV.AppInterface")
				if remote_app.GetDatabaseName() == os.path.join(utils.get_home(), "penguintv4.db"):
					#shouldn't happen if this file is run with __main__
					raise AlreadyRunning, remote_app
			#initialize dbus object
			name = dbus.service.BusName("com.ywwg.PenguinTV", bus=bus)
			ptv_dbus = ptvDbus.ptvDbus(self, name)
			
		self._net_connected = True
		self.connect('online-status-changed', self.__online_status_changed)
		self.connect('state-changed', self._state_changed_cb)
			
		if utils.get_share_prefix() is None:
			logging.error("Error finding glade file.  Have you run python setup.py build?")
			sys.exit()
						
		logging.info("penguintv " + utils.VERSION + " startup")
			
		self.db = ptvDB.ptvDB(self.polling_callback, self._emit_change_setting)
		
		#we have already run this down at the bottom, but run it again
		#because we don't init the DB down there (should we?)
		self._firstrun = self.db.maybe_initialize_db()
		
		# Clean media status on startup, not exit, in case of crash.
		self.db.clean_media_status()
		
		media_dir = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/media_storage_location', os.path.join(utils.get_home(), "media"))
		media_dir = media_dir.replace("\"","")
		self.mediamanager = MediaManager.MediaManager(self, media_dir, self._progress_callback, self._finished_callback)
		self._polled=0      #Used for updating the polling progress bar
		self._poll_message = ""
		self._polling_taskinfo = -1 # the taskid we can use to waitfor a polling operation,
									# and the time of last polling
		self._polling_thread = REMOTE
		self._poll_new_entries = []
		self.polling_frequency=12*60*60*1000
		self._bt_settings = {}
		self._auto_download = False
		self._auto_download_limiter = False
		self._auto_download_limit=50*1024
		self._saved_filter = FeedList.ALL
		self._saved_search = ""
		self._showing_search = False
		self._threaded_searcher = None
		self._waiting_for_search = False
		self._state = DEFAULT
		self._update_thread = None
				
		window_layout = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/app_window_layout', 'planet')
		if utils.RUNNING_SUGAR: 
			window_layout='planet' #always use planet on sugar platform
		if utils.RUNNING_HILDON:
			window_layout='hildon_planet'
		
		#stupid gconf will default to false if the key doesn't exist.  And of course the schema usually
		#doesn't work until they re-login...
		if not utils.RUNNING_SUGAR:
			use_internal_player = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/use_internal_player', True)
		else:
			use_internal_player = True
			
		self._status_icon = None

		if utils.HAS_STATUS_ICON:
			if utils.RUNNING_HILDON:
				icon = "/usr/share/icons/hicolor/26x26/hildon/penguintvicon.png"
				if not os.path.isfile(icon):
					icon = utils.get_image_path('penguintvicon.png')
			else:
				icon = utils.get_image_path('penguintvindicator.png')
			self._status_icon = PtvTrayIcon.PtvTrayIcon(self, icon)	

		self.main_window = MainWindow.MainWindow(self, use_internal_player, window=window, status_icon=self._status_icon, playlist=playlist) 
		self.main_window.layout=window_layout
		
		self._hildon_context = None
		if utils.RUNNING_HILDON:
			self._hildon_context = osso.Context("PenguinTV", utils.VERSION, False)

		#some signals
		self.connect('feed-added', self.__feed_added_cb)
		
	def _handle_db_exception(self):
		logging.debug("Got db exception, reconnecting to database")
		self.db._db.close()
		del self.db
		self.db = ptvDB.ptvDB(self.polling_callback, self._emit_change_setting)
		self.emit('new-database', self.db)
	
	@utils.db_except()
	def post_show_init(self):
		"""After we have Show()n the main window, set up some more stuff"""
		
		gst_player = self.main_window.get_gst_player()
		self.player = Player.Player(self, gst_player)
		if gst_player is not None:
			gst_player.connect('item-not-supported', self._on_item_not_supported)
			gst_player.connect('tick', self._on_gst_tick)
		self._gui_updater = UpdateTasksManager.UpdateTasksManager(UpdateTasksManager.GOBJECT, "gui updater")
		
		if utils.RUNNING_HILDON:
			hildon_listener = HildonListener.HildonListener(self, self.main_window.window, self._hildon_context)

		#WINDOWS
		#TODO: move this initialization till when we actually need these
		if utils.RUNNING_HILDON:
			self.window_preferences = PreferencesDialog.PreferencesDialog(gtk.glade.XML(os.path.join(utils.get_glade_prefix(),'hildon_dialogs.glade'), "window_preferences",'penguintv'),self) #MAGIC
		else:
			self.window_preferences = PreferencesDialog.PreferencesDialog(gtk.glade.XML(os.path.join(utils.get_glade_prefix(),'dialogs.glade'), "window_preferences",'penguintv'),self) #MAGIC
		self.window_preferences.hide()
		
		if utils.HAS_STATUS_ICON:
			self._status_icon.set_parent(self.main_window.window)
		
		#gconf
		if utils.HAS_GCONF:
			try:
				import gconf
			except:
				from gnome import gconf
			conf = gconf.client_get_default()
			conf.add_dir('/apps/penguintv',gconf.CLIENT_PRELOAD_NONE)
			conf.notify_add('/apps/penguintv/auto_resume',self._gconf_set_auto_resume)
			conf.notify_add('/apps/penguintv/poll_on_startup',self._gconf_set_poll_on_startup)
			conf.notify_add('/apps/penguintv/cache_images_locally',self._gconf_set_cache_images)
			conf.notify_add('/apps/penguintv/bt_max_port',self._gconf_set_bt_maxport)
			conf.notify_add('/apps/penguintv/bt_min_port',self._gconf_set_bt_minport)
			conf.notify_add('/apps/penguintv/bt_ul_limit',self._gconf_set_bt_ullimit)
			conf.notify_add('/apps/penguintv/feed_refresh_frequency',self._gconf_set_polling_frequency)
			conf.notify_add('/apps/penguintv/app_window_layout',self._gconf_set_app_window_layout)
			conf.notify_add('/apps/penguintv/feed_refresh_method',self._gconf_set_feed_refresh_method)
			conf.notify_add('/apps/penguintv/show_notifications',self._gconf_set_show_notifications)
			conf.notify_add('/apps/penguintv/auto_download',self._gconf_set_auto_download)
			conf.notify_add('/apps/penguintv/show_notification_always',self._gconf_set_show_notification_always)
			conf.notify_add('/apps/penguintv/auto_download_limiter',self._gconf_set_auto_download_limiter)
			conf.notify_add('/apps/penguintv/auto_download_limit',self._gconf_set_auto_download_limit)
			conf.notify_add('/apps/penguintv/media_storage_location',self._gconf_set_media_storage_location)
			conf.notify_add('/apps/penguintv/media_storage_style',self._gconf_set_media_storage_style)
			conf.notify_add('/apps/penguintv/use_article_sync',self._gconf_set_use_article_sync)
			#conf.notify_add('/apps/penguintv/sync_username',self._gconf_set_sync_username)
			#conf.notify_add('/apps/penguintv/sync_password',self._gconf_set_sync_password)
			conf.notify_add('/apps/penguintv/sync_readonly', self._gconf_set_sync_readonly)

		self._load_settings()
		
		#more DBUS
		if HAS_DBUS:
			sys_bus = dbus.SystemBus()
			try:
				sys_bus.add_signal_receiver(self._nm_properties_changed,
											'PropertiesChanged',
											'org.freedesktop.NetworkManager',
											'org.freedesktop.NetworkManager',
											'/org/freedesktop/NetworkManager')
										
				nm_ob = sys_bus.get_object("org.freedesktop.NetworkManager", 
										   "/org/freedesktop/NetworkManager")
										   
				self._nm_interface = dbus.Interface(nm_ob, 
											  "org.freedesktop.DBus.Properties")
				logging.info("Listening to NetworkManager")
				
			except:
				logging.warning("Couldn't connect to NetworkManager")
				self._nm_interface = None
		
		self.feed_list_view = self.main_window.feed_list_view
		self._entry_list_view = self.main_window.entry_list_view
		self._entry_view = self.main_window.entry_view
		
		self._entry_view.post_show_init()
		
		self._article_sync = self._setup_article_sync()
		self.window_preferences.set_article_sync(self._article_sync)
		self.window_preferences.set_article_sync_plugin( \
			self._article_sync.get_current_plugin())
			
		if self._nm_interface:
			self._nm_properties_changed()
			
		self._connect_signals()
		
		self.main_window.search_container.set_sensitive(False)
		if utils.HAS_SEARCH:
			#if self.db.cache_dirty or self.db.searcher.needs_index: #assume index is bad as well or if it is bad
			if self.db.searcher.needs_index: #if index is bad
				self.main_window.search_entry.set_text(_("Please wait..."))
				self.main_window.display_status_message(_("Reindexing Feeds..."))
				self.db.doindex(self._sensitize_search)
				self._populate_feeds(self._done_populating_dont_sensitize)
			else:
				self._populate_feeds(self._done_populating)
		else:
			##PROFILE: comment out
			self._populate_feeds(self._done_populating)
		#val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/selected_feed', 0)
		#if val > 0:
		#	self.feed_list_view.set_selected(val)
		val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/selected_entry', 0)
		if val > 0:
			#self._entry_list_view.set_selected(val)
			try:
				self.select_entry(val)
			except:
				pass
		#crash protection: if we crash, we'll have resetted selected_feed to 0
		self.db.set_setting(ptvDB.INT, '/apps/penguintv/selected_feed', 0)
		self.db.set_setting(ptvDB.INT, '/apps/penguintv/selected_entry', 0)
		if self._autoresume:
			gobject.idle_add(self.resume_resumable)
		self.update_disk_usage()
		# do this after we have the poller
		if self._firstrun and not utils.RUNNING_HILDON:
			self._import_default_feeds()
				
		#gtk.gdk.threads_leave()
		self.emit('app-loaded')
		self._app_loaded = True
		self.db.done_initializing()
		if utils.RUNNING_HILDON:
			self.main_window.feed_tabs.set_current_page(0)
		#self.save_settings()
		return False #for idler	

	def poller_ping_cb(self):
		if self._exiting:
			return False
		# -2 pid means we are ready to grab
		# -1 pid indicates we are already trying to grab
		# 0 pid indicates no poller, dead poller, or no other status.
		if self._remote_poller is None and self._remote_poller_pid == -2:
			logging.debug("poller ping, getting it")
			p = threading.Thread(None, self._get_poller)
			p.start()
		return True
	
	def _spawn_poller(self):
		self._remote_poller_pid = -2
		rundir = os.path.split(utils.__file__)[0]
		if rundir == "": rundir = "./"
		#logging.debug("RUN POLLER NOW")
		logging.debug("running poller: %s %s" % ('/usr/bin/env python', os.path.join(rundir, 'Poller.py')))
		subprocess.Popen(['/usr/bin/env', 'python', 
			os.path.join(rundir, 'Poller.py')])
	
	def _get_poller(self):
		self._remote_poller = None
		self._remote_poller_pid = -1
		gtk.gdk.threads_enter()
		bus = dbus.SessionBus()
		dubus = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/dbus')
		dubus_methods = dbus.Interface(dubus, 'org.freedesktop.DBus')
		gtk.gdk.threads_leave()
		
		wait_time = 5
		sleep_time = 0.3
		if utils.RUNNING_HILDON:
			wait_time = 5
			sleep_time = 2
		for i in range(0, wait_time):
			if self._exiting:
				break
			#sleep first to give Poller time to return its dbus call (which is
			#what triggered this function
			#don't want to deadlock mutual dbus calls
			time.sleep(sleep_time)
			gtk.gdk.threads_enter()
			logging.debug("Getting poller now")
			if dubus_methods.NameHasOwner('com.ywwg.PenguinTVPoller'):
				o = bus.get_object("com.ywwg.PenguinTVPoller", "/PtvPoller")
				poller = dbus.Interface(o, "com.ywwg.PenguinTVPoller.PollInterface")
				try:
					if poller.is_quitting():
						break
					else:
						self._remote_poller = poller
						self._remote_poller_pid = self._remote_poller.get_pid()
				except:
					gtk.gdk.threads_leave()
					break
				gtk.gdk.threads_leave()
				break
			gtk.gdk.threads_leave()
		if self._remote_poller is None:
			logging.error("Unable to start remote poller.  Polling will be done in-process")
			self._remote_poller_pid = 0
		else:
			logging.debug("Got poller")
			
		if utils.RUNNING_HILDON:
			# Now that we have the poller, do firstrun import
			gtk.gdk.threads_enter()
			if self._firstrun:
				self._import_default_feeds()
			gtk.gdk.threads_leave()
		
		#return success or fail
		return self._remote_poller_pid != 0
			
	def _check_poller(self):
		#logging.debug("Checking in on the poller: %i" % self._remote_poller_pid)
		if self._remote_poller_pid < 0:
			logging.debug("Not checking, no poller anyway (maybe it hasn't started up)")
		elif self._remote_poller_pid == 0:
			logging.debug("No poller, spawning it")
			self._spawn_poller()
		else:
			try:
				#is the process still running?
				os.kill(self._remote_poller_pid, 0)
			except Exception, e:
				logging.error("We lost the poller: %s" % str(e))
				if self._polling_taskinfo != -1:
					self._polled = 0
					self._polling_taskinfo = -1
					self._poll_message = ""
					if not utils.RUNNING_HILDON:
						self._article_sync.get_readstates_for_entries(self._poll_new_entries)
						self._poll_new_entries = []
					self.main_window.update_progress_bar(-1, MainWindow.U_POLL)
					self.main_window.display_status_message(_("Polling Error"),MainWindow.U_POLL)
					gobject.timeout_add(2000, self.main_window.display_status_message,"")
				self._remote_poller = None
				self._remote_poller_pid = 0
				self._spawn_poller()
				return True
			if self._polling_taskinfo == -1:
				#logging.debug("pinging the poller")
				try:
					#and is it still responding?
					self._remote_poller.ping()
					#logging.debug("Poller still running")
				except Exception, e:
					logging.debug("no ping response, rerunning poller: %s" % str(e))
					os.kill(self._remote_poller_pid, 15)
					self._spawn_poller()
					if self._get_poller():
						logging.debug("restarted poller")
					else:
						logging.debug("failed to restart poller")
			#else:
			#	logging.debug("not pinging while polling")
				
		return True
		
	def _setup_article_sync(self):
		if utils.ENABLE_ARTICLESYNC:
			enabled = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/use_article_sync', False)
		else:
			enabled = False
		plugin = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/article_sync_plugin', "")
		readonly = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/sync_readonly', False)
		article_sync = ArticleSync.ArticleSync(self, self._entry_view,  plugin, 
							enabled, readonly)
	
		self.window_preferences.set_use_article_sync(enabled)
		self.window_preferences.set_article_sync_readonly(readonly)
		return article_sync
		
	def sync_authenticate(self, newplugin=None, cb=None):
		logging.debug("authenticating sync settings")
		
		def authenticate_cb(result):
			if result:
				self._sync_articles_put()
				#self._sync_articles_get()
				self.window_preferences.set_sync_status(_("Logged in"))
			else:
				self.window_preferences.set_sync_status(_("Not Logged in"))
			if cb is not None:
				cb(result)
			return False
		
		def _do_authenticate():
			if not self._article_sync.is_loaded():
				logging.debug("plugin not loaded yet")
				return True
			self._article_sync.authenticate(cb=authenticate_cb)
			return False
		
		#username = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/sync_username', "")
		#self._article_sync.set_username(username)
		#password = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/sync_password', "")
		#self._article_sync.set_password(password)
		
		if newplugin is not None:
			logging.debug("telling old plugin to clean up")
			self._article_sync.finish()
			logging.debug("old plugin done")
		else:
			if self._article_sync.get_current_plugin() is None:
				logging.debug("no current plugin specified to authenticate")
				return
			
		if not self._article_sync.is_loaded():
			logging.debug("app loading the plugin")
			self._article_sync.load_plugin(newplugin)
			gobject.timeout_add(500, _do_authenticate)
		else:
			_do_authenticate()
			
	def _sync_articles_put(self):
		timestamp = self.db.get_setting(ptvDB.INT, 'article_sync_timestamp', int(time.time()))
		self._article_sync.submit_readstates_since(timestamp, self.__put_readstates_cb)

	def __put_readstates_cb(self, success):
		self._sync_articles_get()
		
	def _sync_articles_get(self):
		#timestamp = self.db.get_setting(ptvDB.INT, 'article_sync_timestamp', int(time.time()) - (60 * 60 * 24))
		# because clocks might be different, make it everything in the past day
		#timestamp -= 60 * 60 * 24
		#self._article_sync.get_readstates_since(timestamp)
		
		hashlist = self.db.get_unread_hashes()
		logging.debug("getting readstates for %i entries" % (len(hashlist)))
		self._article_sync.get_readstates(hashlist)

	def __got_readstates_cb(self, o, viewlist):
		if self._exiting:
			#logging.debug("got readstates, but no time to apply them")
			return
		if len(viewlist) > 0:
			self.mark_entrylist_viewstate(viewlist, True)
			self.emit('entries-viewed', viewlist)
		#else:
		#	logging.debug("stamping even though none found")
		#logging.debug("SETTING GCONF TIMESTAMP=========")
		self.db.set_setting(ptvDB.INT, 'article_sync_timestamp', int(time.time()))
		
	def __sent_readstates_cb(self, o):
		def __do():
			self.db.set_setting(ptvDB.INT, 'article_sync_timestamp', int(time.time()))
			return False
		gobject.idle_add(__do)
		return False
		

	#def _submit_new_readstates(self):
	#	def _submit_cb(result):
	#		if result:
	#			logging.debug("success submitting readstates!")
	#			self.db.set_setting(ptvDB.INT, 'article_sync_timestamp', int(time.time()))
	#		else:
	#			logging.debug("trouble submitting readstates")
	#		return False
	#
	#	logging.debug("submitting new readstates, maybe")
	#	if not self._article_sync.is_enabled():
	#		logging.debug("not enabled")
	#		return True
	#	if not self._article_sync.is_authenticated():
	#		logging.debug("not authenticated (trying again)")
	#		self._article_sync.authenticate(lambda x: self._startup_article_sync(x, False))
	#	else:
	#		logging.debug("going for it!")
	#		timestamp = self.db.get_setting(ptvDB.INT, 'article_sync_timestamp', 
	#						int(time.time()) - (1 * 24 * 60 * 60)) #one day
	#		self._article_sync.submit_readstates_since(timestamp, _submit_cb)
	#			
	#	return True
			
	def _import_default_feeds(self):
		found_subs = False
		for path in (os.path.join(utils.GetPrefix(), "share" ,"penguintv"),
					 os.path.join(utils.GetPrefix(), "share"),
					 os.path.join(utils.GetPrefix(),"share","sugar","activities","ptv","share"),
					 os.path.join(os.path.split(os.path.split(utils.__file__)[0])[0],'share'),
					 "/usr/share/penguintv"):
			try:
				if utils.HAS_PYXML:
					subs_name = "defaultsubs.opml"
				else:
					subs_name = "defaultsubs.txt"
				os.stat(os.path.join(path,subs_name))
				found_subs = True
				break
			except:
				continue
		if not found_subs:
			logging.error("ptvdb: error finding default subscription file.")
			sys.exit()
		f = open(os.path.join(path,subs_name), "r")
		self.main_window.display_status_message(_("Polling feeds for the first time..."))
		self.import_subscriptions(f, utils.HAS_PYXML)
		
	def _connect_signals(self):
		#self._entry_list_view.connect('entry-selected', self.__entry_selected_cb)
		self.feed_list_view.connect('state-change', self.__feedlist_state_change_cb)
		#self._entry_view.connect('entry-selected', self.__entry_selected_cb)
		self._entry_view.connect('entries-viewed', self.__entries_viewed_cb)
		self._article_sync.connect('got-readstates', self.__got_readstates_cb)
		self._article_sync.connect('sent-readstates', self.__sent_readstates_cb)
		
		self.feed_list_view.set_entry_view(self._entry_view)	
		self._entry_list_view.set_entry_view(self._entry_view)
		
	#def __entry_selected_cb(self, o, entry_id, feed_id):
	#	if self._state == MANUAL_SEARCH or self._state == TAG_SEARCH and feed_id != -1:
	#		self.select_feed(feed_id)
	#	#FIXME: we're not passing the query for highlighting purposes here
	#	if self.db.get_flags_for_feed(feed_id) & ptvDB.FF_MARKASREAD == 0:
	#		#self.db.set_entry_read(entry_id, 1)
	#		self._delayed_set_viewed(feed_id, [entry_id])
	#			
	#def __entries_selected_cb(self, o, feed_id, entrylist):
	#	#self.mark_entrylist_viewstate(feed_id, entrylist, False)
	#	self._delayed_set_viewed(feed_id, entrylist)
	
	def __entries_viewed_cb(self, o, viewlist):
		if self._exiting:
			return
		#logging.debug("got viewlist: %s" % str(viewlist))
		self.mark_entrylist_viewstate(viewlist, True)
		
	def __entries_unviewed_cb(self, o, unviewedlist):
		if self._exiting:
			return
		self.mark_entrylist_viewstate(unviewedlist, False)
		
	def __feedlist_state_change_cb(self, o, new_state):
		self.set_state(new_state)
		
	@utils.db_except()
	def __online_status_changed(self, o, connected):
		self._net_connected = connected
		if not self._net_connected:
			if self._update_thread is not None:
				if self._update_thread.isAlive() and not self._update_thread.isDying():
					updater, db = self._get_updater()
					db.interrupt_poll_multiple()
			if self.db:
				self.db.interrupt_poll_multiple()
		
	@utils.db_except()
	def _load_settings(self):
		val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/feed_refresh_frequency', 60)
		self.polling_frequency = val*60*1000
		self.window_preferences.set_feed_refresh_frequency(self.polling_frequency/(60*1000))
			
		val = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method')
		if val is None: 
			self.feed_refresh_method=REFRESH_AUTO
		else:
			if val == 'auto':
				self.feed_refresh_method=REFRESH_AUTO
			elif val == 'specified':
				self.feed_refresh_method=REFRESH_SPECIFIED
			elif val == 'never':
				self.feed_refresh_method=REFRESH_NEVER
			else:
				self.feed_refresh_method=REFRESH_AUTO
		self.window_preferences.set_feed_refresh_method(self.feed_refresh_method)
		
		
		if self.feed_refresh_method == REFRESH_AUTO:
			gobject.timeout_add(AUTO_REFRESH_FREQUENCY,self.do_poll_multiple, AUTO_REFRESH_FREQUENCY)
		elif self.feed_refresh_method == REFRESH_SPECIFIED:
			gobject.timeout_add(self.polling_frequency,self.do_poll_multiple, self.polling_frequency)
				
		val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/bt_min_port', 6881)
		self._bt_settings['min_port']=val
		val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/bt_max_port', 6999)
		self._bt_settings['max_port']=val
		val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/bt_ul_limit', 0)
		self._bt_settings['ul_limit']=val
		self.window_preferences.set_bt_settings(self._bt_settings)
		self.mediamanager.set_bt_settings(self._bt_settings)
		
		val = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/auto_resume', True)
		self._autoresume = val
		self.window_preferences.set_auto_resume(val)
		
		val = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/poll_on_startup', True)
		self.poll_on_startup = val
		self.window_preferences.set_poll_on_startup(val)
		
		val = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/cache_images_locally', False)
		self.window_preferences.set_cache_images(val)
		
		val = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/auto_download', False)
		self._auto_download = val
		self.window_preferences.set_auto_download(val)
		
		val = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/show_notification_always', True)
		if utils.HAS_STATUS_ICON:
			self._status_icon.set_show_always(val)
		self.window_preferences.set_show_notification_always(val)
		
		val = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/auto_download_limiter', False)
		self._auto_download_limiter = val
		self.window_preferences.set_auto_download_limiter(val)
		
		if utils.RUNNING_SUGAR:
			default_max = 50*1024
		else:
			default_max = 1024*1024
		val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/auto_download_limit', default_max)
		self._auto_download_limit = val
		self.window_preferences.set_auto_download_limit(val)
		
		val = self.mediamanager.get_media_dir()
		self.window_preferences.set_media_storage_location(val)
		
		val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/media_storage_style', 0)
		self.window_preferences.set_media_storage_style(val)
		self.mediamanager.set_storage_style(val)
		
	@utils.db_except()
	def save_settings(self):
		if self.main_window.feed_pane is not None:
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/feed_pane_position', self.main_window.feed_pane.get_position())
		if self.main_window.entry_pane is not None:
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/entry_pane_position', self.main_window.entry_pane.get_position())
		if self.main_window.app_window is not None:
			if self.main_window.window_maximized == False:
				x,y=self.main_window.app_window.get_position()
				w,h=self.main_window.app_window.get_size()
				self.db.set_setting(ptvDB.INT, '/apps/penguintv/app_window_position_x',x)
				self.db.set_setting(ptvDB.INT, '/apps/penguintv/app_window_position_y',y)
			else: #grabbing the size when we are maximized is pointless, so just go by the old resized size
				w = self.db.get_setting(ptvDB.INT, '/apps/penguintv/app_window_size_x', 500)
				h = self.db.get_setting(ptvDB.INT, '/apps/penguintv/app_window_size_y', 500)
				w,h=(-abs(w),-abs(h))
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/app_window_size_x',w)
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/app_window_size_y',h)
		
		self.db.set_setting(ptvDB.STRING, '/apps/penguintv/app_window_layout',self.main_window.layout)
		if self.feed_refresh_method==REFRESH_AUTO:
			self.db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method','auto')
		elif self.feed_refresh_method == REFRESH_SPECIFIED:
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/feed_refresh_frequency',self.polling_frequency/(60*1000))
			self.db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method','specified')	
		else:
			self.db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method','never')
		self.db.set_setting(ptvDB.INT, '/apps/penguintv/bt_max_port',self._bt_settings['max_port'])
		self.db.set_setting(ptvDB.INT, '/apps/penguintv/bt_min_port',self._bt_settings['min_port'])
		self.db.set_setting(ptvDB.INT, '/apps/penguintv/bt_ul_limit',self._bt_settings['ul_limit'])
		self.db.set_setting(ptvDB.BOOL, '/apps/penguintv/auto_resume',self._autoresume)
		self.db.set_setting(ptvDB.BOOL, '/apps/penguintv/poll_on_startup',self.poll_on_startup)
		self.db.set_setting(ptvDB.BOOL, '/apps/penguintv/auto_download',self._auto_download)
		self.db.set_setting(ptvDB.BOOL, '/apps/penguintv/auto_download_limiter',self._auto_download_limiter)
		self.db.set_setting(ptvDB.INT, '/apps/penguintv/auto_download_limit',self._auto_download_limit)
		if self.feed_list_view.filter_setting > FeedList.NONE:
			self.db.set_setting(ptvDB.STRING, '/apps/penguintv/default_filter',self.feed_list_view.filter_name)
		else:
			self.db.set_setting(ptvDB.STRING, '/apps/penguintv/default_filter',"")
		if not self.main_window.changing_layout:
			val = self.feed_list_view.get_selected()
			if val is None: val = 0
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/selected_feed', val)
			val = self._entry_list_view.get_selected_id()
			if val is None: val = 0
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/selected_entry', val)
		
		media_dir = self.window_preferences.get_media_storage_location()
		if media_dir is not None:
			self.db.set_setting(ptvDB.STRING, '/apps/penguintv/media_storage_location', media_dir)
		self.db.set_setting(ptvDB.INT, '/apps/penguintv/media_storage_style', self.mediamanager.get_storage_style())
		enabled = self.window_preferences.get_use_article_sync()
		self.db.set_setting(ptvDB.BOOL, '/apps/penguintv/use_article_sync', enabled)
		readonly = self.window_preferences.get_article_sync_readonly()
		self.db.set_setting(ptvDB.BOOL, '/apps/penguintv/sync_readonly', readonly)
		#self.db.set_setting(ptvDB.BOOL, '/apps/penguintv/use_internal_player', self.player.using_internal_player())
	
	@utils.db_except()
	def resume_resumable(self):
		list = self.db.get_resumable_media()
		if list:
			gobject.idle_add(self._resumer_generator(list).next)
		return False #to cancel idler
		
	@utils.db_except()
	def _resumer_generator(self, list):
		for medium in list:
			self.mediamanager.download(medium['media_id'], False, True) #resume please
			self.db.set_entry_read(medium['entry_id'],False)
			self.feed_list_view.update_feed_list(medium['feed_id'],['icon'])
			yield True
		yield False
		
	def is_exiting(self):
		return self._exiting
		
	def do_quit(self):
		"""save and shut down all our threads"""
		
		##good breakpoint for gc analysis
		#import code
		#code.interact()
		
		logging.info('ptv quitting')
		self._exiting=1
		self._entry_view.finish()
		self.feed_list_view.interrupt()
		if self._update_thread is not None:
			if self._update_thread.isAlive():
				self._update_thread.goAway()
				
		if self._article_sync.is_enabled():
			self.main_window.display_status_message(_("Synchronizing Articles"))

		self.main_window.finish()
		logging.info('stopping downloads')
		
		self.stop_downloads()
		logging.info('saving settings')
		self.save_settings()
		
		#if anything is downloading, report it as paused, because we pause all downloads on quit
		feed_cache = self.feed_list_view.get_feed_cache()
		
		feed_dict = {}
		for feed_id, flag, unread, total, pollfail, firstentrytitle in feed_cache:
			feed_dict[feed_id] = unread
			
		adjusted_cache = [[c[0],(c[1] & ptvDB.F_DOWNLOADING and c[1]-ptvDB.F_DOWNLOADING+ptvDB.F_PAUSED or c[1]),c[2],c[3],c[4],c[5]] for c in feed_cache]
		self.db.set_feed_cache(adjusted_cache)
			
		logging.info('stopping mediamanager')
		self.mediamanager.finish()
		
		self._article_sync.finish()
		def article_sync_wait(giveup):
			if time.time() > giveup:
				logging.warning("articlesync taking too long, quitting anyway")
			elif self._article_sync.is_working():
				return True
				
			#while threading.activeCount()>1:
			#	print threading.enumerate()
			#	print str(threading.activeCount())+" threads active..."
			#	time.sleep(1)
			
			logging.info('stopping db')
			self.db.finish(majorsearchwait=False)	
		
			if not utils.RUNNING_SUGAR and not utils.RUNNING_HILDON:
				logging.info('main_quit')
				gtk.main_quit()
			self._exiting = 2
			return False
		toolong = time.time() + 120
		gobject.timeout_add(250, article_sync_wait, toolong)
	
	def is_quit_complete(self):
		return self._exiting > 1
			
	def write_feed_cache(self):
		self.db.set_feed_cache(self.feed_list_view.get_feed_cache())
		
	def do_poll_multiple(self, was_setup=None, arguments=0, feeds=None, message=None, local=False):
		""""was_setup":  So do_poll_multiple is going to get called by timers 
			and manually, and we needed some way of saying "I've got a new 
			frequency, stop the old timer and start the new one."  so it 
			checks to see that the frequency it 'was setup' with is the same 
			as the current frequency.  If not, exit with False to stop 
			the timer."""
			
		if self._state == MAJOR_DB_OPERATION or not self._app_loaded or self._exiting:
			return True
		
		if was_setup is not None:
			if self.feed_refresh_method == REFRESH_AUTO:
				pass
				#if was_setup==0: #initial poll
				#	arguments = arguments | ptvDB.A_ALL_FEEDS
			elif self.feed_refresh_method == REFRESH_SPECIFIED:
				if was_setup!=self.polling_frequency and was_setup!=0:
					return False
			else:
				return False
					
		if self.feed_refresh_method==REFRESH_AUTO:
			arguments = arguments | ptvDB.A_AUTOTUNE
					
		if not self._net_connected:
			return True

		if self._polling_taskinfo != -1:
			if time.time() - self._polling_taskinfo > 20*60:
				#logging.debug("reset polling taskinfo 972")
				self._polling_taskinfo = -1
			else:
				return True
				
		if utils.RUNNING_HILDON and was_setup is not None:
			if self.mediamanager.get_download_count() > 0:
				logging.debug("delaying poll until downloads are complete")
		
		if message is None:
			self._poll_message = _("Polling Feeds...")
		else:
			self._poll_message = message

		self.main_window.update_progress_bar(0,MainWindow.U_POLL)
		self.main_window.display_status_message(self._poll_message, MainWindow.U_POLL)
		self._poll_new_entries = []
		
		if self._remote_poller is not None and not local:
			self._polling_thread = REMOTE
			logging.debug("Using remote poller")
			if feeds is None:
				try:
					self._remote_poller.poll_all(arguments, "FinishedCallback")
				except Exception, e:
					#don't reset poller, maybe it just timed out. _check_poller
					#will find out for sure
					logging.debug("lost the poller, trying again with local poller (err: %s)" % str(e))
					return self.do_poll_multiple(was_setup, arguments, feeds, message, local=True)
			else:
				try:
					self._remote_poller.poll_multiple(arguments, feeds, "FinishedCallback")
				except:
					logging.debug("lost the poller, trying again with local poller (2)")
					return self.do_poll_multiple(was_setup, arguments, feeds, message, local=True)
			self._polling_taskinfo = int(time.time())
		else:	
			self._polling_thread = LOCAL
			logging.debug("Polling in-process")
			updater, db = self._get_updater()
			task_id = updater.queue(db.poll_multiple, (arguments,feeds))
			if arguments & ptvDB.A_ALL_FEEDS==0:
				self._gui_updater.queue(self.main_window.display_status_message,_("Feeds Updated"), task_id, False)
				#insane: queueing a timeout
				self._gui_updater.queue(gobject.timeout_add, 
										(2000, self.main_window.display_status_message, ""), 
									    task_id, 
										False)
			self._polling_taskinfo = self._gui_updater.queue(self.update_disk_usage, 
														   None, 
														   task_id, 
														   False) #because this is also waiting
			if self._auto_download == True:
				self._polling_taskinfo = self._gui_updater.queue(self._auto_download_unviewed, 
															   None, 
															   task_id)
		#gtk.gdk.threads_leave()
		if was_setup!=0:
			return True
		return False
		
	def poll_finished_cb(self, total):
		"""only called over dbus when poller.py finishes.  Keep this fast to
		   prevent timeouts over dbus."""
		self._gui_updater.queue(self.update_disk_usage)
		if self._auto_download == True:
			self._gui_updater.queue(self._auto_download_unviewed)
		self._gui_updater.set_completed(self._polling_taskinfo)
	
	@utils.db_except()
	def _auto_download_unviewed(self):
	
		"""Automatically download any unviewed media.  Runs every five minutes 
		when auto-polling, so make sure is good"""
		
		if self._exiting:
			return
		
		download_list=self.db.get_media_for_download(False) #don't resume paused downloads
		if len(download_list)==0:
			return #no need to bother

		logging.debug("files ready to download:")		
		total_size = 0
		for d in download_list:
			title = self.db.get_feed_title(d[3])
			logging.debug("%s, %i: %i" % (title, d[2], d[1])) 
			total_size=total_size+int(d[1])
			
		logging.info("adding up downloads, we need %i bytes" % (total_size))
			
		if self._free_media_space(total_size):
			for d in download_list:
				self.mediamanager.download(d[0])
				self.emit('entry-updated', d[2], d[3])
		else:
			logging.error("we were unable to free up enough space.")
			#print download_list
		self.update_disk_usage()
		
	@utils.db_except()	
	def _free_media_space(self, size_needed):
		
		"""deletes media so that we have at least 'size_needed' bytes of free space.
		Returns True if successful, returns False if not (ie, too big)"""
		
		disk_total = utils.get_disk_total(self.mediamanager.get_media_dir())
		disk_usage = self.mediamanager.get_disk_usage()
		disk_free = utils.get_disk_free(self.mediamanager.get_media_dir())
		
		
		#adjust actual free space so we never fill up the drive
		if utils.RUNNING_SUGAR or utils.RUNNING_HILDON:
			free_buffer = 300000000 # 300 meg
		else:
			free_buffer =  10000000 # 10 meg
			
		size_to_free = 0
		if self._auto_download_limiter:
			if self._auto_download_limit*1024 - disk_usage < size_needed:
				size_to_free = size_needed - (self._auto_download_limit*1024 - disk_usage)

		if disk_free + size_to_free < size_needed + free_buffer:
			size_to_free = size_needed + free_buffer - disk_free
			
		#if the disk isn't big enough, drop it like it's hot...
		if disk_total - free_buffer < size_needed:
			return False
		
		#if the media ain't big enough, pop it like it's hot...
		if disk_usage < size_to_free:
			return False
			
		if size_to_free == 0:
			return True
			
		#get the media that's currently in the player so we don't delete it
		if utils.HAS_GSTREAMER:
			media_in_player = self.player.get_queue()
			media_in_player = [m[4] for m in media_in_player]
			
		media_to_remove = []
		removed_size = 0
		for media_id,entry_id,feed_id,filename,date in self.db.get_deletable_media():
			if removed_size >= size_to_free:
				disk_usage = self.mediamanager.get_disk_usage()
				if self._auto_download_limiter:
					if self._auto_download_limit*1024 - disk_usage < size_needed:
						logging.error("didn't free up the space like we thought1")
						return False
				if utils.get_disk_free(self.mediamanager.get_media_dir()) < size_needed + free_buffer:
					logging.error("didn't free up the space like we thought2" + str(utils.get_disk_free(self.mediamanager.get_media_dir())))
					return False
				return True
				
			#don't remove anything that's queued in the player
			if utils.HAS_GSTREAMER:
				if media_id in media_in_player:
					continue
			
			try:
				size = os.stat(filename)[6]
				removed_size += size
				logging.info("removing: %s %i bytes for a total of %i" % (filename, size, removed_size))
				self.db.delete_media(media_id)
				self.db.set_entry_read(entry_id, True)
				self.emit('entry-updated', entry_id, feed_id)
			except OSError, e:
				logging.warning("Couldn't remove %s: %s" % (filename, str(e)))
		return False
		
	@utils.db_except()
	def add_search_tag(self, query, tag_name):
		self.db.add_search_tag(query, tag_name)
		#could raise ptvDB.TagAlreadyExists, let it go
		self._saved_search = self.main_window.search_entry.get_text()
		self.emit('tags-changed', 0)
		while gtk.events_pending(): #wait for the list to update
			gtk.main_iteration()
		index = self.main_window.get_filter_index(tag_name)
		if index is not None:
			self.main_window.search_entry.set_text("")
			self.main_window.set_active_filter(index)
		else:
			logging.warning("we just added a search tag but it's not in the list")
		
	@utils.db_except()	
	def remove_search_tag(self, tag_name):
		self.db.remove_tag(tag_name)
		self.emit('tags-changed', 0)
		while gtk.events_pending():
			gtk.main_iteration()
			
	@utils.db_except()
	def change_search_tag(self, current_tag, new_tag=None, new_query=None):
		if new_tag is not None:
			self.db.rename_tag(current_tag, new_tag)
			self.main_window.rename_filter(current_tag, new_tag)
			current_tag = new_tag
			
		if new_query is not None:
			self.db.change_query_for_tag(current_tag, new_query)
			index = self.main_window.get_active_filter()[1]
			if self.main_window.get_active_filter()[0] == current_tag:
				self.set_state(TAG_SEARCH) #redundant, but good practice
				self._show_search(new_query, self._search(new_query))
		
	@utils.db_except()		
	def apply_tags_to_feed(self, feed_id, old_tags, new_tags):
		"""take a list of tags and apply it to a feed"""
		old_set = set(old_tags)
		new_set = set(new_tags)
		removed_tags = list(old_set.difference(new_set))
		added_tags = list(new_set.difference(old_set))
		for tag in removed_tags:
			self.db.remove_tag_from_feed(feed_id, tag)
		for tag in added_tags:
			self.db.add_tag_for_feed(feed_id, tag)	
		if removed_tags or added_tags:
			self.feed_list_view.set_selected(feed_id)
		self.emit('tags-changed', 0)
		self.feed_list_view.filter_all(False)
		#if old_tags is not None:
		#	if ptvDB.NOTIFYUPDATES in old_tags:
		#		self.emit('notify-tags-changed')
		#		return #don't need the next test
		#if new_tags is not None:
		#	if ptvDB.NOTIFYUPDATES in new_tags:
		#		self.emit('notify-tags-changed')
	
	def _populate_feeds(self, callback=None, subset=FeedList.ALL):
		self.set_state(MAJOR_DB_OPERATION)
		self.main_window.display_status_message(_("Loading Feeds..."))
		self.feed_list_view.populate_feeds(callback, subset)
					
	def display_entry(self, entry_id, set_read=True, query=""):
		#FIXME:  no more way to display a specific entry when download is
		# clicked
		
		#if entry_id is not None:
		#	item = self.db.get_entry(entry_id)
		#	media = self.db.get_entry_media(entry_id)
		#	if media:
		#		item['media']=media
		#else:
		#	self._entry_view.display_item()
		#	return
		#	
		#if item.has_key('media') == False:
		#	if item['read']==0 and set_read:
		#		item['read'] = 1
		#		self.db.set_entry_read(entry_id,1)
		#		#self._entry_list_view.mark_as_viewed(entry_id)
		#		#self.feed_list_view.mark_entries_read(1, feed_id=item['feed_id'])
		#		for f in self.db.get_pointer_feeds(item['feed_id']):
		#			self.feed_list_view.update_feed_list(f,['readinfo','icon'])
		##self._entry_view.display_item(item, query)
		pass
	
	def display_custom_entry(self, message):
		"""Used by other classes so they don't need to know about EntryView"""
		self._entry_view.display_custom_entry(message)
		
	def undisplay_custom_entry(self):
		"""Used by other classes so they don't need to know about EntryView"""
		self._entry_view.undisplay_custom_entry()
	
	@utils.db_except()
	def activate_link(self, link):
		"""links can be basic hrefs, or they might be custom penguintv commands"""
		import urlparse
		try:
			parsed_url = urlparse.urlparse(link)
		except:
			logging.warning("Invalid link clicked: %s" % (link,))
			return
		action=parsed_url[0] #protocol
		
		if action == "":
			splitted = link.split(':')
			if len(splitted) == 2:
				try:
					action = splitted[0]
					item=int(splitted[1])
				except:
					logging.warning("Invalid link item: %s" % (link,))
					return
		else:
			parameters=parsed_url[3]
			http_arguments=parsed_url[4]
			anchor = parsed_url[5]
			if action not in ("http", "https", "file"): 
				try:
					item=int(parsed_url[1])
				except:
					try:
						item=int(parsed_url[2].replace("/",""))
					except:
						logging.warning("Invalid link item: %s" % (link,))
						return 

		if action == "keep":
			entry = self.db.get_entry(item)
			self.db.set_entry_keep(item, 1)
			self.emit('entry-updated', item, entry['feed_id'])
		elif action == "unkeep":
			entry = self.db.get_entry(item)
			self.db.set_entry_keep(item, 0)
			self.emit('entry-updated', item, entry['feed_id'])
		elif action == "download":
			self.mediamanager.unpause_downloads()
			self.mediamanager.download(item)
			entry_id = self.db.get_entryid_for_media(item)
			#self.db.set_media_viewed(item,False)
			feed_id = self.db.get_entry(entry_id)['feed_id']
			self.emit('entry-updated', entry_id, feed_id)
		elif action=="resume" or action=="tryresume":
			self.do_resume_download(item)
		elif action=="play":
			if utils.RUNNING_SUGAR and not utils.HAS_GSTREAMER:
				dialog = gtk.Dialog(title=_("Enclosures Disabled"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
				label = gtk.Label("Launching enclosed files is disabled on olpc until a mime system is developed. \n If you install GStreamer PenguinTV can use that. (email owen-olpc@ywwg.com for more info)")
				dialog.vbox.pack_start(label, True, True, 0)
				label.show()
				dialog.set_transient_for(self.main_window.get_parent())
				response = dialog.run()
				dialog.hide()
				del dialog
				return
			media = self.db.get_media(item)
			entry = self.db.get_entry(media['entry_id'])
			feed_title = self.db.get_feed_title(entry['feed_id'])
			if utils.is_known_media(media['file']):
				self.player.play(media['file'], utils.my_quote(feed_title) + " " + utils.get_hyphen() + " " + entry['title'], media['media_id'], context=self._hildon_context)
			else:
				if HAS_GNOME:
					try:
						gnome.url_show(media['file'])
					except:
						webbrowser.open_new_tab(media['file'])
				else:
					webbrowser.open_new_tab(media['file'])
			if not entry['keep']:
				self.db.set_entry_read(media['entry_id'],True)
			self.emit('entry-updated', media['entry_id'], entry['feed_id'])
		elif action=="downloadqueue":
			self.mediamanager.unpause_downloads()
			self.mediamanager.download(item, True)
			self.db.set_media_viewed(item,False)
			entry_id = self.db.get_entryid_for_media(item)
			feed_id = self.db.get_entry(entry_id)['feed_id']
			self.emit('entry-updated', entry_id, feed_id)
		elif action=="queue":
			logging.info(parsed_url)
		elif action=="stop":
			newitem={}
			newitem['media_id']=item
			newitem['entry_id']=self.db.get_entryid_for_media(newitem['media_id'])
			self.do_cancel_download(newitem)
		elif action=="pause":
			self.do_pause_download(item)
		elif action=="clear" or action=="cancel":
			newitem={}
			newitem['media_id']=item
			newitem['entry_id']=self.db.get_entryid_for_media(newitem['media_id'])
			self.do_cancel_download(newitem)
		elif action=="delete":
			self.delete_media(item)
			entry_id = self.db.get_entryid_for_media(item)
			feed_id = self.db.get_entry(entry_id)['feed_id']
			self.emit('entry-updated', entry_id, feed_id)
		elif action=="reveal":
			if utils.is_kde():
				reveal_url = "file:" + parsed_url[1] + parsed_url[2]
				os.system('konqueror --select ' + reveal_url + ' &')
			else:
				reveal_url = "file:"+os.path.split(parsed_url[1]+parsed_url[2])[0]
				reveal_url = reveal_url.replace("%20"," ")
				if HAS_GNOME:
					try:
						gnome.url_show(reveal_url)
					except:
						webbrowser.open_new_tab(reveal_url)
				else:
					webbrowser.open_new_tab(reveal_url)
		elif action == "http" or action == "https":
			try:
				if len(parameters)>0:
					parameters = ";"+parameters
				else:
					parameters = ""
			except:
				parameters = ""
			try:
				if len(http_arguments)>0:
					http_arguments = "?"+http_arguments
				else:
					http_arguments=""
			except TypeError: #"len() of unsized object"
				http_arguments=""
			try:
				if len(anchor)>0:
					anchor="#"+anchor
				else:
					anchor=""
			except:
				anchor=""
			quoted_url = urllib.quote(parsed_url[1]+parsed_url[2])
			#however don't quote * (yahoo news don't like it quoted)
			quoted_url = string.replace(quoted_url,"%2A","*")
			quoted_url = string.replace(quoted_url,"%2B","+")
			uri = parsed_url[0]+"://"+quoted_url+parameters+http_arguments+anchor
			if utils.RUNNING_SUGAR:
				from sugar.activity import activityfactory
				activityfactory.create_with_uri('org.laptop.WebActivity', uri)
			elif utils.RUNNING_HILDON:
				import osso.rpc
				rpc_handler = osso.rpc.Rpc(self._hildon_context)
				logging.debug("Trying to launch maemo browser")
				rpc_handler.rpc_run_with_defaults('osso_browser', 'open_new_window', (uri,))
			elif HAS_GNOME:
				try:
					gnome.url_show(uri)
				except:
					webbrowser.open_new_tab(uri)
			else:
				webbrowser.open_new_tab(uri)
		elif action=="file":
			logging.info(parsed_url[0]+"://"+urllib.quote(parsed_url[1]+parsed_url[2]))
			if HAS_GNOME:
				try:
					gnome.url_show(parsed_url[0]+"://"+urllib.quote(parsed_url[1]+parsed_url[2]))
				except:
					webbrowser.open_new_tab(parsed_url[0]+"://"+urllib.quote(parsed_url[1]+parsed_url[2]))
			else:
				webbrowser.open_new_tab(parsed_url[0]+"://"+urllib.quote(parsed_url[1]+parsed_url[2]))
		elif action=="pane":
			if parsed_url[2] == "back":
				self.main_window.pane_to_feeds()
		
	@utils.db_except()	
	def download_entry(self, entry_id):
		entry = self.db.get_entry(entry_id)
		self.mediamanager.download_entry(entry_id)
		if entry['read']:
			self.emit('entries-unviewed', [(entry['feed_id'], (entry_id,))])
		#FIXME: oh yeah, bit of a hack
		self.feed_list_view.update_feed_list(entry['feed_id'], update_what=['icon'], update_data={'icon':'gtk-execute'})

	@utils.db_except()
	def download_unviewed(self):
		self.mediamanager.unpause_downloads()
		download_list=self.db.get_media_for_download()

		if len(download_list) > 0:
			for d in download_list:
				title = self.db.get_feed_title(d[3])
				logging.info("%s, %i: %i" % (title, d[2], d[1])) 
				
		total_size=0
		
		if len(download_list)==0:
			dialog = gtk.Dialog(title=_("No Unviewed Media"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("There is no unviewed media to download."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			dialog.set_transient_for(self.main_window.get_parent())
			response = dialog.run()
			dialog.hide()
			del dialog
			return
		for d in download_list:
			total_size=total_size+int(d[1])
		if total_size>100000000: #100 megs
			dialog = gtk.Dialog(title=_("Large Download"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("If PenguinTV downloads all of the unviewed media, \nit will take %(space)s. Do you wish to continue?") % {'space':utils.format_size(total_size)})
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			dialog.set_transient_for(self.main_window.get_parent())
			response = dialog.run()
			dialog.hide()
			del dialog
			if response != gtk.RESPONSE_ACCEPT:
				return
				
		if self._free_media_space(total_size):
			gobject.idle_add(self._downloader_generator(download_list).next)
		else:
			dialog = gtk.Dialog(title=_("Not Enough Free Space"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("PenguinTV was unable to free enough disk space to download %(space)s of media.") % {'space':utils.format_size(total_size)})
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			dialog.set_transient_for(self.main_window.get_parent())
			response = dialog.run()
			dialog.hide()
			del dialog

	@utils.db_except()
	def _downloader_generator(self, download_list):
		for d in download_list:
			#gtk.gdk.threads_enter()
			self.mediamanager.download(d[0])
			self.db.set_media_viewed(d[0],False)
			self.emit('entry-updated', d[2], d[3])
			#gtk.gdk.threads_leave()
			yield True
		#gtk.gdk.threads_leave()			
		yield False
	
	def export_opml(self):
		if utils.RUNNING_HILDON:
			dialog = hildon.FileChooserDialog(self.main_window.window, action=gtk.FILE_CHOOSER_ACTION_SAVE)
		else:
			dialog = gtk.FileChooserDialog(_('Select OPML...'),None, action=gtk.FILE_CHOOSER_ACTION_SAVE,
								  buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_SAVE,gtk.RESPONSE_OK))
			dialog.set_default_response(gtk.RESPONSE_OK)

		filter = gtk.FileFilter()
		filter.set_name("OPML files")
		filter.add_pattern("*.opml")
		dialog.add_filter(filter)

		filter = gtk.FileFilter()
		filter.set_name("All files")
		filter.add_pattern("*")
		dialog.add_filter(filter)        
		
		dialog.set_current_name('mySubscriptions.opml')
		dialog.set_transient_for(self.main_window.get_parent())
			
		response = dialog.run()
		if response == gtk.RESPONSE_OK:
			try:
				f = open(dialog.get_filename(), "w")
				self.main_window.display_status_message(_("Exporting Feeds..."))
				updater, db = self._get_updater()
				task_id = updater.queue(db.export_OPML, f)
				self._gui_updater.queue(self.main_window.display_status_message, "", task_id)
			except:
				pass
		elif response == gtk.RESPONSE_CANCEL:
			#print 'Closed, no files selected'
			pass
		dialog.destroy()

	@utils.db_except()
	def remove_feed(self, feed):		
		#select entries and get all the media ids, and tell them all to cancel
		#in case they are downloading
		for entry in self.db.get_entrylist(feed):
			for medium in self.db.get_entry_media(entry[0]):
				if self.mediamanager.has_downloader(medium['media_id']):
					self.mediamanager.stop_download(medium['media_id'])
		self.db.delete_feed(feed)
		self.emit('feed-removed', feed)
		self.update_disk_usage()
	
	def poll_feeds(self, args=0):
		args = args | ptvDB.A_ALL_FEEDS
		self.do_poll_multiple(None, args)
			
	@utils.db_except()
	def import_subscriptions(self, f, opml=True):
		if self._state == MAJOR_DB_OPERATION or not self._app_loaded:
			self._for_import.append((1, f))
			return
			
		def import_gen(f):
			dialog = gtk.Dialog(title=_("Importing OPML file"), parent=None, flags=gtk.DIALOG_MODAL, buttons=None)
			label = gtk.Label(_("Loading the feeds from the OPML file"))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			bar = gtk.ProgressBar()
			dialog.vbox.pack_start(bar, True, True, 0)
			bar.show()
			dialog.set_transient_for(self.main_window.get_parent())
			response = dialog.show()

			gen = self.db.import_subscriptions(f, opml)
			newfeeds = []
			oldfeeds = []
			feed_count=-1.0
			i=1.0
			for feed in gen:
				#status, value
				if feed_count == -1:
					#first yield is the total count
					feed_count = feed[1]
					continue
				if feed==(-1,0): #either EOL or error on insert
					continue
				if self._exiting:
					dialog.hide()
					del dialog
					yield False
				#self.feed_list_view.add_feed(feed)
				if feed[0]==1:
					newfeeds.append(feed[1])
				elif feed[0]==0:
					oldfeeds.append(feed[1])
				bar.set_fraction(i/feed_count)
				i+=1.0
				yield True
			#if len(newfeeds)>10:
			#it's faster to just start over if we have a lot of feeds to add
			self.main_window.search_container.set_sensitive(False)
			self.feed_list_view.clear_list()
			self._populate_feeds(self.done_pop_with_poll)
			self.emit('tags-changed', 0)
			self.main_window.display_status_message("")
			task_id = self._gui_updater.queue(self.__finish_import, None, self._polling_taskinfo)
			dialog.hide()
			del dialog
			if len(newfeeds)==1:
				self.feed_list_view.set_selected(newfeeds[0])
			elif len(oldfeeds)==1:
				self.feed_list_view.set_selected(oldfeeds[0])
			yield False
		#schedule the import pseudo-threadidly
		gobject.idle_add(import_gen(f).next)
					
	def __finish_import(self):
		self.main_window.display_status_message("")
		self.feed_list_view.resize_columns()
		selected = self.feed_list_view.get_selected()

	@utils.db_except()
	def mark_entry_as_viewed(self,entry, feed_id=None): #, update_entrylist=True):
		if feed_id is None:
			feed_id = self.db.get_entry(entry)['feed_id']
		if self.db.get_flags_for_feed(feed_id) & ptvDB.FF_MARKASREAD == ptvDB.FF_MARKASREAD:
			return
		entry = self.db.get_entry(entry)
		if not entry['keep']:
			self.db.set_entry_read(entry['entry_id'],True)
			self.emit('entry-updated', entry['entry_id'], feed_id)
		
	@utils.db_except()
	def mark_entrylist_viewstate(self, viewlist, read=True):
		#print viewlist
		if len(viewlist) == 0:
			return
		
		entrylist = []
		for feed_id, id_list in viewlist:
			entrylist += id_list
		
		self.db.set_entrylist_read(entrylist, read)
			
	@utils.db_except()
	def mark_entry_as_unviewed(self,entry):
		media = self.db.get_entry_media(entry)
		self.db.set_entry_read(entry, 0)
		if media:
			for medium in media:
				self.db.set_media_viewed(medium['media_id'],False)
			#self.update_entry_list(entry)
		else:
			self.db.set_entry_read(entry, 0)
			#self.update_entry_list(entry)
		e = self.db.get_entry(entry)
		self.emit('entry-updated', entry, e['feed_id'])
		#self.feed_list_view.mark_entries_read(-1)
		
	@utils.db_except()
	def mark_feed_as_viewed(self,feed):
		changed = self.db.mark_feed_as_viewed(feed)
		self.emit('entries-viewed', [(feed, changed)])
		#self._entry_list_view.populate_if_selected(feed)
		#self.feed_list_view.update_feed_list(feed, ['readinfo'])
		
	@utils.db_except()
	def mark_all_viewed(self):
		feedlist = self.db.get_feedlist()
		feedlist = [f[0] for f in feedlist]
		def _mark_viewed_gen(feedlist):
			self.main_window.display_status_message(_("Marking everything as viewed..."), MainWindow.U_LOADING)
			self.set_state(MAJOR_DB_OPERATION)
			i=-1.0
			for f in feedlist:
				if self._exiting:
					break
				i+=1.0
				self.mark_feed_as_viewed(f)
				self.main_window.update_progress_bar(i/len(feedlist), MainWindow.U_LOADING)
				yield True
			self._unset_state(True) #force exit of done_loading state
			self.set_state(DEFAULT)
			self.main_window.update_progress_bar(-1)
			self.main_window.display_status_message("")
			yield False
		
		gobject.idle_add(_mark_viewed_gen(feedlist).next)
		
	@utils.db_except()
	def play_entry(self,entry_id):
		media = self.db.get_entry_media(entry_id)
		entry = self.db.get_entry(entry_id)
		feed_title = self.db.get_feed_title(entry['feed_id'])
		if not entry['keep']:
			self.db.set_entry_read(entry_id, True)
		filelist=[]
		if media:
			for medium in media:
				filelist.append([medium['file'], utils.my_quote(feed_title) + " " + utils.get_hyphen() + " " + entry['title'], medium['media_id']])
				if not entry['keep']:
					self.db.set_media_viewed(medium['media_id'],True)
		self.player.play_list(filelist, context=self._hildon_context)
		self.emit('entry-updated', entry_id, entry['feed_id'])
		
	@utils.db_except()
	def play_unviewed(self):
		playlist = self.db.get_unplayed_media(True) #set viewed
		playlist.reverse()
		self.player.play_list([
				[item[3],
				utils.my_quote(item[5]) + " " + utils.get_hyphen() + " " + item[4], 
				item[0]] 
			for item in playlist], 
			context=self._hildon_context)
		for row in playlist:
			self.feed_list_view.update_feed_list(row[2],['readinfo'])
			
	def _on_item_not_supported(self, player, filename, name, userdata):
		# I thought this would be called from main thread, but apparently not
		gtk.gdk.threads_enter()
		dialog = gtk.Dialog(title=_("Can't Play File"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OPEN, gtk.RESPONSE_ACCEPT))
		label = gtk.Label("PenguinTV can not play this file. \nWould you like to try opening it in the default system player?")
		dialog.vbox.pack_start(label, True, True, 0)
		label.show()
		dialog.set_transient_for(self.main_window.get_parent())
		response = dialog.run()
		dialog.hide()

		if response == gtk.RESPONSE_ACCEPT:		
			self.player.play(filename, name, userdata, force_external=True, context=self._hildon_context) #retry, force external player

		dialog.destroy()
		gtk.gdk.threads_leave()
		
	def _on_gst_tick(self, player):
		if utils.RUNNING_HILDON:
			gst_player = self.main_window.get_gst_player()
			if gst_player is not None:
				if gst_player.has_video():
					osso.DeviceState(self._hildon_context).display_blanking_pause()

	@utils.db_except()
	def refresh_feed(self, feed):
		if not self._net_connected:
			return
		
		info = self.db.get_feed_info(feed)	
		updater, db = self._get_updater()
		
		def _refresh_cb(update_data, success):
			self._threaded_emit('feed-polled', feed, update_data)
			if update_data.has_key('new_entryids'):
				self._gui_updater.queue(self._article_sync.get_readstates_for_entries, update_data['new_entryids'])
			if update_data.has_key('mod_entryids'):
				if self._article_sync.is_enabled():
					#if len(update_data['mod_entryids']) > 0:
					#	logging.debug("entries have been modified, resubmitting: %s" % str(update_data['mod_entryids']))
					for e_id in update_data['mod_entryids']:
						self._gui_updater.queue(self._article_sync.diff_entry, (e_id, feed))
			if info['lastpoll'] == 0 and success:
				self._mark_all_media_but_first(feed, db=db)
		self.main_window.display_status_message(_("Polling Feed..."))
		
		self._poll_new_entries = []
		task_id = updater.queue(db.poll_feed_trap_errors,(feed, _refresh_cb))
		
	def _unset_state(self, authorize=False):
		"""gets app ready to display new state by unloading current state.
		Also checks if we are loading feeds, in which case state can not change.
		
		To unset loading_feeds, we take a "manual override" argument"""
				
		#bring state back to default
		
		if self._state != MANUAL_SEARCH:
			#save filter for later
			self._saved_filter = self.main_window.get_active_filter()[1]
		
		if self._state == MAJOR_DB_OPERATION:
			if not authorize:
				raise CantChangeState,"can't interrupt feed loading"
			else:
				self._state = DONE_MAJOR_DB_OPERATION #we don't know what the new state will be...
				return
				
		if self._state == DEFAULT:
			return
	
	def set_state(self, new_state, data=None):
		self.emit('state-changed', new_state, data)
	
	@utils.db_except()
	def _state_changed_cb(self, app, new_state, data):
		if self._state == new_state:
			return	
			
		if new_state == DEFAULT and self._state == MAJOR_DB_OPERATION:
			logging.error("possible programming error: must unset major_db_op manually (self._unset_state(True))")
			#self.main_window.set_state(new_state, data)
			return #do nothing

		self._unset_state()
			
		if new_state == MANUAL_SEARCH:
			assert utils.HAS_SEARCH
		elif new_state == TAG_SEARCH:
			assert utils.HAS_SEARCH
		elif new_state == MAJOR_DB_OPERATION:
			pass
		
		if self._state == MANUAL_SEARCH and new_state == DEFAULT and data != True:
			self._saved_search = self.main_window.search_entry.get_text()
			selected = self.feed_list_view.get_selected()
			if selected is not None:
				name = self.main_window.get_filter_name(self._saved_filter)
				if name not in self.db.get_tags_for_feed(selected):
					self.main_window.set_active_filter(FeedList.ALL)
				else:
					self.main_window.set_active_filter(self._saved_filter)
			else:
				self.main_window.set_active_filter(self._saved_filter)
		
		self._state = new_state
		
	@utils.db_except()
	def _search(self, query, blacklist=None):
		try:
			query = query.replace("!","")
			result = self.db.search(query, blacklist=blacklist)
			logging.debug("search results: %i, %i" % (len(result[0]), len(result[1])))
		except Exception, e:
			logging.warning("Error with that search term: " + str(query) + str(e))
			result=([],[])
		return result
	
	@utils.db_except()
	def _show_search(self, query, result):
		if self._state != MANUAL_SEARCH and self._state != TAG_SEARCH:
			logging.warning("incorrect state, aborting" + str(self._state))
			return
		try:
			self._entry_list_view.show_search_results(result[1], query)
			self.feed_list_view.show_search_results(result[0])
		except ptvDB.BadSearchResults, e:
			logging.warning(str(e))
			self.db.reindex(result[0], [i[0] for i in result[1]])
			self._show_search(query, self._search(query))
			return
		
	def _update_search(self):
		self._search(self._saved_search)
		
	def threaded_search(self, query):
		if query != "":
			if self._threaded_searcher is None:
				self._threaded_searcher = PenguinTVApp._threaded_searcher(query, self.__got_search, self._searcher_done)
			self._threaded_searcher.set_query(query)
			if not self._waiting_for_search:
				self._waiting_for_search = True
				self._threaded_searcher.start()
	
	def __got_search(self, query, results):
		self._gui_updater.queue(self._got_search, (query,results))
		
	def _searcher_done(self):
		self._waiting_for_search = False
		
	def _got_search(self, query, results):
		self.set_state(MANUAL_SEARCH)
		self._show_search(query, results)
		
	if utils.HAS_LUCENE:
		import PyLucene
		threadclass = PyLucene.PythonThread
	else:
		threadclass = threading.Thread
	class _threaded_searcher(threadclass):
		def __init__(self, query, callback, done_callback):
			PenguinTVApp.threadclass.__init__(self)
			self.query = query
			self.callback = callback
			self.done_callback = done_callback
			self.db = ptvDB.ptvDB()
			
		def set_query(self, query):
			self.query = query.replace("!","")
		
		def run(self):
			old_query = self.query+"different"
			waits=0
			while waits<3:
				if self.query == old_query: #we get .2*3 seconds to wait for more characters
					waits+=1
				else:
					waits=0
					try:
						old_query = self.query
						self.callback(self.query, self.db.search(self.query))
					except:
						self.callback(self.query, ([],[]))
				time.sleep(.2) #give signals a chance to get around
			self.done_callback()
		
	def manual_search(self, query):
		#self._saved_search = query #even if it's blank
		if len(query)==0:
			self.set_state(DEFAULT)
			return
		self.set_state(MANUAL_SEARCH)
		self._show_search(query, self._search(query))
		
	def entrylist_selecting_right_now(self):
		return self._entry_list_view.presently_selecting
		
	def select_feed(self, feed_id):
		self.feed_list_view.set_selected(feed_id)
		
	@utils.db_except()
	def select_entry(self, entry_id):
		feed_id = self.db.get_entry(entry_id)['feed_id']
		self.select_feed(feed_id)
		#FIXME: doesn't display entry because list isn't populated yet
		self.display_entry(entry_id)
		self.main_window.notebook_select_page(0)

	@utils.db_except()
	def change_filter(self, current_filter, tag_type):
		filter_id = self.main_window.get_active_filter()[1]
		if utils.HAS_SEARCH and filter_id == FeedList.SEARCH:
			self._show_search(self._saved_search, self._search(self._saved_search))
			if self._threaded_searcher:
				if not self._waiting_for_search:
					self.main_window.search_entry.set_text(self._saved_search)
		else:
			if tag_type == ptvDB.T_SEARCH:
				self.set_state(TAG_SEARCH)
				query = self.db.get_search_tag(current_filter)
				self._show_search(query, self._search(query))			
			else:
				self.set_state(DEFAULT, True) #gonna filter!
				self.main_window.feed_list_view.set_filter(filter_id, current_filter)
				
	def show_downloads(self):
		self.mediamanager.generate_playlist()
		self.mediamanager.show_downloads()
		
	@utils.db_except()
	def stop_downloads(self):
		"""stops downloading everything -- really just pauses them.  Just sets a flag, really.
		progress_callback does the actual work"""
		if self.mediamanager.pause_state == MediaManager.RUNNING:
			download_stopper_thread = threading.Thread(None, self.mediamanager.stop_all_downloads)
			download_stopper_thread.start() #this isn't gonna block any more!
			self.db.pause_all_downloads() #blocks, but prevents race conditions

	@utils.db_except()
	def pause_downloads(self):
		if self.mediamanager.pause_state == MediaManager.RUNNING:
			download_pauser_thread = threading.Thread(None, self.mediamanager.pause_all_downloads)
			download_pauser_thread.start() #this isn't gonna block any more!
			self.db.pause_all_downloads() #blocks, but prevents race conditions
	
	@utils.db_except()		
	def change_layout(self, layout):
		if self.main_window.layout != layout:
			self.set_state(DEFAULT)
			val = self.feed_list_view.get_selected()
			if val is None: val = 0
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/selected_feed', val)
			val = self._entry_list_view.get_selected_id()
			if val is None: val = 0
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/selected_entry', val)
			self.feed_list_view.interrupt()
			self.feed_list_view.set_selected(None)
			self.feed_list_view.finalize()
			self._entry_list_view.finalize()
			self._entry_view.finish()
			while gtk.events_pending(): #make sure everything gets shown
				gtk.main_iteration()
			gc.collect()
			self.main_window.activate_layout(layout)
			self.feed_list_view = self.main_window.feed_list_view
			self._entry_list_view = self.main_window.entry_list_view
			self._entry_view = self.main_window.entry_view
			
			self._connect_signals()
			
			self.main_window.changing_layout = False
			self._populate_feeds(self._done_populating)
			self.update_disk_usage()
			#val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/selected_feed', 0)
			#if val > 0:
			#	self.feed_list_view.set_selected(val)
			val = self.db.get_setting(ptvDB.INT, '/apps/penguintv/selected_entry', 0)
			if val > 0:
				#self._entry_list_view.set_selected(val)
				self.select_entry(val)

	def on_window_changing_layout_delete_event(self, widget, event):
		self.main_window.changing_layout = False
		return widget.hide_on_delete()

	def _gconf_set_bt_maxport(self, client, *args, **kwargs):
		maxport = client.get_int('/apps/penguintv/bt_max_port')
		self.set_bt_maxport(maxport)
		self.window_preferences.set_bt_settings(self._bt_settings)
		
	def set_bt_maxport(self, maxport):
		self._bt_settings['max_port']=maxport
		
	def _gconf_set_bt_minport(self, client, *args, **kwargs):
		minport = client.get_int('/apps/penguintv/bt_min_port')
		self.set_bt_minport(minport)
		self.window_preferences.set_bt_settings(self._bt_settings)
		
	def set_bt_minport(self, minport):
		self._bt_settings['min_port']=minport
		
	def _gconf_set_bt_ullimit(self, client, *args, **kwargs):
		ullimit = client.get_int('/apps/penguintv/bt_ul_limit')
		self.set_bt_ullimit(ullimit)
		self.window_preferences.set_bt_settings(self._bt_settings)
		
	def set_bt_ullimit(self, ullimit):
		self._bt_settings['ul_limit']=ullimit
			
	def _gconf_set_polling_frequency(self, client, *args, **kwargs):
		freq = client.get_int('/apps/penguintv/feed_refresh_frequency')
		self.set_polling_frequency(freq)
			
	def set_polling_frequency(self, freq):
		if self.polling_frequency != freq*60*1000:
			self.polling_frequency = freq*60*1000	
			gobject.timeout_add(self.polling_frequency,self.do_poll_multiple, self.polling_frequency)
			self.window_preferences.set_feed_refresh_frequency(freq)
			
	def _gconf_set_media_storage_location(self, client, *args, **kwargs):
		val = client.get_string('/apps/penguintv/media_storage_location')
		self.set_media_storage_location(val)
		
	def set_media_storage_location(self, location):
		#try:
		old_dir, remap_dir = self.mediamanager.set_media_dir(location)
		#except:
		#	self.window_preferences.alert_bad_storage_location(location)
		#	return

		if remap_dir is not None:
			self.db.relocate_media(old_dir, remap_dir)
			gst_player = self.main_window.get_gst_player()
			if gst_player is not None:
				gst_player.relocate_media(old_dir, remap_dir)
		self.window_preferences.set_media_storage_location(location)
		
	def _gconf_set_media_storage_style(self, client, *args, **kwargs):
		val = client.get_int('/apps/penguintv/media_storage_style')
		self.set_media_storage_style(val)
		
	def set_media_storage_style(self, style):
		self.mediamanager.set_storage_style(style, True)
		
	def get_feed_refresh_method(self):
		return self.feed_refresh_method
		
	@utils.db_except()
	def _gconf_set_feed_refresh_method(self, client, *args, **kwargs):
		refresh = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method', 'auto')
		self.set_feed_refresh_method(refresh, client)
		
	@utils.db_except()
	def set_feed_refresh_method(self, refresh, client=None):
		if refresh == 'auto':
			self.feed_refresh_method=REFRESH_AUTO
			self.polling_frequency = AUTO_REFRESH_FREQUENCY	
			gobject.timeout_add(self.polling_frequency,self.do_poll_multiple, self.polling_frequency)
		elif refresh == 'specified':
			self.feed_refresh_method=REFRESH_SPECIFIED
			if utils.HAS_GCONF:
				self._gconf_set_polling_frequency(client,None,None)
			else:
				self.set_polling_frequency(self.db.get_setting(ptvDB.INT, '/apps/penguintv/feed_refresh_frequency', 5))
		else:
			self.feed_refresh_method=REFRESH_NEVER
			
	@utils.db_except()	
	def add_feed(self, url, title, tags=[]):
		"""Inserts the url and starts the polling process"""
		
		#FIXME:  if we add feed while doing a major db operation like mark all,
		#FIXME:  this won't work
		if self._state == MAJOR_DB_OPERATION or not self._app_loaded:
			self._for_import.append((0, url, title))
			return
		
		self.main_window.display_status_message(_("Trying to poll feed..."))
		feed_id = -1
		try:
			feed_id = self.db.insertURL(url, title)
			if len(tags) > 0 and not utils.RUNNING_SUGAR:
				for tag in tags:
					self.db.add_tag_for_feed(feed_id, tag)

			self.feed_list_view.add_feed(feed_id)
			#let signals take care of this???
			self.main_window.select_feed(feed_id)
			
			if len(tags) > 0 and not utils.RUNNING_SUGAR:
				self.emit('tags-changed', 0)
			
			updater, db = self._get_updater()
			self._poll_new_entries = []
			updater.queue(db.poll_feed_trap_errors, (feed_id,self._db_add_feed_cb))
		except ptvDB.FeedAlreadyExists, e:
			self.main_window.select_feed(e.feed)
		self.main_window.hide_window_add_feed()
		return feed_id
		
	def _db_add_feed_cb(self, feed, success):
		self._threaded_emit('feed-polled', feed['feed_id'], feed)
		self._threaded_emit('feed-added', feed['feed_id'], success)
		
	def __feed_added_cb(self, app, feed_id, success):
		if success:
			self._mark_all_media_but_first(feed_id)
		
	@utils.db_except()
	def _mark_all_media_but_first(self, feed_id, db=None): 
		"""mark all media read except first one.  called when we first add a feed"""
		if db is None:
			db = self.db
		all_feeds_list = db.get_media_for_download()
		this_feed_list = [item[2] for item in all_feeds_list if item[3] == feed_id]
		db.set_entrylist_read(this_feed_list[1:], True)
		self.mark_entrylist_viewstate([(feed_id, this_feed_list[1:])], True)
		self.emit('entries-viewed', [(feed_id, this_feed_list[1:])])
		if self._auto_download:
			self._auto_download_unviewed()
	
	@utils.db_except()
	def add_feed_filter(self, pointed_feed_id, filter_name, query):
		try:
			feed_id = self.db.add_feed_filter(pointed_feed_id, filter_name, query)
		except ptvDB.FeedAlreadyExists, f:
			self.main_window.select_feed(f)
			return
		self.feed_list_view.add_feed(feed_id)
		self.main_window.select_feed(feed_id)
		
	@utils.db_except()
	def set_feed_filter(self, pointer_feed_id, filter_name, query):
		self.db.set_feed_filter(pointer_feed_id, filter_name, query)
		#FIXME: should emit a signal so that planetview updates its title too
		self.feed_list_view.update_feed_list(pointer_feed_id,['title'],{'title':filter_name})
		self.feed_list_view.resize_columns()
			
	@utils.db_except()
	def delete_entry_media(self, entry_id):
		"""Delete all media for an entry"""
		medialist = self.db.get_entry_media(entry_id)
		if medialist:
			for medium in medialist:
				if medium['download_status']==ptvDB.D_DOWNLOADED or medium['download_status']==ptvDB.D_RESUMABLE:
					self.delete_media(medium['media_id'])
		feed_id = self.db.get_entry(entry_id)['feed_id']
		self.emit('entry-updated', entry_id, feed_id)
		self.update_disk_usage()
		
	@utils.db_except()
	def delete_media(self, media_id, update_ui=True, entry_id=None):
		"""Deletes specific media id"""
		self.db.delete_media(media_id)
		self.mediamanager.generate_playlist()
		self.player.unqueue(media_id)
		self.db.set_media_viewed(media_id,True, entry_id)
		if update_ui:
			self.main_window.update_downloads()
			self.update_disk_usage()
			m = self.db.get_media(media_id)
			self.emit('entry-updated', m['entry_id'], m['feed_id'])
		
	def delete_feed_media(self, feed_id):
		"""Deletes media for an entire feed.  Calls generator _delete_media_generator"""
		gobject.idle_add(self._delete_media_generator(feed_id).next)
		
	@utils.db_except()
	def _delete_media_generator(self, feed_id):
		entrylist = self.db.get_entrylist(feed_id)
		if entrylist:
			for entry in entrylist:
				#gtk.gdk.threads_enter()
				medialist = self.db.get_entry_media(entry[0])
				if medialist:
					for medium in medialist:
						if medium['download_status']==ptvDB.D_DOWNLOADED or medium['download_status']==ptvDB.D_RESUMABLE:
							self.delete_media(medium['media_id'], False)
				self._entry_view.update_if_selected(entry[0], feed_id)
				#gtk.gdk.threads_leave()
				yield True
			#gtk.gdk.threads_enter()
			self.update_entry_list()
			self.mediamanager.generate_playlist()
			self.update_disk_usage()
		else:
			pass
			#gtk.gdk.threads_enter()
		self.feed_list_view.update_feed_list(feed_id, ['readinfo','icon'])
		#gtk.gdk.threads_leave()
		yield False
		
	@utils.db_except()
	def do_cancel_download(self, item):
		"""cancels a download and cleans up.  Right now there's redundancy because we call this twice
		   for files that are downloading -- once when we ask it to stop downloading, and again when the
		   callback tells the thread to stop working.  how to make this better?"""
		
		d = None
		try:
			d = self.mediamanager.get_downloader(item['media_id'])
			self.mediamanager.stop_download(item['media_id'])
		except Exception, e:
			pass  #download may not be active anymore, but that's ok
		self.db.set_media_download_status(item['media_id'],ptvDB.D_NOT_DOWNLOADED)
		self.delete_media(item['media_id'], False, item['entry_id']) #marks as viewed
		if self._exiting:
			self.feed_list_view.filter_all() #to remove active downloads from the list
			return
		self.feed_list_view.filter_all() #to remove active downloads from the list
		if d is not None:
			self.emit('download-finished', d)
		else:
			feed_id = self.db.get_entry(item['entry_id'])['feed_id'] 	 
			self.emit('entry-updated', item['entry_id'], feed_id)
		
	@utils.db_except()
	def do_pause_download(self, media_id):
		self.mediamanager.get_downloader(media_id).pause()
		self.db.set_media_download_status(media_id,ptvDB.D_RESUMABLE)
		self.db.set_media_viewed(media_id,0)
		self.db.set_entry_read(media_id,0)
		
	@utils.db_except()
	def do_resume_download(self, media_id):
		self.mediamanager.unpause_downloads()
		self.mediamanager.download(media_id, False, True) #resume please
		self.db.set_media_viewed(media_id,False)
		entry_id = self.db.get_entryid_for_media(media_id)
		feed_id = self.db.get_entry(entry_id)['feed_id']
		self.emit('entry-updated', entry_id, feed_id)
		
	@utils.db_except()
	def _download_finished(self, d):
		"""Process the data from a callback for a downloaded file"""
		
		self.update_disk_usage()
		if d.status==Downloader.FAILURE: 
			self.db.set_media_download_status(d.media['media_id'],ptvDB.D_ERROR,d.media['errormsg'])
		elif d.status==Downloader.STOPPED or d.status==Downloader.PAUSED:
			pass
		elif d.status==Downloader.FINISHED or d.status==Downloader.FINISHED_AND_PLAY:
			if os.stat(d.media['file'])[6] < int(d.media['size']/2) and os.path.isfile(d.media['file']): #don't check dirs
				self.db.set_entry_read(d.media['entry_id'],False)
				self.db.set_media_viewed(d.media['media_id'],False)
				self.db.set_media_download_status(d.media['media_id'],ptvDB.D_DOWNLOADED,_("File did not download completely"))
				d.status = Downloader.FAILURE
			else:
				if d.status==Downloader.FINISHED_AND_PLAY:
					entry = self.db.get_entry(d.media['entry_id'])
					if not entry['keep']:
						self.db.set_entry_read(d.media['entry_id'],True)
						self.db.set_media_viewed(d.media['media_id'], True)
					entry = self.db.get_entry(d.media['entry_id'])
					feed_title = self.db.get_feed_title(entry['feed_id'])
					self.player.play(d.media['file'], utils.my_quote(feed_title) + " " + utils.get_hyphen() + " " + entry['title'], d.media['media_id'], context=self._hildon_context)
				else:
					entry = self.db.get_entry(d.media['entry_id'])
					if not entry['keep']:
						self.db.set_entry_read(d.media['entry_id'],False)
						self.db.set_media_viewed(d.media['media_id'],False)
				self.db.set_media_download_status(d.media['media_id'],ptvDB.D_DOWNLOADED)
		self.emit('download-finished', d)
		if self._exiting:
			self.feed_list_view.filter_all() #to remove active downloads from the list
			return
		self.emit('entry-updated', d.media['entry_id'], d.media['feed_id'])
		self.feed_list_view.filter_all() #to remove active downloads from the list
			
	@utils.db_except()
	def rename_feed(self, feed_id, name):
		oldname = self.db.get_feed_title(feed_id)
		if len(name)==0:
			self.db.set_feed_name(feed_id, None) #gets the title the feed came with
			name = self.db.get_feed_title(feed_id)
		else:
			self.db.set_feed_name(feed_id, name)
		self.emit('feed-name-changed', feed_id, oldname, name)
		
	def _gconf_set_auto_resume(self, client, *args, **kwargs):
		autoresume = client.get_bool('/apps/penguintv/auto_resume')
		self.set_auto_resume(autoresume)
		
	def set_auto_resume(self, autoresume):
		self.window_preferences.set_auto_resume(autoresume)
		self._autoresume = autoresume
		
	def _gconf_set_poll_on_startup(self, client, *args, **kwargs):
		poll_on_startup = client.get_bool('/apps/penguintv/poll_on_startup')
		self.set_poll_on_startup(poll_on_startup)
		self.window_preferences.set_poll_on_startup(poll_on_startup)
	
	def set_poll_on_startup(self, poll_on_startup):
		self.poll_on_startup = poll_on_startup
		
	def _gconf_set_cache_images(self, client, *args, **kwargs):
		cache_images = client.get_bool('/apps/penguintv/cache_images_locally')
		self.set_cache_images(cache_images)
		self.window_preferences.set_cache_images(cache_images)
	
	def set_cache_images(self, cache_images):
		self.db.set_cache_images(cache_images)
		
	def _gconf_set_auto_download(self, client, *args, **kwargs):
		auto_download = client.get_bool('/apps/penguintv/auto_download')
		self.set_auto_download(auto_download)
		self.window_preferences.set_auto_download(auto_download)
		
	def set_auto_download(self, auto_download):
		self._auto_download = auto_download
		
	def _gconf_set_show_notification_always(self, client, *args, **kwargs):
		show_notification_always = client.get_bool('/apps/penguintv/show_notification_always')
		self.window_preferences.set_show_notification_always(show_notification_always)
		if utils.HAS_STATUS_ICON:
			self._status_icon.set_show_always(show_notification_always)
		
	def set_show_notification_always(self, show_notification_always):
		if utils.HAS_STATUS_ICON:
			self._status_icon.set_show_always(show_notification_always)
			
	def _gconf_set_show_notifications(self, client, *args, **kwargs):
		show_notifications = client.get_bool('/apps/penguintv/show_notifications')
		self.emit('setting-changed', ptvDB.BOOL, 
		          '/apps/penguintv/show_notifications',
		          show_notifications)
		
	def _gconf_set_auto_download_limiter(self, client, *args, **kwargs):
		auto_download_limiter = client.get_bool('/apps/penguintv/auto_download_limiter')
		self.set_auto_download_limiter(auto_download_limiter)
		self.window_preferences.set_auto_download_limiter(auto_download_limiter)
		
	def set_auto_download_limiter(self, auto_download_limiter):
		self._auto_download_limiter = auto_download_limiter

	def _gconf_set_auto_download_limit(self, client, *args, **kwargs):
		auto_download_limit = client.get_int('/apps/penguintv/auto_download_limit')
		self.set_auto_download_limit(auto_download_limit)
		self.window_preferences.set_auto_download_limit(auto_download_limit)
		
	def set_auto_download_limit(self, auto_download_limit):
		self._auto_download_limit = auto_download_limit
		
	@utils.db_except()
	def _gconf_set_app_window_layout(self, client, *args, **kwargs):
		layout = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/app_window_layout', 'standard')
		self.set_app_window_layout(layout)
		
	def set_app_window_layout(self, layout):
		self.main_window.layout=layout
		
	def _gconf_set_use_article_sync(self, client, *args, **kwargs):
		enabled = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/use_article_sync', False)
		if not utils.ENABLE_ARTICLESYNC:
			enabled = False
		self.set_use_article_sync(enabled)
		self.window_preferences.set_use_article_sync(enabled)
		if enabled:
			if self._state != MAJOR_DB_OPERATION:
				if not self._article_sync.is_authenticated():
					self.sync_authenticate()
		else:
			self.window_preferences.set_sync_status(_("Not Logged In"))
		
	def set_use_article_sync(self, enabled):
		self._article_sync.set_enabled(enabled)
		
	#def _gconf_set_sync_username(self, client, *args, **kwargs):
	#	username = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/sync_username', "")
	#	self.set_sync_username(username)
	#	
	#def set_sync_username(self, username):
	#	pass
	#	#self._article_sync.set_username(username)
	#	#self.window_preferences.set_sync_username(username)
	#	
	#def _gconf_set_sync_password(self, client, *args, **kwargs):
	#	password = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/sync_password', "")
	#	#self.set_sync_password(password)
	#	
	#def set_sync_password(self, password):
	#	pass
	#	#self._article_sync.set_password(password)
	#	#self.window_preferences.set_sync_password(password)
	
	def _gconf_set_sync_readonly(self, client, *args, **kwargs):
		readonly = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/sync_readonly', False)
		self.set_article_sync_readonly(readonly)
		
	def set_article_sync_readonly(self, readonly):
		self._article_sync.set_readonly(readonly)
		
	#def update_feed_list(self, feed_id=None):
	#	self.feed_list_view.update_feed_list(feed_id) #for now, just update this ONLY
		
	def update_entry_list(self, entry_id=None):
		self._entry_list_view.update_entry_list(entry_id)			
		
	def update_disk_usage(self):
		size = self.mediamanager.get_disk_usage()
		self.main_window.update_disk_usage(size)
		
	def _sensitize_search(self):
		self._gui_updater.queue(self.main_window._sensitize_search)
		
	def _done_populating(self):
		self._gui_updater.queue(self.done_populating)

	def _done_populating_dont_sensitize(self):
		self._gui_updater.queue(self.done_populating, False)
		
	def done_populating(self, sensitize=True):
		self._unset_state(True) #force exit of done_loading state
		self.set_state(DEFAULT) #redundant
		if self._article_sync.is_enabled():
			self.sync_authenticate()
		if sensitize:
			self.main_window._sensitize_search()
		
		self._spawn_poller()
		gobject.timeout_add(2 * 60 * 1000, self._check_poller)
		if not self._firstrun and self.poll_on_startup: #don't poll on startup on firstrun, we take care of that
			gobject.timeout_add(30*1000,self.do_poll_multiple, 0)
			
		if not self.__importing:
			self.__importing = True
			for item in self._for_import:
				if item[0] == 0: #url
					typ, url, title = item
					self.add_feed(url, title)
				elif item[0] == 1: #opml
					typ, f = item
					try:
						self.import_subscriptions(f)
					except e:
						logging.error("Exception importing opml file:" + str(e))

			self._for_import = []
			self.__importing = False
			
	def done_pop_with_poll(self):
		self.done_populating()
		self.do_poll_multiple()
		
	def get_database_name(self):
		return os.path.join(utils.get_home(), "penguintv4.db")
		
	def toggle_net_connection(self):
		self.emit('online-status-changed', not self._net_connected)
		
	def _nm_get_state(self):
		try:
			return int(self._nm_interface.Get("org.freedesktop.NetworkManager","State"))
		except:
			logging.warning("Error returning device state")
			return 0

	def _nm_properties_changed(self, *args):
		#state = int(args[0]["State"])
		state = self._nm_get_state()
		if state == 3:
			self.maybe_change_online_status(True)
		else:
			self.maybe_change_online_status(False)
				
	def maybe_change_online_status(self, new_status):
		logging.debug("NetworkManager possible status change")
		if new_status != self._net_connected:
			if new_status:
				self._article_sync.authenticate()
			else:
				self._article_sync.disconnected()
			self.emit('online-status-changed', new_status)
			
	def _progress_callback(self,d):
		"""Callback for downloads.  Not in main thread, so shouldn't generate gtk calls"""
		if self._exiting == 1:
			return 1 #returning one is what interrupts the download
		
		if d.media.has_key('size_adjustment'):
			if d.media['size_adjustment']==True:
				updater, db = self._get_updater()
				updater.queue(db.set_media_size,(d.media['media_id'], d.media['size']))
		if self.main_window.changing_layout == False:
			#self._gui_updater.queue(self._entry_view.update_if_selected,(d.media['entry_id'],d.media['feed_id']))
			self._gui_updater.queue(self._entry_view.progress_update,(d.media['entry_id'],d.media['feed_id']))
			self._gui_updater.queue(self.main_window.update_download_progress)

	def _finished_callback(self,downloader):
		self._gui_updater.queue(self._download_finished, downloader)
		
	def polling_callback(self, args, cancelled=False):
		if not self._exiting:
			feed_id, update_data, total = args
			if len(update_data)>0:
				if (update_data['pollfail'] and not self._net_connected) or \
				  update_data.has_key('ioerror'):
					logging.warning("ioerror polling reset")
					updater, db = self._get_updater()
					db.interrupt_poll_multiple()
					self._polled = 0
					#logging.debug("reset polling taskinfo 2468")
					self._polling_taskinfo = -1
					self._poll_message = ""
					if not utils.RUNNING_HILDON:
						self._gui_updater.queue(self._article_sync.get_readstates_for_entries, self._poll_new_entries)
					self.main_window.update_progress_bar(-1, MainWindow.U_POLL)
					self.main_window.display_status_message(_("Trouble connecting to the internet"),MainWindow.U_POLL)
					gobject.timeout_add(2000, self.main_window.display_status_message,"")
					return
				else:
					update_data['polling_multiple'] = True
					if update_data.has_key('new_entryids'):
						if utils.RUNNING_HILDON:
							self._gui_updater.queue(self._article_sync.get_readstates_for_entries, update_data['new_entryids'])
						else:
							self._poll_new_entries += update_data['new_entryids']
					if update_data.has_key('mod_entryids'):
						if self._article_sync.is_enabled():
							#if len(update_data['mod_entryids']) > 0:
							#	logging.debug("entries have been modified, resubmitting: %s" % str(update_data['mod_entryids']))
							for e_id in update_data['mod_entryids']:
								self._gui_updater.queue(self._article_sync.diff_entry, (e_id, feed_id))
					self._threaded_emit('feed-polled', feed_id, update_data)
					if update_data.has_key('first_poll'):
						if update_data['first_poll']:
							self._gui_updater.queue(self._mark_all_media_but_first, feed_id)
					if self._polling_thread == LOCAL:
						updater, db = self._get_updater()
					elif self._polling_thread == REMOTE:
						db = self.db
					if db.get_flags_for_feed(feed_id) & ptvDB.FF_DOWNLOADSINGLE == ptvDB.FF_DOWNLOADSINGLE:
						self._gui_updater.queue(self._mark_all_media_but_first, feed_id)
			elif not cancelled and feed_id != -1:
				#check image just in case
				self._gui_updater.queue(self.feed_list_view.update_feed_list, (feed_id,['image']))
			self._gui_updater.queue(self._poll_update_progress, (total, cancelled))
		
	def _poll_update_progress(self, total=0, cancelled=False):
		"""Updates progress for do_poll_multiple, and also displays the "done" message"""

		self._polled += 1
		if self._polled >= total or cancelled:
			#logging.debug("done polling multiple 1, updating readstates")
			if not utils.RUNNING_HILDON:
				self._article_sync.get_readstates_for_entries(self._poll_new_entries)
			self.main_window.update_progress_bar(-1,MainWindow.U_POLL)
			self.main_window.display_status_message(_("Feeds Updated"),MainWindow.U_POLL)
			self._polled = 0
			#logging.debug("reset polling taskinfo 2508")
			self._polling_taskinfo = -1
			self._poll_message = ""
			
			gobject.timeout_add(2000, self.main_window.display_status_message,"")
		else:
			d = { 'polled':self._polled,
				  'total':total}
			self.main_window.update_progress_bar(float(self._polled)/float(total),MainWindow.U_POLL)
			self.main_window.display_status_message(self._poll_message + 
				" (%(polled)d/%(total)d)" % d,MainWindow.U_POLL)
			
	def _entry_image_download_callback(self, entry_id, html):
		self._gui_updater.queue(self._entry_view._images_loaded,(entry_id, html))
		
	def _emit_change_setting(self, typ, datum, value):
		self.emit('setting-changed', typ, datum, value)
		
	def _threaded_emit(self, signal, *args):
		def do_emit(signal, *args):
			gtk.gdk.threads_enter()
			self.emit(signal, *args)
			gtk.gdk.threads_leave()
			return False
		gobject.idle_add(do_emit, signal, *args, **{"priority" : gobject.PRIORITY_HIGH})
		
	def _get_updater(self):
		"""if the updater thread is not running, or we never started one,
		delete and restart it.  Otherwise return the current values"""
		
		if self._update_thread is not None:
			if self._update_thread.isAlive() and not self._update_thread.isDying():
				updater = self._update_thread.get_updater()
				updater_thread_db = self._update_thread.get_db()
				if updater_thread_db is None:
					logging.error("updater db is none: 1")
				return (updater, updater_thread_db)
			else:
				del self._update_thread

		self._update_thread = self.DBUpdaterThread(self.polling_callback)
		self._update_thread.start()
		updater_thread_db = None
		updater = None
		while True:
			#this may race, so be patient 
			updater = self._update_thread.get_updater()
			updater_thread_db = self._update_thread.get_db()
			if updater_thread_db is not None and updater is not None:
				break
			time.sleep(.05)

		if updater_thread_db is None:
			logging.error("updater db is none: 2")
		return (updater, updater_thread_db)
				
	class DBUpdaterThread(threadclass):
		def __init__(self, polling_callback):
			PenguinTVApp.threadclass.__init__(self)
			self.__isDying = False
			self.db = None
			self.updater = UpdateTasksManager.UpdateTasksManager(UpdateTasksManager.MANUAL, "db updater")
			self.threadSleepTime = 1.0
			self.threadDieTime = 30.0
			self.polling_callback = polling_callback
			self._db_lock = threading.Lock()
			self._restart_db = False
			
		def run(self):
	
			""" Until told to quit, retrieve the next task and execute
				it, calling the callback if any.  """
			
			if self.db == None:
				self._db_lock.acquire()
				self._start_db()
				self._db_lock.release()
			
			born_t = time.time()
			while self.__isDying == False:
				if self._restart_db:
					logging.debug("We were told to restart the database")
					if self.db is not None:
						logging.debug("and yet db is not none.  what gives?")
					self._restart_db = False
					self._db_lock.acquire()
					self._start_db()
					self._db_lock.release()
				while self.updater.updater_gen().next():
					#do we also need to check for db restarting here?
					if self.updater.exception is not None:
						if isinstance(self.updater.exception, OperationalError):
							self._db_lock.acquire()
							logging.warning("detected a database lock error, restarting threaded db")
							self.db._db.close()
							del self.db
							self._start_db()
							self._db_lock.release()
				if time.time() - born_t > self.threadDieTime:
					self.__isDying = True
				time.sleep(self.threadSleepTime)
			
			if self.db is not None:
				self.db.finish(False)
				self.db = None
				
		def _start_db(self):
			#traceback.print_stack()
			self.db = ptvDB.ptvDB(self.polling_callback)
						
		def get_db(self):
			#doesn't work, not run in thread
			self._db_lock.acquire()
			self._db_lock.release()
			if self.db is None:
				for i in range(1,10):
					if self.db is not None:
						return self.db
					time.sleep(0.2)
				logging.warning("db not found, starting a new one")
				self._restart_db = True
				for i in range(1,15):
					if self.db is not None:
						break
					time.sleep(0.2)
				if self.db is None:
					logging.error("problem restarting the database")
				else:
					logging.warning("DB restarted successfully")
			return self.db
			
		def get_updater(self):
			return self.updater
	
		def goAway(self):
			
			""" Exit the run loop next time through."""
			logging.debug("got goAway signal, shutting down update thread")
			self.__isDying = True
			if self.db is not None:
				self.db.finish(vacuumok=False, correctthread=False)
				self.db = None
				
		def isDying(self):
			return self.__isDying
	
class CantChangeState(Exception):
	def __init__(self,m):
		self.m = m
	def __str__(self):
		return self.m
		
class AlreadyRunning(Exception):
	def __init__(self, remote_app):
		self.remote_app = remote_app

def usage():
	print "penguintv command line options:"
	print "   -o [filename]     Import an OPML file"
	print "   -u [filename]     Add an RSS url"
	print "   --play            Tell the media player to play"
	print "   --pause           Tell the media player to pause"
	print "   --playpause       Toggle between playing and pausing"
	print "   --prev            Go to the previous track"
	print "   --next            Go to the next track"
	print "   [filename]        (alternate) Import an RSS url"
	print "   -h | --help       This explanation"
		
def do_commandline(remote_app=None, local_app=None):
	assert remote_app is not None or local_app is not None
	
	try:
		opts, args = getopt.getopt(sys.argv[1:], "ho:u:", ["help","play","pause","prev","next","playpause","playlist"])
	except getopt.GetoptError:
		# print help information and exit:
		usage()
		sys.exit(2)
		
	#ignore --playlist, that is already taken care of before
	if len(opts) > 0:
		for o, a in opts:
			if o in ('-h', '--help'):
				usage()
				sys.exit(0)
			elif o == '-o':
				if local_app is None:
					remote_app.ImportOpml(a)
				else:
					local_app.import_subscriptions(a)
			elif o == '-u':
				if local_app is None:
					remote_app.AddFeed(a)
				else:
					if utils.RUNNING_SUGAR:
						local_app.sugar_add_button.popup()
					else:
						local_app.main_window.show_window_add_feed(False)
					local_app.main_window.set_window_add_feed_location(url)
			elif o == '--play':
				if remote_app is not None:
					remote_app.Play()
			elif o == '--pause':
				if remote_app is not None:
					remote_app.Pause()
			elif o == '--next':
				if remote_app is not None:
					remote_app.Next()
			elif o == '--prev':
				if remote_app is not None:
					remote_app.Prev()
			elif o == '--playpause':
				if remote_app is not None:
					remote_app.PlayPause()
				
	if len(opts) == 0 and len(sys.argv) > 1:
		url = sys.argv[1]
		if local_app is None:
			remote_app.AddFeed(url)
		else:
			if utils.RUNNING_SUGAR:
				local_app.sugar_add_button.popup()
			else:
				local_app.main_window.show_window_add_feed(False)
			local_app.main_window.set_window_add_feed_location(url)
			
	if len(opts) == 0 and len(sys.argv) == 1 and local_app is None:
		usage()

def do_quit(event, app):
	app.do_quit()
	
setup_success = True
def setup_database():
	global setup_success
	
	try:
		home = utils.get_home()
		os.stat(os.path.join(home,"penguintv4.db"))
		db=sqlite.connect(os.path.join(home,"penguintv4.db"), timeout=10)
		db.isolation_level="DEFERRED"
		c = db.cursor()
		c.execute(u'SELECT rowid FROM feeds LIMIT 1')
		c.execute(u'SELECT value FROM settings WHERE data="db_ver"')
		db_ver = c.fetchone()
		if db_ver is None: db_ver = 0
		else: db_ver = int(db_ver[0])
		latest_ver = ptvDB.LATEST_DB_VER
		#print "got without object:",db_ver, latest_ver
		c.close()
		db.close()
		return True
	except:
		logging.debug("Didn't get sqlite the easy way, trying the hard way")
		try:
			db = ptvDB.ptvDB()
			db_ver, latest_ver = db.get_version_info()
			db.finish(vacuumok=False)
		except Exception, e:
			logging.error("Couldn't open database: %s", str(e))
			return False
		
	def upgrade_db(dialog, cb):
		try:
			logging.info(_("Upgrading Database"))
			db = ptvDB.ptvDB()
			db.maybe_initialize_db()
			db.finish(vacuumok=False)
			logging.info("Done upgrading database")
			cb(True, dialog)
		except Exception, e:
			cb(False, dialog, str(e))
			
	def upgrade_done(success, dialog, errormsg=None):
		global setup_success
		setup_success = success
		if errormsg is not None:
			logging.error("Problem upgrading DB: %s" % errormsg)
		dialog.destroy()
		gtk.main_quit() 
		
	def pulse(progressbar):
		progressbar.pulse()
		return True
		
	def destroy(widget, data):
		gtk.main_quit()
		
	logging.info("Our database version: %i" % db_ver)
	logging.info("Program version: %i" % latest_ver)
	
	if db_ver == latest_ver:
		pass
	elif db_ver == -1:
		pass
	elif db_ver > latest_ver:
		logging.error("""The database you are running is from a later version of PenguinTV than the version you are currently running.  Please upgrade back to the latest version of PenguinTV.  To avoid errors and corruption, PenguinTV will quit now.""")
		dialog = gtk.Dialog(title=_("Database Version Mismatch"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_QUIT, gtk.RESPONSE_ACCEPT))
		frame = gtk.Frame()
		title = gtk.Label()
		title.set_use_markup(True)
		title.set_markup(_("<b>Database Version Mismatch</b>"))
		frame.set_label_widget(title)
		hbox = gtk.HBox()
		hbox.set_spacing(12)
		image = gtk.image_new_from_stock(gtk.STOCK_DIALOG_ERROR, gtk.ICON_SIZE_DIALOG)
		hbox.pack_start(image, False, False, 12)
		label = gtk.Label(_("""The database you are running is from a later version of PenguinTV than the version you are currently running.  To avoid errors and corruption, PenguinTV will quit now. 
		
Please upgrade back to the latest version of PenguinTV."""))
		label.set_line_wrap(True)
		hbox.pack_start(label, True, True, 12)
		frame.add(hbox)
		frame.set_border_width(12)
		dialog.vbox.pack_start(frame, True, True, 0)
		label.show()
		dialog.resize(400,200)
		response = dialog.show_all()
		dialog.connect("response", destroy)
		dialog.connect("destroy", destroy)
		gtk.main()
		return False
	elif db_ver < latest_ver:
		logging.info("""The PenguinTV database is being upgraded. This may take a few minutes.""")
		dialog = gtk.Dialog(title=_("Upgrading Database"), parent=None, flags=gtk.DIALOG_MODAL)
		frame = gtk.Frame()
		title = gtk.Label()
		title.set_use_markup(True)
		title.set_markup(_("<b>Upgrading Database</b>"))
		frame.set_label_widget(title)
		vbox = gtk.VBox()
		vbox.set_spacing(12)
		hbox = gtk.HBox()
		hbox.set_spacing(12)
		image = gtk.image_new_from_stock(gtk.STOCK_EXECUTE, gtk.ICON_SIZE_DIALOG)
		hbox.pack_start(image, False, False, 12)
		label = gtk.Label(_("""The PenguinTV database is being upgraded. This may take a few minutes."""))
		label.set_line_wrap(True)
		hbox.pack_start(label, True, True, 12)
		vbox.pack_start(hbox, True, True, 12)
		progressbar = gtk.ProgressBar()
		progressbar.set_pulse_step(0.05)
		vbox.pack_start(progressbar, False, False, 12)
		frame.add(vbox)
		frame.set_border_width(12)
		dialog.vbox.add(frame)
		dialog.resize(400,200)
		dialog.show_all()
		gobject.timeout_add(50, pulse, progressbar)
		
		t = threading.Thread(None, upgrade_db, args=(dialog, upgrade_done))
		t.start()
		
		gtk.main()
		return setup_success
	return True
		
if __name__ == '__main__': # Here starts the dynamic part of the program
	if utils.HAS_MOZILLA and not utils.HAS_WEBKIT:
		if not os.path.exists('/usr/lib/xulrunner-1.9'):
			if not os.environ.has_key('MOZILLA_FIVE_HOME'):
				print """MOZILLA_FIVE_HOME not set.  Please set before running Penguintv 
to prevent crashes."""
				sys.exit(1)
		
	gtk.gdk.threads_init()
	
	if HAS_DBUS:
		bus = dbus.SessionBus()
		dubus = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/dbus')
		dubus_methods = dbus.Interface(dubus, 'org.freedesktop.DBus')
		if dubus_methods.NameHasOwner('com.ywwg.PenguinTV'):
			remote_object = bus.get_object("com.ywwg.PenguinTV", "/PtvApp")
			remote_app = dbus.Interface(remote_object, "com.ywwg.PenguinTV.AppInterface")
			if remote_app.GetDatabaseName() == os.path.join(utils.get_home(), "penguintv4.db"):
				do_commandline(remote_app=remote_app)
				sys.exit(0)
		
	if not setup_database():
		logging.error("Error initializing database")
		sys.exit(1)
		
	if HAS_GNOME:
		logging.info("Have GNOME")
		
		gtk.window_set_auto_startup_notification(True)
		gnome.init("PenguinTV", utils.VERSION)
		playlist = None
		try:
			opts, args = getopt.getopt(sys.argv[1:], "p:", ["playlist="])
		except getopt.GetoptError, e:
			pass
		if len(opts) > 0:
			print opts
			for o, a in opts:
				if o in ('-p', '--playlist'):
					playlist = a
		try:
			app = PenguinTVApp(playlist=playlist)    # Instancing of the GUI
		except AlreadyRunning, e:
			logging.info("PenguinTV is already running, why didn't we catch it?")
			do_commandline(remote_app=e.remote_app)
			sys.exit(0)
		
		app.main_window.Show()
		
		#import psyco
		##psyco.log("/home/owen/Desktop/psyco.log")
		##psyco.profile()
		#psyco.full()

		if utils.is_kde():
			try:
				from kdecore import KApplication, KCmdLineArgs, KAboutData

				description = "test kde"
				version     = "1.0"
				aboutData   = KAboutData ("", "",\
				    version, description, KAboutData.License_GPL,\
				    "(C) 2004-2008 Owen Williams")
				KCmdLineArgs.init (sys.argv, aboutData)
				app = KApplication ()
				
			except:
				logging.error("Unable to initialize KDE")
				sys.exit(1)
	elif utils.RUNNING_HILDON: #no gnome, no gnomeapp
		logging.debug("Starting Hildon version")
		gtk.window_set_auto_startup_notification(True)
		app = PenguinTVApp()
		app.main_window.Show()
	else:
		logging.debug("No gnome")
		window = gtk.Window()
		app = PenguinTVApp()
		app.main_window.Show(window)
		window.connect('delete-event', do_quit, app)
	do_commandline(local_app=app)
	
	##PROFILE
	#import cProfile
	#cProfile.run('gtk.main()', '/tmp/penguintv-prof')
	#sys.exit(0)
	gtk.main()
