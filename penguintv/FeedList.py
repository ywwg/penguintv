import gtk
import gobject
import penguintv
import ptvDB
import utils


ALL=0
DOWNLOADED=1
ACTIVE=2
NONE=3
UNKNOWN=4
BUILTIN_TAGS=[_("All Feeds"),_("Downloaded Media"),_("Active Downloads"),_("No Feeds (Calm Mode)")]

TITLE=0
MARKUPTITLE=1
FEEDID=2
STOCKID=3
READINFO=4
FLAG=5
VISIBLE=6
POLLFAIL=7

class FeedList:
	def __init__(self, widget_tree, app, db):
		self.scrolled_window = widget_tree.get_widget('scrolledwindow2')
		self.va = self.scrolled_window.get_vadjustment()
		self._widget = widget_tree.get_widget('feedlistview')
		self.entry_list_widget = widget_tree.get_widget('entrylistview')
		self._app = app
		self.feedlist = gtk.ListStore(str, str, int, str, str, int, bool, bool) #title, markuptitle, feed_id, stock_id, readinfo, flag, visible, pollfail
		self.feed_filter = self.feedlist.filter_new()
		self.feed_filter.set_visible_column(VISIBLE)
		self.db = db
		self.last_selected=None
		self.last_feed=None
		self.filter_setting=ALL
		self.filter_name = _("All Feeds")
		self.selecting_misfiltered=False
		self.filter_unread = False
		
		#build list view
		self._widget.set_model(self.feed_filter)
		renderer = gtk.CellRendererText()
		icon_renderer = gtk.CellRendererPixbuf()
		self.feed_column = gtk.TreeViewColumn('Feeds')
		self.feed_column.set_resizable(True)
		self.feed_column.pack_start(icon_renderer, False)
		self.feed_column.pack_start(renderer, True)
		self.feed_column.set_attributes(renderer, markup=MARKUPTITLE)
		self.feed_column.set_attributes(icon_renderer, stock_id=STOCKID)
		self._widget.append_column(self.feed_column)
			
		renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn('Articles')
		column.set_resizable(True)
		column.pack_start(renderer, True)
		column.set_attributes(renderer, markup=READINFO)		
		self._widget.append_column(column)
		
		self._widget.columns_autosize()
		
		#signals
		self._widget.get_selection().connect("changed", self.item_selection_changed)
				
	def resize_columns(self):
		self._widget.columns_autosize()
		
	def set_filter(self, new_filter, name):
		self.filter_setting = new_filter
		self.filter_name = name
		self.do_filter()
		self.va.set_value(0)
		self.resize_columns()
		
	def set_unread_toggle(self, active):
		self.filter_unread = active
		self.do_filter(False)
		self.va.set_value(0)
		
	def do_filter(self,keep_misfiltered=True):
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
					for tag in tags:
						if tag == self.filter_name:
							passed_filter = True
							break
			#so now we know if we passed the main filter, but not the unviewed filter
			if i == index and selected is not None:  #if it's the selected feed, we have to be careful
				if self.filter_unread == True and flag & ptvDB.F_UNVIEWED==0: #if it still fails the unviewed test
					if self.filter_setting != NONE and keep_misfiltered==True:    # except with NONE and also not if overridden
						passed_filter = True  #keep it
						self.selecting_misfiltered=True
					else:
						passed_filter = False  #otherwise lose it
				if self.filter_setting == DOWNLOADED and flag & ptvDB.F_DOWNLOADED == 0 and flag & ptvDB.F_PAUSED:
					if keep_misfiltered==True:
						passed_filter = True
						self.selecting_misfiltered = True
					else:
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
		flag = self.feedlist[self.find_index_of_item(feed_id)][FLAG]
		
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
				for tag in tags:
					if tag == self.filter_name:
						passed_filter = True
						break
		return passed_filter
		
	def populate_feeds(self):
		"""With 100 feeds, this is starting to get slow (2-3 seconds)"""
		#FIXME:  better way to get to the status display?
		#self._app.main_window.display_status_message(_("Loading Feeds..."))
		#while gtk.events_pending():
		#	gtk.main_iteration()
	#	if blocking:
	#		while self._populate_feeds_generator().next():
	#			pass
	#	else:
	#		gobject.idle_add(self._populate_feeds_generator().next)
		#self._app.main_window.display_status_message("")
	#	return False #in case this was called by the timeout below
	#disable the generator thang for a while.  Eventually I'll need a way
	#to update the list without screwing everything up
	#def _populate_feeds_generator(self):
		db_feedlist = self.db.get_feedlist()
		selection = self._widget.get_selection()
		selected = self.get_selected()
		self.feedlist.clear()
		
		i=-1
		downloaded=0
				
		for feed_id,title in db_feedlist:
			i=i+1
			unviewed=0
			
			entry_info = self.db.get_feed_verbose(feed_id)
			entrylist = entry_info['entry_list']
			unviewed  = entry_info['unread_count']
			flag      = entry_info['important_flag']
			pollfail  = entry_info['poll_fail']
			
			m_title = self.get_markedup_title(title,flag) 
			m_readinfo = self.get_markedup_title("("+str(unviewed)+"/"+str(len(entrylist))+")", flag)
			icon = self.get_icon(flag)	

 			if pollfail:
 				if icon=='gtk-harddisk' or icon=='gnome-stock-blank':
 					icon='gtk-dialog-error'
			self.feedlist.append([title, m_title, feed_id, icon, m_readinfo, flag, True, pollfail]) #assume visible
			#self.do_filter()
	#		yield True
		
		if selected:
			index = self.find_index_of_item(selected)
			selection.select_path((index,))
			if index<0:
				self.va.set_value(self.va.lower)
		#	self.do_filter(index)	
		#else:
		self.do_filter()	
	#	yield False
		return False
				
	def get_icon(self, flag):
		if flag & ptvDB.F_ERROR == ptvDB.F_ERROR:
			return 'gtk-dialog-error'
		if flag & ptvDB.F_DOWNLOADING == ptvDB.F_DOWNLOADING:
			return 'gtk-execute'
		if flag & ptvDB.F_DOWNLOADED == ptvDB.F_DOWNLOADED:
			return 'gtk-harddisk'
		if flag & ptvDB.F_PAUSED:
			return 'gtk-media-pause'
		return 'gnome-stock-blank'
	
	def get_markedup_title(self, title, flag):
		if not title:
			return _("Please wait...")
		if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
				title="<b>"+utils.my_quote(title)+"</b>"
		return title
		
	def update_feed_list(self, feed_id=None, update_data=None):  #returns True if this is the already-displayed feed
		"""updates the feed list.  Right now uses db to get flags, entrylist (for unread count), pollfail
	
		We should just get the flag, unread count, and poll fail, and then figure out:
		   icon, markup, and numbers
		   
		update_data would be a dic with unreadcount, flag list, and pollfail"""
		   
		if feed_id is None:
			if self.last_feed is None:
				return
			feed_id = self.last_feed
			
		if update_data is None:
			db_unread_count = self.db.get_unread_count(feed_id)
			entrylist = self.db.get_entrylist(feed_id)
			if entrylist:
				flag_list = []
				for entry in entrylist:
					flag = self.db.get_entry_flags(entry[0])
					flag_list.append(flag)
			poll_fail = self.db.get_feed_poll_fail(feed_id)
		else:
			db_unread_count = update_data['unread_count']
			flag_list = update_data['flag_list']
			poll_fail = update_data['pollfail']
			
		updated=0
		unviewed=0
		downloaded=0
		active=0
	 	try:
	 	 	feed = self.feedlist[self.find_index_of_item(feed_id)]
 		except:
			print "error getting feed"
			return
		updated=1
		for flag in flag_list:
			if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
				unviewed=unviewed+1
			if flag & ptvDB.F_DOWNLOADED or flag & ptvDB.F_PAUSED:
				downloaded=1
			if flag & ptvDB.F_DOWNLOADING:
				active=1

		flag = self.pick_important_flag(feed_id, flag_list)
		feed[MARKUPTITLE] = self.get_markedup_title(feed[TITLE],flag)
		feed[READINFO] = self.get_markedup_title("("+str(unviewed)+"/"+str(len(flag_list))+")",flag)
		feed[STOCKID] = self.get_icon(flag)
				
									
		if unviewed != db_unread_count:
			self.db.correct_unread_count(feed_id) #FIXME this shouldn't be necessary

		if poll_fail:
			if feed[STOCKID]=='gtk-harddisk' or feed[STOCKID]=='gnome-stock-blank':
				feed[STOCKID]='gtk-dialog-error'
		#print "icon is:"+str(feed[STOCKID])
		feed[FLAG] = flag	 
		feed[POLLFAIL] = poll_fail			

	 	if self.filter_unread:
	 		if updated==1 and unviewed==0 and self.filter_test_feed(feed_id): #no sense testing the filter if we won't see it anyway
	 			#print "doing filter"
				self.do_filter()
	 	if self.filter_setting == DOWNLOADED:
	 		if updated==1 and downloaded==0:
		 		self.do_filter()
		if self.filter_setting == ACTIVE:
	 		if updated==1 and active==0:
		 		self.do_filter()
