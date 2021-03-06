#!/usr/bin/python

#runs standalone, or can be accessed as a class for use in penguintv

import os,os.path,sys
import string
import glob

import os.path
import shutil
import getopt

import utils

try:
	import penguintv
	import ptvDB
except:
	sys.path.insert(0, find_penguintv_lib()) #this will bomb if necessry
	import penguintv
	import ptvDB

class ptv_sync:
	def __init__(self,dest_dir, delete=False, move=False, audio=False, dryrun=False):
		self.dest_dir = dest_dir
		self.audio = audio
		self.delete = delete
		self.move = move
		self.dryrun = dryrun
		self.cancel = False
		
	def interrupt(self):
		self.cancel = True
	
	def sync_gen(self):
		"""generator yields cur item number, total, and message.  If total is -1, unmeasured progress"""
		db = ptvDB.ptvDB()
		feedlist = db.get_feedlist()
		locallist = []
	
		for feed in feedlist:
			if self.cancel:
				break
			entrylist = db.get_entrylist(feed[0])
			for entry in entrylist:
				if self.cancel:
					break
				medialist = db.get_entry_media(entry[0])
				if medialist:
					for medium in medialist:
						yield (0,-1,_("Building file list..."), None)
						if medium['file']:
							if self.audio == True:
								if medium['file'].rsplit(".",1)[-1].upper() not in ("MP3","OGG","FLAC","WMA","M4A"):
									continue
							try:
								source_size = os.stat(medium['file'])[6]
							except:
								continue
							locallist.append([feed[1],medium['file'],source_size, medium['media_id']])
					
		if not self.move:
			db._c.close() #ug
			db._db.close() #yuck
		
		if self.delete:
			for root,dirs,files in os.walk(self.dest_dir):
				if self.cancel: break
				i=-1
				for f in files:
					if self.cancel: break
					i+=1
					if f not in [os.path.split(l[1])[1] for l in locallist]:
						d = {'filename': os.path.join(str(root),str(f))}
						yield (0,-1,_("Removing %(filename)s") % d, None)
						if self.dryrun==False:
							os.remove(os.path.join(str(root),str(f)))
							
		i=-1
		for f in locallist:
			i+=1
			if self.cancel: break
			filename = os.path.split(f[1])[1]
			sub_dir = os.path.join(self.dest_dir,f[0])
			sub_dir = sub_dir.replace(":","_")
			if self.dryrun==False:
				try:
					os.mkdir(sub_dir)
				except OSError,e:
					if e.errno == 17:
						pass
					else:
						print "couldn't create dir:"+str(sub_dir)
						continue
			try:
				dest_size = os.stat(os.path.join(sub_dir,filename))[6]
				if f[2] == dest_size:
					yield (i, len(locallist), _("%(filename)s already exists") % d, f[3])
					continue
			except:
				pass
			d = {'filename': filename}
			yield (i, len(locallist), _("Copying %(filename)s") % d, f[3])
			if self.dryrun==False:
				shutil.copyfile(f[1], os.path.join(sub_dir,filename))

		if self.move:
			db._c.close() #ug
			db._db.close() #yuck
				
		if self.delete and not self.cancel:
			for root,dirs,files in os.walk(self.dest_dir):
				for d in dirs:
					globlist = glob.glob(os.path.join(self.dest_dir,d,"*"))
					if len(globlist)==0: #empty dir
						yield (0, -1, _("Removing empty folders..."), None)
						if not self.dryrun:
							utils.deltree(os.path.join(self.dest_dir,d))
				
		if self.cancel:
			yield (100,100,_("Synchronization cancelled"), None)
		else:
			yield (100,100,_("Copying Complete"), None)

def find_penguintv_lib():
    if os.environ.has_key("PENGUINTV_LIB"):
        return os.environ["PENGUINTV_LIB"]
    for d in sys.path:
        sd = os.path.join(d, 'penguintv')
        if os.path.isdir(sd):
            return sd
    print sys.argv[0]
    h, t = os.path.split(os.path.split(os.path.abspath(sys.argv[0]))[0])
    if t == 'bin':
        libdir = os.path.join(h, 'lib')
        fp = os.path.join(libdir, 'penguintv')
        if os.path.isdir(fp):
            return libdir
    raise "FileNotFoundError", "couldn't find penguintv library dir"

if __name__ == '__main__': # Here starts the dynamic part of the program 
	dest_dir = ""
	delete = False
	dryrun = False
	audio = False
	move = False
	opts, args = getopt.getopt(sys.argv[1:], "andmp:","path=")
	for o, a in opts:
		if o == "-d":
			delete = True
		elif o == "-m":
			move = True
		elif o == "-n":
			print "Dry Run"
			dryrun = True
		elif o in ("-p", "--path"):
			dest_dir = a
		elif o == "-a":
			audio = True
			
	if dest_dir=="":
		print """
	ptv_sync.py (-n) (-d) (-m) -p [destination]:

	Synchronizes a penguintv media directory with another directory.  It
	doesn't just copy the files, however, it builds a different directory
	tree based on the feed name instead of the date of download.

	Options:

	-p or --path=          Set the destination folder.  This option must
	                       be set.

	-d                     Use to delete files on the remote end that don't
	                       exist in the penguintv media directory

	-m                     Move, don't copy.  Deletes media from the penguintv
	                       database after copy is complete.	                       
	                       
	-n                     Dry run.  Demonstrates what would happen, but
	                       doesn't perform any copy or delete actions.
	                       
	-a                     Audio mode.  Copy only audio files"""
	                       
		sys.exit(1)

	s = ptv_sync(dest_dir, delete, move, audio, dryrun)
	last_message = ""
	for item in s.sync_gen():
		if item[2] != last_message:
			print item[2]
		last_message = item[2]
