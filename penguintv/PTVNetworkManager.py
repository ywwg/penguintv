# A simple class to listen to networkmanager (both old and new APIs)
# and send out a signal when we go offline or online

import gobject
import dbus
import logging

#this is really just for reference
#thanks to http://code.google.com/p/specto/issues/attachmentText?id=327&aid=7834456851323426811&name=specto-0.3.1-networkmanager.patch&token=v9SrlyZyIuoHDQ-k3eOZqT-hdoc%3A1327327453434
nm_statustable = {0:  u'Unknown',
                     10: u'Asleep',
                     20: u'Disconnected',
                     30: u'Disconnecting',
                     40: u'Connecting',
                     50: u'Local connectivity',
                     60: u'Site connectivity',
                     70: u'Global connectivity'}

class PTVNetworkManager(gobject.GObject):
    __gsignals__ = {
        'connection-status': (gobject.SIGNAL_RUN_FIRST, 
                         gobject.TYPE_NONE, 
                         ([gobject.TYPE_BOOLEAN])),
    }

    def __init__(self):
        gobject.GObject.__init__(self)
        sys_bus = dbus.SystemBus()
        #let exceptions bubble up
        sys_bus.add_signal_receiver(self._properties_changed,
									'PropertiesChanged',
									'org.freedesktop.NetworkManager',
									'org.freedesktop.NetworkManager',
									'/org/freedesktop/NetworkManager')
								
        nm_ob = sys_bus.get_object("org.freedesktop.NetworkManager", 
								   "/org/freedesktop/NetworkManager")
								   
        self._nm_interface = dbus.Interface(nm_ob, 
									  "org.freedesktop.DBus.Properties")
        logging.info("Listening to NetworkManager")

    def get_connection_state(self):
        try:
            state_val = int(self._nm_interface.Get("org.freedesktop.NetworkManager","State"))
        except:
            logging.warning("Error getting network device state")
            return False
            
        if self._nm_interface.Get("org.freedesktop.NetworkManager", "Version") > "0.8.9":
            return state_val == 70
        else:
            return state_val == 3

    def _properties_changed(self, *args):
        connected = self.get_connection_state()
        self.emit('connection-status', connected)
