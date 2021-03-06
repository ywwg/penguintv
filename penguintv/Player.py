# Written by Owen Williams
# see LICENSE for license information

import subProcess
import utils
import os, os.path
import urllib
import logging
from types import *
from MainWindow import N_PLAYER
import gobject

class Player:
	def __init__(self, app, gst_player=None):
		self._app = app
		self._gst_player = gst_player
		self.cmdline = 'totem --enqueue'
		if utils.RUNNING_SUGAR:
			import sugar.env
			home = os.path.join(sugar.env.get_profile_path(), 'penguintv')
		else:
			home = os.path.join(os.getenv('HOME'), ".penguintv")
		try:
			os.stat(os.path.join(home, 'media'))
		except:
			try:
				os.mkdir(os.path.join(home, 'media'))
			except:
				raise NoDir, "error creating " +os.path.join(home,'/media')
		self.media_dir = os.path.join(home, 'media')
		try:
			playlist = open(os.path.join(self.media_dir,"recovery_playlist.m3u") , "w")
			playlist.write("#EXTM3U\n")
			playlist.close()
		except:
			print "Warning: couldn't append to playlist file", os.path.join(self.media_dir,"recovery_playlist.m3u")
		pass
	
	def using_internal_player(self):
		return self._gst_player != None	
		
	def internal_player_exposed(self):
		return self._gst_player.is_exposed()
		
	def connect_internal(self, signal, func):
		assert self.using_internal_player()
		self._gst_player.connect(signal, func)
		
	def control_internal(self, action):
		assert self.using_internal_player()
		
		def _expose_check_generator(q_action):
			"""Wait for player to become exposed, then play"""
			for i in range(0,10):
				if self.internal_player_exposed():
					self.control_internal(q_action)
					yield True
					break
				yield False
			yield False

		if self.using_internal_player():
			if not self.internal_player_exposed():
				self._app.main_window.notebook_select_page(N_PLAYER)
				gobject.timeout_add(200, _expose_check_generator(action).next)
				return
		
		if action.lower() == "play":
			self._gst_player.play()
		elif action.lower() == "pause":
			self._gst_player.pause()
		elif action.lower() == "next":
			self._gst_player.next()
		elif action.lower() in ("prev", "previous"):
			self._gst_player.prev()
		elif action.lower() == "playpause":
			self._gst_player.play_pause_toggle()
		elif action.lower() == "stop":
			self._gst_player.stop()
		else:
			print "unhandled action:",action
		
	def get_queue(self):
		assert self.using_internal_player()
		return self._gst_player.get_queue()
		
	def unqueue(self, userdata):
		if self.using_internal_player():
			self._gst_player.unqueue(userdata=userdata)
		
	def play(self, f, title=None, userdata=None, force_external=False, context=None):
		self.play_list([[f,title,userdata]], force_external, context)
	
	def play_list(self, files, force_external = False, context=None):
		cmdline = self.cmdline
		try:
			playlist = open(os.path.join(self.media_dir,"recovery_playlist.m3u") , "a")
			playlist.write("#"*20+"\n")
		except Exception,e:
			print "Warning: couldn't append to playlist file, ", str(e), os.path.join(self.media_dir,"recovery_playlist.m3u")
			return
			
		players={}

		for f,t,u in files:
			if os.path.isdir(f):
				for root,dirs,filelist in os.walk(f):
					for filen in filelist:
						next = os.path.join(f, filen)
						if os.path.isfile(next) and utils.is_known_media(filen):
							head,filename = os.path.split(next)
							dated_dir = os.path.split(head)[1]
							playlist.write(os.path.join(dated_dir, filename)+"\n")
							
							player = utils.get_play_command_for(filen)
							if players.has_key(player):
								players[player].append(filen)
							else:
								players[player]=[filen]
							
			elif os.path.isfile(f):
				head,filename = os.path.split(f)
				dated_dir = os.path.split(head)[1]
				playlist.write(os.path.join(dated_dir,filename)+"\n")
				player = utils.get_play_command_for(f)
				if players.has_key(player):
					players[player].append(f)
				else:
					players[player]=[f]
		playlist.close()
		
		if self._gst_player is not None and not force_external:
			for f,t,u in files:
				self._gst_player.queue_file(f,name=t,userdata=u)
		else:
			if utils.RUNNING_HILDON:
				import osso.rpc
				rpc_handler = osso.rpc.Rpc(context)
				for filename,t,u in files:
					uri = str("file://" + filename)
					logging.debug("Trying to launch media player: %s" % uri)
					rpc_handler.rpc_run_with_defaults('mediaplayer', 'mime_open', (uri,))
			else:
				for player in players.keys():
					cmdline=player+" "
					for filename in players[player]:
						cmdline += '"%s" ' % filename
					cmdline+="&"
					# logging.debug("running: "+str(cmdline))
					subProcess.subProcess(cmdline)
			
class NoDir(Exception):
	def __init__(self,durr):
		self.durr = durr
	def __str__(self):
		return "no such directory: "+self.durr
