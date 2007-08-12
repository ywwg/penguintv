#!/usr/bin/env python
# Written by Owen Williams
# using pieces from Straw
# see LICENSE for license information

#states:
DEFAULT            = 1
MANUAL_SEARCH      = 2
TAG_SEARCH         = 3
LOADING_FEEDS      = 4
DONE_LOADING_FEEDS = 5

#memory profiling:

#import code
#from sizer import scanner
##objs = scanner.Objects()
##code.interact(local = {'objs': objs})
##from sizer import formatting

#import urlparse loaded as needed
from pysqlite2.dbapi2 import OperationalError as OperationalError
import threading
import sys, os, os.path
import gc
#gc.set_debug(gc.DEBUG_STATS | gc.DEBUG_SAVEALL)
import logging

logging.basicConfig(level=logging.DEBUG)

import urllib
try:
	import gnome
	import gnome.ui
	HAS_GNOME=True
except:
	HAS_GNOME=False
import time
import sets
import string
import socket
#socket.setdefaulttimeout(30.0)

import pygtk
pygtk.require('2.0')
import gtk
import gtk.glade
import gobject
import locale
import gettext
import getopt
try:
	import dbus
	import dbus.service
	HAS_DBUS = True
except:
	HAS_DBUS = False

locale.setlocale(locale.LC_ALL, '')
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

import AddFeedDialog
import PreferencesDialog
import MainWindow, FeedList, EntryList, EntryView

if utils.HAS_STATUS_ICON:
	import PtvTrayIcon

CANCEL=0
PAUSE=1

REFRESH_SPECIFIED=0
REFRESH_AUTO=1

