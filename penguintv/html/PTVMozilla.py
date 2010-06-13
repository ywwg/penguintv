import os.path
import logging

import gobject
import gtk

import PTVhtml
import utils

try:
	import gtkmozembed
except:
	try:
		from ptvmozembed import gtkmozembed
	except:
		pass

class PTVMozilla(PTVhtml.PTVhtml):
	def __init__(self, view, home, share_path):
		PTVhtml.PTVhtml.__init__(self, view, home, share_path)
		self._home = home	
		self._css = ""
		self._realized = False
		self._USING_AJAX = False
		self._view = view
		
		if utils.RUNNING_HILDON:
			f = open(os.path.join(share_path, "mozilla-planet-hildon.css"))
		else:
			f = open(os.path.join(share_path, "mozilla-planet.css"))
		for l in f.readlines(): self._css += l
		f.close()
		
	def finish(self):
		self._moz.destroy()
		gtkmozembed.pop_startup()
		
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
			self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_moz_font)
		self._reset_moz_font()
			
		utils.init_gtkmozembed()
		gtkmozembed.set_profile_path(self._home, 'gecko')
		gtkmozembed.push_startup()
		self._moz = gtkmozembed.MozEmbed()
		self._moz.connect("new-window", self._new_window)
		self._moz.connect("link-message", self._link_message)
		self._moz.connect("open-uri", self._link_clicked)
		self._moz.connect("realize", self._realize, True)
		self._moz.connect("unrealize", self._realize, False)
		widget.add_with_viewport(self._moz)
		self._moz.show()
		
	def build_header(self, html=""):
		header = ["""<html><head>
			    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
				<style type="text/css">
			    body { background-color: %s; color: %s; font-family: %s; font-size: %s; }
			    %s
			    </style>
			    <title>title</title>""" % (self._view.get_bg_color(),
										   self._view.get_fg_color(),
										   self._moz_font, 
										   self._moz_size, 
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
		if self._realized or utils.RUNNING_SUGAR:
			if stream_url is None:
				stream_url = "file:///"
			self._moz.render_data(html, long(len(html)), stream_url, 'text/html')
		else:
			logging.warning("HTML widget not realized")
			
	def dl_interrupt(self):
		pass
		
	def _new_window(self, mozembed, retval, chromemask):
		# hack to try to properly load links that want a new window
		self.emit('open-uri', mozembed.get_link_message())
		
	def _realize(self, widget, realized):
		self._realized = realized
		self._moz.load_url("about:blank")
		#self._moz.load_url("http://google.com")
		
	def _link_message(self, data):
		if not utils.RUNNING_HILDON:
			self.emit('link-message', self._moz.get_link_message())
			
	def _link_clicked(self, mozembed, link):
		link = link.strip()
		#As of ubuntu 10.04, I get tons of spurious file:/// or ajax proxy url
		#signals that I have to trap
		if link == "file:///" or link.startswith("http://localhost:80"):
			return False
		self.emit('open-uri', link)
		return True #don't load url please
			
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
				
		moz_font = self._conf.get_string('/desktop/gnome/interface/font_name')
		if moz_font is None:
			moz_font = "Sans Serif 12"
		#take just the beginning for the font name.  prepare for dense, unreadable code
		self._moz_font = " ".join(map(str, [x for x in moz_font.split() if not isNumber(x)]))
		self._moz_font = "'"+self._moz_font+"','"+" ".join(map(str, [x for x in moz_font.split() if isValid(x)])) + "',Arial"
		self._moz_size = int([x for x in moz_font.split() if isNumber(x)][-1])+4

gobject.type_register(PTVMozilla)
