import gtk, gobject
import ptvDB
import penguintv

import string
import traceback

TITLE         = 0 
MARKEDUPTITLE = 1
ENTRY_ID      = 2
INDEX         = 3
ICON          = 4
FLAG          = 5
FEED          = 6

S_DEFAULT = 0
S_SEARCH  = 1
#S_ACTIVE  = 2

class EntryList:
	def __init__(self, widget_tree, app, main_window, entry_view, db):
		self._widget = widget_tree.get_widget("entrylistview")
		self._app = app
		self._main_window = main_window
		self._entry_view = entry_view
		self._entrylist = gtk.ListStore(str, str, int, int, str, int, int) #title, markeduptitle, entry_id, index, icon, flag, feed
		self._db = db
		self._feed_id=None
		self._last_entry=None
		self._search_query = ""
		self._search_results = []
		self._state = S_DEFAULT
		self.presently_selecting = False
		
		
		#build list view
		self._widget.set_model(self._entrylist)
		
		icon_renderer = gtk.CellRendererPixbuf()
		renderer = gtk.CellRendererText()
		self._vadjustment = widget_tree.get_widget("entry_scrolled_window").get_vadjustment()
		self._hadjustment = widget_tree.get_widget("entry_scrolled_window").get_hadjustment()
		column = gtk.TreeViewColumn(_('Articles'))
		column.pack_start(icon_renderer, False)
		column.pack_start(renderer, True)
		column.set_attributes(icon_renderer, stock_id=4)
		column.set_attributes(renderer, markup=1)
		#column.set_property("sizing", gtk.TREE_VIEW_COLUMN_GROW_ONLY) #AUTOSIZE or GROW_ONLY or FIXED
		self._widget.append_column(column)
		
		#If you want to grow _and_ shrink, start uncommenting and switch above to autosize
		column = gtk.TreeViewColumn('') 
		#column.set_property("resizable", False)
		#column.set_property("sizing", gtk.TREE_VIEW_COLUMN_AUTOSIZE)
		self._widget.append_column(column)
		
		self._widget.columns_autosize()
		self._widget.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		
		#signals
		self._widget.get_selection().connect("changed", self.item_selection_changed)
		self._widget.connect("row-activated", self.on_row_activated)
		
	def populate_if_selected(self, feed_id):
		if feed_id == self._feed_id:
			self.populate_entries(feed_id, -1)
			
	def populate_entries(self, feed_id, selected=-1):
		if self._state == S_SEARCH:
