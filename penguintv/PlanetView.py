#PlanetView.  Actually uses AJAX on an internal server to update progress 
#and media info.  Stupid, or clever?  You be the judge!
#suggestions for security holes?  The only problem I see is that someone else can see the 
#progress of our downloads, and prevent those UI updates from making it to the screen
#OH NOES!

from EntryView import *
import ptvDB
import utils
import gtkmozembed

import socket
import SocketServer
import SimpleHTTPServer
import urllib
import threading
import random

try:
	import gtkmozembed
except:
	pass
	
ENTRIES_PER_PAGE = 10

#states
S_DEFAULT=0
S_SEARCH=1

class PlanetView:
	"""PlanetView implementes the api for entrylist and entryview, so that the main program doesn't
	need to know that the two objects are actually the same"""
	
	PORT = 8000
	def __init__(self, widget_tree, app, main_window, db, renderer=GTKHTML):
		#public
		self.presently_selecting = False
		
		#protected
		self._app = app
		
		self._mm = self._app.mediamanager
		self._widget_tree = widget_tree
		self._main_window = main_window
		self._db = db
		self._renderer = renderer
		self._css = ""
		self._current_feed_id = -1
		self._moz_realized = False
		self._feed_title=""
		self._state = S_DEFAULT
		
		self._entrylist = []
		self._entry_store = {}
		
		self._first_entry = 0 #first entry visible
		
		html_dock = widget_tree.get_widget('html_dock')
		scrolled_window = gtk.ScrolledWindow()
		html_dock.add(scrolled_window)
		scrolled_window.set_property("hscrollbar-policy",gtk.POLICY_AUTOMATIC)
		scrolled_window.set_property("vscrollbar-policy",gtk.POLICY_AUTOMATIC)
		style = html_dock.get_style().copy()
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
			self._app.log("not supported (need AJAX, believe it or not)")
			print "not supported (need AJAX, believe it or not)"
			return
		elif self._renderer == MOZILLA:
			f = open (os.path.join(self._app.glade_prefix,"mozilla-planet.css"))
			for l in f.readlines(): self._css += l
			f.close()
			gtkmozembed.set_profile_path(os.path.join(os.getenv('HOME'),".penguintv"), 'gecko')
			self._moz = gtkmozembed.MozEmbed()
			self._moz.connect("open-uri", self._moz_link_clicked)
			self._moz.connect("link-message", self._moz_link_message)
			self._moz.connect("realize", self._moz_realize, True)
			self._moz.connect("unrealize", self._moz_realize, False)
			self._moz.load_url("about:blank")
			scrolled_window.add_with_viewport(self._moz)
			#scrolled_window.add(self._moz)
			self._moz.show()
			if ptvDB.HAS_GCONF:
				import gconf
				self._conf = gconf.client_get_default()
				self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_moz_font)
			self._reset_moz_font()
		html_dock.show_all()
		while True:
			try:
				if PlanetView.PORT == 8050:
					break
				self._update_server = PlanetView.MyTCPServer(('', PlanetView.PORT), PlanetView.EntryInfoServer)
				break
			except:
				PlanetView.PORT += 1
		if PlanetView.PORT==8050:
			self._app.log("tried a lot of ports without success.  Problem?")
			print "tried a lot of ports without success.  Problem?"
		t = threading.Thread(None, self._update_server.serve_forever)
		t.setDaemon(True)
		t.start()
		
	#entrylist functions
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

		db_entrylist = self._db.get_entrylist(feed_id)
		
		if feed_id != self._current_feed_id:
			self._current_feed_id = feed_id
			self._first_entry = 0
			self._entry_store={}
			self._feed_title = self._db.get_feed_title(feed_id)
		
		self._entrylist = [e[0] for e in db_entrylist]
		self._render_entries()
		
		
	def auto_pane(self):
		pass
		
	def update_entry_list(self, entry_id=None):
		if entry_id is None:
			self._entry_store = {}
			self._render_entries()
		if entry_id not in self._entrylist: #not this feed
			return
		self._load_entry(entry_id, True)
		
	def show_search_results(self, entries, query):
		if entries is None:
			self.display_custom_entry(_("No entries match those search criteria"))
			
		self._entrylist = [e[0] for e in entries]
		print "rendering (highlighting)",query
		self._render_entries(query)
		
	def unshow_search(self):
		self._render("<html><body></body></html")
		
	def highlight_results(self, feed_id):
		"""doesn't apply in planet mode"""
		pass
		
	def clear_entries(self):
		self._first_entry = 0
		self._entry_store={}
		self._entrylist = []
		self._render("<html><body></body></html")
		
	def _unset_state(self):
		self.clear_entries()
	
	def set_state(self, newstate, data=None):
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
	def update_if_selected(self, entry_id=None):
		self.update_entry_list(entry_id)
		
	def display_custom_entry(self, message):
		self._custom_message = message
		#print "custom: ",message
		#self.populate_entries()
		
	def undisplay_custom_entry(self):
		self._custom_message = ""
		#print "custom: blank (undisplay)"
		
	def display_item(self, item=None, highlight=""):
		if item is None:
			self._render("<html><body></body></html")
		else:
			pass
		
	def finish(self):
		self._update_server.finish()
		urllib.urlopen("http://localhost:"+str(PlanetView.PORT)+"/") #pings the server, gets it to quit
		self._render("<html><body></body></html")
		
	#protected functions
	def _load_entry(self, entry_id, force = False):
		if self._entry_store.has_key(entry_id) and not force:
			return self._entry_store[entry_id]
		
		item = self._db.get_entry(entry_id)
		media = self._db.get_entry_media(entry_id)
		read = self._db.get_entry_read(entry_id)
		if media:
			item['media']=media
		item['read'] = read
		if self._state == S_SEARCH:
		#if self._showing_search:
			item['feed_title'] = self._db.get_feed_title(item['feed_id'])
			self._entry_store[entry_id] = (htmlify_item(item, ajax=True, with_feed_titles=True, indicate_new=True),item)
		else:
			self._entry_store[entry_id] = (htmlify_item(item, ajax=True, indicate_new=True),item)
		
		index = self._entrylist.index(entry_id)
		if index >= self._first_entry and index <= self._first_entry+ENTRIES_PER_PAGE:
			entry = self._entry_store[entry_id][1]
			if not entry.has_key('media'):
				return self._entry_store[entry_id]
			ret = []
			ret.append(str(entry_id)+" ")
			for medium in entry['media']:
				ret += htmlify_media(medium, self._mm)
			ret = "".join(ret)
			self._update_server.push_update(ret)
		
		return self._entry_store[entry_id]
		
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
		entries = ""
		html = ""
		unreads = []
		for entry_id in self._entrylist[self._first_entry:last_entry]:
			entry_html, item = self._load_entry(entry_id)
			if item.has_key('media'):
				media_exists = True
			if not item.has_key('media'):
				unreads.append(entry_id)
			entries += entry_html
			
		self._app.mark_entrylist_as_viewed(unreads, False)
		for e in unreads:
			try:
				del self._entry_store[e] #need to regen because it's not new anymore
			except:
				print "warning: can't remove non-existant entry from store"
			
		#######build HTML#######	
				
		html = self._build_header(media_exists)
		
		html += """<div id="nav_bar"><table
					style="width: 100%; text-align: left; margin-left: auto; margin-right: auto;"
 					border="0" cellpadding="2" cellspacing="0">
					<tbody>
					<tr><td>"""
		if self._first_entry > 0:
			html += '<a href="planet:up">Newer Entries</a>'
		html += '</td><td style="text-align: right;">'
		if last_entry < len(self._entrylist):
			html += '<a href="planet:down">Older Entries</a>'
		html += "</td></tr></tbody></table></div>"
		
		if self._state != S_SEARCH:
		#if not self._showing_search: 
			html += '<div class="feed_title">'+self._feed_title+"</div>"
		html += entries
			
		html += """<div id="nav_bar"><table
					style="width: 100%; text-align: left; margin-left: auto; margin-right: auto;"
					border="0" cellpadding="2" cellspacing="0">
					<tbody>
					<tr><td>"""
		if self._first_entry > 0:
			html += '<a href="planet:up">Newer Entries</a>'
		html += '</td><td style="text-align: right;">'
		if last_entry < len(self._entrylist):
			html += '<a href="planet:down">Older Entries</a>'
		html += "</td></tr></tbody></table></div>"
		html += "</body></html>"
		
		if highlight is not None:
			print "doing highlight"
			html = html.encode('utf-8')
			try:
				highlight = highlight.replace("*","")
				p = HTMLHighlightParser(highlight)
				p.feed(html)
				html = p.new_data
				print "highlighted"
			except:
				pass
				
		self._render(html)
	
	def _build_header(self, media_exists):
		if self._renderer == MOZILLA or self._renderer == DEMOCRACY_MOZ:
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
			if media_exists:
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
						xmlHttp.open("GET","http://localhost:"""+str(PlanetView.PORT)+"/"+self._update_server.generate_key()+"""",true)
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
					    	response_array = xmlHttp.responseText.split(" ")
					    	entry_id = response_array[0]
					    	split_point = xmlHttp.responseText.indexOf(" ")
							document.getElementById(entry_id).innerHTML=xmlHttp.responseText.substring(split_point)
							//keep refreshing
							refresh_entries(0) //don't queue timer
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
		
	def _render(self, html):
		if self._moz_realized:
			self._moz.open_stream("http://localhost:"+str(PlanetView.PORT),"text/html")
			#self._moz.open_stream("file:///","text/html")
			while len(html)>60000:
					part = html[0:60000]
					html = html[60000:]
					self._moz.append_data(part, long(len(part)))
			self._moz.append_data(html, long(len(html)))
			self._moz.close_stream()
		
	def _moz_link_clicked(self, mozembed, link):
		link = link.strip()
		if link == "planet:up":
			self._first_entry -= ENTRIES_PER_PAGE
			self._render_entries()
		elif link == "planet:down":
			self._first_entry += ENTRIES_PER_PAGE
			self._render_entries()
		else:
			self._app.activate_link(link)
		return True #don't load url please
		
	def _moz_realize(self, widget, realized):
		self._moz_realized = realized
		
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
		
	class MyTCPServer(SocketServer.TCPServer):
		def __init__(self, server_address, RequestHandlerClass):
			#SocketServer.ForkingTCPServer.__init__(self, server_address, RequestHandlerClass)
			#going against comments and overriding :)  We have to get around timeoutsocket manually
			#or else it doesn't work.  There's some sort of bug in timeoutsocket that's messing us up.
			SocketServer.BaseServer.__init__(self, server_address, RequestHandlerClass)
			self.socket = socket._no_timeoutsocket(self.address_family, self.socket_type)
			self.server_bind()
			self.server_activate()
			self._key = ""
			self.generate_key()
			
			self._updates = []
			self._quitting = False
			
		def serve_forever(self):
			while 1:
				self.handle_request()
				if self._quitting:
					return
				if len(self._updates)>0:
					#We must have posted an update.  So pop it (unlike in the request handler,
					#changes actually have an effect here!)
					self._updates.pop(0)
					
		def finish(self):
			self._quitting = True
					
		def generate_key(self):
			self._key = str(random.randint(1,1000000))
			return self._key
			
		def get_key(self):
			return self._key
			
		def push_update(self, update):
			self._updates.append(update)
			
		def peek_update(self):
			return self._updates[0]
			
		def update_count(self):
			return len(self._updates)
					
	class EntryInfoServer(SimpleHTTPServer.SimpleHTTPRequestHandler):	
		"""for some reason, any variable I change in this class changes RIGHT FUCKING BACK
		as soon as it exits.  So we don't actually pop the value here"""
		def do_GET(self):
			key = self.path[1:] #strip leading /
			if key != self.server.get_key():
				self.wfile.write("PenguinTV Unauthorized")
				return
			if self.server.update_count()==0:
				self.wfile.write("")
			else:
				update = self.server.peek_update()
				self.wfile.write(update)
				