# we know always repopulate since it's faster
		if feed_id == self.last_feed:
			return True
		
	def pick_important_flag(self, feed_id, flag_list):
		"""go through entries and pull out most important flag"""
		if len(flag_list)==0:
			return 0

		entry_count = len(flag_list)
		important_flag = 0
		media_exists = 0
		for flag in flag_list:
			if flag & ptvDB.F_DOWNLOADED == ptvDB.F_DOWNLOADED:
				media_exists=1
		flag_list.sort()
		best_flag = flag_list[-1]
		if best_flag & ptvDB.F_DOWNLOADED == 0 and media_exists==1: #if there is an unread text-only entry, but all viewed media,
																	#we need a special case (mixing flags from different entries)
			return best_flag + ptvDB.F_DOWNLOADED
		else:
			return best_flag
			
	def item_selection_changed(self, selection):
		item = self.get_selected(selection)
		self.last_feed=item
		if item:
			if item == self.last_selected:
				self._app.display_feed(item)
			else:
				self.last_selected = item
				self._app.display_feed(item, -2)
				if self.selecting_misfiltered == True and item!=None:
					self.selecting_misfiltered = False
					gobject.timeout_add(250, self.populate_feeds) #update in just a bit so people can see the change
			if self.feedlist[self.find_index_of_item(item)][POLLFAIL] == True:
				self._app.display_custom_entry("<b>"+_("There was an error trying to poll this feed.")+"</b>")
				return
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
		if index >= 0:
			self._widget.get_selection().select_path((index,))
			self._widget.scroll_to_cell((index,))
		else:
			self._widget.get_selection().unselect_all()
			
	def find_index_of_item(self, feed_id):
		list = [feed[FEEDID] for feed in self.feedlist]
		try:
			return list.index(feed_id)
		except:
			return -1
		