if utils.RUNNING_SUGAR:
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
		'entry-updated': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_INT])),
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
		'online-status-changed':(gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
						   ([gobject.TYPE_BOOLEAN]))
	}

	def __init__(self, window=None):
		gobject.GObject.__init__(self)
		self._for_import = []
		self._app_loaded = False
		
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
					raise AlreadyRunning, remote_app
			#initialize dbus object
			name = dbus.service.BusName("com.ywwg.PenguinTV", bus=bus)
			ptv_dbus = ptvDbus.ptvDbus(self, name)
			
			sys_bus = dbus.SystemBus()
			
			try:
				sys_bus.add_signal_receiver(self._nm_device_no_longer_active,
											'DeviceNoLongerActive',
											'org.freedesktop.NetworkManager',
											'org.freedesktop.NetworkManager',
											'/org/freedesktop/NetworkManager')
	
				sys_bus.add_signal_receiver(self._nm_device_now_active,
											'DeviceNowActive',
											'org.freedesktop.NetworkManager',
											'org.freedesktop.NetworkManager',
											'/org/freedesktop/NetworkManager')
											
				nm_ob = sys_bus.get_object("org.freedesktop.NetworkManager", 
										   "/org/freedesktop/NetworkManager")
										   
				self._nm_interface = dbus.Interface(nm_ob, 
											  "org.freedesktop.NetworkManager")
				logging.info("Listening to NetworkManager")
			except:
				self._nm_interface = None
			
		self._net_connected = True
		self.connect('online-status-changed', self.__online_status_changed)
			
		found_glade = False
		
		self.glade_prefix = utils.get_glade_prefix()
		if self.glade_prefix is None:
			logging.error("error finding glade file.")
			sys.exit()
						
		logging.info("penguintv " + utils.VERSION + " startup")
			
		self.db = ptvDB.ptvDB(self._polling_callback, self._emit_change_setting)
		
		self._firstrun = self.db.maybe_initialize_db()

		self.db.clean_media_status()
		self.mediamanager = MediaManager.MediaManager(self, self._progress_callback, self._finished_callback)
		self._polled=0      #Used for updating the polling progress bar
		self._polling_taskinfo = -1 # the taskid we can use to waitfor a polling operation,
									# and the time of last polling
		self.polling_frequency=12*60*60*1000
		self._bt_settings = {}
		self._exiting=0
		self._auto_download = False
		self._auto_download_limiter = False
		self._auto_download_limit=50*1024
		self._saved_filter = FeedList.ALL
		self._saved_search = ""
		self._showing_search = False
		self._threaded_searcher = None
		self._waiting_for_search = False
		self._state = DEFAULT
				
		window_layout = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/app_window_layout', 'standard')
		if utils.RUNNING_SUGAR: window_layout='planet' #always use planet on sugar platform
		
		#stupid gconf will default to false if the key doesn't exist.  And of course the schema usually
		#doesn't work until they re-login...
		if not utils.RUNNING_SUGAR:
			use_internal_player = self.db.get_setting(ptvDB.BOOL, '/apps/penguintv/use_internal_player', True)
		else:
			use_internal_player = True
			
		self._status_icon = None
		if utils.HAS_STATUS_ICON:
			self._status_icon = PtvTrayIcon.PtvTrayIcon(self, 
							         utils.get_image_path('penguintvicon.png'))	
			
		self.main_window = MainWindow.MainWindow(self, self.glade_prefix, use_internal_player, window=window, status_icon=self._status_icon) 
		self.main_window.layout=window_layout
		
		#some signals
		self.connect('feed-added', self.__feed_added_cb)
		
	def post_show_init(self):
		"""After we have Show()n the main window, set up some more stuff"""
		#gtk.gdk.threads_enter()
		
		gst_player = self.main_window.get_gst_player()
		self.player = Player.Player(gst_player)
		if gst_player is not None:
			gst_player.connect('item-not-supported', self._on_item_not_supported)
		self._gui_updater = UpdateTasksManager.UpdateTasksManager(UpdateTasksManager.GOBJECT, "gui updater")
		self._update_thread = self.DBUpdaterThread(self._polling_callback, 
												   self._reset_db_updater)
		self._update_thread.start()
		self._updater_thread_db = None
		while self._updater_thread_db==None or self._db_updater == None:
			#this may race, so be patient 
			self._updater_thread_db = self._update_thread.get_db()
			self._db_updater = self._update_thread.get_updater()
			time.sleep(.1)

		#WINDOWS
		self.window_add_feed = AddFeedDialog.AddFeedDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_add_feed",'penguintv'),self) #MAGIC
		self.window_add_feed.hide()
		self.window_preferences = PreferencesDialog.PreferencesDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_preferences",'penguintv'),self) #MAGIC
		self.window_preferences.hide()
					
		#gconf
		if utils.HAS_GCONF:
			import gconf
			conf = gconf.client_get_default()
			conf.add_dir('/apps/penguintv',gconf.CLIENT_PRELOAD_NONE)
			conf.notify_add('/apps/penguintv/auto_resume',self._gconf_set_auto_resume)
			conf.notify_add('/apps/penguintv/poll_on_startup',self._gconf_set_poll_on_startup)
			conf.notify_add('/apps/penguintv/bt_max_port',self._gconf_set_bt_maxport)
			conf.notify_add('/apps/penguintv/bt_min_port',self._gconf_set_bt_minport)
			conf.notify_add('/apps/penguintv/ul_limit',self._gconf_set_bt_ullimit)
			conf.notify_add('/apps/penguintv/feed_refresh_frequency',self._gconf_set_polling_frequency)
			conf.notify_add('/apps/penguintv/app_window_layout',self._gconf_set_app_window_layout)
			conf.notify_add('/apps/penguintv/feed_refresh_method',self._gconf_set_feed_refresh_method)
			conf.notify_add('/apps/penguintv/show_notifications',self._gconf_set_show_notifications)
			conf.notify_add('/apps/penguintv/auto_download',self._gconf_set_auto_download)
			conf.notify_add('/apps/penguintv/show_notification_always',self._gconf_set_show_notification_always)
			conf.notify_add('/apps/penguintv/auto_download_limiter',self._gconf_set_auto_download_limiter)
			conf.notify_add('/apps/penguintv/auto_download_limit',self._gconf_set_auto_download_limit)

		self._load_settings()
		
		self.feed_list_view = self.main_window.feed_list_view
		self._entry_list_view = self.main_window.entry_list_view
		self._entry_view = self.main_window.entry_view
		
		self._entry_view.display_item()
		
		self._connect_signals()
		
		self.main_window.search_container.set_sensitive(False)
		if utils.HAS_LUCENE:
			if self.db.cache_dirty or self.db.searcher.needs_index: #assume index is bad as well or if it is bad
				self.main_window.search_entry.set_text(_("Please wait..."))
				self.main_window.display_status_message(_("Reindexing Feeds..."))
				self.db.doindex(self._sensitize_search)
				self._populate_feeds(self._done_populating_dont_sensitize)
			else:
				self._populate_feeds(self._done_populating)
		else:
			##PROFILE: comment out
			self._populate_feeds(self._done_populating)

		if self._autoresume:
			gobject.idle_add(self.resume_resumable)
		self.update_disk_usage()
		if self._firstrun:
			self._import_default_feeds()
		elif self.poll_on_startup: #don't poll on startup on firstrun, we take care of that
			gobject.timeout_add(30*1000,self.do_poll_multiple, 0)
		
		#gtk.gdk.threads_leave()
		self.emit('app-loaded')
		self._app_loaded = True
		return False #for idler	
		
	def _import_default_feeds(self):
		found_subs = False
		for path in (os.path.join(utils.GetPrefix(), "share" ,"penguintv"),
					 os.path.join(utils.GetPrefix(), "share"),
					 os.path.join(utils.GetPrefix(),"share","sugar","activities","ptv","share"),
					 os.path.join(os.path.split(os.path.split(utils.__file__)[0])[0],'share')):
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
		self._entry_list_view.connect('entry-selected', self.__entry_selected_cb)
		self.feed_list_view.connect('state-change', self.__feedlist_state_change_cb)
		self._entry_view.connect('entry-selected', self.__entry_selected_cb)
		self._entry_view.connect('entries-selected', self.__entries_selected_cb)
		
	def __entry_selected_cb(self, o, entry_id, feed_id):
		if self._state == MANUAL_SEARCH or self._state == TAG_SEARCH and feed_id != -1:
			self.select_feed(feed_id)
		#FIXME: we're not passing the query for highlighting purposes here
		self.display_entry(entry_id)
		
	def __entries_selected_cb(self, o, feed_id, entrylist):
		self.mark_entrylist_as_viewed(entrylist, False)
		
	def __feedlist_state_change_cb(self, o, new_state):
		self.set_state(new_state)
		
	def __online_status_changed(self, o, connected):
		self._net_connected = connected
		if not self._net_connected:
			if self._updater_thread_db:
				self._updater_thread_db.interrupt_poll_multiple()
			if self.db:
				self.db.interrupt_poll_multiple()
		
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
			else:
				self.feed_refresh_method=REFRESH_SPECIFIED
		self.window_preferences.set_feed_refresh_method(self.feed_refresh_method)
		
		
		if self.feed_refresh_method == REFRESH_AUTO:
			gobject.timeout_add(AUTO_REFRESH_FREQUENCY,self.do_poll_multiple, AUTO_REFRESH_FREQUENCY)
		else:
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
			
	def save_settings(self):
		self.db.set_setting(ptvDB.INT, '/apps/penguintv/feed_pane_position', self.main_window.feed_pane.get_position())
		self.db.set_setting(ptvDB.INT, '/apps/penguintv/entry_pane_position', self.main_window.entry_pane.get_position())
		if self.main_window.app_window is not None:
			x,y=self.main_window.app_window.get_position()
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/app_window_position_x',x)
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/app_window_position_y',y)
			if self.main_window.window_maximized == False:
				x,y=self.main_window.app_window.get_size()
			else: #grabbing the size when we are maximized is pointless, so just go by the old resized size
				x = self.db.get_setting(ptvDB.INT, '/apps/penguintv/app_window_size_x', 500)
				y = self.db.get_setting(ptvDB.INT, '/apps/penguintv/app_window_size_y', 500)
				x,y=(-abs(x),-abs(y))
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/app_window_size_x',x)
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/app_window_size_y',y)
		
		self.db.set_setting(ptvDB.STRING, '/apps/penguintv/app_window_layout',self.main_window.layout)
		if self.feed_refresh_method==REFRESH_AUTO:
			self.db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method','auto')
		else:
			self.db.set_setting(ptvDB.INT, '/apps/penguintv/feed_refresh_frequency',self.polling_frequency/(60*1000))
			self.db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method','specified')	
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
		#self.db.set_setting(ptvDB.BOOL, '/apps/penguintv/use_internal_player', self.player.using_internal_player())
	
	def resume_resumable(self):
		list = self.db.get_resumable_media()
		if list:
			gobject.idle_add(self._resumer_generator(list).next)
		return False #to cancel idler
		
	def _resumer_generator(self, list):
		for medium in list:
			#gtk.gdk.threads_enter()
			self.mediamanager.download(medium['media_id'], False, True) #resume please
			self.db.set_entry_read(medium['entry_id'],False)
			self.feed_list_view.update_feed_list(medium['feed_id'],['icon'])
			#gtk.gdk.threads_leave()
			yield True
		#gtk.gdk.threads_leave()
		yield False
		
	def do_quit(self):
		"""save and shut down all our threads"""
		
		##good breakpoint for gc analysis
		#import code
		#code.interact()
		
		logging.info('ptv quitting')
		self._exiting=1
		self._entry_view.finish()
		self.feed_list_view.interrupt()
		self._update_thread.goAway()
		self._updater_thread_db.finish(False)
		self.main_window.finish()
		logging.info('stopping downloads')
		self.stop_downloads()
		logging.info('saving settings')
		self.save_settings()
		#if anything is downloading, report it as paused, because we pause all downloads on quit
		adjusted_cache = [[c[0],(c[1] & ptvDB.F_DOWNLOADING and c[1]-ptvDB.F_DOWNLOADING+ptvDB.F_PAUSED or c[1]),c[2],c[3]] for c in self.feed_list_view.get_feed_cache()]
		self.db.set_feed_cache(adjusted_cache)
		logging.info('stopping db')
		self.db.finish()	
		logging.info('stopping mediamanager')
		self.mediamanager.finish()
		#while threading.activeCount()>1:
		#	print threading.enumerate()
		#	print str(threading.activeCount())+" threads active..."
		#	time.sleep(1)
		
		if not utils.RUNNING_SUGAR:
			gtk.main_quit()
		
	def write_feed_cache(self):
		self.db.set_feed_cache(self.feed_list_view.get_feed_cache())
		
	def do_poll_multiple(self, was_setup=None, arguments=0, feeds=None):
		""""was_setup":  So do_poll_multiple is going to get called by timers 
			and manually, and we needed some way of saying "I've got a new 
			frequency, stop the old timer and start the new one."  so it 
			checks to see that the frequency it 'was setup' with is the same 
			as the current frequency.  If not, exit with False to stop 
			the timer."""
		
		if was_setup is not None:
			if self.feed_refresh_method==REFRESH_AUTO:
				if was_setup==0: #initial poll
					arguments = arguments | ptvDB.A_ALL_FEEDS
				arguments = arguments | ptvDB.A_AUTOTUNE 
			else:
				if was_setup!=self.polling_frequency and was_setup!=0:
					return False
					
		if not self._net_connected:
			return True

		if self._polling_taskinfo != -1:
			logging.debug("I think we are already polling")
			logging.debug("poll id set: %i %d (%d)" % (self._polling_taskinfo, time.time(), time.time() - self._polling_taskinfo))
			if time.time() - self._polling_taskinfo > 20*60:
				logging.debug("poll id reset")
				logging.debug("but it's been an awful long time.  Polling anyway")
				self._polling_taskinfo = -1
			else:
				return True
		#gtk.gdk.threads_enter()

		self.main_window.update_progress_bar(0,MainWindow.U_POLL)
		self.main_window.display_status_message(_("Polling Feeds..."), MainWindow.U_POLL)			
		task_id = self._db_updater.queue(self._updater_thread_db.poll_multiple, (arguments,feeds))
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
	
	def _auto_download_unviewed(self):
	
		"""Automatically download any unviewed media.  Runs every five minutes 
		when auto-polling, so make sure is good"""
		
		download_list=self.db.get_media_for_download(False) #don't resume paused downloads
		if len(download_list)==0:
			return #no need to bother
		
		total_size = 0
		for d in download_list:
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
			
	def _free_media_space(self, size_needed):
		
		"""deletes media so that we have at least 'size_needed' bytes of free space.
		Returns True if successful, returns False if not (ie, too big)"""
		
		disk_total = utils.get_disk_total(self.mediamanager.media_dir)
		disk_usage = self.mediamanager.get_disk_usage()
		disk_free = utils.get_disk_free(self.mediamanager.media_dir)
		
		
		#adjust actual free space so we never fill up the drive
		if utils.RUNNING_SUGAR:
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
			media_in_player = [m[3] for m in media_in_player]
			
		media_to_remove = []
		removed_size = 0
		for media_id,entry_id,feed_id,filename,date in self.db.get_deletable_media():
			if removed_size >= size_to_free:
				disk_usage = self.mediamanager.get_disk_usage()
				if self._auto_download_limiter:
					if self._auto_download_limit*1024 - disk_usage < size_needed:
						logging.error("didn't free up the space like we thought1")
						return False
				if utils.get_disk_free(self.mediamanager.media_dir) < size_needed + free_buffer:
					logging.error("didn't free up the space like we thought2" + str(utils.get_disk_free(self.mediamanager.media_dir)))
					return False
				return True
				
			#don't remove anything that's queued in the player
			if utils.HAS_GSTREAMER:
				if media_id in media_in_player:
					continue
			
			size = os.stat(filename)[6]
			removed_size += size
			logging.info("removing:" + filename +str(size) + "bytes for a total of" + str(removed_size))
			self.db.delete_media(media_id)
			self.db.set_entry_read(entry_id, True)
			self.emit('entry-updated', entry_id, feed_id)
		return False
		
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
			
	def remove_search_tag(self, tag_name):
		self.db.remove_tag(tag_name)
		self.emit('tags-changed', 0)
		while gtk.events_pending():
			gtk.main_iteration()
			
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

	def apply_tags_to_feed(self, feed_id, old_tags, new_tags):
		"""take a list of tags and apply it to a feed"""
		old_set = sets.Set(old_tags)
		new_set = sets.Set(new_tags)
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
		self.set_state(LOADING_FEEDS)
		self.main_window.display_status_message(_("Loading Feeds..."))
		self.feed_list_view.populate_feeds(callback, subset)
					
	def display_entry(self, entry_id, set_read=1, query=""):
		if entry_id is not None:
			item = self.db.get_entry(entry_id)
			media = self.db.get_entry_media(entry_id)
			if media:
				item['media']=media
		else:
			self._entry_view.display_item()
			return
			
		if item.has_key('media') == False:
			if item['read']==0 and set_read==1:
				self.db.set_entry_read(entry_id,1)
				self._entry_list_view.mark_as_viewed(entry_id)
				self.feed_list_view.mark_entries_read(1, feed_id=item['feed_id'])
				for f in self.db.get_pointer_feeds(item['feed_id']):
					self.feed_list_view.update_feed_list(f,['readinfo','icon'])
		self._entry_view.display_item(item, query)
	
	def display_custom_entry(self, message):
		"""Used by other classes so they don't need to know about EntryView"""
		self._entry_view.display_custom_entry(message)
		
	def undisplay_custom_entry(self):
		"""Used by other classes so they don't need to know about EntryView"""
		self._entry_view.undisplay_custom_entry()
	
	def activate_link(self, link):
		"""links can be basic hrefs, or they might be custom penguintv commands"""
		import urlparse
		parsed_url = urlparse.urlparse(link)
		action=parsed_url[0] #protocol
		parameters=parsed_url[3]
		http_arguments=parsed_url[4]
		anchor = parsed_url[5]
		try:
			item=int(parsed_url[2])
		except:
			pass
		if action == "download":
			self.mediamanager.unpause_downloads()
			self.mediamanager.download(item)
			entry_id = self.db.get_entryid_for_media(item)
			self.db.set_media_viewed(item,False)
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
			self.db.set_entry_read(media['entry_id'],True)
			self.db.set_media_viewed(item,True)
			if utils.is_known_media(media['file']):
				self.player.play(media['file'], feed_title + " &#8211; " + entry['title'], media['media_id'])
			else:
				if HAS_GNOME:
					gnome.url_show(media['file'])
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
				reveal_url = "file:" + urllib.quote(parsed_url[1]+parsed_url[2])
				os.system('konqueror --select ' + reveal_url + ' &')
			else:
				reveal_url = "file:"+os.path.split(urllib.quote(parsed_url[1]+parsed_url[2]))[0]
				if HAS_GNOME:
					gnome.url_show(reveal_url)
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
			if HAS_GNOME:
				gnome.url_show(parsed_url[0]+"://"+quoted_url+parameters+http_arguments+anchor)
			elif utils.RUNNING_SUGAR:
				from sugar.activity import activityfactory
				uri=parsed_url[0]+"://"+quoted_url+parameters+http_arguments+anchor
				activityfactory.create_with_uri('org.laptop.WebActivity', uri)
		elif action=="file":
			logging.info(parsed_url[0]+"://"+urllib.quote(parsed_url[1]+parsed_url[2]))
			if HAS_GNOME:
				gnome.url_show(parsed_url[0]+"://"+urllib.quote(parsed_url[1]+parsed_url[2]))
			
	def download_entry(self, entry_id):
		self.mediamanager.download_entry(entry_id)
		feed_id = self.db.get_entry(entry_id)['feed_id']
		self.emit('entry-updated', entry_id, feed_id)

	def download_unviewed(self):
		self.mediamanager.unpause_downloads()
		feeds = self.db.get_feedlist()
		download_list=self.db.get_media_for_download()
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
				task_id = self._db_updater.queue(self._updater_thread_db.export_OPML, f)
				self._gui_updater.queue(self.main_window.display_status_message, "", task_id)
			except:
				pass
		elif response == gtk.RESPONSE_CANCEL:
			#print 'Closed, no files selected'
			pass
		dialog.destroy()

	def remove_feed(self, feed):		
		#select entries and get all the media ids, and tell them all to cancel
		#in case they are downloading
		try:
			for entry_id,title,date,read in self.db.get_entrylist(feed):
				for medium in self.db.get_entry_media(entry_id):
					if self.mediamanager.has_downloader(medium['media_id']):
						self.mediamanager.stop_download(medium['media_id'])
		except:
			pass
		self.db.delete_feed(feed)
		self.emit('feed-removed', feed)
		self.update_disk_usage()
	
	def poll_feeds(self, args=0):
		args = args | ptvDB.A_ALL_FEEDS
		if self.feed_refresh_method==REFRESH_AUTO:
			args = args | ptvDB.A_AUTOTUNE
		self.do_poll_multiple(None, args)
			
	def import_subscriptions(self, f, opml=True):
		if self._state == LOADING_FEEDS or not self._app_loaded:
			self._for_import.append((1, f))
			return
	
		def import_gen(f):
			#gtk.gdk.threads_enter()
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
			#gtk.gdk.threads_leave()
			for feed in gen:
				#gtk.gdk.threads_enter()
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
					#gtk.gdk.threads_leave()
					yield False
				#self.feed_list_view.add_feed(feed)
				if feed[0]==1:
					newfeeds.append(feed[1])
				elif feed[0]==0:
					oldfeeds.append(feed[1])
				bar.set_fraction(i/feed_count)
				i+=1.0
				#gtk.gdk.threads_leave()
				yield True
			#gtk.gdk.threads_enter()
			if len(newfeeds)>10:
				#it's faster to just start over if we have a lot of feeds to add
				self.main_window.search_container.set_sensitive(False)
				self.feed_list_view.clear_list()
				self._populate_feeds(self._done_populating)
			else:
				for feed in newfeeds:
					self.feed_list_view.add_feed(feed)
			self.emit('tags-changed', 0)
			saved_auto = False
			self.main_window.display_status_message("")
			#shut down auto-downloading for now (need to wait until feeds are marked)
			if self._auto_download:
				saved_auto = True
				self._auto_download = False
			self.do_poll_multiple(feeds=newfeeds)
			task_id = self._gui_updater.queue(self.__first_poll_marking_list, (newfeeds,saved_auto), self._polling_taskinfo)
			dialog.hide()
			del dialog
			if len(newfeeds)==1:
				self.feed_list_view.set_selected(newfeeds[0])
			elif len(oldfeeds)==1:
				self.feed_list_view.set_selected(oldfeeds[0])
			#gtk.gdk.threads_leave()
			yield False
		#schedule the import pseudo-threadidly
		gobject.idle_add(import_gen(f).next)
					
	def __first_poll_marking_list(self, list, saved_auto=False):
		def marking_gen(list):
			#gtk.gdk.threads_enter()
			self.main_window.display_status_message(_("Finishing OPML import"))
			selected = self.feed_list_view.get_selected()
			#gtk.gdk.threads_leave()
			for feed in list:
				#gtk.gdk.threads_enter()
				self._first_poll_marking(feed)
				self.feed_list_view.update_feed_list(feed,['readinfo','icon','title'])
				if feed == selected:
					self._entry_list_view.update_entry_list()
				#gtk.gdk.threads_leave()
				yield True
			#gtk.gdk.threads_enter()
			self.main_window.display_status_message("")
			if saved_auto:
				self._auto_download_unviewed()
				self._reset_auto_download()
			#gtk.gdk.threads_leave()
			yield False
		
		gobject.idle_add(marking_gen(list).next)

	def _reset_auto_download(self):
		self._auto_download = True
			
	def mark_entry_as_viewed(self,entry, feed_id, update_entrylist=True):
		self.db.set_entry_read(entry,True)
		if update_entrylist: #hack for PlanetView
			self.update_entry_list(entry)
		self.feed_list_view.mark_entries_read(1, feed_id)
		
	def mark_entrylist_as_viewed(self, entrylist, update_entrylist=True):
		if len(entrylist) == 0:
			return
		self.db.set_entrylist_read(entrylist,True)
		for e in entrylist:
			if update_entrylist: #hack for PlanetView
				self.update_entry_list(e)
		self.feed_list_view.mark_entries_read(len(entrylist))
			
	def mark_entry_as_unviewed(self,entry):
		media = self.db.get_entry_media(entry)
		self.db.set_entry_read(entry, 0)
		if media:
			for medium in media:
				self.db.set_media_viewed(medium['media_id'],False)
			self.update_entry_list(entry)
		else:
			self.db.set_entry_read(entry, 0)
			self.update_entry_list(entry)
		self.feed_list_view.mark_entries_read(-1)
		
	def mark_feed_as_viewed(self,feed):
		self.db.mark_feed_as_viewed(feed)
		self._entry_list_view.populate_entries(feed)
		self.feed_list_view.update_feed_list(feed,['readinfo'],{'unread_count':0})

	def play_entry(self,entry_id):
		media = self.db.get_entry_media(entry_id)
		entry = self.db.get_entry(entry_id)
		feed_title = self.db.get_feed_title(entry['feed_id'])
		self.db.set_entry_read(entry_id, True)
		filelist=[]
		if media:
			for medium in media:
				filelist.append([medium['file'], feed_title + " &#8211; " + entry['title'], medium['media_id']])
				self.db.set_media_viewed(medium['media_id'],True)
		self.player.play_list(filelist)
		self.emit('entry-updated', entry_id, entry['feed_id'])
		
	def play_unviewed(self):
		#objs = scanner.Objects()
		#code.interact(local = {'objs': objs})
		#code.interact()
		#return
		playlist = self.db.get_unplayed_media(True) #set viewed
		playlist.reverse()
		self.player.play_list([[item[3],item[5] + " &#8211; " + item[4], item[0]] for item in playlist])
		for row in playlist:
			self.feed_list_view.update_feed_list(row[2],['readinfo'])
			
	def _on_item_not_supported(self, player, filename, name, userdata):
		if not utils.RUNNING_SUGAR:
			self.player.play(filename, name, userdata, force_external=True) #retry, force external player
		else:
			dialog = gtk.Dialog(title=_("Unknown file type"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label("Gstreamer did not recognize this file. (email owen-olpc@ywwg.com for more info)")
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			dialog.set_transient_for(self.main_window.get_parent())
			response = dialog.run()
			dialog.hide()
			del dialog
			return

	def refresh_feed(self, feed):
		if not self._net_connected:
			return
			
		def _refresh_cb(update_data, success):
			self._threaded_emit('feed-polled', feed, update_data)
		self.main_window.display_status_message(_("Polling Feed..."))
		task_id = self._db_updater.queue(self._updater_thread_db.poll_feed_trap_errors,(feed,  _refresh_cb))
		
	def _unset_state(self, authorize=False):
		"""gets app ready to display new state by unloading current state.
		Also checks if we are loading feeds, in which case state can not change.
		
		To unset loading_feeds, we take a "manual override" argument"""
				
		#bring state back to default
		
		if self._state != MANUAL_SEARCH:
			#save filter for later
			self._saved_filter = self.main_window.get_active_filter()[1]
		
		if self._state == LOADING_FEEDS:
			if not authorize:
				raise CantChangeState,"can't interrupt feed loading"
			else:
				self._state = DONE_LOADING_FEEDS #we don't know what the new state will be...
				return
				
		if self._state == DEFAULT:
			return
	
	def set_state(self, new_state, data=None):
		if self._state == new_state:
			return	
			
		if new_state == DEFAULT and self._state == LOADING_FEEDS:
			return #do nothing

		self._unset_state()
			
		if new_state == MANUAL_SEARCH:
			pass
		elif new_state == TAG_SEARCH:
			pass
		elif new_state == LOADING_FEEDS:
			pass
			
		self.main_window.set_state(new_state, data)
		self._entry_view.set_state(new_state, data)
		self._entry_list_view.set_state(new_state, data)
		self.feed_list_view.set_state(new_state, data)
		
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
		
	def _search(self, query, blacklist=None):
		try:
			query = query.replace("!","")
			result = self.db.search(query, blacklist=blacklist)
		except Exception, e:
			logging.warning("Error with that search term: " + str(query) + str(e))
			result=([],[])
		return result
	
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
		
	def highlight_entry_results(self, feed_id):
		return self._entry_list_view.highlight_results(feed_id)
		
	def select_feed(self, feed_id):
		self.feed_list_view.set_selected(feed_id)
		
	def select_entry(self, entry_id):
		feed_id = self.db.get_entry(entry_id)['feed_id']
		self.select_feed(feed_id)
		self.display_entry(entry_id)
		self.main_window.notebook_select_page(0)

	def change_filter(self, current_filter, tag_type):
		filter_id = self.main_window.get_active_filter()[1]
		if utils.HAS_LUCENE and filter_id == FeedList.SEARCH:
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
		
	def stop_downloads(self):
		"""stops downloading everything -- really just pauses them.  Just sets a flag, really.
		progress_callback does the actual work"""
		if self.mediamanager.pause_state == MediaManager.RUNNING:
			download_stopper_thread = threading.Thread(None, self.mediamanager.stop_all_downloads)
			download_stopper_thread.start() #this isn't gonna block any more!
			self.db.pause_all_downloads() #blocks, but prevents race conditions

	def pause_downloads(self):
		if self.mediamanager.pause_state == MediaManager.RUNNING:
			download_pauser_thread = threading.Thread(None, self.mediamanager.pause_all_downloads)
			download_pauser_thread.start() #this isn't gonna block any more!
			self.db.pause_all_downloads() #blocks, but prevents race conditions
			
	def change_layout(self, layout):
		if self.main_window.layout != layout:
			selected = self.feed_list_view.get_selected()
			old_filter = self.main_window.get_active_filter()[1]
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
			while gtk.events_pending(): #wait for pop to be done, _then_ select
				gtk.main_iteration()
			self.update_disk_usage()
			new_selected = self.feed_list_view.get_selected()
			new_filter = self.main_window.get_active_filter()[1]
			#don't set selected if they've done anything since the switch
			if new_selected is None and selected is not None and old_filter == new_filter:
				self.feed_list_view.set_selected(selected)
			
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
		self._bt_settings['ullimit']=ullimit
			
	def _gconf_set_polling_frequency(self, client, *args, **kwargs):
		freq = client.get_int('/apps/penguintv/feed_refresh_frequency')
		self.set_polling_frequency(freq)
			
	def set_polling_frequency(self, freq):
		if self.polling_frequency != freq*60*1000:
			self.polling_frequency = freq*60*1000	
			gobject.timeout_add(self.polling_frequency,self.do_poll_multiple, self.polling_frequency)
			self.window_preferences.set_feed_refresh_frequency(freq)
			
	def get_feed_refresh_method(self):
		return self.feed_refresh_method
		
	def _gconf_set_feed_refresh_method(self, client, *args, **kwargs):
		refresh = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method', 'auto')
		self.set_feed_refresh_method(refresh, client)
		
	def set_feed_refresh_method(self, refresh, client=None):
		if refresh == 'auto':
			self.feed_refresh_method=REFRESH_AUTO
			self.polling_frequency = AUTO_REFRESH_FREQUENCY	
			gobject.timeout_add(self.polling_frequency,self.do_poll_multiple, self.polling_frequency)
		else:
			self.feed_refresh_method=REFRESH_SPECIFIED
			if utils.HAS_GCONF:
				self._gconf_set_polling_frequency(client,None,None)
			else:
				self.set_polling_frequency(self.db.get_setting(ptvDB.INT, '/apps/penguintv/feed_refresh_frequency', 5))
			
	def add_feed(self, url, title):
		"""Inserts the url and starts the polling process"""
		
		if self._state == LOADING_FEEDS or not self._app_loaded:
			self._for_import.append((0, url, title))
			return
		
		self.main_window.display_status_message(_("Trying to poll feed..."))
		feed_id = -1
		try:
			feed_id = self.db.insertURL(url, title)
			#change to add_and_select (can't use signals because order is important)
			self.feed_list_view.add_feed(feed_id)
			self.main_window.select_feed(feed_id)
			self._db_updater.queue(self._updater_thread_db.poll_feed_trap_errors, (feed_id,self._db_add_feed_cb))
		except ptvDB.FeedAlreadyExists, e:
			self.main_window.select_feed(e.feed)
		self.window_add_feed.hide()
		return feed_id
		
	def _db_add_feed_cb(self, feed, success):
		self._threaded_emit('feed-polled', feed['feed_id'], feed)
		self._threaded_emit('feed-added', feed['feed_id'], success)
		
	def __feed_added_cb(self, app, feed_id, success):
		if success:
			self._first_poll_marking(feed_id)
			if self._auto_download:
				self._auto_download_unviewed()
		
	def _first_poll_marking(self, feed_id): 
		"""mark all media read except first one.  called when we first add a feed"""
		all_feeds_list = self.db.get_media_for_download()
		this_feed_list = [item for item in all_feeds_list if item[3] == feed_id]
		for item in this_feed_list[1:]:
			self.db.set_entry_read(item[2],1)
			self.emit('entry-updated', item[2], feed_id)
	
	def add_feed_filter(self, pointed_feed_id, filter_name, query):
		try:
			feed_id = self.db.add_feed_filter(pointed_feed_id, filter_name, query)
		except ptvDB.FeedAlreadyExists, f:
			self.main_window.select_feed(f)
			return
		self.feed_list_view.add_feed(feed_id)
		self.main_window.select_feed(feed_id)
		
	def set_feed_filter(self, pointer_feed_id, filter_name, query):
		self.db.set_feed_filter(pointer_feed_id, filter_name, query)
		self.display_feed(pointer_feed_id)
			
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
		
	def delete_media(self, media_id, update_ui=True):
		"""Deletes specific media id"""
		self.db.delete_media(media_id)
		self.main_window.update_downloads()
		self.mediamanager.generate_playlist()
		self.db.set_media_viewed(media_id,True)
		self.update_disk_usage()
		if update_ui:
			m = self.db.get_media(media_id)
			self.emit('entry-updated', m['entry_id'], m['feed_id'])
		
	def delete_feed_media(self, feed_id):
		"""Deletes media for an entire feed.  Calls generator _delete_media_generator"""
		gobject.idle_add(self._delete_media_generator(feed_id).next)
		
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
				self._entry_view.update_if_selected(entry[0])
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
		
	def do_cancel_download(self, item):
		"""cancels a download and cleans up.  Right now there's redundancy because we call this twice
		   for files that are downloading -- once when we ask it to stop downloading, and again when the
		   callback tells the thread to stop working.  how to make this better?"""
		
		d = None
		try:   
			d = self.mediamanager.get_downloader(item['media_id'])
			self.mediamanager.stop_download(item['media_id'])
		except:
			pass
		self.db.set_media_download_status(item['media_id'],ptvDB.D_NOT_DOWNLOADED)
		self.delete_media(item['media_id']) #marks as viewed
		self.main_window.update_download_progress()
		if self._exiting:
			self.feed_list_view.filter_all() #to remove active downloads from the list
			return
		try:
			feed_id = self.db.get_entry(item['entry_id'])['feed_id']
			self.emit('entry-updated', item['entry_id'], feed_id)
		except ptvDB.NoEntry:
			logging.warning("noentry error, don't worry about it")
			#print "downloads finished pop"
			#taken care of in callbacks?
			self.main_window.search_container.set_sensitive(False)
			self._populate_feeds(self._done_populating, FeedList.DOWNLOADED)
			self.feed_list_view.resize_columns()
		self.feed_list_view.filter_all() #to remove active downloads from the list
		if d is not None:
			self.emit('download-finished', d)
		
	def do_pause_download(self, media_id):
		self.mediamanager.get_downloader(media_id).pause()
		self.db.set_media_download_status(media_id,ptvDB.D_RESUMABLE)
		self.db.set_media_viewed(media_id,0)
		self.db.set_entry_read(media_id,0)
		
	def do_resume_download(self, media_id):
		self.mediamanager.unpause_downloads()
		self.mediamanager.download(media_id, False, True) #resume please
		self.db.set_media_viewed(media_id,False)
		entry_id = self.db.get_entryid_for_media(media_id)
		feed_id = self.db.get_entry(entry_id)['feed_id']
		self.emit('entry-updated', entry_id, feed_id)
		
	def _download_finished(self, d):
		"""Process the data from a callback for a downloaded file"""
		
		self.update_disk_usage()
		if d.status==Downloader.FAILURE: 
			self.db.set_media_download_status(d.media['media_id'],ptvDB.D_ERROR) 
		elif d.status==Downloader.STOPPED or d.status==Downloader.PAUSED:
			self.main_window.update_download_progress()
		elif d.status==Downloader.FINISHED or d.status==Downloader.FINISHED_AND_PLAY:
			if os.stat(d.media['file'])[6] < int(d.media['size']/2) and os.path.isfile(d.media['file']): #don't check dirs
				self.db.set_entry_read(d.media['entry_id'],False)
				self.db.set_media_viewed(d.media['media_id'],False)
				self.db.set_media_download_status(d.media['media_id'],ptvDB.D_DOWNLOADED)
				d.status = Downloader.FAILURE
			else:
				self.main_window.update_download_progress()
				if d.status==Downloader.FINISHED_AND_PLAY:
					self.db.set_entry_read(d.media['entry_id'],True)
					self.db.set_media_viewed(d.media['media_id'], True)
					entry = self.db.get_entry(d.media['entry_id'])
					feed_title = self.db.get_feed_title(entry['feed_id'])
					self.player.play(d.media['file'], feed_title + " &#8211; " + entry['title'], d.media['media_id'])
				else:
					self.db.set_entry_read(d.media['entry_id'],False)
					self.db.set_media_viewed(d.media['media_id'],False)
				self.db.set_media_download_status(d.media['media_id'],ptvDB.D_DOWNLOADED)	
		self.emit('download-finished', d)
		if self._exiting:
			self.feed_list_view.filter_all() #to remove active downloads from the list
			return
		try:
			feed_id = self.db.get_entry(d.media['entry_id'])['feed_id']
			self.emit('entry-updated', d.media['entry_id'], feed_id)
		except ptvDB.NoEntry:
			logging.warning("noentry error")
			#print "downloads finished pop"
			#taken care of in callbacks?
			self.main_window.search_container.set_sensitive(False)
			self._populate_feeds(self._done_populating, FeedList.DOWNLOADED)
			self.feed_list_view.resize_columns()
		except:
			logging.warning("some other error")
		self.feed_list_view.filter_all() #to remove active downloads from the list
			
	def rename_feed(self, feed_id, name):
		if len(name)==0:
			self.db.set_feed_name(feed_id, None) #gets the title the feed came with
		else:
			self.db.set_feed_name(feed_id, name)
		self.feed_list_view.update_feed_list(feed_id,['title'],{'title':name})
		self.feed_list_view.resize_columns()	
		
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
		
	def _gconf_set_app_window_layout(self, client, *args, **kwargs):
		layout = self.db.get_setting(ptvDB.STRING, '/apps/penguintv/app_window_layout', 'standard')
		self.set_app_window_layout(layout)
		
	def set_app_window_layout(self, layout):
		self.main_window.layout=layout
		
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
		if sensitize:
			self.main_window._sensitize_search()
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
		
	def get_database_name(self):
		return os.path.join(utils.get_home(), "penguintv4.db")
		
	def toggle_net_connection(self):
		self.emit('online-status-changed', not self._net_connected)
		
	def _nm_device_now_active(self, *args):
		if self._nm_interface is not None:
			state = self._nm_interface.state()
			if state == 3 and not self._net_connected:
				self.emit('online-status-changed', True)
			elif state != 3 and self._net_connected:
				self.emit('online-status-changed', False)
	
	def _nm_device_no_longer_active(self, *args):
		if self._nm_interface is not None:
			state = self._nm_interface.state()
			if state == 3 and not self._net_connected:
				self.emit('online-status-changed', True)
			elif state != 3 and self._net_connected:
				self.emit('online-status-changed', False)
			
	def _progress_callback(self,d):
		"""Callback for downloads.  Not in main thread, so shouldn't generate gtk calls"""
		if self._exiting == 1:
			self._gui_updater.queue(self.do_cancel_download,d.media, None, True, 1)
			return 1 #returning one is what interrupts the download
		
		if d.media.has_key('size_adjustment'):
			if d.media['size_adjustment']==True:
				self._db_updater.queue(self._updater_thread_db.set_media_size,(d.media['media_id'], d.media['size']))
		if self.main_window.changing_layout == False:
			self._gui_updater.queue(self._entry_view.update_if_selected,d.media['entry_id'])
			self._gui_updater.queue(self.main_window.update_download_progress)

	def _finished_callback(self,downloader):
		self._gui_updater.queue(self._download_finished, downloader)
		
	def _polling_callback(self, args, cancelled=False):
		if not self._exiting:
			feed_id, update_data, total = args
			if len(update_data)>0:
				if update_data.has_key('ioerror'):
					logging.warning("ioerror polling reset")
					self._updater_thread_db.interrupt_poll_multiple()
					self._polled = 0
					self._polling_taskinfo = -1
					self.main_window.update_progress_bar(-1, MainWindow.U_POLL)
					self.main_window.display_status_message(_("Trouble connecting to the internet"),MainWindow.U_POLL)
					gobject.timeout_add(2000, self.main_window.display_status_message,"")
					return
				else:
					update_data['polling_multiple'] = True
					self._threaded_emit('feed-polled', feed_id, update_data)
			elif not cancelled:
				#check image just in case
				self._gui_updater.queue(self.feed_list_view.update_feed_list, (feed_id,['image']))
			self._gui_updater.queue(self._poll_update_progress, (total, cancelled))
		
	def _poll_update_progress(self, total=0, cancelled=False):
		"""Updates progress for do_poll_multiple, and also displays the "done" message"""

		self._polled += 1
		if self._polled == total or cancelled:
			self._polled = 0
			self._polling_taskinfo = -1
			self.main_window.update_progress_bar(-1,MainWindow.U_POLL)
			self.main_window.display_status_message(_("Feeds Updated"),MainWindow.U_POLL)
			gobject.timeout_add(2000, self.main_window.display_status_message,"")
		else:
			d = { 'polled':self._polled,
				  'total':total}
			self.main_window.update_progress_bar(float(self._polled)/float(total),MainWindow.U_POLL)
			self.main_window.display_status_message(_("Polling Feeds... (%(polled)d/%(total)d)" % d),MainWindow.U_POLL)
			
	def _entry_image_download_callback(self, entry_id, html):
		self._gui_updater.queue(self._entry_view._images_loaded,(entry_id, html))
		
	def _reset_db_updater(self, db):
		self._updater_thread_db = db
		
	def _emit_change_setting(self, typ, datum, value):
		self.emit('setting-changed', typ, datum, value)
		
	def _threaded_emit(self, signal, *args):
		def do_emit(signal, *args):
			gtk.gdk.threads_enter()
			self.emit(signal, *args)
			gtk.gdk.threads_leave()
			return False
		gobject.idle_add(do_emit, signal, *args, **{"priority" : gobject.PRIORITY_HIGH})
				
	class DBUpdaterThread(threadclass):
		def __init__(self, polling_callback, reset_callback):
			PenguinTVApp.threadclass.__init__(self)
			self.__isDying = False
			self.db = None
			self.updater = UpdateTasksManager.UpdateTasksManager(UpdateTasksManager.MANUAL, "db updater")
			self.threadSleepTime = 0.5
			self.polling_callback = polling_callback
			self.reset_callback = reset_callback
			
		def run(self):
	
			""" Until told to quit, retrieve the next task and execute
				it, calling the callback if any.  """
				
			if self.db == None:
				self.db = ptvDB.ptvDB(self.polling_callback)
						
			while self.__isDying == False:
				while self.updater.updater_gen().next():
					if self.updater.exception is not None:
						if isinstance(self.updater.exception, OperationalError):
							logging.warning("detected a database lock error, restarting threaded db")
							self.db._db.close()
							self.db = ptvDB.ptvDB(self.polling_callback)
							self.reset_callback(self.db)
				time.sleep(self.threadSleepTime)
						
		def get_db(self):
			return self.db
			
		def get_updater(self):
			return self.updater
	
		def goAway(self):
	
			""" Exit the run loop next time through."""
	        
			self.__isDying = True
	
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
	print "   [filename]        (alternate) Import an RSS url"
	print "   -h | --help       This explanation"
		
def do_commandline(remote_app=None, local_app=None):
	assert remote_app is not None or local_app is not None

	try:
		opts, args = getopt.getopt(sys.argv[1:], "ho:u:", ["help"])
	except getopt.GetoptError:
        # print help information and exit:
		usage()
		sys.exit(2)
		
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
				local_app.add_feed(a, a)
				
	if len(opts) == 0 and len(sys.argv) > 1:
		if local_app is None:
			remote_app.AddFeed(a)
		else:
			local_app.add_feed(a, a)

def main():
	gtk.gdk.threads_init()
	if HAS_GNOME:
		gnome.init("PenguinTV", utils.VERSION)
	try:
		app = PenguinTVApp()    # Instancing of the GUI
	except AlreadyRunning, e:
		do_commandline(remote_app=e.remote_app)
		sys.exit(0)
	app.main_window.Show() 
	if utils.is_kde():
		try:
			from kdecore import KApplication, KCmdLineArgs, KAboutData
			from kdeui import KMainWindow
			import kio

			description = "test kde"
			version     = "1.0"
			aboutData   = KAboutData ("", "",\
			    version, description, KAboutData.License_GPL,\
			    "(C) 2006 Owen Williams")
			KCmdLineArgs.init (sys.argv, aboutData)
			app = KApplication ()
			
		except:
			logging.error("Unable to initialize KDE")
			sys.exit(1)	
	do_commandline(local_app=app)
	gtk.main() 

def do_quit(self, event, app):
	app.do_quit()
        
if __name__ == '__main__': # Here starts the dynamic part of the program 
	if HAS_GNOME:
		gtk.gdk.threads_init()
		gnome.init("PenguinTV", utils.VERSION)
		try:
			app = PenguinTVApp()    # Instancing of the GUI
		except AlreadyRunning, e:
			do_commandline(remote_app=e.remote_app)
			sys.exit(0)
		
		app.main_window.Show()
		
		##PROFILE
		#import cProfile
		#cProfile.run('gtk.main()', '/tmp/penguintv-prof')
		#sys.exit(0)

		if utils.is_kde():
			try:
				from kdecore import KApplication, KCmdLineArgs, KAboutData
				from kdeui import KMainWindow
				import kio

				description = "test kde"
				version     = "1.0"
				aboutData   = KAboutData ("", "",\
				    version, description, KAboutData.License_GPL,\
				    "(C) 2006 Owen Williams")
				KCmdLineArgs.init (sys.argv, aboutData)
				app = KApplication ()
				
			except:
				logging.error("Unable to initialize KDE")
				sys.exit(1)
	else: #no gnome, no gnomeapp
		window = gtk.Window()
		gtk.gdk.threads_init()
		app = PenguinTVApp()
		app.main_window.Show(window)
		window.connect('delete-event', do_quit, app)
	do_commandline(local_app=app)
	gtk.main()

