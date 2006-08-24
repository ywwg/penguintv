import gtk
#import gnome.ui
import gtk.glade
import gobject
#import pango
#import pycurl
#import locale
#import gettext
import gconf
#import time
import sys


import ptvDB
import penguintv
import Player
import UpdateTasksManager
import utils

import EditTextTagsDialog
import EditTagsMultiDialog
import RenameFeedDialog
import AddSearchTagDialog
import EditSearchesDialog
import MainWindow, FeedList, EntryList, EntryView

superglobal=utils.SuperGlobal()
superglobal.download_status={}

#status of the main window progress bar
U_NOBODY=0
U_DOWNLOAD=1
U_LOADING=2
U_POLL=3
U_STANDARD=4

class MainWindow:
	COLUMN_TITLE = 0
	COLUMN_ITEM = 1
	COLUMN_BOLD = 2
	COLUMN_STICKY_FLAG = 3

	def __init__(self, app, glade_prefix):
		self.app = app
		self.db = self.app.db #this and app are always in the same thread
		self.glade_prefix = glade_prefix
		self.widgetTree   = None
		self.window_maximized = False
		self.changing_layout=False
		self.layout='standard'
		self.bar_owner = U_NOBODY
		self.status_owner = U_NOBODY
		
		#other WINDOWS we open
		self.window_rename_feed = RenameFeedDialog.RenameFeedDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_rename_feed",'penguintv'),self.app) #MAGIC
		self.window_rename_feed.hide()
		self.window_edit_tags_single = EditTextTagsDialog.EditTextTagsDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_edit_tags_single",'penguintv'),self.app)
		self.window_add_search = AddSearchTagDialog.AddSearchTagDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_add_search_tag",'penguintv'),self.app)
		self.about_box_widgets = gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "aboutdialog1",'penguintv')
		self.about_box = self.about_box_widgets.get_widget('aboutdialog1')
		try:
			self.about_box.set_version(utils.VERSION)
		except:
			pass #fc3 workaround (doesn't have aboutbox class)
		self.about_box.hide()
		#most of the initialization is done on Show()

	def __getitem__(self, key):
		return self.widgets.get_widget(key)

	def set_wait_cursor(self, wait=True):
		if wait:
			c = gtk.gdk.Cursor(gtk.gdk.WATCH)
			self.app_window.window.set_cursor(c)
		else:
			self.app_window.window.set_cursor(None)

	def Show(self):
		conf = gconf.client_get_default()
		self.widgetTree = gtk.glade.XML(self.glade_prefix+'/penguintv.glade', self.layout+'app','penguintv') #MAGIC
		self.feed_list_view = FeedList.FeedList(self.widgetTree,self.app, self.db)
		self.entry_list_view = EntryList.EntryList(self.widgetTree,self.app, self, self.db)
		renderrer_str = conf.get_string('/apps/penguintv/renderrer')
		renderrer = EntryView.GTKHTML
		
		if renderrer_str == "GTKHTML":
			renderrer = EntryView.GTKHTML
		elif renderrer_str == "DEMOCRACY_MOZ":
			renderrer = EntryView.DEMOCRACY_MOZ
		
		def load_renderrer(x,recur=0):
			"""little function I define so I can recur"""
			if recur==2:
				print "too many tries"
				self.do_quit()
				sys.exit(2)
			try:
				self.entry_view = EntryView.EntryView(self.widgetTree, self.app, self, x)
			except:
				if renderrer == EntryView.DEMOCRACY_MOZ:
					if  _FORCE_DEMOCRACY_MOZ:
						load_renderrer(EntryView.DEMOCRACY_MOZ,recur+1)
					else:
						print "Error instantiating Democracy Mozilla renderrer, falling back to GTKHTML"
						print "(if running from source dir, build setup.py and copy MozillaBrowser.so to democracy_moz/)"
						load_renderrer(EntryView.GTKHTML,recur+1)
				else:
					print "Error loading renderrer"
					sys.exit(2)
		
		load_renderrer(renderrer)
					
		for key in dir(self.__class__): #python insaneness
			if key[:3] == 'on_':
				self.widgetTree.signal_connect(key, getattr(self, key))
				
		#major WIDGETS
		self.feed_pane = self.widgetTree.get_widget('feed_pane')
		self.feedlist = self.widgetTree.get_widget('feedlistview')
		self.entry_pane = self.widgetTree.get_widget('entry_pane')
		self.app_window = self.widgetTree.get_widget(self.layout+'app')
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
		filter_combo_model = gtk.ListStore(str,str,bool,int) #text to display, name of filter, separator-or-not, type
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
		
		filter_combo_model.append([FeedList.BUILTIN_TAGS[0],"("+str(len(self.db.get_feedlist()))+")",False,ptvDB.T_BUILTIN])
		for builtin in FeedList.BUILTIN_TAGS[1:]:
			filter_combo_model.append([builtin,"",False,ptvDB.T_BUILTIN])
		filter_combo_model.append(["---","---",True,ptvDB.T_BUILTIN])
		self.update_filters()
		
		self.search_entry = self.widgetTree.get_widget('search_entry')
		self.search_container = self.widgetTree.get_widget('search_container')
		
		#button = self.widgetTree.get_widget('search_button')
		#button.set_property("image",gtk.image_new_from_stock('gtk-find',gtk.ICON_SIZE_SMALL_TOOLBAR))
		#button.set_property("label",None)
		
		#button = self.widgetTree.get_widget('clear_search_button')
		#button.set_property("image",gtk.image_new_from_stock('gtk-clear',gtk.ICON_SIZE_SMALL_TOOLBAR))
		#button.set_property("label",None)
			
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
		
		#final setup for the window comes from gconf
		x = conf.get_int('/apps/penguintv/app_window_position_x')
		y = conf.get_int('/apps/penguintv/app_window_position_y')
		if x is None:
			x=40
		if y is None:
			y=40
		self.app_window.move(x,y)
		w = conf.get_int('/apps/penguintv/app_window_size_x')
		h = conf.get_int('/apps/penguintv/app_window_size_y')
		if w<0 or h<0:  #very cheesy.  negative values really means "maximize"
			self.app_window.resize(abs(w),abs(h)) #but be good and don't make assumptions about negativity
			self.app_window.maximize()
			self.window_maximized = True
		else:
			self.app_window.resize(w,h)
		val = conf.get_int('/apps/penguintv/feed_pane_position')
		if val is None:
			val=132
		if val < 10:
			val=50
		self.feed_pane.set_position(val)
		val = conf.get_int('/apps/penguintv/entry_pane_position')
		if val is None:
			val=309
		if val < 10:
			val = 50
		self.app_window.show()
		self.entry_pane.set_position(val)
		
		val = conf.get_string('/apps/penguintv/default_filter')
		if val is not None:
			try:
				filter_index = [row[0] for row in filter_combo_model].index(val)
				cur_filter = filter_combo_model[filter_index]
				if cur_filter[3] != ptvDB.T_SEARCH and filter_index!=FeedList.SEARCH:
					self.feed_list_view.set_filter(filter_index,val)
					self.filter_combo_widget.set_active(filter_index)
				else:
					self.filter_combo_widget.set_active(FeedList.ALL)
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

	def on_about_activate(self,event):
		try:
			self.about_box.run()
		except:
			pass #fc3 workaround
		
	def on_about_close(self, event):
		self.about_box.hide()
		
	def on_app_delete_event(self,event,data):
		self.app.do_quit()
		
	def on_app_destroy_event(self,event,data):
		self.app.do_quit()
		
	def on_app_window_state_event(self, client, event):
		if event.new_window_state & gtk.gdk.WINDOW_STATE_MAXIMIZED:
			self.window_maximized = True
		elif event.new_window_state & gtk.gdk.WINDOW_STATE_MAXIMIZED == 0:
			self.window_maximized = False
			
	def on_add_feed_activate(self, event):
		self.app.window_add_feed.show() #not modal / blocking
		
	def on_feed_add_clicked(self, event):
		self.app.window_add_feed.show() #not modal / blocking
	
	#def on_feed_pane_expose_event(self, widget, event):
	#	self.feed_list_view.resize_columns(self.feed_pane.get_position())
		
	def on_download_entry_activate(self, event):
		try:
			entry = self.entry_list_view.get_selected()['entry_id']
			self.app.download_entry(entry)
		except:
			pass
			
	def on_download_unviewed_activate(self, event):
		self.app.download_unviewed()
				
	def on_download_unviewed_clicked(self,event):
		self.app.download_unviewed()
			
	def on_delete_entry_media_activate(self,event):
		try:
			selected = self.entry_list_view.get_selected()['entry_id']
			self.app.delete_entry_media(selected)
		except:
			pass
			
	def on_delete_feed_media_activate(self,event):
		selected = self.feed_list_view.get_selected()
		if selected:
			self.app.delete_feed_media(selected)
			
	def on_edit_tags_activate(self, event):
		self.edit_tags()
		
	def on_edit_tags_for_all_activate(self, event):
		"""Bring up mass tag creation window"""
		window_edit_tags_multi = EditTagsMultiDialog.EditTagsMultiDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_edit_tags_multi",'penguintv'),self.app)
		window_edit_tags_multi.show()
		window_edit_tags_multi.set_feed_list(self.db.get_feedlist())
			
	def on_export_opml_activate(self, event):
		self.app.export_opml()
		
	def on_feed_remove_clicked(self,event): 
		selected = self.feed_list_view.get_selected()
		if selected:
			self.app.remove_feed(selected)
			
	def on_feedlistview_drag_data_received(self, widget, context, x, y, selection, targetType, time):
		widget.emit_stop_by_name('drag-data-received')
		if targetType == self.TARGET_TYPE_TEXT:
			url = ""
			for c in selection.data:
				if c != "\0":  #for some reason ever other character is a null.  what gives?
					url = url+c
			if url.split(':')[0] == 'feed':
				url = url[url.find(':')+1:]
			self.app.add_feed(url)
		elif targetType == self.TARGET_TYPE_URL:
			url = ""
			for c in selection.data[0:selection.data.find('\n')]:
				if c != '\0':
					url = url+c
			if url.split(':')[0] == 'feed': #stupid wordpress does 'feed:http://url.com/whatever'
				url = url[url.find(':')+1:]
			self.app.add_feed(url)
			
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
			
			item = gtk.MenuItem(_("_Delete All Media"))
			item.connect('activate',self.on_delete_feed_media_activate)
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
		self.app.poll_feeds()
		self.set_wait_cursor(False)
		
	def on_filter_combo_changed(self, event):
		model = self.filter_combo_widget.get_model()
		current_filter = model[self.filter_combo_widget.get_active()]
		self.app.change_filter(current_filter[0],current_filter[3])
			
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
				self.app.import_opml(f)
			except:
				pass
		elif response == gtk.RESPONSE_CANCEL:
			print 'Closed, no files selected'
		dialog.destroy()		
			
	def on_mark_entry_as_viewed_activate(self,event):
		try:
			entry = self.entry_list_view.get_selected()['entry_id']
			self.app.mark_entry_as_viewed(entry)
		except:
			pass
		
	def on_mark_entry_as_unviewed_activate(self,event):
		try:
			entry = self.entry_list_view.get_selected()['entry_id']
			self.app.mark_entry_as_unviewed(entry)
		except:
			pass

	def on_mark_feed_as_viewed_activate(self,event):
		feed = self.feed_list_view.get_selected()
		if feed:
			self.app.mark_feed_as_viewed(feed)
 
 	def on_play_entry_activate(self, event):
 		try:
			entry = self.entry_list_view.get_selected()['entry_id']
			self.app.play_entry(entry)
		except:
			pass
				
	def on_play_unviewed_activate(self, event):
		self.app.play_unviewed()
			
	def on_play_unviewed_clicked(self, event):
		self.app.play_unviewed()
		
	def on_preferences_activate(self, event):
		self.app.window_preferences.show()
		
	def on_quit2_activate(self,event):
		self.app.do_quit() #make the program quit, dumbass
		
	def on_refresh_activate(self, event):
		feed = self.feed_list_view.get_selected()
		self.app.refresh_feed(feed)
		
	def on_refresh_feeds_activate(self, event):
		self.set_wait_cursor()
		self.app.poll_feeds()
		self.set_wait_cursor(False)
		
	def on_reindex_searches_activate(self, event):
		self.app.db.doindex()
		
	def on_remove_feed_activate(self, event):
		selected = self.feed_list_view.get_selected()
		if selected:
			self.app.remove_feed(selected)
		
	def on_rename_feed_activate(self, event):
		feed = self.feed_list_view.get_selected()
		self.window_rename_feed.set_feed_id(feed)
		self.window_rename_feed.set_feed_name(self.db.get_feed_title(feed))
		self.window_rename_feed.show()	

	def on_resume_all_activate(self, event):
		self.app.resume_resumable()
		
	def on_save_search_clicked(self, event):
		query = self.search_entry.get_text()
		if query=="":
			return
		self.window_add_search.show()
		self.window_add_search.set_query(query)		
		
	def on_search_clear_clicked(self, event):
		self.app.manual_search("")
		
	def on_saved_searches_activate(self, event):
		window_edit_saved_searches = EditSearchesDialog.EditSearchesDialog(gtk.glade.XML(self.glade_prefix+'/penguintv.glade', "window_edit_search_tags",'penguintv'),self.app)
		window_edit_saved_searches.show()
		del window_edit_saved_searches
		
	def on_search_entry_activate(self, event):
		self.app.manual_search(self.search_entry.get_text())
		
	def on_show_downloads_activate(self, event):
		self.app.show_downloads()
		
	def on_stop_downloads_clicked(self, widget):
		self.app.stop_downloads()
		
	#def on_stop_downloads_toggled(self, widget):
	#	print "toggled"
	#	self.app.stop_downloads_toggled(widget.get_active())

	def on_standard_layout_activate(self, event):	
		self.app.change_layout('standard')
	
	def on_horizontal_layout_activate(self, event):
		self.app.change_layout('widescreen')	

	def on_vertical_layout_activate(self,event):
		self.app.change_layout('vertical')	
				
	def activate_layout(self, layout):
		"""gets called by app when it's ready"""
		self.changing_layout = True
		self.layout=layout
		dic = self.get_selected_items()
		self.app.save_settings()
		self.app.write_feed_cache()
		self.Hide()
		self.Show()
		self.feed_list_view.populate_feeds()
		self.set_selected_items(dic)
		self.app.update_disk_usage()
		
	def is_changing_layout(self):
		return self.changing_layout
		
	def on_unread_filter_toggled(self, event):
		self.feed_list_view.set_unread_toggle(self.filter_unread_checkbox.get_active())

	def display_status_message(self, m, update_category=U_STANDARD):
		"""displays a status message on the main status bar.  If this is a polling update or download
		   update, we don't overwrite what's there."""	
		current_text = self._status_view.get_status().get_text()
		
		if current_text == "":
			self.status_owner = update_category
			self._status_view.set_status(m)
		else:
			if update_category >= self.status_owner:
				self._status_view.set_status(m)
				if m == "":
					self.status_owner = U_NOBODY
				else:
					self.status_owner = update_category
			#if update_category==U_STANDARD:  #only overwrite if this is not a poll or download
			#	self.status_owner = update_category
			#	self._status_view.set_status(m)
			#elif update_category == U_POLL and self.status_owner != U_STANDARD:
			#	self.status_owner = update_category
			#	self._status_view.set_status(m)				
			#elif update_category == U_DOWNLOAD and self.status_owner == U_DOWNLOAD:
			#	self._status_view.set_status(m)
			
		return False #in case of timeouts
		
	def update_progress_bar(self, p, update_category=U_STANDARD):
		"""Update the progress bar.  if both downloading and polling, polling wins"""
		if p==-1:
			self.bar_owner = U_NOBODY
			self._status_view.set_progress_percentage(0)
		else:
			if update_category >= self.bar_owner:
				self.bar_owner = update_category
				self._status_view.set_progress_percentage(p)		
		#if update_category == U_STANDARD:
		#	raise ShouldntHappenError, "only polls and downloads should update the bar"
		#elif update_category == U_DOWNLOAD:
		#	if self.bar_owner != U_POLL:
		#		self.bar_owner = U_DOWNLOAD
		#		self._status_view.set_progress_percentage(p)
		#	#else tough luck
		#elif update_category == U_POLL:
		#	self.bar_owner = U_POLL
		#	self._status_view.set_progress_percentage(p)
		
		
	def edit_tags(self):
		"""Edit Tags clicked, bring up tag editing dialog"""
		selected = self.feed_list_view.get_selected()
		self.window_edit_tags_single.set_feed_id(selected)
		self.window_edit_tags_single.set_tags(self.db.get_tags_for_feed(selected))
		self.window_edit_tags_single.show()

	def update_filters(self):
		"""update the filter combo box with the current list of filters"""
		#get name of current filter, if a tag
		model = self.filter_combo_widget.get_model()
		current_filter = model[self.filter_combo_widget.get_active()][0]
		#if current_filter not in BUILTIN_TAGS:	
		#	if current_filter not in self.db.get_all_tags():
		#		current_filter = ALL  #in case the current filter is an out of date tag
		model.clear()

		model.append([FeedList.BUILTIN_TAGS[0],"("+str(len(self.db.get_feedlist()))+")",False,ptvDB.T_BUILTIN])
		for builtin in FeedList.BUILTIN_TAGS[1:]:
			model.append([builtin,"",False,ptvDB.T_BUILTIN])

		model.append(["---","---",True,ptvDB.T_BUILTIN])			
		tags = self.db.get_all_tags(ptvDB.T_SEARCH)	
		if tags:
			for tag in tags:
				model.append([tag,"",False,ptvDB.T_SEARCH])
		
		model.append(["---","---",True,ptvDB.T_BUILTIN])
		tags = self.db.get_all_tags(ptvDB.T_TAG)	
		if tags:
			for tag in tags:
				model.append([tag,"("+str(self.db.get_count_for_tag(tag))+")",False,ptvDB.T_TAG])
		
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

	#def populate_and_select(self, feed_id):
	def select_feed(self, feed_id):
		#self.feed_list_view.populate_feeds()
		self.filter_combo_widget.set_active(FeedList.ALL)
		self.filter_unread_checkbox.set_active(False)
		self.feed_list_view.set_selected(feed_id)
		self.feed_list_view.resize_columns()

	def get_selected_items(self):
		selected_feed = self.feed_list_view.get_selected()
		filter_setting = self.feed_list_view.filter_setting
		try:
			selected_entry = self.entry_list_view.get_selected()['entry_id']
		except:
			selected_entry = 0
		return {'feed':selected_feed,
				'filter':filter_setting,
				'entry':selected_entry}

	def set_selected_items(self, dic):
		#self.feed_list_view.set_filter(dic['filter'])
		self.feed_list_view.set_selected(dic['feed'])
		self.entry_list_view.populate_entries(dic['feed'],dic['entry'])

	def update_disk_usage(self, size):
		self.disk_usage_widget.set_text(utils.format_size(size))

	def update_download_progress(self):
		progresses = [superglobal.download_status[id] for id in superglobal.download_status.keys() if superglobal.download_status[id][0]==penguintv.DOWNLOAD_PROGRESS]
		queued = [superglobal.download_status[id] for id in superglobal.download_status.keys() if superglobal.download_status[id][0]==penguintv.DOWNLOAD_QUEUED]
		if len(progresses)+len(queued)==0:
			self.display_status_message("")
			self.update_progress_bar(-1,U_DOWNLOAD)
			return
		total_size = 0
		downloaded = 0
		for item in progresses+queued:
			if item[2]<=0:
				total_size += 1
			else:
				total_size += item[2]
			downloaded += (item[1]/100.0)*item[2]
		if total_size == 0:
			total_size=1
		dict = { 'percent': downloaded*100.0/total_size,
				 'files': len(progresses)+len(queued),
				 'total': total_size>1 and "("+utils.format_size(total_size)+")" or '', #ternary operator simulation
				 's': len(progresses)>1 and 's' or '',
				 'queued': len(queued)} 
		if dict['queued']>0:
			message = _("Downloaded %(percent)d%% of %(files)d file%(s)s, %(queued)d queued %(total)s") % dict
		else:
			message = _("Downloaded %(percent)d%% of %(files)d file%(s)s %(total)s") % dict
		self.display_status_message(message , U_DOWNLOAD) 
		self.update_progress_bar(dict['percent']/100.0,U_DOWNLOAD)
				
	def desensitize(self):
		self.app_window.set_sensitive(False)
		while gtk.events_pending(): #make sure the sensitivity change goes through
			gtk.main_iteration()
	
class ShouldntHappenError(Exception):
	def __init__(self,error):
		self.error = error
	def __str__(self):
		return self.error
