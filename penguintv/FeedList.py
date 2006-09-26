import gtk
import gobject
import penguintv
import ptvDB
import utils

import MainWindow

import traceback, sys
import glob

import random


NONE=-1 #unused, needs a value
ALL=0
DOWNLOADED=1
ACTIVE=2
SEARCH=3
UNKNOWN=4
BUILTIN_TAGS=[_("All Feeds"),_("Downloaded Media"),_("Active Downloads"), _("Search Results")]

TITLE=0
MARKUPTITLE=1
FEEDID=2
STOCKID=3
READINFO=4
PIXBUF=5
UNREAD=6
TOTAL=7
FLAG=8
VISIBLE=9
POLLFAIL=10

class FeedList:
	def __init__(self, widget_tree, app, db, fancy=False):
		self._scrolled_window = widget_tree.get_widget('feed_scrolled_window')
		self._va = self._scrolled_window.get_vadjustment()
		self._widget = widget_tree.get_widget('feedlistview')
		self._entry_list_widget = widget_tree.get_widget('entrylistview')
		self._app = app
		self._feedlist = gtk.ListStore(str, str, int, str, str, gtk.gdk.Pixbuf, int, int, int, bool, bool) #see enum above
		self._feed_filter = self._feedlist.filter_new()
		self._feed_filter.set_visible_column(VISIBLE)
		self._db = db
		self._last_selected=None
		self._last_feed=None
		self.filter_setting=ALL
		self.filter_name = _("All Feeds")
		self._selecting_misfiltered=False
		self._filter_unread = False
		self._cancel_load = False
		self._showing_search = False
		self._fancy = fancy
		
		#build list view
		self._widget.set_model(self._feed_filter)
		renderer = gtk.CellRendererText()
		self._icon_renderer = gtk.CellRendererPixbuf()
		feed_image_renderer = gtk.CellRendererPixbuf()
		self._feed_column = gtk.TreeViewColumn(_('Feeds'))
		self._feed_column.set_resizable(True)
		
		#primary column
		self._feed_column.pack_start(self._icon_renderer, False)
		self._feed_column.pack_start(renderer, True)
		self._feed_column.pack_start(feed_image_renderer, False)
		
		self._feed_column.set_attributes(renderer, markup=MARKUPTITLE)
		self._feed_column.set_attributes(self._icon_renderer, stock_id=STOCKID)
		self._feed_column.set_attributes(feed_image_renderer, pixbuf=PIXBUF)
		
		#self._feed_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		self._widget.append_column(self._feed_column)
			
		renderer = gtk.CellRendererText()
		self._articles_column = gtk.TreeViewColumn(_(''))
		self._articles_column.set_resizable(True)
		self._articles_column.pack_start(renderer, True)
		self._articles_column.set_attributes(renderer, markup=READINFO)		
		#self._articles_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		self._widget.append_column(self._articles_column)
		
		self._widget.columns_autosize()
		
		#signals
		self._widget.get_selection().connect("changed", self._item_selection_changed)
		self._widget.connect("row-activated", self.on_row_activated)
		
		#init style
		if self._fancy:
			self._icon_renderer.set_property('stock-size',gtk.ICON_SIZE_LARGE_TOOLBAR)
			self._widget.set_property('rules-hint', True)
			
	def set_fancy(self, fancy):
		if fancy == self._fancy:
			return #no need
		self._fancy = fancy
		if self._fancy:
			self._icon_renderer.set_property('stock-size',gtk.ICON_SIZE_LARGE_TOOLBAR)
			self._widget.set_property('rules-hint', True)
		else:
			self._icon_renderer.set_property('stock-size',gtk.ICON_SIZE_SMALL_TOOLBAR)
			self._widget.set_property('rules-hint', False)
		if self._showing_search:
			self.unshow_search()
		self._app.write_feed_cache()
		self.clear_list()
		self.populate_feeds(self._app._done_populating)
		self._widget.columns_autosize()
				
	def on_row_activated(self, treeview, path, view_column):
		index = path[0]
		model = treeview.get_model()
		link = self._db.get_feed_info(model[index][FEEDID])['link']
		if len(link) == 0:
			dialog = gtk.Dialog(title=_("No Homepage"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("There is no homepage associated with this feed.  You can set one in the feed properties"))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			response = dialog.run()
			dialog.hide()
			del dialog
		self._app.activate_link(link)
	
	def resize_columns(self, pane_size=0):
		self._widget.columns_autosize()
	#	if pane_size>0:
	#		print "resize"
	#		self._feed_column.set_fixed_width(pane_size - (self._articles_column.get_width()))
			
	def set_filter(self, new_filter, name):
		self.filter_setting = new_filter
		self.filter_name = name
		
		if new_filter != SEARCH and self._showing_search:
			self.unshow_search()
			
		self.do_filter(False)
		self._va.set_value(0)
		self.resize_columns()
		
	def show_search_results(self, results=[]):
		"""shows the feeds in the list 'results'"""
		self._showing_search = True
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
		self._va.set_value(0)
		showing_feed = self.get_selected()
		if not self._app.entrylist_selecting_right_now() and showing_feed is not None:
			highlight_count = self._app.highlight_entry_results(showing_feed)
			if highlight_count == 0:
				self._app.display_feed(showing_feed)
		
	def unshow_search(self, gonna_filter=False):
		showing_feed = self.get_selected()
		self._showing_search = False
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
			self._app.display_feed(showing_feed)
			if not self.filter_test_feed(showing_feed):
				self._app.main_window.filter_combo_widget.set_active(ALL)
			self.set_selected(showing_feed)
		elif not gonna_filter:
			self._app.main_window.filter_combo_widget.set_active(ALL)
			self._app.display_entry(None)
		
	def set_unread_toggle(self, active):
		if self._showing_search:
			return
		self._filter_unread = active
		self.do_filter(False)
		self._va.set_value(0)
		
	def do_filter(self,keep_misfiltered=True):
		if self.filter_setting == SEARCH:
			print "not filtering, we have search results"
			return #not my job
	
		#if index == -1:
		selected = self.get_selected()
		index = self.find_index_of_item(selected)
			
		#else:
		#	selected = self._feed_filter[index][FEEDID]
			
		i=-1
		for feed in self._feedlist:
			i=i+1
			flag = feed[FLAG]
			passed_filter = False
			
			if self.filter_setting == DOWNLOADED:
				if flag & ptvDB.F_DOWNLOADED or flag & ptvDB.F_PAUSED:
					passed_filter = True
			elif self.filter_setting == ACTIVE:
				if flag & ptvDB.F_DOWNLOADING:
					passed_filter = True
			elif self.filter_setting == ALL:
				passed_filter = True
			else:
				tags = self._db.get_tags_for_feed(feed[2])
				if tags:
					if self.filter_name in tags:
						passed_filter = True
			#so now we know if we passed the main filter, but we need to test for special cases where we keep it anyway
			#also, we still need to test for unviewed
			if i == index and selected is not None:  #if it's the selected feed, we have to be careful
				if self.filter_setting != NONE:
					if keep_misfiltered==True: 
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
						elif self.filter_setting == ACTIVE and flag & ptvDB.F_DOWNLOADING == 0:
							passed_filter = True
							self._selecting_misfiltered=True
					#else: leave the filter result alone
				else:
					#if filter is NONE, no one is getting past.
					passed_filter = False
				if passed_filter == False:
					self._widget.get_selection().unselect_all() #and clear out the entry list and entry view
					self._app.display_feed(-1)
			else: #if it's not the selected feed
				if self._filter_unread == True and flag & ptvDB.F_UNVIEWED==0: #and it fails unviewed
					passed_filter = False #see ya
			feed[VISIBLE] = passed_filter #note, this seems to change the selection!
			
		if self.filter_setting == NONE:
			self._app.display_feed(-1)
			self._last_selected = None
			self._selecting_misfiltered=False
		self._feed_filter.refilter()
		
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
		elif self.filter_setting == ACTIVE:
			if flag & ptvDB.F_DOWNLOADING:
				passed_filter = True
		elif self.filter_setting == ALL:
			passed_filter = True
		else:
			tags = self._db.get_tags_for_feed(feed_id)
			if tags:
				if self.filter_name in tags:
					passed_filter = True
		return passed_filter
		
	def clear_list(self):
		self._feedlist.clear()
		
	def populate_feeds(self,callback=None, subset=ALL):
		"""With 100 feeds, this is starting to get slow (2-3 seconds).  Speed helped with cache"""
		#FIXME:  better way to get to the status display?
		#DON'T gtk.iteration in this func! Causes endless loops!
		if len(self._feedlist)==0:
			self._app.main_window.display_status_message(_("Loading Feeds..."))
			#first fill out rough feedlist
			db_feedlist = self._db.get_feedlist()
			p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, 10,10)
			p.fill(0xffffff00)			
			for feed_id,title in db_feedlist:
				self._feedlist.append([title, title, feed_id, 'gtk-stock-blank', "", p, 0, 0, 0, False, False]) #assume invisible
		else:
			self._app.main_window.display_status_message(_("Reloading Feeds..."))
		
		gobject.idle_add(self._update_feeds_generator(callback,subset).next)
		#self._update_feeds_generator(subset)
		return False #in case this was called by the timeout below
		
	def _update_feeds_generator(self, callback=None, subset=ALL):
		"""A generator that updates the feed list.  Called from populate_feeds"""	
			
		selection = self._widget.get_selection()
		selected = self.get_selected()
		feed_cache = self._db.get_feed_cache()
		db_feedlist = self._db.get_feedlist()
		
		i=-1
		downloaded=0
		
		if not self._fancy:
			blank_pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, 10,10)
			blank_pixbuf.fill(0xffffff00)
		
		for feed_id,title in db_feedlist:
			if self._cancel_load:
				self._cancel_load = False
				yield False
			i=i+1
			
			if subset==DOWNLOADED:
				flag = self._feedlist[i][FLAG]
				if flag & ptvDB.F_DOWNLOADED==0 and flag & ptvDB.F_PAUSED==0:
					continue
			if subset==ACTIVE:
				flag = self._feedlist[i][FLAG]
				if flag & ptvDB.F_DOWNLOADING==0:
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
			if entry_count==0: #this is a good indication that the cache is bad
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
			
			if not self._fancy:
				m_title = self._get_markedup_title(title,flag) 
				m_readinfo = self._get_markedup_title("(%d/%d)" % (unviewed,entry_count), flag)
				m_pixbuf = blank_pixbuf
			else:
				m_title = self._get_fancy_markedup_title(title,unviewed,entry_count,flag, False) 
				m_pixbuf = self._get_pixbuf(feed_id)
				m_readinfo = ""
			icon = self._get_icon(flag)	
			
			if pollfail:
 				if icon=='gtk-harddisk' or icon=='gnome-stock-blank':
 					icon='gtk-dialog-error'
			visible = self._feedlist[i][VISIBLE]
			self._feedlist[i] = [title, m_title, feed_id, icon, m_readinfo, m_pixbuf, unviewed, entry_count, flag, visible, pollfail]
			try:
				if i % (len(db_feedlist)/20) == 0:
					self.do_filter()
					self._app.main_window.update_progress_bar(float(i)/len(db_feedlist),MainWindow.U_LOADING)
			except:
				pass
			yield True
	
		if selected:
			index = self.find_index_of_item(selected)
			if index is None:
				self._va.set_value(self._va.lower)
			else:
				selection.select_path((index,))
		self.do_filter()
		if callback is not None:
			try:
				callback()
			except:
				pass
	
		yield False
		
	def add_feed(self, feed_id):
		newlist = self._db.get_feedlist()
		index = [f[0] for f in newlist].index(feed_id)
		feed = newlist[index]
		p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, 10,10)
		p.fill(0xffffff00)
		self._feedlist.insert(index,[feed[1], feed[1], feed[0], 'gnome-stock-blank', "", p, 1, 1, 0, True, False])
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
		try:
			if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
					title="<b>"+utils.my_quote(title)+"</b>"
		except:
			return title
		return title
		
	def _get_pixbuf(self, feed_id):
		"""right now this is a proof-of-concept horrible hack.  Most of this code will be
		moved to ptvDB"""
		filename = '/home/owen/.penguintv/icons/'+str(feed_id)+'.*'
		result = glob.glob(filename)
		if len(result)==0:
			p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, 10,10)
			p.fill(0xffffff00)
			return p
	
		try:
			p = gtk.gdk.pixbuf_new_from_file(result[0])
		except:
			p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, 10,10)
			p.fill(0xffffff00)
			return p
		height = p.get_height()
		width = p.get_width()
		if height > 64:
			height = 64
			width = p.get_width() * height / p.get_height()
		if width > 80:
			width = 80
			height = p.get_height() * width / p.get_width()
		if width < 32 and height < 32:
			height = 32
			width = p.get_width() * height / p.get_height()
		if height != p.get_height() or width != p.get_width():
			p = gtk.gdk.pixbuf_new_from_file_at_size(result[0], width, height)
		return p
		
	def _get_fancy_markedup_title(self, title, unread, total, flag, selected):
		if not title:
			return _("Please wait...")
		try:
			#selected = self.get_selected()
			if not selected:
				title = utils.my_quote(title)+'\n<span color="#777777" size="smaller"><i>('+str(unread)+'/'+str(total)+')</i></span>'
			else:
				title = utils.my_quote(title)+'\n<span size="smaller"><i>('+str(unread)+'/'+str(total)+')</i></span>'
			if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
				title="<b>"+title+'</b>'
		except:
			return title
		return title
		
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
			feed_id = self._last_feed
			
		if update_what is None:
			update_what = ['readinfo','icon','pollfail','title']
		if update_data is None:
			update_data = {}
			
		if self._fancy and 'readinfo' in update_what and 'title' not in update_what:
			update_what.append('title') #need this too
		
		try:
			feed = self._feedlist[self.find_index_of_item(feed_id)]
		except:
			print "error getting feed", feed_id, self.find_index_of_item(feed_id)
			return
			
		need_filter = False #some updates will require refiltering. 
		
		if 'pollfail' not in update_what or len(update_what)>1:
			#or in the converse, if pollfail in what and len is one, we don't need to do this
			
			if update_data.has_key('flag_list')==False:
				entrylist = self._db.get_entrylist(feed_id)
				if entrylist:
					update_data['flag_list'] = self._db.get_entry_flags(feed_id)
				else:
					update_data['flag_list'] = []
						
			updated=0
			unviewed=0
			downloaded=0
			active=0
		 	
			updated=1
			for flag in update_data['flag_list']:
				if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
					unviewed=unviewed+1
				if flag & ptvDB.F_DOWNLOADED or flag & ptvDB.F_PAUSED:
					downloaded=1
				if flag & ptvDB.F_DOWNLOADING:
					active=1

			flag = self._pick_important_flag(feed_id, update_data['flag_list'])				

		if 'icon' in update_what and 'pollfail' not in update_what:
			update_what.append('pollfail')	 #we need that data for icon updates
			
		if 'image' in update_what:
			feed[PIXBUF] = self._get_pixbuf(feed_id)
			
		if 'pollfail' in update_what:	
			if not update_data.has_key('pollfail'):
				update_data['pollfail'] = self._db.get_feed_poll_fail(feed_id)
			feed[POLLFAIL] = update_data['pollfail']
			if feed[STOCKID]=='gtk-harddisk' or feed[STOCKID]=='gnome-stock-blank':
				feed[STOCKID]='gtk-dialog-error'
				
		if 'readinfo' in update_what:
			#db_unread_count = self._db.get_unread_count(feed_id) #need it always for FIXME below
			if not update_data.has_key('unread_count'):
				update_data['unread_count'] = self._db.get_unread_count(feed_id)#, db_unread_count)
			if update_data['unread_count'] > 0:
				if feed[FLAG] & ptvDB.F_UNVIEWED==0:
					feed[FLAG] = feed[FLAG] + ptvDB.F_UNVIEWED
			else:
				if feed[FLAG] & ptvDB.F_UNVIEWED:
					feed[FLAG] = feed[FLAG]-ptvDB.F_UNVIEWED
			feed[UNREAD]   = update_data['unread_count']
			feed[TOTAL]    = len(update_data['flag_list'])
			if not self._fancy:
				feed[READINFO] = self._get_markedup_title("("+str(update_data['unread_count'])+"/"+str(len(update_data['flag_list']))+")",flag)
				feed[MARKUPTITLE] = self._get_markedup_title(feed[TITLE],flag)
			else:
				feed[READINFO] = ""
				selected = self.get_selected()
				feed[MARKUPTITLE] = self._get_fancy_markedup_title(feed[TITLE],update_data['unread_count'], len(update_data['flag_list']), flag, feed_id == selected)
				#feed[PIXBUF] = self._get_pixbuf(feed_id)
			#if unviewed != db_unread_count:
			#	print "correcting unread count"
			#	self._db.correct_unread_count(feed_id) #FIXME this shouldn't be necessary
			#	print "done"
			if self._filter_unread:
		 		if updated==1 and unviewed==0 and self.filter_test_feed(feed_id): #no sense testing the filter if we won't see it
					need_filter = True
					
		if 'title' in update_what:
			selected = self.get_selected()
			if not update_data.has_key('title'):
				update_data['title'] = self._db.get_feed_title(feed_id)
			feed[TITLE] = update_data['title']
			feed[MARKUPTITLE] = self._get_fancy_markedup_title(feed[TITLE],feed[UNREAD], feed[TOTAL], flag, feed_id == selected)
			#feed[PIXBUF] = self._get_pixbuf(feed_id)
			#may need to resort the feed list
			try:
				old_iter = self._feedlist.get_iter((self.find_index_of_item(feed_id),))
				new_iter = self._feedlist.get_iter(([f[0] for f in self._db.get_feedlist()].index(feed_id),))
				self._feedlist.move_after(old_iter,new_iter)
				if selected == feed_id:
					self._widget.scroll_to_cell((self.find_index_of_item(feed_id),))
			except:
				print "Error finding feed for update"
			need_filter = True
			
		if 'icon' in update_what:
			feed[STOCKID] = self._get_icon(flag)
			if update_data['pollfail']:
				if feed[STOCKID]=='gtk-harddisk' or feed[STOCKID]=='gnome-stock-blank':
					feed[STOCKID]='gtk-dialog-error'
			feed[FLAG] = flag	 
		 	if self.filter_setting == DOWNLOADED:
		 		if updated==1 and downloaded==0:
			 		need_filter = True
			if self.filter_setting == ACTIVE:
		 		if updated==1 and active==0:
			 		need_filter = True		
			
		if need_filter and not self._showing_search:
			self.do_filter()
		
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
		item = self.get_selected()
		try:
			feed = self._feedlist[self.find_index_of_item(item)]
		except:
			return
		
		if self._fancy and self._last_feed is not None:
			old_item = self._feedlist[self.find_index_of_item(self._last_feed)]
			old_item[MARKUPTITLE] = self._get_fancy_markedup_title(old_item[TITLE],old_item[UNREAD], old_item[TOTAL], old_item[FLAG], False)
			
		self._last_feed=item
		
		if item:
			if self._fancy:
				feed[MARKUPTITLE] = self._get_fancy_markedup_title(feed[TITLE],feed[UNREAD], feed[TOTAL], feed[FLAG], True)
		
			if self._showing_search:
				if item == self._last_selected:
					return
				self._last_selected = item
				if not self._app.entrylist_selecting_right_now():
					highlight_count = self._app.highlight_entry_results(item)
					if highlight_count == 0:
						self._app.display_feed(item)
				return
			if item == self._last_selected:
				self._app.display_feed(item)
			else:
				self._last_selected = item
				self._app.display_feed(item, -2)
				if self._selecting_misfiltered == True and item!=None:
					self._selecting_misfiltered = False
					gobject.timeout_add(250, self.do_filter)
			try:
				if self._feedlist[self.find_index_of_item(item)][POLLFAIL] == True:
					self._app.display_custom_entry("<b>"+_("There was an error trying to poll this feed.")+"</b>")
					return
			except:
				pass
		self._app.undisplay_custom_entry()
			
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
		index = self.find_index_of_item(feed_id)
		if index is not None:
			self._widget.get_selection().select_path((index,))
			self._widget.scroll_to_cell((index,))
		else:
			self._widget.get_selection().unselect_all()
			
	def find_index_of_item(self, feed_id):
		#list = [feed[FEEDID] for feed in self._feedlist]
		try:
			i=-1
			for feed in self._feedlist:
				i+=1
				if feed_id == feed[FEEDID]:
					return i
			#return list.index(feed_id)
			return None
		except:
			return None
			
	def get_feed_cache(self):
		return [[f[FEEDID],f[FLAG],f[UNREAD],f[TOTAL]] for f in self._feedlist]
		
	def interrupt(self):
		self._cancel_load = True
		
