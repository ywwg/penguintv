#!/usr/bin/env python
# Written by Owen Williams
# using pieces from Straw
# see LICENSE for license information


#memory profiling:

#import code
#from sizer import scanner
#objs = scanner.Objects()
#code.interact(local = {'objs': objs})
#from sizer import formatting


import urlparse
import threading
import sys,os, os.path
import traceback
import urllib
import time
import sets
import string
import timeoutsocket

import gtk
import gnome.ui
import gtk.glade
import gobject
import locale
import gettext
import gconf
import HTMLParser
import feedparser

import PyLucene

locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

#DEBUG (see also utils.py for some debugs)
_FORCE_DEMOCRACY_MOZ=False

DOWNLOAD_ERROR=0
DOWNLOAD_PROGRESS=1
DOWNLOAD_WARNING=2
DOWNLOAD_QUEUED=3

import ptvDB
import MediaManager
import Player
import UpdateTasksManager
import utils
import Downloader
import PTVAppSocket

import AddFeedDialog
import PreferencesDialog
import MainWindow, FeedList, EntryList, EntryView

CANCEL=0
PAUSE=1

REFRESH_SPECIFIED=0
REFRESH_AUTO=1

AUTO_REFRESH_FREQUENCY=5*60*1000

class PenguinTVApp:
	def __init__(self, logfile=None):
		self.socket = PTVAppSocket.PTVAppSocket(self._socket_cb)
		if not self.socket.is_server:
			#just pass the arguments and quit
			if len(sys.argv)>1:
				self.socket.send(" ".join(sys.argv[1:]))
			self.socket.close()
			return
			
		self.for_import = []
		if len(sys.argv)>1:
			self.for_import.append(sys.argv[1])
			
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
					try:
						self.glade_prefix = utils.GetPrefix()+"/share/sugar/activities/ptv/share"
						os.stat(self.glade_prefix+"/penguintv.glade")
					except:
						print "error finding glade file."
						sys.exit()
						
		if logfile is not None:
			try:
				f = os.stat(logfile)
				self.logfile = open(logfile,"a")	
			except:
				self.logfile = open(logfile,"w")
			self.log("penguintv "+utils.VERSION+" startup")
		else:
			self.logfile = None
			
		self.db = ptvDB.ptvDB(self._polling_callback)
		self.firstrun = self.db.maybe_initialize_db()
		#self.db.maybe_write_term_frequency_table()
		self.db.clean_media_status()
		self.mediamanager = MediaManager.MediaManager(self._progress_callback, self._finished_callback)
		self.conf = gconf.client_get_default()
		self.player = Player.Player()
		self._updater_db = None
		self.polled=0      #Used for updating the polling progress bar
		self.polling_taskid=0 #the taskid we can use to waitfor a polling operation
		self.polling_frequency=12*60*60*1000
		self.bt_settings = {}
		self.exiting=0
		self.auto_download = False
		self.auto_download_limiter = False
		self.auto_download_limit=1024*1024
		self.saved_filter = FeedList.ALL
		self.saved_search = ""
		self.showing_search = False
		self.threaded_searcher = None
		self.waiting_for_search = False
		
		window_layout = self.conf.get_string('/apps/penguintv/app_window_layout')
		if window_layout is None:
			window_layout='standard'
		
		self.main_window = MainWindow.MainWindow(self,self.glade_prefix) 
		self.main_window.layout=window_layout
		
	def log(self, message):
		if self.logfile is not None:
			self.logfile.write(message+"\n")
			self.logfile.flush()
			
	def post_show_init(self):
		"""After we have Show()n the main window, set up some more stuff"""
		self.gui_updater = UpdateTasksManager.UpdateTasksManager(UpdateTasksManager.GOBJECT, "gui updater")
		self._db_updater = self.DBUpdaterThread(self._polling_callback)
		self._db_updater.start()
		self.updater_thread_db = None
		while self.updater_thread_db==None or self.db_updater == None:
			#this may race, so be patient 
			self.updater_thread_db = self._db_updater.get_db()
			self.db_updater = self._db_updater.get_updater()
			time.sleep(.1)

		#WINDOWS
		self.window_add_feed = AddFeedDialog.AddFeedDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_add_feed",'penguintv'),self) #MAGIC
		self.window_add_feed.hide()
		self.window_preferences = PreferencesDialog.PreferencesDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_preferences",'penguintv'),self) #MAGIC
		self.window_preferences.hide()
		#self.layout_changing_dialog = gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_changing_layout",'penguintv').get_widget("window_changing_layout")
		#self.layout_changing_dialog.connect("delete-event",self.on_window_changing_layout_delete_event)
		#self.layout_changing_dialog.hide()
					
		#gconf
		self.conf.add_dir('/apps/penguintv',gconf.CLIENT_PRELOAD_NONE)
		self.conf.notify_add('/apps/penguintv/auto_resume',self.set_auto_resume)
		self.conf.notify_add('/apps/penguintv/poll_on_startup',self.set_poll_on_startup)
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
		
		self.feed_list_view = self.main_window.feed_list_view
		self.entry_list_view = self.main_window.entry_list_view
		self.entry_view = self.main_window.entry_view

		#updaters
		#gobject.timeout_add(500, self._gui_updater)
		self.main_window.search_container.set_sensitive(False)
		if self.db.cache_dirty: #assume index is bad as well
			self.main_window.search_entry.set_text(_("Please wait..."))
			self.db.doindex(self._sensitize_search)
			self.feed_list_view.populate_feeds(self._done_populating_dont_sensitize)
		else:
			self.feed_list_view.populate_feeds(self._done_populating)
		if self.autoresume:
			gobject.idle_add(self.resume_resumable)
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
			self.main_window.display_status_message(_("Polling feeds for the first time..."))
			#task_id = self.db_updater.queue_task(self.updater_thread_db.import_OPML,f)
			#self.gui_updater.queue_task(self.feed_list_view.populate_feeds,None, task_id)
			#self.do_poll_multiple()
			self.import_opml(f)
		return False #for idler	
		
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
		
		val = self.conf.get_bool('/apps/penguintv/poll_on_startup')
		if val is None:
			val=True
		self.poll_on_startup = val
		self.window_preferences.set_poll_on_startup(val)
		
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
		
		#also poll in 30 seconds (ie, "poll on startup")
		if self.poll_on_startup and not self.firstrun: #don't poll on startup on firstrun, we take care of that
			gobject.timeout_add(30*1000,self.do_poll_multiple, 0)
			
	def save_settings(self):
		self.conf.set_int('/apps/penguintv/feed_pane_position',self.main_window.feed_pane.get_position())
		self.conf.set_int('/apps/penguintv/entry_pane_position',self.main_window.entry_pane.get_position())
		if self.main_window.app_window is not None:
			x,y=self.main_window.app_window.get_position()
			self.conf.set_int('/apps/penguintv/app_window_position_x',x)
			self.conf.set_int('/apps/penguintv/app_window_position_y',y)
			if self.main_window.window_maximized == False:
				x,y=self.main_window.app_window.get_size()
			else: #grabbing the size when we are maximized is pointless, so just go by the old resized size
				x = self.conf.get_int('/apps/penguintv/app_window_size_x')
				y = self.conf.get_int('/apps/penguintv/app_window_size_y')
				x,y=(-abs(x),-abs(y))
			self.conf.set_int('/apps/penguintv/app_window_size_x',x)
			self.conf.set_int('/apps/penguintv/app_window_size_y',y)
		
		self.conf.set_string('/apps/penguintv/app_window_layout',self.main_window.layout)
		if self.feed_refresh_method==REFRESH_AUTO:
			self.conf.set_string('/apps/penguintv/feed_refresh_method','auto')
		else:
			self.conf.set_int('/apps/penguintv/feed_refresh_frequency',self.polling_frequency/(60*1000))
			self.conf.set_string('/apps/penguintv/feed_refresh_method','specified')	
		self.conf.set_int('/apps/penguintv/bt_max_port',self.bt_settings['max_port'])
		self.conf.set_int('/apps/penguintv/bt_min_port',self.bt_settings['min_port'])
		self.conf.set_int('/apps/penguintv/bt_ul_limit',self.bt_settings['ul_limit'])
		self.conf.set_bool('/apps/penguintv/auto_resume',self.autoresume)
		self.conf.set_bool('/apps/penguintv/poll_on_startup',self.poll_on_startup)
		self.conf.set_bool('/apps/penguintv/auto_download',self.auto_download)
		self.conf.set_bool('/apps/penguintv/auto_download_limiter',self.auto_download_limiter)
		self.conf.set_int('/apps/penguintv/auto_download_limit',self.auto_download_limit)
		if self.feed_list_view.filter_setting > FeedList.NONE:
			self.conf.set_string('/apps/penguintv/default_filter',self.feed_list_view.filter_name)
		else:
			self.conf.set_string('/apps/penguintv/default_filter',"")
	
	def resume_resumable(self):
		list = self.db.get_resumable_media()
		if list:
			gobject.idle_add(self._resumer_generator(list).next)
		return False #to cancel idler
		
	def _resumer_generator(self, list):
		for medium in list:
			#if self.pausing_all_downloads: #bail
			#	yield False
			print "resuming "+str(medium['file'])
			self.mediamanager.download(medium['media_id'], False, True) #resume please
			self.db.set_entry_read(medium['entry_id'],False)
			self.feed_list_view.update_feed_list(medium['feed_id'],['icon'])
			yield True
		yield False
		
	def do_quit(self):
		"""save and shut down all our threads"""
		self.exiting=1
		self.feed_list_view.interrupt()
		self._db_updater.goAway()
		self.updater_thread_db.finish()
		self.entry_view.finish()
		self.main_window.desensitize()
		self.stop_downloads()
		self.save_settings()
		#if anything is downloading, report it as paused, because we pause all downloads on quit
		adjusted_cache = [[c[0],(c[1] & ptvDB.F_DOWNLOADING and c[1]-ptvDB.F_DOWNLOADING+ptvDB.F_PAUSED or c[1]),c[2],c[3]] for c in self.feed_list_view.get_feed_cache()]
		self.db.set_feed_cache(adjusted_cache)
		self.db.finish()	
		self.mediamanager.finish()
		while threading.activeCount()>1:
			###print threading.enumerate()
			###print str(threading.activeCount())+" threads active..."
			time.sleep(1)
		self.socket.close()
		gtk.main_quit()
		
	def write_feed_cache(self):
		self.db.set_feed_cache(self.feed_list_view.get_feed_cache())
		
	def do_poll_multiple(self, was_setup=None, arguments=0, feeds=None):
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
		self.main_window.update_progress_bar(0,MainWindow.U_POLL)
		self.main_window.display_status_message(_("Polling Feeds..."), MainWindow.U_POLL)			
		task_id = self.db_updater.queue_task(self.updater_thread_db.poll_multiple, (arguments,feeds))
		if arguments & ptvDB.A_ALL_FEEDS==0:
			self.gui_updater.queue_task(self.main_window.display_status_message,_("Feeds Updated"), task_id, False)
			#insane: queueing a timeout
			self.gui_updater.queue_task(gobject.timeout_add, (2000, self.main_window.display_status_message, ""), task_id, False)
		self.polling_taskid = self.gui_updater.queue_task(self.update_disk_usage, None, task_id, False) #because this is also waiting
		if self.auto_download == True:
			self.polling_taskid = self.gui_updater.queue_task(self.auto_download_unviewed, None, task_id)
		if was_setup!=0:
			return True
		return False
	
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
			self.feed_list_view.update_feed_list(d[3],['icon'])
			#self.entry_list_view.populate_entries(d[3])
			self.entry_list_view.update_entry_list(d[2])
			
	def add_search_tag(self, query, tag_name):
		self.db.add_search_tag(query, tag_name)
		#could raise ptvDB.TagAlreadyExists, let it go
		self.main_window.update_filters()
			
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
		self.main_window.update_filters()
					
	def display_feed(self, feed_id, selected_entry=-1):
		"""used by other classes so they don't all need to know about EntryList"""
		self.entry_list_view.populate_entries(feed_id,selected_entry)
		
	def display_entry(self, entry_id, set_read=1, query=""):
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
				self.feed_list_view.update_feed_list(item['feed_id'],['readinfo','icon'])
				for f in self.db.get_pointer_feeds(item['feed_id']):
					self.feed_list_view.update_feed_list(f,['readinfo','icon'])
		self.entry_view.display_item(item, query)
	
	def display_custom_entry(self, message):
		"""Used by other classes so they don't need to know about EntryView"""
		self.entry_view.display_custom_entry(message)
		
	def undisplay_custom_entry(self):
		"""Used by other classes so they don't need to know about EntryView"""
		self.entry_view.undisplay_custom_entry()
	
	def activate_link(self, link):
		"""links can be basic hrefs, or they might be custom penguintv commands"""
		parsed_url = urlparse.urlparse(link)
		action=parsed_url[0] #protocol
		http_arguments=parsed_url[4]
		anchor = parsed_url[5]
		try:
			item=int(parsed_url[2])
		except:
			pass
		if action == "download":
			self.mediamanager.unpause_downloads()
			self.mediamanager.download(item)
			media = self.db.get_media(item)
			self.db.set_media_viewed(item,False)
			self.feed_list_view.update_feed_list(None,['icon'])
			self.update_entry_list()
		elif action=="resume" or action=="tryresume":
			self.mediamanager.unpause_downloads()
			self.mediamanager.download(item, False, True) #resume please
			media = self.db.get_media(item)
			self.db.set_media_viewed(item,False)
			self.feed_list_view.update_feed_list(None,['readinfo','icon'])
			self.update_entry_list()
		elif action=="play":
			media = self.db.get_media(item)
			self.db.set_entry_read(media['entry_id'],True)
			self.db.set_media_viewed(item,True)
			if utils.is_known_media(media['file']):
				self.player.play(media['file'])
			else:
				gnome.url_show(media['file'])
			self.feed_list_view.update_feed_list(None,['readinfo'])
			self.update_entry_list()
		elif action=="downloadqueue":
			self.mediamanager.unpause_downloads()
			self.mediamanager.download(item, True)
			self.db.set_media_viewed(item,False)
			self.feed_list_view.update_feed_list(None,['icon'])
			self.update_entry_list()
		elif action=="queue":
			print parsed_url		
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
			self.feed_list_view.update_feed_list(None,['readinfo','icon'])
			self.update_entry_list()
		elif action=="delete":
			self.delete_media(item)
			self.feed_list_view.update_feed_list(None,['readinfo','icon'])
			self.update_entry_list()
		elif action=="reveal":
			if utils.is_kde():
				reveal_url = "file:" + urllib.quote(parsed_url[1]+parsed_url[2])
				os.system('konqueror --select ' + reveal_url + ' &')
			else:
				reveal_url = "file:"+os.path.split(urllib.quote(parsed_url[1]+parsed_url[2]))[0]
				gnome.url_show(reveal_url)
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
			
	def download_entry(self, entry):
		self.mediamanager.download_entry(entry)
		self.update_entry_list(entry)
		self.feed_list_view.update_feed_list(None,['icon'])

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
		gobject.idle_add(self._downloader_generator(download_list).next)

	def _downloader_generator(self, download_list):
		for d in download_list:
			self.mediamanager.download(d[0])
			self.db.set_media_viewed(d[0],False)
			self.feed_list_view.update_feed_list(d[3],['icon'])
			self.feed_list_view.do_filter()
			self.entry_list_view.update_entry_list(d[2])
			yield True
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
    		
		response = dialog.run()
		if response == gtk.RESPONSE_OK:
			try:
				f = open(dialog.get_filename(), "w")
				self.main_window.display_status_message(_("Exporting Feeds..."))
				task_id = self.db_updater.queue_task(self.updater_thread_db.export_OPML, f)
				self.gui_updater.queue_task(self.main_window.display_status_message, "", task_id)
			except:
				pass
		elif response == gtk.RESPONSE_CANCEL:
			#print 'Closed, no files selected'
			pass
		dialog.destroy()

	def remove_feed(self, feed):		
		dialog = gtk.Dialog(title=_("Really Delete Feed?"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
		label = gtk.Label(_("Are you sure you want to delete this feed?"))
		dialog.vbox.pack_start(label, True, True, 0)
		label.show()
		response = dialog.run()
		dialog.hide()
		del dialog
		if response == gtk.RESPONSE_ACCEPT:
			#select entries and get all the media ids, and tell them all to cancel
			#in case they are downloading
			try:
				for entry_id,title,date,new in self.db.get_entrylist(feed):
					for medium in self.db.get_entry_media(entry_id):
						if self.mediamanager.has_downloader(medium['media_id']):
							self.mediamanager.stop_download(medium['media_id'])
			except:
				pass
			self.db.delete_feed(feed)
			self.feed_list_view.remove_feed(feed)
			self.update_disk_usage()
			self.feed_list_view.resize_columns()
			self.entry_list_view.clear_entries()
			self.main_window.update_filters()
	
	def poll_feeds(self, args=0):
		args = args | ptvDB.A_ALL_FEEDS
		if self.feed_refresh_method==REFRESH_AUTO:
			args = args | ptvDB.A_AUTOTUNE
		self.do_poll_multiple(None, args)
			
	def import_opml(self, f):
		print "import"
		def import_gen(f):
			dialog = gtk.Dialog(title=_("Importing OPML file"), parent=None, flags=gtk.DIALOG_MODAL, buttons=None)
			label = gtk.Label(_("Loading the feeds from the OPML file"))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			bar = gtk.ProgressBar()
			dialog.vbox.pack_start(bar, True, True, 0)
			bar.show()
			response = dialog.show()

			gen = self.db.import_OPML(f)
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
				if self.exiting:
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
			if len(newfeeds)>10:
				#it's faster to just start over if we have a lot of feeds to add
				self.main_window.search_container.set_sensitive(False)
				self.feed_list_view.clear_list()
				self.feed_list_view.populate_feeds(self._done_populating)
			else:
				for feed in newfeeds:
					self.feed_list_view.add_feed(feed)
			self.main_window.update_filters()
			saved_auto = False
			self.main_window.display_status_message("")
			#shut down auto-downloading for now (need to wait until feeds are marked)
			if self.auto_download:
				saved_auto = True
				self.auto_download = False
			self.do_poll_multiple(feeds=newfeeds)
			task_id = self.gui_updater.queue_task(self._first_poll_marking_list, (newfeeds,saved_auto), self.polling_taskid)
			dialog.hide()
			del dialog
			if len(newfeeds)==1:
				self.feed_list_view.set_selected(newfeeds[0])
			elif len(oldfeeds)==1:
				self.feed_list_view.set_selected(oldfeeds[0])
			yield False
		#schedule the import pseudo-threadidly
		gobject.idle_add(import_gen(f).next)
					
	def _first_poll_marking_list(self, list, saved_auto=False):
		def marking_gen(list):
			self.main_window.display_status_message(_("Finishing OPML import"))
			selected = self.feed_list_view.get_selected()
			for feed in list:
				self.first_poll_marking(feed)
				self.feed_list_view.update_feed_list(feed,['readinfo','icon','title'])
				if feed == selected:
					self.entry_list_view.update_entry_list()
				yield True
			self.main_window.display_status_message("")
			if saved_auto:
				self.auto_download_unviewed()
				self._reset_auto_download()
			yield False
		
		gobject.idle_add(marking_gen(list).next)

	def _reset_auto_download(self):
		self.auto_download = True
			
	def mark_entry_as_viewed(self,entry):
		self.db.set_entry_read(entry,True)
		self.update_entry_list(entry)
		self.feed_list_view.update_feed_list(None,['readinfo'])
			
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
		self.feed_list_view.update_feed_list(None,['readinfo'])

	def mark_feed_as_viewed(self,feed):
		self.db.mark_feed_as_viewed(feed)
		self.entry_list_view.populate_entries(feed)
		self.feed_list_view.update_feed_list(feed,['readinfo'])

	def play_entry(self,entry):
		media = self.db.get_entry_media(entry)
		self.db.set_entry_read(entry, True)
		filelist=[]
		if media:
			for medium in media:
				filelist.append(medium['file'])
				self.db.set_media_viewed(medium['media_id'],True)
		self.player.play(filelist)
		self.feed_list_view.update_feed_list(None,['readinfo'])
		self.update_entry_list(entry)
		
	def play_unviewed(self):
		playlist = self.db.get_unplayed_media_set_viewed()
		playlist.reverse()
		self.player.play(playlist)
		for item in playlist:
			self.feed_list_view.update_feed_list(item[3],['readinfo'])

	def refresh_feed(self,feed):
		#if event.state & gtk.gdk.SHIFT_MASK:
		#	print "shift-- shift delete it"
		self.main_window.display_status_message(_("Polling Feed..."))
		task_id = self.db_updater.queue_task(self.updater_thread_db.poll_feed,(feed,ptvDB.A_IGNORE_ETAG+ptvDB.A_DO_REINDEX))
		self.gui_updater.queue_task(self.feed_list_view.update_feed_list,(feed,['readinfo','icon']), task_id, False)
		self.gui_updater.queue_task(self.entry_list_view.update_entry_list,None, task_id, False)
		task_id2 = self.gui_updater.queue_task(self.main_window.display_status_message,_("Feed Updated"), task_id)
		self.gui_updater.queue_task(gobject.timeout_add, (2000, self.main_window.display_status_message, ""), task_id2)
		#self.gui_updater.queue_task(self.feed_list_view.set_selected,selected, task_id)
		
	def search(self, query, blacklist=None):
		try:
			query = query.replace("!","")
			#print blacklist
			result = self.db.search(query, blacklist=blacklist)
		except Exception, e:
			print "error with that search term", e
			result=([],[])
		return result
	
	def show_search(self, query, result):
		self.showing_search = True		
		try:
			#print result
			self.entry_list_view.show_search_results(result[1], query)
			self.feed_list_view.show_search_results(result[0])
		except ptvDB.BadSearchResults, e:
			print e
			self.db.reindex(result[0], [i[0] for i in result[1]])
			self.show_search(query, self.search(query))
			return
		self.main_window.filter_unread_checkbox.set_sensitive(False)
		
	def unshow_search(self):
		self.saved_search = self.main_window.search_entry.get_text()
		self.showing_search = False
		self.entry_list_view.unshow_search()
		self.feed_list_view.unshow_search()
		#self.entry_view.display_item()
		self.main_window.search_entry.set_text("")
		self.main_window.filter_unread_checkbox.set_sensitive(True)
		
	def threaded_search(self, query):
		if query != "":
			if self.threaded_searcher is None:
				self.threaded_searcher = PenguinTVApp.threaded_searcher(query, self._got_search, self._searcher_done)
			self.threaded_searcher.set_query(query)
			if not self.waiting_for_search:
				self.waiting_for_search = True
				self.threaded_searcher.start()
	
	def _got_search(self, query, results):
		self.gui_updater.queue_task(self.got_search, (query,results))
		
	def _searcher_done(self):
		self.waiting_for_search = False
		
	def got_search(self, query, results):
		self.show_search(query, results)
		if self.main_window.filter_combo_widget.get_active() != FeedList.SEARCH:
			self.saved_filter = self.main_window.filter_combo_widget.get_active()
			self.main_window.filter_combo_widget.set_active(FeedList.SEARCH)
		
	class threaded_searcher(PyLucene.PythonThread):
		def __init__(self, query, callback, done_callback):
			PyLucene.PythonThread.__init__(self)
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
		#self.saved_search = query #even if it's blank
		if len(query)==0:
			self.unshow_search()
			#self.saved_search = ""
			selected = self.feed_list_view.get_selected()
			if selected is not None:
				name = self.main_window.get_filter_name(self.saved_filter)
				if name not in self.db.get_tags_for_feed(selected):
					self.main_window.filter_combo_widget.set_active(FeedList.ALL)
				else:
					self.main_window.filter_combo_widget.set_active(self.saved_filter)
			return
	
		self.show_search(query, self.search(query))
		if self.main_window.filter_combo_widget.get_active() != FeedList.SEARCH:
			self.saved_filter = self.main_window.filter_combo_widget.get_active()
		self.main_window.filter_combo_widget.set_active(FeedList.SEARCH)
		
	def entrylist_selecting_right_now(self):
		return self.entry_list_view.presently_selecting
		
	def highlight_entry_results(self, feed_id):
		return self.entry_list_view.highlight_results(feed_id)
		
	def select_feed(self, feed_id):
		self.feed_list_view.set_selected(feed_id)

	def change_filter(self, current_filter, tag_type):
		filter_id = self.main_window.filter_combo_widget.get_active()
		if filter_id == FeedList.SEARCH:
			self.show_search(self.saved_search, self.search(self.saved_search))
			if self.threaded_searcher:
				if not self.waiting_for_search:
					self.main_window.search_entry.set_text(self.saved_search)
		else:
			if tag_type == ptvDB.T_SEARCH:
				query = self.db.get_search_tag(current_filter)
				#self.unshow_search()
				self.show_search(query, self.search(query,blacklist=[]))			
			else:
				if self.showing_search:
					self.unshow_search()
				self.main_window.feed_list_view.set_filter(filter_id, current_filter)
				
				
	def show_downloads(self):
		self.mediamanager.generate_playlist()
		self.mediamanager.show_downloads()
		
	def stop_downloads(self):
		"""stops downloading everything -- really just pauses them.  Just sets a flag, really.
		progress_callback does the actual work"""
		if self.mediamanager.pause_state == MediaManager.RUNNING:
			download_stopper_thread = threading.Thread(None, self.mediamanager.pause_all_downloads)
			download_stopper_thread.start() #this isn't gonna block any more!
			self.db.pause_all_downloads() #blocks, but prevents race conditions
			
	def change_layout(self, layout):
		if self.main_window.layout != layout:
			#self.layout_changing_dialog.show_all()
			self.feed_list_view.interrupt()
			while gtk.events_pending(): #make sure everything gets shown
				gtk.main_iteration()
			self.main_window.activate_layout(layout)
			self.feed_list_view = self.main_window.feed_list_view
			self.entry_list_view = self.main_window.entry_list_view
			self.entry_view = self.main_window.entry_view
			self.main_window.changing_layout = False
			#self.layout_changing_dialog.hide()

	def on_window_changing_layout_delete_event(self, widget, event):
		self.main_window.changing_layout = False
		return widget.hide_on_delete()

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
			
	def get_feed_refresh_method(self):
		return self.feed_refresh_method
			
	def set_feed_refresh_method(self, client, *args, **kwargs):
		refresh = self.conf.get_string('/apps/penguintv/feed_refresh_method')
		if refresh == 'auto':
			self.feed_refresh_method=REFRESH_AUTO
			self.polling_frequency = AUTO_REFRESH_FREQUENCY	
			gobject.timeout_add(self.polling_frequency,self.do_poll_multiple, self.polling_frequency)
		else:
			self.feed_refresh_method=REFRESH_SPECIFIED
			self.set_polling_frequency(client,None,None)
			
	def add_feed(self, url, title):
		"""Inserts the url and starts the polling process"""
		self.main_window.display_status_message(_("Trying to poll feed..."))
		feed_id = -1
		try:
			feed_id = self.db.insertURL(url, title)
			#change to add_and_select
			#taskid = self.gui_updater.queue_task(self.main_window.populate_and_select, feed_id)
			taskid = self.gui_updater.queue_task(self.feed_list_view.add_feed, feed_id)
			self.gui_updater.queue_task(self.main_window.select_feed, feed_id, taskid, False)
			taskid2=self.db_updater.queue_task(self.updater_thread_db.poll_feed_trap_errors, (feed_id,self._add_feed_callback), taskid)
			
		except ptvDB.FeedAlreadyExists, e:
			self.gui_updater.queue_task(self.main_window.select_feed, e.feed)
		self.window_add_feed.hide()
		return feed_id
		
	def add_feed_filter(self, pointed_feed_id, filter_name, query):
		#print pointed_feed_id, filter_name, query
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
		
	def _add_feed_callback(self, feed, success):
		if success:
			self.gui_updater.queue_task(self._add_feed_success, feed['feed_id'])
			self.gui_updater.queue_task(self.first_poll_marking, feed['feed_id'])
			self.gui_updater.queue_task(self.entry_list_view.populate_entries, feed['feed_id'])
			self.gui_updater.queue_task(self.feed_list_view.update_feed_list, (feed['feed_id'],['readinfo','icon','title']))
			if self.auto_download:
				self.gui_updater.queue_task(self.auto_download_unviewed)
			self.gui_updater.queue_task(gobject.idle_add, self.entry_list_view.auto_pane) #oh yeah, queue an idler
		else:
			self.gui_updater.queue_task(self.feed_list_view.update_feed_list, (feed['feed_id'],['icon','pollfail']))
			self.gui_updater.queue_task(self._add_feed_error, feed['feed_id'])
	
	def first_poll_marking(self, feed_id): 
		"""mark all media read except first one.  called when we first add a feed"""
		all_feeds_list = self.db.get_media_for_download()
		this_feed_list = []
		for item in all_feeds_list:
			if item[3]==feed_id:
				this_feed_list.append(item)
		for item in this_feed_list[1:]:
			self.db.set_entry_read(item[2],1)
		
	def _add_feed_error(self,feed_id):
		self.main_window.display_status_message(_("Error adding feed"))
		self.main_window.select_feed(feed_id)
		return False #for idle_add
		
	def _add_feed_success(self, feed_id):
		self.feed_list_view.update_feed_list(feed_id,['title'])
		self.main_window.select_feed(feed_id)
		self.main_window.display_status_message(_("Feed Added"))
		gobject.timeout_add(2000, self.main_window.display_status_message, "")
			
	def delete_entry_media(self, entry_id):
		"""Delete all media for an entry"""
		medialist = self.db.get_entry_media(entry_id)
		if medialist:
			for medium in medialist:
				if medium['download_status']==ptvDB.D_DOWNLOADED or medium['download_status']==ptvDB.D_RESUMABLE:
					#self.db_updater.queue_task(self.updater_thread_db.set_media_viewed, medium['media_id'])
					self.delete_media(medium['media_id'])
		self.update_entry_list(entry_id)
		self.feed_list_view.update_feed_list(None, ['readinfo','icon'])
		self.update_disk_usage()
		
	def delete_media(self, media_id):
		"""Deletes specific media id"""
		self.db.delete_media(media_id)
		self.mediamanager.generate_playlist()
		self.db.set_media_viewed(media_id,True)
		self.update_disk_usage()
		
	def delete_feed_media(self, feed_id):
		"""Deletes media for an entire feed.  Calls generator _delete_media_generator"""
		gobject.idle_add(self._delete_media_generator(feed_id).next)
		
	def _delete_media_generator(self, feed_id):
		entrylist = self.db.get_entrylist(feed_id)
		if entrylist:
			for entry in entrylist:
				medialist = self.db.get_entry_media(entry[0])
				if medialist:
					for medium in medialist:
						if medium['download_status']==ptvDB.D_DOWNLOADED or medium['download_status']==ptvDB.D_RESUMABLE:
							#self.db_updater.queue_task(self.updater_thread_db.set_media_viewed, medium['media_id'])
							self.delete_media(medium['media_id'])
				yield True
			self.update_entry_list()
			self.mediamanager.generate_playlist()
			self.update_disk_usage()
		self.feed_list_view.update_feed_list(feed_id, ['readinfo','icon'])
		yield False
		
	def do_cancel_download(self, item):
		"""cancels a download and cleans up.  Right now there's redundancy because we call this twice
		   for files that are downloading -- once when we ask it to stop downloading, and again when the
		   callback tells the thread to stop working.  how to make this better?"""
		if self.mediamanager.has_downloader(item['media_id']):
			self.mediamanager.get_downloader(item['media_id']).stop()
		self.db.set_media_download_status(item['media_id'],ptvDB.D_NOT_DOWNLOADED)
		self.delete_media(item['media_id']) #marks as viewed
		self.main_window.update_download_progress()
		if self.exiting:
			self.feed_list_view.do_filter() #to remove active downloads from the list
			return
		try:
			feed_id = self.db.get_entry(item['entry_id'])['feed_id']
			self.update_entry_list(item['entry_id'])
			self.feed_list_view.update_feed_list(feed_id,['readinfo','icon'])
		except ptvDB.NoEntry:
			print "noentry error, don't worry about it"
			#print "downloads finished pop"
			#taken care of in callbacks?
			self.main_window.search_container.set_sensitive(False)
			self.feed_list_view.populate_feeds(self._done_populating, FeedList.DOWNLOADED)
			self.feed_list_view.resize_columns()
		self.feed_list_view.do_filter() #to remove active downloads from the list
		
	def do_pause_download(self, media_id):
		self.mediamanager.get_downloader(media_id).stop()
		self.db.set_media_download_status(media_id,ptvDB.D_RESUMABLE)
		self.db.set_media_viewed(media_id,0)
		self.db.set_entry_read(media_id,0)
		
	def download_finished(self, d):
		"""Process the data from a callback for a downloaded file"""
		self.update_disk_usage()
		if d.status==Downloader.FAILURE: 
			self.db.set_media_download_status(d.media['media_id'],ptvDB.D_ERROR) 
		elif d.status==Downloader.STOPPED:
			self.main_window.update_download_progress()
		elif d.status==Downloader.FINISHED or d.status==Downloader.FINISHED_AND_PLAY:
			if os.stat(d.media['file'])[6] < int(d.media['size']/2) and os.path.isfile(d.media['file']): #don't check dirs
				dic = {'reported_size': str(d.media['size']),
					 'actual_size': str(os.stat(d.media['file'])[6])}
				self.db.set_entry_read(d.media['entry_id'],False)
				self.db.set_media_viewed(d.media['media_id'],False)
				self.db.set_media_download_status(d.media['media_id'],ptvDB.D_DOWNLOADED)
			else:
				self.main_window.update_download_progress()
				if d.status==Downloader.FINISHED_AND_PLAY:
					self.db.set_entry_read(d.media['entry_id'],True)
					self.db.set_media_viewed(d.media['media_id'], True)
					self.feed_list_view.update_feed_list(None,['readinfo'])
					self.update_entry_list()
					self.player.play(d.media['file'])
				else:
					self.db.set_entry_read(d.media['entry_id'],False)
					self.db.set_media_viewed(d.media['media_id'],False)
				self.db.set_media_download_status(d.media['media_id'],ptvDB.D_DOWNLOADED)	
		if self.exiting:
			self.feed_list_view.do_filter() #to remove active downloads from the list
			return
		try:
			feed_id = self.db.get_entry(d.media['entry_id'])['feed_id']
			self.update_entry_list(d.media['entry_id'])
			self.feed_list_view.update_feed_list(feed_id,['readinfo','icon'])
		except ptvDB.NoEntry:
			print "noentry error"
			#print "downloads finished pop"
			#taken care of in callbacks?
			self.main_window.search_container.set_sensitive(False)
			self.feed_list_view.populate_feeds(self._done_populating, FeedList.DOWNLOADED)
			self.feed_list_view.resize_columns()
		except:
			print "some other error"
		self.feed_list_view.do_filter() #to remove active downloads from the list
			
	def rename_feed(self, feed_id, name):
		if len(name)==0:
			self.db.set_feed_name(feed_id, None) #gets the title the feed came with
		else:
			self.db.set_feed_name(feed_id, name)
		self.feed_list_view.update_feed_list(feed_id,['title'],{'title':name})
		self.feed_list_view.resize_columns()	
		#self.filter_combo_widget.set_active(FeedList.ALL)
		#self.filter_unread_checkbox.set_active(False)
		
	def set_auto_resume(self, client, *args, **kwargs):
		autoresume = client.get_bool('/apps/penguintv/auto_resume')
		self.window_preferences.set_auto_resume(autoresume)	
		self.autoresume = autoresume
		
	def set_poll_on_startup(self, client, *args, **kwargs):
		poll_on_startup = client.get_bool('/apps/penguintv/poll_on_startup')
		self.window_preferences.set_poll_on_startup(poll_on_startup)	
		self.poll_on_startup = poll_on_startup
		
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
		
	def set_app_window_layout(self, client, *args, **kwargs):
		layout = self.conf.get_string('/apps/penguintv/app_window_layout')
		self.main_window.layout=layout
		
	#def update_feed_list(self, feed_id=None):
	#	self.feed_list_view.update_feed_list(feed_id) #for now, just update this ONLY
		
	def update_entry_list(self, entry_id=None):
		self.entry_list_view.update_entry_list(entry_id)			
		
	def update_disk_usage(self):
		size = self.mediamanager.get_disk_usage()
		self.main_window.update_disk_usage(size)
		
	def _sensitize_search(self):
		self.gui_updater.queue_task(self.main_window._sensitize_search)
		
	def _done_populating(self):
		self.gui_updater.queue_task(self.done_populating)

	def _done_populating_dont_sensitize(self):
		self.gui_updater.queue_task(self.done_populating, False)
		
	def done_populating(self, sensitize=True):
		"""this is only called on startup I think"""
		self.main_window.display_status_message("")	
		self.main_window.update_progress_bar(-1,MainWindow.U_LOADING)
		if sensitize:
			self.main_window._sensitize_search()
		for filename in self.for_import:
			try:
				f = open(filename)
				self.import_opml(f)
			except Exception, e:
				print "not a valid file",e
		self.for_import = []
			
	
	def _progress_callback(self,d):
		"""Callback for downloads.  Not in main thread, so shouldn't generate gtk calls"""
		if self.exiting == 1:
			self.gui_updater.queue_task(self.do_cancel_download,d, None, True, 1)
			return 1 #returning one is what interrupts the download
		
		if d.media.has_key('size_adjustment'):
			if d.media['size_adjustment']==True:
				self.db_updater.queue_task(self.updater_thread_db.set_media_size,(d.media['media_id'], d.media['size']))
		if self.main_window.changing_layout == False:
			self.gui_updater.queue_task(self.entry_view.update_progress,d)
			self.gui_updater.queue_task(self.main_window.update_download_progress)

	def _finished_callback(self,downloader):
		self.gui_updater.queue_task(self.download_finished, downloader)
		
	def _polling_callback(self, args):
		if not self.exiting:
			feed_id,update_data,total = args
			self.gui_updater.queue_task(self.poll_update_progress,total)
			if len(update_data)>0: #else don't need to update, nothing changed
				if update_data.has_key('ioerror'):
					self.updater_thread_db.interrupt_poll_multiple()
					self.gui_updater.queue_task(self.poll_update_progress, (total, True, _("Trouble connecting to internet")))
				elif update_data['pollfail']==False:
					self.gui_updater.queue_task(self.feed_list_view.update_feed_list, (feed_id,['readinfo','icon','pollfail'],update_data))
					self.gui_updater.queue_task(self.entry_list_view.populate_if_selected, feed_id)
				else:
					self.gui_updater.queue_task(self.feed_list_view.update_feed_list, (feed_id,['pollfail'],update_data))
		
	def poll_update_progress(self, total=0, error = False, errmsg = ""):
		"""Updates progress for do_poll_multiple, and also displays the "done" message"""
		if error:
			#print "error, resetting"
			self.polled=0
			self.main_window.update_progress_bar(-1,MainWindow.U_POLL)
			self.main_window.display_status_message(errmsg,MainWindow.U_POLL)
			gobject.timeout_add(2000, self.main_window.display_status_message,"")
			return
		self.polled += 1
		#print "polled",self.polled,"items"
		if self.polled == total:
			#print "done, resetting"
			self.polled=0
			self.main_window.update_progress_bar(-1,MainWindow.U_POLL)
			self.main_window.display_status_message(_("Feeds Updated"),MainWindow.U_POLL)
			gobject.timeout_add(2000, self.main_window.display_status_message,"")
		else:
			d = { 'polled':self.polled,
				  'total':total}
			self.main_window.update_progress_bar(float(self.polled)/float(total),MainWindow.U_POLL)
			self.main_window.display_status_message(_("Polling Feeds... (%(polled)d/%(total)d)" % d),MainWindow.U_POLL)
			
	def _entry_image_download_callback(self, entry_id, html):
		self.gui_updater.queue_task(self.entry_view._images_loaded,(entry_id, html))
		
	def _socket_cb(self, data):
		"""right now just tries to import an opml file"""
		#goddamn hack: if it's insensitive, _done_pop will get called so use that
		#method
		if not self.main_window.search_container.get_property('sensitive'):
			self.for_import.append(data)
		else:
			try:
				f = open(data)
				self.import_opml(f)
			except Exception, e:
				print "not a valid file: ",e
				
			
	class DBUpdaterThread(PyLucene.PythonThread):
		def __init__(self, polling_callback=None):
			PyLucene.PythonThread.__init__(self)
			self.__isDying = False
			self.db = None
			self.updater = UpdateTasksManager.UpdateTasksManager(UpdateTasksManager.MANUAL, "db updater")
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
				while self.updater.updater_gen().next():
					pass
				time.sleep(self.threadSleepTime)
						
		def get_db(self):
			return self.db
			
		def get_updater(self):
			return self.updater
	
		def goAway(self):
	
			""" Exit the run loop next time through."""
	        
			self.__isDying = True
		
def main():
	gnome.init("PenguinTV", utils.VERSION)
	app = PenguinTVApp()    # Instancing of the GUI
	if not app.socket.is_server:
		sys.exit(0)
	app.main_window.Show() 
	gobject.idle_add(app.post_show_init) #lets window appear first)
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
	if not app.socket.is_server:
		sys.exit(0)
	app.main_window.Show() 
	gobject.idle_add(app.post_show_init) #lets window appear first)
	gtk.threads_init()
#	import profile
#	profile.run('gtk.main()', 'pengprof')
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
