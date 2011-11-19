#PlanetView.  Actually uses AJAX on an internal server to update progress 
#and media info.  Stupid, or clever?  You be the judge!
#suggestions for security holes?  The only problem I see is that someone else can see the 
#progress of our downloads, and prevent those UI updates from making it to the screen
#OH NOES!


import logging
import os, os.path

import gobject
import gtk

import html.PTVhtml
import EntryFormatter
import ptvDB
import utils

if utils.RUNNING_HILDON:
	import hildon
elif utils.RUNNING_SUGAR:
	import hulahop

if utils.RUNNING_HILDON:
	ENTRIES_PER_PAGE = 5
else:
	ENTRIES_PER_PAGE = 10

#states
S_DEFAULT=0
S_SEARCH=1

class PlanetView(gobject.GObject):
	"""PlanetView implementes the api for entrylist and entryview, so that the main program doesn't
	need to know that the two objects are actually the same"""
	
	PORT = 8000
	
	__gsignals__ = {
	   	'link-activated': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_PYOBJECT])),
		'entries-viewed': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_PYOBJECT])),
		#
		#unused by planetview, but part of entrylist API
		#
		'entry-selected': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   ([gobject.TYPE_INT, gobject.TYPE_INT])),
		'no-entry-selected': (gobject.SIGNAL_RUN_FIRST, 
						   gobject.TYPE_NONE, 
						   [])
	}	                       
	
	def __init__(self, dock_widget, main_window, db, share_path, feed_list_view=None, app=None, renderer=EntryFormatter.WEBKIT):
		gobject.GObject.__init__(self)
		#public
		self.presently_selecting = False
		
		#protected
		self._app = app
		if self._app is not None:
			self._mm = self._app.mediamanager
		else:
			self._mm = None
		
		self._main_window = main_window
		self._db = db
		self._renderer = renderer
		#self._renderer = EntryFormatter.GTKHTML
		self._current_feed_id = -1
		self._feed_title=""
		self._state = S_DEFAULT
		self._auth_info = (-1, "","") #user:pass, url
		self._custom_message = ""
		self._last_link = ""
		self._current_link = None
		self._search_query = None
		self._filter_feed = None
		self._hide_viewed = False
		self._ignore_next_event = False
		self._USING_AJAX = False
		
		self._entrylist = []
		self._entry_store = {}
		self._convert_newlines = False
		
		self._first_entry = 0 #first entry visible
		
		self._html_dock = dock_widget
		self._scrolled_window = gtk.ScrolledWindow()
		if utils.RUNNING_HILDON:
			hildon.hildon_helper_set_thumb_scrollbar(self._scrolled_window, True)
		self._html_dock.add(self._scrolled_window)
		self._scrolled_window.set_property("hscrollbar-policy",gtk.POLICY_AUTOMATIC)
		self._scrolled_window.set_property("vscrollbar-policy",gtk.POLICY_AUTOMATIC)
		self._scrolled_window.set_flags(self._scrolled_window.flags() & gtk.CAN_FOCUS) 
		if self._renderer == EntryFormatter.WEBKIT:
			self._scrolled_window.set_shadow_type(gtk.SHADOW_IN)

		style = self._html_dock.get_style().copy()
		self._background_color = "#%.2x%.2x%.2x;" % (
				style.base[gtk.STATE_NORMAL].red / 256,
				style.base[gtk.STATE_NORMAL].blue / 256,
				style.base[gtk.STATE_NORMAL].green / 256)
				
		self._foreground_color = "#%.2x%.2x%.2x;" % (
				style.text[gtk.STATE_NORMAL].red / 256,
				style.text[gtk.STATE_NORMAL].blue / 256,
				style.text[gtk.STATE_NORMAL].green / 256)
				
		self._insensitive_color = "#%.2x%.2x%.2x;" % (
				style.base[gtk.STATE_INSENSITIVE].red / 256,
				style.base[gtk.STATE_INSENSITIVE].blue / 256,
				style.base[gtk.STATE_INSENSITIVE].green / 256)
		
		
		if self._renderer == EntryFormatter.WEBKIT:
			import html.PTVWebkit
			self._html_widget = html.PTVWebkit.PTVWebkit(self, self._db.home, share_path)
		elif self._renderer == EntryFormatter.MOZILLA:
			import html.PTVMozilla
			self._html_widget = html.PTVMozilla.PTVMozilla(self, self._db.home, share_path)
		elif self._renderer == EntryFormatter.GTKHTML:
			import html.PTVGtkHtml
			self._html_widget = html.PTVGtkHtml.PTVGtkHtml(self, self._db.home, share_path)
				
		#signals
		self._handlers = []
		if feed_list_view is not None:
			h_id = feed_list_view.connect('feed-selected', self.__feedlist_feed_selected_cb)
			self._handlers.append((feed_list_view.disconnect, h_id))
			h_id = feed_list_view.connect('search-feed-selected', self.__feedlist_search_feed_selected_cb)
			self._handlers.append((feed_list_view.disconnect, h_id))
			h_id = feed_list_view.connect('no-feed-selected', self.__feedlist_none_selected_cb)
			self._handlers.append((feed_list_view.disconnect, h_id))
		if self._app is not None:
			h_id = self._app.connect('feed-added',self.__feed_added_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('feed-removed', self.__feed_removed_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('feed-polled', self.__feed_polled_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('feed-name-changed', self.__feed_name_changed_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('entry-updated', self.__entry_updated_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('render-ops-updated', self.__render_ops_updated_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('state-changed', self.__state_changed_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('entries-viewed', self.__entries_updated_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('entries-unviewed', self.__entries_updated_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = app.connect('new-database', self.__new_database_cb)
			self._handlers.append((app.disconnect, h_id))
		screen = gtk.gdk.screen_get_default()
		h_id = screen.connect('size-changed', self.__size_changed_cb)
		self._handlers.append((screen.disconnect, h_id))
		
	def post_show_init(self):
		self._html_widget.post_show_init(self._scrolled_window)
		self._html_widget.connect('link-message', self.__link_message_cb)
		self._html_widget.connect('open-uri', self.__open_uri_cb)
		self._USING_AJAX = self._html_widget.is_ajax_ok()
		
		if self._USING_AJAX:
			logging.info("initializing ajax server")
			import threading
			from ajax import EntryInfoServer, MyTCPServer
			
			store_location = os.path.join(self._db.get_setting(ptvDB.STRING, '/apps/penguintv/media_storage_location', ""), os.path.join(utils.get_home(), "media", "images"))

			while True:
				try:
					if PlanetView.PORT == 8050:
						break
					self._update_server = MyTCPServer.MyTCPServer(('', PlanetView.PORT), EntryInfoServer.EntryInfoServer, store_location)
					break
				except:
					PlanetView.PORT += 1
			if PlanetView.PORT==8050:
				logging.warning("tried a lot of ports without success.  Problem?")
			t = threading.Thread(None, self._update_server.serve_forever, name="PTV AJAX Server Thread")
			t.setDaemon(True)
			t.start()
			self._ajax_url = "http://localhost:"+str(PlanetView.PORT)+"/"+self._update_server.get_key()
			self._entry_formatter = EntryFormatter.EntryFormatter(self._mm, False, True, ajax_url=self._ajax_url, renderer=self._renderer)
			self._search_formatter = EntryFormatter.EntryFormatter(self._mm, True, True, ajax_url=self._ajax_url, renderer=self._renderer)
		else:
			logging.info("not using ajax")
			self._ajax_url = None
			self._entry_formatter = EntryFormatter.EntryFormatter(self._mm, False, True, basic_progress=True, renderer=self._renderer)
			self._search_formatter = EntryFormatter.EntryFormatter(self._mm, True, True, basic_progress=True, renderer=self._renderer)
		self.display_item()
		self._html_dock.show_all()

		
	def set_entry_view(self, entry_view):
		pass
		
	def __feedlist_feed_selected_cb(self, o, feed_id):
		self.populate_entries(feed_id)

	def __feedlist_search_feed_selected_cb(self, o, feed_id):
		self._filter_feed = feed_id
		self._current_feed_id = feed_id
		self._first_entry = 0
		self._render_entries()
		
	def __feedlist_none_selected_cb(self, o):
		if self._state == S_SEARCH:
			self._filter_feed = None
			self._current_feed_id = -1
			self._render_entries()
		else:
			self.clear_entries()
		
	def __feed_added_cb(self, app, feed_id, success):
		if success:
			self.populate_entries(feed_id)
			
	def __feed_polled_cb(self, app, feed_id, update_data):
		#don't do anything if polled, we will be told to redraw if necessary
		if self._state == S_SEARCH:
			return
		f_list = self._db.get_associated_feeds(feed_id)
		if self._current_feed_id in f_list:
			self.populate_entries(feed_id)
			if update_data['pollfail']:
				self.display_custom_entry("<b>"+_("There was an error trying to poll this feed.")+"</b>")
			else:
				self.undisplay_custom_entry()
			
	def __feed_removed_cb(self, app, feed_id):
		self.clear_entries()
		
	def __feed_name_changed_cb(self, app, feed_id, oldname, name):
		if self._current_feed_id == feed_id:
			self._entry_store = {}
			self.populate_entries(feed_id)
		
	def __entry_updated_cb(self, app, entry_id, feed_id):
		self.update_entry_list(entry_id)
		f_list = self._db.get_associated_feeds(feed_id)
		if self._current_feed_id in f_list and not self._USING_AJAX:
			self._render_entries(mark_read=False, force=True)
			
	def __entries_updated_cb(self, app, viewlist):
		for feed_id, idlist in viewlist:
			f_list = self._db.get_associated_feeds(feed_id)
			if self._current_feed_id in f_list:
				self.populate_entries(feed_id)
			
	def __render_ops_updated_cb(self, app):
		self._convert_newlines = self._db.get_flags_for_feed(self._current_feed_id) & ptvDB.FF_ADDNEWLINES == ptvDB.FF_ADDNEWLINES
		self._entry_store = {}
		self._render_entries(force=True)		
			
	def __size_changed_cb(self, screen):
		"""Redraw after xrandr calls"""
		self._render_entries()
		
	def __new_database_cb(self, app, db):
		self._db = db
		
	def __link_message_cb(self, o, message):
		if len(message) > 0:
			#current_link might be blank when they actually click on the 
			#menu item, so save the last link
			self._current_link = message
			self._last_link = message
		else:
			self._current_link = None
			
		if not utils.RUNNING_HILDON:
			self._main_window.display_status_message(message)
	
	def __open_uri_cb(self, o, uri):
		self._link_clicked(uri)
		
	#def grab_focus(self):
	#	if utils.RUNNING_SUGAR:
	#		self._moz.grab_focus()
		
	#entrylist functions
	def get_selected(self):
		# just return the top one
		if len(self._entrylist) > 0:
			return self._entrylist[0][0]
		return None
		
	def get_selected_id(self):
		val = self.get_selected()
		if val is None:
			return 0
		return val
				
	def set_selected(self, entry_id):
		pass
		
	def get_current_feed_id(self):
		return self._current_feed_id
		
	def get_display_id(self):
		return (self._current_feed_id, self._first_entry)
		
	def get_bg_color(self):
		return self._background_color
		
	def get_fg_color(self):
		return self._foreground_color
		
	def get_in_color(self):
		return self._insensitive_color
		
	def populate_if_selected(self, feed_id):
		if feed_id == self._current_feed_id:
			self.populate_entries(feed_id)
		
	def populate_entries(self, feed_id=None, selected=-1):
		"""selected is unused in planet mode"""
		if feed_id is None:
			feed_id = self._current_feed_id
			
		if feed_id==-1:
			self.clear_entries()
			return
			
		try:
			db_entrylist = self._db.get_entrylist(feed_id)
		except ptvDB.NoEntry, e:
			loggin.warning("error displaying search")
			self._render(_("There was an error displaying the search results.  Please reindex searches and try again"))
			return

		new_feed = False
		if feed_id != self._current_feed_id:
			new_feed = True
			#self._hide_viewed = False
			#self._main_window.set_hide_entries_menuitem(self._hide_viewed)
			#self._main_window.set_hide_entries_visibility(True)
			self._current_feed_id = feed_id
			self._first_entry = 0
			self._html_widget.dl_interrupt()
			self._entry_store={}
			feed_info = self._db.get_feed_info(feed_id)
			if feed_info['auth_feed']:
				self._auth_info = (feed_id,feed_info['auth_userpass'], feed_info['auth_domain'])
			else:
				self._auth_info = (-1, "","")
			if self._USING_AJAX:
				self._update_server.clear_updates()
		#always update title in case it changed... it's a cheap lookup
		self._feed_title = self._db.get_feed_title(feed_id)
		self._entrylist = []
		for e in db_entrylist:
			self._entrylist.append((e[0], feed_id))
			
		self._convert_newlines = self._db.get_flags_for_feed(feed_id) & ptvDB.FF_ADDNEWLINES == ptvDB.FF_ADDNEWLINES
			
		self._render_entries(mark_read=new_feed, force=True)
		
	def auto_pane(self):
		pass
		
	def update_entry_list(self, entry_id=None):
		if entry_id is None:
			self._entry_store = {}
			self.populate_entries()
		else:
			for e,f in self._entrylist:
				if e == entry_id:
					try:
						self._load_entry(entry_id, True)
					except ptvDB.NoEntry:
						return
					return
			
	def mark_as_viewed(self, entry_id=None):
		logging.error("doesn't apply in planet view, right?")
	
	def show_search_results(self, entries, query):
		if entries is None:
			self.display_custom_entry(_("No entries match those search criteria"))
			
		self._entrylist = [(e[0],e[3]) for e in entries]
		self._convert_newlines = False
		self._current_feed_id = -1
		self._hide_viewed = False
		self._main_window.set_hide_entries_menuitem(self._hide_viewed)
		self._main_window.set_hide_entries_visibility(False)
		query = query.replace("*","")
		self._search_query = query
		try:
			self._render_entries()
		except ptvDB.NoEntry:
			logging.warning("error displaying search")
			self._render(_("There was an error displaying the search results.  Please reindex searches and try again"))
		
	def unshow_search(self):
		self._render("<html><body></body></html")
		
	#def highlight_results(self, feed_id):
	#	"""doesn't apply in planet mode"""
	#	pass
		
	def clear_entries(self):
		self._current_feed_id = -1
		self._first_entry = 0
		self._entry_store={}
		self._entrylist = []
		self._convert_newlines = False
		self._html_widget.dl_interrupt()
		self._render("<html><body></body></html")
		if self._USING_AJAX:
			self._update_server.clear_updates()
		
	def _unset_state(self):
		if self._state == S_SEARCH:
			self._search_query = None
			self._filter_feed = None
		self.clear_entries()
	
	def __state_changed_cb(self, app, newstate, data=None):
		import penguintv
		d = {penguintv.DEFAULT: S_DEFAULT,
			 penguintv.MANUAL_SEARCH: S_SEARCH,
			 penguintv.TAG_SEARCH: S_SEARCH,
			 #penguintv.ACTIVE_DOWNLOADS: S_DEFAULT,
			 penguintv.MAJOR_DB_OPERATION: S_DEFAULT}
			 
		newstate = d[newstate]
		
		if newstate == self._state:
			return
		
		self._unset_state()
		self._state = newstate

	#entryview functions
	def progress_update(self, entry_id, feed_id):
		if self._USING_AJAX:
			self.update_if_selected(entry_id, feed_id)
	
	def update_if_selected(self, entry_id=None, feed_id=None):
		self.update_entry_list(entry_id)
		
	def display_custom_entry(self, message):
		if self._custom_message == message:
			return
		self._custom_message = message
		
	def undisplay_custom_entry(self):
		if self._custom_message == "":
			return
		self._custom_message = ""
		
	def display_item(self, item=None, highlight=""):
		if item is None:
			self._render("<html><body></body></html")
		else:
			pass
	
	def finalize(self):
		pass
		
	def finish(self):
		for disconnector, h_id in self._handlers:
			disconnector(h_id)
		if self._USING_AJAX:
			import urllib
			self._update_server.finish()
			try:
				urllib.urlopen("http://localhost:"+str(PlanetView.PORT)+"/") #pings the server, gets it to quit
			except:
				logging.error('error closing planetview server')
		self._render("<html><body></body></html")
		self._html_widget.finish()
					
	#protected functions
	def _render_entries(self, mark_read=False, force=False):
		"""Takes a block on entry_ids and throws up a page."""

		if self._first_entry < 0:
			self._first_entry = 0
			self._html_widget.dl_interrupt()
			
		if self._filter_feed is not None:
			assert self._state == S_SEARCH
			entrylist = [r for r in self._entrylist if r[1] == self._filter_feed]
		else:
			entrylist = self._entrylist
			if self._hide_viewed:
				newlist = []
				#kept = self._db.get_kept_entries(self._current_feed_id)
				unviewed = self._db.get_unread_entries(self._current_feed_id)
				for e,f in entrylist:
					if e in unviewed:
						newlist.append((e,f))
				entrylist = newlist
			
		if len(entrylist)-self._first_entry >= ENTRIES_PER_PAGE:
			self._last_entry = self._first_entry+ENTRIES_PER_PAGE
		else:
			self._last_entry = len(entrylist)
			
		media_exists = False
		entries = []
		html = ""
		#unreads = []
		
		#preload the block of entries, which is nicer to the db
		self._load_entry_block(entrylist[self._first_entry:self._last_entry], mark_read=mark_read, force=force)

		i=self._first_entry-1
		for entry_id, feed_id in entrylist[self._first_entry:self._last_entry]:
			i+=1
			try:
				entry_html, item = self._load_entry(entry_id)
			except ptvDB.NoEntry:
				continue
			if item.has_key('media'):
				media_exists = True
			#else:
			#	if item.has_key('new'):
			#		if item['new'] and not item['keep']:
			#			unreads.append(entry_id)
			if self._search_query is not None:
				entry_html = entry_html.encode('utf-8')
				try:
					p = EntryFormatter.HTMLHighlightParser(self._search_query)
					p.feed(entry_html)
					entry_html = p.new_data
				except:
					pass	
					
			if self._auth_info[0] != -1:
				p = EntryFormatter.HTMLImgAuthParser(self._auth_info[2], self._auth_info[1])
				p.feed(entry_html)
				entry_html = p.new_data
			
			if self._USING_AJAX:
				entries.append('\n\n<span id="%i">' % (entry_id,))
			entries.append(entry_html)
			if self._USING_AJAX:
				entries.append('</span>\n\n')
			
		gobject.timeout_add(2000, self._do_delayed_set_viewed, self._current_feed_id, self._first_entry, self._last_entry)
			
		#######build HTML#######	
		#cb_status = self._hide_viewed and "CHECKED" or "UNCHECKED"
		#cb_function = self._hide_viewed and "hideviewed:0" or "hideviewed:1"
		
		html = []
		html.append(self._build_header(media_exists))
		if self._USING_AJAX:
			html.append("""<span id="errorMsg"><br></span>\n""")
		
		html.append(self._custom_message+"<br>")
		
		if utils.RUNNING_HILDON:
			html.append('<a href="pane:back"><img border="0" src="file://%s"/>%s</a>' % (
					"/usr/share/icons/hicolor/26x26/hildon/qgn_list_hw_button_esc.png",
					_("Back to Feeds")))
					
		html.append("""<div id="nav_bar"><table
					style="width: 100%; text-align: left; margin-left: auto; margin-right: auto;"
 					border="0" cellpadding="2" cellspacing="0">
					<tbody>
					<tr><td>""")
		if self._first_entry > 0:
			html.append(_('<a href="planet:up">Newer Entries</a>'))
		
		html.append('</td><td style="text-align: right;">')
		if self._last_entry < len(entrylist):
			html.append(_('<a href="planet:down">Older Entries</a>'))
			
		html.append("</td></tr></tbody></table></div>")
		
		if self._state != S_SEARCH:
			html.append('<div class="feedtitle">'+self._feed_title+"</div>")
		html += entries
			
		html.append("""<div id="nav_bar"><table
					style="width: 100%; text-align: left; margin-left: auto; margin-right: auto;"
					border="0" cellpadding="2" cellspacing="0">
					<tbody>
					<tr><td>""")
		if self._first_entry > 0:
			html.append(_('<a href="planet:up">Newer Entries</a>'))
		html.append('</td><td style="text-align: right;">')
		if self._last_entry < len(entrylist):
			html.append(_('<a href="planet:down">Older Entries</a>'))
		html.append("</td></tr></tbody></table></div>")
		
		if utils.RUNNING_HILDON:
			html.append('<a href="pane:back"><img border="0" src="file://%s"/>%s</a>' % (
					"/usr/share/icons/hicolor/26x26/hildon/qgn_list_hw_button_esc.png",
					_("Back to Feeds")))
		
		html.append("</body></html>")
		
		html = "".join(html)
		self._render(html)
	
	def _build_header(self, media_exists):
		html = []
			
		if self._USING_AJAX:
			html.append("""<script type="text/javascript"><!--""")
			html.append("""
		
			var xmlHttp=GetXmlHttpObject()
			
			function log(msg) {
				window.status=msg
				/*setTimeout(function() {
					throw new Error(msg);
				}, 0);*/
			}


			function refresh_entries(timed)
			{
				if (xmlHttp==null)
				{
					alert ("Browser does not support HTTP Request")
					return
				}
				//log("current status... " +xmlHttp.readyState);
				xmlHttp.onreadystatechange=stateChanged
				try
				{
					//log("pulling update http://localhost:"""+str(PlanetView.PORT)+"/"+self._update_server.get_key()+"""/update")
					//log("uri "+ document.baseURI)
					xmlHttp.open("GET","http://localhost:"""+str(PlanetView.PORT)+"/"+self._update_server.get_key()+"""/update",true)
					//xmlHttp.setRequestHeader("Access-Control-Allow-Origin", "*")
					xmlHttp.send(null)
				} 
				catch (error) 
				{
					log("ERROR")
					document.getElementById("errorMsg").innerHTML="Permissions problem loading ajax"
				}
				if (timed == 1)
				{
					SetTimer()
				}
			} 

			function stateChanged(e) 
			{ 
				if (e.target.readyState==4 || e.target.readyState=="complete")
				{ 
					if (e.target.responseText.length > 0)
					{
						line_split = e.target.responseText.split(" ")
						entry_id = line_split[0]
						split_point = e.target.responseText.indexOf(" ")
						document.getElementById(entry_id).innerHTML=e.target.responseText.substring(split_point)
					}
				} 
			} 

			function GetXmlHttpObject()
			{ 
				var objXMLHttp=null
				if (window.XMLHttpRequest)
				{
					objXMLHttp=new XMLHttpRequest()
				}
				else if (window.ActiveXObject)
				{
					objXMLHttp=new ActiveXObject("Microsoft.XMLHTTP")
				}
				return objXMLHttp
			} 
		
			var timerObj;
			function SetTimer()
			{
  				timerObj = setTimeout("refresh_entries(1)",1000);
			}
			refresh_entries(1)""")
			html.append("--> </script>")
	
		html = "\n".join(html)
		header = self._html_widget.build_header(html)

		return header
		
	def _load_entry_block(self, entry_list, mark_read=False, force=False):
		#if not forcing, load what we can from cache
		entries = []
		if not force:
			l = [row for row in entry_list if self._entry_store.has_key(row[0])]
			for row in l:
				entries.append(self._entry_store[row[0]][1])
				entry_list.remove(row)
		
		#load the rest from db
		if len(entry_list) > 0:
			e_id_list = [r[0] for r in entry_list]
			db_entries = self._db.get_entry_block(e_id_list, self._ajax_url)
			media = self._db.get_entry_media_block(e_id_list)
		
			for item in db_entries:
				if media.has_key(item['entry_id']):
					item['media'] = media[item['entry_id']]
				else:
					item['media'] = []

				item['new'] = not item['read']
				if mark_read and not item.has_key('media'):
					item['read'] = True
				
				if self._state == S_SEARCH:
					item['feed_title'] = self._db.get_feed_title(item['feed_id'])
					self._entry_store[item['entry_id']] = (self._search_formatter.htmlify_item(item, self._convert_newlines),item)
				else:
					self._entry_store[item['entry_id']] = (self._entry_formatter.htmlify_item(item, self._convert_newlines),item)
					
		#only reformat if read status changes
		for item in entries:
			item['new'] = not item['read']
			if mark_read and not item.has_key('media'):
				item['read'] = True
				if self._state == S_SEARCH:
					item['feed_title'] = self._db.get_feed_title(item['feed_id'])
					self._entry_store[item['entry_id']] = (self._search_formatter.htmlify_item(item, self._convert_newlines),item)
				else:
					self._entry_store[item['entry_id']] = (self._entry_formatter.htmlify_item(item, self._convert_newlines),item)
				
	def _load_entry(self, entry_id, force=False):
		if self._entry_store.has_key(entry_id) and not force:
			return self._entry_store[entry_id]
		
		item = self._db.get_entry(entry_id, self._ajax_url)
		media = self._db.get_entry_media(entry_id)
		if media:
			item['media']=media
		else:
			item['media'] = []
		item['new'] = not item['read']
		
		if self._state == S_SEARCH:
			item['feed_title'] = self._db.get_feed_title(item['feed_id'])
			new_format = self._search_formatter.htmlify_item(item, self._convert_newlines)
			if self._entry_store.has_key(entry_id):
				if new_format == self._entry_store[entry_id][0]:
					self._entry_store[entry_id] = (new_format, item)
					return self._entry_store[entry_id]
			self._entry_store[entry_id] = (new_format, item)
		else:
			new_format = self._entry_formatter.htmlify_item(item, self._convert_newlines)
			if self._entry_store.has_key(entry_id):
				if new_format == self._entry_store[entry_id][0]:
					#if the new formatting is the same as the old, don't do anything different
					self._entry_store[entry_id] = (new_format, item)
					return self._entry_store[entry_id]
			self._entry_store[entry_id] = (new_format, item)
		try:
			index = self._entrylist.index((entry_id,self._current_feed_id))
		except:
			logging.warning("Told to update an entry we don't have -- can't update")
			return self._entry_store[entry_id]
			
		if index >= self._first_entry and index <= self._first_entry+ENTRIES_PER_PAGE:
			entry = self._entry_store[entry_id][1]
			#if self._renderer == EntryFormatter.WEBKIT:
			#	self._html_widget.rewrite(entry_id, self._entry_store[entry_id][0])
			if self._USING_AJAX:
				ret = []
				ret.append(str(entry_id)+" ")
				ret.append(self._entry_store[entry_id][0])
				ret = "".join(ret)
				self._update_server.push_update(ret)
			else:
				self._render_entries()
			gobject.timeout_add(2000, self._do_delayed_set_viewed, self._current_feed_id, self._first_entry, self._last_entry, True)
		
		return self._entry_store[entry_id]
		
	def _update_entry(self, entry_id, item, show_change):
		if self._state == S_SEARCH:
			self._entry_store[entry_id] = (self._search_formatter.htmlify_item(item, self._convert_newlines),item)
		else:
			self._entry_store[entry_id] = (self._entry_formatter.htmlify_item(item, self._convert_newlines),item)
		i=0			
		for e,f in self._entrylist:
			if e == entry_id:
				index = i
			i += 1
		if not show_change:
			return
		if index >= self._first_entry and index <= self._first_entry+ENTRIES_PER_PAGE:
			#if self._renderer == EntryFormatter.WEBKIT:
			#	self._html_widget.rewrite(entry_id, self._entry_store[entry_id][0])
			if self._USING_AJAX:
				ret = []
				ret.append(str(entry_id)+" ")
				ret.append(self._entry_store[entry_id][0])
				ret = "".join(ret)
				self._update_server.push_update(ret)
	
	def _render(self, html):
		image_id = None
		if self._renderer == EntryFormatter.GTKHTML:
			image_id = self.get_display_id()
		
		#if self._renderer == EntryFormatter.WEBKIT:
		#	self._update_server.push_update(html)
		#	self._html_widget.load_update(self._ajax_url)
		#else:
		self._html_widget.render(html, self._ajax_url, image_id)
		
	def _do_delayed_set_viewed(self, feed_id, first_entry, last_entry, show_change=False):
		if (feed_id, first_entry, last_entry) != \
		   (self._current_feed_id, self._first_entry, self._last_entry):
			return False
			
		keepers = []
		
		if self._filter_feed is not None:
			assert self._state == S_SEARCH
			entrylist = [r for r in self._entrylist if r[1] == self._filter_feed]
		else:
			entrylist = self._entrylist

		self._load_entry_block(entrylist[self._first_entry:self._last_entry])
		for entry_id, f in entrylist[self._first_entry:self._last_entry]:
			item = self._entry_store[entry_id][1]
			if not item['read'] and not item['keep'] and len(item['media']) == 0:
				keepers.append(item)
		
		for item in keepers:
			item['read'] = True
			item['new'] = False
			self._update_entry(item['entry_id'], item, show_change)
				
		if len(keepers) > 0:
			if self._state == S_SEARCH:
				return False
			#	if feed_id == -1:
			#		for item in keepers:
			#			self.emit('entries-viewed', [(item['feed_id'], [item['entry_id']])])
			#		return False
			self.emit('entries-viewed', [(feed_id, [e['entry_id'] for e in keepers])])
		return False

	def _do_context_menu(self, entry_id):
		"""pops up a context menu for the designated item"""
		
		# When we right click on an item, we also get an event for the whole
		# document, so ignore that one.
		
		if entry_id == 0:
			if self._ignore_next_event:
				self._ignore_next_event = False
				return
		else:
			self._ignore_next_event = True
		
		menu = gtk.Menu()
		
		if entry_id == 0 and self._state == S_SEARCH:
			return
			
		if self._current_link is not None:
			if self._current_link.startswith("http"):
				#if we're on a link, override everything else
				item = gtk.MenuItem(_("_Open Link in Browser..."))
				item.connect('activate', lambda e: self._app.activate_link(self._last_link))
				menu.append(item)
				item = gtk.MenuItem(_("_Copy Link Location"))
				item.connect('activate', lambda e: self._set_clipboard_text(self._last_link))
				menu.append(item)
				menu.show_all()
				menu.popup(None,None,None, 3, 0)
				return
		
		if entry_id > 0:
			try:
				entry = self._load_entry(entry_id)[1]
			except ptvDB.NoEntry:
				return
				
			item = gtk.MenuItem(_("_Open Entry in Browser..."))
			item.connect('activate', lambda e: self._app.activate_link(entry['link']))
			menu.append(item)
			
			item = gtk.MenuItem(_("_Copy Entry URL"))
			item.connect('activate', lambda e: self._set_clipboard_text(entry['link']))
			menu.append(item)
			
			#separator = gtk.SeparatorMenuItem()
			#menu.append(separator)
				
			entry['flag'] = self._db.get_entry_flag(entry_id)
			
			if entry['flag'] & ptvDB.F_MEDIA:
				if entry['flag'] & ptvDB.F_DOWNLOADED == 0:
					item = gtk.ImageMenuItem(_("_Download"))
					img = gtk.image_new_from_stock('gtk-go-down',gtk.ICON_SIZE_MENU)
					item.set_image(img)
					item.connect('activate', lambda e,i: self._app.download_entry(i), entry_id)
					menu.append(item)
				else:
					item = gtk.ImageMenuItem(_("_Re-Download"))
					img = gtk.image_new_from_stock('gtk-go-down',gtk.ICON_SIZE_MENU)
					item.set_image(img)
					item.connect('activate', lambda e,i: self._app.download_entry(i), entry_id)
					menu.append(item)

					item = gtk.ImageMenuItem('gtk-media-play')
					item.connect('activate', lambda e,i: self._app.play_entry(i), entry_id)
					menu.append(item)
				
					item = gtk.MenuItem(_("Delete"))
					item.connect('activate', lambda e,i: self._app.delete_entry_media(i), entry_id)
					menu.append(item)
					
				if entry['flag'] & ptvDB.F_UNVIEWED:
					item = gtk.MenuItem(_("Mark As _Viewed"))
					item.connect('activate', lambda e,i: self._app.mark_entry_as_viewed(i), entry_id)
					menu.append(item)
				else:
					item = gtk.MenuItem(_("Mark As _Unviewed"))
					item.connect('activate', lambda e,i: self._app.mark_entry_as_unviewed(i), entry_id)
					menu.append(item)
			
			keep = self._db.get_entry_keep(entry['entry_id'])
			if keep:
				item = gtk.MenuItem(_("_Don't Keep New"))
				item.connect('activate', lambda e,i: self._app.activate_link("unkeep:%i" % (i,)), entry_id)
				menu.append(item)
			else:
				item = gtk.MenuItem(_("_Keep New"))
				item.connect('activate', lambda e,i: self._app.activate_link("keep:%i" % (i,)), entry_id)
				menu.append(item)
			
			if self._state != S_SEARCH:
				separator = gtk.SeparatorMenuItem()
				menu.append(separator)
				
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
		menu.popup(None,None,None, 3, 0)
		
	def _set_clipboard_text(self, text):
		clipboard = gtk.clipboard_get(selection="CLIPBOARD")
		clipboard.set_text(text)
		
	def _link_clicked(self, link):
		if link == "planet:up":
			self._do_planet_up()
		elif link == "planet:down":
			self._do_planet_down()
		elif link == "pane:back":
			self._do_pane_back()
		elif link.startswith("rightclick"):
			self._do_context_menu(int(link.split(':')[1]))
		else:
			self.emit('link-activated', link)

	def _do_pane_back(self, a=None):
		self._main_window.pane_to_feeds()
	
	def _do_planet_up(self, a=None):
		self._first_entry -= ENTRIES_PER_PAGE
		self._html_widget.dl_interrupt()
		self._render_entries(mark_read=True)
		
	def _do_planet_down(self, a=None):
		self._first_entry += ENTRIES_PER_PAGE
		self._html_widget.dl_interrupt()
		self._render_entries(mark_read=True)
		
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
		self._first_entry = 0
		self._render_entries()
