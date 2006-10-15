import gtk
import gtk.glade
import gobject
import sys, os, os.path

import traceback


import ptvDB
import penguintv
import Player
import UpdateTasksManager
import utils
import Downloader

#status of the main window progress bar
U_NOBODY=0
U_DOWNLOAD=1
U_LOADING=2
U_POLL=3
U_STANDARD=4

#states
S_DEFAULT       = 0
S_MANUAL_SEARCH = 1
S_TAG_SEARCH    = 2
S_LOADING_FEEDS = 3

#filter model
F_TEXT         = 0
F_COUNT        = 1
F_SEPARATOR    = 2 
F_FAVORITE     = 3
F_NOT_FAVORITE = 4
F_TYPE         = 5						  

import EditTextTagsDialog
import EditTagsMultiDialog
import RenameFeedDialog
import AddSearchTagDialog
import EditSearchesDialog
import FeedFilterDialog
import FeedPropertiesDialog
import FeedFilterPropertiesDialog
import SynchronizeDialog
import FilterSelectorWidget
import MainWindow, FeedList, EntryList, EntryView, PlanetView, DownloadView

class MainWindow:
	COLUMN_TITLE = 0
	COLUMN_ITEM = 1
	COLUMN_BOLD = 2
	COLUMN_STICKY_FLAG = 3

	def __init__(self, app, glade_prefix):
		self._app = app
		self._mm = self._app.mediamanager
		self._db = self._app.db #this and app are always in the same thread
		self._glade_prefix = glade_prefix
		self._widgetTree   = None
		self.window_maximized = False
		self.changing_layout=False
		self.layout='standard'
		self._bar_owner = U_NOBODY
		self._status_owner = U_NOBODY
		self._state = S_DEFAULT
		
		self._active_filter_name = FeedList.BUILTIN_TAGS[FeedList.ALL]
		self._active_filter_index = FeedList.ALL
		
		##other WINDOWS we open
		self._window_rename_feed = RenameFeedDialog.RenameFeedDialog(gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "window_rename_feed",'penguintv'),self._app) #MAGIC
		self._window_rename_feed.hide()
		self._window_edit_tags_single = EditTextTagsDialog.EditTextTagsDialog(gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "window_edit_tags_single",'penguintv'),self._app)
		self._window_add_search = AddSearchTagDialog.AddSearchTagDialog(gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "window_add_search_tag",'penguintv'),self._app)
		self._about_box_widgets = gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "aboutdialog1",'penguintv')
		self._about_box = self._about_box_widgets.get_widget('aboutdialog1')
		self._feed_properties_dialog = FeedPropertiesDialog.FeedPropertiesDialog(gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "window_feed_properties",'penguintv'),self._app)
		self._feed_filter_properties_dialog = FeedFilterPropertiesDialog.FeedFilterPropertiesDialog(gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "window_filter_properties",'penguintv'),self._app)
		self._sync_dialog = SynchronizeDialog.SynchronizeDialog(os.path.join(self._glade_prefix,'penguintv.glade'), self._db)
		
		try:
			self._about_box.set_version(utils.VERSION)
		except:
			pass #fc3 workaround (doesn't have aboutbox class)
		self._about_box.hide()
		#most of the initialization is done on Show()

