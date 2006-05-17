import gtk, gobject
import ptvDB
import penguintv

import string

class EntryList:
	def __init__(self, widget_tree, app, main_window, db):
		self._widget = widget_tree.get_widget("entrylistview")
		self._app = app
		self.main_window = main_window
		self.entrylist = gtk.ListStore(str, str, int, int, str, int) #title, markeduptitle, entry_id, index, icon, flag
		self.db = db
		self.feed_id=None
		self.last_entry=None
		#self.context_menu_activate=False
		#self.context_event = None
		
		#build list view
		self._widget.set_model(self.entrylist)
		
		icon_renderer = gtk.CellRendererPixbuf()
		renderer = gtk.CellRendererText()
		self.vadjustment = widget_tree.get_widget("entry_scrolled_window").get_vadjustment()
		self.hadjustment = widget_tree.get_widget("entry_scrolled_window").get_hadjustment()
		column = gtk.TreeViewColumn('Entries')
		column.pack_start(icon_renderer, False)
		column.pack_start(renderer, True)
		column.set_attributes(icon_renderer, stock_id=4)
		column.set_attributes(renderer, markup=1)
		#column.set_property("sizing", gtk.TREE_VIEW_COLUMN_GROW_ONLY) #AUTOSIZE or GROW_ONLY or FIXED
		self._widget.append_column(column)
		
		#If you want to grow _and_ shrink, start uncommenting and switch above to autosize
		column = gtk.TreeViewColumn('Padding') 
		#column.set_property("resizable", False)
		#column.set_property("sizing", gtk.TREE_VIEW_COLUMN_AUTOSIZE)
		self._widget.append_column(column)
		
		self._widget.columns_autosize()
		
		#signals
		self._widget.get_selection().connect("changed", self.item_selection_changed)
		self._widget.connect("row-activated", self.on_row_activated)
		
	def populate_if_selected(self, feed_id):
		if feed_id == self.feed_id:
			self.populate_entries(feed_id, -1)
				
	def populate_entries(self, feed_id, selected=-1):
		if feed_id == self.feed_id:
			dont_autopane = True 
		else:
			dont_autopane = False #it's a double negative, but it makes sense to me at the moment.
		self.feed_id = feed_id
		db_entrylist = self.db.get_entrylist(feed_id)
		selection = self._widget.get_selection()
		if selected==-1:
			item = self.get_selected()
			selected=item['entry_id']
			index = item['index']
		self.entrylist.clear()
		
		i=-1
		for entry_id,title,date,new in db_entrylist:
			i=i+1	
			flag = self.db.get_entry_flag(entry_id)
			icon = self.get_icon(flag)
			markeduptitle = self.get_markedup_title(title, flag)
			self.entrylist.append([title, markeduptitle, entry_id, i, icon, flag])
		self.vadjustment.set_value(0)
		self.hadjustment.set_value(0)
		if selected>=0:
			index = self.find_index_of_item(selected)
			if index >= 0:
				selection.select_path((index),)
			else:	
				selection.unselect_all()
		self._widget.columns_autosize()
		if self.main_window.layout == "widescreen" and dont_autopane != True:
			gobject.idle_add(self.auto_pane)
		
	def auto_pane(self):
		"""Automatically adjusts the pane width to match the column width"""
		#If the second column exists, this cause the first column to shrink,
		#and then we can set the pane to the same size
		column = self._widget.get_column(0)
		new_width = column.get_width()+10
		listnview_width = self.main_window.app_window.get_size()[0] - self.main_window.feed_pane.get_position()
		if listnview_width - new_width < 300: #ie, entry view will be tiny
			self.main_window.entry_pane.set_position(listnview_width-300) #MAGIC NUMBER
		elif new_width > 20: #MAGIC NUMBER
			self.main_window.entry_pane.set_position(new_width)
		return False
		
	def get_icon(self, flag):
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
	
	def get_markedup_title(self, title, flag):
		if flag & ptvDB.F_UNVIEWED == ptvDB.F_UNVIEWED:
			title="<b>"+title+"</b>"
		if flag & ptvDB.F_MEDIA == ptvDB.F_MEDIA:
			title="<span color='Blue'>"+title+"</span>"
		title = string.replace(title,"\n"," ")
		return title
		
	def update_entry_list(self, entry_id=None):
		if entry_id is None:
			for entry in self.entrylist:
				entry[5] = self.db.get_entry_flag(entry[2])
		 		entry[1] = self.get_markedup_title(entry[0],entry[5])
		 		entry[4] = self.get_icon(entry[5]) 
		else:
			try:
				index = self.find_index_of_item(entry_id)
				entry = self.entrylist[index]
				entry[5] = self.db.get_entry_flag(entry_id)
			 	entry[1] = self.get_markedup_title(entry[0],entry[5])
				entry[4] = self.get_icon(entry[5]) 
			except:
				#we aren't even viewing this feed
				return #don't need to do any of the below
		#	if self.last_entry is None:
		#		return
		#	entry_id = self.last_entry
		
	 	#always update the selected entry, just in case.
	 	#this means the app updates the feeds and entries, but the 
	 	#entry list knows best when it comes to entries
		selection = self._widget.get_selection()
		selected = self.get_selected(selection)['entry_id']
		if selected:
			self._app.display_entry(selected, 0) #don't change read-state on this display, so if someone just marked this unread, it won't change right back 
		if entry_id == self.last_entry:
			return True
			
	def item_selection_changed(self, selection):	
		selected = self.get_selected(selection)['entry_id'] #then do something with it
		self.last_entry = selected
		#print "selected item: "+str(selected) #CONVENIENT
		if selected:
			self._app.display_entry(selected)
		else:
			self._app.display_entry(None)
			
	def get_selected(self, selection=None):
		if selection==None:
			s = self._widget.get_selection().get_selected()
		else:	
			s = selection.get_selected()
		selected={ 'title':None,
				   'markeduptitle':None,
				   'entry_id': 0,
				   'index': 0,
				   'icon': None,
				   'flag': 0}
		if s:
			model, iter = s
			if iter is None:
				return selected
			path = model.get_path(iter)
			index = path[0]
			#title, markeduptitle, entry_id, index, icon, flag
			selected={ 'title': model[index][0],
				   'markeduptitle':model[index][1],
				   'entry_id': model[index][2],
				   'index': model[index][3],
				   'icon': model[index][4],
				   'flag': model[index][5]}
			return selected
		else:
			return selected
			
	def set_selected(self, entry_id):
		index = self.find_index_of_item(entry_id)
		self._widget.get_selection().select_path((index,))
		
	def clear_entries(self):
		self.entrylist.clear()
		
	def find_index_of_item(self, entry_id):
		i=0
		for entry in self.entrylist:
			if entry[2] == entry_id:
				return i
			i=i+1
		return -1
	
	def on_row_activated(self, treeview, path, view_column):
		index = path[0]
		model = treeview.get_model()
		item = self.db.get_entry(model[index][2])
		self._app.activate_link(item['link'])
		
	def do_context_menu(self, event):
		"""pops up a context menu for the item where the mouse is positioned"""
		
		#we can't go by the selected item, because that changes after this executes
		#so we find out what is selected based on mouse position
		path = self._widget.get_path_at_pos(int(event.x),int(event.y))
		if path is None: #nothing selected
			return
		index = path[0]
		selected={ 'title': self.entrylist[index][0],
				   'markeduptitle':self.entrylist[index][1],
				   'entry_id': self.entrylist[index][2],
				   'index': self.entrylist[index][3],
				   'icon': self.entrylist[index][4],
				   'flag': self.entrylist[index][5]}
		menu = gtk.Menu()   
		if selected['flag'] & ptvDB.F_MEDIA:
			item = gtk.ImageMenuItem(_("_Download"))
			img = gtk.image_new_from_stock('gtk-go-down',gtk.ICON_SIZE_MENU)
			item.set_image(img)
			item.connect('activate',self.main_window.on_download_entry_activate)
			menu.append(item)
			
			item = gtk.ImageMenuItem('gtk-media-play')
			item.connect('activate',self.main_window.on_play_entry_activate)
			menu.append(item)
			
			item = gtk.MenuItem(_("Delete"))
			item.connect('activate',self.main_window.on_delete_entry_media_activate)
			menu.append(item)
			
		if selected['flag'] & ptvDB.F_UNVIEWED:
			item = gtk.MenuItem(_("Mark as _Viewed"))
			item.connect('activate',self.main_window.on_mark_entry_as_viewed_activate)
			menu.append(item)
		else:
			item = gtk.MenuItem(_("Mark as _Unviewed"))
			item.connect('activate',self.main_window.on_mark_entry_as_unviewed_activate)
			menu.append(item)
			
		menu.show_all()
		menu.popup(None,None,None, event.button,event.time)
