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

import AddFeedDialog
import PreferencesDialog
import MainWindow, FeedList, EntryList, EntryView

CANCEL=0
PAUSE=1

GUI = UpdateTasksManager.GUI
DB = UpdateTasksManager.DB

REFRESH_SPECIFIED=0
REFRESH_AUTO=1

AUTO_REFRESH_FREQUENCY=5*60*1000

superglobal=utils.SuperGlobal()
superglobal.download_status={}

class PenguinTVApp:

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
		self.db = ptvDB.ptvDB(self._polling_callback)
		self.firstrun = self.db.maybe_initialize_db()
		self.db.clean_media_status()
		if self.db.cache_dirty: #assume index is bad as well
			self.db.searcher.Do_Index_Threaded()
		self.mediamanager = MediaManager.MediaManager(self._progress_callback, self._finished_callback)
		self.conf = gconf.client_get_default()
		self.player = Player.Player()
		self._updater_db = None
		self.download_task_ops=[]
		self.poll_tasks=0 #Used for updating the polling progress bar
		self.polled=0     # ditto
		self.polling_taskid=0 #the taskid we can use to waitfor a polling operation
		self.polling_frequency=12*60*60*1000
		self.bt_settings = {}
		self.exiting=0
		self.auto_download = False
		self.auto_download_limiter = False
		self.auto_download_limit=1024*1024
		self.pausing_all_downloads = False
		self.saved_filter = FeedList.ALL
		self.saved_search = ""
		self.showing_search = False
		
		window_layout = self.conf.get_string('/apps/penguintv/app_window_layout')
		if window_layout is None:
			window_layout='standard'
		
		self.main_window = MainWindow.MainWindow(self,self.glade_prefix) 
		self.main_window.layout=window_layout
			
	def post_show_init(self):
		"""After we have Show()n the main window, set up some more stuff"""
		self.updater = UpdateTasksManager.UpdateTasksManager()
		self._db_updater = self.DBUpdaterThread(self.updater, self._polling_callback)
		self._db_updater.start()
		self.updater_thread_db = None
		while self.updater_thread_db==None:
			#this may race, so be patient 
			self.updater_thread_db = self._db_updater.get_db()
			time.sleep(.1)

		#WINDOWS
		self.window_add_feed = AddFeedDialog.AddFeedDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_add_feed",'penguintv'),self) #MAGIC
		self.window_add_feed.hide()
		self.window_preferences = PreferencesDialog.PreferencesDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_preferences",'penguintv'),self) #MAGIC
		self.window_preferences.hide()
		self.layout_changing_dialog = gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_changing_layout",'penguintv').get_widget("window_changing_layout")
		self.layout_changing_dialog.connect("delete-event",self.on_window_changing_layout_delete_event)
		self.layout_changing_dialog.hide()
					
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
		gobject.timeout_add(500, self._gui_updater)
		gobject.timeout_add(10000, self.progress_checker)
		self.main_window.search_container.set_sensitive(False)
		self.feed_list_view.populate_feeds()
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
			#task_id = self.updater.queue_task(DB, self.updater_thread_db.import_OPML,f)
			#self.updater.queue_task(GUI, self.feed_list_view.populate_feeds,None, task_id)
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
			if self.pausing_all_downloads: #bail
				yield False
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
		gtk.main_quit()
		
	def write_feed_cache(self):
		self.db.set_feed_cache(self.feed_list_view.get_feed_cache())
		
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
		if arguments & ptvDB.A_ALL_FEEDS:
			#only do the progress bar for all feeds, because if we are on auto we don't know 
			#how many polls there are
			self.poll_tasks = len(self.db.get_feedlist())
			self.main_window.update_progress_bar(0,MainWindow.U_POLL)
		self.main_window.display_status_message(_("Polling Feeds..."), MainWindow.U_POLL)			
		task_id = self.updater.queue_task(DB, self.updater_thread_db.poll_multiple, arguments)
		if arguments & ptvDB.A_ALL_FEEDS==0:
			self.updater.queue_task(GUI, self.main_window.display_status_message,_("Feeds Updated"), task_id, False)
			#insane: queueing a timeout
			self.updater.queue_task(GUI, gobject.timeout_add, (2000, self.main_window.display_status_message, ""), task_id, False)
		self.polling_taskid = self.updater.queue_task(GUI, self.update_disk_usage, None, task_id, False) #because this is also waiting
		if self.auto_download == True:
			self.polling_taskid = self.updater.queue_task(GUI, self.auto_download_unviewed, None, task_id)
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
			self.mediamanager.download(item)
			media = self.db.get_media(item)
			self.db.set_media_viewed(item,False)
			self.feed_list_view.update_feed_list(None,['icon'])
			self.update_entry_list()
		elif action=="resume" or action=="tryresume":
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
			self.mediamanager.download(item, True)
			self.db.set_media_viewed(item,False)
			self.feed_list_view.update_feed_list(None,['icon'])
			self.update_entry_list()
		elif action=="queue":
			print parsed_url		
		elif action=="stop":
			self.download_task_ops.append((CANCEL,item))
			newitem={}
			newitem['media_id']=item
			newitem['entry_id']=self.db.get_entryid_for_media(newitem['media_id'])
			self.do_cancel_download(newitem)
		elif action=="pause":
			self.download_task_ops.append((PAUSE, item))
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
			#self.db.set_media_viewed(item,False)
			#self.feed_list_view.update_feed_list(['readinfo'])
			#self.update_entry_list()
			
	def download_entry(self, entry):
		self.mediamanager.download_entry(entry)
		self.update_entry_list(entry)
		self.feed_list_view.update_feed_list(None,['icon'])

	def download_unviewed(self):
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
				task_id = self.updater.queue_task(DB, self.updater_thread_db.export_OPML, f)
				self.updater.queue_task(GUI,self.main_window.display_status_message, "", task_id)
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
			#selected = self.feed_list_view.get_selected()
			#select entries and get all the media ids, and tell them all to cancel
			#in case they are downloading
			try:
				for entry_id,title,date,new in self.db.get_entrylist(feed):
					try:
						for medium in self.db.get_entry_media(entry_id):
							#hack because we don't really know about downloads, and we can't just cancel them all
							#because they might add the feed again, and then the cancels would still be hanging around
							if superglobal.download_status.has_key(medium['media_id']):
								self.download_task_ops.append((CANCEL,medium['media_id']))
					except: #keep trying
						pass
			except:
				pass
			self.db.delete_feed(feed)
			self.feed_list_view.remove_feed(feed)
			self.update_disk_usage()
			self.feed_list_view.resize_columns()
			self.entry_list_view.clear_entries()
			self.main_window.update_filters()
	
	def poll_feeds(self):
		args = ptvDB.A_ALL_FEEDS
		if self.feed_refresh_method==REFRESH_AUTO:
			args = args | ptvDB.A_AUTOTUNE
		self.do_poll_multiple(None, args)
			
	def import_opml(self, f):
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
			feed_count=-1.0
			i=1.0
			for feed in gen:
				if feed_count == -1:
					#first yield is the total count
					feed_count = feed
					continue
				if feed==-1: #either EOL or error on insert
					continue
				if self.exiting:
					dialog.hide()
					del dialog
					yield False
				#self.feed_list_view.add_feed(feed)
				newfeeds.append(feed)
				bar.set_fraction(i/feed_count)
				i+=1.0
				yield True
			self.feed_list_view.clear_list()
			self.main_window.search_container.set_sensitive(False)
			self.feed_list_view.populate_feeds()
			self.main_window.update_filters()
			saved_auto = False
			self.main_window.display_status_message("")
			#shut down auto-downloading for now (need to wait until feeds are marked)
			if self.auto_download:
				saved_auto = True
				self.auto_download = False
			self.do_poll_multiple(None, ptvDB.A_ALL_FEEDS)
			task_id = self.updater.queue_task(GUI, self._first_poll_marking_list, (newfeeds,saved_auto), self.polling_taskid) 
			dialog.hide()
			del dialog
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
		task_id = self.updater.queue_task(DB,self.updater_thread_db.poll_feed,(feed,ptvDB.A_IGNORE_ETAG+ptvDB.A_DO_REINDEX))
		self.updater.queue_task(GUI,self.feed_list_view.update_feed_list,(feed,['readinfo','icon']), task_id, False)
		self.updater.queue_task(GUI,self.entry_list_view.update_entry_list,None, task_id, False)
		task_id2 = self.updater.queue_task(GUI, self.main_window.display_status_message,_("Feed Updated"), task_id)
		self.updater.queue_task(GUI, gobject.timeout_add, (2000, self.main_window.display_status_message, ""), task_id2)
		#self.updater.queue_task(GUI,self.feed_list_view.set_selected,selected, task_id)
		
	def search(self, query):
		query = query.replace("!","")
		self.showing_search = True
		
		try:
			result = self.db.search(query)
		except Exception, e:
			print "error with that search term", e
			result=([],[])
		try:
			#print result
			self.entry_list_view.show_search_results(result[1], query)
			self.feed_list_view.show_search_results(result[0])
		except ptvDB.BadSearchResults, e:
			print e
			self.db.reindex(result[0], [i[0] for i in result[1]])
			self.search(query)
			return
		self.main_window.filter_unread_checkbox.set_sensitive(False)
		
	def unshow_search(self):
		self.showing_search = False
		self.entry_list_view.unshow_search()
		self.feed_list_view.unshow_search()
		self.entry_view.display_item()
		self.main_window.search_entry.set_text("")
		self.main_window.filter_unread_checkbox.set_sensitive(True)
		
	def manual_search(self, query):
		self.saved_search = query #even if it's blank
		if len(query)==0:
			self.unshow_search()
			self.saved_search = ""
			self.main_window.filter_combo_widget.set_active(self.saved_filter)
			return
			
		self.search(query)
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
			self.search(self.saved_search)
			self.main_window.search_entry.set_text(self.saved_search)
		else:
			if tag_type != ptvDB.T_SEARCH:
				if self.showing_search:
					self.unshow_search()
				self.main_window.feed_list_view.set_filter(filter_id, current_filter)
			else:
				query = self.db.get_search_tag(current_filter)
				self.unshow_search()
				self.search(query)
				
	def show_downloads(self):
		self.mediamanager.generate_playlist()
		self.mediamanager.show_downloads()
		
	def stop_downloads(self):
		"""stops downloading everything -- really just pauses them.  Just sets a flag, really.
		progress_callback does the actual work"""
		if self.pausing_all_downloads == False:
			self.pausing_all_downloads = True
			download_stopper_thread = threading.Thread(None, self.mediamanager.pause_all_downloads)
			download_stopper_thread.start() #this isn't gonna block any more!
			self.db.pause_all_downloads() #blocks, but prevents race conditions
			#print "stop download pop"
			if not self.exiting:
				self.main_window.search_container.set_sensitive(False)
				self.feed_list_view.populate_feeds(FeedList.ACTIVE) #right now this is taking the longest
				self.feed_list_view.populate_feeds(FeedList.DOWNLOADED) #right now this is taking the longest
				self.entry_list_view.update_entry_list()
				
	#def stop_downloads_toggled(self, stopped):
	#	if stopped:
	#		self.stop_downloads() #sets pausing_all_downloads to True
	#	else:
	#		self.pausing_all_downloads = False
	#		self.resume_resumable()
			
	def change_layout(self, layout):
		if self.main_window.layout != layout:
			self.layout_changing_dialog.show_all()
			self.feed_list_view.interrupt()
			while gtk.events_pending(): #make sure everything gets shown
				gtk.main_iteration()
			self.main_window.activate_layout(layout)
			self.feed_list_view = self.main_window.feed_list_view
			self.entry_list_view = self.main_window.entry_list_view
			self.entry_view = self.main_window.entry_view
			self.main_window.changing_layout = False
			self.layout_changing_dialog.hide()

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
			#taskid = self.updater.queue_task(GUI, self.main_window.populate_and_select, feed_id)
			taskid = self.updater.queue_task(GUI, self.feed_list_view.add_feed, feed_id)
			self.updater.queue_task(GUI, self.main_window.select_feed, feed_id, taskid, False)
			taskid2=self.updater.queue_task(DB, self.updater_thread_db.poll_feed_trap_errors, (feed_id,self._add_feed_callback), taskid)
			
		except ptvDB.FeedAlreadyExists, e:
			self.updater.queue_task(GUI, self.main_window.select_feed, e.feed)
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
		
	def _add_feed_callback(self, feed, success):
		if success:
			self.updater.queue_task(GUI, self._add_feed_success, feed['feed_id'])
			self.updater.queue_task(GUI, self.first_poll_marking, feed['feed_id'])
			self.updater.queue_task(GUI, self.entry_list_view.populate_entries, feed['feed_id'])
			self.updater.queue_task(GUI, self.feed_list_view.update_feed_list, (feed['feed_id'],['readinfo','icon','title']))
			if self.auto_download:
				self.updater.queue_task(GUI, self.auto_download_unviewed)
			self.updater.queue_task(GUI, gobject.idle_add, self.entry_list_view.auto_pane) #oh yeah, queue an idler
		else:
			self.updater.queue_task(GUI, self.feed_list_view.update_feed_list, (feed['feed_id'],['icon','pollfail']))
			self.updater.queue_task(GUI, self._add_feed_error, feed['feed_id'])
	
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
					#self.updater.queue_task(DB, self.updater_thread_db.set_media_viewed, medium['media_id'])
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
							#self.updater.queue_task(DB, self.updater_thread_db.set_media_viewed, medium['media_id'])
							self.delete_media(medium['media_id'])
				yield True
			self.update_entry_list()
			self.mediamanager.generate_playlist()
			self.update_disk_usage()
		self.feed_list_view.update_feed_list(feed_id, ['readinfo','icon'])
		yield False
		
	def do_cancel_download(self, data):
		"""cancels a download and cleans up.  Right now there's redundancy because we call this twice
		   for files that are downloading -- once when we ask it to stop downloading, and again when the
		   callback tells the thread to stop working.  how to make this better?"""
		self.db.set_media_download_status(data['media_id'],ptvDB.D_NOT_DOWNLOADED)
		self.delete_media(data['media_id']) #marks as viewed
		try:
			del superglobal.download_status[data['media_id']]
		except:
			pass
		#self.main_window.update_download_progress(self.mediamanager.get_download_count())
		self.main_window.update_download_progress()
		if self.exiting:
			self.feed_list_view.do_filter() #to remove active downloads from the list
			return
		try:
			feed_id = self.db.get_entry(data['entry_id'])['feed_id']
			self.update_entry_list(data['entry_id'])
			self.feed_list_view.update_feed_list(feed_id,['readinfo','icon'])
		except ptvDB.NoEntry:
			print "noentry error, don't worry about it"
			#print "downloads finished pop"
			#taken care of in callbacks?
			self.main_window.search_container.set_sensitive(False)
			self.feed_list_view.populate_feeds(FeedList.DOWNLOADED)
			self.feed_list_view.resize_columns()
		self.feed_list_view.do_filter() #to remove active downloads from the list
		
	def do_pause_download(self, data):
		self.db.set_media_download_status(data['media_id'],ptvDB.D_RESUMABLE)
		self.db.set_media_viewed(data['media_id'],0)
		self.db.set_entry_read(data['entry_id'],0)
		
	def download_finished(self, media, status, message):
		"""Process the data from a callback for a downloaded file"""
		self.update_disk_usage()
		if status==MediaManager.FAILURE: 
			self.db.set_media_download_status(media['media_id'],ptvDB.D_ERROR) 
			superglobal.download_status[media['media_id']]=(DOWNLOAD_ERROR,media['errormsg'],0)
		elif status==MediaManager.STOPPED:
			try:
				del superglobal.download_status[media['media_id']] #clear progress information
				self.main_window.update_download_progress() #should clear things out
			except:
				pass
				#print "tried to delete: "+str(media['media_id'])
				#print superglobal.download_status
				#print "error deleting progress info 2"
		elif status==MediaManager.FINISHED or status==MediaManager.FINISHED_AND_PLAY:
			if os.stat(media['file'])[6] < int(media['size']/2) and os.path.isfile(media['file']): #don't check dirs
				d = {'reported_size': str(media['size']),
					 'actual_size': str(os.stat(media['file'])[6])}
				superglobal.download_status[media['media_id']]=(DOWNLOAD_WARNING,_("WARNING: Expected %(reported_size)s bytes but the file is %(actual_size)s bytes.") % d,0)
				#self.delete_media(media['media_id'])
				self.db.set_entry_read(media['entry_id'],False)
				self.db.set_media_viewed(media['media_id'],False)
				self.db.set_media_download_status(media['media_id'],ptvDB.D_DOWNLOADED)
			else:
				try:
					del superglobal.download_status[media['media_id']] #clear progress information
					self.main_window.update_download_progress() #should clear things out
				except:
					#print "error deleting progress info"
					pass #no big whoop if it fails
				if status==MediaManager.FINISHED_AND_PLAY:
					self.db.set_entry_read(media['entry_id'],True)
					self.db.set_media_viewed(media['media_id'], True)
					self.feed_list_view.update_feed_list(None,['readinfo'])
					self.update_entry_list()
					self.player.play(media['file'])
				else:
					self.db.set_entry_read(media['entry_id'],False)
					self.db.set_media_viewed(media['media_id'],False)
				self.db.set_media_download_status(media['media_id'],ptvDB.D_DOWNLOADED)	
		if self.exiting:
			self.feed_list_view.do_filter() #to remove active downloads from the list
			return
		try:
			feed_id = self.db.get_entry(media['entry_id'])['feed_id']
			self.update_entry_list(media['entry_id'])
			self.feed_list_view.update_feed_list(feed_id,['readinfo','icon'])
		except ptvDB.NoEntry:
			print "noentry error"
			#print "downloads finished pop"
			#taken care of in callbacks?
			self.main_window.search_container.set_sensitive(False)
			self.feed_list_view.populate_feeds(FeedList.DOWNLOADED)
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
		
	def _done_populating(self):
		self.main_window.search_container.set_sensitive(True)

	def _progress_callback(self,data):
		"""Callback for downloads.  Not in main thread, so shouldn't generate gtk calls"""
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
		superglobal.download_status[data[0]['media_id']]=(DOWNLOAD_PROGRESS,data[1],data[0]['size'])
		if self.main_window.changing_layout == False:
			self.updater.queue_task(GUI,self.entry_view.update_progress,data)
			self.updater.queue_task(GUI,self.main_window.update_download_progress)

	def _finished_callback(self,data):
		#print "finished callback"
		#reset pausing_all_downloads
		if self.pausing_all_downloads:
			if self.mediamanager.get_download_count() <= 1: #last one!
				self.pausing_all_downloads = False #we're done
		self.mediamanager.update_playlist(data[0])
		self.updater.queue_task(GUI,self.download_finished, data)
		
	def _polling_callback(self, args):
		if not self.exiting:
			feed_id,update_data = args
			self.updater.queue_task(GUI, self.poll_update_progress)
			if update_data['pollfail']==False:
				self.updater.queue_task(GUI, self.feed_list_view.update_feed_list, (feed_id,['readinfo','icon','pollfail'],update_data))
				self.updater.queue_task(GUI, self.entry_list_view.populate_if_selected, feed_id)
			else:
				self.updater.queue_task(GUI, self.feed_list_view.update_feed_list, (feed_id,['pollfail'],update_data))
		
	def poll_update_progress(self):
		"""Updates progress for do_poll_multiple, and also displays the "done" message"""
		if self.poll_tasks > 0:
			self.polled += 1
			if self.polled == self.poll_tasks:
				self.poll_tasks=0 #this is where we reset the poll tasks
				self.polled=0
				self.main_window.update_progress_bar(-1,MainWindow.U_POLL)
				self.main_window.display_status_message(_("Feeds Updated"),MainWindow.U_POLL)
				gobject.timeout_add(2000, self.main_window.display_status_message,"")
			else:
				d = { 'polled':self.polled,
					  'total':self.poll_tasks}
				self.main_window.update_progress_bar(float(self.polled)/float(self.poll_tasks),MainWindow.U_POLL)
				self.main_window.display_status_message(_("Polling Feeds... (%(polled)d/%(total)d)" % d),MainWindow.U_POLL)
	
	def progress_checker(self):
		"""Every 10 seconds make sure the download_status matches the mediamanager"""
		val1 = len([p for p in superglobal.download_status.keys() if superglobal.download_status[p][0]==DOWNLOAD_PROGRESS])
		val2 = self.mediamanager.get_download_count()
		if len([p for p in superglobal.download_status.keys() if superglobal.download_status[p][0]==DOWNLOAD_PROGRESS]) > self.mediamanager.get_download_count():
			print "There are "+str(val2)+ " files downloading, but download_status records "+str(val1)+"  Resetting download_status"
			print superglobal.download_status
			print self.mediamanager.get_download_count()
			superglobal.download_status = {}
			self.main_window.update_progress_bar(-1) #reset
			self.main_window.display_status_message("")
			#blow them all away, they will be regenerated
		return True
		
	def _entry_image_download_callback(self, entry_id, html):
		self.updater.queue_task(GUI, self.entry_view._images_loaded,(entry_id, html))
			
	class DBUpdaterThread(PyLucene.PythonThread):
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
								#print e
								pass
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
							pass
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
		"""Called very often.  Only perform three tasks and then return to prevent long-term
		   blocking"""
		if self.updater.task_count(GUI)==0:
			return True
		skipped=0
		performed=0
		current_task_count = self.updater.task_count(GUI)
		while current_task_count > 0 and performed<10 and skipped != current_task_count:
			var = self.updater.peek_task(GUI, skipped)
			func, args, task_id, waitfor, clear_completed =  var
			if waitfor:
				if self.updater.is_completed(waitfor): #don't pop if false
					try:
						###print var
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
					#print "skipping "+str(var)
					skipped = skipped+1
			else:
				try:
					###print var
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
		return True
				

def main():
	gnome.init("PenguinTV", utils.VERSION)
	app = PenguinTVApp()    # Instancing of the GUI
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
	app.main_window.Show() 
	gobject.idle_add(app.post_show_init) #lets window appear first)
	#app.post_show_init()
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
