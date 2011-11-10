import os
import logging

import gtk

import utils
import SimpleHTTPServer
import SimpleImageCache

class EntryInfoServer(SimpleHTTPServer.SimpleHTTPRequestHandler):	
	"""This class is recreated on every GET call.  So things changed in this
	   scope don't stick"""
	
	_image_cache = SimpleImageCache.SimpleImageCache()

	def __init__(self, request, client_address, server):
		self._server = server
		SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self, request, client_address, server)
		
	def do_GET(self):
		p = self.path[1:] #strip leading /
		
		splitted = p.split("/")
		
		key = ""
		command = "update"
		arg = ""
		
		if len(splitted) >= 1:
			key = splitted[0]
		
		if len(splitted) == 0 or key != self.server.get_key():
			self.wfile.write("PenguinTV Unauthorized")
			return
			
		if len(splitted) >= 2:
			command = splitted[1]
		if len(splitted) >= 3:
			arg = splitted[2]
			
		if command == "update":
			if self.server.update_count()==0:
				self.wfile.write("")
			else:
				update = self.server.peek_update()
				#print "WRITING UPDATE", update
				#self.send_header('Access-Control-Allow-Origin', '*')
				#self.send_header('Cache-Control', 'no-cache')
				self.wfile.write(update)
		elif command == "icon":
			theme = gtk.icon_theme_get_default()
			iconinfo = theme.lookup_icon(arg, 16, gtk.ICON_LOOKUP_NO_SVG)
			if iconinfo is not None:
				image_data = self._image_cache.get_image_from_file(iconinfo.get_filename())
				self.wfile.write(image_data)
			else:
				logging.error("no icon found for: %s" % (arg,))
				self.wfile.write("")
		elif command == "pixmaps":
			image_data = self._image_cache.get_image_from_file(utils.get_image_path(arg))
			self.wfile.write(image_data)
		elif command == "cache":
			#strip out possible ../../../ crap.  I think this is all I need?
			securitize = [s for s in splitted if s not in ("/",".","..")]
			filename = os.path.join(self._server.store_location, *securitize[2:])
			if utils.RUNNING_HILDON:
				#not enough ram to cache it
				f = open(filename, "rb")
				image_data = f.read()
				f.close()
			else:
				image_data = self._image_cache.get_image_from_file(filename)
			self.wfile.write(image_data)