#		if self._showing_search:
			if len(self._search_results) > 0: 
				if feed_id in [s[1] for s in self._search_results]:
					self.show_search_results(self._search_results, self._search_query)
					self.highlight_results(feed_id)
					return
	
		if feed_id == self._feed_id:
			dont_autopane = True 
		else:
			dont_autopane = False #it's a double negative, but it makes sense to me at the moment.
		self._feed_id = feed_id
		
		db_entrylist = self._db.get_entrylist(feed_id)
		selection = self._widget.get_selection()
		if selected==-1:
			rows = selection.get_selected_rows()
			if len(rows[1]) > 0:
				item = rows[0][rows[1][-1]]
				try:
					selected=item[ENTRY_ID]			
					index = item[INDEX]
				except Exception,e:
					print e
					print "rows: ",rows," item:",item
		self._entrylist.clear()
		#self._app.display_custom_entry("")
		self._app.display_entry(None)
		
		def populate_gen():
			i=-1
			for entry_id,title,date,read,placeholder in db_entrylist:
				i=i+1	
				flag = self._db.get_entry_flag(entry_id)
				icon = self._get_icon(flag)
				markeduptitle = self._get_markedup_title(title, flag)
				self._entrylist.append([title, markeduptitle, entry_id, i, icon, flag, feed_id])
				if i % 100 == 99:
					yield True
				if i == 25 and not dont_autopane: #ie, DO auto_pane please
					#this way we don't push the list way out because 
					#of something we can't even see
					gobject.idle_add(self.auto_pane)
					yield True
			if i<25 and not dont_autopane: #ie, DO auto_pane please
				gobject.idle_add(self.auto_pane)
			self._vadjustment.set_value(0)
			self._hadjustment.set_value(0)
			if selected>=0:
				index = self.find_index_of_item(selected)
				if index is not None:
					selection.select_path((index),)
				else:	
					selection.unselect_all()
			self._widget.columns_autosize()
			
			#if not dont_autopane:
			#	self._app.display_entry(None)
			
			yield False
		if len(db_entrylist) > 300: #only use an idler when the list is getting long
			gobject.idle_add(populate_gen().next)
		else:
			for i in populate_gen():
				pass
		
	def auto_pane(self):
		"""Automatically adjusts the pane width to match the column width"""
		#If the second column exists, this cause the first column to shrink,
		#and then we can set the pane to the same size
		if self._main_window.layout == "widescreen" and self._main_window.app_window is not None:			
			column = self._widget.get_column(0)
			new_width = column.get_width()+10
			listnview_width = self._main_window.app_window.get_size()[0] - self._main_window.feed_pane.get_position()
			if listnview_width - new_width < 400: #ie, entry view will be tiny
				self._main_window.entry_pane.set_position(listnview_width-400) #MAGIC NUMBER
			elif new_width > 20: #MAGIC NUMBER
				self._main_window.entry_pane.set_position(new_width)
		return False
		
	def _get_icon(self, flag):
		""" This would be a nice place to drop in custom icons """
		if flag & ptvDB.F_ERROR:
			return 'gtk-dialog-error'
		if flag & ptvDB.F_DOWNLOADING:
			return 'gtk-execute'
		if flag & ptvDB.F_DOWNLOADED:
			return 'gtk-harddisk'
		if flag & ptvDB.F_PAUSED:
			return 'gtk-media-pause'
		else:
			return 'gnome-stock-blank'
	
	def _get_markedup_title(self, title, flag):
		if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
			title="<b>"+title+"</b>"
		if flag & ptvDB.F_MEDIA == ptvDB.F_MEDIA:
			title="<span color='Blue'>"+title+"</span>"
		title = string.replace(title,"\n"," ")
		return title
		
	def update_entry_list(self, entry_id=None):
		if entry_id is None:
			if len(self._entrylist) != len(self._db.get_entrylist(self._feed_id)):
				self.populate_entries(self._feed_id)
				return
			for entry in self._entrylist:
				entry[FLAG] = self._db.get_entry_flag(entry[ENTRY_ID])
		 		entry[MARKEDUPTITLE] = self._get_markedup_title(entry[TITLE],entry[FLAG])
		 		entry[ICON] = self._get_icon(entry[FLAG]) 
		else:
			try:
				index = self.find_index_of_item(entry_id)
				if index is not None:
					entry = self._entrylist[index]
					entry[FLAG] = self._db.get_entry_flag(entry_id)
				 	entry[MARKEDUPTITLE] = self._get_markedup_title(entry[TITLE],entry[FLAG])
					entry[ICON] = self._get_icon(entry[FLAG]) 
				else:
					return
			except:
				#we aren't even viewing this feed
				return
				
		if entry_id == self._last_entry:
			return True
			
	def mark_as_viewed(self, entry_id=None):
		index = self.find_index_of_item(entry_id)
		if index is not None:
			entry = self._entrylist[index]
			if entry[FLAG] & ptvDB.F_UNVIEWED:
				entry[FLAG] -= ptvDB.F_UNVIEWED
				entry[MARKEDUPTITLE] = self._get_markedup_title(entry[TITLE],entry[FLAG])
		 		entry[ICON] = self._get_icon(entry[FLAG])
			
	def show_search_results(self, entries, query):
		"""Only show the first hundred LUCENE IS IN CHARGE OF THAT"""
		self._search_query = query
		if entries is None:
			entries = []
		self._search_results = entries
		self._entrylist.clear()
		if len(entries) == 0:
			self._app.display_entry(None)
			return
		
		i=-1
		for entry_id,title, fakedate, readinfo, feed_id in entries:	
			i+=1
			try:
				entry = self._db.get_entry(entry_id)
			except ptvDB.NoEntry:
				raise ptvDB.BadSearchResults, "Entry not found, possible out of date index"
			flag = self._db.get_entry_flag(entry_id)
			icon = self._get_icon(flag)
			markeduptitle = self._get_markedup_title(entry['title'], flag)
			self._entrylist.append([entry['title'], markeduptitle, entry_id, i, icon, flag, feed_id])
			
		self._vadjustment.set_value(0)
		self._hadjustment.set_value(0)
		self._widget.columns_autosize()
		gobject.idle_add(self.auto_pane)
		
	def _unset_state(self):
		if self._state == S_SEARCH:
			self._search_query = ""
			self._widget.get_selection().unselect_all()
			self._search_results = []
			self._entrylist.clear()
	
	def set_state(self, newstate, data=None):
		d = {penguintv.DEFAULT: S_DEFAULT,
			 penguintv.MANUAL_SEARCH: S_SEARCH,
			 penguintv.TAG_SEARCH: S_SEARCH,
			 #penguintv.ACTIVE_DOWNLOADS: S_ACTIVE,
			 penguintv.LOADING_FEEDS: S_DEFAULT}
			 
		newstate = d[newstate]
		
		if newstate == self._state:
			return
			
		#print "what"
		#if newstate == S_ACTIVE:
		#	print "active downloads already!"
		
		self._unset_state()
		self._state = newstate
		
	def highlight_results(self, feed_id):
		selection = self._widget.get_selection()
		selection.unselect_all()
		i=-1
		j=0
		first=-1
		first_in_range = -1
		last_selected = -1
		for e in self._entrylist:
			i+=1
			if e[FEED] == feed_id:
				j+=1			
				if first==-1:
					first = i
				if first_in_range == -1:
					first_in_range = i
					last_selected = i
					continue
				if last_selected == i-1:
					last_selected = i
				else:
					if last_selected == first_in_range:
						selection.select_path((last_selected,))
					else:
						selection.select_range((first_in_range,),(last_selected,))
					last_selected = -1
					first_in_range = -1

		if first_in_range!=-1:
			if last_selected == first_in_range:
				selection.select_path((last_selected,))
			else:
				selection.select_range((first_in_range,),(last_selected,))			
		
		count = j
		if count > 1:
			self._app.display_entry(None)
		if count > 0:
			self._widget.scroll_to_cell(first)
		return count
			
	def item_selection_changed(self, selection):
		self.presently_selecting = True
		try:
			selected = self.get_selected(selection) #then do something with it
		except:
			self.presently_selecting = False
			return
		if selected is None:
			self.presently_selecting = False
			return
		self._last_entry = selected['entry_id']
		#print "selected item: "+str(selected) #CONVENIENT
		#if self._showing_search:
		if self._state == S_SEARCH:
			self._app.select_feed(selected['feed_id'])
		if selection.count_selected_rows()==1:
			self._app.display_entry(selected['entry_id'], query=self._search_query)
		self.presently_selecting = False
			
	def get_selected(self, selection=None):
		if selection==None:
			s = self._widget.get_selection().get_selected_rows()
		else:	
			s = selection.get_selected_rows()
		if s[0] is None or len(s[1])==0:
			return None
		s = s[0][s[1][-1]]
		selected={ 'title': s[TITLE],
			   'markeduptitle':s[MARKEDUPTITLE],
			   'entry_id': s[ENTRY_ID],
			   'index': s[INDEX],
			   'icon': s[ICON],
			   'flag': s[FLAG],
			   'feed_id': s[FEED]}
		return selected
			
	def set_selected(self, entry_id):
		index = self.find_index_of_item(entry_id)
		if index is not None:
			self._widget.get_selection().select_path((index,))
		
	def clear_entries(self):
		self._entrylist.clear()
		
	def find_index_of_item(self, entry_id):
		list = [entry[ENTRY_ID] for entry in self._entrylist]
		try:
			return list.index(entry_id)
		except:
			return None
	
	def on_row_activated(self, treeview, path, view_column):
		index = path[0]
		model = treeview.get_model()
		item = self._db.get_entry(model[index][ENTRY_ID])
		self._app.activate_link(item['link'])
		
	def do_context_menu(self, event):
		"""pops up a context menu for the item where the mouse is positioned"""
		
		#we can't go by the selected item, because that changes _after_ this executes
		#so we find out what is selected based on mouse position
		path = self._widget.get_path_at_pos(int(event.x),int(event.y))
		if path is None: #nothing selected
			return
		index = path[0]
		selected={ 'title': self._entrylist[index][TITLE],
				   'markeduptitle':self._entrylist[index][MARKEDUPTITLE],
				   'entry_id': self._entrylist[index][ENTRY_ID],
				   'index': self._entrylist[index][INDEX],
				   'icon': self._entrylist[index][ICON],
				   'flag': self._entrylist[index][FLAG]}
		menu = gtk.Menu()   
		if selected['flag'] & ptvDB.F_MEDIA:
			item = gtk.ImageMenuItem(_("_Download"))
			img = gtk.image_new_from_stock('gtk-go-down',gtk.ICON_SIZE_MENU)
			item.set_image(img)
			item.connect('activate',self._main_window.on_download_entry_activate)
			menu.append(item)
			
			item = gtk.ImageMenuItem('gtk-media-play')
			item.connect('activate',self._main_window.on_play_entry_activate)
			menu.append(item)
			
			item = gtk.MenuItem(_("Delete"))
			item.connect('activate',self._main_window.on_delete_entry_media_activate)
			menu.append(item)
			
		if selected['flag'] & ptvDB.F_UNVIEWED:
			item = gtk.MenuItem(_("Mark as _Viewed"))
			item.connect('activate',self._main_window.on_mark_entry_as_viewed_activate)
			menu.append(item)
		else:
			item = gtk.MenuItem(_("Mark as _Unviewed"))
			item.connect('activate',self._main_window.on_mark_entry_as_unviewed_activate)
			menu.append(item)
			
		menu.show_all()
		menu.popup(None,None,None, event.button,event.time)
