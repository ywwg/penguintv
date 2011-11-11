import SocketServer
import random
import logging

class MyTCPServer(SocketServer.ForkingTCPServer):
	def __init__(self, server_address, RequestHandlerClass, store_location):
		SocketServer.ForkingTCPServer.__init__(self, server_address, RequestHandlerClass)
		
		self._key = ""
		self.generate_key()
		
		self._updates = []
		self._quitting = False
		self.store_location = store_location
		
	def serve_forever(self):
		while 1:
			try:
				self.handle_request()
			except Exception, e:
				logging.error("Error in Ajax Server: %s" % str(e))
				continue
			if self._quitting:
				logging.info('quitting tcp server')
				return
			if len(self._updates)>0:
				#We must have posted an update.  So pop it (unlike in the request handler,
				#changes actually have an effect here!)
				self._updates.pop(0)
				#pass
				
	def finish(self):
		self._quitting = True
				
	def generate_key(self):
		self._key = str(random.randint(1,1000000))
		return self._key
		
	def get_key(self):
		return self._key
		
	def push_update(self, update):
		remove_list = [u for u in self._updates if u.split(" ")[0] == update.split(" ")[0]]
		for item in remove_list:
			self._updates.remove(item)
		self._updates.append(update)
		
	def peek_update(self):
		return self._updates[0]
		
	def peek_all(self):
		return "\n".join(self._updates)

	def clear_updates(self):
		self._updates = []
		
	def update_count(self):
		return len(self._updates)
		
