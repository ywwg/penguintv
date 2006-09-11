# Written by Owen Williams
# see LICENSE for license information

from pysqlite2 import dbapi2 as sqlite
from math import floor,ceil
import pysqlite2
import feedparser
import OPML
import time
import string
import sha
import urllib, urllib2
from types import *
import threading
import ThreadPool
import sys, os, re, traceback, shutil
import glob
import locale
import gettext
import sets
import pickle

import Lucene

import timeoutsocket
import smtplib
timeoutsocket.setDefaultSocketTimeout(30)

locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

import utils


NEW = 0
EXISTS = 1
MODIFIED = 2
DELETED = 3

MAX_ARTICLES = 1000

_common_unicode = { u'\u0093':u'"', u'\u0091': u"'", u'\u0092': u"'", u'\u0094':u'"', u'\u0085':u'...'}

#Possible entry flags
F_ERROR       = 64
F_DOWNLOADING = 32   
F_UNVIEWED    = 16
F_DOWNLOADED  = 8
F_NEW         = 4
F_PAUSED      = 2
F_MEDIA       = 1

#arguments for poller
A_ERROR_FEEDS    = 32
A_DO_REINDEX     = 16
A_ALL_FEEDS      = 8
A_AUTOTUNE       = 4
A_IGNORE_ETAG    = 2
A_DELETE_ENTRIES = 1 

#download statuses
D_NOT_DOWNLOADED = 0
D_DOWNLOADING    = 1
D_DOWNLOADED     = 2
D_RESUMABLE      = 3
D_ERROR          = -1
D_WARNING        = -2

#tag types
T_ALL     = 0
T_TAG     = 1
T_SEARCH  = 2
T_BUILTIN = 3

NOAUTODOWNLOAD="noautodownload"
NOSEARCH="nosearch"

DB_FILE="penguintv3.db"

from HTMLParser import HTMLParser
from formatter import NullFormatter

class ptvDB:
	entry_flag_cache = {}
	
	def __init__(self, polling_callback=None):#,username,password):	
		try:
			self.home=os.getenv('HOME')
			os.stat(self.home+"/.penguintv")
		except:
			try:
				os.mkdir(self.home+"/.penguintv")
			except:
				raise DBError, "error creating directories: "+self.home+"/.penguintv"
		try:	
			#also change db connection in pool poll
			if os.path.isfile(self.home+"/.penguintv/penguintv3.db") == False:
				if os.path.isfile(self.home+"/.penguintv/penguintv2.db"):
					try: 
						shutil.copyfile(self.home+"/.penguintv/penguintv2.db", self.home+"/.penguintv/penguintv3.db")
					except:
						raise DBError,"couldn't create new database file"
				elif os.path.isfile(self.home+"/.penguintv/penguintv.db"):
					try: 
						shutil.copyfile(self.home+"/.penguintv/penguintv.db", self.home+"/.penguintv/penguintv3.db")
					except:
						raise DBError,"couldn't create new database file"
			self.db=sqlite.connect(self.home+"/.penguintv/penguintv3.db", timeout=10	)
			self.db.isolation_level="DEFERRED"
		except:
			raise DBError,"error connecting to database"
		
		self.c = self.db.cursor()
		self.cache_dirty = True
		try:
			self.c.execute(u'SELECT value FROM settings WHERE data="feed_cache_dirty"')
			if self.c.fetchone()[0] == 0:
				self.cache_dirty = False
		except:
			pass
			
		self.exiting = False
		self.cancel_poll_multiple = False
			
		if polling_callback==None:
			self.polling_callback=self._polling_callback
		else:
			self.polling_callback = polling_callback		
			
		self.searcher = Lucene.Lucene()
		self.blacklist = self.get_feeds_for_tag(NOSEARCH)
		self.reindex_entry_list = []
		self.reindex_feed_list = []
		self.filtered_entries = {}
		self._parse_list = []
				
	def __del__(self):
		self.finish()
		
	def finish(self):
		self.exiting=True
		#self.c.close() finish gets called out of thread so this is bad
		#self.db.close()

	def maybe_initialize_db(self):
		try:
			self.c.execute(u'SELECT * FROM feeds')
		except:
			self.init_database()
			return True	
			
		try:
			self.c.execute(u'SELECT value FROM settings WHERE data="db_ver"')
			db_ver = self.c.fetchone()
			db_ver = db_ver[0]
			#print "current database version is",db_ver
			if db_ver is None:
				self.migrate_database_one_two()
				self.migrate_database_two_three()
				self.migrate_database_three_four()
				self.clean_database_media()
			elif db_ver < 2:
				self.migrate_database_one_two()
				self.migrate_database_two_three()
				self.migrate_database_three_four()
				self.clean_database_media()
			elif db_ver < 3:
				self.migrate_database_two_three()
				self.migrate_database_three_four()
				self.clean_database_media()
			elif db_ver < 4:
				self.migrate_database_three_four()
				self.clean_database_media()
			elif db_ver > 4:
				print "WARNING: This database comes from a later version of PenguinTV and may not work with this version"
				raise DBError, "db_ver is "+str(db_ver)+" instead of 4"
		except Exception, e:
			print "exception:",e
			self.migrate_database_one_two()
			self.migrate_database_two_three()
			#self.migrate_database_three_four()
			
		if self.searcher.needs_index:
			print "indexing for the first time"
			self.searcher.Do_Index_Threaded()
			
		self.fix_tags()
		return False
			
	def migrate_database_one_two(self):
		#add table settings
		print "upgrading to database schema 2"
		try:
			self.c.execute(u'SELECT * FROM settings')  #if it doesn't exist, 
		except:                                        #we create it
			self.c.execute(u"""CREATE TABLE settings   
(
	id INTEGER PRIMARY KEY,
    data NOT NULL,
	value
	);""")
	
		self.c.execute(u"""CREATE TABLE tags
		(
		id INTEGER PRIMARY KEY,
		tag,
		feed_id INT UNSIGNED NOT NULL);""")
		
		
		#add fake_date column
		try:
			self.c.execute(u'ALTER TABLE entries ADD COLUMN fakedate DATE')
			self.c.execute(u'UPDATE entries SET fakedate = date')
		except pysqlite2.dbapi2.OperationalError,e:
			if e != "duplicate column name: fakedate":
				print e #else pass
			#change db_ver (last thing)
		self.c.execute(u'ALTER TABLE feeds ADD COLUMN pollfreq INT')
		self.c.execute(u'UPDATE feeds SET pollfreq=1800')
		self.c.execute(u'ALTER TABLE feeds ADD COLUMN lastpoll DATE')
		self.c.execute(u'UPDATE feeds SET lastpoll=?',(time.time()-(30*60),))
		self.c.execute(u'ALTER TABLE feeds ADD COLUMN newatlast INT')
		self.c.execute(u'UPDATE feeds SET newatlast=0')
   
		try:
			self.c.execute(u'INSERT INTO settings (data, value) VALUES ("db_ver",2)')
		except:
			pass
		try:
			self.c.execute(u'UPDATE settings SET value=2 WHERE data="db_ver"')
		except:
			pass
		self.db.commit()
			
	def migrate_database_two_three(self):
		"""version 3 added flag cache, entry_count_cache, and unread_count_cache"""
		print "upgrading to database schema 3"
		self.c.execute(u'ALTER TABLE feeds ADD COLUMN flag_cache INT')
		self.c.execute(u'ALTER TABLE feeds ADD COLUMN entry_count_cache INT')
		self.c.execute(u'ALTER TABLE feeds ADD COLUMN unread_count_cache INT')
		
		self.c.execute(u'UPDATE settings SET value=3 WHERE data="db_ver"')
		self.c.execute(u'INSERT INTO settings (data, value) VALUES ("feed_cache_dirty",1)')
		self.db.commit()
		
	def migrate_database_three_four(self):
		"""version 4 adds fulltext table"""
		print "upgrading to database schema 4"
		self.c.execute(u'ALTER TABLE tags ADD COLUMN type INT')
		self.c.execute(u'ALTER TABLE tags ADD COLUMN query')
		self.c.execute(u'UPDATE tags SET type=?',(T_TAG,)) #they must all be regular tags right now
		self.c.execute(u'UPDATE settings SET value=4 WHERE data="db_ver"')
		self.c.execute(u'ALTER TABLE feeds ADD COLUMN feed_pointer INT')
		self.c.execute(u'ALTER TABLE feeds ADD COLUMN link')
		self.c.execute(u'UPDATE feeds SET feed_pointer=-1') #no filters yet!
		self.c.execute(u'UPDATE feeds SET link=""')
		self.c.execute(u"""CREATE TABLE terms
							(
							id INTEGER PRIMARY KEY,
							term,
							frequency INT);""")
		self.c.execute(u'INSERT INTO settings (data, value) VALUES ("frequency_table_update",0)')
		self.db.commit()
		
	def init_database(self):
		try:
			self.c.execute(u'DROP TABLE settings')
		except:
			pass	
			
		try:
			self.c.execute(u'DROP TABLE feeds')
		except:
			pass
			
		try:
			self.c.execute(u'DROP TABLE entries')
		except:
			pass
			
		try:
			self.c.execute(u'DROP TABLE media')
		except:
			pass
			
		try:
			self.c.execute(u'DROP TABLE fulltext')
		except:
			pass
			
		self.c.execute(u"""CREATE TABLE settings
							(
								id INTEGER PRIMARY KEY,
							    data NOT NULL,
								value
								);""")

		#for pointer / pointed filter feeds, feed_pointer is feed_id, and description is query
		self.c.execute(u"""CREATE TABLE  feeds
							(
							    id INTEGER PRIMARY KEY,
							    url NOT NULL,
							    polled INT NOT NULL,
							    pollfail BOOL NOT NULL,
							    title  ,
							    description  ,
							    link, 
							    modified INT UNSIGNED NOT NULL,
							    etag ,
							    pollfreq INT NOT NULL,
							    lastpoll DATE,
							    newatlast INT,
							    flag_cache INT,
							    entry_count_cache INT,
							    unread_count_cache INT,
							    feed_pointer INT,
							    UNIQUE(url)
							);""")
		self.c.execute(u"""CREATE TABLE entries
							(
							    id INTEGER  PRIMARY KEY,
							        feed_id INT UNSIGNED NOT NULL,
							        title ,
							        creator  ,
							        description,
							        fakedate DATE,
							        date DATE,
							        guid ,
							        link ,
											read BOOL NOT NULL,
							        old BOOL NOT NULL,
							        new BOOL NOT NULL,
							        UNIQUE(id)
							);""")
		self.c.execute(u"""CREATE TABLE  media
							(
								id INTEGER  PRIMARY KEY,
								entry_id INTEGER UNSIGNED NOT NULL,
								url  NOT NULL,
								file ,
								mimetype ,
								download_status NOT NULL,
								viewed BOOL NOT NULL,
								keep BOOL NOT NULL,
								length,
								UNIQUE(id)
							);
							""")
		self.c.execute(u"""CREATE TABLE tags
							(
							id INTEGER PRIMARY KEY,
							tag,
							feed_id INT UNSIGNED NOT NULL,
							query,
							type INT);""")
							
		self.c.execute(u"""CREATE TABLE terms
							(
							id INTEGER PRIMARY KEY,
							term,
							frequency INT""")
							
