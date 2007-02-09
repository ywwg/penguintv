import gtk
import gtk.glade
import gobject
import sys, os, os.path
import sets

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
F_FAVORITE = 0
F_NAME     = 1
F_DISPLAY  = 2
F_TYPE     = 3

#notebook tabs
N_FEEDS     = 0
N_PLAYER    = 1
N_DOWNLOADS = 2

import EditTagsMultiDialog
import AddSearchTagDialog
import EditSearchesDialog
import FeedFilterDialog
import FeedPropertiesDialog
import FeedFilterPropertiesDialog
import SynchronizeDialog
import FilterSelectorDialog
import MainWindow, FeedList, EntryList, EntryView, PlanetView, DownloadView
if utils.HAS_GSTREAMER:
	import GStreamerPlayer

class MainWindow:
	COLUMN_TITLE = 0
	COLUMN_ITEM = 1
	COLUMN_BOLD = 2
	COLUMN_STICKY_FLAG = 3

	def __init__(self, app, glade_prefix, use_internal_player=False, window=None):
		self._app = app
		self._app_inited = False
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
		self._fullscreen = False
		
		self._use_internal_player = False
		if utils.HAS_GSTREAMER and use_internal_player:
			self._use_internal_player = True
		
		self._active_filter_name = FeedList.BUILTIN_TAGS[FeedList.ALL]
		self._active_filter_index = FeedList.ALL
		
		##other WINDOWS we open
		self._window_add_search = AddSearchTagDialog.AddSearchTagDialog(gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "window_add_search_tag",'penguintv'),self._app)
		
		self._feed_properties_dialog = FeedPropertiesDialog.FeedPropertiesDialog(gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "window_feed_properties",'penguintv'),self._app)
		self._feed_filter_properties_dialog = FeedFilterPropertiesDialog.FeedFilterPropertiesDialog(gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "window_filter_properties",'penguintv'),self._app)
		self._sync_dialog = SynchronizeDialog.SynchronizeDialog(os.path.join(self._glade_prefix,'penguintv.glade'), self._db)
		self._filter_selector_dialog = FilterSelectorDialog.FilterSelectorDialog(gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "dialog_tag_favorites",'penguintv'),self)
		
		#signals
		self._app.connect('feed-added', self.__feed_added_cb)
		self._app.connect('feed-removed', self.__feed_removed_cb)
		self._app.connect('feed-polled', self.__feed_polled_cb)
	
		#most of the initialization is done on Show()
		if window:
			window.connect('show', self.Show)
		
	def __link_activated_cb(self, o, link):
		self._app.activate_link(link)
				
	def __entrylistview_list_resized_cb(self, entrylistview, new_width):
		if self.layout == "widescreen" and self.app_window is not None:			
			listnview_width = self.app_window.get_size()[0] - self.feed_pane.get_position()
			if listnview_width - new_width < 400: #ie, entry view will be tiny
				self.entry_pane.set_position(listnview_width-400) #MAGIC NUMBER
			elif new_width > 20: #MAGIC NUMBER
				self.entry_pane.set_position(new_width)
				
	def __feed_added_cb(self, app, feed_id, success):
		if success:
			self.select_feed(feed_id)
			self.display_status_message(_("Feed Added"))
			gobject.timeout_add(2000, self.display_status_message, "")
		else:
			self.display_status_message(_("Error adding feed"))
			self.select_feed(feed_id)
			
	def __feed_polled_cb(self, app, feed_id):
		self.display_status_message(_("Feed Updated"))
		gobject.timeout_add(2000, self.display_status_message, "")
			
	def __feed_removed_cb(self, app, feed_id):
		self.update_filters()

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
		
		if not EntryView.MOZ_OK and self.layout == "planet":
			print "requested planet layout, but can't use because gtkmozembed isn't installed correctly (won't import)"
			self.layout = "standard"
		
		if dock_widget is None:  #if we are loading in a regular window...
			self._load_app_window()
			if not utils.HAS_LUCENE:
				#remove UI elements that don't apply without search
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
			self._layout_dock = self.load_notebook()
			self._layout_dock.add(self.load_layout())
			vbox.pack_start(self._notebook)
			self._status_view = MainWindow._my_status_view()
			vbox.pack_start(self._status_view, False, False)
			dock_widget.add(vbox)
			dock_widget.show_all()
			self._widgetTree.get_widget('debug_exit_toolbutton').hide()
			self._window = dock_widget
		self._notebook.show_only(N_FEEDS)
		if not utils.HAS_LUCENE:
			self.search_container.hide_all()
		#if utils.RUNNING_SUGAR:
		#	self._filter_container.hide_all()
		if self._use_internal_player:
			if self._gstreamer_player.get_queue_count() > 0:
				self._notebook.show_page(N_PLAYER)
				
		if not self._app_inited:
			gobject.idle_add(self._app.post_show_init)
			self._app_inited = True
				
	def _load_toolbar(self):
		if self._widgetTree is None:
			self._widgetTree = gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), 'toolbar1','penguintv')
			for key in dir(self.__class__): #python insaneness
				if key[:3] == 'on_':
					self._widgetTree.signal_connect(key, getattr(self, key))
		toolbar = self._widgetTree.get_widget('toolbar1')
		
		#set up separator (see below)
		vseparator = self._widgetTree.get_widget('vseparator1')
		vseparator_toolitem = self._widgetTree.get_widget('toolitem1')
		vseparator_toolitem.set_expand(True)
		vseparator.set_draw(False)
		
		if utils.RUNNING_SUGAR:
			vsep2 = self._widgetTree.get_widget('vseparator2')
			vseparator.set_property('visible',True)
			pref_button = self._widgetTree.get_widget('preferences_toolbutton')
			pref_button.set_property('visible',True)
			pref_button.set_property('label',_("Preferences"))
			
			debug_exit_button = self._widgetTree.get_widget('debug_exit_toolbutton')
			debug_exit_button.set_property('visible',False)
			#debug_exit_button.set_property('label',_("Exit (DEBUG)"))
			
			theme = gtk.icon_theme_get_default()
			theme.append_search_path(os.path.join(self._glade_prefix, "icons"))
			self._widgetTree.get_widget('feed_add_button').set_stock_id(None)
			self._widgetTree.get_widget('feed_add_button').set_icon_name('stock-add')
			self._widgetTree.get_widget('feed_remove').set_stock_id(None)
			self._widgetTree.get_widget('feed_remove').set_icon_name('stock-remove')
			self._widgetTree.get_widget('feeds_poll').set_stock_id(None)
			self._widgetTree.get_widget('feeds_poll').set_icon_name('stock-continue')
			self._widgetTree.get_widget('download_unviewed').set_stock_id(None)
			self._widgetTree.get_widget('download_unviewed').set_icon_name('stock-go-down')
			self._widgetTree.get_widget('play_unviewed').set_stock_id(None)
			self._widgetTree.get_widget('play_unviewed').set_icon_name('stock-media-play')
			self._widgetTree.get_widget('preferences_toolbutton').set_stock_id(None)
			self._widgetTree.get_widget('preferences_toolbutton').set_icon_name('stock-preferences')
		self._disk_usage_widget = self._widgetTree.get_widget('disk_usage')
		self._disk_usage_widget.set_use_markup(True)
		if utils.RUNNING_SUGAR:
			l = self._widgetTree.get_widget('using_label')
			l.set_use_markup(True)
			l.set_markup(_('<span color="#FFFFFF">Using: </span>'))
	
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
		self._widgetTree = gtk.glade.XML(self._glade_prefix+'/penguintv.glade', 'app','penguintv')
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
		self._notebook = NotebookManager()
		self._notebook.set_property('tab-border',0)
		label = gtk.Label(_('<span size="small">Feeds</span>'))
		label.set_property('use-markup',True)
		vbox = gtk.VBox()
		self._notebook.append_page(vbox, label)
		
		p_vbox = gtk.VBox()
		if self._use_internal_player:
			self._gstreamer_player = GStreamerPlayer.GStreamerPlayer(p_vbox)
			self._gstreamer_player.connect('item-queued', self._on_player_item_queued)
			self._gstreamer_player.connect('items-removed', self._on_player_items_removed)
			self._gstreamer_player.Show()
		self._player_label = gtk.Label('<span size="small">'+_('Player')+'</span>')
		self._player_label.set_property('use-markup',True)
		self._notebook.append_page(p_vbox, self._player_label)
		
		self._downloads_label = gtk.Label(_('<span size="small">Downloads</span>'))
		self._downloads_label.set_property('use-markup',True)
		self._download_view = DownloadView.DownloadView(self._app, self._mm, self._db, self._glade_prefix+'/penguintv.glade')
		self._notebook.append_page(self._download_view.get_widget(), self._downloads_label)
		
		#self._notebook.set_show_tabs(False)
		self._notebook.set_property('show-border', False)
		self._notebook.connect('realize', self._on_notebook_realized)
		
		self._notebook.show_all()
		return vbox
		
	def get_gst_player(self):
		try:
			return self._gstreamer_player
		except:
			print "no gstreamer player to get"
			return None
		
	def notebook_select_page(self, page):
		self._notebook.set_current_page(page)
		
	def load_layout(self):
		components = gtk.glade.XML(self._glade_prefix+'/penguintv.glade', self.layout+'_layout_container','penguintv') #MAGIC
		self._layout_container = components.get_widget(self.layout+'_layout_container')
		#dock_widget.add(self._layout_container)
		
		fancy = self._db.get_setting(ptvDB.BOOL, '/apps/penguintv/fancy_feedlist', True)
		if utils.RUNNING_SUGAR:
			fancy = False
		
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
		if utils.RUNNING_SUGAR:
			renderer = EntryView.MOZILLA
			
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
					self.entry_view = EntryView.EntryView(components, self.feed_list_view, 
										 				   self.entry_list_view, self._app, self, x)
				else:
					self.entry_view = PlanetView.PlanetView(components, self.feed_list_view, 
									                        self._app, self, self._db, x)
			except Exception, e:
				print e
				if renderer == EntryView.DEMOCRACY_MOZ:
					if _FORCE_DEMOCRACY_MOZ:
						load_renderer(EntryView.DEMOCRACY_MOZ,recur+1)
					else:
						print "Error instantiating Democracy Mozilla renderer, falling back to GTKHTML"
						print "(if running from source dir, build setup.py and copy MozillaBrowser.so to democracy_moz/)"
						load_renderer(EntryView.GTKHTML,recur+1)
				else:
					print "Error loading renderer"
					self._app.do_quit()
		
		if self.layout != "planet":
			self.entry_list_view = EntryList.EntryList(components, self._app, self.feed_list_view, self, self._db)
			load_renderer(renderer)
		else:
			load_renderer(renderer)
			self.entry_list_view = self.entry_view
		
		if renderer == EntryView.GTKHTML:
			self._widgetTree.get_widget('planet_layout').hide()	
			
		for key in dir(self.__class__): #python insaneness
			if key[:3] == 'on_':
				components.signal_connect(key, getattr(self, key))
				
		#some more signals
		self.feed_list_view.connect('link-activated', self.__link_activated_cb)

		if self.layout != "planet":
			self.entry_list_view.connect('entrylist-resized', self.__entrylistview_list_resized_cb)
			#if we connected this in planetview, we'd activate links twice
			self.entry_list_view.connect('link-activated', self.__link_activated_cb)
		
		self.entry_view.connect('link-activated', self.__link_activated_cb)
				
		#major WIDGETS
		self.feed_pane = components.get_widget('feed_pane')
		self._feedlist = components.get_widget('feedlistview')
		if self.layout != "planet":
			self.entry_pane = components.get_widget('entry_pane')
		else:
			self.entry_pane = self.feed_pane #cheat
		
		self._filter_container = components.get_widget('filter_container')
		self._filter_selector_button = components.get_widget('filter_selector_button')
		#self._filter_menubar = components.get_widget('filter_menubar')
		#self._filter_menuitem = gtk.MenuItem()#components.get_widget('filter_menu_root')
		self._filter_menu = gtk.Menu()
		#self._filter_menu.append(self._filter_menuitem)
		self._filter_menu.attach_to_widget(self._filter_selector_button, (lambda widget,menu:widget))
		self._filters = [] #text, text to display, type
		self._favorite_filters = [] #text, text to display, type
		
		self.search_entry = components.get_widget('search_entry')
		completion = gtk.EntryCompletion()
		completion_model = gtk.ListStore(str, str, int) #name, display, index
		completion.set_model(completion_model)
		renderer = gtk.CellRendererText()
		completion.pack_start(renderer)
		completion.add_attribute(renderer, 'text', 1)
		def match_func(comp, string, iter):
			try: return comp.get_model()[iter][0].upper().startswith(string.upper())
			except: return False
		completion.set_match_func(match_func)
		#completion.set_text_column(0)
		completion.connect('match-selected',self._on_completion_match_selected, 2)
		self.search_entry.set_completion(completion)
		self.search_container = components.get_widget('search_container')
		
		self.update_filters()
		self.set_active_filter(FeedList.ALL)
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
		self.entry_pane.set_position(val)
		
		val = self._db.get_setting(ptvDB.STRING, '/apps/penguintv/default_filter')
		if val is not None:
			try:
				filter_index = [row[F_NAME] for row in self._filters].index(val)
				cur_filter = self._filters[filter_index]
				if utils.HAS_LUCENE:
					if cur_filter[F_TYPE] == ptvDB.T_SEARCH or filter_index==FeedList.SEARCH:
						self.set_active_filter(FeedList.ALL)
					else:
						self.set_active_filter(filter_index)
				else:
					self.set_active_filter(filter_index)
			except ValueError: #didn't find the item in the model (.index(val) fails)
				self.set_active_filter(FeedList.ALL)
		else:
			self.set_active_filter(FeedList.ALL)
		#sys.stderr.write("done")
		return self._layout_container
			
	def Hide(self):
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
		#	return self._layout_dock.get_parent_window()
		return self._window
		
	def toggle_fullscreen(self, fullscreen):
		if not fullscreen:
			self._notebook.set_show_tabs(True)
			self._gstreamer_player.toggle_controls(fullscreen)
			self._window.window.set_cursor(None)
			if not utils.RUNNING_SUGAR:
				self.app_window.window.unfullscreen()
				self._widgetTree.get_widget('bonobodockitem1').show()
				self._widgetTree.get_widget('bonobodockitem2').show()
				self._widgetTree.get_widget('appbar').show()
			else:
				self._widgetTree.get_widget('toolbar1').show()
				self._status_view.show()
		else:
			self._notebook.set_show_tabs(False)
			self._gstreamer_player.toggle_controls(fullscreen)
			pixmap = gtk.gdk.Pixmap(None, 1, 1, 1)
			color = gtk.gdk.Color()
			cursor = gtk.gdk.Cursor(pixmap, pixmap, color, color, 0, 0)
			self._window.window.set_cursor(cursor)
			if not utils.RUNNING_SUGAR:
				self._widgetTree.get_widget('bonobodockitem1').hide()
				self._widgetTree.get_widget('bonobodockitem2').hide()
				self._widgetTree.get_widget('appbar').hide()
				self.app_window.window.fullscreen()
			else:
				self._widgetTree.get_widget('toolbar1').hide()
				self._status_view.hide()

	def on_about_activate(self,event):
		widgets = gtk.glade.XML(os.path.join(self._glade_prefix,'penguintv.glade'), "aboutdialog1",'penguintv')
		about_box = widgets.get_widget('aboutdialog1')
		about_box.set_version(utils.VERSION)
		about_box.connect('response', self.on_about_response)
		about_box.show_all()
		
	def on_about_response(self, widget, event):
		widget.destroy()

	def on_app_delete_event(self,event,data):
		self._app.do_quit()
		
	def on_app_destroy_event(self,event,data):
		self._app.do_quit()
		
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
			self._feed_properties_dialog.set_tags(self._db.get_tags_for_feed(selected))
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
		entry = self.entry_list_view.get_selected()['entry_id']
		self._app.download_entry(entry)
			
	def on_download_unviewed_activate(self, event):
		self._app.download_unviewed()
				
	def on_download_unviewed_clicked(self,event):
		self._app.download_unviewed()
			
	def on_delete_entry_media_activate(self,event):
		selected = self.entry_list_view.get_selected()['entry_id']
		self._app.delete_entry_media(selected)
			
	def on_delete_feed_media_activate(self,event):
		selected = self.feed_list_view.get_selected()
		if selected:
			self._app.delete_feed_media(selected)
			
	def on_edit_tags_for_all_activate(self, event):
		"""Bring up mass tag creation window"""
		window_edit_tags_multi = EditTagsMultiDialog.EditTagsMultiDialog(gtk.glade.XML(self._glade_prefix+'/penguintv.glade', "window_edit_tags_multi",'penguintv'),self._app)
		window_edit_tags_multi.show()
		window_edit_tags_multi.set_feed_list(self._db.get_feedlist())
			
	def on_export_opml_activate(self, event):
		self._app.export_opml()
		
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
			
			if is_filter and not utils.HAS_LUCENE:
				item = gtk.MenuItem(_("Lucene required for feed filters"))
				item.set_sensitive(False)
				menu.append(item)
				separator = gtk.SeparatorMenuItem()
				menu.append(separator)

			item = gtk.ImageMenuItem('gtk-refresh')
			item.connect('activate',self.on_refresh_activate)
			if is_filter and not utils.HAS_LUCENE:
				item.set_sensitive(False)
			menu.append(item)
			
			item = gtk.MenuItem(_("Mark as _Viewed"))
			item.connect('activate',self.on_mark_feed_as_viewed_activate)
			if is_filter and not utils.HAS_LUCENE:
				item.set_sensitive(False)
			menu.append(item)
			
			item = gtk.MenuItem(_("_Delete All Media"))
			item.connect('activate',self.on_delete_feed_media_activate)
			if is_filter and not utils.HAS_LUCENE:
				item.set_sensitive(False)
			menu.append(item)
			
			item = gtk.ImageMenuItem(_("_Remove Feed"))
			img = gtk.image_new_from_stock('gtk-remove',gtk.ICON_SIZE_MENU)
			item.set_image(img)
			item.connect('activate',self.on_remove_feed_activate)
			if self._state == S_LOADING_FEEDS:
				item.set_sensitive(False)
			menu.append(item)

			
			separator = gtk.SeparatorMenuItem()
			menu.append(separator)
			
			if not is_filter:
				if utils.HAS_LUCENE:
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
				if not utils.HAS_LUCENE:
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
		
	def _on_filter_menu_activate(self, widget, filter_name):
		names = [f[F_NAME] for f in self._filters]
		self._active_filter_name = filter_name	
		self._active_filter_index = names.index(filter_name)
		self.on_filter_changed()
		
	def on_edit_favorite_tags(self, widget):
		#self._filters
		#self._favorite_filters #ordered
		self._filter_selector_dialog.set_taglists(self._filters, self._favorite_filters)
		self._filter_selector_dialog.Show()	
		
	def on_filter_changed(self, widget=None):
		current_filter = self._filters[self.get_active_filter()[1]]
		#label = self._filter_menuitem.get_children()[0]
		#label.set_text(current_filter[1])
		self._filter_selector_button.set_label(current_filter[F_DISPLAY])
		if current_filter[F_TYPE] == ptvDB.T_SEARCH and self._state == S_LOADING_FEEDS:
			self.set_active_filter(FeedList.ALL)
			return
		self._app.change_filter(current_filter[F_NAME],current_filter[F_TYPE])
		
	def on_filter_selector_button_press_event(self, button, event):
		self._filter_menu.popup(None, None, self._position_menu_func, event.button, event.get_time())
	
	def _position_menu_func(self, data=None):
		#figure out the onscreen location of the button by starting with the window
		#and doing a translation
		x,y = self._filter_selector_button.window.get_position()
		y_offset = self._filter_selector_button.get_allocation().height
		if self.app_window is not None:
			x2,y2 = self._filter_selector_button.translate_coordinates(self.app_window, 0, 0)
		else: #olpc has no appwindow, it has a 'window' that's the old dock_widget
			x2,y2 = self._filter_selector_button.translate_coordinates(self._window, 0, 0)
		x += x2
		y += y2 + y_offset
		return (x,y,True)	
		
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
			f = open(dialog.get_filename(), "r")
			self.display_status_message(_("Importing Feeds, please wait..."))
			self._app.import_subscriptions(f)
		elif response == gtk.RESPONSE_CANCEL:
			print 'Closed, no files selected'
		dialog.destroy()		
		
	def on_app_key_press_event(self, widget, event):
		keyname = gtk.gdk.keyval_name(event.keyval)
		if event.state & gtk.gdk.CONTROL_MASK:
			if keyname == 'k':
				self.search_entry.grab_focus()
		if keyname == 'f':
			if self._notebook.get_current_page() == N_PLAYER:
				self._fullscreen = not self._fullscreen
				self.toggle_fullscreen(self._fullscreen)
		
	def on_mark_entry_as_viewed_activate(self,event):
		entry = self.entry_list_view.get_selected()['entry_id']
		self._app.mark_entry_as_viewed(entry)
		
	def on_mark_entry_as_unviewed_activate(self,event):
		entry = self.entry_list_view.get_selected()['entry_id']
		self._app.mark_entry_as_unviewed(entry)
		
	def on_mark_feed_as_viewed_activate(self,event):
		feed = self.feed_list_view.get_selected()
		if feed:
			self._app.mark_feed_as_viewed(feed)
			
	def _on_notebook_realized(self, widget):
		self._notebook.show_page(N_FEEDS)
		if not utils.HAS_LUCENE:
			self.search_container.hide_all()
		#if utils.RUNNING_SUGAR:
		#	self._filter_container.hide_all()
	
		if self._use_internal_player:
			self._gstreamer_player.load()
			if self._gstreamer_player.get_queue_count() > 0:
				self._notebook.show_page(N_PLAYER)
		
	#def _on_gst_player_realized(self, widget):
	#	print "seek seek seek"
	#	self._gstreamer_player.seek_to_saved_position()
 
 	def on_play_entry_activate(self, event):
 		entry = self.entry_list_view.get_selected()['entry_id']
		self._app.play_entry(entry)
				
	def on_play_unviewed_activate(self, event):
		self._app.play_unviewed()
			
	def on_play_unviewed_clicked(self, event):
		self._app.play_unviewed()
		
	def _on_player_item_queued(self, player, filename, name):
		self._notebook.show_page(N_PLAYER)	
		#if player.get_queue_count() == 1:
		#	try:
		#		self._notebook.set_current_page(N_PLAYER)
		#		player.play()
		#	except:
		#		pass #fails while loading
		self._player_label.set_markup(_('<span size="small">Player (%d)</span>') % player.get_queue_count())
		
	def _on_player_items_removed(self, player):
		if player.get_queue_count() == 0:
			self._notebook.hide_page(N_PLAYER)
			player.stop()
		self._player_label.set_markup(_('<span size="small">Player (%d)</span>') % player.get_queue_count())
		
	def on_preferences_activate(self, event):
		self._app.window_preferences.show()
		
	def on_quit2_activate(self,event):
		self._app.do_quit() #make the program quit, dumbass
		##DEBUG for exit_toolbutton
		#if utils.RUNNING_SUGAR:
		#	gtk.main_quit()
		
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
		assert self._state != S_LOADING_FEEDS
		selected = self.feed_list_view.get_selected()
		if selected:
			dialog = gtk.Dialog(title=_("Really Delete Feed?"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("Are you sure you want to delete this feed?"))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			response = dialog.run()
			dialog.hide()
			del dialog
			if response == gtk.RESPONSE_ACCEPT:		
				self._app.remove_feed(selected)
		
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
		pass
		#self.search_entry.get_completion().complete()
		#if self.search_container.get_property("sensitive"):
		#	self._app.threaded_search(self.search_entry.get_text())
		
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
		self._notebook.show_only(N_FEEDS)
		if not utils.HAS_LUCENE:
			self.search_container.hide_all()
		#if utils.RUNNING_SUGAR:
		#	self._filter_container.hide_all()			
		if self._use_internal_player:
			if self._gstreamer_player.get_queue_count() > 0:
				self._notebook.show_page(N_PLAYER)
		#can't reset changing_layout because app hasn't updated pointers yet
		
	def is_changing_layout(self):
		return self.changing_layout
		
	def display_status_message(self, m, update_category=U_STANDARD):
		"""displays a status message on the main status bar.  If this is a polling update or download
		   update, we don't overwrite what's there."""	
		if self._status_view is None:
			return
		
		#gtk.gdk.threads_enter()
			
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
		
		#gtk.gdk.threads_leave()	
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
		
	def _unset_state(self):
		"""gets app ready to display new state by unloading current state"""
		#bring state back to default
		if self._state == S_MANUAL_SEARCH:
			self.search_entry.set_text("")
		if self._state == S_LOADING_FEEDS:
			self._widgetTree.get_widget("feed_add_button").set_sensitive(True)
			self._widgetTree.get_widget("feed_remove").set_sensitive(True)
			if not utils.RUNNING_SUGAR:
				#these are menu items
				self._widgetTree.get_widget("add_feed").set_sensitive(True)
				self._widgetTree.get_widget("add_feed_filter").set_sensitive(True)
				self._widgetTree.get_widget("remove_feed").set_sensitive(True)
				self._widgetTree.get_widget("properties").set_sensitive(True)
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
		if new_state == S_TAG_SEARCH:
			self.search_entry.set_text("")
		
		if new_state == S_LOADING_FEEDS:
			self._widgetTree.get_widget("feed_add_button").set_sensitive(False)
			self._widgetTree.get_widget("feed_remove").set_sensitive(False)
			
			if not utils.RUNNING_SUGAR: 
				#these are menu items
				self._widgetTree.get_widget("add_feed").set_sensitive(False)
				self._widgetTree.get_widget("add_feed_filter").set_sensitive(False)
				self._widgetTree.get_widget("remove_feed").set_sensitive(False)
				self._widgetTree.get_widget("properties").set_sensitive(False)
			
		self._state = new_state

	def update_filters(self):
		"""update the filter combo box with the current list of filters"""
		#get name of current filter, if a tag
		current_filter = self.get_active_filter()[0]
		self._filters = []
		self._favorite_filters = []
		for child in self._filter_menu.get_children():
			self._filter_menu.remove(child)
		completion_model = self.search_entry.get_completion().get_model()
		completion_model.clear()
				
		i=-1 #we only set i here so that searches and regular tags have incrementing ids
		for builtin in FeedList.BUILTIN_TAGS:
			if not utils.HAS_LUCENE and builtin == FeedList.BUILTIN_TAGS[FeedList.SEARCH]:
				continue
			i+=1
			if builtin == _("All Feeds"):
				text = builtin+" ("+str(len(self._db.get_feedlist()))+")"
				self._filters.append([0,builtin,text,ptvDB.T_BUILTIN])
				menuitem = gtk.MenuItem(text)
			else:
				self._filters.append([0,builtin,builtin,ptvDB.T_BUILTIN])
				menuitem = gtk.MenuItem(builtin)
			menuitem.connect('activate',self._on_filter_menu_activate, builtin)
			self._filter_menu.append(menuitem)

		has_search = False
		if utils.HAS_LUCENE:	
			tags = self._db.get_all_tags(ptvDB.T_SEARCH)	
			if tags:
				has_search = True
				for tag,favorite in tags:
					i+=1
					self._filters.append([favorite, tag,tag,ptvDB.T_SEARCH])
					completion_model.append([tag,_('tag: %s') % (tag,), i])
					if favorite > 0:
						self._favorite_filters.append([favorite, tag,tag, i]) 
		
		tags = self._db.get_all_tags(ptvDB.T_TAG)	
		if tags:
			sep = gtk.SeparatorMenuItem()
			self._filter_menu.append(sep)
			for tag,favorite in tags:
				i+=1
				self._filters.append([favorite, tag,tag+" ("+str(self._db.get_count_for_tag(tag))+")",ptvDB.T_TAG])
				completion_model.append([tag,_('tag: %s') % (tag,), i])
				if favorite > 0:
					self._favorite_filters.append([favorite, tag,tag+" ("+str(self._db.get_count_for_tag(tag))+")", i])
					
		self._favorite_filters.sort()
		self._favorite_filters = [f[1:] for f in self._favorite_filters]
		
		for fav in self._favorite_filters:
			menuitem = gtk.MenuItem(fav[1])
			menuitem.connect('activate',self._on_filter_menu_activate, fav[0])
			self._filter_menu.append(menuitem)
			
		if tags:
			all_tags_item = gtk.MenuItem(_('All Tags'))
			all_tags_submenu = gtk.Menu()
			if has_search:
				for f in self._filters:
					if f[F_TYPE] == ptvDB.T_SEARCH:
						menuitem = gtk.MenuItem(f[F_DISPLAY])
						menuitem.connect('activate',self._on_filter_menu_activate, f[F_NAME])
						all_tags_submenu.append(menuitem)
				sep = gtk.SeparatorMenuItem()
				all_tags_submenu.append(sep)
			for f in self._filters:
				if f[F_TYPE] == ptvDB.T_TAG:
					menuitem = gtk.MenuItem(f[F_DISPLAY])
					menuitem.connect('activate',self._on_filter_menu_activate, f[F_NAME])
					all_tags_submenu.append(menuitem)
			all_tags_item.set_submenu(all_tags_submenu)
			self._filter_menu.append(all_tags_item)
			
		#sep = gtk.SeparatorMenuItem()
		#self._filter_menu.append(sep)
		
		menuitem = gtk.MenuItem(_('Edit Favorite Tags...'))
		menuitem.connect('activate', self.on_edit_favorite_tags)
		self._filter_menu.append(menuitem) 
		self._filter_menu.show_all()	
		
		#get index for our previously selected tag
		index = self.get_filter_index(current_filter)
		if not self.changing_layout:
			if index is not None:
				self.set_active_filter(index)
			else:
				self.set_active_filter(FeedList.ALL)
				
	def set_tag_favorites(self, tag_list):
		old_order = [f[0] for f in self._favorite_filters]
		
		i=0
		for t in tag_list[:len(old_order)]:
			i+=1
			if t != old_order[i-1]:
				self._db.set_tag_favorite(t, i)
		
		i=len(old_order)-1
		for t in tag_list[len(old_order):]:
			i+=1
			self._db.set_tag_favorite(t, i)
				
		old = sets.Set(old_order)
		new = sets.Set(tag_list)
		removed = list(old.difference(new))
		for t in removed:
			self._db.set_tag_favorite(t, 0)
		self.update_filters()
		
	def _on_completion_match_selected(self, completion, model, iter, column):
		self.search_entry.set_text("")
		self.set_active_filter(model[iter][column])
				
	def set_active_filter(self, index):
		if self._active_filter_index == index:
			return
		self._active_filter_index = index
		self._active_filter_name = self._filters[index][F_NAME]
		self.on_filter_changed()
		
	def finish(self):
		if self._use_internal_player:
			self._gstreamer_player.finish()
		self.desensitize()
			
	def get_filter_name(self, filt):
		return self._filters[filt][F_NAME]
		
	def get_filter_index(self, string):
		names = [m[F_NAME] for m in self._filters]
		try:
			index = names.index(string)
			if names not in FeedList.BUILTIN_TAGS:
				return index
			return None
		except:
			return None
		
	def get_active_filter(self):
		return (self._active_filter_name,self._active_filter_index) 
		
	def rename_filter(self, old_name, new_name):
		names = [m[F_NAME] for m in self._filters]
		index = names.index(old_name)
		self._filters[index][F_NAME] = new_name
		self._filters[index][F_DISPLAY] = new_name
		
	def select_feed(self, feed_id):
		#if we have a tag, pick the first one (really used just when adding
		#feeds)
		tags = self._db.get_tags_for_feed(feed_id)
		if len(tags) > 0:
			self.set_active_filter(self.get_filter_index(tags[0]))
		else:
			self.set_active_filter(FeedList.ALL)
		self.feed_list_view.set_selected(feed_id)
		self.feed_list_view.resize_columns()

	def update_disk_usage(self, size):
		if self._disk_usage_widget is None:
			return
		if utils.RUNNING_SUGAR:
			self._disk_usage_widget.set_markup('<span color="#FFFFFF">'+utils.format_size(size)+"</span>")
		else:
			self._disk_usage_widget.set_markup(utils.format_size(size))

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
		
	def download_finished(self): #FIXME: convert to gobject signal one day
		self._download_view.update_downloads()
		
	def _update_notebook_tabs(self, number):
		if number == 0:
			self._notebook.hide_page(N_DOWNLOADS)
		else:
			self._downloads_label.set_markup(_('<span size="small">Downloads (%d)</span>') % number)
			self._notebook.show_page(N_DOWNLOADS)
				
	def desensitize(self):
		if self.app_window:
			self.app_window.set_sensitive(False)
		else:
			self._layout_container.set_sensitive(False)
		while gtk.events_pending(): #make sure the sensitivity change goes through
			gtk.main_iteration()
			
class NotebookManager(gtk.Notebook):
	"""manages showing and hiding of tabs.  Also, hides the whole tab bar if only one 
	tab open, and selects a different tab if the one we are closing is selected"""
	def __init__(self):
		gtk.Notebook.__init__(self)
		self._pages_showing = {}
		self._default_page = 0
		
	def append_page(self, widget, label):
		self._pages_showing[len(self._pages_showing)] = False
		gtk.Notebook.append_page(self, widget, label)
	
	def show_page(self, n):
		if not self._pages_showing.has_key(n): return
		if self._pages_showing[n] == True: return
		self._pages_showing[n] = True
		self.get_nth_page(n).show_all()
		showing_count = 0
		for key in self._pages_showing.keys():
			if self._pages_showing[key]:
				showing_count+=1
		if showing_count > 1:
			self.set_show_tabs(True)
					
	def hide_page(self, n):
		if not self._pages_showing.has_key(n): return
		if self._pages_showing[n] == False: return
		self._pages_showing[n] = False
		self.get_nth_page(n).hide()
		showing_count = 0
		for key in self._pages_showing.keys():
			if self._pages_showing[key]:
				showing_count+=1
		if showing_count == 1:
			for key in self._pages_showing.keys():
				if self._pages_showing[key]:
					self.set_current_page(key)
					self.set_show_tabs(False)
		if self.get_current_page() == n:
			self.set_current_page(self._default_page)
					
	def show_only(self, n):
		if not self._pages_showing.has_key(n): return
		self._default_page = n
		for i in range(0,self.get_n_pages()):
			self._pages_showing[i] = i==n
			if i == n:
				self.get_nth_page(i).show_all()
			else:
				self.get_nth_page(i).hide_all()
		self.set_current_page(n)
		self.set_show_tabs(False)
					
class ShouldntHappenError(Exception):
	def __init__(self,error):
		self.error = error
	def __str__(self):
		return self.error
