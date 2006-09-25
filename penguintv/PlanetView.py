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

import gobject

try:
	import gtkmozembed
except:
	pass
	
ENTRIES_PER_PAGE = 10

class PlanetView:
	"""PlanetView implementes the api for entrylist and entryview, so that the main program doesn't
	need to know that the two objects are actually the same"""
	
	#look at all these class-wide variables!  I'm so bad
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
		
		self._entrylist = []
		
		self._first_entry = 0 #first entry visible
		
		html_dock = widget_tree.get_widget('html_dock')
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
			print "not supported (need AJAX, believe it or not)"
			return
		elif self._renderer == MOZILLA:
			f = open (os.path.join(self._app.glade_prefix,"mozilla.css"))
			for l in f.readlines(): self._css += l
			f.close()
			gtkmozembed.set_profile_path(os.path.join(os.getenv('HOME'),".penguintv"), 'gecko')
			self._moz = gtkmozembed.MozEmbed()
			self._moz.connect("open-uri", self._moz_link_clicked)
			self._moz.connect("link-message", self._moz_link_message)
			self._moz.connect("realize", self._moz_realize, True)
			self._moz.connect("unrealize", self._moz_realize, False)
			self._moz.load_url("about:blank")
			html_dock.add(self._moz)
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
				self._update_server = PlanetView.MyForkingTCPServer(('', PlanetView.PORT), PlanetView.EntryInfoServer)
				break
			except:
				PlanetView.PORT += 1
		if PlanetView.PORT==8050:
			print "tried a lot of ports without success.  Problem?"
		t = threading.Thread(None, self._update_server.serve_forever)
		t.setDaemon(True)
		t.start()
		
	#entrylist functions
	def populate_if_selected(self, feed_id):
		pass
		
	def populate_entries(self, feed_id=None, selected=-1):
		if feed_id is None:
			feed_id = self._current_feed_id
		html = ""
		db_entrylist = self._db.get_entrylist(feed_id)
		
		if feed_id != self._current_feed_id:
			self._current_feed_id = feed_id
			self._first_entry = 0
			last_entry = ENTRIES_PER_PAGE
			self._entry_store={}
			self._entrylist = [e[0] for e in db_entrylist]
			
		else:
			if self._first_entry < 0:
				self._first_entry = 0
			
		if len(db_entrylist)-self._first_entry >= ENTRIES_PER_PAGE:
			last_entry = self._first_entry+ENTRIES_PER_PAGE
		else:
			last_entry = len(db_entrylist)
				
		html = self._build_header()
		
		html += """<table
					style="width: 100%; text-align: left; margin-left: auto; margin-right: auto;"
 					border="0" cellpadding="2" cellspacing="0">
					<tbody>
					<tr><td>"""

		if self._first_entry > 0:
			html += '<a href="planet:up">Newer Entries</a>'
		html += '</td><td style="text-align: right;">'
		if last_entry < len(db_entrylist):
			html += '<a href="planet:down">Older Entries</a>'
		html += "</td></tr></tbody></table>"
		
		for entry_id,title,date in db_entrylist[self._first_entry:last_entry]:
		#for entry_id,title,date in db_entrylist[0:10]:
			html += self._load_entry(entry_id)[0]
			html += "<hr>\n"
			
		html += """<table
					style="width: 100%; text-align: left; margin-left: auto; margin-right: auto;"
					border="0" cellpadding="2" cellspacing="0">
					<tbody>
					<tr><td>"""

		if self._first_entry > 0:
			html += '<a href="planet:up">Newer Entries</a>'
		html += '</td><td style="text-align: right;">'
		if last_entry < len(db_entrylist):
			html += '<a href="planet:down">Older Entries</a>'
		html += "</td></tr></tbody></table>"
		html += "</body></html>"
		
		self._render(html)
		
	def auto_pane(self):
		pass
		
	def update_entry_list(self, entry_id=None):
		if entry_id not in self._entrylist: #not this feed
			return
		if entry_id is None:
			self._entry_store = {}
			self.populate_entries()
		self._load_entry(entry_id, True)
		try:
			index = self._entrylist.index(entry_id)
		except:
			print "can't find index???"
			return
		
	def show_search_results(self, entries, query):
		pass
		
	def unshow_search(self):
		pass
		
	def highlight_results(self, feed_id):
		pass
		
	def clear_entries(self):
		self._first_entry = 0
		last_entry = ENTRIES_PER_PAGE
		self._entry_store={}
		self._entrylist = []
		self._render("<html><body></body></html")

	#entryview functions
	def update_if_selected(self, entry_id=None):
		self.update_entry_list(entry_id)
		
	def display_custom_entry(self, message):
		self._custom_message = message
		print "custom: ",message
		#self.populate_entries()
		
	def undisplay_custom_entry(self):
		self._custom_message = ""
		print "custom: blank (undisplay)"
		
	def display_item(self, item=None, highlight=""):
		if item is None:
			self._render("<html><body></body></html")
		else:
			import traceback
			print traceback.print_stack()
			print "why is display_item being called?"
		
	def finish(self):
		pass
		
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
		
		self._entry_store[entry_id] = (htmlify_item(item, ajax=True),item)
		
		index = self._entrylist.index(entry_id)
		if index >= self._first_entry and index <= self._first_entry+ENTRIES_PER_PAGE:
			entry = self._entry_store[entry_id][1]
			if not entry.has_key('media'):
				return
			ret = []
			ret.append(str(entry_id)+" ")
			for medium in entry['media']:
				ret += htmlify_media(medium, self._mm)
			ret = "".join(ret)
			self._update_server.updates.append(ret)
		
		return self._entry_store[entry_id]
	
	def _render(self, html):
		if self._moz_realized:
			print "rendering"
			self._moz.render_data(html, long(len(html)), "http://localhost:"+str(PlanetView.PORT),"text/html")
			print "done"
		
	def _build_header(self):
		if self._renderer == MOZILLA or self._renderer == DEMOCRACY_MOZ:
			html = (
            """<html><head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
			<style type="text/css">
            body { background-color: %s; color: %s; font-family: %s; font-size: %s; }
            %s
            </style>
            <title>title</title>
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
					xmlHttp.open("GET","http://localhost:"""+str(PlanetView.PORT)+"""/updates",true)
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
  				timerObj = setTimeout("refresh_entries(1)",1000);
			}
			refresh_entries(1)
			-->
            </script>
            </head><body><span id="errorMsg"></span><br>""") % (self._background_color,
            														 self._foreground_color,
            														 self._moz_font, 
            														 self._moz_size, 
            														 self._css)
			
		return html
		
	def _moz_link_clicked(self, mozembed, link):
		link = link.strip()
		if link == "planet:up":
			self._first_entry -= ENTRIES_PER_PAGE
			self.populate_entries(self._current_feed_id)
		elif link == "planet:down":
			self._first_entry += ENTRIES_PER_PAGE
			self.populate_entries(self._current_feed_id)
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
				
		moz_font = self._db.get_setting(ptvDB.STRING, '/desktop/gnome/interface/font_name')
		#take just the beginning for the font name.  prepare for dense, unreadable code
		self._moz_font = " ".join(map(str, [x for x in moz_font.split() if isNumber(x)==False]))
		self._moz_font = "'"+self._moz_font+"','"+" ".join(map(str, [x for x in moz_font.split() if isValid(x)])) + "',Arial"
		self._moz_size = int([x for x in moz_font.split() if isNumber(x)][-1])+4
		
	class MyForkingTCPServer(SocketServer.ForkingTCPServer):
		def __init__(self, server_address, RequestHandlerClass):
			#SocketServer.ForkingTCPServer.__init__(self, server_address, RequestHandlerClass)
			#going against comments and overriding :)  We have to get around timeoutsocket manually
			#or else it doesn't work.  There's some sort of bug in timeoutsocket that's messing us up.
			SocketServer.BaseServer.__init__(self, server_address, RequestHandlerClass)
			self.socket = socket._no_timeoutsocket(self.address_family, self.socket_type)
			self.server_bind()
			self.server_activate()
			self.updates = []
			
		def serve_forever(self):
			while 1:
				self.handle_request()
				if len(self.updates)>0:
					#We must have posted an update.  So pop it (unlike in the request handler,
					#changes actually have an effect here!)
					self.updates.pop(0)
					
	class EntryInfoServer(SimpleHTTPServer.SimpleHTTPRequestHandler):	
		"""for some reason, any variable I change in this class changes RIGHT FUCKING BACK
		as soon as it exits.  So we don't actually pop the value here"""
		def do_GET(self):
			if len(self.server.updates)==0:
				self.wfile.write("")
			else:
				update = self.server.updates[0]
				self.wfile.write(update)
				
