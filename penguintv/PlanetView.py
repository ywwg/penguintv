#PlanetView.  Actually uses AJAX on an internal server to update progress 
#and media info.  Stupid, or clever?  You be the judge!
#suggestions for security holes?  The only problem I see is that someone else can see the 
#progress of our downloads, and prevent those UI updates from making it to the screen
#OH NOES!


import logging
import os, os.path

import gobject
import gtk

from EntryFormatter import *
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
		'entries-selected': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_PYOBJECT])),
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
	
	def __init__(self, dock_widget, main_window, db, glade_path, feed_list_view=None, app=None, renderer=MOZILLA):
		gobject.GObject.__init__(self)
		#public
		self.presently_selecting = False
		
		#protected
		if app is not None:
			self._mm = app.mediamanager
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
		
		self._entrylist = []
		self._readinfo  = None
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
		
		if self._renderer == GTKHTML:
			logging.error("gtkhtml and planetview not supported")
			return
			#self._USING_AJAX = False
		elif self._renderer == MOZILLA:
			if utils.RUNNING_SUGAR:
				self._USING_AJAX = False
				f = open(os.path.join(glade_path, "mozilla-planet-olpc.css"))
				for l in f.readlines(): self._css += l
				f.close()
				
				hulahop.startup(os.path.join(self._db.home, 'gecko'))
				import OLPCBrowser
				self._moz = OLPCBrowser.Browser()
				self._moz.load_uri("about:blank")
				self._moz.connect("notify", self._hulahop_prop_changed)
			else:
				self._USING_AJAX = True
				f = open(os.path.join(glade_path, "mozilla-planet.css"))
				for l in f.readlines(): self._css += l
				f.close()
				if not utils.init_gtkmozembed():
					logging.error("Error initializing mozilla.  Penguintv may crash shortly")
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
				import gconf
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
			t = threading.Thread(None, self._update_server.serve_forever)
			t.setDaemon(True)
			t.start()
		else:
			logging.info("not using ajax")
		
		#signals
		self._handlers = []
		if feed_list_view is not None:
			h_id = feed_list_view.connect('feed-selected', self.__feedlist_feed_selected_cb)
			self._handlers.append((feed_list_view.disconnect, h_id))
			h_id = feed_list_view.connect('no-feed-selected', self.__feedlist_none_selected_cb)
			self._handlers.append((feed_list_view.disconnect, h_id))
		if app is not None:
			h_id = app.connect('feed-added',self.__feed_added_cb)
			self._handlers.append((app.disconnect, h_id))
			h_id = app.connect('feed-removed', self.__feed_removed_cb)
			self._handlers.append((app.disconnect, h_id))
			h_id = app.connect('feed-polled', self.__feed_polled_cb)
			self._handlers.append((app.disconnect, h_id))
			h_id = app.connect('entry-updated', self.__entry_updated_cb)
			self._handlers.append((app.disconnect, h_id))
			h_id = app.connect('render-ops-updated', self.__render_ops_updated_cb)
			self._handlers.append((app.disconnect, h_id))
		screen = gtk.gdk.screen_get_default()
		h_id = screen.connect('size-changed', self.__size_changed_cb)
		self._handlers.append((screen.disconnect, h_id))
		
	def __feedlist_feed_selected_cb(self, o, feed_id):
		self.populate_entries(feed_id)
		
	def __feedlist_none_selected_cb(self, o):
		self.clear_entries()
		
	def __feed_added_cb(self, app, feed_id, success):
		if success:
			self.populate_entries(feed_id)
			
	def __feed_polled_cb(self, app, feed_id, update_data):
		if feed_id == self._current_feed_id:
			self.populate_entries(feed_id)
			
	def __feed_removed_cb(self, app, feed_id):
		self.clear_entries()
		
	def __entry_updated_cb(self, app, entry_id, feed_id):
		self.update_entry_list(entry_id)
		if feed_id == self._current_feed_id:
			self._render_entries()
			
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
			return self._entrylist[0]
		return None
	
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

		if feed_id != self._current_feed_id:
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
		self._readinfo = []
		for e in db_entrylist:
			self._entrylist.append(e[0])
			self._readinfo.append(e[3])
			
		self._convert_newlines = self._db.get_flags_for_feed(feed_id) & ptvDB.FF_ADDNEWLINES == ptvDB.FF_ADDNEWLINES
			
		self._render_entries()
		
	def auto_pane(self):
		pass
		
	def update_entry_list(self, entry_id=None):
		if entry_id is None:
			self._entry_store = {}
			self.populate_entries()
		else:
			if entry_id not in self._entrylist: #not this feed
				return
			self._load_entry(entry_id, True)
			
	def mark_as_viewed(self, entry_id=None):
		logging.error("doesn't apply in planet view, right?")
	
	def show_search_results(self, entries, query):
		if entries is None:
			self.display_custom_entry(_("No entries match those search criteria"))
			
		self._entrylist = [e[0] for e in entries]
		self._convert_newlines = False
		try:
			self._render_entries(query)
		except ptvDB.NoEntry:
			logging.warning("error displaying search")
			self._render(_("There was an error displaying the search results.  Please reindex searches and try again"))
		
	def unshow_search(self):
		self._render("<html><body></body></html")
		
	def highlight_results(self, feed_id):
		"""doesn't apply in planet mode"""
		pass
		
	def clear_entries(self):
		self._current_feed_id = -1
		self._first_entry = 0
		self._entry_store={}
		self._entrylist = []
		self._convert_newlines = False
		self._readinfo  = None
		self._render("<html><body></body></html")
		if self._USING_AJAX:
			self._update_server.clear_updates()
		
	def _unset_state(self):
		self.clear_entries()
	
	def set_state(self, newstate, data=None):
		import penguintv
		d = {penguintv.DEFAULT: S_DEFAULT,
			 penguintv.MANUAL_SEARCH: S_SEARCH,
			 penguintv.TAG_SEARCH: S_SEARCH,
			 #penguintv.ACTIVE_DOWNLOADS: S_DEFAULT,
			 penguintv.LOADING_FEEDS: S_DEFAULT}
			 
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
		if not utils.RUNNING_SUGAR:
			gtkmozembed.pop_startup()
		
	#protected functions
	def _render_entries(self, highlight=None):
		"""Takes a block on entry_ids and throws up a page.  also calls penguintv so that entries
		are marked as read"""

		if self._first_entry < 0:
			self._first_entry = 0
			
		if len(self._entrylist)-self._first_entry >= ENTRIES_PER_PAGE:
			last_entry = self._first_entry+ENTRIES_PER_PAGE
		else:
			last_entry = len(self._entrylist)
			
		media_exists = False
		entries = []
		html = ""
		unreads = []
		
		#preload the block of entries, which is nicer to the db
		self._load_entry_block(self._entrylist[self._first_entry:last_entry])

		i=self._first_entry-1
		for entry_id in self._entrylist[self._first_entry:last_entry]:
			i+=1
			entry_html, item = self._load_entry(entry_id)
			if item.has_key('media'):
				media_exists = True
			else:
				if self._readinfo:
					if self._readinfo[i]==0:
						unreads.append(entry_id)
				else:
					unreads.append(entry_id)
			if highlight is not None:
				entry_html = entry_html.encode('utf-8')
				try:
					highlight = highlight.replace("*","")
					p = HTMLHighlightParser(highlight)
					p.feed(entry_html)
					entry_html = p.new_data
				except:
					pass	
					
			if self._auth_info[0] != -1:
				p = HTMLImgAuthParser(self._auth_info[2], self._auth_info[1])
				p.feed(entry_html)
				entry_html = p.new_data
			
			entries.append(entry_html)

		self.emit('entries-selected', self._current_feed_id, unreads)
		for e in unreads:
			try:
				del self._entry_store[e] #need to regen because it's not new anymore
			except:
				logging.warning("can't remove non-existant entry from store")
			
		#######build HTML#######	
		html = []
		html.append(self._build_header(media_exists))
		
		html.append(self._custom_message)
		
		html.append("""<div id="nav_bar"><table
					style="width: 100%; text-align: left; margin-left: auto; margin-right: auto;"
 					border="0" cellpadding="2" cellspacing="0">
					<tbody>
					<tr><td>""")
		if self._first_entry > 0:
			html.append('<a href="planet:up">Newer Entries</a>')
		html.append('</td><td style="text-align: right;">')
		if last_entry < len(self._entrylist):
			html.append('<a href="planet:down">Older Entries</a>')
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
			html.append('<a href="planet:up">Newer Entries</a>')
		html.append('</td><td style="text-align: right;">')
		if last_entry < len(self._entrylist):
			html.append('<a href="planet:down">Older Entries</a>')
		html.append("</td></tr></tbody></table></div>")
		html.append("</body></html>")
		
		html = "".join(html)
		
		self._render(html)
	
	def _build_header(self, media_exists):
		if self._renderer == MOZILLA:
			html = (
            """<html><head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
			<style type="text/css">
            body { background-color: %s; color: %s; font-family: %s; font-size: %s; }
            %s
            </style>
            <title>title</title>""") % (self._background_color,
									   self._foreground_color,
									   self._moz_font, 
									   self._moz_size, 
									   self._css)
			if media_exists and self._USING_AJAX:
				html += """
	            <script type="text/javascript">
	            <!--
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
						xmlHttp.open("GET","http://localhost:"""+str(PlanetView.PORT)+"/"+self._update_server.get_key()+"""",true)
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
					    	response_array = xmlHttp.responseText.split("\\n")
							for (line in response_array)
							{
								line_split = response_array[line].split(" ")
								entry_id = line_split[0]
					    		split_point = response_array[line].indexOf(" ")
								document.getElementById(entry_id).innerHTML=response_array[line].substring(split_point)
							}
							//keep refreshing
							//refresh_entries(0) //don't queue timer
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
	  				timerObj = setTimeout("refresh_entries(1)",2000);
				}
				refresh_entries(1)
				-->
	            </script>"""
			html += """</head><body><span id="errorMsg"></span><br>"""
			
		return html
		
	def _load_entry_block(self, entry_id_list):
		for entry in entry_id_list:
			if self._entry_store.has_key(entry):
				entry_id_list.remove(entry)
		
		if len(entry_id_list) == 0:
			return
				
		entries = self._db.get_entry_block(entry_id_list)
		media = self._db.get_entry_media_block(entry_id_list)
		for item in entries:
			if media.has_key(item['entry_id']):
				item['media'] = media[item['entry_id']]
				if self._USING_AJAX:
					ret = []
					ret.append(str(item['entry_id'])+" ")
					for medium in item['media']:
						ret += htmlify_media(medium, self._mm)
					ret = "".join(ret)
					self._update_server.push_update(ret)
				
			if self._state == S_SEARCH:
				item['feed_title'] = self._db.get_feed_title(item['feed_id'])
				self._entry_store[item['entry_id']] = (htmlify_item(item, mm=self._mm, ajax=self._USING_AJAX, with_feed_titles=True, indicate_new=not utils.RUNNING_SUGAR, basic_progress=not self._USING_AJAX, convert_newlines=self._convert_newlines),item)
			else:
				self._entry_store[item['entry_id']] = (htmlify_item(item, mm=self._mm, ajax=self._USING_AJAX, indicate_new=not utils.RUNNING_SUGAR, basic_progress=not self._USING_AJAX, convert_newlines=self._convert_newlines),item)
				
	def _load_entry(self, entry_id, force = False):
		if self._entry_store.has_key(entry_id) and not force:
			#print "loaded:", self._entry_store[entry_id]
			return self._entry_store[entry_id]
		
		item = self._db.get_entry(entry_id)
		media = self._db.get_entry_media(entry_id)
		if media:
			item['media']=media
		if self._state == S_SEARCH:
			item['feed_title'] = self._db.get_feed_title(item['feed_id'])
			self._entry_store[entry_id] = (htmlify_item(item, mm=self._mm, ajax=self._USING_AJAX, with_feed_titles=True, indicate_new=not utils.RUNNING_SUGAR, basic_progress=not self._USING_AJAX, convert_newlines=self._convert_newlines),item)
		else:
			self._entry_store[entry_id] = (htmlify_item(item, mm=self._mm, ajax=self._USING_AJAX, indicate_new=not utils.RUNNING_SUGAR, basic_progress=not self._USING_AJAX, convert_newlines=self._convert_newlines),item)
		
		index = self._entrylist.index(entry_id)
		if index >= self._first_entry and index <= self._first_entry+ENTRIES_PER_PAGE:
			entry = self._entry_store[entry_id][1]
			if not entry.has_key('media'):
				return self._entry_store[entry_id]
			if self._USING_AJAX:
				ret = []
				ret.append(str(entry_id)+" ")
				for medium in entry['media']:
					ret += htmlify_media(medium, self._mm)
				ret = "".join(ret)
				self._update_server.push_update(ret)
		
		return self._entry_store[entry_id]
		
	def _render(self, html):
		# temp until olpcbrowser dows moz_realized
		if self._moz_realized or utils.RUNNING_SUGAR:
			self._moz.open_stream("http://localhost:"+str(PlanetView.PORT),"text/html")
			while len(html)>60000:
					part = html[0:60000]
					html = html[60000:]
					self._moz.append_data(part, long(len(part)))
			self._moz.append_data(html, long(len(html)))
			self._moz.close_stream()
			
	def _hulahop_prop_changed(self, obj, pspec):
		if pspec.name == 'status':
			self._main_window.display_status_message(self._moz.get_property('status'))
		
	def _moz_link_clicked(self, mozembed, link):
		link = link.strip()
		if link == "planet:up":
			self._first_entry -= ENTRIES_PER_PAGE
			self._render_entries()
		elif link == "planet:down":
			self._first_entry += ENTRIES_PER_PAGE
			self._render_entries()
		else:
			self.emit('link-activated', link)
		return True #don't load url please
		
	def _moz_new_window(self, mozembed, retval, chromemask):
		# hack to try to properly load links that want a new window
		self.emit('link-activated', mozembed.get_link_message())
		
	def _moz_realize(self, widget, realized):
		self._moz_realized = realized
		self.display_item()
		
	def _moz_link_message(self, data):
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
		

					

