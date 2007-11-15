import dbus
import dbus.service
import gobject
from dbus import Interface
from dbus.service import method, signal
from dbus.gobject_service import ExportedGObject

import utils

class NRLTube(ExportedGObject):
    """The bit that talks over the TUBES!!!"""

    def __init__(self, tube, is_initiator, get_buddy):
        super(NRLTube, self).__init__(tube, PATH)
        self._logger = logging.getLogger('hellomesh-activity.NRLTube')
        self.tube = tube
        self.is_initiator = is_initiator
        self.entered = False  # Have we set up the tube?
        self.helloworld = False  # Trivial "game state"
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
            if self.is_initiator:
                self._logger.debug("I'm initiating the tube, will "
                    "watch for hellos.")
                self.tube.add_signal_receiver(self.hello_cb, 'Hello', IFACE,
                    path=PATH, sender_keyword='sender')
            else:
                self._logger.debug('Hello, everyone! What did I miss?')
                self.Hello()
        self.entered = True

    @signal(dbus_interface=IFACE, signature='')
    def Hello(self):
        """Say Hello to whoever else is in the tube."""
        self._logger.debug('I said Hello.')

    @method(dbus_interface=IFACE, in_signature='s', out_signature='')
    def World(self, game_state):
        """To be called on the incoming XO after they Hello."""
        if not self.helloworld:
            self._logger.debug('Somebody said World.')
            self.helloworld = game_state
            # now I can World others
            self.add_hello_handler()
        else:
            self._logger.debug("I've already been welcomed, doing nothing")

    def add_hello_handler(self):
        self._logger.debug('Adding hello handler.')
        self.tube.add_signal_receiver(self.hello_cb, 'Hello', IFACE,
            path=PATH, sender_keyword='sender')

    def hello_cb(self, sender=None):
        """Somebody Helloed me. World them."""
        if sender == self.tube.get_unique_name():
            # sender is my bus name, so ignore my own signal
            return
        self._logger.debug('Newcomer %s has joined', sender)
        self._logger.debug('Welcoming newcomer and sending them the game state')
        game_state = str(time.time())  # Something to send for demo
        self.tube.get_object(sender, PATH).World(game_state,
                                                 dbus_interface=IFACE)
		
#	@dbus.service.method("com.ywwg.NewsReaderLite.AppInterface")
#	def GetDatabaseName(self):
#		return self._app.get_database_name()
#
#	@dbus.service.method("com.ywwg.NewsReaderLite.AppInterface")
#	def AddFeed(self, url):
#		if utils.RUNNING_SUGAR:
#			self.sugar_add_button.popup()
#		else:
#			self._app.window_add_feed.show(False)
#		self._app.window_add_feed.set_location(url)
#
#	@dbus.service.method("com.ywwg.NewsReaderLite.AppInterface")
#	def ImportOpml(self, filename):
#		try:
#			f = open(filename)
#			self._app.import_subscriptions(f)
#		except e:
#			print "Error importing subscriptions:", e
#		return