#		self.c.execute(u"""CREATE TABLE fulltext
#						   (
#						   		id INTEGER PRIMARY KEY,
						   		
							
		self.db.commit()
		
		self.c.execute(u"""INSERT INTO settings (data, value) VALUES ("db_ver",4)""")
		self.c.execute(u'INSERT INTO settings (data, value) VALUES ("frequency_table_update",0)')
		self.db.commit()
		
	def clean_database_media(self):
		self.c.execute("SELECT id,file,entry_id FROM media")
		result = self.c.fetchall()
		for item in result:
			self.c.execute("SELECT title FROM entries WHERE id=?",(item[2],))
			title = self.c.fetchone()
			if title is None: #this entry doesn't exist anymore
				self.c.execute("DELETE FROM media WHERE id=?",(item[0],))
		self.db.commit()
	
	#right now this code doesn't get called.  Maybe we should?
	def clean_file_media(self):
		"""walks the media dir, and deletes anything that doesn't have an entry in the database.
		Also deletes dirs with only a playlist or with nothing"""
		media_dir = self.home+"/.penguintv/media"
		d = os.walk(media_dir)
		for root,dirs,files in d:
			if root!=media_dir:
				for file in files:
					if file != "playlist.m3u":
						self.c.execute(u"SELECT id FROM media WHERE file=?",(root+"/"+file,))
						result = self.c.fetchone()
						if result is None:
							print "deleting "+root+"/"+file
							os.remove(root+"/"+file)
		d = os.walk(media_dir)
		for root,dirs,files in d:
			if root!=media_dir:
				if len(files) == 1:
					if files[0] == "playlist.m3u":
						print "deleting "+root
						utils.deltree(root)
				elif len(files) == 0:
					print "deleting "+root
					utils.deltree(root)
		
	def set_feed_cache(self, cachelist):
		"""Cachelist format:
		   id, flag, unread, total"""
		for cache in cachelist:
			###print cache
			self.c.execute(u'UPDATE feeds SET flag_cache=? WHERE id=?',(cache[1],cache[0]))
			self.c.execute(u'UPDATE feeds SET unread_count_cache=? WHERE id=?',(cache[2],cache[0]))
			self.c.execute(u'UPDATE feeds SET entry_count_cache=? WHERE id=?',(cache[3],cache[0]))
		self.db.commit()
		#and only then...
		self.c.execute(u'UPDATE settings SET value=0 WHERE data="feed_cache_dirty"')
		self.db.commit()
		self.cache_dirty = False
		
	def get_feed_cache(self):
		if self.cache_dirty:
			return None
		self.c.execute(u'SELECT id, flag_cache, unread_count_cache, entry_count_cache, pollfail FROM feeds ORDER BY UPPER(TITLE)')
		cache = self.c.fetchall()
		self.c.execute(u'UPDATE settings SET value=1 WHERE data="feed_cache_dirty"')
		self.db.commit()
		self.cache_dirty=True
		return cache
		
	def insertURL(self, url,title=None):
		#if a feed with that url doesn't already exists, add it

		self.c.execute("""SELECT url FROM feeds WHERE url=?""",(url,))
		#on success, fetch will return the url itself
		if self.c.fetchone() != (url,):
			if title is not None:
				self.c.execute(u"""INSERT INTO feeds (id,title,url,polled,pollfail,modified,pollfreq,lastpoll,newatlast,feed_pointer) VALUES (NULL,?, ?,0,0, 0,1800,0,0,-1)""", (title,url)) #default 30 minute polling
			else:
				self.c.execute(u"""INSERT INTO feeds (id,title,url,polled,pollfail,modified,pollfreq,lastpoll,newatlast,feed_pointer) VALUES (NULL,?, ?,0,0, 0,1800,0,0,-1)""", (url,url)) #default 30 minute polling
			self.db.commit()
			self.c.execute(u"""SELECT id,url FROM feeds WHERE url=?""",(url,))
			feed_id = self.c.fetchone()
			feed_id = feed_id[0]
			d={ 'title':_("Waiting for first poll"),
				'description':_("This feed has not yet been polled successfully.  There might be an error with this feed.<br>"+str(url)),
			  }
			self.c.execute(u'INSERT INTO entries (id, feed_id, title, creator, description, read, fakedate, date, guid, link, old, new) VALUES (NULL, ?, ?, NULL, ?, ?, 0, ?, ?, "http://", "0", "1")',(feed_id,d['title'],d['description'],'0',time.time(),time.time()))
			self.db.commit()
		else:
			self.c.execute("""SELECT id FROM feeds WHERE url=?""",(url,))
			feed_id = self.c.fetchone()
			feed_id = feed_id[0]
			print "db: feed already exists"
			raise FeedAlreadyExists(feed_id)
			
		return feed_id
	
	def add_feed_filter(self, pointed_feed_id, filter_name, query):
		self.c.execute(u'SELECT id,feed_pointer,description FROM feeds WHERE feed_pointer=? AND description=?',(pointed_feed_id,query))
		result = self.c.fetchone()
		if result is None:
		#if self.c.fetchone() != (str(pointed_feed_id),query):
			s = sha.new()
			#this is lame I know.  We shouldn't ever get a collision here though!
			s.update(filter_name+query)
			self.c.execute(u'INSERT INTO feeds (id,title,url,feed_pointer,description,polled,pollfail,modified,pollfreq,lastpoll,newatlast) VALUES (NULL,?, ?,?,?,0,0, 0,1800,0,0)', (filter_name,s.hexdigest(),pointed_feed_id,query))
			self.db.commit()
			self.c.execute(u'SELECT id FROM feeds WHERE feed_pointer=? AND description=?',(pointed_feed_id,query))
			return self.c.fetchone()[0]
		else:
			raise FeedAlreadyExists, result[0]
			
	def set_feed_filter(self, pointer_feed_id, filter_name, query):
		self.c.execute(u'SELECT feed_pointer FROM feeds WHERE id=?',(pointer_feed_id,))
		pointed_id = self.c.fetchone()
		if pointed_id is None:
			raise NoFeed, pointer_feed_id
		pointed_id = pointed_id[0]
		self.c.execute(u'SELECT id FROM feeds WHERE feed_pointer=? AND description=?',(pointed_id,query))
		result = self.c.fetchone()
		if result is None:
			self.c.execute(u'UPDATE feeds SET title=?, description=? WHERE id=?',(filter_name, query, pointer_feed_id))
			self.db.commit()
		else:
			raise FeedAlreadyExists, result[0]
				
	def delete_feed(self, feed_id):
		#check for valid entry		
		self.c.execute("""SELECT id FROM feeds WHERE id=?""",(feed_id,))
		result = self.c.fetchone()[0]

		if result != feed_id:			
			raise NoFeed,feed_id
		
		#delete the feed, its entries, and its media (this does not delete files)
		self.c.execute("""DELETE FROM feeds WHERE id=?""",(feed_id,))
		self.reindex_feed_list.append(feed_id)
		self.c.execute(u'DELETE FROM tags WHERE feed_id=?',(feed_id,))
		self.db.commit()
		#result = self.c.fetchone()
		#print(result)
		self.c.execute('SELECT id FROM entries WHERE feed_id=?',(feed_id,))
		data=self.c.fetchall()
		if data: 
			dataList = [list(row) for row in data]
			for datum in dataList:
				self.c.execute('SELECT id FROM media WHERE entry_id=?',(datum[0],))
				media=self.c.fetchall()
				if media: 
					mediaList = [list(row) for row in media]
					for medium in mediaList:
						self.delete_media(int(medium[0]))
						self.db.commit()
					self.c.execute('DELETE FROM media WHERE entry_id=?',(datum[0],))
			self.reindex_entry_list.append(datum[0])
		self.c.execute("""DELETE FROM entries WHERE feed_id=?""",(feed_id,))
		self.db.commit()
		
	def delete_media(self, media_id):
		media = self.get_media(media_id)
		try: #if it doesn't even have a 'file' key then return
			if media['file']==None:
				return
		except:
			return
		try:
			if os.path.isfile(media['file']):
				os.remove(media['file'])
			elif os.path.isdir(media['file']): #could be a dir if it was a bittorrent download
				utils.deltree(media['file']) 
		except os.error, detail:
			print "Error deleting: "+str(detail)
		#but keep going in case the dirs are empty now
		try:
			#now check to see if we should get rid of the dated dir
			globlist = glob.glob(os.path.split(media['file'])[0]+"/*")
			if len(globlist)==1 and os.path.split(globlist[0])[1]=="playlist.m3u": #if only the playlist is left, we're done
				utils.deltree(os.path.split(media['file'])[0])
			if len(globlist)==0: #similarly, if dir is empty, we're done.
				utils.deltree(os.path.split(media['file'])[0])
		except os.error, detail:
			print "Error deleting dirs: "+str(detail)
		#if everything worked, set status
		self.set_media_download_status(media_id,D_NOT_DOWNLOADED)			
		
	def delete_bad(self):	
		self.c.execute("""DELETE FROM feeds WHERE title IS NULL""")
		self.db.commit()
		
	def poll_multiple(self, arguments=0, feeds=None):
		"""Polls multiple feeds multithreadedly"""
		successes=[]
		self.reindex_entry_list = []
		self.reindex_feed_list = []
		cur_time = time.time()
		
		if feeds is None:
			if arguments & A_AUTOTUNE and arguments & A_ALL_FEEDS == 0:
				self.c.execute('SELECT id FROM feeds WHERE (? - lastpoll) >= pollfreq', (cur_time,))
			elif arguments & A_ERROR_FEEDS:
				self.c.execute('SELECT id FROM feeds WHERE pollfail=1')
			else: #polling all
				self.c.execute('SELECT id FROM feeds')
				
			data=self.c.fetchall()
			if data: 
				feeds = [row[0] for row in data]
			else:
				return
		
		pool = ThreadPool.ThreadPool(6,"ptvDB", lucene_compat=True)
		self._parse_list = []
		for feed in feeds:
			if self.cancel_poll_multiple or self.exiting:
				break
			self.c.execute(u'SELECT feed_pointer FROM feeds WHERE id=?',(feed,))
			result = self.c.fetchone()[0]
			if result >= 0:
				self._parse_list.append((feed, arguments, len(feeds), -2)) 
				continue
				
			self.c.execute("""SELECT url,modified,etag FROM feeds WHERE id=?""",(feed,))
			data = self.c.fetchone()
			#url,modified,etag=data
			pool.queueTask(self.pool_poll_feed,(feed,arguments,len(feeds), data),self._poll_mult_cb)
			#time.sleep(.1) #maybe this will help stagger things a bit?
			
		polled = 0
		while polled < len(feeds):
			if self.exiting:
				break
			#print polled,len(feeds)
			if len(self._parse_list) > 0:
				#print "result"
				polled+=1
				feed_id, args, total, parsed = self._parse_list.pop(0)
				self.polling_callback(self.process_feed(feed_id, args, total, parsed))
			time.sleep(.1)
			
		while pool.getTaskCount()>0: #manual joinAll so we can check for exit
			if self.exiting:
				pool.joinAll(False,True)
				self.c.close()
				self.db.close()
				return
			time.sleep(.5)
		pool.joinAll(False,True) #just to make sure I guess
		del pool
		#print "reindexing"
		self.reindex()
		self.cancel_poll_multiple = False
		
	def interrupt_poll_multiple(self):
		self.cancel_poll_multiple = True
		
	def _poll_mult_cb(self, args):
		feed_id, args, total, parsed = args
		#print "append"
		self._parse_list.append((feed_id, args, total, parsed))
		
	def pool_poll_feed(self, args):
		#print "JUST polling"
		feed_id, arguments, total, data = args
		url,modified,etag=data
		
		#print "just poll:", feed_id, arguments, total, data
		
		try:
			feedparser.disableWellFormedCheck=1  #do we still need this?  it used to cause crashes
			if arguments & A_IGNORE_ETAG == A_IGNORE_ETAG:
				data = feedparser.parse(url)
			else:
				data = feedparser.parse(url,etag)
			#print "made it"
			return (feed_id, arguments, total, data)
		except Exception, e:
			print e
			return (feed_id, arguments, total, -1)

	def process_feed(self,feed_id, args, total, data, recurse=0):# recurse=0):
		"""a wrapper function that returns the index along with the result
		so we can sort.  Each poller needs its own db connection for locking reasons"""
		#try:	
		#	db=sqlite.connect(self.home+"/.penguintv/penguintv3.db", timeout=20)
		#except:
		#	raise DBError,"error connecting to database"
		
		#feed_id=args[0]
		#total = args[2]
		
		#print "processing",feed_id, args, total, type(data)
		
		db = self.db 
		
		poll_arguments = 0
		result = 0
		pollfail = False
		try:
			#poll_arguments = args[1]
			if self.exiting:
				return (feed_id,{'pollfail':True}, total)
			result = self.poll_feed(feed_id, args, preparsed=data)
			if self.exiting:
				return (feed_id,{'pollfail':True} ,total)
		except sqlite.OperationalError, e:
			print "Database warning...", e
			#db.close()
			#del db #delete it to release the lock
			if recurse < 2:
				time.sleep(5)
				print "trying again..."
				return self.process_feed(feed_id, args, total, data, recurse+1) #and reconnect
			print "can't get lock, giving up"
			return (feed_id,{'pollfail':True}, total)
		except FeedPollError,e:
			print e
			pollfail = True
			#db.close()
			#del db
			print "done"
			return (feed_id,{'pollfail':True}, total)
		except IOError, e:
			print e
			#db.close()
			#del db
			return (feed_id,{'ioerror':e}, total)
		except:
			print "other error polling feed:"
			exc_type, exc_value, exc_traceback = sys.exc_info()
			error_msg = ""
			for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
				error_msg += s
			print error_msg
			pollfail = True
			#db.close()
			#del db
			return (feed_id,{'pollfail':True}, total)
			
		#assemble our handy dictionary while we're in a thread
		update_data={}
		#c = db.cursor()
		c = self.c
		
		if self.is_feed_filter(feed_id, c):
			entries = self.get_entrylist(feed_id, c) #reinitialize filtered_entries dict
			update_data['unread_count'] = self.get_unread_count(feed_id, c)
			flag_list = self.get_entry_flags(feed_id,c)
			update_data['pollfail']=self.get_feed_poll_fail(self.resolve_pointed_feed(feed_id,c),c)
		else:
			c.execute(u'SELECT read FROM entries WHERE feed_id=?',(feed_id,))
			list = c.fetchall()
			update_data['unread_count'] = len([item for item in list if item[0]==0])
			flag_list = self.get_entry_flags(feed_id,c)
			
			if len(self.get_pointer_feeds(feed_id, c)) > 0:
				print "have pointers, reindexing now"
				self.reindex()
				
			update_data['flag_list']=flag_list
			update_data['pollfail']=pollfail
		#c.close()
		#db.close()
		#del db
		#print "done processing",feed_id
		return (feed_id,update_data, total)
			
	def poll_feed_trap_errors(self, feed_id, callback):
		try:
			feed={}
			self.c.execute("SELECT title,url FROM feeds WHERE id=?",(feed_id,))
			result = self.c.fetchone()
			feed['feed_id']=feed_id
			feed['title']=result[0]
			feed['url']=result[1]
			self.poll_feed(feed_id)
			self.reindex()
			callback(feed, True)
		except Exception, e:#FeedPollError,e:
			print e
			print "error polling feed:"
			exc_type, exc_value, exc_traceback = sys.exc_info()
			error_msg = ""
			for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
				error_msg += s
			print error_msg
			callback(feed, False)

	def _polling_callback(self, data):
		print "look a callback"
		print data
		
	def poll_feed(self, feed_id, arguments=0, db=None, preparsed=None):
		"""polls a feed and returns the number of new articles.  Optionally, one can pass
			a feedparser dictionary in the preparsed argument and avoid network operations"""
		if db is None:
			db = self.db
		c = db.cursor()
		
		#print "poll:",feed_id, arguments
		
		if preparsed is None:
			#feed_id = self.resolve_pointed_feed(feed_id, c)
			c.execute(u'SELECT feed_pointer FROM feeds WHERE id=?',(feed_id,))
			result = c.fetchone()[0]
			if result >= 0:
				return 0
				
			c.execute("""SELECT url,modified,etag FROM feeds WHERE id=?""",(feed_id,))
			data = c.fetchone()
			url,modified,etag=data
			try:
				feedparser.disableWellFormedCheck=1  #do we still need this?  it used to cause crashes
				if arguments & A_IGNORE_ETAG == A_IGNORE_ETAG:
					data = feedparser.parse(url)
				else:
					data = feedparser.parse(url,etag)
			except Exception, e:
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					self.set_new_update_freq(db, c, feed_id, 0)
				c.execute("""UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
				db.commit()
				c.close()
				print e
				raise FeedPollError,(feed_id,"feedparser blew a gasket")
		else:
			if preparsed == -1:
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					self.set_new_update_freq(db, c, feed_id, 0)
				c.execute("""UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
				db.commit()
				c.close()
				#print "it's -1"
				raise FeedPollError,(feed_id,"feedparser blew a gasket")
			elif preparsed == -2:
				#print "pointer feed, returning 0"
				return 0
			else:
				#print "data is good"
				data = preparsed
			
		if data.has_key('status'):
			if data['status'] == 304:  #this means "nothing has changed"
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					self.set_new_update_freq(db, c, feed_id, 0)
				c.execute("""UPDATE feeds SET pollfail=0 WHERE id=?""",(feed_id,))
				c.execute("""UPDATE entries SET new=0 WHERE feed_id=?""",(feed_id,))
				db.commit()
				c.close()
				return 0
			if data['status'] == 404: #whoops
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					self.set_new_update_freq(db, c, feed_id, 0)
				c.execute("""UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
				db.commit()
				c.close()
				raise FeedPollError,(feed_id,"404 not found: "+url)

		if len(data['channel']) == 0 or len(data['items']) == 0:
			if data.has_key('bozo_exception'):
				if isinstance(data['bozo_exception'],urllib2.URLError):
					e = data['bozo_exception'][0]
					errno = e[0]
					if e[0] == -3: #failure in name resolution
						raise IOError(e)	
			
			if arguments & A_AUTOTUNE == A_AUTOTUNE:
				self.set_new_update_freq(db, c, feed_id, 0)
			c.execute("""UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
			db.commit()
			c.close()
			raise FeedPollError,(feed_id,"empty feed")
			
		#else...
		if arguments & A_DELETE_ENTRIES == A_DELETE_ENTRIES:
			print "deleting existing entries", feed_id, arguments
			c.execute("""DELETE FROM entries WHERE feed_id=?""",(feed_id,))
			db.commit()
	        #to discover the old entries, first we mark everything as old
		#later, we well unset this flag for everything that is NEW,
		#MODIFIED, and EXISTS. anything still flagged should be deleted  
		c.execute("""UPDATE entries SET old=1 WHERE feed_id=?""",(feed_id,)) 
		c.execute("""UPDATE entries SET new=0 WHERE feed_id=?""",(feed_id,))
		c.execute("""UPDATE feeds SET pollfail=0 WHERE id=?""",(feed_id,))
		db.commit()
	
		#normalize results
		channel = data['channel']
		if channel.has_key('description') == 0:
			channel['description']=""
		if len(channel['description']) > 128:
			channel['description'] = channel['description'][0:127]
		channel['description']=self.encode_text(channel['description'])
		if channel.has_key('title') == 0:
			if channel['description'] != "":
				channel['title']=channel['description']
			else:
				channel['title']=url
		channel['title'] = self.encode_text(channel['title'])
		
		#print channel['title']

		if not data.has_key('etag'):
			data['etag']='0'
		if not data.has_key('modified'):
			modified='0'
		else:
			modified = time.mktime(data['modified'])

		try:
			c.execute(u'SELECT title FROM feeds WHERE id=?',(feed_id,))
			exists=c.fetchone()
			if len(exists[0])>4:
				if exists[0][0:4]!="http": #hack to detect when the title hasn't been set yet because of first poll
				 	c.execute("""UPDATE feeds SET description=?, modified=?, etag=? WHERE id=?""", (channel['description'], modified,data['etag'],feed_id))
				else:
					c.execute("""UPDATE feeds SET title=?, description=?, modified=?, etag=? WHERE id=?""", (channel['title'],channel['description'], modified,data['etag'],feed_id))
			elif len(exists[0])>0: #don't change title
				if exists[0] is not None:
					c.execute("""UPDATE feeds SET description=?, modified=?, etag=? WHERE id=?""", (channel['description'], modified,data['etag'],feed_id))
				else:
					c.execute("""UPDATE feeds SET title=?, description=?, modified=?, etag=? WHERE id=?""", (channel['title'],channel['description'], modified,data['etag'],feed_id))
			else:
				c.execute("""UPDATE feeds SET title=?, description=?, modified=?, etag=? WHERE id=?""", (channel['title'],channel['description'], modified,data['etag'],feed_id))
			self.reindex_feed_list.append(feed_id)
		except Exception, e:
			print e
			#f = open("/var/log/penguintv.log",'a')
			#f.write("borked on: UPDATE feeds SET title="+str(channel['title'])+", description="+str(channel['description'])+", modified="+str(modified)+", etag="+str(data['etag'])+", pollfail=0 WHERE id="+str(feed_id))
			#f.close()	
			c.execute("""UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
			db.commit()	
			c.close()		 
			raise FeedPollError,(feed_id,"error updating title and description of feed")
			
		c.execute(u'SELECT link FROM feeds WHERE id=?',(feed_id,))
		link = c.fetchone()
		if link is not None:
			link = link[0]
			if link == "" and data['feed'].has_key('link'):
				c.execute(u'UPDATE feeds SET link=? WHERE id=?',(data['feed']['link'],feed_id))
		db.commit()
		
		#populate the entries
		c.execute("""SELECT id,guid,link,title,description FROM entries WHERE feed_id=? order by fakedate""",(feed_id,)) 
		existing_entries = c.fetchall()
		
		#we can't trust the dates inside the items for timing data
		#bad formats, no dates at all, and timezones screw things up
		#so I introduce a fake date which works for determining read and
		#unread article counts, and keeps the articles in order
		fake_time = time.time()#-len(data['items'])
		i=0
		try:
			if data['items'][0].has_key('updated_parsed') == 1:
				data['items'].sort(lambda x,y: int(time.mktime(y['updated_parsed'])-time.mktime(x['updated_parsed'])))
		except:
			try:
				if data['items'][0].has_key('modified_parsed') == 1:
					data['items'].sort(lambda x,y: int(time.mktime(y['modified_parsed'])-time.mktime(x['modified_parsed'])))
			except:
				try:
					if data['items'][0].has_key('created_parsed') == 1:
						data['items'].sort(lambda x,y: int(time.mktime(y['created_parsed'])-time.mktime(x['created_parsed'])))
				except:	
					try:	
						if data['items'][0].has_key('date_parsed') == 1:
							data['items'].sort(lambda x,y: int(time.mktime(y['date_parsed'])-time.mktime(x['date_parsed'])))
					except:
						pass #I feel dirty.
		
		new_items = 0
		for item in data['items']:
			#do a lot of normalizing
			item['body'] = ''
			possible_bodies = []
			#right now we look in the following places for the body, and take the longest one:
			#content, description, summary, summary_detail
			if item.has_key('content'):   #ok so peter was right, 
				possible_bodies.append(item['content'][0]['value'])
			if item.has_key('description'):   #content_encoded is where we should be
				possible_bodies.append(item['description'])
			if item.has_key('summary'):             #or the summary
				possible_bodies.append(item['summary'])
			if item.has_key('summary_detail'):
				possible_bodies.append(item['summary_detail']['value'])	
			
			if len(possible_bodies):
				possible_bodies.sort(lambda x,y: len(y)-len(x))
				item['body'] = possible_bodies[0]	
				
			
			item['body']=self.encode_text(item['body'])
			
			if item['body'].count('&lt') > 5: #probably encoded body
				item['body'] = utils.html_entity_unfixer(item['body'])
			
			if item.has_key('title') == 0:
				item['title']=item['description'][0:35]	
				html_begin = string.find(item['title'],'<')
				if html_begin >= 0 and html_begin < 5: #in case it _begins_ with html, and the html is really early
					p = utils.StrippingParser()
					p.feed(item['description'])
					p.close()
					p.cleanup()
					item['title']=p.result[0:35]
			elif item['title']=="":
				item['title']=item['description'][0:35]
				html_begin = string.find(item['title'],'<')
				if html_begin >= 0 and html_begin < 5: #in case it _begins_ with html, and the html is really early
					p = utils.StrippingParser()
					p.feed(item['description'])
					p.close()
					p.cleanup()
					item['title']=p.result[0:35]
			
				elif html_begin > 5: #in case there's html within 35 chars...
					item['title']=item['title'][0:html_begin-1] #strip
					#things mess up if a title ends in a space, so strip trailing spaces
				#doublecheck
				if len(item['title'])==0:
					item['title']='untitled'
				else:
					item['title'] = item['title'].strip()
			
			try:
				p = utils.StrippingParser()
				p.feed(item['title'])
				p.close()
				p.cleanup()
				item['title'] = p.result				
			except:
				pass

			#try disabling this for a while
			#this may seem weird, but this prevents &amp;amp;	
			#item['title'] = re.sub('&amp;','&',item['title'])
			item['title'] = re.sub('& ','&amp; ',item['title'])
			
			if type(item['body']) is str:
				item['body'] = unicode(item['body'],'utf-8')
			for uni in _common_unicode.keys():
				item['body'] = item['body'].replace(uni, _common_unicode[uni])
			
			item['title'] = self.encode_text(item['title'])
			
			if item.has_key('creator') == 0:
				item['creator']=""
			if item.has_key('author') == 1:
				item['creator']=item['author']
			if item.has_key('guid') == 0:
				item['id']=0
				item['guid']='0'
			if item.has_key('link') == 0:
				item['link'] = ""
				
			item['creator']=self.encode_text(item['creator'])
			
			#blow away date_parsed with more recent times
			if item.has_key('updated_parsed'):
				item['date_parsed'] = item['updated_parsed']
			elif item.has_key('modified_parsed'):
				item['date_parsed'] = item['modified_parsed']
			elif item.has_key('created_parsed'):
				item['date_parsed'] = item['created_parsed']
			elif item.has_key('update_parsed'):
				item['date_parsed'] = item['update_parsed']
			
			if item.has_key('date_parsed')==False:
				item['date_parsed']=(0,0,0,0,0,0,0,0,0)
				
			status = self.get_status(item,existing_entries,c)
			
			#print item['title']
			
			if status[0]==NEW:
				new_items = new_items+1
				#finally insert the entry with fake time
				#try:
				c.execute(u'INSERT INTO entries (id, feed_id, title, creator, description, read, fakedate, date, guid, link, old, new) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',(feed_id,item['title'],item['creator'],item['body'],'0',fake_time-i, time.mktime(item['date_parsed']),item['guid'],item['link'],'0','1'))
				#db.commit()
				#except:
				#	pass
				c.execute("""SELECT id FROM entries WHERE fakedate=?""",(fake_time-i,))
				entry_id = c.fetchone()[0]

				if item.has_key('enclosures'):
					for media in item['enclosures']:
						media.setdefault('length', 0)
						media.setdefault('type', 'application/octet-stream')
						c.execute(u"""INSERT INTO media (id, entry_id, url, mimetype, download_status, viewed, keep, length) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)""", (entry_id, media['url'], media['type'], 0, D_NOT_DOWNLOADED, 0, media['length']))
						#db.commit()
				self.reindex_entry_list.append(entry_id)
			elif status[0]==EXISTS:
				c.execute("""UPDATE entries SET old=0 where id=?""",(status[1],))
				#db.commit()
			elif status[0]==MODIFIED:
#				new_items = new_items+1
				c.execute(u'UPDATE entries SET title=?, creator=?, description=?, date=?, guid=?, link=?, old=? WHERE id=?', (item['title'],item['creator'],item['body'], time.mktime(item['date_parsed']),item['guid'],item['link'],'0',status[1]))
				if self.entry_flag_cache.has_key(status[1]): del self.entry_flag_cache[status[1]]
				if item.has_key('enclosures'):
					c.execute("DELETE FROM media WHERE entry_id=? AND (download_status=? OR download_status=?)",(status[1],D_NOT_DOWNLOADED,D_ERROR)) #delete any not-downloaded or errored enclosures
					db.commit()
					for media in item['enclosures']: #add the rest
						c.execute(u'SELECT url FROM media WHERE url=?',(media['href'],))
						dburl = c.fetchone()
						if dburl:
							if dburl[0] != media['url']: #only add if that url doesn't exist
								media.setdefault('length', 0)
								media.setdefault('type', 'application/octet-stream')
								c.execute(u"""INSERT INTO media (id, entry_id, url, mimetype, download_status, viewed, keep, length) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)""", (status[1], media['url'], media['type'], 0, D_NOT_DOWNLOADED, 0, media['length']))
				#db.commit()
						else:
							media.setdefault('length', 0)
							media.setdefault('type', 'application/octet-stream')
							c.execute(u"""INSERT INTO media (id, entry_id, url, mimetype, download_status, viewed, keep, length) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)""", (status[1], media['url'], media['type'], 0, D_NOT_DOWNLOADED, 0, media['length']))
				self.reindex_entry_list.append(status[1])
			i+=1
		db.commit()
		#don't call anything old that has media...
		c.execute("""SELECT entries.id FROM entries INNER JOIN media ON entries.id = media.entry_id WHERE media.download_status>0 AND entries.feed_id=?""",(feed_id,))
		for id in c.fetchall():
			c.execute("""UPDATE entries SET old=0 WHERE id=?""",(id[0],))
		db.commit()
		#anything not set above as new, mod, or exists is no longer in
		#the xml and therefore should be deleted
		
		c.execute("""SELECT id FROM entries WHERE feed_id=?""",(feed_id,))
		all_entries = len(c.fetchall())
		c.execute("""SELECT id FROM entries WHERE old=1 AND feed_id=?""",(feed_id,))
		old_entries = len(c.fetchall())
		if old_entries>0:
			new_entries = all_entries - old_entries
			if MAX_ARTICLES > 0: #zero means never delete
				if new_entries >= MAX_ARTICLES:
					#deleting all old because we got more than enough new
					c.execute("""DELETE FROM entries WHERE old=1 AND feed_id=?""",(feed_id,))
				elif new_entries+old_entries > MAX_ARTICLES:
					old_articles_to_keep = MAX_ARTICLES-new_entries
					if old_articles_to_keep > 0:
						old_articles_to_ditch = old_entries - old_articles_to_keep
						c.execute("""SELECT id,title FROM entries WHERE old=1 AND feed_id=? ORDER BY fakedate LIMIT ?""",(feed_id,old_articles_to_ditch))
						ditchables = c.fetchall()
						for e in ditchables:
							c.execute("""DELETE FROM entries WHERE id=?""",(e[0],))
		c.execute("DELETE FROM entries WHERE fakedate=0 AND feed_id=?",(feed_id,))
		#self.update_entry_flags(feed_id,db)
		#self.update_feed_flag(feed_id,db)
		db.commit()
		if arguments & A_AUTOTUNE == A_AUTOTUNE:
			self.set_new_update_freq(db,c, feed_id, new_items)
		c.close()
		if arguments & A_DO_REINDEX:
			if new_items > 0:
				self.reindex()
		return new_items
		
	def set_new_update_freq(self, db,c, feed_id, new_items):
		"""Based on previous feed history and number of items found, adjust
		the polling frequency.  The goal is one item per poll.
		Right now the algorithm is:
		
		find new items per poll period.
		
		if it's zero (didn't find anything):
		 increase the poll frequency by ratio of average polltime to our previous frequency
		if it's >1:
		 set poll freq to now-last_poll / new_items_per_poll_period
		 (ie if we got 1.5 items this past period, set poll freq to old_freq/1.5
		if it's 1:
		 jackpot, do nothing
		 
		updates are never more often than 30 mins and never rarer than 4 hours
		"""
		
		#should never be called on a filtered feed
		
		c.execute(u'SELECT lastpoll, newatlast, pollfreq FROM feeds WHERE id=?',(feed_id,))
		last_time,newatlast,old_poll_freq = c.fetchone()
		cur_time = time.time()
		#this could suck if the program was just started, so only do it if the poll_freq seems correct
		#however still update the db with the poll time
		c.execute(u'UPDATE feeds SET lastpoll=?, newatlast=? WHERE id=?',(cur_time,new_items,feed_id))
		db.commit()
		if cur_time - last_time < old_poll_freq/2:  #too soon to get a good reading.
			return
		
		#normalize dif:
		new_items = round(new_items *  old_poll_freq / (cur_time-last_time))
		
		if new_items==0:
			#figure out the average time between article postings
			#this algorithm seems to be the most accurate based on my own personal judgment
			c.execute('SELECT date FROM entries WHERE feed_id=?',(feed_id,))
			datelist = c.fetchall()
			datelist.append((time.time(),)) #helps in some cases to pretend we found one now
 			i=0
			list=[]
			for item in datelist[:-1]:
				diff=abs(datelist[i+1][0]-datelist[i][0])
				list.append(diff)
  				i=i+1
			if len(list)>0:
  				avg = sum(list)/len(list)
			else:
				avg=0
			#increase the poll frequency by ratio of average polltime to our previous frequency
			modifier = avg / old_poll_freq
			poll_freq = round(old_poll_freq + modifier*60)
		elif new_items>1:
			poll_freq = floor((cur_time - last_time) / new_items)
		else:
			return
			
		if poll_freq > 21600: #four hours
			poll_freq = 21600
		if poll_freq < 1800: #30 mins
			poll_freq = 1800
	
		c.execute('UPDATE feeds SET pollfreq=? WHERE id=?',(poll_freq,feed_id))
		db.commit()
		
	def get_status(self,item,existing_entries,c):
		ID=0
		GUID=1
		LINK=2
		TITLE=3
		BODY=4

		entry_id=-1
		old_hash = sha.new()
		new_hash = sha.new()
		
		for entry_item in existing_entries:
			if str(item['guid'])!='0':
				if str(entry_item[GUID]) == str(item['guid']):# and entry_item[TITLE] == item['title']:
					entry_id = entry_item[ID]
					old_hash.update(self.ascii(entry_item[GUID])+self.ascii(entry_item[BODY]))
					new_hash.update(self.ascii(item['guid'])+self.ascii(item['body']))
					break
			elif item['link']!='':
				if entry_item[LINK] == item['link'] and entry_item[TITLE] == item['title']:
					entry_id = entry_item[ID]
					old_hash.update(self.ascii(entry_item[LINK])+self.ascii(entry_item[BODY]))
					new_hash.update(self.ascii(item['link'])+self.ascii(item['body']))
					break
			elif entry_item[TITLE] == item['title']:
				entry_id = entry_item[ID]
				old_hash.update(self.ascii(entry_item[TITLE])+self.ascii(entry_item[BODY]))
				new_hash.update(self.ascii(item['title'])+self.ascii(item['body']))
				break

		if entry_id == -1:
			return (NEW, entry_id)

		if new_hash.hexdigest() == old_hash.hexdigest():
			#now check enclosures
			old_media = self.get_entry_media(entry_id,c)
			
			if old_media is not None:
				old_media = [medium['url'] for medium in old_media]
			else:
				old_media = []

			new_media = []
			if item.has_key('enclosures'):
				for m in item['enclosures']:
					new_media.append(m['href'])
				
			if len(old_media) != len(new_media):
				return (MODIFIED,entry_id)
				
			if len(old_media) == 0 and len(new_media)==0:
				return (EXISTS,entry_id)
			
			old_media = utils.uniquer(old_media)
			old_media.sort()
			new_media = utils.uniquer(new_media)
			new_media.sort()

			if old_media != new_media:
				return (MODIFIED,entry_id)
			return (EXISTS,entry_id)
		else:
			return (MODIFIED,entry_id)
			
	def get_entry_media(self, entry_id, c=None):
		if c==None:
			c = self.c
		c.execute("""SELECT id,entry_id,url,file,download_status,viewed,length,mimetype FROM media WHERE entry_id = ?""",(entry_id,))
		data=c.fetchall()
		
		if data: 
			dataList = [list(row) for row in data]
		else:
			return []
		media_list=[]
		for datum in dataList:
			medium={}
			medium['url']=datum[2] #MAGIC
			medium['download_status']=int(datum[4]) #MAGIC
			try:
				medium['size']=int(datum[6]) #MAGIC
			except:
				medium['size']=0
			medium['media_id']=int(datum[0]) #MAGIC
			medium['file']=datum[3] #MAGIC			
			medium['entry_id']=datum[1] #MAGIC
			medium['viewed']=int(datum[5]) #MAGIC
			medium['mimetype']=datum[7] #MAGIC
			media_list.append(medium)			
		return media_list
		
	def get_media(self, media_id):
		self.c.execute(u'SELECT url, download_status, length, file, entry_id, viewed, mimetype FROM media WHERE id=?',(media_id,))
		datum=self.c.fetchone()
		if datum is None:
			return None
		medium={}
		medium['url']=datum[0] #MAGIC
		medium['download_status']=int(datum[1]) #MAGIC
		try:
			medium['size']=int(datum[2]) #MAGIC
		except:
			pass
		medium['media_id']=media_id
		medium['file']=datum[3] #MAGIC
		medium['entry_id']=datum[4] #MAGIC
		medium['viewed']=int(datum[5]) #MAGIC
		medium['mimetype']=datum[6] #MAGIC
		return medium
	
	def get_entry(self, entry_id):
		self.c.execute("""SELECT title, creator, link, description, feed_id, date FROM entries WHERE id=?""",(entry_id,))
		result = self.c.fetchone()
		
		entry_dic={}
		try:
			entry_dic['title'] = result[0]
			entry_dic['creator'] = result[1]
			entry_dic['link'] = result[2]
			entry_dic['description']=result[3]
			entry_dic['feed_id']= result[4]
			entry_dic['date'] = result[5]
			entry_dic['entry_id'] = entry_id
		except TypeError: #this error occurs when feed or item is wrong
			raise NoEntry, entry_id
		return entry_dic
		
	def get_entrylist(self, feed_index, c=None):
		if c is None:
			c = self.c
		c.execute(u'SELECT feed_pointer,description FROM feeds WHERE id=?',(feed_index,))
		result = c.fetchone()
		if result is None:
			return []
		if result[0] >= 0:
			pointed_feed = result[0]
			#this is where we perform a search
			entries =  self.search(result[1],pointed_feed)[1]
			if len(entries)==0:
				return []
			entries.sort(lambda x,y: int(y[2] - x[2]))
			#need list of "new"s.
			c.execute(u'SELECT id,new FROM entries WHERE feed_id=? ORDER BY fakedate DESC',(pointed_feed,))
			new_info = c.fetchall()
			ret_val = []
			i=0
			try:
				for entry in entries:
					while new_info[i][0] != entry[0]:
						i+=1
					ret_val.append((entry[0],entry[1],entry[2],new_info[i][1]))
			except Exception, e:
				print "problem with getentrylist..."
				print e
				print i
				print len(entries)
				print len(new_info)
			self.filtered_entries[feed_index] = ret_val
			return ret_val
	
		c.execute("""SELECT id,title,fakedate,new FROM entries WHERE feed_id=? ORDER BY fakedate DESC""",(feed_index,))
		result = c.fetchall()
		
		if result=="":
			raise NoFeed, feed_index
		return result

	def get_feedlist(self):
		self.c.execute("""SELECT id,title FROM feeds ORDER BY UPPER(title)""")
		result = self.c.fetchall()
		dataList = []
		if result: 
			dataList = [list(row) for row in result]
		else:
			result=[]
		return dataList
		
	def get_feed_title(self, feed_index):
		self.c.execute("""SELECT title FROM feeds WHERE id=?""",(feed_index,))
		try:
			result = self.c.fetchone()[0]
		except TypeError:
			raise NoFeed, feed_index	
		
		#don't return a tuple
		return result #self.decode_text(result)
		
	def get_feed_info(self, feed_id):
		self.c.execute("""SELECT title, description, url, link, feed_pointer, lastpoll, pollfreq FROM feeds WHERE id=?""",(feed_id,))
		try:
			result = self.c.fetchone()
			d = {'title':result[0],
				 'description':result[1],
				 'url':result[2],
				 'link':result[3],
				 'feed_pointer':result[4],
				 'lastpoll':result[5],
				 'pollfreq':result[6]}
			return d
		except TypeError:
			raise NoFeed, feed_id	
		return result
		
	def set_feed_name(self, feed_id, name):
		name = self.encode_text(name)
		
		if name is not None:
			self.c.execute(u'UPDATE feeds SET title=? WHERE id=?',(name,feed_id))
			self.db.commit()
		else:
			self.c.execute("""SELECT url FROM feeds WHERE id=?""",(feed_id,))
			url=self.c.fetchone()[0]
			
			try:
				feedparser.disableWellFormedCheck=1
				data = feedparser.parse(url)
			except:
				return
			channel=data['channel']
			if channel.has_key('title') == 0:
				if channel['description'] != "":
					channel['title']=channel['description']
				else:
					channel['title']=url
			channel['title'] = self.encode_text(channel['title'])
			
			self.c.execute(u'UPDATE feeds SET title=? WHERE id=?',(channel['title'],feed_id))
			self.db.commit()
		self.reindex_feed_list.append(feed_id)
		self.reindex()
		
	def set_feed_url(self, feed_id, url):
		try:
			self.c.execute(u'UPDATE feeds SET url=? WHERE id=?',(url,feed_id))
			self.db.commit()
		except sqlite.IntegrityError:
			raise FeedAlreadyExists,feed_id			
		
	def set_feed_link(self, feed_id, link):
		self.c.execute(u'UPDATE feeds SET link=? WHERE id=?',(link,feed_id))
		self.db.commit()
				
	def set_media_download_status(self, media_id, status):
		self.c.execute(u'UPDATE media SET download_status=? WHERE id=?', (status,media_id,))
		self.db.commit()
		self.c.execute(u'SELECT entry_id FROM media WHERE id=?',(media_id,))
		entry_id = self.c.fetchone()[0]
		if self.entry_flag_cache.has_key(entry_id):
			del self.entry_flag_cache[entry_id]
		
	def set_media_filename(self, media_id, filename):
		self.c.execute(u'UPDATE media SET file=? WHERE id=?', (filename,media_id))
		self.db.commit()
		
	def set_media_viewed(self, media_id, viewed):
		self.c.execute(u'UPDATE media SET viewed=? WHERE id=?',(int(viewed),media_id))
		self.db.commit()
		self.c.execute(u'SELECT entry_id FROM media WHERE id=?',(media_id,))
		entry_id = self.c.fetchone()[0]
		
		if self.entry_flag_cache.has_key(entry_id): del self.entry_flag_cache[entry_id]
	
		if viewed==1:#check to see if this makes the whole entry viewed
			self.c.execute(u'SELECT viewed FROM media WHERE entry_id=?',(entry_id,))
			list = self.c.fetchall()
			if list:
				for v in list:
					if v==0: #still some unviewed
						return
					#else
					self.set_entry_read(entry_id, 1)
		else:
			#mark as unviewed by default
			self.set_entry_read(entry_id, 0)
				
		
	def get_media_size(self, media_id):
		self.c.execute(u'SELECT length FROM media WHERE id=?',(media_id,))
		return self.c.fetchone()[0]
	
	def set_media_size(self, media_id, size):
		self.c.execute(u'UPDATE media SET length=? WHERE id=?',(int(size),media_id))
		self.db.commit()

	def set_entry_new(self, entry_id, new):
		self.c.execute(u'UPDATE entries SET new=? WHERE id=?',(int(new),entry_id))
		self.db.commit()
		if self.entry_flag_cache.has_key(entry_id): del self.entry_flag_cache[entry_id]
		
	def set_entry_read(self, entry_id, read):
		self.c.execute(u'UPDATE entries SET read=? WHERE id=?',(int(read),entry_id))
		self.c.execute(u'UPDATE media SET viewed=? WHERE entry_id=?',(int(read),entry_id))
		self.db.commit()
		if self.entry_flag_cache.has_key(entry_id): del self.entry_flag_cache[entry_id]
		
	def get_entry_read(self, entry_id):
		self.c.execute(u'SELECT read FROM entries WHERE id=?',(entry_id,))
		retval = self.c.fetchone()[0]
		return int(retval)
		
	def clean_media_status(self):
		self.c.execute(u'UPDATE media SET download_status=? WHERE download_status<1',(D_NOT_DOWNLOADED,))
		self.db.commit()
		self.c.execute(u'UPDATE media SET download_status=? WHERE download_status=1',(D_RESUMABLE,))
		self.db.commit()
		
	def get_entryid_for_media(self, media_id):
		self.c.execute(u'SELECT entry_id FROM media WHERE id=?',(media_id,))
		ret = self.c.fetchone()
		return ret[0]
		
	def get_media_for_download(self):
		self.c.execute(u'SELECT media.id, media.length, media.entry_id, entries.feed_id FROM media INNER JOIN entries ON media.entry_id = entries.id WHERE (download_status==? OR download_status==?) AND viewed=0',(D_NOT_DOWNLOADED,D_RESUMABLE))
		list=self.c.fetchall()
		self.c.execute(u'SELECT media.id, media.length, media.entry_id, entries.feed_id FROM media INNER JOIN entries ON media.entry_id = entries.id WHERE download_status==?',(D_ERROR,))
		list=list+self.c.fetchall()
		newlist=[]
		for item in list:
			try:
				size = int(item[1])
			except ValueError:
				#try _this_!
				try:
					size = int(''.join([b for b in a if b.isdigit()]))
				except:
					size = 0
			new_item = (item[0],size,item[2], item[3])
			newlist.append(new_item)
			if self.entry_flag_cache.has_key(item[2]): del self.entry_flag_cache[item[2]]
			
		#build a list of feeds that do not include the noautodownload tag
		feeds = [l[3] for l in newlist]
		feeds = utils.uniquer(feeds)
		if feeds is not None:
			good_feeds = [f for f in feeds if NOAUTODOWNLOAD not in self.get_tags_for_feed(f)]
			newlist = [l for l in newlist if l[3] in good_feeds]
		return newlist 
		
	def get_resumable_media(self):
		self.c.execute(u'SELECT media.id, media.file, media.entry_id, entries.feed_id  FROM media INNER JOIN entries ON media.entry_id = entries.id WHERE download_status=?',(D_RESUMABLE,))
		list = self.c.fetchall()
		dict_list = []	
		dict = {}
		for item in list:
			dict = {}
			dict['media_id'] = item[0]
			dict['file'] = item[1]
			dict['entry_id'] = item[2]
			dict['feed_id'] = item[3]
			dict_list.append(dict)				
		return dict_list
		
	def mark_feed_as_viewed(self, feed_id):
		"""marks a feed's entries and media as viewed.  If there's a way to do this all
		in sql, I'd like to know"""
		
		if self.filtered_entries.has_key(feed_id):
			list = []
			for entry in self.filtered_entries[feed_id]:
				self.c.execute(u'UPDATE entries SET read=1 WHERE id=?',(entry[0],))
				self.c.execute(u'SELECT media.id, media.download_status FROM media WHERE entry_id=?',(entry[0],))
				list = list+self.c.fetchall()
			feed_id = self.resolve_pointed_feed(feed_id)
		else:
			#feed_id = self.resolve_pointed_feed(feed_id)
			self.c.execute(u'UPDATE entries SET read=1 WHERE feed_id=?',(feed_id,))#
			self.c.execute(u'SELECT media.id, media.download_status FROM media INNER JOIN entries ON media.entry_id = entries.id WHERE entries.feed_id = ?',(feed_id,))
			list = self.c.fetchall()
			
		for item in list:
			self.c.execute(u'UPDATE media SET viewed=? WHERE id=?',(1,item[0]))
			if item[1] == D_ERROR:
				self.c.execute(u'UPDATE media SET download_status=? WHERE id=?', (D_NOT_DOWNLOADED,item[0]))
		self.db.commit()
		self.c.execute(u'SELECT id,read FROM entries WHERE feed_id=?',(feed_id,))
		list = self.c.fetchall()
		for item in list:
			if self.entry_flag_cache.has_key(item[0]): 
				del self.entry_flag_cache[item[0]]
	
	def media_exists(self, filename):
		self.c.execute(u'SELECT media.id FROM media WHERE media.file=?',(filename,))
		list=self.c.fetchall()
		if len(list)>1:
			print "WARNING: multiple entries in db for one filename"
		if len(list)==0:
			return False
		return True
		
	def get_unplayed_media_set_viewed(self):
		self.c.execute(u'SELECT media.id, media.entry_id, media.file, entries.feed_id FROM media INNER JOIN entries ON media.entry_id = entries.id WHERE download_status=? AND viewed=0',(D_DOWNLOADED,))
		list=self.c.fetchall()
		playlist=[]
		for item in list:
			self.c.execute(u'UPDATE media SET viewed=1 WHERE id=?',(item[0],))
			self.c.execute(u'UPDATE entries SET new=0 WHERE id=?',(item[1],))		
			self.c.execute(u'UPDATE entries SET read=1 WHERE id=?',(item[1],))	
			if self.entry_flag_cache.has_key(item[1]): del self.entry_flag_cache[item[1]]				
			playlist.append(item[2])
		self.db.commit()
		return playlist 
		
	def pause_all_downloads(self):
		self.c.execute(u'SELECT entry_id FROM media WHERE download_status=?',(D_DOWNLOADING,))
		list = self.c.fetchall()
		list = utils.uniquer(list)
		if list:
			for e in list:
				if self.entry_flag_cache.has_key(e[0]): del self.entry_flag_cache[e[0]]
			self.c.execute(u'UPDATE media SET viewed = 0 WHERE download_status=?',(D_DOWNLOADING,))
			self.c.execute(u'UPDATE media SET download_status=? WHERE download_status=?',(D_RESUMABLE,D_DOWNLOADING))
			self.db.commit()
		
	def get_entry_download_status(self, entry_id, c=None):
		if c == None:
			c = self.c
		c.execute(u'SELECT media.download_status, media.viewed FROM media INNER JOIN entries ON media.entry_id=entries.id WHERE media.download_status!=0 AND entries.id=?',(entry_id,))
		result = c.fetchall()
		#if entry_id==262:
		#	print result
		
		if result: 
			dataList = [list(row) for row in result]
		else:
			return 0
		for datum in dataList:
			val = int(datum[0])
			if val==D_DOWNLOADING:
				return D_DOWNLOADING
			if val==D_ERROR:
				return D_ERROR
			if val==D_RESUMABLE:
				return D_RESUMABLE
		return D_DOWNLOADED		
		
	def get_feed_poll_fail(self, feed_id,c=None):
		if c is None:
			c = self.c
		feed_id = self.resolve_pointed_feed(feed_id, c)
	
		c.execute(u'SELECT pollfail FROM feeds WHERE id=?',(feed_id,))
		result = c.fetchone()[0]
		if result==0:
			return False
		return True

	def get_feed_download_status(self, feed_id):
		#feed_id = self.resolve_pointed_feed(feed_id)
			
		entrylist = self.get_entrylist(feed_id)
		for entry in entrylist:
			status = self.get_entry_download_status(entry[0])
			if status!=D_NOT_DOWNLOADED:
				return status
		return D_NOT_DOWNLOADED
		
	def get_feed_verbose(self, feed_id):
		"""This function is slow, but all of the time is in the execute and fetchall calls.  I can't even speed
		   it up if I do my own sort.  profilers don't lie!"""
		feed_info = {}
		
		is_filter = self.is_feed_filter(feed_id)
		
		if is_filter or self.cache_dirty:
			if is_filter:
				entries = self.get_entrylist(feed_id) #gets search...
				read_status = []
				for e in entries:
					self.c.execute(u'SELECT read FROM entries WHERE id=?',(e[0],))
					result = self.c.fetchone()
					if result: read_status.append(result)
				entry_list = read_status
			else:
				self.c.execute("""SELECT read FROM entries WHERE feed_id=?""",(feed_id,))
				entry_list = self.c.fetchall()
			unread=0
			for item in entry_list:
				if item[0]==0: #read
					unread=unread+1
			feed_info['unread_count'] = unread
			feed_info['entry_count'] = len(entry_list)
			feed_info['important_flag'] = self.get_feed_flag(feed_id)  #not much speeding up this	
		else:
			self.c.execute(u'SELECT flag_cache, unread_count_cache, entry_count_cache FROM feeds WHERE id=?',(feed_id,))
			cached_info = self.c.fetchone()
			feed_info['important_flag'] = cached_info[0]
			feed_info['unread_count'] = cached_info[1]
			feed_info['entry_count'] = cached_info[2]
		
		self.c.execute(u'SELECT pollfail FROM feeds WHERE id=?',(feed_id,))
		result = self.c.fetchone()[0]
		if result==0:
			feed_info['poll_fail'] = False
		else:
			feed_info['poll_fail'] = True
		return feed_info
	
	def get_entry_flag(self, entry_id, c=None):
		if self.entry_flag_cache.has_key(entry_id):
			#print "cache hit "+str(entry_id)
			return self.entry_flag_cache[entry_id]
		#print "cache miss "+str(entry_id)

		if c == None:
			c = self.c
			
		importance=0
		status = self.get_entry_download_status(entry_id,c)
		
		c.execute(u'SELECT new,read FROM entries WHERE id=?',(entry_id,))
		temp = c.fetchone()
		new=temp[0]
		read=temp[1]
		
		medialist = self.get_entry_media(entry_id,c)
		
		if status==-1:
			importance=importance+F_ERROR
		if status==1:
			importance=importance+F_DOWNLOADING		
		if new==1:
			importance=importance+F_NEW
				
		if medialist:	
			importance=importance+F_MEDIA
			if status==2:
				importance=importance+F_DOWNLOADED
			elif status==3:
				importance=importance+F_PAUSED
			for medium in medialist:
				if medium['viewed']==0:
					importance=importance+F_UNVIEWED
					break
		else:
			if int(read)==0:
				importance=importance+F_UNVIEWED
		
		self.entry_flag_cache[entry_id] = importance
		return importance		
		
	def get_unread_count(self, feed_id, c=None):
		if c is None:
			c = self.c
		if self.filtered_entries.has_key(feed_id):
			entries = self.filtered_entries[feed_id]
			list = []
			for entry in entries:
				c.execute(u'SELECT read FROM entries WHERE id=?',(entry[0],))
				try:
					list.append(c.fetchone())
				except:
					pass
		else:
			feed_id = self.resolve_pointed_feed(feed_id, c)		
			c.execute(u'SELECT read FROM entries WHERE feed_id=?',(feed_id,))
			list = c.fetchall()
		unread=0
		for item in list:
			if item[0]==0:
				unread=unread+1
		return unread
		
	def correct_unread_count(self, feed_id): #FIXME: we shouldn't need this one day
		""" Set the entry_read flag to the correct value based on all its enclosures.
			This is necessary because there are some bugs with regard to when this
			value gets set. """
		if self.filtered_entries.has_key(feed_id):
			return #just don't do anything
		#feed_id = self.resolve_pointed_feed(feed_id)
			
		entrylist = self.get_entrylist(feed_id)
		if entrylist:
			for entry in entrylist:
				flag = self.get_entry_flag(entry[0])
				if flag & F_UNVIEWED:
					self.set_entry_read(entry[0],False)
				else:
					self.set_entry_read(entry[0],True)
					
	def get_entry_flags(self, feed_id, c=None):
		if c is None:
			c = self.c
		#c.execute(u'SELECT feed_pointer, description FROM feeds WHERE id=?',(feed_id,))
		#result = c.fetchone()
		#if result[0] >= 0:
		if self.filtered_entries.has_key(feed_id):
			entrylist = [e[0] for e in self.filtered_entries[feed_id]]
			#entrylist = self.search(result[1], feed_id)
			#entrylist = [e[0] for e in entrylist]
		else:
			c.execute(u'SELECT id FROM entries WHERE feed_id=?',(feed_id,))
			entrylist = c.fetchall()
			entrylist = [e[0] for e in entrylist]
		flaglist = []
		for entry in entrylist:
			flaglist.append(self.get_entry_flag(entry,c))
		return flaglist
	
	def get_feed_flag(self, feed_id):#, c=None):
		""" Based on a feed, what flag best represents the overall status of the feed at top-level?
			This is based on the numeric value of the flag, which is why flags are enumed the way they are."""
			
		feed_has_media=0
		flaglist = self.get_entry_flags(feed_id)
		
		if len(flaglist)==0:
			return 0
		flaglist.sort()#lambda x,y:x[1]-y[1])
		best_flag = flaglist[-1]
		
		if best_flag & F_DOWNLOADED == 0 and feed_has_media==1:
			return best_flag + F_DOWNLOADED
		else:
			return best_flag
	
	def get_feeds_for_tag(self, tag):
		self.c.execute(u'SELECT feeds.id FROM feeds INNER JOIN tags ON tags.feed_id=feeds.id WHERE tag=?',(tag,))
		result = self.c.fetchall()
		return [r[0] for r in result]
			
	def get_tags_for_feed(self, feed_id):
		self.c.execute(u'SELECT tag FROM tags WHERE feed_id=? ORDER BY tag',(feed_id,))
		result = self.c.fetchall()
		dataList = []
		if result: 
			dataList = [row[0] for row in result]
		else:
			return
		return dataList
		
	def get_search_tag(self, tag):
		self.c.execute(u'SELECT query FROM tags WHERE tag=?',(tag,))
		result = self.c.fetchone()
		if result: 
			return result[0]
		return None
		
	def get_search_tags(self):
		self.c.execute(u'SELECT tag,query FROM tags WHERE type=? ORDER BY tag',(T_SEARCH,))
		result = self.c.fetchall()
		if result:
			return result
		return None
	
	def add_tag_for_feed(self, feed_id, tag):
		current_tags = self.get_tags_for_feed(feed_id)
		if current_tags:
			if tag not in current_tags and len(tag)>0:
				self.c.execute(u'INSERT INTO tags (tag, feed_id, type) VALUES (?,?,?)',(tag,feed_id, T_TAG))
				self.db.commit()
		else:
			self.c.execute(u'INSERT INTO tags (tag, feed_id, type) VALUES (?,?,?)',(tag,feed_id, T_TAG))
			self.db.commit()
		if tag == NOSEARCH:
			self.blacklist = self.get_tags_for_feed(NOSEARCH)
			
	def fix_tags(self):
		self.c.execute(u'DELETE FROM tags WHERE tag=""')
		self.db.commit()
			
	def add_search_tag(self, query, tag):
		current_tags = self.get_all_tags(T_ALL)
		if current_tags:
			if tag not in current_tags:
				self.c.execute(u'INSERT INTO tags (tag, feed_id, query, type) VALUES (?,?,?,?)',(tag,0,query,T_SEARCH))
				self.db.commit()
			else:
				raise TagAlreadyExists,"The tag name "+str(tag)+" is already being used"
		else:
			self.c.execute(u'INSERT INTO tags (tag, feed_id, query, type) VALUES (?,?,?,?)',(tag,0,query,T_SEARCH))
			self.db.commit()	
	
	def change_query_for_tag(self, tag, query):
		try:
			self.c.execute(u'UPDATE tags SET query=? WHERE tag=?',(query,tag))
			self.db.commit()
		except:
			print "error updating tag"

	def rename_tag(self, old_tag, new_tag):
		self.c.execute(u'UPDATE tags SET tag=? WHERE tag=?',(new_tag,old_tag))
		self.db.commit()
		if new_tag == NOSEARCH or old_tag == NOSEARCH:
			self.blacklist=self.get_tags_for_feed(NOSEARCH)

		
	def remove_tag_from_feed(self, feed_id, tag):
		self.c.execute(u'DELETE FROM tags WHERE tag=? AND feed_id=?',(tag,feed_id))
		self.db.commit()
		if tag == NOSEARCH:
			self.blacklist=self.get_tags_for_feed(NOSEARCH)
		
	def remove_tag(self, tag):
		self.c.execute(u'DELETE FROM tags WHERE tag=?',(tag,))
		self.db.commit()
		if tag == NOSEARCH:
			self.blacklist=self.get_tags_for_feed(NOSEARCH)
		
	def get_all_tags(self, type=T_TAG):
		if type==T_ALL:
			self.c.execute(u'SELECT DISTINCT tag FROM tags ORDER BY tag')
		elif type==T_TAG:
			self.c.execute(u'SELECT DISTINCT tag FROM tags WHERE type=? ORDER BY tag',(T_TAG,))
		elif type==T_SEARCH:
			self.c.execute(u'SELECT DISTINCT tag FROM tags WHERE type=? ORDER BY tag',(T_SEARCH,))
		result = self.c.fetchall()
		dataList = []
		if result: 
			dataList = [row[0] for row in result]
		else:
			return None
		return dataList
	
	def get_count_for_tag(self, tag):
		self.c.execute(u'SELECT feed_id FROM tags WHERE tag=?',(tag,))
		result = self.c.fetchall()
		return len(result)
		
	def export_OPML(self,stream):
		self.c.execute(u'SELECT title, description, url FROM feeds ORDER BY UPPER(title)')
		result = self.c.fetchall()
		dataList = []
		if result: 
			dataList = [list(row) for row in result]
		else:
			return
		
		o = OPML.OPML()
		o['title']='All'
		for feed in result:
			item = OPML.Outline()
			item['title']=self.ascii(feed[0])
			item['text']=self.ascii(feed[0])
			item['description']=self.ascii(feed[1])
			item['xmlUrl']=feed[2]
			o.outlines.append(item)
		o.output(stream)
		stream.close()
		
	def import_OPML(self, stream):
		"""A generator which first yields the number of feeds, and then the feedids as they
		are inserted, and finally -1 on completion"""
		
		try:
			p = OPML.parse(stream)
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			error_msg = ""
			for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
				error_msg += s
			print error_msg
			stream.close()
			yield (-1,0)
		added_feeds=[]
		yield (1,len(p.outlines))
		for o in OPML.outline_generator(p.outlines):
			try:
				feed_id=self.insertURL(o['xmlUrl'],o['text'])
				#added_feeds.append(feed_id)
				yield (1,feed_id)
			except FeedAlreadyExists, f:
				yield (0,f.feed)
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				error_msg = ""
				for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
					error_msg += s
				print error_msg
				yield (-1,0)
		stream.close()
		#return added_feeds
		yield (-1,0)
		
	def search(self, query, filter_feed=None, blacklist=None, since=0):
		if blacklist is None:
			blacklist = self.blacklist
		#print blacklist
		if filter_feed: #no blacklist on filter feeds (doesn't make sense)
			#print "no blacklist"
			return self.searcher.Search("feed_id:"+str(filter_feed)+" AND "+query, since=since)
		return self.searcher.Search(query,blacklist, since=since)
		
	def doindex(self, callback=None):
		self.searcher.Do_Index_Threaded(callback)
		
	def reindex(self, feed_list=[], entry_list=[]):
		"""reindex self.reindex_feed_list and self.reindex_entry_list as well as anything specified"""
		feed_list += self.reindex_feed_list
		entry_list += self.reindex_entry_list
		self.searcher.Re_Index_Threaded(feed_list, entry_list)
		self.reindex_feed_list = []
		self.reindex_entry_list = []
		
	def maybe_write_term_frequency_table(self):
		try:
			self.c.execute(u'SELECT value FROM settings WHERE data="frequency_table_update"')
			last_update = self.c.fetchone()
			if last_update is None:
				print "nothing there"
				self.c.execute(u'INSERT INTO settings (data, value) VALUES ("frequency_table_update",?)',(time.time(),))
				self.db.commit()
				return
			last_update = last_update[0]
			if time.time() - last_update >= 60*60*24:
				print "writing table"
				self.write_term_frequency_table()
			else:
				print "not writing table"
		except Exception, e:
			print e
		
	def write_term_frequency_table(self):
		terms = self.searcher.get_popular_terms(max_terms=0,fields=['entry_title','entry_description'])
		f = open(self.home+"/.penguintv/pop_search_terms.pickle","w")
		pickle.dump(terms,f)
		f.close()
		#self.c.execute(u'DELETE FROM terms')
		#i=-1
		#for t in terms:
		#	i+=1
		#	self.c.execute(u'INSERT INTO terms (term, frequency) VALUES (?,?)',(t[0],t[1]))
		#self.c.execute(u'UPDATE settings SET value=? WHERE data="frequency_table_update"',(time.time(),))
		#self.db.commit()
		
	def get_recent_popular_terms(self):
		pop_terms = []
		f = open(self.home+"/.penguintv/pop_search_terms.pickle")
		old_terms = pickle.load(f)
		#old_terms = old_terms[:100]
		#print old_terms
		#self.c.execute(u'SELECT term,frequency FROM terms')	
		#old_terms = self.c.fetchall()
		#old_terms_index = [t[0] for t in old_terms]
		if old_terms is None:
			print "no old terms found"
			return []
		new_terms = self.searcher.get_popular_terms(max_terms=0,fields=['entry_title','entry_description'])
		#new_terms_index = [t[0] for t in new_terms]
		simple_pop = []
		i=-1
		j=0
		#print old_terms
		#print new_terms
		for term,freq in new_terms:
			i+=1
			differential = 0
			#print "looking for",term,i,j
			if j < len(old_terms):
				#print "searching"
				while old_terms[j][0] < term:			
					j+=1
					if j >= len(old_terms):
						break
			if j >= len(old_terms): #don't use else, i might have changed
				differential = freq
				###pop_terms.append((new_terms[i][0],new_terms[i][1], float(differential)*100.0/float(new_terms[i][1])))
			elif term == old_terms[j][0]:
				#print "equal!",term,old_terms[j][0]				
				differential = freq - old_terms[j][1]
			###if differential>0:
				###pop_terms.append((new_terms[i][0],new_terms[i][1], float(differential)*100.0/float(new_terms[i][1])))
			if freq<10 and freq>=0:
				if differential>=3:
					pop_terms.append((new_terms[i][0],new_terms[i][1], float(differential)/float(old_terms[j][1])))
			elif freq>=0:
				if differential >= freq/2:
					pop_terms.append((new_terms[i][0],new_terms[i][1], float(differential)/float(old_terms[j][1])))

		#simple_pop.sort(lambda x,y: int(x[2]-y[2]))
		pop_terms.sort(lambda x,y: int(x[2]-y[2]))
		#print len(simple_pop)
		#for item in simple_pop:
		#	print item
		print "-="*20+"-"
		#print pop_terms
		#print "-="*20+"-"
		#for item in pop_terms:
		#	print item
		since = time.time()-60*60*6 #last six hours
		new_pop = []
		print len(pop_terms)
		for term,freq,rank in pop_terms:
			result = self.search(term, since=since)
			#breadth = len(result[0])*5+len(result[1]) #number of feeds is important
			f_breadth = len(result[0])
			e_breadth = len(result[1])
			#new_pop.append((term,freq,rank, len(result[0]), len(result[1]), 0.6*f_breadth+.8*e_breadth+0.1*rank))
			new_pop.append((term,result[0],result[1], 0.6*f_breadth+.8*e_breadth+0.1*rank))
			#print pop_terms[i]
		new_pop.sort(lambda x,y: int(x[-1]-y[-1]))
		#for item in new_pop:
		#	print item	
		new_pop.reverse()
		new_pop = new_pop[0:20]
		print len(new_pop)
		pop_feeds = []
		pop_entries = []
		for pop in new_pop:
			pop_feeds+=pop[1]
			pop_entries+=pop[2]
		pop_feeds = utils.uniquer(pop_feeds)
		pop_entries = utils.uniquer(pop_entries)
		print len(pop_feeds)
		for i in pop_feeds:
			print i
		for i in pop_entries:
			print i
		
			
		
	def resolve_pointed_feed(self, feed_id, c=None):
		if c is None:
			c = self.c
		c.execute(u'SELECT feed_pointer FROM feeds WHERE id=?',(feed_id,))
		result = c.fetchone()[0]
		if result >= 0:
			return result
		return feed_id
		
	def is_feed_filter(self, feed_id, c=None):
		if c is None:
			c = self.c
		c.execute(u'SELECT feed_pointer FROM feeds WHERE id=?',(feed_id,))
		result = c.fetchone()[0]
		if result >= 0:
			return True
		return False
		
	def get_pointer_feeds(self, feed_id, c=None):
		if c is None:
			c = self.c
		c.execute(u'SELECT id FROM feeds WHERE feed_pointer=?',(feed_id,))
		results = c.fetchall()
		if results is None:
			return []
		return [f[0] for f in results]
		
	#############convenience Functions####################3
		
	def encode_text(self,text):
		try:
			return text.encode('utf8')
		except:
			return u''
	
	def ascii(self, text):
		try:
			return text.encode('ascii','replace')
		except UnicodeDecodeError:
			return u''

	def DEBUG_get_full_feedlist(self):
		self.c.execute("""SELECT id,title,url FROM feeds ORDER BY id""")
		result = self.c.fetchall()
		return result
					
	def DEBUG_reset_freqs(self):
		self.c.execute('UPDATE feeds SET pollfreq=1800')
		self.db.commit()	
	
	def DEBUG_get_freqs(self):
		self.c.execute('SELECT title, pollfreq, lastpoll, id  FROM feeds ORDER BY title')
		a = self.c.fetchall()
		max_len = 0
		for item in a:
			if len(item[0]) > max_len:
				max_len = len(item[0])
		for item in a:
			try:
			#item2=(str(item[0]),item[1]/(60),time.asctime(time.localtime(item[2])))
				print self.ascii(item[0])+" "*(max_len-len(str(item[0])))+" "+str(item[1]/60)+"       "+time.asctime(time.localtime(item[2]))+" "+str(item[3])
			except:
				print "whoops: "+ self.ascii(item[0]) 

			#print item2
		print "-"*80
		self.c.execute('SELECT title, pollfreq, lastpoll, id FROM feeds ORDER BY lastpoll')
		a = self.c.fetchall()
		max_len = 0
		for item in a:
			if len(item[0]) > max_len:
				max_len = len(item[0])
		for item in a:
			try:
			#item2=(str(item[0]),item[1]/(60),time.asctime(time.localtime(item[2])))
				print self.ascii(item[0])+" "*(max_len-len(str(item[0])))+" "+str(item[1]/60)+"       "+time.asctime(time.localtime(item[2]))+" "+ str(item[3])
			except:
				print "whoops: "+ self.ascii(item[0])
			#print item2
			
		print "-"*80
		self.c.execute('SELECT title, pollfreq, lastpoll, id FROM feeds ORDER BY pollfreq')
		a = self.c.fetchall()
		a.reverse()
		max_len = 0
		for item in a:
			if len(item[0]) > max_len:
				max_len = len(item[0])
		for item in a:
			try:
			#item2=(str(item[0]),item[1]/(60),time.asctime(time.localtime(item[2])))
				print self.ascii(item[0])+" "*(max_len-len(self.ascii(item[0])))+" "+str(item[1]/60)+"       "+time.asctime(time.localtime(item[2]))+" "+ str(item[3])
			except:
				print "whoops: "+ self.ascii(item[0])
			#print item2
			
	def DEBUG_delete_all_media(self):		
		self.c.execute(u'UPDATE media SET download_status=?',(D_NOT_DOWNLOADED,))
		self.db.commit()
		
	def DEBUG_correct_feed(self, feed_id):
		self.c.execute(u'SELECT media.download_status, media.viewed, media.entry_id, media.id FROM media,entries WHERE media.entry_id=entries.id AND media.download_status!=? AND entries.feed_id=?',(D_NOT_DOWNLOADED,feed_id))
		media = self.c.fetchall()
		for item in media:
			self.set_entry_read(item[2],item[1])				
	
class NoFeed(Exception):
	def __init__(self,feed):
		self.feed = feed
	def __str__(self):
		return self.feed
		
class FeedPollError(Exception):
	def __init__(self,feed,message="unspecified error"):
		self.feed = feed
		self.message = message
	def __str__(self):
		return str(self.feed)+": "+self.message
		
class NoEntry(Exception):
	def __init__(self,entry):
		self.entry = entry
	def __str__(self):
		return self.entry
		
class NoSetting(Exception):
	def __init__(self,setting):
		self.setting = setting
	def __str__(self):
		return self.setting
		
class DBError(Exception):
	def __init__(self,error):
		self.error = error
	def __str__(self):
		return self.error
		
class FeedAlreadyExists(Exception):
	def __init__(self,feed):
		self.feed = feed
	def __str__(self):
		return self.feed
		
class TagAlreadyExists(Exception):
	def __init__(self,tag):
		self.tag = tag
	def __str__(self):
		return self.tag
		
class BadSearchResults(Exception):
	def __init__(self,m):
		self.m = m
	def __str__(self):
		return self.m
