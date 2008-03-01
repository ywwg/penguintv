#PlanetView.  Actually uses AJAX on an internal server to update progress 
#and media info.  Stupid, or clever?  You be the judge!
#suggestions for security holes?  The only problem I see is that someone else can see the 
#progress of our downloads, and prevent those UI updates from making it to the screen
#OH NOES!


import logging
import os, os.path

import gobject
import gtk

import EntryFormatter
import ptvDB
import utils

if not utils.RUNNING_SUGAR:
	try:
		import gtkmozembed
	except:
		pass
else:
	import hulahop
	
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
	
	def __init__(self, dock_widget, main_window, db, glade_path, feed_list_view=None, app=None, renderer=EntryFormatter.MOZILLA):
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
		self._css = ""
		self._current_feed_id = -1
		self._moz_realized = False
		self._feed_title=""
		self._state = S_DEFAULT
		self._auth_info = (-1, "","") #user:pass, url
		self._custom_message = ""
		self._search_query = None
		self._filter_feed = None
		self._show_kept = False
		self._ignore_next_event = False
		
		self._entrylist = []
		self._entry_store = {}
		self._convert_newlines = False
		
		self._first_entry = 0 #first entry visible
		
		self._html_dock = dock_widget
		self._scrolled_window = gtk.ScrolledWindow()
		self._html_dock.add(self._scrolled_window)
		self._scrolled_window.set_property("hscrollbar-policy",gtk.POLICY_AUTOMATIC)
		self._scrolled_window.set_property("vscrollbar-policy",gtk.POLICY_AUTOMATIC)
		self._scrolled_window.set_flags(self._scrolled_window.flags() & gtk.CAN_FOCUS) 

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
		
		if self._renderer == EntryFormatter.MOZILLA:
			if utils.RUNNING_SUGAR:
				f = open(os.path.join(glade_path, "mozilla-planet-olpc.css"))
				for l in f.readlines(): self._css += l
				f.close()
			else:
				if utils.RUNNING_HILDON:
					f = open(os.path.join(glade_path, "mozilla-planet-hildon.css"))
				else:
					f = open(os.path.join(glade_path, "mozilla-planet.css"))
				for l in f.readlines(): self._css += l
				f.close()
				
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
			h_id = self._app.connect('entry-updated', self.__entry_updated_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('render-ops-updated', self.__render_ops_updated_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('state-changed', self.__state_changed_cb)
			self._handlers.append((self._app.disconnect, h_id))
			h_id = self._app.connect('entries-viewed', self.__entries_updated_cb)
		self._handlers.append((self._app.disconnect, h_id))
		screen = gtk.gdk.screen_get_default()
		h_id = screen.connect('size-changed', self.__size_changed_cb)
		self._handlers.append((screen.disconnect, h_id))
		
	def post_show_init(self):
		if self._renderer == EntryFormatter.MOZILLA:
			if utils.RUNNING_SUGAR:
				self._USING_AJAX = False
				hulahop.startup(os.path.join(self._db.home, 'gecko'))
				import OLPCBrowser
				self._moz = OLPCBrowser.Browser()
				self._moz.load_uri("about:blank")
				self._moz.connect("notify", self._hulahop_prop_changed)
			else:
				if utils.RUNNING_HILDON:
					logging.debug("Hildon: Not using ajax view")
					self._USING_AJAX = False
				else:
					self._USING_AJAX = True
				utils.init_gtkmozembed()
				gtkmozembed.set_profile_path(self._db.home, 'gecko')
				gtkmozembed.push_startup()
				self._moz = gtkmozembed.MozEmbed()
				self._moz.load_url("about:blank")
			
			#TEMP INDENT START	
				#hard:
				self._moz.connect("new-window", self._moz_new_window)
				#requires changes to hulahop to get at _chrome:
				self._moz.connect("link-message", self._moz_link_message)
				
			self._moz.connect("open-uri", self._moz_link_clicked)
			self._moz.connect("realize", self._moz_realize, True)
			self._moz.connect("unrealize", self._moz_realize, False)
			self._scrolled_window.add_with_viewport(self._moz)
			self._moz.show()
			if utils.HAS_GCONF:
				try:
					import gconf
				except:
					from gnome import gconf
				self._conf = gconf.client_get_default()
				self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_moz_font)
			self._reset_moz_font()
		self.display_item()
		self._html_dock.show_all()
		if self._USING_AJAX:
			logging.info("initializing ajax server")
			import threading
			from ajax import EntryInfoServer, MyTCPServer

			while True:
				try:
					if PlanetView.PORT == 8050:
						break
					self._update_server = MyTCPServer.MyTCPServer(('', PlanetView.PORT), EntryInfoServer.EntryInfoServer)
					break
				except:
					PlanetView.PORT += 1
			if PlanetView.PORT==8050:
				logging.warning("tried a lot of ports without success.  Problem?")
			t = threading.Thread(None, self._update_server.serve_forever, name="PTV AJAX Server Thread")
			t.setDaemon(True)
			t.start()
			img_url = "http://localhost:"+str(PlanetView.PORT)+"/"+self._update_server.get_key()
			self._entry_formatter = EntryFormatter.EntryFormatter(self._mm, False, True, ajax_url=img_url)
			self._search_formatter = EntryFormatter.EntryFormatter(self._mm, True, True, ajax_url=img_url)
		else:
			logging.info("not using ajax")
			img_url = None
			self._entry_formatter = EntryFormatter.EntryFormatter(self._mm, False, True, basic_progress=True)
			self._search_formatter = EntryFormatter.EntryFormatter(self._mm, True, True, basic_progress=True)
		
	def set_entry_view(self, entry_view):
		pass
		
	def __feedlist_feed_selected_cb(self, o, feed_id):
		self.populate_entries(feed_id)

	def __feedlist_search_feed_selected_cb(self, o, feed_id):
		self._filter_feed = feed_id
		self._current_feed_id = feed_id
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
		if feed_id == self._current_feed_id:
			self.populate_entries(feed_id)
			if update_data['pollfail']:
				self.display_custom_entry("<b>"+_("There was an error trying to poll this feed.")+"</b>")
			else:
				self.undisplay_custom_entry()
			
	def __feed_removed_cb(self, app, feed_id):
		self.clear_entries()
		
	def __entry_updated_cb(self, app, entry_id, feed_id):
		self.update_entry_list(entry_id)
		if feed_id == self._current_feed_id and not self._USING_AJAX:
			self._render_entries(mark_read=False, force=True)
			
	def __entries_updated_cb(self, app, viewlist):
		for feed_id, idlist in viewlist:
			if feed_id == self._current_feed_id:
				self.populate_entries(feed_id)
			
	def __render_ops_updated_cb(self, app):
		self._convert_newlines = self._db.get_flags_for_feed(self._current_feed_id) & ptvDB.FF_ADDNEWLINES == ptvDB.FF_ADDNEWLINES
		self._entry_store = {}
		self._render_entries()		
			
	def __size_changed_cb(self, screen):
		"""Redraw after xrandr calls"""
		self._render_entries()
		
	def grab_focus(self):
		if utils.RUNNING_SUGAR:
			self._moz.grab_focus()
		
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
			self._show_kept = False
			self._main_window.set_show_kept_menuitem(self._show_kept)
			self._main_window.set_show_kept_visibility(True)
			self._current_feed_id = feed_id
			self._first_entry = 0
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
					self._load_entry(entry_id, True)
					return
			
	def mark_as_viewed(self, entry_id=None):
		logging.error("doesn't apply in planet view, right?")
	
	def show_search_results(self, entries, query):
		if entries is None:
			self.display_custom_entry(_("No entries match those search criteria"))
			
		self._entrylist = [(e[0],e[3]) for e in entries]
		self._convert_newlines = False
		self._current_feed_id = -1
		self._show_kept = False
		self._main_window.set_show_kept_menuitem(self._show_kept)
		self._main_window.set_show_kept_visibility(False)
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
		if not utils.RUNNING_SUGAR and not utils.RUNNING_HILDON:
			gtkmozembed.pop_startup()
					
	#protected functions
	def _render_entries(self, mark_read=False, force=False):
		"""Takes a block on entry_ids and throws up a page."""

		if self._first_entry < 0:
			self._first_entry = 0
			
		if self._filter_feed is not None:
			assert self._state == S_SEARCH
			entrylist = [r for r in self._entrylist if r[1] == self._filter_feed]
		else:
			entrylist = self._entrylist
			if self._show_kept:
				newlist = []
				kept = self._db.get_kept_entries(self._current_feed_id)
				for e,f in entrylist:
					if e in kept:
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
			entry_html, item = self._load_entry(entry_id)
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
		cb_status = self._show_kept and "CHECKED" or "UNCHECKED"
		cb_function = self._show_kept and "showkept:0" or "showkept:1"
		
		html = []
		html.append(self._build_header(media_exists))
		
		html.append(self._custom_message)
		
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
			html.append('<div class="feed_title">'+self._feed_title+"</div>")
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
		html.append("</body></html>")
		
		html = "".join(html)
		self._render(html)
	
	def _build_header(self, media_exists):
		if self._renderer == EntryFormatter.MOZILLA:
			html = ["""<html><head>
				    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
					<style type="text/css">
				    body { background-color: %s; color: %s; font-family: %s; font-size: %s; }
				    %s
				    </style>
				    <title>title</title>""" % (self._background_color,
											   self._foreground_color,
											   self._moz_font, 
											   self._moz_size, 
											   self._css)] 
			html.append("""<script type="text/javascript"><!--""")
			if self._USING_AJAX:
				html.append("""
	            
	            var xmlHttp

				function refresh_entries(timed)
				{
					xmlHttp=GetXmlHttpObject()
					if (xmlHttp==null)
					{
						alert ("Browser does not support HTTP Request")
						return
					}        
					xmlHttp.onreadystatechange=stateChanged 
					try
					{
						xmlHttp.open("GET","http://localhost:"""+str(PlanetView.PORT)+"/"+self._update_server.get_key()+"""/update",true)
						xmlHttp.send(null)
					} 
					catch (error) 
					{
						document.getElementById("errorMsg").innerHTML="Permissions problem loading ajax"
					}
					if (timed == 1)
					{
						SetTimer()
					}
				} 

				function stateChanged() 
				{ 
					if (xmlHttp.readyState==4 || xmlHttp.readyState=="complete")
				    { 
				    	if (xmlHttp.responseText.length > 0)
				    	{
							line_split = xmlHttp.responseText.split(" ")
							entry_id = line_split[0]
				    		split_point = xmlHttp.responseText.indexOf(" ")
							document.getElementById(entry_id).innerHTML=xmlHttp.responseText.substring(split_point)
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
			html.append("""
				document.oncontextmenu = function()
					{
						parent.location="rightclick:0"
						return false;
					};""")
			
			html.append("--> </script>")
			html.append("""</head><body><span id="errorMsg"></span><br>""")
			
		return "\n".join(html)
		
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
			db_entries = self._db.get_entry_block(e_id_list)
			media = self._db.get_entry_media_block(e_id_list)
		
			for item in db_entries:
				if media.has_key(item['entry_id']):
					item['media'] = media[item['entry_id']]
				else:
					item['media'] = []
					
			#combine them
			entries += db_entries
		
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
		
		item = self._db.get_entry(entry_id)
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
					self._entry_store[entry_id] = (new_format, item)
					return self._entry_store[entry_id]
			self._entry_store[entry_id] = (new_format, item)
		index = self._entrylist.index((entry_id,item['feed_id']))
		if index >= self._first_entry and index <= self._first_entry+ENTRIES_PER_PAGE:
			entry = self._entry_store[entry_id][1]
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
			if self._USING_AJAX:
				ret = []
				ret.append(str(entry_id)+" ")
				ret.append(self._entry_store[entry_id][0])
				ret = "".join(ret)
				self._update_server.push_update(ret)
		
	def _render(self, html):
		# temp until olpcbrowser dows moz_realized
		#logging.debug("="*80)
		#logging.debug(html)
		#logging.debug("="*80)
		if self._moz_realized or utils.RUNNING_SUGAR:
			if self._USING_AJAX:
				self._moz.open_stream("http://localhost:"+str(PlanetView.PORT),"text/html")
			else:
				self._moz.open_stream("file:///","text/html")
			while len(html)>60000:
				part = html[0:60000]
				html = html[60000:]
				self._moz.append_data(part, long(len(part)))
			self._moz.append_data(html, long(len(html)))
			self._moz.close_stream()
			
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
				if feed_id == -1:
					for item in keepers:
						self.emit('entries-viewed', [(item['feed_id'], [item['entry_id']])])
					return False
			self.emit('entries-viewed', [(feed_id, [e['entry_id'] for e in keepers])])
		return False

	def _hulahop_prop_changed(self, obj, pspec):
		if pspec.name == 'status':
			self._main_window.display_status_message(self._moz.get_property('status'))
			
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
		
		if entry_id > 0:
			entry = self._load_entry(entry_id)[1]
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
			if self._show_kept:
				item = gtk.MenuItem(_("_Show All"))
				item.connect('activate', self._toggle_show_kept)
				menu.append(item)
			else:
				item = gtk.MenuItem(_("_Show Kept Entries"))
				item.connect('activate', self._toggle_show_kept)
				menu.append(item)
			
		menu.show_all()
		menu.popup(None,None,None, 3, 0)
		
	def _moz_link_clicked(self, mozembed, link):
		link = link.strip()
		if link == "planet:up":
			self._first_entry -= ENTRIES_PER_PAGE
			self._render_entries(mark_read=True)
		elif link == "planet:down":
			self._first_entry += ENTRIES_PER_PAGE
			self._render_entries(mark_read=True)
		elif link.startswith("rightclick"):
			self._do_context_menu(int(link.split(':')[1]))
		else:
			self.emit('link-activated', link)
			
		return True #don't load url please
		
	def set_show_kept(self, state):
		if state == self._show_kept:
			return
				
		self._toggle_show_kept()
		
	def _toggle_show_kept(self, e=None):
		if self._show_kept:
			self._show_kept = False
		else:
			self._show_kept = True
		self._main_window.set_show_kept_menuitem(self._show_kept)
		self._first_entry = 0
		self._render_entries()
		
	def _moz_new_window(self, mozembed, retval, chromemask):
		# hack to try to properly load links that want a new window
		self.emit('link-activated', mozembed.get_link_message())
		
	def _moz_realize(self, widget, realized):
		self._moz_realized = realized
		self.display_item()
		
	def _moz_link_message(self, data):
		if not utils.RUNNING_HILDON:
			self._main_window.display_status_message(self._moz.get_link_message())
	
	def _gconf_reset_moz_font(self, client, *args, **kwargs):
		self._reset_moz_font()
	
	def _reset_moz_font(self):
		def isNumber(x):
			try:
				float(x)
				return True
			except:
				return False
				
		def isValid(x):
			if x in ["Bold", "Italic", "Regular","BoldItalic"]:#,"Demi","Oblique" Book 
				return False
			return True
				
		moz_font = self._db.get_setting(ptvDB.STRING, '/desktop/gnome/interface/font_name', "Sans Serif 12")
		#take just the beginning for the font name.  prepare for dense, unreadable code
		self._moz_font = " ".join(map(str, [x for x in moz_font.split() if not isNumber(x)]))
		self._moz_font = "'"+self._moz_font+"','"+" ".join(map(str, [x for x in moz_font.split() if isValid(x)])) + "',Arial"
		self._moz_size = int([x for x in moz_font.split() if isNumber(x)][-1])+4
		

					

