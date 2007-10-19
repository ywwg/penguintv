import sys, os, re
import glob
import logging
import random
import traceback

import gtk
import gobject
import pango

import penguintv
import ptvDB
import utils
import IconManager
import MainWindow



NONE=-1 #unused, needs a value
ALL=0
DOWNLOADED=1
NOTIFY=2
SEARCH=3
BUILTIN_TAGS=[_("All Feeds"),_("Downloaded Media"), _("Notifying Feeds"), _("Search Results")]

TITLE=0
MARKUPTITLE=1
FEEDID=2
STOCKID=3
READINFO=4
PIXBUF=5
DETAILS_LOADED=6
UNREAD=7
TOTAL=8
FLAG=9
VISIBLE=10
POLLFAIL=11
FIRSTENTRYTITLE=12

#STATES
S_DEFAULT          = 0
S_SEARCH           = 1 
S_LOADING_FEEDS    = 2

MAX_WIDTH  = 48
MAX_HEIGHT = 48
MIN_SIZE   = 24

class FeedList(gobject.GObject):

	__gsignals__ = {
        'link-activated': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
		'feed-selected': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT])),
		'no-feed-selected': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           []),
		'state-change': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT]))
	}
                           
	def __init__(self, widget_tree, app, db, fancy=False):
		gobject.GObject.__init__(self)
		self._app = app
		self._db = db
		self._icon_manager = IconManager.IconManager(self._db.home)
		self._scrolled_window = widget_tree.get_widget('feed_scrolled_window')
		self._va = self._scrolled_window.get_vadjustment()
		self._widget = widget_tree.get_widget('feedlistview')
		self._entry_list_widget = widget_tree.get_widget('entrylistview')
		
		self._feedlist = gtk.ListStore(str,            #title
									   str,            #markup title
									   int,            #feed_id
									   str,            #stockid
									   str,            #readinfo
									   gtk.gdk.Pixbuf, #pixbuf 
									   bool,           #details loaded
									   int,            #unread
									   int,            #total
									   int,            #flag
									   bool,           #visible
									   bool,           #pollfail
									   str)            #first entry title
		self._last_selected=None
		self._last_feed=None
		self.filter_setting=ALL
		self.filter_name = _("All Feeds")
		self._selecting_misfiltered=False
		self._filter_unread = False
		self._cancel_load = [False,False] #loading feeds, loading details
		self._loading_details = False
		self._state = S_DEFAULT
		self._fancy = fancy
		self.__widget_width = 0
		
		#build list view
		
		self._feed_filter = self._feedlist.filter_new()
		self._feed_filter.set_visible_column(VISIBLE)
		self._widget.set_model(self._feed_filter)
		
		# Icon Column
		self._icon_renderer = gtk.CellRendererPixbuf()
		self._icon_column = gtk.TreeViewColumn(_('Icon'))
		self._icon_column.pack_start(self._icon_renderer, False)
		self._icon_column.set_attributes(self._icon_renderer, stock_id=STOCKID)
		self._icon_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		self._icon_column.set_min_width(32)
		self._widget.append_column(self._icon_column)
		
		# Feed Column
		renderer = gtk.CellRendererText()
		renderer.set_property("ellipsize", pango.ELLIPSIZE_END)
		self._feed_column = gtk.TreeViewColumn(_('Feeds'))
		self._feed_column.pack_start(renderer, True)
		self._feed_column.set_attributes(renderer, markup=MARKUPTITLE)
		self._feed_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		self._feed_column.set_resizable(True)
		self._feed_column.set_expand(True)
		self._widget.append_column(self._feed_column)
		
		# Articles column
		self._articles_renderer = gtk.CellRendererText()
		self._articles_column = gtk.TreeViewColumn(_(''))
		self._articles_column.set_resizable(False)
		self._articles_column.pack_start(self._articles_renderer, False)
		self._articles_column.set_attributes(self._articles_renderer, markup=READINFO)		
		self._articles_column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
		self._articles_column.set_expand(True)
		self._widget.append_column(self._articles_column)
		
		# Image Column
		feed_image_renderer = gtk.CellRendererPixbuf()
		self._image_column = gtk.TreeViewColumn(_('Image'))
		self._image_column.pack_start(feed_image_renderer, False)
		self._image_column.set_attributes(feed_image_renderer, pixbuf=PIXBUF)
		self._image_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		self._image_column.set_min_width(MAX_WIDTH)
		self._image_column.set_max_width(MAX_WIDTH)
		self._articles_column.set_expand(False)
		self._widget.append_column(self._image_column)
		
		self.resize_columns()
		
		#signals are MANUAL ONLY
		self._widget.get_selection().connect("changed", self._item_selection_changed)
		self._widget.connect("row-activated", self.on_row_activated)
		#applies to mousewheel ONLY, stop trying this (leaving for future note)
		#self._scrolled_window.connect("scroll-event", self.on_feedlistview_scroll_event)
		
		self._handlers = []
		h_id = self._app.connect('feed-polled', self.__feed_polled_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('feed-added', self.__feed_added_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('feed-removed', self.__feed_removed_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('entry-updated', self.__entry_updated_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('tags-changed', self.__tags_changed_cb)
		self._handlers.append((self._app.disconnect, h_id))
		
		#init style
		if self._fancy:
			#if utils.RUNNING_SUGAR:
			#	self._icon_renderer.set_property('stock-size',gtk.ICON_SIZE_SMALL_TOOLBAR)
			#else:
			self._icon_renderer.set_property('stock-size',gtk.ICON_SIZE_LARGE_TOOLBAR)
			self._widget.set_property('rules-hint', True)
			
	def finalize(self):
		for disconnector, h_id in self._handlers:
			disconnector(h_id)
			
	def __feed_polled_cb(self, app, feed_id, update_data):
		if update_data.has_key('no_changes'):
			if update_data['no_changes']:
				self.update_feed_list(feed_id, ['icon'], update_data)
				return
		self.update_feed_list(feed_id, ['readinfo','icon','title','image'], update_data)
		
	def __feed_added_cb(self, app, feed_id, success):
		self.update_feed_list(feed_id, ['title'])
			
	def __feed_removed_cb(self, app, feed_id):
		self.remove_feed(feed_id)
		self.resize_columns()
		
	def __tags_changed_cb(self, app, a):
		self.filter_all(False)
	
	def __entry_updated_cb(self, app, entry_id, feed_id):
		self.update_feed_list(feed_id,['readinfo','icon'])	
		
	def grab_focus(self):
		self._widget.grab_focus()
			
	def populate_feeds(self,callback=None, subset=ALL):
		"""With 100 feeds, this is starting to get slow (2-3 seconds).  Speed helped with cache"""
		#DON'T gtk.iteration in this func! Causes endless loops!
		if len(self._feedlist)==0:
			#first fill out rough feedlist
			db_feedlist = self._db.get_feedlist()
			blank_pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, 10,10)
			blank_pixbuf.fill(0xffffff00)			
			for feed_id,title,url in db_feedlist:
				if self._fancy:
					title_m = title+"\n"
				else:
					title_m = title
				self._feedlist.append([title, 
									   title_m, 
									   feed_id, 
									   'gtk-stock-blank', 
									   "", 
									   blank_pixbuf, 
									   False,
									   0, 
									   0, 
									   0, 
									   False, 
									   False,
									   ""]) #assume invisible
		self.filter_all(False)	
		gobject.idle_add(self._update_feeds_generator(callback,subset).next)
		#self._update_feeds_generator(subset)
		return False #in case this was called by the timeout below
		
	def _update_feeds_generator(self, callback=None, subset=ALL):
		"""A generator that updates the feed list.  Called from populate_feeds"""	
		#gtk.gdk.threads_enter()
		selection = self._widget.get_selection()
		selected = self.get_selected()
		feed_cache = self._db.get_feed_cache()
		db_feedlist = self._db.get_feedlist()
		
		i=-1
	
		blank_pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, 10,10)
		blank_pixbuf.fill(0xffffff00)
		
		# While populating, allow articles column to autosize
		self._articles_column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
		
		for feed_id,title,url in db_feedlist:
			#gtk.gdk.threads_enter()
			if self._cancel_load[0]:
				break
			i=i+1
			
			if subset==DOWNLOADED:
				flag = self._feedlist[i][FLAG]
				if flag & ptvDB.F_DOWNLOADED==0 and flag & ptvDB.F_PAUSED==0:
					continue
			if feed_cache is not None:
				cached     = feed_cache[i]
				unviewed   = cached[2]
				flag       = cached[1]
				pollfail   = cached[4]
				entry_count= cached[3]
			else:
				feed_info   = self._db.get_feed_verbose(feed_id)
				unviewed    = feed_info['unread_count']
				flag        = feed_info['important_flag']
				pollfail    = feed_info['poll_fail']
				entry_count = feed_info['entry_count']
			if entry_count==0 or entry_count is None: #this is a good indication that the cache is bad
				feed_info   = self._db.get_feed_verbose(feed_id)
				unviewed    = feed_info['unread_count']
				flag        = feed_info['important_flag']
				pollfail    = feed_info['poll_fail']
				entry_count = feed_info['entry_count']
				
			if self._feedlist[i][FLAG]!=0:
				flag = self._feedlist[i][FLAG] #don't overwrite flag (race condition)
				
			if unviewed == 0 and flag & ptvDB.F_UNVIEWED:
				print "WARNING: zero unread articles but flag says there should be some"
				flag -= ptvDB.F_UNVIEWED
				
			visible = self._feedlist[i][VISIBLE]
			
			if self._fancy:
				if visible:
					try: m_first_entry_title = self._db.get_entrylist(feed_id)[0][1]
					except: m_first_entry_title = ""
					m_details_loaded = True
				else:
					m_first_entry_title = ""
					m_pixbuf = blank_pixbuf
					m_details_loaded = False
				m_pixbuf = self._get_pixbuf(feed_id)
				model, iter = selection.get_selected()
				try: sel = model[iter][FEEDID]
				except: sel = -1
				m_title = self._get_fancy_markedup_title(title,m_first_entry_title,unviewed,entry_count,flag, feed_id == sel) 
				m_readinfo = self._get_markedup_title("(%d/%d)\n" % (unviewed,entry_count), flag)
			else:
				m_title = self._get_markedup_title(title,flag) 
				m_readinfo = self._get_markedup_title("(%d/%d)" % (unviewed,entry_count), flag)
				m_pixbuf = blank_pixbuf
				m_first_entry_title = ""
				m_details_loaded = False
				
			icon = self._get_icon(flag)	
			
			if pollfail:
 				if icon=='gtk-harddisk' or icon=='gnome-stock-blank':
 					icon='gtk-dialog-error'
			
			self._feedlist[i] = [title, 
								 m_title, 
								 feed_id, 
								 icon, 
								 m_readinfo, 
								 m_pixbuf, 
								 m_details_loaded, 
								 unviewed, 
								 entry_count, 
								 flag, 
								 visible, 
								 pollfail, 
								 m_first_entry_title]
#			try:
				#if i % (len(db_feedlist)/10) == 0:
				#	self.filter_all()
			self._filter_one(self._feedlist[i])

			self._app.main_window.update_progress_bar(float(i)/len(db_feedlist),MainWindow.U_LOADING)
#			except:
#				pass
			#gtk.gdk.threads_leave()
			yield True
			
		# Once we are done populating, set size to fixed, otherwise we get
		# a nasty flicker when we click on feeds
		self._reset_articles_column()
		
		
		if not self._cancel_load[0]:
			#self.filter_all()
			if self._fancy:
				gobject.idle_add(self._load_visible_details().next)
			if selected:
				#gtk.gdk.threads_enter()
				self.set_selected(selected)
				#gtk.gdk.threads_leave()
			if callback is not None:
				try: callback()
				except: pass
		else:
			self._cancel_load[0] = False
		yield False
		
	def resize_columns(self):
		self._reset_articles_column()

		#self._widget.columns_autosize()
		
	def _reset_articles_column(self, allow_recur=True):
		#temporarily allow articles column to size itself, then set it
		#to fixed again to avoid flicker.
		
		self._articles_column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
		self._feed_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		self._feed_column.set_expand(False)
		self._feed_column.set_min_width(20)
		self._feed_column.set_max_width(20)
		
		self._widget.columns_autosize()

		self._articles_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		self._articles_column.set_min_width(self._articles_column.get_width())
		self._feed_column.set_expand(True)
		self._feed_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		
	def update_feed_list(self, feed_id=None, update_what=None, update_data=None, recur_ok=True):  #returns True if this is the already-displayed feed
		"""updates the feed list.  Right now uses db to get flags, entrylist (for unread count), pollfail
	
		We should just get the flag, unread count, and poll fail, and then figure out:
		   icon, markup, and numbers
		   
		update_data would be a dic with unreadcount, flag list, and pollfail
		
		update_what is a bunch of strings saying what we want to update.  it will go to the
		db for info unless the value is already in update_data"""
		
		if feed_id is None:
			if self._last_feed is None:
				return
			feed_id = self._feedlist[self._last_feed][FEEDID]
			
		if update_what is None:
			update_what = ['readinfo','icon','title']
		if update_data is None:
			update_data = {}
			
		if 'readinfo' in update_what and 'title' not in update_what:
			update_what.append('title') #need this too
		
		try:
			feed = self._feedlist[self.find_index_of_item(feed_id)]
		except:
			logging.warning("tried to update feed not in list: %i, %s, %s, %s" % (feed_id, str(update_what), str(update_data), str(recur_ok)))
			return
			
		need_filter = False #some updates will require refiltering. 
		
		if 'title' in update_what or 'icon' in update_what:
			if not update_data.has_key('flag_list'):
				update_data['flag_list'] = self._db.get_entry_flags(feed_id)
						
			updated=0
			unviewed=0
			downloaded=0
		 	
			for flag in update_data['flag_list']:
				if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
					unviewed=unviewed+1
				if flag & ptvDB.F_DOWNLOADED or flag & ptvDB.F_PAUSED:
					downloaded=1				
			flag = self._pick_important_flag(feed_id, update_data['flag_list'])				

		if 'image' in update_what and self._fancy:
			feed[PIXBUF] = self._get_pixbuf(feed_id)
			
		if 'readinfo' in update_what:
			#db_unread_count = self._db.get_unread_count(feed_id) #need it always for FIXME below
			if not update_data.has_key('unread_count'):
				update_data['unread_count'] = self._db.get_unread_count(feed_id)#, db_unread_count)
			if update_data['unread_count'] > 0:
				if feed[FLAG] & ptvDB.F_UNVIEWED==0:
					feed[FLAG] = feed[FLAG] + ptvDB.F_UNVIEWED
			else:
				if feed[FLAG] & ptvDB.F_UNVIEWED:
					feed[FLAG] = feed[FLAG] - ptvDB.F_UNVIEWED
			feed[UNREAD]   = update_data['unread_count']
			feed[TOTAL]    = len(update_data['flag_list'])

			readinfo_string = "("+str(update_data['unread_count'])+"/"+str(len(update_data['flag_list']))+")"			
			if self._fancy:
				readinfo_string += "\n"
			feed[READINFO] = self._get_markedup_title(readinfo_string,flag)
			
			if self._filter_unread: 	 
				if unviewed==0 and self.filter_test_feed(feed_id): #no sense testing the filter if we won't see it 	 
					need_filter = True
				
		if 'title' in update_what:
			selected = self.get_selected()
			if not update_data.has_key('title'):
				update_data['title'] = self._db.get_feed_title(feed_id)
			old_title_len = len(feed[TITLE])
			new_title_len = len(update_data['title'])
			
			# don't update feed[TITLE] yet, we need these data first
			if self._fancy:
				try: feed[FIRSTENTRYTITLE] = self._db.get_entrylist(feed_id)[0][1]
				except: feed[FIRSTENTRYTITLE] = ""
				feed[MARKUPTITLE] = self._get_fancy_markedup_title(update_data['title'],feed[FIRSTENTRYTITLE],feed[UNREAD], feed[TOTAL], flag, feed_id == selected)
			else:
				feed[MARKUPTITLE] = self._get_markedup_title(update_data['title'], flag)
				
			if feed[TITLE] != update_data['title']:
				feed[TITLE] = update_data['title']
				try:
					old_iter = self._feedlist.get_iter((self.find_index_of_item(feed_id),))
					new_iter = self._feedlist.get_iter(([f[0] for f in self._db.get_feedlist()].index(feed_id),))
					self._feedlist.move_after(old_iter,new_iter)
					if selected == feed_id:
						self._widget.scroll_to_cell((self.find_index_of_item(feed_id),))
				except:
					print "Error finding feed for update"
				need_filter = True
				#columns_autosize produces a flicker, so only do it if we need to
				if abs(new_title_len - old_title_len) > 5:
					self.resize_columns()
			
		if 'icon' in update_what:
			if not update_data.has_key('pollfail'):
				update_data['pollfail'] = self._db.get_feed_poll_fail(feed_id)
			feed[POLLFAIL] = update_data['pollfail']
			feed[STOCKID] = self._get_icon(flag)
			if update_data['pollfail']:
				if feed[STOCKID]=='gtk-harddisk' or feed[STOCKID]=='gnome-stock-blank':
					feed[STOCKID]='gtk-dialog-error'
			feed[FLAG] = flag	 
		 	if self.filter_setting == DOWNLOADED:
		 		if downloaded==0:
			 		need_filter = True	
			
		if need_filter and self._state != S_SEARCH:#not self._showing_search:
			self._filter_one(feed)
			
	def mark_entries_read(self, num_to_mark, feed_id=None):
	
		"""alters the number of unread entries by num_to_mark.  if negative,
		marks some as unread"""
		
		#there's some trickiness here.  The model for the selection is
		#self._feed_filter, not self._feedlist, so we can't write to items
		#in that model.  We have to go back and find where this feed is in the
		#original model.

		if feed_id is None:
			s = self._widget.get_selection().get_selected()
			if s is None:
				return
			model, iter = s
			if iter is None:
				return

			unfiltered_iter = model.convert_iter_to_child_iter(iter)
			feed = self._feedlist[unfiltered_iter]
		else:
			feed = self._feedlist[self.find_index_of_item(feed_id)]

		#print feed[UNREAD],feed[TOTAL],num_to_mark

		#sanity check
		if feed[UNREAD] - num_to_mark < 0 or feed[UNREAD] - num_to_mark > feed[TOTAL]:
			print "WARNING: trying to mark more or less than we have:", feed[TITLE], feed[UNREAD], num_to_mark
			self.update_feed_list(feed[FEEDID], ['readinfo'])
			return
			
		feed[UNREAD] -= num_to_mark
		
		if feed[UNREAD] == 0 and feed[FLAG] & ptvDB.F_UNVIEWED:
			feed[FLAG] -= ptvDB.F_UNVIEWED
			
		if feed[UNREAD] > 0 and feed[FLAG] & ptvDB.F_UNVIEWED == 0:
			feed[FLAG] += ptvDB.F_UNVIEWED
		
		readinfo_string = "("+str(feed[UNREAD])+"/"+str(feed[TOTAL])+")"
		
		if self._fancy:
			readinfo_string += "\n"
			feed[MARKUPTITLE] = self._get_fancy_markedup_title(feed[TITLE],
															   feed[FIRSTENTRYTITLE],
															   feed[UNREAD], 
															   feed[TOTAL], 
															   feed[FLAG], 
															   True)
		else:
			feed[MARKUPTITLE] = self._get_markedup_title(feed[TITLE], feed[FLAG])
			
		feed[READINFO] = self._get_markedup_title(readinfo_string,feed[FLAG])
		
		if self._filter_unread: 	 
			self._filter_one(feed)
				
	def show_search_results(self, results=[]):
		
		"""shows the feeds in the list 'results'"""
		
		if self._state != S_SEARCH:
			print "not in search state, returning"
			return
			
		if results is None:
			results = []
		#print results[0]
		if len(results) == 0:
			for feed in self._feedlist:
				feed[VISIBLE] = 0
			self._feed_filter.refilter()
			return
		
		for feed in self._feedlist:
			if feed[FEEDID] in results:
				feed[VISIBLE] = 1
			else:
				feed[VISIBLE] = 0
							
		id_list = [feed[FEEDID] for feed in self._feedlist]
						
		def sorter(a, b):
			if a[VISIBLE] != b[VISIBLE]:
				return b[VISIBLE] - a[VISIBLE]
			if a[VISIBLE]==1:
				return results.index(a[FEEDID]) - results.index(b[FEEDID])
			else:
				return id_list.index(a[FEEDID]) - id_list.index(b[FEEDID])
		
		#convert to list
		f_list = list(self._feedlist)
		#we sort the new feed list as is
		f_list.sort(sorter)
		#we go through the new feed list, and for each id find its old index
		i_list = []
		for f in f_list:
			i_list.append(id_list.index(f[FEEDID]))
		#we now have a list of old indexes in the new order		
		self._feedlist.reorder(i_list)
		self._feed_filter.refilter()
		if self._fancy:
			gobject.idle_add(self._load_visible_details().next)
		self._va.set_value(0)
		showing_feed = self.get_selected()
		if not self._app.entrylist_selecting_right_now() and showing_feed is not None:
			highlight_count = self._app.highlight_entry_results(showing_feed)
			if highlight_count == 0:
				#self._app.display_feed(showing_feed)
				self.emit('feed-selected', showing_feed)
		
	def _unset_state(self, data=True):
		if self._state == S_SEARCH:
			gonna_filter = data
			showing_feed = self.get_selected()
			id_list = [feed[FEEDID] for feed in self._feedlist]
			f_list = list(self._feedlist)
			def alpha_sorter(x,y):
				if x[TITLE].upper()>y[TITLE].upper():
					return 1
				if x[TITLE].upper()==y[TITLE].upper():
					return 0
				return -1
			f_list.sort(alpha_sorter)
			i_list = []
			for f in f_list:
				i_list.append(id_list.index(f[FEEDID]))
			self._feedlist.reorder(i_list)
			if showing_feed is not None:
				#self._app.display_feed(showing_feed)
				self.emit('feed-selected', showing_feed)
				if not self.filter_test_feed(showing_feed):
					self._app.main_window.set_active_filter(ALL)
				self.set_selected(showing_feed)
			elif gonna_filter == False:
				self._app.main_window.set_active_filter(ALL)
				#self._app.display_entry(None)
				self.emit('no-feed-selected')

	
	def set_state(self, newstate, data=None):
		d = {penguintv.DEFAULT: S_DEFAULT,
			 penguintv.MANUAL_SEARCH: S_SEARCH,
			 penguintv.TAG_SEARCH: S_SEARCH,
			 penguintv.LOADING_FEEDS: S_LOADING_FEEDS}
			 
		newstate = d[newstate]
		
		if newstate == self._state:
			return
			 
		self._unset_state(data)
		self._state = newstate
			
	def filter_all(self, keep_misfiltered=True):
		if utils.HAS_LUCENE and self.filter_setting == SEARCH:
			print "not filtering, we have search results"
			return #not my job
			
		#gtk.gdk.threads_enter()
		selected = self.get_selected()
		index = self.find_index_of_item(selected)
			
		i=-1
		for feed in self._feedlist:
			i=i+1
			flag = feed[FLAG]
			passed_filter = False
			
			if self.filter_setting == DOWNLOADED:
				if flag & ptvDB.F_DOWNLOADED or flag & ptvDB.F_PAUSED:
					passed_filter = True
			elif self.filter_setting == NOTIFY:
				opts = self._db.get_flags_for_feed(feed[FEEDID])
				if opts & ptvDB.FF_NOTIFYUPDATES:
					passed_filter = True
			elif self.filter_setting == ALL:
				passed_filter = True
			else:
				tags = self._db.get_tags_for_feed(feed[FEEDID])
				if tags:
					if self.filter_name in tags:
						passed_filter = True
			#so now we know if we passed the main filter, but we need to test for special cases where we keep it anyway
			#also, we still need to test for unviewed
			if i == index and selected is not None:  #if it's the selected feed, we have to be careful
				if keep_misfiltered: 
					#some cases when we want to keep the current feed visible
					if self._filter_unread == True and flag & ptvDB.F_UNVIEWED==0: #if it still fails the unviewed test
						passed_filter = True  #keep it
						self._selecting_misfiltered=True
					elif self.filter_setting == DOWNLOADED and flag & ptvDB.F_DOWNLOADED == 0 and flag & ptvDB.F_PAUSED == 0:
						passed_filter = True
						self._selecting_misfiltered=True
					elif self.filter_setting == DOWNLOADED and flag & ptvDB.F_DOWNLOADING:
						passed_filter = True
						self._selecting_misfiltered=True
				if not passed_filter:
					self._widget.get_selection().unselect_all() #and clear out the entry list and entry view
					if self._fancy:
						feed[MARKUPTITLE] = self._get_fancy_markedup_title(feed[TITLE],feed[FIRSTENTRYTITLE],feed[UNREAD], feed[TOTAL], feed[FLAG], False)
					#self._app.display_feed(-1)
					self.emit('no-feed-selected')
			else: #if it's not the selected feed
				if self._filter_unread == True and flag & ptvDB.F_UNVIEWED==0: #and it fails unviewed
					passed_filter = False #see ya
			if feed[VISIBLE] != passed_filter:
				feed[VISIBLE] = passed_filter #note, this seems to change the selection!
		self._feed_filter.refilter()
		self._reset_articles_column()
		#gtk.gdk.threads_leave()
		return False

	def _filter_one(self,feed, keep_misfiltered=True):
		if utils.HAS_LUCENE and self.filter_setting == SEARCH:
			print "not filtering, we have search results"
			return #not my job
	
		selected = self.get_selected()
		s_index = self.find_index_of_item(selected)
		feed_index = self.find_index_of_item(feed[FEEDID])
		
		flag = feed[FLAG]
		passed_filter = False
		
		if self.filter_setting == DOWNLOADED:
			if flag & ptvDB.F_DOWNLOADED or flag & ptvDB.F_PAUSED:
				passed_filter = True
		elif self.filter_setting == NOTIFY:
			opts = self._db.get_flags_for_feed(feed[FEEDID])
			if opts & ptvDB.FF_NOTIFYUPDATES:
				passed_filter = True
		elif self.filter_setting == ALL:
			passed_filter = True
		else:
			tags = self._db.get_tags_for_feed(feed[FEEDID])
			if tags:
				if self.filter_name in tags:
					passed_filter = True
		#so now we know if we passed the main filter, but we need to test for special cases where we keep it anyway
		#also, we still need to test for unviewed
		if feed_index == s_index and selected is not None:  #if it's the selected feed, we have to be careful
			if keep_misfiltered: 
				#some cases when we want to keep the current feed visible
				if self._filter_unread == True and flag & ptvDB.F_UNVIEWED==0: #if it still fails the unviewed test
					passed_filter = True  #keep it
					self._selecting_misfiltered=True
				elif self.filter_setting == DOWNLOADED and flag & ptvDB.F_DOWNLOADED == 0 and flag & ptvDB.F_PAUSED == 0:
					passed_filter = True
					self._selecting_misfiltered=True
				elif self.filter_setting == DOWNLOADED and flag & ptvDB.F_DOWNLOADING:
					passed_filter = True
					self._selecting_misfiltered=True
			if not passed_filter:
				self._widget.get_selection().unselect_all() #and clear out the entry list and entry view
				#self._app.display_feed(-1)
				self.emit('no-feed-selected')
		else: #if it's not the selected feed
			if self._filter_unread == True and flag & ptvDB.F_UNVIEWED==0: #and it fails unviewed
				passed_filter = False #see ya
		if feed[VISIBLE] != passed_filter:
			feed[VISIBLE] = passed_filter #note, this seems to change the selection!
		self._feed_filter.refilter()
			
	def _load_visible_details(self):
		self._loading_details = True
		for row in self._feedlist:
			#gtk.gdk.threads_enter()
			if self._cancel_load[1]:
				break
			if row[VISIBLE] and not row[DETAILS_LOADED]:
				try: row[FIRSTENTRYTITLE] = self._db.get_entrylist(row[FEEDID])[0][1]
				except: row[FIRSTENTRYTITLE] = ""
				#row[PIXBUF] = self._get_pixbuf(row[FEEDID])
				model, iter = self._widget.get_selection().get_selected()
				row[DETAILS_LOADED] = True
				try: selected = model[iter][FEEDID]
				except: selected = -1
				row[MARKUPTITLE] = self._get_fancy_markedup_title(row[TITLE],
																  row[FIRSTENTRYTITLE],
																  row[UNREAD],
																  row[TOTAL],
																  row[FLAG], 
																  row[FEEDID] == selected)
				#gtk.gdk.threads_leave()
				#self.resize_columns()
				yield True
		if self._cancel_load[1]:
			self._cancel_load[1] = False

		self._loading_details = False
		yield False
				
	def filter_test_feed(self, feed_id):
		"""Tests a feed against the filters (although _not_ unviewed status testing)"""
		passed_filter = False
		try:
			flag = self._feedlist[self.find_index_of_item(feed_id)][FLAG]
		except:
			return False
		
		if self.filter_setting == DOWNLOADED:
			if flag & ptvDB.F_DOWNLOADED or flag & ptvDB.F_PAUSED:
				passed_filter = True
		elif self.filter_setting == NOTIFY:
			opts = self._db.get_flags_for_feed(feed[FEEDID])
			if opts & ptvDB.FF_NOTIFYUPDATES:
				passed_filter = True
		elif self.filter_setting == ALL:
			passed_filter = True
		else:
			tags = self._db.get_tags_for_feed(feed_id)
			if tags:
				if self.filter_name in tags:
					passed_filter = True
		return passed_filter
			
	def on_row_activated(self, treeview, path, view_column):
		index = path[0]
		model = treeview.get_model()
		link = self._db.get_feed_info(model[index][FEEDID])['link']
		if link is None:
			dialog = gtk.Dialog(title=_("No Homepage"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("There is no homepage associated with this feed.  You can set one in the feed properties."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			dialog.run()
			dialog.hide()
			del dialog
		#self._app.activate_link(link)
		self.emit('link-activated', link)
		
	def set_filter(self, new_filter, name):
		self.filter_setting = new_filter
		self.filter_name = name

		#if new_filter != SEARCH and self._state == S_SEARCH:
		#	print "hope we also changed state"
		#	self._app.set_state(penguintv.DEFAULT)
			
		self.filter_all(False)
		if self._fancy:
			gobject.idle_add(self._load_visible_details().next)
		self._va.set_value(0)
		self.resize_columns()
		
	def set_fancy(self, fancy):
		if fancy == self._fancy:
			return #no need
		if self._state == S_LOADING_FEEDS:
			self.interrupt()
			while gtk.events_pending():
				gtk.main_iteration()
		#self._app.set_state(penguintv.LOADING_FEEDS)
		self.emit('state-change', penguintv.LOADING_FEEDS)
		self._fancy = fancy
		if self._fancy:
			self._icon_renderer.set_property('stock-size',gtk.ICON_SIZE_LARGE_TOOLBAR)
			self._widget.set_property('rules-hint', True)
		else:
			self._icon_renderer.set_property('stock-size',gtk.ICON_SIZE_SMALL_TOOLBAR)
			self._widget.set_property('rules-hint', False)
		if self._state == S_SEARCH:
			#self._app.set_state(penguintv.DEFAULT)
			self.emit('state-change', penguintv.DEFAULT)
		self._app.write_feed_cache()
		self.clear_list()
		self.populate_feeds(self._app._done_populating)
		self.resize_columns()
		
	def set_unread_toggle(self, active):
		if self._state == S_SEARCH:
			return 
		self._filter_unread = active
		self.filter_all(False)
		if self._fancy:
			gobject.idle_add(self._load_visible_details().next)
		self._va.set_value(0)	
		
	def clear_list(self):
		self._feedlist.clear()
		
	def add_feed(self, feed_id):
		newlist = self._db.get_feedlist()
		index = [f[0] for f in newlist].index(feed_id)
		feed = newlist[index]
		p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, 10,10)
		p.fill(0xffffff00)
		#insert, not append
		self._feedlist.insert(index,[feed[1], feed[1], feed[0], 'gnome-stock-blank', "", p, False, 1, 1, 0, True, False, ""])
		self.update_feed_list(feed_id)
		
	def remove_feed(self, feed_id):
		try:
			self._feedlist.remove(self._feedlist.get_iter((self.find_index_of_item(feed_id),)))
		except:
			print "Error: feed not in list"
				
	def _get_icon(self, flag):
		if flag & ptvDB.F_ERROR == ptvDB.F_ERROR:
			return 'gtk-dialog-error'
		if flag & ptvDB.F_DOWNLOADING == ptvDB.F_DOWNLOADING:
			return 'gtk-execute'
		if flag & ptvDB.F_DOWNLOADED == ptvDB.F_DOWNLOADED:
			return 'gtk-harddisk'
		if flag & ptvDB.F_PAUSED:
			return 'gtk-media-pause'
		return 'gnome-stock-blank'
	
	def _get_markedup_title(self, title, flag):
		if not title:
			return _("Please wait...")
		if utils.RUNNING_SUGAR:
			title='<span size="x-small">'+title+'</span>'
		try:
			if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
					title="<b>"+utils.my_quote(title)+"</b>"
		except:
			return title
		return title
		
	def _get_pixbuf(self, feed_id):
		filename = self._icon_manager.get_icon(feed_id)
		if filename is None:
			p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, MIN_SIZE, MIN_SIZE)
			p.fill(0xffffff00)
			return p
	
		try:
			p = gtk.gdk.pixbuf_new_from_file(filename)
		except:
			p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, MIN_SIZE, MIN_SIZE)
			p.fill(0xffffff00)
			return p
		height = p.get_height()
		width = p.get_width()
		if height > MAX_HEIGHT:
			height = MAX_HEIGHT
			width = p.get_width() * height / p.get_height()
		if width > MAX_WIDTH:
			width = MAX_WIDTH
			height = p.get_height() * width / p.get_width()
		if width < MIN_SIZE and height < MIN_SIZE:
			height = MIN_SIZE
			width = p.get_width() * height / p.get_height()
		if height != p.get_height() or width != p.get_width():
			del p
			p = gtk.gdk.pixbuf_new_from_file_at_size(filename, width, height)
		return p
		
	def _get_fancy_markedup_title(self, title, first_entry_title, unread, total, flag, selected):
		if not title:
			return _("Please wait...")
		try:
			if not selected:
				title = utils.my_quote(title)+'\n<span color="#777777" size="x-small"><i>'+utils.my_quote(first_entry_title)+'</i></span>'
			else:
				title = utils.my_quote(title)+'\n<span size="x-small"><i>'+utils.my_quote(first_entry_title)+'</i></span>'
			if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
				title="<b>"+title+'</b>'
		except:
			return title
		return title
	
	def _pick_important_flag(self, feed_id, flag_list):
		"""go through entries and pull out most important flag"""
		if len(flag_list)==0:
			return 0

		entry_count = len(flag_list)
		important_flag = 0
		media_exists = 0
		for flag in flag_list:
			if flag & ptvDB.F_DOWNLOADED == ptvDB.F_DOWNLOADED:
				media_exists=1
				break
		flag_list.sort()
		best_flag = flag_list[-1]
		if best_flag & ptvDB.F_DOWNLOADED == 0 and media_exists==1: #if there is an unread text-only entry, but all viewed media,
																	#we need a special case (mixing flags from different entries)
			return best_flag + ptvDB.F_DOWNLOADED
		else:
			return best_flag
			
	def _item_selection_changed(self, selection):
		s = selection.get_selected()
		if s:
			model, iter = s
			if iter is None:
				self.emit('no-feed-selected') 
				return
			unfiltered_iter = model.convert_iter_to_child_iter(iter)
			feed = self._feedlist[unfiltered_iter]
		else:
			self.emit('no-feed-selected') 
			return
		
		if self._fancy and self._last_feed is not None:
			try: 
				old_item = self._feedlist[self._last_feed]
				old_item[MARKUPTITLE] = self._get_fancy_markedup_title(old_item[TITLE],old_item[FIRSTENTRYTITLE],old_item[UNREAD], old_item[TOTAL], old_item[FLAG], False)
			except:
				pass
			
		self._last_feed=unfiltered_iter
		self._select_after_load=None
		
		if self._fancy:
			feed[MARKUPTITLE] = self._get_fancy_markedup_title(feed[TITLE],feed[FIRSTENTRYTITLE],feed[UNREAD], feed[TOTAL], feed[FLAG], True)

		try:
			if self._feedlist[self.find_index_of_item(feed[FEEDID])][POLLFAIL]:
				self._app.display_custom_entry("<b>"+_("There was an error trying to poll this feed.")+"</b>")
			else:
				self._app.undisplay_custom_entry()
		except:
			self._app.undisplay_custom_entry()

		#if self._showing_search:
		if self._state == S_SEARCH:
			if feed[FEEDID] == self._last_selected:
				return
			self._last_selected = feed[FEEDID]
			if not self._app.entrylist_selecting_right_now():
				highlight_count = self._app.highlight_entry_results(feed[FEEDID])
				if highlight_count == 0:
					#self._app.display_feed(feed[FEEDID])
					self.emit('feed-selected', feed[FEEDID])
			return
		if feed[FEEDID] == self._last_selected:
			#self._app.display_feed(feed[FEEDID])
			self.emit('feed-selected', feed[FEEDID])
		else:
			self._last_selected = feed[FEEDID]
			#print "wtf is this negative 2 shit (feedlistview)"
			#self._app.display_feed(feed[FEEDID], -2)
			self.emit('feed-selected', feed[FEEDID])
			if self._selecting_misfiltered and feed[FEEDID]!=None:
				self._selecting_misfiltered = False
				gobject.timeout_add(250, self.filter_all)
			
	def get_selected(self, selection=None):
		if selection==None:
			try:
				s = self._widget.get_selection().get_selected()
			except AttributeError:
				return None
		else:
			s = selection.get_selected()
		if s:
			model, iter = s
			if iter is None:
				return None
			path = model.get_path(iter)
			index = path[0]
			return model[index][FEEDID]
		else:
			return None
			
	def set_selected(self, feed_id):
		if feed_id is None:
			self._widget.get_selection().unselect_all()
			return
		visible = [f[FEEDID] for f in self._feedlist if f[VISIBLE]]
		index=None
		try:
			index = visible.index(feed_id)
		except:
			pass
		if index is None:
			if self.filter_setting != ALL:
				self._app.main_window.set_active_filter(ALL) #hmm..
				self.set_selected(feed_id)
				return
			else:
				self._widget.get_selection().unselect_all()
		else:
			self._widget.get_selection().select_path((index,))
			self._widget.scroll_to_cell((index,))
			
	def find_index_of_item(self, feed_id):
		try:
			i=-1
			for feed in self._feedlist:
				i+=1
				if feed_id == feed[FEEDID]:
					return i
			return None
		except:
			return None
			
	def get_feed_cache(self):
		return [[f[FEEDID],f[FLAG],f[UNREAD],f[TOTAL]] for f in self._feedlist]
		
	def interrupt(self):
		self._cancel_load = [True,True]
		
