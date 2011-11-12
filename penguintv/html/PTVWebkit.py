# -*- coding: utf-8 -*-

import os.path
import logging

import gobject
import gtk

import PTVhtml
import utils

import webkit

class PTVWebkit(PTVhtml.PTVhtml):
	def __init__(self, view, home, share_path):
		PTVhtml.PTVhtml.__init__(self, view, home, share_path)
		self._home = home	
		self._css = ""
		self._realized = False
		self._USING_AJAX = False
		self._view = view
		self._stream_url = ""
		
		if utils.RUNNING_HILDON:
			f = open(os.path.join(share_path, "mozilla-planet-hildon.css"))
		else:
			f = open(os.path.join(share_path, "mozilla-planet.css"))
		for l in f.readlines(): self._css += l
		f.close()
		
	def finish(self):
		pass
		
	def is_ajax_ok(self):
		if utils.RUNNING_HILDON:
			return False
		return True
			
	def post_show_init(self, widget):
		if utils.RUNNING_HILDON:
			logging.debug("Hildon: Not using ajax view")
			self._USING_AJAX = False
		else:
			self._USING_AJAX = True
			
		if utils.HAS_GCONF:
			try:
				import gconf
			except:
				from gnome import gconf
			self._conf = gconf.client_get_default()
			self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_webview_font)
		self._reset_webview_font()
			
		logging.info("Loading Webkit renderer")
		self._webview = webkit.WebView()
		#self._webview.connect("new-window", self._new_window)
		self._webview.connect("hovering-over-link", self._link_message)
		self._webview.connect("navigation-policy-decision-requested", self._nav_policy)
		self._webview.connect("new-window-policy-decision-requested", self._nav_policy)
		self._webview.connect("realize", self._realize, True)
		self._webview.connect("unrealize", self._realize, False)
		self._webview.connect("status-bar-text-changed", self._console_message)
		#self._webview.connect("script-alert", lambda a,b,c: logging.debug("script-alert"))
		#self._webview.connect("script-confirm", lambda a,b,c: logging.debug("script-confirm"))
		widget.add(self._webview)
		self._webview.show()
		
	def build_header(self, html=""):
		header = ["""<html><head>
			    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
				<style type="text/css">
			    body { background-color: %s; color: %s; font-family: %s; font-size: %s; }
			    %s
			    </style>
			    <title>title</title>""" % (self._view.get_bg_color(),
										   self._view.get_fg_color(),
										   self._webview_font, 
										   self._webview_size, 
										   self._css)] 
										   
		header.append("""<script type="text/javascript"><!--""")
		header.append("""
				document.oncontextmenu = function()
					{
						parent.location="rightclick:0"
						return false;
					};""")
		
		header.append("--> </script>")
		header.append(html)
		header.append("""</head><body>""")
		return "\n".join(header)
		
	def render(self, html, stream_url="file:///", display_id=None):
		if stream_url is None:
			stream_url = "file:///"
		self._stream_url = stream_url
		if self._realized or utils.RUNNING_SUGAR:
			self._webview.load_string(html, 'text/html', 'UTF-8', stream_url)
		else:
			logging.warning("HTML widget not realized")
			
	#def load_update(self, stream_url):
	#	self._stream_url = stream_url
	#	self._webview.load_uri("%s/%s" % (self._stream_url, "update"))
	#	print "load %s/%s" % (self._stream_url, "update")
	
	#def rewrite(self, entry_id, html):
	#	print "rewriting"
	#	document = self._webview.get_dom_document()
	#	document.getElementById(entry_id).innerHTML=html
			
	def dl_interrupt(self):
		pass
		
	#def _new_window(self, mozembed, retval, chromemask):
	#	# hack to try to properly load links that want a new window
	#	self.emit('open-uri', mozembed.get_link_message())
		
	def _realize(self, widget, realized):
		self._realized = realized
		self._webview.load_uri("about:blank")
		
	def _link_message(self, webview, title, uri):
		if uri is None:
			uri = ""
		if not utils.RUNNING_HILDON:
			self.emit('link-message', uri)
			
	def _nav_policy(self, webview, frame, request, action, decision):
		link = request.get_uri().strip()
		#use our own generated htmls and such
		if link.startswith(self._stream_url) or \
		   link.startswith("about"):
		   	decision.use()
		   	return True
		
		decision.ignore()
		self.emit('open-uri', link)
		return True #don't load url please
		
	def _console_message(self, webview, message):
		if len(message) > 0:
			logging.debug("webkit message %s" % (message,))
			
	def _gconf_reset_webview_font(self, client, *args, **kwargs):
		self._reset_webview_font()
	
	def _reset_webview_font(self):
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
				
		webview_font = self._conf.get_string('/desktop/gnome/interface/font_name')
		if webview_font is None:
			webview_font = "Sans Serif 12"
		#take just the beginning for the font name.  prepare for dense, unreadable code
		self._webview_font = " ".join(map(str, [x for x in webview_font.split() if not isNumber(x)]))
		self._webview_font = "'"+self._webview_font+"','"+" ".join(map(str, [x for x in webview_font.split() if isValid(x)])) + "',Arial"
		self._webview_size = int([x for x in webview_font.split() if isNumber(x)][-1])+4

gobject.type_register(PTVWebkit)
