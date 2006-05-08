#!/usr/bin/env python
# Written by Owen Williams
# using pieces from Straw
# see LICENSE for license information

import urlparse
import threading
from threading import RLock
import sys,os, os.path
import traceback
import urllib
import time
import random
import sets
import string

import gtk
import gnome.ui
import gtk.glade
import gobject
import pango
import pycurl
import locale
import gettext
import gconf

locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

#DEBUG (see also utils.py for some debugs)
_SKIP_FIRST_POLL=True

import ptvDB
import MediaManager
import Player
import UpdateTasksManager
import utils

import AddFeedDialog
import PreferencesDialog
import RenameFeedDialog
import EditTextTagsDialog
import EditTagsMultiDialog
import FeedList, EntryList, EntryView

CANCEL=0
PAUSE=1

GUI = UpdateTasksManager.GUI
DB = UpdateTasksManager.DB

REFRESH_SPECIFIED=0
REFRESH_AUTO=1

AUTO_REFRESH_FREQUENCY=5*60*1000

superglobal=utils.SuperGlobal()
superglobal.download_status={}

DOWNLOAD_ERROR=0
DOWNLOAD_PROGRESS=1
DOWNLOAD_WARNING=2

class PenguinTVApp:
	COLUMN_TITLE = 0
	COLUMN_ITEM = 1
	COLUMN_BOLD = 2
	COLUMN_STICKY_FLAG = 3

	def __init__(self):
		try:
			self.glade_prefix = utils.GetPrefix()+"/share/penguintv"
			os.stat(self.glade_prefix+"/penguintv.glade")
		except:
			try:
				self.glade_prefix = utils.GetPrefix()+"/share"
				os.stat(self.glade_prefix+"/penguintv.glade")
			except:
				try:
					self.glade_prefix = os.path.split(os.path.abspath(sys.argv[0]))[0]+"/share"
					os.stat(self.glade_prefix+"/penguintv.glade")
				except:
					print "error finding glade file."
					sys.exit()
		self.widgetTree   = None
		self.db = ptvDB.ptvDB(self._polling_callback)
		self.firstrun = self.db.maybe_initialize_db()
		self.mediamanager = MediaManager.MediaManager(self._progress_callback, self._finished_callback)
		self.conf = gconf.client_get_default()
		self.player = Player.Player()
	 	self._status_messages = []
		self._updater_db = None
		self.download_task_ops=[]
		self.db.clean_media_status()
		self.poll_tasks=0
		self.polling_frequency=12*60*60*1000
		self.bt_settings = {}
		self.exiting=0
		self.window_maximized = False
		self.auto_download = False
		self.auto_download_limiter = False
		self.auto_download_limit=1024*1024
		self.changing_layout=False
		self.pausing_all_downloads = False
		
		self.updater = UpdateTasksManager.UpdateTasksManager()
		self._db_updater = self.DBUpdaterThread(self.updater, self._polling_callback)
		self._db_updater.start()
		self.updater_thread_db = None
		while self.updater_thread_db==None:
			#this may race, so be patient 
			self.updater_thread_db = self._db_updater.get_db()
			time.sleep(.1)
			
		self.app_window_layout = self.conf.get_string('/apps/penguintv/app_window_layout')
		if self.app_window_layout is None:
			self.app_window_layout='standard'
			
	def post_show_init(self):
		#windows
		self.window_add_feed = AddFeedDialog.AddFeedDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_add_feed",'penguintv'),self) #MAGIC
		self.window_add_feed.hide()
		self.window_preferences = PreferencesDialog.PreferencesDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_preferences",'penguintv'),self) #MAGIC
		self.window_preferences.hide()
		self.window_rename_feed = RenameFeedDialog.RenameFeedDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_rename_feed",'penguintv'),self) #MAGIC
		self.window_rename_feed.hide()
		#self.layout_changing_dialog = LayoutChangingDialog.LayoutChangingDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_changing_layout",'penguintv'))
		self.layout_changing_dialog = gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_changing_layout",'penguintv').get_widget("window_changing_layout")
		self.layout_changing_dialog.connect("delete-event",self.on_window_changing_layout_delete_event)
		self.layout_changing_dialog.hide()
		self.about_box_widgets = gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "aboutdialog1",'penguintv')
		self.about_box = self.about_box_widgets.get_widget('aboutdialog1')
		try:
			self.about_box.set_version(utils.VERSION)
		except:
			pass #fc3 workaround (doesn't have aboutbox class)
		self.about_box.hide()
		self.window_edit_tags_single = EditTextTagsDialog.EditTextTagsDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_edit_tags_single",'penguintv'),self)
		
		#gconf
		self.conf.add_dir('/apps/penguintv',gconf.CLIENT_PRELOAD_NONE)
		self.conf.notify_add('/apps/penguintv/auto_resume',self.set_auto_resume)
		self.conf.notify_add('/apps/penguintv/bt_max_port',self.set_bt_maxport)
		self.conf.notify_add('/apps/penguintv/bt_min_port',self.set_bt_minport)
		self.conf.notify_add('/apps/penguintv/ul_limit',self.set_bt_ullimit)
		self.conf.notify_add('/apps/penguintv/feed_refresh_frequency',self.set_polling_frequency)
		self.conf.notify_add('/apps/penguintv/app_window_layout',self.set_app_window_layout)
		self.conf.notify_add('/apps/penguintv/feed_refresh_method',self.set_feed_refresh_method)
		self.conf.notify_add('/apps/penguintv/auto_download',self.set_auto_download)
		self.conf.notify_add('/apps/penguintv/auto_download_limiter',self.set_auto_download_limiter)
		self.conf.notify_add('/apps/penguintv/auto_download_limit',self.set_auto_download_limit)
		self.load_settings()
		
		#updaters
		gobject.timeout_add(500, self._gui_updater)
		if self.autoresume:
			self.resume_resumable()
		else:
			self.feed_list_view.populate_feeds()
		self.update_disk_usage()
		
		if self.firstrun:
			try:
				glade_prefix = utils.GetPrefix()+"/share/penguintv"
				os.stat(glade_prefix+"/defaultsubs.opml")
			except:
				try:				
					glade_prefix = utils.GetPrefix()+"/share"
					os.stat(glade_prefix+"/defaultsubs.opml")
				except:
					print "ptvdb: error finding default subscription file."
					sys.exit()
			f = open(glade_prefix+"/defaultsubs.opml", "r")
			self.display_status_message(_("Polling feeds for the first time..."))
			task_id = self.updater.queue_task(DB, self.updater_thread_db.import_OPML,f)
			self.updater.queue_task(GUI, self.feed_list_view.populate_feeds,None, task_id)
			self.do_poll_multiple()
			
	def set_wait_cursor(self, wait=True):
		if wait:
			c = gtk.gdk.Cursor(gtk.gdk.WATCH)
			self.app_window.window.set_cursor(c)
		else:
			self.app_window.window.set_cursor(None)
		
	def Show(self):
		self.widgetTree = gtk.glade.XML(self.glade_prefix+'/penguintv.glade', self.app_window_layout+'app','penguintv') #MAGIC
		self.feed_list_view = FeedList.FeedList(self.widgetTree,self, self.db)
		self.entry_list_view = EntryList.EntryList(self.widgetTree,self, self.db)
		renderrer_str = self.conf.get_string('/apps/penguintv/renderrer')
		renderrer = EntryView.GTKHTML
		
		if renderrer_str == "GTKHTML":
			renderrer = EntryView.GTKHTML
		elif renderrer_str == "DEMOCRACY_MOZ":
			renderrer = EntryView.DEMOCRACY_MOZ
		
		def load_renderrer(x):
			try:
				self.entry_view = EntryView.EntryView(self.widgetTree, self, x)
			except:
				if renderrer == EntryView.DEMOCRACY_MOZ:
					print "Error instantiating Democracy Mozilla renderrer, falling back to GTKHTML"
					print "(if running from source dir, build setup.py and copy MozillaBrowser.so to democracy_moz/)"
					load_renderrer(EntryView.GTKHTML)
				else:
					print "Error loading renderrer"
					sys.exit(2)
		
		load_renderrer(renderrer)
					
		for key in dir(self.__class__): #python insaneness
			if key[:3] == 'on_':
				self.widgetTree.signal_connect(key, getattr(self, key))
				
		#some widgets
		self.feed_pane = self.widgetTree.get_widget('feed_pane')
		self.feedlist = self.widgetTree.get_widget('feedlistview')
		self.entry_pane = self.widgetTree.get_widget('entry_pane')
		self.app_window = self.widgetTree.get_widget(self.app_window_layout+'app')
		try:
			self.app_window.set_icon_from_file(utils.GetPrefix()+"/share/pixmaps/penguintvicon.png")
		except:
			try:
				self.app_window.set_icon_from_file(utils.GetPrefix()+"/share/penguintvicon.png") #in case the install is still in the source dirs
			except:
				self.app_window.set_icon_from_file(self.glade_prefix+"/penguintvicon.png")
		self._status_view = self.widgetTree.get_widget("appbar")
		self.disk_usage_widget = self.widgetTree.get_widget('disk_usage')
		
		self.filter_combo_widget = self.widgetTree.get_widget('filter_combo')
		filter_combo_model = gtk.ListStore(str,str,bool) #text to display, name of filter, separator-or-not
		self.filter_combo_widget.set_model(filter_combo_model)		
		self.filter_combo_widget.set_row_separator_func(lambda model,iter: model[model.get_path(iter)[0]][2])
		
		self.filter_combo_widget.clear()
		renderer = gtk.CellRendererText()
		self.filter_combo_widget.pack_start(renderer, False)
		self.filter_combo_widget.set_attributes(renderer, text=0)
		
		renderer = gtk.CellRendererText()
		self.filter_combo_widget.pack_start(renderer, False)
		self.filter_combo_widget.set_attributes(renderer, text=1)
		
		self.filter_unread_checkbox = self.widgetTree.get_widget('unread_filter')
		
		filter_combo_model.append([FeedList.BUILTIN_TAGS[0],"("+str(len(self.db.get_feedlist()))+")",False])
		for builtin in FeedList.BUILTIN_TAGS[1:]:
			filter_combo_model.append([builtin,"",False])
		filter_combo_model.append(["---","---",True])
		self.update_filters()
			
		#set up separator between toolbar buttons and free space indicator
		vseparator = self.widgetTree.get_widget('vseparator1')
		vseparator_toolitem = self.widgetTree.get_widget('toolitem1')
		vseparator_toolitem.set_expand(True)
		vseparator.set_draw(False)
			
		
		#dnd
		self.TARGET_TYPE_TEXT = 80
		self.TARGET_TYPE_URL = 81
		drop_types = [ ('text/x-moz-url',0,self.TARGET_TYPE_URL),
									 ('text/unicode',0,self.TARGET_TYPE_TEXT),
									 ('text/plain',0,self.TARGET_TYPE_TEXT)]
		self.feedlist.drag_dest_set(gtk.DEST_DEFAULT_ALL, drop_types, gtk.gdk.ACTION_COPY)
		
		#final setup for the window
		x = self.conf.get_int('/apps/penguintv/app_window_position_x')
		y = self.conf.get_int('/apps/penguintv/app_window_position_y')
		if x is None:
			x=40
		if y is None:
			y=40
		self.app_window.move(x,y)
		w = self.conf.get_int('/apps/penguintv/app_window_size_x')
		h = self.conf.get_int('/apps/penguintv/app_window_size_y')
		if w<0 or h<0:  #very cheesy.  negative values really means "maximize"
			self.app_window.resize(abs(w),abs(h)) #but be good and don't make assumptions about negativity
			self.app_window.maximize()
			self.window_maximized = True
		else:
			self.app_window.resize(w,h)
		val = self.conf.get_int('/apps/penguintv/feed_pane_position')
		if val is None:
			val=132
		if val < 10:
			val=50
		self.feed_pane.set_position(val)
		val = self.conf.get_int('/apps/penguintv/entry_pane_position')
		if val is None:
			val=309
		if val < 10:
			val = 50
		self.app_window.show()
		self.entry_pane.set_position(val)
		
		val = self.conf.get_string('/apps/penguintv/default_filter')
		if val is not None:
			try:
				self.feed_list_view.set_filter([row[0] for row in filter_combo_model].index(val),val)
				self.filter_combo_widget.set_active([row[0] for row in filter_combo_model].index(val))
			except ValueError: #didn't find the item in the model (.index(val) fails)
				self.filter_combo_widget.set_active(FeedList.ALL)
		else:
			self.filter_combo_widget.set_active(FeedList.ALL)
		
		
	def Hide(self):
		self.app_window.hide()
		del self.widgetTree
		del self.feed_list_view
		del self.entry_list_view
		del self.entry_view
				
		#some widgets
		del self.feed_pane
		del self.feedlist
		del self.entry_pane
		del self.app_window
		del self._status_view
		del self.disk_usage_widget
		del self.filter_combo_widget
		
	def load_settings(self):
		val = self.conf.get_int('/apps/penguintv/feed_refresh_frequency')
		if val is None:
			val=60
		self.polling_frequency = val*60*1000
		self.window_preferences.set_feed_refresh_frequency(self.polling_frequency/(60*1000))
			
		val = self.conf.get_string('/apps/penguintv/feed_refresh_method')
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
		#also poll in 30 seconds (ie, "poll on startup")
		if _SKIP_FIRST_POLL==False:
			gobject.timeout_add(30*1000,self.do_poll_multiple, 0)
			
		val = self.conf.get_int('/apps/penguintv/bt_min_port')
		if val is None:
			val=6881
		self.bt_settings['min_port']=val
		val = self.conf.get_int('/apps/penguintv/bt_max_port')
		if val is None:
			val=6999
		self.bt_settings['max_port']=val
		val = self.conf.get_int('/apps/penguintv/bt_ul_limit')
		if val is None:
			val=0
		self.bt_settings['ul_limit']=val
		self.window_preferences.set_bt_settings(self.bt_settings)
		self.mediamanager.set_bt_settings(self.bt_settings)
		
		val = self.conf.get_bool('/apps/penguintv/auto_resume')
		if val is None:
			val=True
		self.autoresume = val
		self.window_preferences.set_auto_resume(val)
		
		val = self.conf.get_bool('/apps/penguintv/auto_download')
		if val is None:
			val=False
		self.auto_download = val
		self.window_preferences.set_auto_download(val)
		
		val = self.conf.get_bool('/apps/penguintv/auto_download_limiter')
		if val is None:
			val=False
		self.auto_download_limiter = val
		self.window_preferences.set_auto_download_limiter(val)
		
		val = self.conf.get_int('/apps/penguintv/auto_download_limit')
		if val is None:
			val=1024*1024
		self.auto_download_limit = val
		self.window_preferences.set_auto_download_limit(val)
			
	def save_settings(self):
		self.conf.set_int('/apps/penguintv/feed_pane_position',self.feed_pane.get_position())
		self.conf.set_int('/apps/penguintv/entry_pane_position',self.entry_pane.get_position())
		x,y=self.app_window.get_position()
		self.conf.set_int('/apps/penguintv/app_window_position_x',x)
		self.conf.set_int('/apps/penguintv/app_window_position_y',y)
		if self.window_maximized == False:
			x,y=self.app_window.get_size()
		else:
			x,y=self.app_window.get_size()
			x,y=(-x,-y)
		self.conf.set_int('/apps/penguintv/app_window_size_x',x)
		self.conf.set_int('/apps/penguintv/app_window_size_y',y)
		
		self.conf.set_string('/apps/penguintv/app_window_layout',self.app_window_layout)
		if self.feed_refresh_method==REFRESH_AUTO:
			self.conf.set_string('/apps/penguintv/feed_refresh_method','auto')
		else:
			self.conf.set_int('/apps/penguintv/feed_refresh_frequency',self.polling_frequency/(60*1000))
			self.conf.set_string('/apps/penguintv/feed_refresh_method','specified')	
		self.conf.set_int('/apps/penguintv/bt_max_port',self.bt_settings['max_port'])
		self.conf.set_int('/apps/penguintv/bt_min_port',self.bt_settings['min_port'])
		self.conf.set_int('/apps/penguintv/bt_ul_limit',self.bt_settings['ul_limit'])
		self.conf.set_bool('/apps/penguintv/auto_resume',self.autoresume)
		self.conf.set_bool('/apps/penguintv/auto_download',self.auto_download)
		self.conf.set_bool('/apps/penguintv/auto_download_limiter',self.auto_download_limiter)
		self.conf.set_int('/apps/penguintv/auto_download_limit',self.auto_download_limit)
		if self.feed_list_view.filter_setting > FeedList.NONE:
			self.conf.set_string('/apps/penguintv/default_filter',self.feed_list_view.filter_name)
		else:
			self.conf.set_string('/apps/penguintv/default_filter',"")
	
	def resume_resumable(self):
		feeds = self.db.get_feedlist()
		for feed in feeds:
			entrylist = self.db.get_entrylist(feed[0])
			found=0
			for entry in entrylist:
				media = self.db.get_entry_media(entry[0])
				try:
					for medium in media:
						if medium['download_status']==ptvDB.D_RESUMABLE: 
							print "resuming "+str(medium['file'])
							self.mediamanager.download(medium['media_id'], False, True) #resume please
							self.db.set_entry_read(medium['entry_id'],False)
				except:
					pass
		self.feed_list_view.populate_feeds()
		
	def do_quit(self):
		#save and shut down all our threads
		self.exiting=1
		self.save_settings()
		self.mediamanager.finish()
		self.db.finish()
		self._db_updater.goAway()
		gtk.main_quit()
		
	def do_poll_multiple(self, was_setup=None, arguments=0):
		#"was_setup":  So do_poll_multiple is going to get called by timers and manually, and we needed some
		#way of saying "I've got a new frequency, stop the old timer and start the new one."  so it checks to
		#see that the frequency it 'was setup' with is the same as the current frequency.  If not, exit with
		#False to stop the timer.

		if was_setup is not None:
			if self.feed_refresh_method==REFRESH_AUTO:
				if was_setup==0: #initial poll
					arguments = arguments | ptvDB.A_ALL_FEEDS
				arguments = arguments | ptvDB.A_AUTOTUNE 
			else:
				if was_setup!=self.polling_frequency and was_setup!=0:
					return False
				
		self.poll_tasks = len(self.db.get_feedlist())
		self.display_status_message("Polling Feeds...")
		task_id = self.updater.queue_task(DB, self.updater_thread_db.poll_multiple, arguments)
		self.updater.queue_task(GUI, self.display_status_message, _("Feeds Updated"), task_id, False) #waitfor, and don't clear the flag
		self.updater.queue_task(GUI, self.update_disk_usage, None, task_id, False) #because this is also waiting
		if self.auto_download == True:
			#self.updater.queue_task(GUI, self.feed_list_view.populate_feeds, None, task_id,False)
			self.updater.queue_task(GUI, self.auto_download_unviewed, None, task_id)
		#else:
		#	self.updater.queue_task(GUI, self.feed_list_view.populate_feeds, None, task_id) 
		if was_setup!=0:
			return True
		return False
	
	def __getitem__(self, key):
		return self.widgets.get_widget(key)
		
	def auto_download_unviewed(self):
		"""Automatically download any unviewed media.  Runs every five minutes when auto-polling, so make sure is good"""
		download_list=self.db.get_media_for_download()
		if len(download_list)==0:
			return #no need to bother
		total_size=0
		disk_usage = self.mediamanager.get_disk_usage()
		download_list.sort(lambda x,y: int(y[1]-x[1]))

		at_least_one=False
		for d in download_list:                #skip anything that puts us over the limit
			if self.auto_download_limiter and disk_usage + total_size+int(d[1]) > self.auto_download_limit*1024: 
				continue
			total_size=total_size+int(d[1])
			self.mediamanager.download(d[0])
			at_least_one=True #let's see if len(download_list) still > 0 after checking space limits 
		if at_least_one: # No sense populating feeds if we didn't do anything!
			self.feed_list_view.populate_feeds()
			
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
		self.update_filters()
		
	def update_filters(self):
		"""update the filter combo box with the current list of filters"""
		#get name of current filter, if a tag
		model = self.filter_combo_widget.get_model()
		current_filter = model[self.filter_combo_widget.get_active()][0]
		#if current_filter not in BUILTIN_TAGS:	
		#	if current_filter not in self.db.get_all_tags():
		#		current_filter = ALL  #in case the current filter is an out of date tag
		model.clear()

		model.append([FeedList.BUILTIN_TAGS[0],"("+str(len(self.db.get_feedlist()))+")",False])
		for builtin in FeedList.BUILTIN_TAGS[1:]:
			model.append([builtin,"",False])
		model.append(["---","---",True])
		tags = self.db.get_all_tags()	
		if tags:
			for tag in tags:
				model.append([tag,"("+str(self.db.get_count_for_tag(tag))+")",False])
			
		#get index for our previously selected tag
		i = 0
		found = 0
		for tag in model:
			if tag[0]==current_filter:
				found=1
				break
			i=i+1
		if found:
			self.filter_combo_widget.set_active(i)
			self.feed_list_view.set_filter(i,current_filter)
		else:
			self.filter_combo_widget.set_active(FeedList.ALL)
			self.feed_list_view.set_filter(FeedList.ALL,current_filter)
			
	def display_feed(self, feed_id, selected_entry=-1):
		self.entry_list_view.populate_entries(feed_id,selected_entry)
		
	def display_entry(self, entry_id, set_read=1):
		if entry_id is not None:
			item = self.db.get_entry(entry_id)
			media = self.db.get_entry_media(entry_id)
			read = self.db.get_entry_read(entry_id)
		else:
			self.entry_view.display_item()
			return
			
		if media:
			item['media']=media
		else:
			if read==0 and set_read==1:
				self.db.set_entry_read(entry_id,1)
				self.entry_list_view.update_entry_list(entry_id)
				self.feed_list_view.update_feed_list(item['feed_id'])
		self.entry_view.display_item(item)
	
	def display_custom_entry(self, message):
		self.entry_view.display_custom_entry(message)
		
	def undisplay_custom_entry(self):
		self.entry_view.undisplay_custom_entry()
	
	def activate_link(self, link):
		parsed_url = urlparse.urlparse(link)
		action=parsed_url[0]
		http_arguments=parsed_url[4]
		anchor = parsed_url[5]
		try:
			item=int(parsed_url[2])
		except:
			pass
		if action == "download":
			self.mediamanager.download(item)
			media = self.db.get_media(item)
			#self.db.set_media_viewed(item,False)
			self.update_feed_list()
			self.update_entry_list()
		elif action=="resume" or action=="tryresume":
			self.mediamanager.download(item, False, True) #resume please
			media = self.db.get_media(item)
			self.db.set_media_viewed(item,False)
			self.update_feed_list()
			self.update_entry_list()
		elif action=="play":
			media = self.db.get_media(item)
			self.db.set_entry_read(media['entry_id'],True)
			self.db.set_media_viewed(item,True)
			if utils.is_known_media(media['file']):
				self.player.play(media['file'])
			else:
				gnome.url_show(media['file'])
			self.update_feed_list()
			self.update_entry_list()
		elif action=="downloadqueue":
			self.mediamanager.download(item, True)
			self.update_feed_list()
			self.update_entry_list()
		elif action=="queue":
			print parsed_url		
		elif action=="stop":
			self.download_task_ops.append((CANCEL,item))
		elif action=="pause":
			self.download_task_ops.append((PAUSE, item))
		elif action=="clear" or action=="cancel":
			newitem={}
			newitem['media_id']=item
			newitem['entry_id']=self.db.get_entryid_for_media(newitem['media_id'])
			self.do_cancel_download(newitem)
			self.update_feed_list()
			self.update_entry_list()
		elif action=="delete":
			self.delete_media(item)
			self.update_feed_list()
			self.update_entry_list()
		elif action=="reveal":
			if utils.is_kde():
				reveal_url = "file:" + urllib.quote(parsed_url[1]+parsed_url[2])
				os.system('konqueror --select ' + reveal_url + ' &')
			else:
				reveal_url = "file:"+os.path.split(urllib.quote(parsed_url[1]+parsed_url[2]))[0]
				gnome.url_show(reveal_url)
			#gnome.url_show("file:"+os.path.split(urllib.quote(parsed_url[1]+parsed_url[2]))[0])
	#except:
	#		pass
		elif action=="http":
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
			gnome.url_show(parsed_url[0]+"://"+quoted_url+http_arguments+anchor)
		elif action=="file":
			print parsed_url[0]+"://"+urllib.quote(parsed_url[1]+parsed_url[2])
			gnome.url_show(parsed_url[0]+"://"+urllib.quote(parsed_url[1]+parsed_url[2]))
			#self.db.set_media_viewed(item,False)
			self.update_feed_list()
			self.update_entry_list()
			
	def set_bt_maxport(self, client, *args, **kwargs):
		maxport = client.get_int('/apps/penguintv/bt_max_port')
		self.bt_settings['max_port']=maxport
		self.window_preferences.set_bt_settings(self.bt_settings)
		
	def set_bt_minport(self, client, *args, **kwargs):
		minport = client.get_int('/apps/penguintv/bt_min_port')
		self.bt_settings['min_port']=minport
		self.window_preferences.set_bt_settings(self.bt_settings)
		
	def set_bt_ullimit(self, client, *args, **kwargs):
		ullimit = client.get_int('/apps/penguintv/bt_ul_limit')
		self.bt_settings['ul_limit']=ullimit
		self.window_preferences.set_bt_settings(self.bt_settings)
			
	def set_polling_frequency(self, client, *args, **kwargs):
		freq = client.get_int('/apps/penguintv/feed_refresh_frequency')
		if self.polling_frequency != freq*60*1000:
			self.polling_frequency = freq*60*1000	
			gobject.timeout_add(self.polling_frequency,self.do_poll_multiple, self.polling_frequency)
			self.window_preferences.set_feed_refresh_frequency(freq)
	
	def get_app_window_layout(self):
		return self.app_window_layout
		
	def get_feed_refresh_method(self):
		return self.feed_refresh_method
	
	def set_app_window_layout(self, client, *args, **kwargs):
		layout = self.conf.get_string('/apps/penguintv/app_window_layout')
		self.app_window_layout = layout
		
	def set_feed_refresh_method(self, client, *args, **kwargs):
		refresh = self.conf.get_string('/apps/penguintv/feed_refresh_method')
		if refresh == 'auto':
			self.feed_refresh_method=REFRESH_AUTO
			self.polling_frequency = AUTO_REFRESH_FREQUENCY	
			gobject.timeout_add(self.polling_frequency,self.do_poll_multiple, self.polling_frequency)
		else:
			self.feed_refresh_method=REFRESH_SPECIFIED
			self.set_polling_frequency(client,None,None)
			
	def add_feed(self, url):
		self.display_status_message(_("Trying to poll feed..."))
		feed_id = self.db.insertURL(url)
		self.window_add_feed.hide()
		taskid = self.updater.queue_task(GUI, self.populate_and_select, feed_id)
		self.updater.queue_task(DB, self.updater_thread_db.poll_feed_trap_errors, (feed_id,self._add_feed_callback), taskid)
		return feed_id
		
	def _add_feed_callback(self, feed, success):
		if success:
			self.updater.queue_task(GUI, self.add_feed_success, feed['feed_id'])
			self.updater.queue_task(GUI, self.first_poll_marking, feed['feed_id'])
			self.updater.queue_task(GUI, self.entry_list_view.populate_entries, feed['feed_id'])
			self.updater.queue_task(GUI, self.update_feed_list, feed['feed_id'])
			if self.auto_download:
				self.updater.queue_task(GUI, self.auto_download_unviewed)
		else:
			self.updater.queue_task(GUI, self.add_feed_error, feed['feed_id'])
	
	def first_poll_marking(self, feed_id): 
		"""mark all media read except first one.  called when we first add a feed"""
		all_feeds_list = self.db.get_media_for_download()
		this_feed_list = []
		for item in all_feeds_list:
			if item[3]==feed_id:
				this_feed_list.append(item)
		for item in this_feed_list[1:]:
			self.db.set_entry_read(item[2],1)
		
	def add_feed_error(self,feed_id):
		self.display_status_message(_("Error adding feed"))
		#self.db.set_feed_name(feed['feed_id'],feed['url'])
		self.populate_and_select(feed_id)
		return
		
	def add_feed_success(self, feed_id):
		self.display_status_message(_("Feed Added"))
		#self.feed_list_view.update_feed_list(feed['feed_id'])
		self.populate_and_select(feed_id)
					
			
	def delete_entry_media(self, entry_id):
		medialist = self.db.get_entry_media(entry_id)
		if medialist:
			for medium in medialist:
				if medium['download_status']==ptvDB.D_DOWNLOADED or medium['download_status']==ptvDB.D_RESUMABLE:
					#self.updater.queue_task(DB, self.updater_thread_db.set_media_viewed, medium['media_id'])
					self.delete_media(medium['media_id'])
		
	def delete_media(self, media_id):
		self.db.delete_media(media_id)
		self.mediamanager.generate_playlist()
		self.db.set_media_viewed(media_id,True)
		self.update_disk_usage()
		
	def delete_feed_media(self, feed_id):
		entrylist = self.db.get_entrylist(feed_id)
		if entrylist:
			for entry in entrylist:
				self.delete_entry_media(entry[0])
				self.mediamanager.generate_playlist()
				self.update_disk_usage()
				self.update_entry_list(entry[0])
		self.update_feed_list(feed_id)
		
	def do_cancel_download(self, data):
		print "cancelling download"
		self.db.set_media_download_status(data['media_id'],ptvDB.D_NOT_DOWNLOADED)
		self.delete_media(data['media_id'])
		
	def do_pause_download(self, data):
		self.db.set_media_download_status(data['media_id'],ptvDB.D_RESUMABLE)
		self.db.set_media_viewed(data['media_id'],0)
		self.db.set_entry_read(data['entry_id'],0)
		
	def download_finished(self, media, status, message):
		#global download_status
		self.update_disk_usage()
		if status==MediaManager.FAILURE: 
			self.db.set_media_download_status(media['media_id'],ptvDB.D_ERROR) 
			superglobal.download_status[media['media_id']]=(DOWNLOAD_ERROR,media['errormsg'])
		elif status==MediaManager.STOPPED:
			pass #no need to do anything
		elif status==MediaManager.FINISHED or status==MediaManager.FINISHED_AND_PLAY:
			if os.stat(media['file'])[6] < int(media['size']/2) and os.path.isfile(media['file']): #don't check dirs
				d = {'reported_size': str(media['size']),
					 'actual_size': str(os.stat(media['file'])[6])}
				superglobal.download_status[media['media_id']]=(DOWNLOAD_WARNING,_("WARNING: Expected %(reported_size)s bytes but the file is %(actual_size)s bytes.") % d)
				#self.delete_media(media['media_id'])
				self.db.set_entry_read(media['entry_id'],False)
				self.db.set_media_viewed(media['media_id'],False)
				self.db.set_media_download_status(media['media_id'],ptvDB.D_DOWNLOADED)
			else:
				try:
					del superglobal.download_status[media['media_id']] #clear progress information
				except:
					pass #no big whoop if it fails
				if status==MediaManager.FINISHED_AND_PLAY:
					self.db.set_media_viewed(media['media_id'],True)
					self.db.set_entry_read(media['entry_id'],True)
					self.player.play(media['file'])
				else:
					self.db.set_entry_read(media['entry_id'],False)
					self.db.set_media_viewed(media['media_id'],False)
				self.db.set_media_download_status(media['media_id'],ptvDB.D_DOWNLOADED)		
		try:
			feed_id = self.db.get_entry(media['entry_id'])['feed_id']
			self.update_entry_list(media['entry_id'])
			self.update_feed_list(feed_id)
		except ptvDB.NoEntry:
			self.feed_list_view.populate_feeds()
			self.feed_list_view.resize_columns()
			
	def populate_and_select(self, feed_id):
		self.feed_list_view.populate_feeds()
		self.filter_combo_widget.set_active(FeedList.ALL)
		self.filter_unread_checkbox.set_active(False)
		self.feed_list_view.set_selected(feed_id)
		self.feed_list_view.resize_columns()
		
	def rename_feed(self, feed_id, name):
		if len(name)==0:
			self.db.set_feed_name(feed_id, None) #gets the title the feed came with
		else:
			self.db.set_feed_name(feed_id, name)
		self.feed_list_view.populate_feeds()
		self.feed_list_view.resize_columns()	
		#self.filter_combo_widget.set_active(FeedList.ALL)
		#self.filter_unread_checkbox.set_active(False)
		
	def set_auto_resume(self, client, *args, **kwargs):
		autoresume = client.get_bool('/apps/penguintv/auto_resume')
		self.window_preferences.set_auto_resume(autoresume)	
		self.autoresume = autoresume
		
	def set_auto_download(self, client, *args, **kwargs):
		auto_download = client.get_bool('/apps/penguintv/auto_download')
		self.window_preferences.set_auto_download(auto_download)	
		self.auto_download = auto_download
		
	def set_auto_download_limiter(self, client, *args, **kwargs):
		auto_download_limiter = client.get_bool('/apps/penguintv/auto_download_limiter')
		self.window_preferences.set_auto_download_limiter(auto_download_limiter)	
		self.auto_download_limiter = auto_download_limiter

	def set_auto_download_limit(self, client, *args, **kwargs):
		auto_download_limit = client.get_int('/apps/penguintv/auto_download_limit')
		self.window_preferences.set_auto_download_limit(auto_download_limit)	
		self.auto_download_limit = auto_download_limit
		
	def get_selected_items(self):
		selected_feed = self.feed_list_view.get_selected()[0]
		filter_setting = self.feed_list_view.filter_setting
		selected_entry = self.entry_list_view.get_selected()['entry_id']
		return {'feed':selected_feed,
				'filter':filter_setting,
				'entry':selected_entry}
	
	def set_selected_items(self, dic):
		#self.feed_list_view.set_filter(dic['filter'])
		self.feed_list_view.set_selected(dic['feed'])
		self.entry_list_view.populate_entries(dic['feed'],dic['entry'])

	def update_feed_list(self, feed_id=None):
		self.feed_list_view.update_feed_list(feed_id) #for now, just update this ONLY
		
	def update_entry_list(self, entry_id=None):
		self.entry_list_view.update_entry_list(entry_id)			
		
	def update_disk_usage(self):
		size = self.mediamanager.get_disk_usage()
		self.disk_usage_widget.set_text(utils.format_size(size))
		
	def on_about_activate(self,event):
		try:
			self.about_box.run()
		except:
			pass #fc3 workaround
		
	def on_about_close(self, event):
		self.about_box.hide()
		
	def on_app_delete_event(self,event,data):
		self.do_quit()
		
	def on_app_destroy_event(self,event,data):
		self.do_quit()
		
	def on_app_window_state_event(self, client, event):
		if event.new_window_state & gtk.gdk.WINDOW_STATE_MAXIMIZED:
			self.window_maximized = True
		elif event.new_window_state & gtk.gdk.WINDOW_STATE_MAXIMIZED == 0:
			self.window_maximized = False
			
	def on_add_feed_activate(self, event):
		self.on_feed_add_clicked(event)

	def on_download_entry_activate(self, event):
		entry = self.entry_list_view.get_selected()['entry_id']
		if entry:
			self.mediamanager.download_entry(entry)
			self.update_entry_list()
			self.update_feed_list()
			
	def on_download_unviewed_activate(self, event):
		feeds = self.db.get_feedlist()
		download_list=self.db.get_media_for_download()
		total_size=0
		if len(download_list)==0:
			dialog = gtk.Dialog(title=_("No Unviewed Media"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("There is no unviewed media to download."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
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
			response = dialog.run()
			dialog.hide()
			del dialog
			if response != gtk.RESPONSE_ACCEPT:
				return
		for d in download_list:
			self.mediamanager.download(d[0])
		self.feed_list_view.populate_feeds()
		
	def on_download_unviewed_clicked(self,event):
		self.on_download_unviewed_activate(event)
			
	def on_delete_entry_media_activate(self,event):
		selected = self.entry_list_view.get_selected()['entry_id']
		if selected:
			self.delete_entry_media(selected)
			self.update_entry_list()
			self.update_feed_list()
			self.update_disk_usage()
			
	def on_delete_feed_media_activate(self,event):
		selected,index = self.feed_list_view.get_selected()
		if selected:
			self.delete_feed_media(selected)
			
	def on_edit_tags_activate(self, event):
		"""Edit Tags clicked, bring up tag editing dialog"""
		selected,index = self.feed_list_view.get_selected()
		self.window_edit_tags_single.set_feed_id(selected)
		self.window_edit_tags_single.set_tags(self.db.get_tags_for_feed(selected))
		self.window_edit_tags_single.show()
		
	def on_edit_tags_for_all_activate(self, event):
		"""Bring up mass tag creation window"""
		window_edit_tags_multi = EditTagsMultiDialog.EditTagsMultiDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_edit_tags_multi",'penguintv'),self)
		window_edit_tags_multi.show()
		window_edit_tags_multi.set_feed_list(self.db.get_feedlist())

			
	def on_export_opml_activate(self, event):
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
    		
		response = dialog.run()
		if response == gtk.RESPONSE_OK:
			try:
				f = open(dialog.get_filename(), "w")
				self.display_status_message(_("Exporting Feeds..."))
				task_id = self.updater.queue_task(DB, self.updater_thread_db.export_OPML, f)
				task_id2 = self.updater.queue_task(GUI, self.feed_list_view.populate_feeds, None, task_id)
				self.updater.queue_task(GUI,self.display_status_message, " ", task_id2)
			except:
				pass
		elif response == gtk.RESPONSE_CANCEL:
			#print 'Closed, no files selected'
			pass
		dialog.destroy()
		
	def on_feed_add_clicked(self,event):
		self.window_add_feed.show() #not modal / blocking
		
	def on_feed_remove_clicked(self,event): 
		dialog = gtk.Dialog(title=_("Really Delete Feed?"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
		label = gtk.Label(_("Are you sure you want to delete this feed?"))
		dialog.vbox.pack_start(label, True, True, 0)
		label.show()
		response = dialog.run()
		dialog.hide()
		del dialog
		if response == gtk.RESPONSE_ACCEPT:
			selected,index = self.feed_list_view.get_selected()
			#select entries and get all the media ids, and tell them all to cancel
			#in case they are downloading
			try:
				for entry_id,title,date,new in self.db.get_entrylist(selected):
					try:
						for medium in self.db.get_entry_media(entry_id):
							self.download_task_ops.append((CANCEL,medium['media_id']))
					except: #keep trying
						pass
			except:
				pass
			self.db.delete_feed(selected)
			self.feed_list_view.populate_feeds()
			self.update_disk_usage()
			self.feed_list_view.resize_columns()
			self.entry_list_view.clear_entries()
			self.update_filters()
			
	def on_feedlistview_drag_data_received(self, widget, context, x, y, selection, targetType, time):
		widget.emit_stop_by_name('drag-data-received')
		if targetType == self.TARGET_TYPE_TEXT:
			url = ""
			for c in selection.data:
				if c != "\0":  #for some reason ever other character is a null.  what gives?
					url = url+c
			if url.split(':')[0] == 'feed':
				url = url[url.find(':')+1:]
			self.add_feed(url)
		elif targetType == self.TARGET_TYPE_URL:
			url = ""
			for c in selection.data[0:selection.data.find('\n')]:
				if c != '\0':
					url = url+c
			if url.split(':')[0] == 'feed': #stupid wordpress does 'feed:http://url.com/whatever'
				url = url[url.find(':')+1:]
			self.add_feed(url)
			
	def on_feedlistview_button_press_event(self, widget, event):          
		if event.button==3: #right click                               
			menu = gtk.Menu()                                       

			item = gtk.MenuItem(_("Re_name"))
			item.connect('activate',self.on_rename_feed_activate)
			menu.append(item)
			
			item = gtk.MenuItem(_("Edit _Tags"))
			item.connect('activate',self.on_edit_tags_activate)
			menu.append(item)
			
			item = gtk.ImageMenuItem('gtk-refresh')
			item.connect('activate',self.on_refresh_activate)
			menu.append(item)
			
			item = gtk.MenuItem(_("Mark as _Viewed"))
			item.connect('activate',self.on_mark_feed_as_viewed_activate)
			menu.append(item)
			
			menu.show_all()
			menu.popup(None,None,None, event.button,event.time)
	
	def on_feedlistview_popup_menu(self, event):
		pass
		
	def on_entrylistview_button_press_event(self, widget, event):          
		if event.button==3: #right click     
			self.entry_list_view.do_context_menu(event)       
	
	def on_entrylistview_popup_menu(self, event):
		self.entry_list_view.do_context_menu(event)
	
		
	def on_feeds_poll_clicked(self,event):
		self.set_wait_cursor()
		args = ptvDB.A_ALL_FEEDS
		if self.feed_refresh_method==REFRESH_AUTO:
			args = args | ptvDB.A_AUTOTUNE
		self.do_poll_multiple(None, args)
		self.set_wait_cursor(False)
		
	def on_filter_combo_changed(self, event):
		model = self.filter_combo_widget.get_model()
		current_filter = model[self.filter_combo_widget.get_active()][0]
		self.feed_list_view.set_filter(self.filter_combo_widget.get_active(), current_filter)
		
	def on_import_opml_activate(self, event):
		dialog = gtk.FileChooserDialog(_('Select OPML...'),None, action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                  buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
		dialog.set_default_response(gtk.RESPONSE_OK)
    
		filter = gtk.FileFilter()
		filter.set_name("OPML files")
		filter.add_pattern("*.opml")
		dialog.add_filter(filter)
		
		filter = gtk.FileFilter()
		filter.set_name("All files")
		filter.add_pattern("*")
		dialog.add_filter(filter)
		
		response = dialog.run()
		if response == gtk.RESPONSE_OK:
			try:
				f = open(dialog.get_filename(), "r")
				self.display_status_message(_("Importing Feeds, please wait..."))
				#task_id = self.updater.queue_task(DB, self.updater_thread_db.import_OPML,f)
				#task_id2 = self.updater.queue_task(GUI, self.feed_list_view.populate_feeds,None, task_id)
				#task_id3 = self.updater.queue_task(GUI, self.do_poll_multiple,None, task_id2)
				#self.updater.queue_task(GUI, self.display_status_message, " ", task_id3)
				self.db.import_OPML(f)
				self.feed_list_view.populate_feeds()
				self.do_poll_multiple()
				self.display_status_message(" ")
			except:
				pass
		elif response == gtk.RESPONSE_CANCEL:
			print 'Closed, no files selected'
		dialog.destroy()		
			
	def on_mark_entry_as_viewed_activate(self,event):
		entry = self.entry_list_view.get_selected()['entry_id']
		if entry:
			self.db.set_entry_read(entry,True)
			self.update_entry_list()
			self.update_feed_list()

	def on_mark_entry_as_unviewed_activate(self,event):
		entry = self.entry_list_view.get_selected()['entry_id']
		if entry:
			media = self.db.get_entry_media(entry)
			self.db.set_entry_read(entry, 0)
			if media:
				for medium in media:
					self.db.set_media_viewed(medium['media_id'],False)
				self.update_entry_list()
			else:
				self.db.set_entry_read(entry, 0)
				self.update_entry_list()
			self.update_feed_list()
	
	def on_mark_feed_as_viewed_activate(self,event):
		feed = self.feed_list_view.get_selected()[0]
		if feed:
			self.db.mark_feed_as_viewed(feed)
			self.entry_list_view.populate_entries(feed)
			self.update_feed_list(feed)
 
 	def on_play_entry_activate(self, event):
		entry = self.entry_list_view.get_selected()['entry_id']
		if entry:
			media = self.db.get_entry_media(entry)
			self.db.set_entry_read(entry, True)
			filelist=[]
			if media:
				for medium in media:
					filelist.append(medium['file'])
					self.db.set_media_viewed(medium['media_id'],True)
		self.player.play(filelist)
		self.update_feed_list()
		self.update_entry_list()
				
	def on_play_unviewed_activate(self, event):
		playlist = self.db.get_unplayed_media_set_viewed()
		playlist.reverse()
		self.player.play(playlist)
		self.feed_list_view.populate_feeds()
	
	def on_play_unviewed_clicked(self, event):
		self.on_play_unviewed_activate(event)
		
	def on_preferences_activate(self, event):
		self.window_preferences.show()
		
	def on_quit2_activate(self,event):
		self.do_quit() #make the program quit, dumbass
		
	def on_refresh_activate(self, event):
		#if event.state & gtk.gdk.SHIFT_MASK:
		#	print "shift-- shift delete it"
		selected,index = self.feed_list_view.get_selected()
		task_id = self.updater.queue_task(DB,self.updater_thread_db.poll_feed,(selected,ptvDB.A_IGNORE_ETAG))
		self.updater.queue_task(GUI,self.feed_list_view.populate_feeds,None, task_id)
		#self.updater.queue_task(GUI,self.feed_list_view.set_selected,selected, task_id)
		
	def on_refresh_feeds_activate(self, event):
		self.on_feeds_poll_clicked(event)
		
	def on_remove_feed_activate(self, event):
		self.on_feed_remove_clicked(event)		
		
	def on_rename_feed_activate(self, event):
		selected,index = self.feed_list_view.get_selected()
		self.window_rename_feed.set_feed_id(selected)
		self.window_rename_feed.set_feed_name(self.db.get_feed_title(selected))
		self.window_rename_feed.show()	
			
	def on_resume_all_activate(self, event):
		self.resume_resumable()
		
	def on_show_downloads_activate(self, event):
		self.mediamanager.generate_playlist()
		self.mediamanager.show_downloads()
		
	def on_stop_downloads_clicked(self, widget):
		"""stops downloading everything -- really just pauses them.  Just sets a flag, really.
		progress_callback does the actual work"""
		if self.pausing_all_downloads == False:
			self.pausing_all_downloads = True
			download_stopper_thread = threading.Thread(None, self.mediamanager.pause_all_downloads)
			download_stopper_thread.start() #this isn't gonna block any more!
			self.db.pause_all_downloads() #blocks, but prevents race conditions
			self.feed_list_view.populate_feeds() #right now this is taking the longest

	def on_standard_layout_activate(self, event):
		if self.app_window_layout != 'standard':
			self.layout_changing_dialog.show_all()
			taskid = self.updater.queue_task(GUI, self.activate_layout, 'standard')
			self.updater.queue_task(GUI,  gobject.timeout_add, (333, self.hide_layout_changing_dialog), taskid)
	
	def on_horizontal_layout_activate(self, event):
		if self.app_window_layout != 'widescreen':
			self.layout_changing_dialog.show_all()
			taskid = self.updater.queue_task(GUI, self.activate_layout, 'widescreen')
			self.updater.queue_task(GUI,  gobject.timeout_add, (333, self.hide_layout_changing_dialog), taskid)
	
	def on_vertical_layout_activate(self,event):
		if self.app_window_layout != 'vertical':
			self.layout_changing_dialog.show_all()
			taskid = self.updater.queue_task(GUI, self.activate_layout, 'vertical')
			self.updater.queue_task(GUI,  gobject.timeout_add, (333, self.hide_layout_changing_dialog), taskid)
			
	def on_window_changing_layout_delete_event(self, widget, event):
		self.changing_layout = False
		return widget.hide_on_delete()
			
	def activate_layout(self, layout):
		self.changing_layout = True
		self.app_window_layout=layout
		dic = self.get_selected_items()
		self.save_settings()
		self.Hide()
		self.Show()
		self.feed_list_view.populate_feeds()
		self.set_selected_items(dic)
		self.update_disk_usage()
		
	def hide_layout_changing_dialog(self):
		self.changing_layout = False
		self.layout_changing_dialog.hide()
		return False
		
	def is_changing_layout(self):
		return self.changing_layout
		
	def on_unread_filter_toggled(self, event):
		self.feed_list_view.set_unread_toggle(self.filter_unread_checkbox.get_active())
			
	def _progress_callback(self,data):
		if self.pausing_all_downloads == True:
			self.updater.queue_task(GUI,self.do_pause_download,data[0], None, True, 1)
			return 1 #returning one is what interrupts the download
		
		cancel_this = self.download_task_ops.count((CANCEL,data[0]['media_id']))
		while self.download_task_ops.count((CANCEL, data[0]['media_id'])):  #could be multiple copies of same click
			self.download_task_ops.remove((CANCEL, data[0]['media_id']))
			
		pause_this = self.download_task_ops.count((PAUSE,data[0]['media_id']))
		while self.download_task_ops.count((PAUSE, data[0]['media_id'])):
			self.download_task_ops.remove((PAUSE, data[0]['media_id']))
			
		if cancel_this>0 or self.exiting==1:
			self.updater.queue_task(GUI,self.do_cancel_download,data[0], None, True, 1)
			return 1 #returning one is what interrupts the download
		elif pause_this>0:
			self.updater.queue_task(GUI,self.do_pause_download,data[0], None, True, 1)
			return 1 #returning one is what interrupts the download
		
		if data[0].has_key('size_adjustment'):
			if data[0]['size_adjustment']==True:
				###print "adjusting size"
				self.updater.queue_task(DB,self.updater_thread_db.set_media_size,(data[0]['media_id'], data[0]['size']))
				###print "done adjusting size"
			
		superglobal.download_status[data[0]['media_id']]=(DOWNLOAD_PROGRESS,data[1])
		if self.changing_layout == False:
			self.updater.queue_task(GUI,self.entry_view.update_progress,data)

	def _finished_callback(self,data):
		###print "finished callback"
		if self.pausing_all_downloads:
			if self.mediamanager.get_download_count() <= 1: #last one!
				self.pausing_all_downloads = False #we're done
		self.mediamanager.update_playlist(data[0])
		self.updater.queue_task(GUI,self.download_finished, data)
		
	def _polling_callback(self, args):
		###print "polling callback",
		feed_id,update_data = args
		self.updater.queue_task(GUI, self.feed_list_view.update_feed_list, (feed_id,update_data))
		self.updater.queue_task(GUI, self.entry_list_view.populate_if_selected, feed_id)
		###print ", and out"
				
	def _entry_image_download_callback(self, entry_id, html):
		self.updater.queue_task(GUI, self.entry_view._images_loaded,(entry_id, html))
			
	class DBUpdaterThread(threading.Thread):
		def __init__(self, updater, polling_callback=None):
			threading.Thread.__init__(self)
			self.__isDying = False
			self.db = None
			self.updater = updater
			self.threadSleepTime = 0.5
			if polling_callback is None:
				self.polling_callback = self._polling_callback
			else:
				self.polling_callback = polling_callback
			
		def _polling_callback(self, data):
			pass
	        
		def run(self):
	
			""" Until told to quit, retrieve the next task and execute
				it, calling the callback if any.  """
				
			if self.db == None:
				self.db = ptvDB.ptvDB(self.polling_callback)
						
			while self.__isDying == False:
				skipped = 0
#				self.updater.lock_acquire(DB)
				current_task_count = self.updater.task_count(DB)
				while current_task_count>0 and skipped != current_task_count:
					var = self.updater.peek_task(DB, skipped)
					func, args, task_id, waitfor, clear_completed = var 
					if waitfor:
						if self.updater.is_completed(waitfor): #don't pop if false
							try:
								if type(args) is tuple:
									func(*args)
								elif args:
									func(args)
								else:
									func()
							except ptvDB.FeedPollError,e:
								print e
							except:
								print "ERROR from db updater"
								exc_type, exc_value, exc_traceback = sys.exc_info()
								error_msg = ""
								for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
									error_msg += s
								print error_msg
							self.updater.set_completed(task_id)
							if clear_completed:
								self.updater.clear_completed(waitfor)
							self.updater.pop_task(DB, skipped)
						else:
							skipped = skipped+1
					else:
						try:
							if type(args) is tuple:
								func(*args)
							elif args:
								func(args)
							else:
								func()
						except ptvDB.FeedPollError,e:
							print e
						except:
							print "ERROR from db updater:"
							exc_type, exc_value, exc_traceback = sys.exc_info()
							error_msg = ""
							for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
								error_msg += s
							print error_msg
						self.updater.set_completed(task_id)
						self.updater.pop_task(DB, skipped)
					current_task_count-=1
#				self.updater.lock_release(DB)
				time.sleep(self.threadSleepTime)
						
		def get_db(self):
			return self.db
	
		def goAway(self):
	
			""" Exit the run loop next time through."""
	        
			self.__isDying = True
		
	def _gui_updater(self):
		if self.updater.task_count(GUI)==0:
			return True
		skipped=0
		performed=0
		#self.updater.lock_acquire(GUI)
		current_task_count = self.updater.task_count(GUI)
		while current_task_count > 0 and performed<3 and skipped != current_task_count:
			var = self.updater.peek_task(GUI, skipped)
			#print var
			func, args, task_id, waitfor, clear_completed =  var
			if waitfor:
				if self.updater.is_completed(waitfor): #don't pop if false
					
					try:
						if type(args) is tuple:
							func(*args)
						elif args:
							func(args)
						else:
							func()
					except:
						print "ERROR from gui updater:"
						exc_type, exc_value, exc_traceback = sys.exc_info()
						error_msg = ""
						for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
							error_msg += s
						print error_msg
					performed+=1
					self.updater.set_completed(task_id)
					if clear_completed:
						self.updater.clear_completed(waitfor)
					self.updater.pop_task(GUI, skipped)
				else:
					skipped = skipped+1
			else:
				try:
					if type(args) is tuple:
						func(*args)
					elif args:
						func(args)
					else:
						func()
				except:
					exc_type, exc_value, exc_traceback = sys.exc_info()
					error_msg = ""
					for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
						error_msg += s
					print error_msg
				performed+=1
				self.updater.set_completed(task_id)
				self.updater.pop_task(GUI, skipped)
			current_task_count-=1
		#self.updater.lock_release(GUI)
		return True
				
	def display_status_message(self, m):
		self._status_view.set_status(m)

def main():
	gnome.init("PenguinTV", utils.VERSION)
	app = PenguinTVApp()    # Instancing of the GUI
	app.Show() 
	app.post_show_init()
	gtk.threads_init()
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
			print "Unable to initialize KDE"
			sys.exit(1)	
	gtk.main() 
        
if __name__ == '__main__': # Here starts the dynamic part of the program 
	gnome.init("PenguinTV", utils.VERSION)
	app = PenguinTVApp()    # Instancing of the GUI
	app.Show() 
	app.post_show_init()
	gtk.threads_init()
	#profile.run('gtk.main()', 'pengprof')
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
			print "Unable to initialize KDE"
			sys.exit(1)	
	gtk.main()
