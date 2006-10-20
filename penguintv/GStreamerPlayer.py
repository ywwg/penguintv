#!/usr/bin/env python
#a basic gstreamer-based player.  Can run standalone or inside the widget of your choice
#much help from the mesk player code, totem, and most of all, google.com/codesearch

import pygst
pygst.require("0.10")
import gst

import pygtk
pygtk.require("2.0")
import gtk 
import gobject

import ptvDB
import utils

import os,os.path
import pickle

class GStreamerPlayer(gobject.GObject):
	def __init__(self, db, layout_dock):
		gobject.GObject.__init__(self)
		self._db = db	
		self._layout_dock = layout_dock
		self._media_duration = 0
		self._media_position = 0
		self._last_file = -1
		self._current_file = 0 #index to tree model
		self._fullscreen = False
		self.__no_seek = False
		
		gobject.signal_new('item-queued', GStreamerPlayer, gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, [])
		gobject.signal_new('items-removed', GStreamerPlayer, gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, [])
		
	def Show(self):
		self._external_window = gtk.Window()
		self._drawing_area_fullscreen = gtk.DrawingArea()
		color = gtk.gdk.Color(0,0,0)
		self._drawing_area_fullscreen.modify_bg(gtk.STATE_NORMAL, color)
		self._external_window.add(self._drawing_area_fullscreen)
		self._external_window.connect('key-press-event', self._on_key_press_event)
	
		hpaned = gtk.HPaned()
		self._video_container = gtk.VBox()
		self._drawing_area = gtk.DrawingArea()
		color = gtk.gdk.Color(0,0,0)
		self._drawing_area.modify_bg(gtk.STATE_NORMAL, color)
		self._video_container.pack_start(self._drawing_area)
		
		self._seek_scale = gtk.HScale()
		self._seek_scale.set_range(0,1)
		self._seek_scale.set_draw_value(False)
		self._seek_scale.connect('value-changed', self._on_seek_value_changed)
		self._video_container.pack_start(self._seek_scale, False)
		
		button_box = gtk.HButtonBox()
		button_box.set_property('layout-style', gtk.BUTTONBOX_START)
		
		image = gtk.Image()
		image.set_from_stock("gtk-media-previous",gtk.ICON_SIZE_BUTTON)
		button = gtk.Button("")
		button.set_image(image)
		button.connect("clicked", self._on_prev_clicked)
		button_box.add(button)
		
		image = gtk.Image()
		image.set_from_stock("gtk-media-rewind",gtk.ICON_SIZE_BUTTON)
		button = gtk.Button("")
		button.set_image(image)
		button.connect("clicked", self._on_rewind_clicked)
		button_box.add(button)
		
		image = gtk.Image()
		image.set_from_stock("gtk-media-play",gtk.ICON_SIZE_BUTTON)
		button = gtk.Button("")
		button.set_image(image)
		button.connect("clicked", self._on_play_clicked)
		button_box.add(button)
		
		image = gtk.Image()
		image.set_from_stock("gtk-media-pause",gtk.ICON_SIZE_BUTTON)
		button = gtk.Button("")
		button.set_image(image)
		button.connect("clicked", self._on_pause_clicked)
		button_box.add(button)
		
		image = gtk.Image()
		image.set_from_stock("gtk-media-forward",gtk.ICON_SIZE_BUTTON)
		button = gtk.Button("")
		button.set_image(image)
		button.connect("clicked", self._on_forward_clicked)
		button_box.add(button)
		
		image = gtk.Image()
		image.set_from_stock("gtk-media-next",gtk.ICON_SIZE_BUTTON)
		button = gtk.Button("")
		button.set_image(image)
		button.connect("clicked", self._on_next_clicked)
		button_box.add(button)
		
		self._video_container.pack_start(button_box, False)
		hpaned.add1(self._video_container)
		
		vbox = gtk.VBox()
		s_w = gtk.ScrolledWindow()
		s_w.set_shadow_type(gtk.SHADOW_IN)
		s_w.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		self._queue_listview = gtk.TreeView()
		model = gtk.ListStore(str, str) #filename, title to display
		self._queue_listview.set_model(model)
		column = gtk.TreeViewColumn(_("Playlist"))
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, markup=1)
		self._queue_listview.append_column(column)
		self._queue_listview.connect('row-activated', self._on_queue_row_activated)
		self._queue_listview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		s_w.add(self._queue_listview)
		vbox.pack_start(s_w, True)
		button_box = gtk.HButtonBox()
		button_box.set_property('layout-style', gtk.BUTTONBOX_END)
		button = gtk.Button(stock='gtk-remove')
		button.connect("clicked", self._on_remove_clicked)
		button_box.add(button)
		vbox.pack_start(button_box, False)
		
		hpaned.add2(vbox)
		self._layout_dock.add(hpaned)
		
		#Gstreamer init
		self._pipeline = gst.element_factory_make("playbin", "ptv_bin")
		#use default audio sink, but get our own video sink
		self._v_sink = self._get_video_sink()
		self._pipeline.set_property('video-sink',self._v_sink)
		bus = self._pipeline.get_bus()
		bus.add_signal_watch()
		bus.connect('message', self._on_gst_message)

		self._layout_dock.show_all()
		self._external_window.hide_all()
		self._load()
		
	def detach(self):
		"""video window can detach.  queue stays embedded"""
		pass
	
	def reattach(self):
		"""hides external window and reinits embedded window"""
		pass
		
	def toggle_fullscreen(self):
		if self._fullscreen:
			self._fullscreen = False
			self._external_window.window.unfullscreen()
			self._external_window.hide_all()
			self._v_sink.set_xwindow_id(self._drawing_area.window.xid)
		else:
			self._fullscreen = True
			self._external_window.show_all()
			self._external_window.window.fullscreen()
			self._v_sink.set_xwindow_id(self._drawing_area_fullscreen.window.xid)
		
	def queue_file(self, filename, name=None):
		if name is None:
			name = os.path.split(filename)[1]
		model = self._queue_listview.get_model()
		model.append([filename, name])
		self.emit('item-queued')
		
	def get_queue_count(self):
		return len(self._queue_listview.get_model())
		
	def play(self):
		model = self._queue_listview.get_model()
		if len(model) == 0:
			return
		filename, title = list(model[self._current_file])
		if self._last_file != self._current_file:
			if self._pipeline.get_state()[1] == gst.STATE_PLAYING:
				self._pipeline.set_state(gst.STATE_READY)
			print "setting uri for playback:",filename
			self._pipeline.set_property('uri',filename)
			self._last_file = self._current_file
			
		if self._fullscreen:
			self._v_sink.set_xwindow_id(self._drawing_area_fullscreen.window.xid)
		else:
			self._v_sink.set_xwindow_id(self._drawing_area.window.xid)
		self._v_sink.set_property('force-aspect-ratio', True)
		self._pipeline.set_state(gst.STATE_PLAYING)
		self._media_duration = -1
		gobject.timeout_add(1000, self._tick)
		
	def pause(self):
		try: self._media_position = self._pipeline.query_position(gst.FORMAT_TIME)[0]
		except: pass
		self._pipeline.set_state(gst.STATE_PAUSED)
		
	def stop(self):
		try: self._media_position = self._pipeline.query_position(gst.FORMAT_TIME)[0]
		except: pass
		self._pipeline.set_state(gst.STATE_READY)
		
	def ff(self):
		new_pos = self._media_position+15000000000L #15 seconds I think
		if new_pos > self._media_duration:
			new_pos = self._media_duration
		self.seek(new_pos)
		
	def rew(self):
		new_pos = self._media_position-15000000000L #15 seconds I think
		if new_pos < 0:
			new_pos = 0
		self.seek(new_pos)
		
	def next(self):
		model = self._queue_listview.get_model()
		if self._current_file >= len(model):
			return
		self._pipeline.set_state(gst.STATE_READY)
		self._current_file += 1
		self.play()
		
	def prev(self):
		self._pipeline.set_state(gst.STATE_READY)
		if self._current_file <= 0:
			self._current_file = 0
			self.seek(0)
		self._current_file -= 1
		self.play()
		
	def finish(self):
		self._save()
		
	def seek(self, time):
		self._pipeline.seek(1.0, gst.FORMAT_TIME,
							gst.SEEK_FLAG_FLUSH | gst.SEEK_FLAG_ACCURATE,
							gst.SEEK_TYPE_SET, time,
							gst.SEEK_TYPE_NONE, 0)
		
	def _on_play_clicked(self, b): self.play()
		
	def _on_pause_clicked(self, b): self.pause()
		
	def _on_rewind_clicked(self, b): self.rew()
		
	def _on_forward_clicked(self, b): self.ff()
	
	def _on_next_clicked(self, b): self.next()
	
	def _on_prev_clicked(self, b): self.prev()
	
	def _on_remove_clicked(self, b):
		model, paths = self._queue_listview.get_selection().get_selected_rows()
		iter_list = []
		for path in paths:
			if path[0] == self._current_file:
				self._current_file+=1
			iter_list.append(model.get_iter(path))
			
		for i in iter_list:
			model.remove(i)
			
		if self._current_file >= len(model):
			self._current_file = len(model) - 1
			self.stop()
		self.emit('items-removed')
		
	def _on_seek_value_changed(self, widget):
		if self.__no_seek:
			return
		pos = widget.get_value()
		self.seek(pos)
		
	def _on_queue_row_activated(self, treeview, path, view_column):
		self._current_file = path[0]
		self.play()
		
	def _on_key_press_event(self, widget, event):
		keyname = gtk.gdk.keyval_name(event.keyval)
		if keyname == 'f':
			self.toggle_fullscreen()
		
	def _tick(self):
		self.__no_seek = True
		self._update_seek_bar()
		self.__no_seek = False
		return self._pipeline.get_state()[1] == gst.STATE_PLAYING

	def _update_seek_bar(self):
		try:
			self._media_position = self._pipeline.query_position(gst.FORMAT_TIME)[0]
			#print self._media_position
			if self._media_position > self._media_duration:
				self._media_duration = self._pipeline.query_duration(gst.FORMAT_TIME)[0]
				self._seek_scale.set_range(0,self._media_duration)
			self._seek_scale.set_value(self._media_position)
		except Exception, e:
			print e
		
	def _get_video_sink(self):
		sinks = ["xvimagesink","glimagesink","sdlimagesink","ximagesink"]
		for sink_str in sinks:
			try:
				v_sink = gst.element_factory_make(sink_str, "v_sink")
				break
			except:
				print "couldn't init ",sink_str
		print "video sink:", sink_str
		return v_sink
		
	def _on_gst_message(self, bus, message):
		#if message.type == gst.MESSAGE_STATE_CHANGED:
		#	oldstate, newstate, pending = message.parse_state_changed()
		#	if newstate == gst.STATE_PLAYING and self._prepare_seek >= 0:
		#		self.seek(self._prepare_seek)
		if message.type == gst.MESSAGE_EOS:
			self.next()
		#elif message.type == gst.MESSAGE_TAG:
		#    if not self._current_audio_src.meta_data.frozen:
		#        self._update_meta_data(self._current_audio_src,
		#                               message.parse_tag())
		elif message.type == gst.MESSAGE_ERROR:
			print str(message)
			
	def _load(self):
		home = os.path.join(os.getenv('HOME'), '.penguintv')
		try:
			playlist = open(os.path.join(home, 'gst_playlist.pickle'), 'r')
		except:
			print "error reading playlist"
			return
			
		self._current_file = pickle.load(playlist)
		self._media_position = pickle.load(playlist)
		self._media_duration= pickle.load(playlist)
		l = pickle.load(playlist)
		model = self._queue_listview.get_model()
		for filename, name in l:
			model.append([filename, name])
			self.emit('item-queued')
		self._seek_scale.set_range(0,self._media_duration)
		self._seek_scale.set_value(self._media_position)
		self.seek(self._media_position)
		self.pause()
		playlist.close()
			
	def _save(self):
		"""pauses, saves state, and cleans up gstreamer"""
		home = os.path.join(os.getenv('HOME'), '.penguintv')
		try:
			playlist = open(os.path.join(home, 'gst_playlist.pickle'), 'w')
		except:
			print "error writing playlist"
			return
			
		pickle.dump(self._current_file, playlist)
		pickle.dump(self._media_position, playlist)
		pickle.dump(self._media_duration, playlist)
		l = []
		for filename, name in self._queue_listview.get_model():
			l.append([filename,name])
		pickle.dump(l, playlist)
		playlist.close()
	
		
def do_quit(self, widget):
	gtk.main_quit()
	
def items_removed(player):
	print "items removed"
	print player.get_queue_count()
	
def on_app_key_press_event(widget, event, player):
	keyname = gtk.gdk.keyval_name(event.keyval)
	if keyname == 'f':
		player.toggle_fullscreen()
		
if __name__ == '__main__': # Here starts the dynamic part of the program 
	db = ptvDB.ptvDB()
	
	window = gtk.Window()
	app = GStreamerPlayer(db, window)
	app.Show()
	window.connect('delete-event', do_quit)
	window.connect('key-press-event', on_app_key_press_event, app)
	app.connect('items-removed', items_removed)
	app.queue_file('file:///home/owen/Documents/videos/Summoner Geeks.wmv') 
	app.queue_file('file:///home/owen/Documents/videos/What do I do now.AVI')
	gtk.main()
	
