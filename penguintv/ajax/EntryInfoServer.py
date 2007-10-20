import SimpleHTTPServer
import logging

class EntryInfoServer(SimpleHTTPServer.SimpleHTTPRequestHandler):	
	"""for some reason, any variable I change in this class changes RIGHT FUCKING BACK
	as soon as it exits.  So we don't actually pop the value here"""

	def __init__(self, request, client_address, server):
		SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self, request, client_address, server)
		
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
