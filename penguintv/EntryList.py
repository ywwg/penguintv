import string
import logging
import time

import gtk, gobject
import ptvDB
import penguintv

TITLE         = 0 
MARKEDUPTITLE = 1
ENTRY_ID      = 2
INDEX         = 3
ICON          = 4
FLAG          = 5
FEED          = 6
VISIBLE       = 7

S_DEFAULT = 0
S_SEARCH  = 1
#S_ACTIVE  = 2

class EntryList(gobject.GObject):
	
	__gsignals__ = {
        'entry-selected': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_INT])),
        'search-entry-selected': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_INT, gobject.TYPE_PYOBJECT])),
       	'link-activated': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
		'no-entry-selected': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           []),
		'entrylist-resized': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT]))
    }	
	
	def __init__(self, widget_tree, app, feed_list_view, main_window):
		gobject.GObject.__init__(self)
		self._widget = widget_tree.get_widget("entrylistview")
		self._main_window = main_window
		self._entrylist = gtk.ListStore(str, str, int, int, str, int, int, bool) #title, markeduptitle, entry_id, index, icon, flag, feed, visible
		self._app = app
		self._feed_id=None
		self._last_entry=None
		self._search_query = ""
		self._search_results = []
		self._state = S_DEFAULT
		self._hide_viewed = False
		self.__populating = False
		self.__cancel_populating = False
		self.presently_selecting = False
		
		#build list view
		
		self._entry_filter = self._entrylist.filter_new()
		self._entry_filter.set_visible_column(VISIBLE)
		self._widget.set_model(self._entry_filter)
		
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
		self._widget.connect("button-press-event", self._on_button_press_event)
		
		self._handlers = []
		h_id = feed_list_view.connect('feed-selected', self.__feedlist_feed_selected_cb)
		self._handlers.append((feed_list_view.disconnect, h_id))
		h_id = feed_list_view.connect('search-feed-selected', self.__feedlist_search_feed_selected_cb)
		self._handlers.append((feed_list_view.disconnect, h_id))
		h_id = feed_list_view.connect('no-feed-selected', self.__feedlist_none_selected_cb)
		self._handlers.append((feed_list_view.disconnect, h_id))
		h_id = app.connect('feed-polled', self.__feed_polled_cb)
		self._handlers.append((app.disconnect, h_id))
		h_id = app.connect('feed-removed', self.__feed_removed_cb)
		self._handlers.append((app.disconnect, h_id))
		h_id = app.connect('entry-updated', self.__entry_updated_cb)
		self._handlers.append((app.disconnect, h_id))
		h_id = app.connect('state-changed', self.__state_changed_cb)
		self._handlers.append((app.disconnect, h_id))
		h_id = app.connect('entries-viewed', self.__entries_viewed_cb)
		self._handlers.append((app.disconnect, h_id))
		h_id = app.connect('entries-unviewed', self.__entries_viewed_cb)
		self._handlers.append((app.disconnect, h_id))
		
	def finalize(self):
		for disconnector, h_id in self._handlers:
			disconnector(h_id)
			
	def set_entry_view(self, entry_view):
		h_id = entry_view.connect('entries-viewed', self.__entries_viewed_cb)
		self._handlers.append((entry_view.disconnect, h_id))
		
	def __feedlist_feed_selected_cb(self, o, feed_id):
		self.populate_entries(feed_id)
		
	def __feedlist_search_feed_selected_cb(self, o, feed_id):
		for e in self._entrylist:
			if e[FEED] == feed_id:
				e[VISIBLE] = True
			else:
				e[VISIBLE] = False
		
	def __feedlist_none_selected_cb(self, o):
		if self._state == S_SEARCH:
			for e in self._entrylist:
				e[VISIBLE] = True
		else:
			self.populate_entries(None)
		
	def __feed_polled_cb(self, app, feed_id, update_data):
		feed_list = self._app.db.get_associated_feeds(feed_id)
		if self._feed_id in feed_list:
			self.update_entry_list()
			
	def __feed_removed_cb(self, app, feed_id):
		if feed_id == self._feed_id:
			self.clear_entries()
			
	def __entry_updated_cb(self, app, entry_id, feed_id):
		self.update_entry_list(entry_id)
		
	def __entries_viewed_cb(self, app, viewlist):
		for feed_id, entrylist in viewlist:
			feed_list = self._app.db.get_associated_feeds(feed_id)
			if self._feed_id in feed_list:
				for e in entrylist:
					self.update_entry_list(e)
					
	def populate_if_selected(self, feed_id):
		if feed_id == self._feed_id:
			self.populate_entries(feed_id, -1)
			
	def populate_entries(self, feed_id, selected=-1):
		if self._state == S_SEARCH:
			if len(self._search_results) > 0: 
				if feed_id in [s[1] for s in self._search_results]:
					self.show_search_results(self._search_results, self._search_query)
					#self.highlight_results(feed_id)
					return
					
		if self.__populating:
			self.__cancel_populating = True
			while gtk.events_pending():
				gtk.main_iteration()
	
		if feed_id == self._feed_id:
			dont_autopane = True 
		else:
			dont_autopane = False #it's a double negative, but it makes sense to me at the moment.
		self._feed_id = feed_id
		
		
		db_entrylist = self._app.db.get_entrylist(feed_id)
		if self._hide_viewed:
			unviewed = self._app.db.get_unread_entries(feed_id)
			db_entrylist = [e for e in db_entrylist if e[0] in unviewed]
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
		self.emit('no-entry-selected')
		
		def populate_gen():
			self.__populating = True
			i=-1
			for entry_id,title,date,read,placeholder in db_entrylist:
				if self.__cancel_populating:
					self.__cancel_populating = False
					break
				i=i+1	
				flag = self._app.db.get_entry_flag(entry_id)
				icon = self._get_icon(flag)
				markeduptitle = self._get_markedup_title(title, flag)
				self._entrylist.append([title, markeduptitle, entry_id, i, icon, flag, feed_id, True])
				if i % 100 == 99:
					#gtk.gdk.threads_leave()
					yield True
				if i == 25 and not dont_autopane: #ie, DO auto_pane please
					#this way we don't push the list way out because 
					#of something we can't even see
					gobject.idle_add(self.auto_pane)
					#gtk.gdk.threads_leave()
					yield True
			if not self.__cancel_populating:
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
			self.__populating = False
			yield False
		if len(db_entrylist) > 300: #only use an idler when the list is getting long
			gobject.idle_add(populate_gen().next)
		else:
			for i in populate_gen():
				if not i: #said the cat
					return
		
	def auto_pane(self):
		"""Automatically adjusts the pane width to match the column width"""
		#If the second column exists, this cause the first column to shrink,
		#and then we can set the pane to the same size
		
		column = self._widget.get_column(0)
		new_width = column.get_width()+10
		
		self.emit('entrylist-resized', new_width)
		
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
			if len(self._entrylist) != len(self._app.db.get_entrylist(self._feed_id)):
				self.populate_entries(self._feed_id)
				return
			for entry in self._entrylist:
				entry[FLAG] = self._app.db.get_entry_flag(entry[ENTRY_ID])
		 		entry[MARKEDUPTITLE] = self._get_markedup_title(entry[TITLE],entry[FLAG])
		 		entry[ICON] = self._get_icon(entry[FLAG]) 
		else:
			try:
				index = self.find_index_of_item(entry_id)
				if index is not None:
					entry = self._entrylist[index]
					entry[FLAG] = self._app.db.get_entry_flag(entry_id)
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
		"""Only show the first hundred SEARCHENGINE IS IN CHARGE OF THAT"""
		self._search_query = query
		if entries is None:
			entries = []
		self._search_results = entries
		self._entrylist.clear()
		if len(entries) == 0:
			self.emit('no-entry-selected')
			return
			
		self._hide_viewed = False
		self._main_window.set_hide_entries_menuitem(self._hide_viewed)
		self._main_window.set_hide_entries_visibility(False)
		
		i=-1

		for entry_id,title, fakedate, feed_id in entries:	
			i+=1
			try:
				entry = self._app.db.get_entry(entry_id)
			except ptvDB.NoEntry:
				raise ptvDB.BadSearchResults, "Entry not found, possible out of date index"
			flag = self._app.db.get_entry_flag(entry_id)
			icon = self._get_icon(flag)
			markeduptitle = self._get_markedup_title(entry['title'], flag)
			self._entrylist.append([entry['title'], markeduptitle, entry_id, i, icon, flag, feed_id, True])
			
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
	
	def __state_changed_cb(self, app, newstate, data=None):
		d = {penguintv.DEFAULT: S_DEFAULT,
			 penguintv.MANUAL_SEARCH: S_SEARCH,
			 penguintv.TAG_SEARCH: S_SEARCH,
			 #penguintv.ACTIVE_DOWNLOADS: S_ACTIVE,
			 penguintv.MAJOR_DB_OPERATION: S_DEFAULT}
			 
		newstate = d[newstate]
		
		if newstate == self._state:
			return
			
		self._unset_state()
		self._state = newstate
		
	def _on_button_press_event(self, widget, event):
		if event.button==3: #right click
			self.do_context_menu(event)
		
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
		
		if selected['entry_id'] != self._last_entry:	
			self._last_entry = selected['entry_id']
			#print "selected item: "+str(selected) #CONVENIENT
			#if self._showing_search:
		
			if selection.count_selected_rows()==1:
				if self._state == S_SEARCH:
					self.emit('search-entry-selected', selected['entry_id'], selected['feed_id'], self._search_query)
				else:
					self.emit('entry-selected', selected['entry_id'], selected['feed_id'])
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
		
	def get_selected_id(self, selection=None):
		selected = self.get_selected(selection)
		if selected is None:
			return 0
		else:
			return selected['entry_id']
			
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
		item = self._app.db.get_entry(model[index][ENTRY_ID])
		self.emit('link-activated', item['link'])
		
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
			if selected['flag'] & ptvDB.F_DOWNLOADED == 0:
				item = gtk.ImageMenuItem(_("_Download"))
				img = gtk.image_new_from_stock('gtk-go-down',gtk.ICON_SIZE_MENU)
				item.set_image(img)
				item.connect('activate',self._main_window.on_download_entry_activate)
				menu.append(item)
			else:
				item = gtk.ImageMenuItem(_("_Re-Download"))
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
			
		keep = self._app.db.get_entry_keep(selected['entry_id'])
		if keep:
			item = gtk.MenuItem(_("_Don't Keep New"))
			item.connect('activate',self._main_window.on_unkeep_entry_new_activate)
			menu.append(item)
		else:
			item = gtk.MenuItem(_("_Keep New"))
			item.connect('activate',self._main_window.on_keep_entry_new_activate)
			menu.append(item)
			
		if self._state != S_SEARCH:
			if self._hide_viewed:
				item = gtk.MenuItem(_("_Show All"))
				item.connect('activate', self._toggle_hide_viewed)
				menu.append(item)
			else:
				item = gtk.MenuItem(_("_Hide Viewed Entries"))
				item.connect('activate', self._toggle_hide_viewed)
				menu.append(item)
			
		menu.show_all()
		menu.popup(None,None,None, event.button,event.time)
		
	def set_hide_viewed(self, state):
		if state == self._hide_viewed:
			return
				
		self._toggle_hide_viewed()
		
	def _toggle_hide_viewed(self, e=None):
		if self._hide_viewed:
			self._hide_viewed = False
		else:
			self._hide_viewed = True
		self._main_window.set_hide_entries_menuitem(self._hide_viewed)
		self.populate_entries(self._feed_id)
