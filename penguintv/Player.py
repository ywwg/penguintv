# Written by Owen Williams
# see LICENSE for license information

import subProcess
import utils
import os
import urllib
from types import *

class Player:
	def __init__(self, gst_player=None):
		self._gst_player = gst_player
		self.cmdline = 'totem --enqueue'
		try:
			home=os.getenv('HOME')
			os.stat(home+'/.penguintv/media')
		except:
			try:
				os.mkdir(home+'/.penguintv/media')
			except:
				raise NoDir, "error creating " +home+'/.penguintv/media'
		self.media_dir = home+'/.penguintv/media'
		try:
			playlist = open(self.media_dir+"/recovery_playlist.m3u" , "w")
			playlist.write("#EXTM3U\n")
			playlist.close()
		except:
			print "Warning: couldn't append to playlist file"			
		pass
	
	def using_internal_player(self):
		return self._gst_player != None	
		
	def play(self, f, title=None, force_external=False):
		self.play_list([[f,title]], force_external)
	
	def play_list(self, files, force_external = False):
		cmdline = self.cmdline
		try:
			playlist = open(self.media_dir+"/recovery_playlist.m3u" , "a")
			playlist.write("#"*20+"\n")
		except:
			print "Warning: couldn't append to playlist file"
			
		players={}

		for f,t in files:
			if os.path.isdir(f):
				for root,dirs,filelist in os.walk(f):
					for filen in filelist:
						next = os.path.join(f, filen)
						if os.path.isfile(next) and utils.is_known_media(filen):
							head,filename = os.path.split(next)
							dated_dir = os.path.split(head)[1]
							playlist.write(dated_dir+"/"+filename+"\n")
							
							player = utils.get_play_command_for(filen)
							if players.has_key(player):
								players[player].append(filen)
							else:
								players[player]=[filen]
							
			elif os.path.isfile(f):
				head,filename = os.path.split(f)
				dated_dir = os.path.split(head)[1]
				playlist.write(dated_dir+"/"+filename+"\n")
				player = utils.get_play_command_for(f)
				if players.has_key(player):
					players[player].append(f)
				else:
					players[player]=[f]
		playlist.close()
		
		if self._gst_player is not None and not force_external:
			for f,t in files:
				self._gst_player.queue_file(f,t)
		else:
			for player in players.keys():
				cmdline=player+" "
				for filename in players[player]:
					cmdline+=filename+" "
				cmdline+="&"
				#print "running: "+str(cmdline)
				subProcess.subProcess(cmdline)
			
class NoDir(Exception):
	def __init__(self,durr):
		self.durr = durr
	def __str__(self):
		return "no such directory: "+self.durr
