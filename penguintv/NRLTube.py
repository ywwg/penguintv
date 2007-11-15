import logging

import dbus
import dbus.service
import gobject
from dbus import Interface
from dbus.service import method, signal
from dbus.gobject_service import ExportedGObject

import utils

SERVICE = "com.ywwg.NewsReaderLite"
IFACE = SERVICE
PATH = "/com/ywwg/NewsReaderLite"

class NRLTube(ExportedGObject):
	"""The bit that talks over the TUBES!!!"""

	def __init__(self, activity, tube, is_initiator, get_buddy):
		super(NRLTube, self).__init__(tube, PATH)
		self.activity = activity
		self._logger = logging.getLogger('newsreader-activity.NRLTube')
		self.tube = tube
		self.is_initiator = is_initiator
		self.entered = False  # Have we set up the tube?
		self.current_url = None
		self.current_title = None
		self._get_buddy = get_buddy  # Converts handle to Buddy object
		self.tube.watch_participants(self.participant_change_cb)

	def participant_change_cb(self, added, removed):
		self._logger.debug('Tube: Added participants: %r', added)
		self._logger.debug('Tube: Removed participants: %r', removed)
		for handle, bus_name in added:
			buddy = self._get_buddy(handle)
			if buddy is not None:
				self._logger.debug('Tube: Handle %u (Buddy %s) was added',
								   handle, buddy.props.nick)
		for handle in removed:
			buddy = self._get_buddy(handle)
			if buddy is not None:
				self._logger.debug('Buddy %s was removed' % buddy.props.nick)
		if not self.entered:
			self.tube.add_signal_receiver(self.change_feed_cb, 'ChangeFeed', IFACE,
					path=PATH, sender_keyword='sender')
			if self.is_initiator:
				self._logger.debug("I'm initiating the tube, will "
					"watch for hellos.")
				self.tube.add_signal_receiver(self.hello_cb, 'Hello', IFACE,
					path=PATH, sender_keyword='sender')
				self.current_title, self.current_url = self.activity.get_current_feed()
			else:
				self._logger.debug('Hello, everyone! What did I miss?')
				self.Hello()
				self.add_hello_handler()
		self.entered = True

	@signal(dbus_interface=IFACE, signature='')
	def Hello(self):
		"""Say Hello to whoever else is in the tube."""
		self._logger.debug('I said Hello.')

	def hello_cb(self, sender=None):
		"""Somebody Helloed me. World them."""
		if sender == self.tube.get_unique_name():
			# sender is my bus name, so ignore my own signal
			return
		self._logger.debug('Newcomer %s has joined', sender)
		self._logger.debug('Welcoming newcomer and sending them the current feed')
		
		#FIXME: Need to transmit the whole list of feeds in this session, not just
		#the current one
		if self.current_url is not None:
			self.ChangeFeed(self.current_url, self.current_title)
		
	def add_hello_handler(self):
		self._logger.debug('Adding hello handler.')
		self.tube.add_signal_receiver(self.hello_cb, 'Hello', IFACE,
			path=PATH, sender_keyword='sender')
												 
	@signal(dbus_interface=IFACE, signature='ss')
	def ChangeFeed(self, new_url, new_title):
		self._logger.debug("sending feed change signal: %s %s" % (new_url, new_title))
		
	def change_feed_cb(self, new_url, new_title, sender=None):
		"""To be called on the incoming XO after they Hello."""
		if new_url != self.current_url:
		#if not self.current_url:
			self._logger.debug('Someone else changed the feed: %s %s' % (new_url, new_title))
			self.current_url = new_url
			self.current_title = new_title
			self.activity.select_by_url(new_url, new_title)
		else:
			self._logger.debug("omeone else changed the feed? no! Same Feed: %s %s"  % (new_url, new_title))
