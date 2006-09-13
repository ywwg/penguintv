import gtk
import gobject
import penguintv
import ptvDB
import utils

import MainWindow

import traceback, sys

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
UNREAD=5
TOTAL=6
FLAG=7
VISIBLE=8
POLLFAIL=9

class FeedList:
	def __init__(self, widget_tree, app, db):
		self.scrolled_window = widget_tree.get_widget('feed_scrolled_window')
		self.va = self.scrolled_window.get_vadjustment()
		self._widget = widget_tree.get_widget('feedlistview')
		self.entry_list_widget = widget_tree.get_widget('entrylistview')
		self._app = app
		self.feedlist = gtk.ListStore(str, str, int, str, str, int, int, int, bool, bool) #title, markuptitle, feed_id, stock_id, readinfo, unread, total, flag, visible, pollfail
		self.feed_filter = self.feedlist.filter_new()
		self.feed_filter.set_visible_column(VISIBLE)
		self.db = db
		self.last_selected=None
		self.last_feed=None
		self.filter_setting=ALL
		self.filter_name = _("All Feeds")
		self.selecting_misfiltered=False
		self.filter_unread = False
		self.cancel_load = False
		self.showing_search = False
		
		#build list view
		self._widget.set_model(self.feed_filter)
		renderer = gtk.CellRendererText()
		icon_renderer = gtk.CellRendererPixbuf()
		self.feed_column = gtk.TreeViewColumn(_('Feeds'))
		self.feed_column.set_resizable(True)
		self.feed_column.pack_start(icon_renderer, False)
		self.feed_column.pack_start(renderer, True)
		self.feed_column.set_attributes(renderer, markup=MARKUPTITLE)
		self.feed_column.set_attributes(icon_renderer, stock_id=STOCKID)
		#self.feed_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		self._widget.append_column(self.feed_column)
			
		renderer = gtk.CellRendererText()
		self.articles_column = gtk.TreeViewColumn(_(''))
		self.articles_column.set_resizable(True)
		self.articles_column.pack_start(renderer, True)
		self.articles_column.set_attributes(renderer, markup=READINFO)		
		#self.articles_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		self._widget.append_column(self.articles_column)
		
		self._widget.columns_autosize()
		
		#signals
		self._widget.get_selection().connect("changed", self._item_selection_changed)
		self._widget.connect("row-activated", self.on_row_activated)
		
	def on_row_activated(self, treeview, path, view_column):
		index = path[0]
		model = treeview.get_model()
		link = self.db.get_feed_info(model[index][FEEDID])['link']
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
	#		self.feed_column.set_fixed_width(pane_size - (self.articles_column.get_width()))
			
	def set_filter(self, new_filter, name):
		self.filter_setting = new_filter
		self.filter_name = name
		
		if new_filter != SEARCH and self.showing_search:
			self.unshow_search()
			
		self.do_filter(False)
		self.va.set_value(0)
		self.resize_columns()
		
	def show_search_results(self, results=[]):
		"""shows the feeds in the list 'results'"""
		self.showing_search = True
		if results is None:
			results = []
		#print results[0]
		if len(results) == 0:
			for feed in self.feedlist:
				feed[VISIBLE] = 0
			self.feed_filter.refilter()
			return
		
		for feed in self.feedlist:
			if feed[FEEDID] in results:
				feed[VISIBLE] = 1
			else:
				feed[VISIBLE] = 0
							
		id_list = [feed[FEEDID] for feed in self.feedlist]
						
		def sorter(a, b):
			if a[VISIBLE] != b[VISIBLE]:
				return b[VISIBLE] - a[VISIBLE]
			if a[VISIBLE]==1:
				return results.index(a[FEEDID]) - results.index(b[FEEDID])
			else:
				return id_list.index(a[FEEDID]) - id_list.index(b[FEEDID])
		
		#convert to list
		f_list = list(self.feedlist)
		#we sort the new feed list as is
		f_list.sort(sorter)
		#we go through the new feed list, and for each id find its old index
		i_list = []
		for f in f_list:
			i_list.append(id_list.index(f[FEEDID]))
		#we now have a list of old indexes in the new order		
		self.feedlist.reorder(i_list)
		self.feed_filter.refilter()
		self.va.set_value(0)
		showing_feed = self.get_selected()
		if not self._app.entrylist_selecting_right_now() and showing_feed is not None:
			highlight_count = self._app.highlight_entry_results(showing_feed)
			if highlight_count == 0:
				self._app.display_feed(showing_feed)
		
	def unshow_search(self):
		showing_feed = self.get_selected()
		self.showing_search = False
		id_list = [feed[FEEDID] for feed in self.feedlist]
		f_list = list(self.feedlist)
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
		self.feedlist.reorder(i_list)
		if showing_feed is not None:
			self._app.display_feed(showing_feed)
			if not self.filter_test_feed(showing_feed):
				self._app.main_window.filter_combo_widget.set_active(ALL)
			self.set_selected(showing_feed)
		else:
			self._app.main_window.filter_combo_widget.set_active(ALL)
			self._app.display_entry(None)
		
	def set_unread_toggle(self, active):
		if self.showing_search:
			return
		self.filter_unread = active
		self.do_filter(False)
		self.va.set_value(0)
		
	def do_filter(self,keep_misfiltered=True):
		if self.filter_setting == SEARCH:
			print "not filtering, we have search results"
			return #not my job
	
		#if index == -1:
		selected = self.get_selected()
		index = self.find_index_of_item(selected)
			
		#else:
		#	selected = self.feed_filter[index][FEEDID]
			
		i=-1
		for feed in self.feedlist:
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
				tags = self.db.get_tags_for_feed(feed[2])
				if tags:
					if self.filter_name in tags:
						passed_filter = True
			#so now we know if we passed the main filter, but we need to test for special cases where we keep it anyway
			#also, we still need to test for unviewed
			if i == index and selected is not None:  #if it's the selected feed, we have to be careful
				if self.filter_setting != NONE:
					if keep_misfiltered==True: 
						#some cases when we want to keep the current feed visible
						if self.filter_unread == True and flag & ptvDB.F_UNVIEWED==0: #if it still fails the unviewed test
							passed_filter = True  #keep it
							self.selecting_misfiltered=True
						elif self.filter_setting == DOWNLOADED and flag & ptvDB.F_DOWNLOADED == 0 and flag & ptvDB.F_PAUSED == 0:
							passed_filter = True
							self.selecting_misfiltered=True
						elif self.filter_setting == DOWNLOADED and flag & ptvDB.F_DOWNLOADING:
							passed_filter = True
							self.selecting_misfiltered=True
						elif self.filter_setting == ACTIVE and flag & ptvDB.F_DOWNLOADING == 0:
							passed_filter = True
							self.selecting_misfiltered=True
					#else: leave the filter result alone
				else:
					#if filter is NONE, no one is getting past.
					passed_filter = False
				if passed_filter == False:
					self._widget.get_selection().unselect_all() #and clear out the entry list and entry view
					self._app.display_feed(-1)
			else: #if it's not the selected feed
				if self.filter_unread == True and flag & ptvDB.F_UNVIEWED==0: #and it fails unviewed
					passed_filter = False #see ya
			feed[VISIBLE] = passed_filter #note, this seems to change the selection!
			
		if self.filter_setting == NONE:
			self._app.display_feed(-1)
			self.last_selected = None
			self.selecting_misfiltered=False
		self.feed_filter.refilter()
		
	def filter_test_feed(self, feed_id):
		"""Tests a feed against the filters (although _not_ unviewed status testing)"""
		passed_filter = False
		try:
			flag = self.feedlist[self.find_index_of_item(feed_id)][FLAG]
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
			tags = self.db.get_tags_for_feed(feed_id)
			if tags:
				if self.filter_name in tags:
					passed_filter = True
		return passed_filter
		
	def clear_list(self):
		self.feedlist.clear()
		
	def populate_feeds(self,subset=ALL, callback=None):
		"""With 100 feeds, this is starting to get slow (2-3 seconds).  Speed helped with cache"""
		#FIXME:  better way to get to the status display?
		#DON'T gtk.iteration in this func! Causes endless loops!
		if len(self.feedlist)==0:
			self._app.main_window.display_status_message(_("Loading Feeds..."))
			#first fill out rough feedlist
			db_feedlist = self.db.get_feedlist()
			for feed_id,title in db_feedlist:
				self.feedlist.append([title, title, feed_id, 'gtk-stock-blank', "", 0, 0, 0, False, False]) #assume invisible
		else:
			self._app.main_window.display_status_message(_("Reloading Feeds..."))
		gobject.idle_add(self._update_feeds_generator(subset,callback).next)
		#self._update_feeds_generator(subset)
		return False #in case this was called by the timeout below
	
	def _update_feeds_generator(self, callback=None, subset=ALL):
		"""A generator that updates the feed list.  Called from populate_feeds"""	
			
		selection = self._widget.get_selection()
		selected = self.get_selected()
		feed_cache = self.db.get_feed_cache()
		db_feedlist = self.db.get_feedlist()
		i=-1
		downloaded=0
		for feed_id,title in db_feedlist:
			if self.cancel_load:
				self.cancel_load = False
				yield False
			i=i+1
			
			if subset==DOWNLOADED:
				flag = self.feedlist[i][FLAG]
				if flag & ptvDB.F_DOWNLOADED==0 and flag & ptvDB.F_PAUSED==0:
					continue
			if subset==ACTIVE:
				flag = self.feedlist[i][FLAG]
				if flag & ptvDB.F_DOWNLOADING==0:
					continue
			if feed_cache is not None:
				cached     = feed_cache[i]
				unviewed   = cached[2]
				flag       = cached[1]
				pollfail   = cached[4]
				entry_count= cached[3]
			else:
				feed_info   = self.db.get_feed_verbose(feed_id)
				unviewed    = feed_info['unread_count']
				flag        = feed_info['important_flag']
				pollfail    = feed_info['poll_fail']
				entry_count = feed_info['entry_count']
			if entry_count==0: #this is a good indication that the cache is bad
				feed_info   = self.db.get_feed_verbose(feed_id)
				unviewed    = feed_info['unread_count']
				flag        = feed_info['important_flag']
				pollfail    = feed_info['poll_fail']
				entry_count = feed_info['entry_count']
				
			if self.feedlist[i][FLAG]!=0:
				flag = self.feedlist[i][FLAG] #don't overwrite flag (race condition)
				
			if unviewed == 0 and flag & ptvDB.F_UNVIEWED:
				print "WARNING: zero unread articles but flag says there should be some"
				flag -= ptvDB.F_UNVIEWED
			
			m_title = self._get_markedup_title(title,flag) 
			m_readinfo = self._get_markedup_title("(%d/%d)" % (unviewed,entry_count), flag)
			icon = self._get_icon(flag)	
			
			if pollfail:
 				if icon=='gtk-harddisk' or icon=='gnome-stock-blank':
 					icon='gtk-dialog-error'
			visible = self.feedlist[i][VISIBLE]
			self.feedlist[i] = [title, m_title, feed_id, icon, m_readinfo, unviewed, entry_count, flag, visible, pollfail]
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
				self.va.set_value(self.va.lower)
			else:
				selection.select_path((index,))
		self.do_filter()
		if callback is not None:
			callback()
		yield False
		
	def add_feed(self, feed_id):
		newlist = self.db.get_feedlist()
		index = [f[0] for f in newlist].index(feed_id)
		feed = newlist[index]
		self.feedlist.insert(index,[feed[1], feed[1], feed[0], 'gnome-stock-blank', "", 1, 1, 0, True, False])
		self.update_feed_list(feed_id)
		
	def remove_feed(self, feed_id):
		try:
			self.feedlist.remove(self.feedlist.get_iter((self.find_index_of_item(feed_id),)))
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
		
	def update_feed_list(self, feed_id=None, update_what=None, update_data=None, recur_ok=True):  #returns True if this is the already-displayed feed
		"""updates the feed list.  Right now uses db to get flags, entrylist (for unread count), pollfail
	
		We should just get the flag, unread count, and poll fail, and then figure out:
		   icon, markup, and numbers
		   
		update_data would be a dic with unreadcount, flag list, and pollfail
		
		update_what is a bunch of strings saying what we want to update.  it will go to the
		db for info unless the value is already in update_data"""
		
		if feed_id is None:
			if self.last_feed is None:
				return
			feed_id = self.last_feed
			
		if update_what is None:
			update_what = ['readinfo','icon','pollfail','title']
		if update_data is None:
			update_data = {}
		
		try:
			feed = self.feedlist[self.find_index_of_item(feed_id)]
		except:
			print "error getting feed", feed_id, self.find_index_of_item(feed_id)
			return
			
		need_filter = False #some updates will require refiltering. 
		
		if 'pollfail' not in update_what or len(update_what)>1:
			#or in the converse, if pollfail in what and len is one, we don't need to do this
			
			if update_data.has_key('flag_list')==False:
				entrylist = self.db.get_entrylist(feed_id)
				if entrylist:
					update_data['flag_list'] = self.db.get_entry_flags(feed_id)
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
			
		if 'pollfail' in update_what:	
			if not update_data.has_key('pollfail'):
				update_data['pollfail'] = self.db.get_feed_poll_fail(feed_id)
			feed[POLLFAIL] = update_data['pollfail']
			if feed[STOCKID]=='gtk-harddisk' or feed[STOCKID]=='gnome-stock-blank':
				feed[STOCKID]='gtk-dialog-error'
				
		if 'readinfo' in update_what:
			#db_unread_count = self.db.get_unread_count(feed_id) #need it always for FIXME below
			if not update_data.has_key('unread_count'):
				update_data['unread_count'] = self.db.get_unread_count(feed_id)#, db_unread_count)
			if update_data['unread_count'] > 0:
				if feed[FLAG] & ptvDB.F_UNVIEWED==0:
					feed[FLAG] = feed[FLAG] + ptvDB.F_UNVIEWED
			else:
				if feed[FLAG] & ptvDB.F_UNVIEWED:
					feed[FLAG] = feed[FLAG]-ptvDB.F_UNVIEWED
			feed[UNREAD]   = update_data['unread_count']
			feed[TOTAL]    = len(update_data['flag_list'])
			feed[READINFO] = self._get_markedup_title("("+str(update_data['unread_count'])+"/"+str(len(update_data['flag_list']))+")",flag)
			feed[MARKUPTITLE] = self._get_markedup_title(feed[TITLE],flag)
			#if unviewed != db_unread_count:
			#	print "correcting unread count"
			#	self.db.correct_unread_count(feed_id) #FIXME this shouldn't be necessary
			#	print "done"
			if self.filter_unread:
		 		if updated==1 and unviewed==0 and self.filter_test_feed(feed_id): #no sense testing the filter if we won't see it
					need_filter = True
					
		if 'title' in update_what:
			selected = self.get_selected()
			if not update_data.has_key('title'):
				update_data['title'] = self.db.get_feed_title(feed_id)
			feed[TITLE] = update_data['title']
			feed[MARKUPTITLE] = self._get_markedup_title(feed[TITLE],flag)
			#may need to resort the feed list
			try:
				old_iter = self.feedlist.get_iter((self.find_index_of_item(feed_id),))
				new_iter = self.feedlist.get_iter(([f[0] for f in self.db.get_feedlist()].index(feed_id),))
				self.feedlist.move_after(old_iter,new_iter)
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
			
		if need_filter and not self.showing_search:
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
		item = self.get_selected(selection)
		self.last_feed=item
		if item:
			if self.showing_search:
				if item == self.last_selected:
					return
				self.last_selected = item
				if not self._app.entrylist_selecting_right_now():
					highlight_count = self._app.highlight_entry_results(item)
					if highlight_count == 0:
						self._app.display_feed(item)
				return
			if item == self.last_selected:
				self._app.display_feed(item)
			else:
				self.last_selected = item
				self._app.display_feed(item, -2)
				if self.selecting_misfiltered == True and item!=None:
					self.selecting_misfiltered = False
					gobject.timeout_add(250, self.do_filter)
			try:
				if self.feedlist[self.find_index_of_item(item)][POLLFAIL] == True:
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
		#list = [feed[FEEDID] for feed in self.feedlist]
		try:
			i=-1
			for feed in self.feedlist:
				i+=1
				if feed_id == feed[FEEDID]:
					return i
			#return list.index(feed_id)
			return None
		except:
			return None
			
	def get_feed_cache(self):
		return [[f[FEEDID],f[FLAG],f[UNREAD],f[TOTAL]] for f in self.feedlist]
		
	def interrupt(self):
		self.cancel_load = True
		
