#!/usr/bin/env python
#a basic gstreamer-based player.  Can run standalone or inside the widget of your choice

import pygst
pygst.require("0.10")
import gst

import pygtk
pygtk.require("2.0")
import gtk
import gobject

import ptvDB
import utils

import os.path

class GStreamerPlayer:
	def __init__(self, db, layout_dock):
		self._db = db	
		self._layout_dock = layout_dock
		self._media_duration = 0
		self._media_position = 0
		self._last_file = -1
		self._current_file = 0 #index to tree model
		
		self.__no_seek = False
		
	def Show(self):
		hpaned = gtk.HPaned()
		vbox = gtk.VBox()
		self._drawing_area = gtk.DrawingArea()
		vbox.pack_start(self._drawing_area)
		
		self._seek_scale = gtk.HScale()
		self._seek_scale.set_range(0,1)
		self._seek_scale.set_draw_value(False)
		self._seek_scale.connect('value-changed', self._on_seek_value_changed)
		vbox.pack_start(self._seek_scale, False)
		
		button_box = gtk.HButtonBox()
		button = gtk.Button(stock='gtk-media-previous')
		button.connect("clicked", self._on_prev_clicked)
		button_box.add(button)
		button = gtk.Button(stock='gtk-media-rewind')
		button.connect("clicked", self._on_rewind_clicked)
		button_box.add(button)
		button = gtk.Button(stock='gtk-media-play')
		button.connect("clicked", self._on_play_clicked)
		button_box.add(button)
		button = gtk.Button(stock='gtk-media-pause')
		button.connect("clicked", self._on_pause_clicked)
		button_box.add(button)
		button = gtk.Button(stock='gtk-media-forward')
		button.connect("clicked", self._on_forward_clicked)
		button_box.add(button)
		button = gtk.Button(stock='gtk-media-next')
		button.connect("clicked", self._on_next_clicked)
		button_box.add(button)
		vbox.pack_start(button_box, False)
		hpaned.add1(vbox)
		
		self._queue_listview = gtk.TreeView()
		model = gtk.ListStore(str, str) #filename, title to display
		self._queue_listview.set_model(model)
		column = gtk.TreeViewColumn(_("Playlist"))
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, markup=1)
		self._queue_listview.append_column(column)
		hpaned.add2(self._queue_listview)
		self._layout_dock.add(hpaned)
		
		#Gstreamer init
		self._pipeline = gst.element_factory_make("playbin", "ptv_bin")
		#use default audio sink, but get our own video sink
		self._v_sink = self._get_video_sink()
		self._pipeline.set_property('video-sink',self._v_sink)
		self.queue_file('file:///home/owen/Documents/videos/Summoner Geeks.wmv')
		#self._pipeline.set_property('uri','file:///home/owen/Documents/videos/Summoner Geeks.wmv')
		
		self._layout_dock.show_all()
		
	def detach(self):
		"""video window can detach.  queue stays embedded"""
		pass
	
	def reattach(self):
		"""hides external window and reinits embedded window"""
		pass
		
	def queue_file(self, filename, name=None):
		if name is None:
			name = os.path.split(filename)[1]
		model = self._queue_listview.get_model()
		model.append([filename, name])
		
	def play(self):
		model = self._queue_listview.get_model()
		filename, title = list(model[self._current_file])
		print filename
		if self._last_file != self._current_file:
			self._pipeline.set_property('uri',filename)
			self._v_sink.set_xwindow_id(self._drawing_area.window.xid)
			self._last_file = self._current_file
		self._pipeline.set_state(gst.STATE_PLAYING)
		self._media_duration = -1
		gobject.timeout_add(1000, self._tick)
		
	def pause(self):
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
		if self._current_file == len(model):
			return
		self._current_file += 1
		self.play()
		
	def prev(self):
		if self._current_file == 0:
			self.seek(0)
		self._current_file -= 1
		self.play()
		
	def finish(self):
		"""pauses, saves state, and cleans up gstreamer"""
		pass
		
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
		
	def _on_seek_value_changed(self, widget):
		if self.__no_seek:
			return
		pos = widget.get_value()
		self.seek(pos)
		
	def _tick(self):
		self.__no_seek = True
		self._update_seek_bar()
		self.__no_seek = False
		return self._pipeline.get_state()[1] == gst.STATE_PLAYING

	def _update_seek_bar(self):
		try:
			self._media_position = self._pipeline.query_position(gst.FORMAT_TIME)[0]
			print self._media_position
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
	#
	#def _get_audio_sink(self):
	#	sinks = ["alsasink","ossink","esdsink"]
	#	if utils.is_kde():
	#		sinks = ["artssink"] + sinks
	#	
	#	for sink_str in sinks:
	#		try:
	#			a_sink = gst.element_factory_make(sink_str, "a_sink")
	#			break
	#		except:
	#			print "couldn't init ",sink_str
	#	print "audio sink:", sink_str
	#	return a_sink
		
def do_quit(self, widget):
	gtk.main_quit()
		
if __name__ == '__main__': # Here starts the dynamic part of the program 
	db = ptvDB.ptvDB()
	
	window = gtk.Window()
	app = GStreamerPlayer(db, window)
	app.Show()
	window.connect('delete-event', do_quit)
	gtk.main()
	