#	def __getitem__(self, key):
#		return self.widgets.get_widget(key)

	def set_wait_cursor(self, wait=True):
		if self.app_window is None:
			return
		if wait:
			c = gtk.gdk.Cursor(gtk.gdk.WATCH)
			self.app_window.window.set_cursor(c)
		else:
			self.app_window.window.set_cursor(None)

	def Show(self, dock_widget = None):
		"""shows the main window. if given a widget, it will put itself in the widget.  otherwise load a regular
		application window"""
		#sys.stderr.write("show,"+str(dock_widget))
		self._app.log("Show, please...")
		
		if not EntryView.MOZ_OK and self.layout == "planet":
			print "requested planet layout, but can't use because gtkmozembed isn't installed correctly (won't import)"
			self.layout = "standard"
		
		if dock_widget is None:  #if we are loading in a regular window...
			self._load_app_window()
			if not ptvDB.HAS_LUCENE:
				#remove UI elements that don't apply without search
				self.search_container.hide_all()
				self._widgetTree.get_widget('saved_searches').hide()
				self._widgetTree.get_widget('separator11').hide()
				self._widgetTree.get_widget('reindex_searches').hide()
			if not EntryView.MOZ_OK:
				self._widgetTree.get_widget('planet_layout').hide()
			self._window = self.app_window
		else:  #if we are in OLPC mode and just have to supply a widget...
			self._status_view = None
			self._disk_usage_widget = None
			self.app_window = None
			
			vbox = gtk.VBox()
			
			vbox.pack_start(self._load_toolbar(), False, False)
			self._app.log("loading layout "+self.layout)
			self._layout_dock = self.load_notebook()
			self._layout_dock.add(self.load_layout())
			vbox.pack_start(self._notebook)
			self._status_view = MainWindow._my_status_view()
			vbox.pack_start(self._status_view, False, False)
			dock_widget.add(vbox)
			dock_widget.show_all()
			if not ptvDB.HAS_LUCENE:
				#remove UI elements that don't apply without search
				self.search_container.hide_all()
			self._window = dock_widget
				
	def _load_toolbar(self):
		if self._widgetTree is None:
			self._widgetTree = gtk.glade.XML(self._glade_prefix+'/penguintv.glade', 'toolbar1','penguintv')
			for key in dir(self.__class__): #python insaneness
				if key[:3] == 'on_':
					self._widgetTree.signal_connect(key, getattr(self, key))
		toolbar = self._widgetTree.get_widget('toolbar1')
		
		#set up separator (see below)
		vseparator = self._widgetTree.get_widget('vseparator1')
		vseparator_toolitem = self._widgetTree.get_widget('toolitem1')
		vseparator_toolitem.set_expand(True)
		vseparator.set_draw(False)
		
		if ptvDB.RUNNING_SUGAR:
			vsep2 = self._widgetTree.get_widget('vseparator2')
			vseparator.set_property('visible',True)
			pref_button = self._widgetTree.get_widget('preferences_toolbutton')
			pref_button.set_property('visible',True)
			pref_button.set_property('label',_("Preferences"))
		self._disk_usage_widget = self._widgetTree.get_widget('disk_usage')
	
		return toolbar
		
	class _my_status_view(gtk.HBox):
		def __init__(self, homogeneous=False, spacing=0):
			gtk.HBox.__init__(self, homogeneous=False, spacing=0)
			self._progress = gtk.ProgressBar()
			sep = gtk.VSeparator()
			self._status = gtk.Label()
			
			self.pack_start(self._progress, False, False)
			self.pack_start(sep, False, False)
			self.pack_start(self._status, False, False)
								
		def get_status(self):
			return self._status
			
		def set_status(self, m):
			self._status.set_text(m)
			
		def set_progress_percentage(self, p):
			self._progress.set_fraction(p)
			
	def _load_app_window(self):
		self._widgetTree = gtk.glade.XML(self._glade_prefix+'/penguintv.glade', 'app','penguintv') #MAGIC
		notebook_dock = self._widgetTree.get_widget('layout_dock')
		self.app_window = self._widgetTree.get_widget('app')
		
		fancy_feedlist_item = self._widgetTree.get_widget('fancy_feed_display')
		fancy_feedlist_item.set_active(self._db.get_setting(ptvDB.BOOL, '/apps/penguintv/fancy_feedlist', True))
		self._widgetTree.get_widget(self.layout+"_layout").set_active(True)
		
		try:
			self.app_window.set_icon_from_file(utils.GetPrefix()+"/share/pixmaps/penguintvicon.png")
		except:
			try:
				self.app_window.set_icon_from_file(utils.GetPrefix()+"/share/penguintvicon.png") #in case the install is still in the source dirs
			except:
				self.app_window.set_icon_from_file(self._glade_prefix+"/penguintvicon.png")
		self._status_view = self._widgetTree.get_widget("appbar")
		
		self._load_toolbar()
		
		#load the layout
		#vbox = gtk.VBox()
		#vbox.pack_start(self.load_layout())
		#self._status_view = MainWindow._my_status_view()
		#vbox.pack_start(self._status_view, False, False)
		#self._layout_dock.add(vbox)
		self._layout_dock = self.load_notebook()
		notebook_dock.add(self._notebook)
		self._layout_dock.add(self.load_layout())
		self.app_window.show_all()
		
				
		#final setup for the window comes from gconf
		x = self._db.get_setting(ptvDB.INT, '/apps/penguintv/app_window_position_x', 40)
		y = self._db.get_setting(ptvDB.INT, '/apps/penguintv/app_window_position_y', 40)
		self.app_window.move(x,y)
		w = self._db.get_setting(ptvDB.INT, '/apps/penguintv/app_window_size_x', 500)
		h = self._db.get_setting(ptvDB.INT, '/apps/penguintv/app_window_size_y', 500)
		if w<0 or h<0:  #very cheesy.  negative values really means "maximize"
			self.app_window.resize(abs(w),abs(h)) #but be good and don't make assumptions about negativity
			self.app_window.maximize()
			self.window_maximized = True
		else:
			self.app_window.resize(w,h)
			
		for key in dir(self.__class__): #python insaneness
			if key[:3] == 'on_':
				self._widgetTree.signal_connect(key, getattr(self, key))
				
	def load_notebook(self):
		self._notebook = gtk.Notebook()
		self._notebook.set_property('tab-border',0)
		label = gtk.Label(_('<span size="small">Feeds</span>'))
		label.set_property('use-markup',True)
		vbox = gtk.VBox()
		self._notebook.append_page(vbox, label)
		
		self._downloads_label = gtk.Label('<span size="small">'+_('Downloads')+'</span>')
		self._downloads_label.set_property('use-markup',True)
		self._download_view = DownloadView.DownloadView(self._app, self._mm, self._db, self._glade_prefix+'/penguintv.glade')
		self._notebook.append_page(self._download_view.get_widget(), self._downloads_label)
		
		self._notebook.set_show_tabs(False)
		self._notebook.set_property('show-border', False)
		
		self._notebook.show_all()
		self._notebook.set_current_page(0)
		
		return vbox
		
	def notebook_select_page(self, page):
		self._notebook.set_current_page(page)
		
	def load_layout(self):
		#self._app.log("load_layout")
				
		components = gtk.glade.XML(self._glade_prefix+'/penguintv.glade', self.layout+'_layout_container','penguintv') #MAGIC
		self._layout_container = components.get_widget(self.layout+'_layout_container')
		#dock_widget.add(self._layout_container)
		
		fancy = self._db.get_setting(ptvDB.BOOL, '/apps/penguintv/fancy_feedlist', True)
		if ptvDB.RUNNING_SUGAR:
			fancy = True
		
		self.feed_list_view = FeedList.FeedList(components,self._app, self._db, fancy)
		renderer_str = self._db.get_setting(ptvDB.STRING, '/apps/penguintv/renderrer', "MOZILLA") #stupid misspelling (renderrer != renderer)
		
		if renderer_str == "GTKHTML":
			renderer = EntryView.GTKHTML
		elif renderer_str == "DEMOCRACY_MOZ":
			renderer = EntryView.DEMOCRACY_MOZ
		elif renderer_str == "MOZILLA":
			renderer = EntryView.MOZILLA
		else:
			renderer = EntryView.GTKHTML
			
		if not EntryView.MOZ_OK:
			renderer = EntryView.GTKHTML
					
		def load_renderer(x,recur=0):
			"""little function I define so I can recur"""
			if recur==2:
				print "too many tries"
				self._app.do_quit()
				sys.exit(2)
			try:
				if self.layout != "planet":
					self.entry_view = EntryView.EntryView(components, self._app, self, x)
				else:
					self.entry_view = PlanetView.PlanetView(components, self._app, self, self._db, x)
			except Exception, e:
			#	print e
				if renderer == EntryView.DEMOCRACY_MOZ:
					if  _FORCE_DEMOCRACY_MOZ:
						load_renderer(EntryView.DEMOCRACY_MOZ,recur+1)
					else:
						print "Error instantiating Democracy Mozilla renderer, falling back to GTKHTML"
						print "(if running from source dir, build setup.py and copy MozillaBrowser.so to democracy_moz/)"
						load_renderer(EntryView.GTKHTML,recur+1)
				else:
					print "Error loading renderer"
					self._app.do_quit()
		load_renderer(renderer)
		if self.layout != "planet":
			self.entry_list_view = EntryList.EntryList(components,self._app, self, self.entry_view, self._db)			
		else:
			self.entry_list_view = self.entry_view
			
		for key in dir(self.__class__): #python insaneness
			if key[:3] == 'on_':
				components.signal_connect(key, getattr(self, key))
				
		#major WIDGETS
		self.feed_pane = components.get_widget('feed_pane')
		self._feedlist = components.get_widget('feedlistview')
		if self.layout != "planet":
			self.entry_pane = components.get_widget('entry_pane')
		else:
			self.entry_pane = self.feed_pane #cheat
		
		self._filter_model = gtk.ListStore(str, #name of filter
										   str, #text to display
										   bool, #separator-or-not
										   int, #favorite
										   bool, #non-favorite
										   int) #type
		
		self._filter_selector_widget = FilterSelectorWidget.FilterSelectorWidget(os.path.join(self._glade_prefix,'penguintv.glade'),
																				 self, self._filter_model)
		
		self.filter_unread_checkbox = components.get_widget('unread_filter')
		self._filter_selector_button = components.get_widget('filter_selector_button')
		self._filter_model.append([FeedList.BUILTIN_TAGS[0],
									     "("+str(len(self._db.get_feedlist()))+")",
									     False,
									     False, 
									     False,
									     ptvDB.T_BUILTIN])
		for builtin in FeedList.BUILTIN_TAGS[1:]:
			self._filter_model.append([builtin,
									 		 "",
											 False,
											 False,
											 False,
											 ptvDB.T_BUILTIN,])
		self._filter_model.append(["---",
									     "---",
 								  	     True,
									     False,
									     True,
									     ptvDB.T_BUILTIN])
		self.update_filters()
		
		self.set_active_filter(FeedList.ALL)
		
		self.search_entry = components.get_widget('search_entry')
		self.search_container = components.get_widget('search_container')
		
		#button = self._widgetTree.get_widget('search_button')
		#button.set_property("image",gtk.image_new_from_stock('gtk-find',gtk.ICON_SIZE_SMALL_TOOLBAR))
		#button.set_property("label",None)
		
		#button = self._widgetTree.get_widget('clear_search_button')
		#button.set_property("image",gtk.image_new_from_stock('gtk-clear',gtk.ICON_SIZE_SMALL_TOOLBAR))
		#button.set_property("label",None)
						
		#dnd
		self._TARGET_TYPE_TEXT = 80
		self._TARGET_TYPE_URL = 81
		drop_types = [ ('text/x-moz-url',0,self._TARGET_TYPE_URL),
									 ('text/unicode',0,self._TARGET_TYPE_TEXT),
									 ('text/plain',0,self._TARGET_TYPE_TEXT)]
		self._feedlist.drag_dest_set(gtk.DEST_DEFAULT_ALL, drop_types, gtk.gdk.ACTION_COPY)
		
		val = self._db.get_setting(ptvDB.INT, '/apps/penguintv/feed_pane_position', 132)
		if val < 10: val=50
		self.feed_pane.set_position(val)
		val = self._db.get_setting(ptvDB.INT, '/apps/penguintv/entry_pane_position', 309)
		if val < 10: val = 50
		#self.app_window.show_all()
		#dock_widget.show_all()
		self.entry_pane.set_position(val)
		
		val = self._db.get_setting(ptvDB.STRING, '/apps/penguintv/default_filter')
		if val is not None:
			try:
				filter_index = [row[F_TEXT] for row in self._filter_model].index(val)
				cur_filter = self._filter_model[filter_index]
				if cur_filter[F_TYPE] != ptvDB.T_SEARCH and filter_index!=FeedList.SEARCH:
					#self.feed_list_view.set_filter(filter_index,val)
					self.set_active_filter(filter_index)
				else:
					self.set_active_filter(FeedList.ALL)
			except ValueError: #didn't find the item in the model (.index(val) fails)
				self.set_active_filter(FeedList.ALL)
		else:
			self.set_active_filter(FeedList.ALL)
		#sys.stderr.write("done")
		return self._layout_container
			
	def Hide(self):
		self._app.log("hiding")
		if self.app_window:
			self.app_window.hide()
		del self._widgetTree
		del self.feed_list_view
		del self.entry_list_view
		del self.entry_view
				
		#some widgets
		del self.feed_pane
		del self._feedlist
		if self.layout != "planet":
			del self.entry_pane
		del self.app_window
		del self._status_view
		del self._disk_usage_widget
		
	def get_parent(self):
		#if self.app_window is not None:
		#	return self.app_window
		#else:
		#	self._app.log(str(self._layout_dock.get_parent_window()))
		#	return self._layout_dock.get_parent_window()
		self._app.log(str(self._window))
		return self._window

	def on_about_activate(self,event):
		try:
			self._about_box.run()
		except:
			pass #fc3 workaround
		
	def on_about_close(self, event):
		self._about_box.hide()
		
	def on_app_delete_event(self,event,data):
		self._app.do_quit()
		
	def on_app_destroy_event(self,event,data):
		self._app.do_quit()
		
	def on_app_focus_out_event(self, widget, event):
		if self._filter_selector_widget.Hide(): #returns false if we're dragging
			self._filter_selector_button.released()
			self._filter_selector_button.set_active(False)
		
	def on_app_window_state_event(self, client, event):
		if event.new_window_state & gtk.gdk.WINDOW_STATE_MAXIMIZED:
			self.window_maximized = True
		elif event.new_window_state & gtk.gdk.WINDOW_STATE_MAXIMIZED == 0:
			self.window_maximized = False
			
	def on_add_feed_activate(self, event):
		if self._state == S_LOADING_FEEDS:
			print "Please wait until feeds have loaded before adding a new one"
			return 
		self._app.window_add_feed.show() #not modal / blocking
		
	def on_add_feed_filter_activate(self,event):
		selected = self.feed_list_view.get_selected()
		if selected:
			title = self._db.get_feed_title(selected)
			dialog = FeedFilterDialog.FeedFilterDialog(gtk.glade.XML(self._glade_prefix+'/penguintv.glade', "window_feed_filter",'penguintv'),self._app)
			dialog.show()
			dialog.set_pointed_feed(selected,title)
			d = { 'title':title }
			dialog.set_filter_name(_("%(title)s Filtered" % d))
		else:
			dialog = gtk.Dialog(title=_("No Feed Selected"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("Please select the feed you would like to filter"))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			response = dialog.run()
			dialog.hide()
			del dialog
		
	def on_feed_add_clicked(self, event):
		if self._state == S_LOADING_FEEDS:
			print "Please wait until feeds have loaded before adding a new one" 
			return 
		self._app.window_add_feed.show() #not modal / blocking
	
	#def on_feed_pane_expose_event(self, widget, event):
	#	self.feed_list_view.resize_columns(self.feed_pane.get_position())
	
	def on_feed_properties_activate(self, event):
		selected = self.feed_list_view.get_selected()
		if selected:
			#title, description, url, link
			feed_info = self._db.get_feed_info(selected)
			self._feed_properties_dialog.set_feedid(selected)
			self._feed_properties_dialog.set_title(feed_info['title'])
			self._feed_properties_dialog.set_rss(feed_info['url'])
			self._feed_properties_dialog.set_description(feed_info['description'])
			self._feed_properties_dialog.set_link(feed_info['link'])
			self._feed_properties_dialog.set_last_poll(feed_info['lastpoll'])
			if self._app.feed_refresh_method == penguintv.REFRESH_AUTO:
				self._feed_properties_dialog.set_next_poll(feed_info['lastpoll']+feed_info['pollfreq'])
			else:
				self._feed_properties_dialog.set_next_poll(feed_info['lastpoll']+self._app.polling_frequency)
			self._feed_properties_dialog.show()
			
	def on_feed_filter_properties_activate(self, event):
		selected = self.feed_list_view.get_selected()
		if selected:
			#title, description, url, link
			feed_info = self._db.get_feed_info(selected)
			self._feed_filter_properties_dialog.set_feed_id(selected)
			self._feed_filter_properties_dialog.set_pointed_feed_id(feed_info['feed_pointer'])
			self._feed_filter_properties_dialog.set_filter_name(feed_info['title'])
			self._feed_filter_properties_dialog.set_query(feed_info['description'])
			self._feed_filter_properties_dialog.show()
		
	def on_download_entry_activate(self, event):
		try:
			entry = self.entry_list_view.get_selected()['entry_id']
			self._app.download_entry(entry)
		except:
			pass
			
	def on_download_unviewed_activate(self, event):
		self._app.download_unviewed()
				
	def on_download_unviewed_clicked(self,event):
		self._app.download_unviewed()
			
	def on_delete_entry_media_activate(self,event):
		try:
			selected = self.entry_list_view.get_selected()['entry_id']
			self._app.delete_entry_media(selected)
		except:
			pass
			
	def on_delete_feed_media_activate(self,event):
		selected = self.feed_list_view.get_selected()
		if selected:
			self._app.delete_feed_media(selected)
			
	def on_edit_tags_activate(self, event):
		self._edit_tags()
		
	def on_edit_tags_for_all_activate(self, event):
		"""Bring up mass tag creation window"""
		window_edit_tags_multi = EditTagsMultiDialog.EditTagsMultiDialog(gtk.glade.XML(self._glade_prefix+'/penguintv.glade', "window_edit_tags_multi",'penguintv'),self._app)
		window_edit_tags_multi.show()
		window_edit_tags_multi.set_feed_list(self._db.get_feedlist())
			
	def on_export_opml_activate(self, event):
		self._app.export_opml()
		
	def on_feed_remove_clicked(self,event): 
		selected = self.feed_list_view.get_selected()
		if selected:
			if self._state == S_LOADING_FEEDS:
				print "Please wait the program has loaded before removing a feed."
				return 
			self._app.remove_feed(selected)
			
	def on_feedlistview_drag_data_received(self, widget, context, x, y, selection, targetType, time):
		widget.emit_stop_by_name('drag-data-received')
		if targetType == self._TARGET_TYPE_TEXT:
			url = ""
			for c in selection.data:
				if c != "\0":  #for some reason ever other character is a null.  what gives?
					url = url+c
			if url.split(':')[0] == 'feed':
				url = url[url.find(':')+1:]
			self._app.add_feed(url)
		elif targetType == self._TARGET_TYPE_URL:
			url = ""
			for c in selection.data[0:selection.data.find('\n')]:
				if c != '\0':
					url = url+c
			if url.split(':')[0] == 'feed': #stupid wordpress does 'feed:http://url.com/whatever'
				url = url[url.find(':')+1:]
			self._app.add_feed(url)
			
	def on_feedlistview_button_press_event(self, widget, event):          
		if event.button==3: #right click     
			menu = gtk.Menu()   
			
			path = widget.get_path_at_pos(int(event.x),int(event.y))
			model = widget.get_model()
			if path is None: #nothing selected
				return
			selected = model[path[0]][FeedList.FEEDID]
			is_filter = self._db.is_feed_filter(selected)  
			
			if is_filter and not ptvDB.HAS_LUCENE:
				item = gtk.MenuItem(_("Lucene required for feed filters"))
				item.set_sensitive(False)
				menu.append(item)
				separator = gtk.SeparatorMenuItem()
				menu.append(separator)

			item = gtk.MenuItem(_("Re_name"))
			item.connect('activate',self.on_rename_feed_activate)
			if self._state == S_LOADING_FEEDS:
				item.set_sensitive(False)
				
			menu.append(item)
			
			item = gtk.MenuItem(_("Edit _Tags"))
			item.connect('activate',self.on_edit_tags_activate)
			menu.append(item)
			
			item = gtk.ImageMenuItem('gtk-refresh')
			item.connect('activate',self.on_refresh_activate)
			if is_filter and not ptvDB.HAS_LUCENE:
				item.set_sensitive(False)
			menu.append(item)
			
			item = gtk.MenuItem(_("Mark as _Viewed"))
			item.connect('activate',self.on_mark_feed_as_viewed_activate)
			if is_filter and not ptvDB.HAS_LUCENE:
				item.set_sensitive(False)
			menu.append(item)
			
			item = gtk.MenuItem(_("_Delete All Media"))
			item.connect('activate',self.on_delete_feed_media_activate)
			if is_filter and not ptvDB.HAS_LUCENE:
				item.set_sensitive(False)
			menu.append(item)
			
			separator = gtk.SeparatorMenuItem()
			menu.append(separator)
			
			if not is_filter:
				if ptvDB.HAS_LUCENE:
					item = gtk.MenuItem(_("_Create Feed Filter"))
					item.connect('activate',self.on_add_feed_filter_activate)
					if self._state == S_LOADING_FEEDS:
						item.set_sensitive(False)
					menu.append(item)
				
				item = gtk.ImageMenuItem('gtk-properties')
				item.connect('activate',self.on_feed_properties_activate)
				menu.append(item)
			else:
				item = gtk.ImageMenuItem('gtk-properties')
				item.connect('activate',self.on_feed_filter_properties_activate)
				if not ptvDB.HAS_LUCENE:
					item.set_sensitive(False)
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
		self._app.poll_feeds()
		self.set_wait_cursor(False)
		
	def on_filter_changed(self, widget):
		current_filter = self._filter_model[self.get_active_filter()[1]]
		if current_filter[F_TYPE] == ptvDB.T_SEARCH and self._state == S_LOADING_FEEDS:
			self.set_active_filter(FeedList.ALL)
			return
		self._filter_selector_button.set_label(current_filter[F_COUNT])
		self._app.change_filter(current_filter[F_TEXT],current_filter[F_TYPE])
		
	def on_filter_selector_button_press_event(self, button, event):
		#if self._filter_selector_widget.is_visible() or button.get_active():
		if button.get_active():
			self._filter_selector_button.released()
			self._filter_selector_widget.Hide()
			return
		
		#figure out the onscreen location of the button by starting with the window
		#and doing a translation
		x,y =  self._filter_selector_button.window.get_position()
		y_offset = self._filter_selector_button.get_allocation().height
		if self.app_window is not None:
			x2,y2 = self._filter_selector_button.translate_coordinates(self.app_window, 0, 0)
		else: #olpc has no appwindow
			x2,y2 = self._filter_selector_button.translate_coordinates(self._layout_dock, 0, 0)
		x += x2
		y += y2 + y_offset
		#self._filter_selector_button.released()
		gtk.gdk.pointer_ungrab(event.get_time())
		self._filter_selector_widget.ShowAt(x,y)
		
		
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
				self._app.import_opml(f)
			except:
				pass
		elif response == gtk.RESPONSE_CANCEL:
			print 'Closed, no files selected'
		dialog.destroy()		
			
	def on_mark_entry_as_viewed_activate(self,event):
		try:
			entry = self.entry_list_view.get_selected()['entry_id']
			self._app.mark_entry_as_viewed(entry)
		except:
			pass
		
	def on_mark_entry_as_unviewed_activate(self,event):
		try:
			entry = self.entry_list_view.get_selected()['entry_id']
			self._app.mark_entry_as_unviewed(entry)
		except:
			pass

	def on_mark_feed_as_viewed_activate(self,event):
		feed = self.feed_list_view.get_selected()
		if feed:
			self._app.mark_feed_as_viewed(feed)
 
 	def on_play_entry_activate(self, event):
 		try:
			entry = self.entry_list_view.get_selected()['entry_id']
			self._app.play_entry(entry)
		except:
			pass
				
	def on_play_unviewed_activate(self, event):
		self._app.play_unviewed()
			
	def on_play_unviewed_clicked(self, event):
		self._app.play_unviewed()
		
	def on_preferences_activate(self, event):
		self._app.window_preferences.show()
		
	def on_quit2_activate(self,event):
		self._app.do_quit() #make the program quit, dumbass
		
	def on_refresh_activate(self, event):
		feed = self.feed_list_view.get_selected()
		self._app.refresh_feed(feed)
		
	def on_refresh_feeds_activate(self, event):
		self.set_wait_cursor()
		self._app.poll_feeds()
		self.set_wait_cursor(False)

	def on_refresh_feeds_with_errors_activate(self, event):
		self.set_wait_cursor()
		self._app.poll_feeds(ptvDB.A_ERROR_FEEDS)
		self.set_wait_cursor(False)
		
	def on_reindex_searches_activate(self, event):
		self.search_container.set_sensitive(False)
		self._app.set_state(penguintv.DEFAULT)
		self.search_entry.set_text(_("Please wait..."))
		self._app.db.doindex(self._app._done_populating)
		
	def _sensitize_search(self):
		self.search_entry.set_text("")
		self.search_container.set_sensitive(True)
		
	def on_remove_feed_activate(self, event):
		selected = self.feed_list_view.get_selected()
		if selected:
			if self._state == S_LOADING_FEEDS:
				print "Please wait the program has loaded before removing a feed."
				return 
			self._app.remove_feed(selected)
		
	def on_rename_feed_activate(self, widget):
		feed = self.feed_list_view.get_selected()
		self._window_rename_feed.set_feed_id(feed)
		self._window_rename_feed.set_feed_name(self._db.get_feed_title(feed))
		self._window_rename_feed.show()	

	def on_resume_all_activate(self, event):
		self._app.resume_resumable()
		
	def on_save_search_clicked(self, event):
		query = self.search_entry.get_text()
		if query=="":
			return
		self._window_add_search.show()
		self._window_add_search.set_query(query)		
		
	def on_search_clear_clicked(self, event):
		self._app.set_state(penguintv.DEFAULT)
		
	def on_saved_searches_activate(self, event):
		window_edit_saved_searches = EditSearchesDialog.EditSearchesDialog(os.path.join(self._glade_prefix,'penguintv.glade'),self._app)
		window_edit_saved_searches.show()
		del window_edit_saved_searches
		
	def on_search_entry_activate(self, event):
		self._app.manual_search(self.search_entry.get_text())
		
	def on_search_entry_changed(self, widget):
		if self.search_container.get_property("sensitive"):
			self._app.threaded_search(self.search_entry.get_text())
		
	def on_show_downloads_activate(self, event):
		self._app.show_downloads()
		
	def on_stop_downloads_clicked(self, widget):
		self._app.stop_downloads()
		
	#def on_stop_downloads_toggled(self, widget):
	#	print "toggled"
	#	self._app.stop_downloads_toggled(widget.get_active())
	
	def on_synchronize_activate(self, event):
		self._sync_dialog.Show()

	def on_standard_layout_activate(self, event):	
		self._app.change_layout('standard')
	
	def on_horizontal_layout_activate(self, event):
		self._app.change_layout('widescreen')	

	def on_vertical_layout_activate(self,event):
		self._app.change_layout('vertical')	
		
	def on_planet_layout_activate(self, event):
		self._app.change_layout('planet')
		
	def on_fancy_feed_display_activate(self, menuitem):
		self.feed_list_view.set_fancy(menuitem.get_active())
		self._db.set_setting(ptvDB.BOOL, '/apps/penguintv/fancy_feedlist', menuitem.get_active())
				
	def activate_layout(self, layout):
		"""gets called by app when it's ready"""
		self.changing_layout = True
		self.layout=layout
		self._app.save_settings()
		self._app.write_feed_cache()
		self._layout_dock.remove(self._layout_container)
		self._layout_dock.add(self.load_layout())
		if not ptvDB.HAS_LUCENE:
			self.search_container.hide_all()
		#can't reset changing_layout because app hasn't updated pointers yet
		
	def is_changing_layout(self):
		return self.changing_layout
		
	def on_unread_filter_toggled(self, event):
		self.feed_list_view.set_unread_toggle(self.filter_unread_checkbox.get_active())

	def display_status_message(self, m, update_category=U_STANDARD):
		"""displays a status message on the main status bar.  If this is a polling update or download
		   update, we don't overwrite what's there."""	
		if self._status_view is None:
			return
			
		current_text = self._status_view.get_status().get_text()
	
		if current_text == "":
			self._status_owner = update_category
			self._status_view.set_status(m)
		else:
			if update_category >= self._status_owner:
				self._status_view.set_status(m)
				if m == "":
					self._status_owner = U_NOBODY
				else:
					self._status_owner = update_category
			#if update_category==U_STANDARD:  #only overwrite if this is not a poll or download
			#	self._status_owner = update_category
			#	self._status_view.set_status(m)
			#elif update_category == U_POLL and self._status_owner != U_STANDARD:
			#	self._status_owner = update_category
			#	self._status_view.set_status(m)				
			#elif update_category == U_DOWNLOAD and self._status_owner == U_DOWNLOAD:
			#	self._status_view.set_status(m)
			
		return False #in case of timeouts
		
	def update_progress_bar(self, p, update_category=U_STANDARD):
		"""Update the progress bar.  if both downloading and polling, polling wins"""
		if p==-1:
			self._bar_owner = U_NOBODY
			self._status_view.set_progress_percentage(0)
		else:
			if update_category >= self._bar_owner:
				self._bar_owner = update_category
				self._status_view.set_progress_percentage(p)
		
	def _edit_tags(self):
		"""Edit Tags clicked, bring up tag editing dialog"""
		selected = self.feed_list_view.get_selected()
		self._window_edit_tags_single.set_feed_id(selected)
		self._window_edit_tags_single.set_tags(self._db.get_tags_for_feed(selected))
		self._window_edit_tags_single.show()
		
	def _unset_state(self):
		"""gets app ready to display new state by unloading current state"""
		#bring state back to default
		
		if self._state == S_MANUAL_SEARCH:
			self.search_entry.set_text("")
		if self._state == S_MANUAL_SEARCH or self._state == S_TAG_SEARCH:
			self.filter_unread_checkbox.set_sensitive(True)
		if self._state == S_LOADING_FEEDS:
			self._widgetTree.get_widget("feed_add_button").set_sensitive(True)
			self._widgetTree.get_widget("feed_remove").set_sensitive(True)
			if not ptvDB.RUNNING_SUGAR:
				#these are menu items
				self._widgetTree.get_widget("add_feed").set_sensitive(True)
				self._widgetTree.get_widget("add_feed_filter").set_sensitive(True)
				self._widgetTree.get_widget("remove_feed").set_sensitive(True)
				self._widgetTree.get_widget("rename_feed").set_sensitive(True)
			self.display_status_message("")	
			self.update_progress_bar(-1,U_LOADING)
			
			
	def set_state(self, new_state, data=None):
		d = {penguintv.DEFAULT: S_DEFAULT,
			 penguintv.MANUAL_SEARCH: S_MANUAL_SEARCH,
			 penguintv.TAG_SEARCH: S_TAG_SEARCH,
			 #penguintv.ACTIVE_DOWNLOADS: S_DEFAULT,
			 penguintv.LOADING_FEEDS: S_LOADING_FEEDS}
			 
		new_state = d[new_state]
		
		if self._state == new_state:
			return	
			
		self._unset_state()
			 
		if new_state == S_MANUAL_SEARCH:
			if self.get_active_filter()[1] != FeedList.SEARCH:	
				self.set_active_filter(FeedList.SEARCH)
			self.filter_unread_checkbox.set_sensitive(False)
		if new_state == S_TAG_SEARCH:
			self.search_entry.set_text("")
			self.filter_unread_checkbox.set_sensitive(False)
		
		if new_state == S_LOADING_FEEDS:
			self._widgetTree.get_widget("feed_add_button").set_sensitive(False)
			self._widgetTree.get_widget("feed_remove").set_sensitive(False)
			
			if not ptvDB.RUNNING_SUGAR: 
				#these are menu items
				self._widgetTree.get_widget("add_feed").set_sensitive(False)
				self._widgetTree.get_widget("add_feed_filter").set_sensitive(False)
				self._widgetTree.get_widget("remove_feed").set_sensitive(False)
				self._widgetTree.get_widget("rename_feed").set_sensitive(False)
			
		self._state = new_state

	def update_filters(self):
		"""update the filter combo box with the current list of filters"""
		#get name of current filter, if a tag
		current_filter = self.get_active_filter()[0]
		#if current_filter not in BUILTIN_TAGS:	
		#	if current_filter not in self._db.get_all_tags():
		#		current_filter = ALL  #in case the current filter is an out of date tag
		self._filter_model.clear()

		self._filter_model.append([FeedList.BUILTIN_TAGS[0],
				  	  FeedList.BUILTIN_TAGS[0]+" ("+str(len(self._db.get_feedlist()))+")",
				  	  False,
				  	  False,
				  	  False,
				  	  ptvDB.T_BUILTIN])
		for builtin in FeedList.BUILTIN_TAGS[1:]:
			if not ptvDB.HAS_LUCENE and builtin == FeedList.BUILTIN_TAGS[FeedList.SEARCH]:
				continue
			self._filter_model.append([builtin,builtin,False,0,False,ptvDB.T_BUILTIN])

		if ptvDB.HAS_LUCENE:	
			tags = self._db.get_all_tags(ptvDB.T_SEARCH)	
			if tags:
				self._filter_model.append(["---","---",True,0,False,ptvDB.T_BUILTIN])
				for tag,favorite in tags:
					self._filter_model.append([tag,tag,False,0,True,ptvDB.T_SEARCH])
		
		
		tags = self._db.get_all_tags(ptvDB.T_TAG)	
		if tags:
			self._filter_model.append(["---","---",True,0,True,ptvDB.T_BUILTIN])
			
			for tag,favorite in tags:
				self._filter_model.append([tag,tag+" ("+str(self._db.get_count_for_tag(tag))+")",False,favorite,True,ptvDB.T_TAG])
		
		#get index for our previously selected tag
		index = self.get_index_for_filter(current_filter)
		if not self.changing_layout:
			if index is not None:
				self.set_active_filter(index)
			else:
				self.set_active_filter(FeedList.ALL)
				
	def set_tag_favorite(self, tag_name, favorite):
		self._db.set_tag_favorite(tag_name, favorite)
		names = [m[F_TEXT] for m in self._filter_model]
		index = names.index(tag_name)
		self._filter_model[index][F_FAVORITE] = favorite
				
	def set_active_filter(self, index):
		#just in case...
		self._filter_selector_button.released()
		self._filter_selector_button.set_active(False)
		if self._active_filter_index == index:
			return
		self._active_filter_index = index
		self._active_filter_name = self._filter_model[index][F_TEXT]
		self.on_filter_changed(None)
			
	def get_filter_name(self, filt):
		return self._filter_model[filt][F_TEXT]
		
	def get_active_filter(self):
		return (self._active_filter_name,self._active_filter_index) 
		
	def rename_filter(self, old_name, new_name):
		names = [m[F_TEXT] for m in self._filter_model]
		index = names.index(old_name)
		self._filter_model[index][F_TEXT] = new_name
		self._filter_model[index][F_COUNT] = new_name
		
	def get_index_for_filter(self, filter_name):
		names = [f[F_TEXT] for f in self._filter_model]
		if filter_name not in names:
			return None
		return names.index(filter_name)

	def select_feed(self, feed_id):
		self.set_active_filter(FeedList.ALL)
		self.filter_unread_checkbox.set_active(False)
		self.feed_list_view.set_selected(feed_id)
		self.feed_list_view.resize_columns()

	def update_disk_usage(self, size):
		if self._disk_usage_widget is None:
			return
		self._disk_usage_widget.set_text(utils.format_size(size))

	def update_download_progress(self):
		progresses = self._mm.get_download_list(Downloader.DOWNLOADING)
		queued     = self._mm.get_download_list(Downloader.QUEUED)
		paused     = self._mm.get_download_list(Downloader.PAUSED)
		#print len(progresses)
		if len(progresses)+len(queued)==0:
			self.display_status_message("")
			self.update_progress_bar(-1,U_DOWNLOAD)
			self._download_view.update_downloads()
			total = len(progresses) + len(queued) + len(paused)
			self._update_notebook_tabs(total)
			return
		total_size = 0
		downloaded = 0
		for d in progresses+queued:
			if d.total_size<=0:
				total_size += 1
			else:
				total_size += d.total_size
			downloaded += (d.progress/100.0)*d.total_size
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
		
		self._download_view.update_downloads()
		self._update_notebook_tabs(len(progresses)+len(queued)+len(paused))
		
	def download_finished(self, d):
		self._download_view.update_downloads()
		
	def _update_notebook_tabs(self, number):
		if number == 0:
			self._notebook.set_show_tabs(False)
			self._notebook.set_current_page(0)
		else:
			self._downloads_label.set_markup(_('<span size="small">Downloads(%d)</span>') % number)
			self._notebook.set_show_tabs(True)
				
	def desensitize(self):
		if self.app_window:
			self.app_window.set_sensitive(False)
		else:
			self._layout_container.set_sensitive(False)
		while gtk.events_pending(): #make sure the sensitivity change goes through
			gtk.main_iteration()
	
class ShouldntHappenError(Exception):
	def __init__(self,error):
		self.error = error
	def __str__(self):
		return self.error
