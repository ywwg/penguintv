# Written by Owen Williams
# see LICENSE for license information

from pysqlite2 import dbapi2 as sqlite
from math import floor,ceil
from random import randint
#import feedparser  loaded when needed
import time
import string
import sha
import urllib #, urlparse loaded as needed
from urllib2 import URLError
from types import *
import threading
import ThreadPool
import sys, os, os.path, re, traceback, shutil
import gc
import glob
import locale
import gettext
import sets
import traceback

import socket
socket.setdefaulttimeout(30.0)

locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

import IconManager
import utils
if utils.HAS_LUCENE:
	import Lucene
if utils.HAS_GCONF:
	import gconf
	import gobject
if utils.HAS_PYXML:
	import OPML
if utils.RUNNING_SUGAR:
	USING_FLAG_CACHE = False
else:
	USING_FLAG_CACHE = True
#USING_FLAG_CACHE = False
	
NEW = 0
EXISTS = 1
MODIFIED = 2
DELETED = 3

BOOL    = 1
INT     = 2
STRING  = 3

if utils.RUNNING_SUGAR:
	MAX_ARTICLES = 50
else:
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
NOAUTOEXPIRE="noautoexpire"
NOTIFYUPDATES="notify"

DB_FILE="penguintv3.db"

from HTMLParser import HTMLParser
from formatter import NullFormatter

class ptvDB:
	entry_flag_cache = {}
	
	def __init__(self, polling_callback=None):#,username,password):	
		if utils.RUNNING_SUGAR:
			import sugar.env
			self.home = os.path.join(sugar.env.get_profile_path(), 'penguintv')
		else:
			self.home = os.path.join(os.getenv('HOME'), ".penguintv")
		try:
			os.stat(self.home)
		except:
			try:
				os.mkdir(self.home)
			except:
				raise DBError, "error creating directories: "+self.home
		try:	
			#also change db connection in pool poll
			if os.path.isfile(os.path.join(self.home,"penguintv3.db")) == False:
				if os.path.isfile(os.path.join(self.home,"penguintv2.db")):
					try: 
						shutil.copyfile(os.path.join(self.home,"penguintv2.db"), os.path.join(self.home,"penguintv3.db"))
					except:
						raise DBError,"couldn't create new database file"
				elif os.path.isfile(os.path.join(self.home,"penguintv.db")):
					try: 
						shutil.copyfile(os.path.join(self.home,"penguintv.db"), os.path.join(self.home,"penguintv3.db"))
					except:
						raise DBError,"couldn't create new database file"
			self._db=sqlite.connect(os.path.join(self.home,"penguintv3.db"), timeout=10	)
			self._db.isolation_level="DEFERRED"
		except:
			raise DBError,"error connecting to database"
		
		self._c = self._db.cursor()
		self._c.execute('PRAGMA synchronous="NORMAL"')
		self.cache_dirty = True
		try:
			#self._db_execute(self._c, u'SELECT value FROM settings WHERE data="feed_cache_dirty"')
			#if self._c.fetchone()[0] == 0:
			#	self.cache_dirty = False
			self.cache_dirty = self.get_setting(BOOL, "feed_cache_dirty", True)
		except:
			pass
			
		self._exiting = False
		self._cancel_poll_multiple = False
			
		if polling_callback==None:
			self.polling_callback=self._polling_callback
		else:
			self.polling_callback = polling_callback		
			
		if utils.HAS_LUCENE:
			self.searcher = Lucene.Lucene()
			
		if utils.HAS_GCONF:
			self._conf = gconf.client_get_default()
			
		self._icon_manager = IconManager.IconManager(self.home)
			
		try:
			self._blacklist = self.get_feeds_for_tag(NOSEARCH)
		except:
			self._blacklist = []
		self._reindex_entry_list = []
		self._reindex_feed_list = []
		self._filtered_entries = {}
		self._parse_list = []
		
	def _db_execute(self, c, command, args=()):
		#if "MEDIA" in command.upper() and "SELECT" not in command.upper(): 
		#traceback.print_stack()
		#print command, args
		try:
			return c.execute(command, args)
		except Exception, e:
			print "Database error:",
			print command, args
			raise e
				
	def __del__(self):
		self.finish()
		
	def finish(self):
		self._exiting=True
		if utils.HAS_LUCENE:
			if len(self._reindex_entry_list) > 0 or len(self._reindex_feed_list) > 0:
				print "have leftover things to reindex, reindexing"
				#don't do it threadedly or else we will interrupt it on the next line
				self.reindex(threaded=False) #it's usually not much...
			self.searcher.finish(False)
		#FIXME: lame, but I'm being lazy
		if randint(1,10) == 1:
			print "compacting database"
			self._c.execute('VACUUM')
			self._c.close()
			self._db.close()

	def maybe_initialize_db(self):
		try:
			self._db_execute(self._c, u'SELECT * FROM feeds')
		except:
			print "create a database"
			self._init_database()
			return True	
			
		try:
			#self._db_execute(self._c, u'SELECT value FROM settings WHERE data="db_ver"')
			#db_ver = self._c.fetchone()
			#db_ver = db_ver[0]
			db_ver = self.get_setting(INT, "db_ver")
			#print "current database version is",db_ver
			if db_ver is None:
				self._migrate_database_one_two()
				self._migrate_database_two_three()
				self._migrate_database_three_four()
				#self.clean_database_media()
			elif db_ver < 2:
				self._migrate_database_one_two()
				self._migrate_database_two_three()
				self._migrate_database_three_four()
				self.clean_database_media()
			elif db_ver < 3:
				self._migrate_database_two_three()
				self._migrate_database_three_four()
				self.clean_database_media()
			elif db_ver < 4:
				self._migrate_database_three_four()
				self.clean_database_media()
			elif db_ver > 4:
				print "WARNING: This database comes from a later version of PenguinTV and may not work with this version"
				raise DBError, "db_ver is "+str(db_ver)+" instead of 4"
		except Exception, e:
			print "exception:",e
			self._migrate_database_one_two()
			self._migrate_database_two_three()
			#self._migrate_database_three_four()
			
		#if self.searcher.needs_index:
		#	print "indexing for the first time"
		#	self.searcher.Do_Index_Threaded()
			
		self.fix_tags()
		return False
			
	def _migrate_database_one_two(self):
		#add table settings
		print "upgrading to database schema 2"
		try:
			self._db_execute(self._c, u'SELECT * FROM settings')  #if it doesn't exist, 
		except:                                        #we create it
			self._db_execute(self._c, u"""CREATE TABLE settings   
(
	id INTEGER PRIMARY KEY,
    data NOT NULL,
	value
	);""")
	
		self._db_execute(self._c, u"""CREATE TABLE tags
		(
		id INTEGER PRIMARY KEY,
		tag,
		feed_id INT UNSIGNED NOT NULL);""")
		
		
		#add fake_date column
		try:
			self._db_execute(self._c, u'ALTER TABLE entries ADD COLUMN fakedate DATE')
			self._db_execute(self._c, u'UPDATE entries SET fakedate = date')
		except sqlite.OperationalError,e:
			if e != "duplicate column name: fakedate":
				print e #else pass
			#change db_ver (last thing)
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN pollfreq INT')
		self._db_execute(self._c, u'UPDATE feeds SET pollfreq=1800')
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN lastpoll DATE')
		self._db_execute(self._c, u'UPDATE feeds SET lastpoll=?',(time.time()-(30*60),))
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN newatlast INT')
		self._db_execute(self._c, u'UPDATE feeds SET newatlast=0')
   
		try:
			self._db_execute(self._c, u'INSERT INTO settings (data, value) VALUES ("db_ver",2)')
		except:
			pass
		try:
			self._db_execute(self._c, u'UPDATE settings SET value=2 WHERE data="db_ver"')
		except:
			pass
		self._db.commit()
			
	def _migrate_database_two_three(self):
		"""version 3 added flag cache, entry_count_cache, and unread_count_cache"""
		print "upgrading to database schema 3"
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN flag_cache INT')
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN entry_count_cache INT')
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN unread_count_cache INT')
		
		self._db_execute(self._c, u'UPDATE settings SET value=3 WHERE data="db_ver"')
		self._db_execute(self._c, u'INSERT INTO settings (data, value) VALUES ("feed_cache_dirty",1)')
		self._db.commit()
		
	def _migrate_database_three_four(self):
		"""version 4 adds fulltext table"""
		print "upgrading to database schema 4"
		self._db_execute(self._c, u'ALTER TABLE tags ADD COLUMN type INT')
		self._db_execute(self._c, u'ALTER TABLE tags ADD COLUMN query')
		self._db_execute(self._c, u'ALTER TABLE tags ADD COLUMN favorite INT')
		self._db_execute(self._c, u'UPDATE tags SET type=?',(T_TAG,)) #they must all be regular tags right now
		self._db_execute(self._c, u'UPDATE settings SET value=4 WHERE data="db_ver"')
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN feed_pointer INT')
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN link')
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN image')
		self._db_execute(self._c, u'ALTER TABLE media ADD COLUMN download_date DATE')
		self._db_execute(self._c, u'ALTER TABLE media ADD COLUMN thumbnail')
		self._db_execute(self._c, u'ALTER TABLE media ADD COLUMN feed_id INTEGER')
		
		self._db_execute(self._c, u'UPDATE feeds SET feed_pointer=-1') #no filters yet!
		self._db_execute(self._c, u'UPDATE feeds SET link=""')
		self._db_execute(self._c, u"""CREATE TABLE terms
							(
							id INTEGER PRIMARY KEY,
							term,
							frequency INT);""")
		self._db_execute(self._c, u'INSERT INTO settings (data, value) VALUES ("frequency_table_update",0)')
		self._db.commit()
		
		print "building new column, please wait..."
		self._db_execute(self._c, u'SELECT id FROM feeds')
		for feed_id, in self._c.fetchall():
			self._db_execute(self._c, u'SELECT media.id FROM entries INNER JOIN media ON media.entry_id = entries.id WHERE entries.feed_id=?', (feed_id,))
			media = self._c.fetchall()
			media = [m[0] for m in media]
			if len(media) > 0:
				qmarks = "?,"*(len(media)-1)+"?"
				self._db_execute(self._c, u'UPDATE media SET feed_id=? WHERE id IN ('+qmarks+')', tuple([feed_id] + media))

		self._db.commit()
		print "done"
		
	def _init_database(self):
		try:
			self._db_execute(self._c, u'DROP TABLE settings')
		except:
			pass	
			
		try:
			self._db_execute(self._c, u'DROP TABLE feeds')
		except:
			pass
			
		try:
			self._db_execute(self._c, u'DROP TABLE entries')
		except:
			pass
			
		try:
			self._db_execute(self._c, u'DROP TABLE media')
		except:
			pass
			
		try:
			self._db_execute(self._c, u'DROP TABLE fulltext')
		except:
			pass
			
		self._db_execute(self._c, u"""CREATE TABLE settings
							(
								id INTEGER PRIMARY KEY,
							    data NOT NULL,
								value
								);""")

		#for pointer / pointed filter feeds, feed_pointer is feed_id, and description is query
		self._db_execute(self._c, u"""CREATE TABLE  feeds
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
							    image,
							    UNIQUE(url)
							);""")
							
		#the new column is no longer used, but I can't get rid of it
		self._db_execute(self._c, u"""CREATE TABLE entries
							(
							    id INTEGER PRIMARY KEY,
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
		self._db_execute(self._c, u"""CREATE TABLE media
							(
								id INTEGER  PRIMARY KEY,
								entry_id INTEGER UNSIGNED NOT NULL,
								feed_id INTEGER UNSIGNED NOT NULL,
								url  NOT NULL,
								file ,
								mimetype ,
								download_status NOT NULL,
								viewed BOOL NOT NULL,
								keep BOOL NOT NULL,
								length,
								download_date DATE, 
								thumbnail,
								UNIQUE(id)
							);
							""")
		self._db_execute(self._c, u"""CREATE TABLE tags
							(
							id INTEGER PRIMARY KEY,
							tag,
							feed_id INT UNSIGNED NOT NULL,
							query,
							favorite INT,
							type INT);""")
							
		self._db_execute(self._c, u"""CREATE TABLE terms
							(
							id INTEGER PRIMARY KEY,
							term,
							frequency INT);""")
							
		self._db.commit()
		
		self._db_execute(self._c, u"""INSERT INTO settings (data, value) VALUES ("db_ver",4)""")
		self._db_execute(self._c, u'INSERT INTO settings (data, value) VALUES ("frequency_table_update",0)')
		self._db.commit()
		
	def clean_database_media(self):
		self._db_execute(self._c, "SELECT id,file,entry_id FROM media")
		result = self._c.fetchall()
		for item in result:
			self._db_execute(self._c, "SELECT title FROM entries WHERE id=?",(item[2],))
			title = self._c.fetchone()
			if title is None: #this entry doesn't exist anymore
				self._db_execute(self._c, "DELETE FROM media WHERE id=?",(item[0],))
		self._db.commit()
	
	#right now this code doesn't get called.  Maybe we should?
	def clean_file_media(self):
		"""walks the media dir, and deletes anything that doesn't have an entry in the database.
		Also deletes dirs with only a playlist or with nothing"""
		media_dir = os.path.join(self.home,"media")
		d = os.walk(media_dir)
		for root,dirs,files in d:
			if root!=media_dir:
				for file in files:
					if file != "playlist.m3u":
						self._db_execute(self._c, u"SELECT id FROM media WHERE file=?",(os.path.join(root, file),))
						result = self._c.fetchone()
						if result is None:
							print "deleting "+os.path.join(root,file)
							os.remove(os.path.join(root,file))
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
					
	def get_setting(self, type, datum, default=None):
		if utils.HAS_GCONF and datum[0] == '/':
			if   type == BOOL:
				retval = self._conf.get_bool(datum)
			elif type == INT:
				retval = self._conf.get_int(datum)
			elif type == STRING:
				retval =  self._conf.get_string(datum)
			if retval is not None:
				return retval
			return default
		else:
			self._db_execute(self._c, u'SELECT value FROM settings WHERE data=?',(datum,))
			retval = self._c.fetchone()
			if retval is not None:
				return retval[0]
			return default
				
	def set_setting(self, type, datum, value):
		if utils.HAS_GCONF and datum[0] == '/':
			if   type == BOOL:
				self._conf.set_bool(datum, value)
			elif type == INT:
				self._conf.set_int(datum, value)
			elif type == STRING:
				self._conf.set_string(datum, value)
		else:
			current_val = self.get_setting(type, datum)
			if current_val is None:
				self._db_execute(self._c, u'INSERT INTO settings (data, value) VALUES (?,?)', (datum, value))
			else:
				self._db_execute(self._c, u'UPDATE settings SET value=? WHERE data=?', (value,datum))
			self._db.commit()
			
	def set_feed_cache(self, cachelist):
		"""Cachelist format:
		   id, flag, unread, total"""
		for cache in cachelist:
			self._db_execute(self._c, u'UPDATE feeds SET flag_cache=? WHERE id=?',(cache[1],cache[0]))
			self._db_execute(self._c, u'UPDATE feeds SET unread_count_cache=? WHERE id=?',(cache[2],cache[0]))
			self._db_execute(self._c, u'UPDATE feeds SET entry_count_cache=? WHERE id=?',(cache[3],cache[0]))
		self._db.commit()
		#and only then...
		self.set_setting(BOOL, "feed_cache_dirty", False)
		#self._db_execute(self._c, u'UPDATE settings SET value=0 WHERE data="feed_cache_dirty"')
		#self._db.commit()
		self.cache_dirty = False
		
	def get_feed_cache(self):
		if self.cache_dirty:
			return None
		self._db_execute(self._c, u'SELECT id, flag_cache, unread_count_cache, entry_count_cache, pollfail FROM feeds ORDER BY UPPER(TITLE)')
		cache = self._c.fetchall()
		self.set_setting(BOOL, "feed_cache_dirty", True)
		#self._db_execute(self._c, u'UPDATE settings SET value=1 WHERE data="feed_cache_dirty"')
		#self._db.commit()
		self.cache_dirty=True
		return cache
		
	def insertURL(self, url,title=None):
		#if a feed with that url doesn't already exists, add it

		self._db_execute(self._c, """SELECT url FROM feeds WHERE url=?""",(url,))
		#on success, fetch will return the url itself
		if self._c.fetchone() != (url,):
			if title is not None:
				self._db_execute(self._c, u"""INSERT INTO feeds (id,title,url,polled,pollfail,modified,pollfreq,lastpoll,newatlast,feed_pointer,image) VALUES (NULL,?, ?,0,0, 0,1800,0,0,-1,"")""", (title,url)) #default 30 minute polling
			else:
				self._db_execute(self._c, u"""INSERT INTO feeds (id,title,url,polled,pollfail,modified,pollfreq,lastpoll,newatlast,feed_pointer,image) VALUES (NULL,?, ?,0,0, 0,1800,0,0,-1,"")""", (url,url)) #default 30 minute polling
			self._db.commit()
			self._db_execute(self._c, u"""SELECT id,url FROM feeds WHERE url=?""",(url,))
			feed_id = self._c.fetchone()
			feed_id = feed_id[0]
			d={ 'title':_("Waiting for first poll"),
				'description':_("This feed has not yet been polled successfully.  There might be an error with this feed.<br>"+str(url)),
			  }
			self._db_execute(self._c, u'INSERT INTO entries (id, feed_id, title, creator, description, read, fakedate, date, guid, link, old, new) VALUES (NULL, ?, ?, NULL, ?, ?, 0, ?, ?, "http://", "0", "0")',(feed_id,d['title'],d['description'],'0',time.time(),time.time()))
			self._db.commit()
		else:
			self._db_execute(self._c, """SELECT id FROM feeds WHERE url=?""",(url,))
			feed_id = self._c.fetchone()
			feed_id = feed_id[0]
			print "db: feed already exists"
			raise FeedAlreadyExists(feed_id)
			
		return feed_id
	
	def add_feed_filter(self, pointed_feed_id, filter_name, query):
		self._db_execute(self._c, u'SELECT id,feed_pointer,description FROM feeds WHERE feed_pointer=? AND description=?',(pointed_feed_id,query))
		result = self._c.fetchone()
		if result is None:
			s = sha.new()
			#this is lame I know.  We shouldn't ever get a collision here though!
			s.update(filter_name+query)
			self._db_execute(self._c, u'INSERT INTO feeds (id,title,url,feed_pointer,description,polled,pollfail,modified,pollfreq,lastpoll,newatlast) VALUES (NULL,?, ?,?,?,0,0, 0,21600,0,0)', (filter_name,s.hexdigest(),pointed_feed_id,query))
			self._db.commit()
			self._db_execute(self._c, u'SELECT id FROM feeds WHERE feed_pointer=? AND description=?',(pointed_feed_id,query))
			return self._c.fetchone()[0]
		else:
			raise FeedAlreadyExists, result[0]
			
	def set_feed_filter(self, pointer_feed_id, filter_name, query):
		self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE id=?',(pointer_feed_id,))
		pointed_id = self._c.fetchone()
		if pointed_id is None:
			raise NoFeed, pointer_feed_id
		pointed_id = pointed_id[0]
		self._db_execute(self._c, u'SELECT id FROM feeds WHERE feed_pointer=? AND description=?',(pointed_id,query))
		result = self._c.fetchone()
		if result is None:
			self._db_execute(self._c, u'UPDATE feeds SET title=?, description=? WHERE id=?',(filter_name, query, pointer_feed_id))
			self._db.commit()
		else:
			raise FeedAlreadyExists, result[0]
				
	def delete_feed(self, feed_id):
		#check for valid entry		
		self._db_execute(self._c, """SELECT id FROM feeds WHERE id=?""",(feed_id,))
		result = self._c.fetchone()[0]

		if result != feed_id:			
			raise NoFeed,feed_id
		
		#delete the feed, its entries, and its media (this does not delete files)
		self._db_execute(self._c, """DELETE FROM feeds WHERE id=?""",(feed_id,))
		self._reindex_feed_list.append(feed_id)
		self._db_execute(self._c, u'DELETE FROM tags WHERE feed_id=?',(feed_id,))
		self._db.commit()
		#result = self._c.fetchone()
		#print(result)
		
		self._icon_manager.remove_icon(feed_id)
		
		self._db_execute(self._c, 'SELECT id FROM entries WHERE feed_id=?',(feed_id,))
		data=self._c.fetchall()
		if data: 
			dataList = [list(row) for row in data]
			for datum in dataList:
				self._db_execute(self._c, 'SELECT id FROM media WHERE entry_id=?',(datum[0],))
				media=self._c.fetchall()
				if media: 
					mediaList = [list(row) for row in media]
					for medium in mediaList:
						self.delete_media(int(medium[0]))
						self._db.commit()
					self._db_execute(self._c, 'DELETE FROM media WHERE entry_id=?',(datum[0],))
			self._reindex_entry_list.append(datum[0])
		self._db_execute(self._c, """DELETE FROM entries WHERE feed_id=?""",(feed_id,))
		self._db.commit()
		
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
		self._db_execute(self._c, """DELETE FROM feeds WHERE title IS NULL""")
		self._db.commit()
		
	def poll_multiple(self, arguments=0, feeds=None):
		"""Polls multiple feeds multithreadedly"""
		successes=[]
		cur_time = time.time()
		
		if feeds is None:
			if arguments & A_AUTOTUNE and arguments & A_ALL_FEEDS == 0:
				self._db_execute(self._c, 'SELECT id FROM feeds WHERE (? - lastpoll) >= pollfreq', (cur_time,))
			elif arguments & A_ERROR_FEEDS:
				self._db_execute(self._c, 'SELECT id FROM feeds WHERE pollfail=1')
			else: #polling all
				self._db_execute(self._c, 'SELECT id FROM feeds')
				
			data=self._c.fetchall()
			if data: 
				feeds = [row[0] for row in data]
			else:
				return
		pool = ThreadPool.ThreadPool(5,"ptvDB", lucene_compat = utils.HAS_LUCENE)
		self._parse_list = []
		for feed in feeds:
			if self._cancel_poll_multiple or self._exiting:
				break
			self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE id=?',(feed,))
			result = self._c.fetchone()[0]
			if result >= 0:
				self._parse_list.append((feed, arguments, len(feeds), -2)) 
				continue
				
			self._db_execute(self._c, """SELECT url,modified,etag FROM feeds WHERE id=?""",(feed,))
			data = self._c.fetchone()
			pool.queueTask(self._pool_poll_feed,(feed,arguments,len(feeds), data),self._poll_mult_cb)
			
		polled = 0
		#grow the cache while we do this operation
		self._db_execute(self._c, 'PRAGMA cache_size=6000')
		while polled < len(feeds):
			if self._exiting:
				break
			if len(self._parse_list) > 0:
				polled+=1
				feed_id, args, total, parsed = self._parse_list.pop(0)
				self.polling_callback(self._process_feed(feed_id, args, total, parsed))
				gc.collect()
			time.sleep(.1)
		self._db_execute(self._c, 'PRAGMA cache_size=2000')
		
		while pool.getTaskCount()>0: #manual joinAll so we can check for exit
			if self._exiting:
				pool.joinAll(False,True)
				self._c.close()
				self._db.close()
				return
			time.sleep(.5)
		pool.joinAll(False,True) #just to make sure I guess
		del pool
		self.reindex()
		self._cancel_poll_multiple = False
		gc.collect()
		
	def interrupt_poll_multiple(self):
		self._cancel_poll_multiple = True
		
	def _poll_mult_cb(self, args):
		feed_id, args, total, parsed = args
		self._parse_list.append((feed_id, args, total, parsed))
		
	def _pool_poll_feed(self, args):
		feed_id, arguments, total, data = args
		url,modified,etag=data
		
		#save ram by not piling up polled data
		if utils.RUNNING_SUGAR:
			parse_list_limit = 2
		else:
			parse_list_limit = 5
		
		while len(self._parse_list) > parse_list_limit:
			time.sleep(1)
		
		try:
			import feedparser
			#feedparser.disableWellFormedCheck=1  #do we still need this?  it used to cause crashes
			if arguments & A_IGNORE_ETAG == A_IGNORE_ETAG:
				data = feedparser.parse(url)
			else:
				data = feedparser.parse(url,etag)
			return (feed_id, arguments, total, data)
		except Exception, e:
			print e
			return (feed_id, arguments, total, -1)

	def _process_feed(self,feed_id, args, total, data, recurse=0):
		"""a wrapper function that returns the index along with the result
		so we can sort.  Each poller needs its own db connection for locking reasons"""
		
		poll_arguments = 0
		result = 0
		try:
			#poll_arguments = args[1]
			if self._exiting:
				return (feed_id,{'pollfail':True}, total)
				
			result = self.poll_feed(feed_id, args, preparsed=data)

			if self._exiting:
				return (feed_id,{'pollfail':True} ,total)
		except sqlite.OperationalError, e:
			print "Database warning...", e
			if recurse < 2:
				time.sleep(5)
				print "trying again..."
				self._db.close()
				self._db=sqlite.connect(os.path.join(self.home,"penguintv3.db"), timeout=10)
				self._c = self._db.cursor()
				return self._process_feed(feed_id, args, total, data, recurse+1) #and reconnect
			print "can't get lock, giving up"
			return (feed_id,{'pollfail':True}, total)
		except FeedPollError,e:
			print e
			return (feed_id,{'pollfail':True}, total)
		except IOError, e:
			print e
			#we got an ioerror, but we won't take it out on the feed
			return (feed_id,{'ioerror':e, 'pollfail':False}, total)
		except:
			print "other error polling feed:",feed_id
			exc_type, exc_value, exc_traceback = sys.exc_info()
			error_msg = ""
			for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
				error_msg += s
			print error_msg
			return (feed_id,{'pollfail':True}, total)
			
		#assemble our handy dictionary while we're in a thread
		update_data={}
		
		if result>0:
			update_data['new_entries'] = result
			if self.is_feed_filter(feed_id):
				entries = self.get_entrylist(feed_id) #reinitialize filtered_entries dict
				update_data['unread_count'] = self.get_unread_count(feed_id)
				flag_list = self.get_entry_flags(feed_id)
				update_data['pollfail']=self.get_feed_poll_fail(self._resolve_pointed_feed(feed_id))
			else:
				self._db_execute(self._c, u'SELECT read FROM entries WHERE feed_id=?',(feed_id,))
				list = self._c.fetchall()
				update_data['unread_count'] = len([item for item in list if item[0]==0])
				update_data['entry_count'] = len(list)
				flag_list = self.get_entry_flags(feed_id)
				
				if len(self.get_pointer_feeds(feed_id)) > 0:
					print "have pointers, reindexing now"
					self.reindex()
					
				update_data['flag_list']=flag_list
				update_data['pollfail']=False
				
		return (feed_id,update_data, total)
			
	def poll_feed_trap_errors(self, feed_id, callback):
		try:
			feed={}
			self._db_execute(self._c, "SELECT title,url FROM feeds WHERE id=?",(feed_id,))
			result = self._c.fetchone()
			feed['feed_id']=feed_id
			feed['title']=result[0]
			feed['url']=result[1]
			feed['new_entries'] = self.poll_feed(feed_id, A_IGNORE_ETAG+A_DO_REINDEX)
			callback(feed, True)
		except Exception, e:#FeedPollError,e:
			print e
			print "error polling feed:"
			exc_type, exc_value, exc_traceback = sys.exc_info()
			error_msg = ""
			for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
				error_msg += s
			print error_msg
			self.reindex()
			callback(feed, False)

	def _polling_callback(self, data):
		print "look a callback"
		print data
		
	def poll_feed(self, feed_id, arguments=0, preparsed=None):
		"""polls a feed and returns the number of new articles and a flag list.  Optionally, one can pass
			a feedparser dictionary in the preparsed argument and avoid network operations"""
		
		#print "poll:",feed_id, arguments
		
		if preparsed is None:
			#feed_id = self._resolve_pointed_feed(feed_id)
			self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE id=?',(feed_id,))
			result =self._c.fetchone()
			if result:
				if result[0] >= 0:
					return 0
				
			self._db_execute(self._c, """SELECT url,modified,etag FROM feeds WHERE id=?""",(feed_id,))
			data = self._c.fetchone()
			url,modified,etag=data
			try:
				import feedparser
				feedparser.disableWellFormedCheck=1  #do we still need this?  it used to cause crashes
				
				#speed up feedparser
				if utils.RUNNING_SUGAR:
					feedparser._sanitizeHTML = lambda a, b: a
					feedparser._resolveRelativeURIs = lambda a, b, c: a
				
				if arguments & A_IGNORE_ETAG == A_IGNORE_ETAG:
					data = feedparser.parse(url)
				else:
					data = feedparser.parse(url,etag)
			except Exception, e:
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					self._set_new_update_freq(feed_id, 0)
				self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
				self._db.commit()
				print e
				raise FeedPollError,(feed_id,"feedparser blew a gasket")
		else:
			if preparsed == -1:
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					self._set_new_update_freq(feed_id, 0)
				self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
				self._db.commit()
				#print "it's -1"
				raise FeedPollError,(feed_id,"feedparser blew a gasket")
			elif preparsed == -2:
				#print "pointer feed, returning 0"
				return 0
			else:
				#print "data is good"
				#need to get a url from somewhere
				data = preparsed
				try:
					url = data['feed']['title_detail']['base']
				except:
					url = feed_id
			
		if data.has_key('status'):
			if data['status'] == 304:  #this means "nothing has changed"
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					self._set_new_update_freq(feed_id, 0)
				self._db_execute(self._c, """UPDATE feeds SET pollfail=0 WHERE id=?""",(feed_id,))
				self._db.commit()
				return 0
			if data['status'] == 404: #whoops
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					self._set_new_update_freq(feed_id, 0)
				self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
				self._db.commit()
				raise FeedPollError,(feed_id,"404 not found: "+str(url))

		if len(data['feed']) == 0 or len(data['items']) == 0:
			if data.has_key('bozo_exception'):
				if isinstance(data['bozo_exception'], URLError):
					e = data['bozo_exception'][0]
					errno = e[0]
					if e[0] in [-3, #failure in name resolution   
								114, #Operation already in progress
								11]:  #Resource temporarily unavailable
						print "ioerror",e,"errno:",e[0]
						raise IOError(e)	
			
			if arguments & A_AUTOTUNE == A_AUTOTUNE:
				self._set_new_update_freq(feed_id, 0)
			self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
			self._db.commit()
			raise FeedPollError,(feed_id,"empty feed")
			
		#else...
		
		#see if we need to get an image
		if not self._icon_manager.icon_exists(feed_id):
			href = self._icon_manager.download_icon(feed_id, data)
			if href is not None:
				self._db_execute(self._c, u"""UPDATE feeds SET image=? WHERE id=?""",(href,feed_id))
				self._db.commit()
		else:
			self._db_execute(self._c, u"""SELECT image FROM feeds WHERE id=?""",(feed_id,))
			try: old_href = self._c.fetchone()[0]
			except: old_href = ""
			
			if not self._icon_manager.is_icon_up_to_date(feed_id, old_href, data):
				self._icon_manager.remove_icon(feed_id)
				href = self._icon_manager.download_icon(feed_id, data)
				if href is not None:
					self._db_execute(self._c, u"""UPDATE feeds SET image=? WHERE id=?""",(href,feed_id))
					self._db.commit()					
		
		if arguments & A_DELETE_ENTRIES == A_DELETE_ENTRIES:
			print "deleting existing entries", feed_id, arguments
			self._db_execute(self._c, """DELETE FROM entries WHERE feed_id=?""",(feed_id,))
			self._db.commit()
		#to discover the old entries, first we mark everything as old
		#later, we well unset this flag for everything that is NEW,
		#MODIFIED, and EXISTS. anything still flagged should be deleted  
		self._db_execute(self._c, """UPDATE entries SET old=1 WHERE feed_id=?""",(feed_id,)) 
		self._db_execute(self._c, """UPDATE feeds SET pollfail=0 WHERE id=?""",(feed_id,))
		self._db.commit()
	
		#normalize results
		channel = data['feed']
		if channel.has_key('description') == 0:
			channel['description']=""
		if len(channel['description']) > 128:
			channel['description'] = channel['description'][0:127]
		channel['description']=self._encode_text(channel['description'])
		if channel.has_key('title') == 0:
			if channel['description'] != "":
				channel['title']=channel['description']
			else:
				channel['title']=url
		channel['title'] = self._encode_text(channel['title'])
		
		#print channel['title']

		if not data.has_key('etag'):
			data['etag']='0'
		if not data.has_key('modified'):
			modified='0'
		else:
			modified = time.mktime(data['modified'])

		try:
			self._db_execute(self._c, u'SELECT title FROM feeds WHERE id=?',(feed_id,))
			exists=self._c.fetchone()
			if len(exists[0])>4:
				if exists[0][0:4]!="http": #hack to detect when the title hasn't been set yet because of first poll
				 	self._db_execute(self._c, """UPDATE feeds SET description=?, modified=?, etag=? WHERE id=?""", (channel['description'], modified,data['etag'],feed_id))
				else:
					self._db_execute(self._c, """UPDATE feeds SET title=?, description=?, modified=?, etag=? WHERE id=?""", (channel['title'],channel['description'], modified,data['etag'],feed_id))
			elif len(exists[0])>0: #don't change title
				if exists[0] is not None:
					self._db_execute(self._c, """UPDATE feeds SET description=?, modified=?, etag=? WHERE id=?""", (channel['description'], modified,data['etag'],feed_id))
				else:
					self._db_execute(self._c, """UPDATE feeds SET title=?, description=?, modified=?, etag=? WHERE id=?""", (channel['title'],channel['description'], modified,data['etag'],feed_id))
			else:
				self._db_execute(self._c, """UPDATE feeds SET title=?, description=?, modified=?, etag=? WHERE id=?""", (channel['title'],channel['description'], modified,data['etag'],feed_id))
			self._reindex_feed_list.append(feed_id)
		except Exception, e:
			print e
			#f = open("/var/log/penguintv.log",'a')
			#f.write("borked on: UPDATE feeds SET title="+str(channel['title'])+", description="+str(channel['description'])+", modified="+str(modified)+", etag="+str(data['etag'])+", pollfail=0 WHERE id="+str(feed_id))
			#f.close()	
			self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE id=?""",(feed_id,))
			self._db.commit()	
			raise FeedPollError,(feed_id,"error updating title and description of feed")
			
		self._db_execute(self._c, u'SELECT link FROM feeds WHERE id=?',(feed_id,))
		link = self._c.fetchone()
		if link is not None:
			link = link[0]
			if link == "" and data['feed'].has_key('link'):
				self._db_execute(self._c, u'UPDATE feeds SET link=? WHERE id=?',(data['feed']['link'],feed_id))
		self._db.commit()
		
		#populate the entries
		self._db_execute(self._c, """SELECT id,guid,link,title,description FROM entries WHERE feed_id=? order by fakedate DESC""",(feed_id,)) 
		existing_entries = self._c.fetchall()
		
		#we can't trust the dates inside the items for timing data
		#bad formats, no dates at all, and timezones screw things up
		#so I introduce a fake date which works for determining read and
		#unread article counts, and keeps the articles in order
		fake_time = time.time()#-len(data['items'])
		i=0
		#try:
		#	if data['items'][0].has_key('updated_parsed') == 1:
		#		data['items'].sort(lambda x,y: int(time.mktime(y['updated_parsed'])-time.mktime(x['updated_parsed'])))
		#except:
		#	try:
		#		if data['items'][0].has_key('modified_parsed') == 1:
		#			data['items'].sort(lambda x,y: int(time.mktime(y['modified_parsed'])-time.mktime(x['modified_parsed'])))
		#	except:
		#		try:
		#			if data['items'][0].has_key('created_parsed') == 1:
		#				data['items'].sort(lambda x,y: int(time.mktime(y['created_parsed'])-time.mktime(x['created_parsed'])))
		#		except:	
		#			try:	
		#				if data['items'][0].has_key('date_parsed') == 1:
		#					data['items'].sort(lambda x,y: int(time.mktime(y['date_parsed'])-time.mktime(x['date_parsed'])))
		#			except:
		#				pass #I feel dirty.
		
		new_items = 0
		
		flag_list = []
		
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
				
			
			item['body']=self._encode_text(item['body'])
			
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

			#let actual entities through, but correct unadorned &s.
			#thanks to http://www.regular-expressions.info/repeat.html#greedy
			#<[^>]+> -> &[^;]+;
			#I wrote: &.+?; which didn't work (matched widest results-- see reference)
			m = re.compile('&[^;]+;').search(item['title'])
			if m is not None: #entity found
				span = m.span()
				if span[1]-span[0] > 10: #unlikely to be an entity
					item['title'] = re.sub('&','&amp;',item['title'])
				#else let it pass
			else:
				item['title'] = re.sub('&','&amp;',item['title'])
			
			if type(item['body']) is str:
				item['body'] = unicode(item['body'],'utf-8')
			for uni in _common_unicode.keys():
				item['body'] = item['body'].replace(uni, _common_unicode[uni])
			
			item['title'] = self._encode_text(item['title'])
			
			if item.has_key('creator') == 0:
				item['creator']=""
			if item.has_key('author') == 1:
				item['creator']=item['author']
			if item.has_key('guid') == 0:
				item['id']=0
				item['guid']='0'
			if item.has_key('link') == 0:
				item['link'] = ""
				
			item['creator']=self._encode_text(item['creator'])
			
			#blow away date_parsed with more recent times
			if item.has_key('updated_parsed'):
				item['date_parsed'] = item['updated_parsed']
			elif item.has_key('modified_parsed'):
				item['date_parsed'] = item['modified_parsed']
			elif item.has_key('created_parsed'):
				item['date_parsed'] = item['created_parsed']
			elif item.has_key('update_parsed'):
				item['date_parsed'] = item['update_parsed']
			
			if not item.has_key('date_parsed') or item['date_parsed'] is None:
				item['date_parsed']=(0,0,0,0,0,0,0,0,0)
				
				
			status = self._get_status(item, existing_entries)
			
			if status[0]==NEW:
				new_items = new_items+1
				self._db_execute(self._c, u'INSERT INTO entries (id, feed_id, title, creator, description, read, fakedate, date, guid, link, old, new) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "0")',(feed_id,item['title'],item['creator'],item['body'],'0',fake_time-i, time.mktime(item['date_parsed']),item['guid'],item['link'],'0'))
				self._db_execute(self._c, """SELECT id FROM entries WHERE fakedate=?""",(fake_time-i,))
				entry_id = self._c.fetchone()[0]

				if item.has_key('enclosures'):
					for media in item['enclosures']:
						media.setdefault('length', 0)
						media.setdefault('type', 'application/octet-stream')
						self._db_execute(self._c, u"""INSERT INTO media (id, entry_id, url, mimetype, download_status, viewed, keep, length, feed_id) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)""", (entry_id, media['url'], media['type'], 0, D_NOT_DOWNLOADED, 0, media['length'], feed_id))
				self._reindex_entry_list.append(entry_id)
			elif status[0]==EXISTS:
				self._db_execute(self._c, """UPDATE entries SET old=0 where id=?""",(status[1],))
			elif status[0]==MODIFIED:
				self._db_execute(self._c, u'UPDATE entries SET title=?, creator=?, description=?, date=?, guid=?, link=?, old=?  WHERE id=?',
								 (item['title'],item['creator'],item['body'], 
								 time.mktime(item['date_parsed']),item['guid'],item['link'],'0', status[1]))
				if self.entry_flag_cache.has_key(status[1]): del self.entry_flag_cache[status[1]]
				if item.has_key('enclosures'):
					#self._db_execute(self._c, u'SELECT url FROM media WHERE entry_id=? AND (download_status=? OR download_status=?)',
					#				(status[1],D_NOT_DOWNLOADED,D_ERROR))
					self._db_execute(self._c, u'SELECT url FROM media WHERE entry_id=?', (status[1],))
					db_enc = self._c.fetchall()
					db_enc = [c_i[0] for c_i in db_enc]
					f_enc = [f_i['url'] for f_i in item['enclosures']]

					db_set = sets.Set(db_enc)
					f_set  = sets.Set(f_enc)
					
					removed = list(db_set.difference(f_set))
					added   = list(f_set.difference(db_set))
					
					if len(removed)>0:
						qmarks = "?,"*(len(removed)-1)+"?"
						self._db_execute(self._c, u'DELETE FROM media WHERE url IN ('+qmarks+') AND (download_status=? OR download_status=?)', tuple(removed)+(D_NOT_DOWNLOADED,D_ERROR))
					
					#need to  delete media that isn't in enclosures only and is not downloaded 
					#need to add media that's in enclosures but not in db after that process
					
					if len(added) > 0:
						print "found new media in feed", feed_id
						print "existing set:",db_enc
						print "enclosures:",item['enclosures']
						print "I think added:",added
						for media in item['enclosures']: #add the rest
							#self._db_execute(self._c, u'SELECT url FROM media WHERE url=?',(media['href'],))
							#dburl = self._c.fetchone()
							#if dburl:
							if media['url'] in added:
								#if dburl[0] != media['url']: #only add if that url doesn't exist
								media.setdefault('length', 0)
								media.setdefault('type', 'application/octet-stream')
								self._db_execute(self._c, u"""INSERT INTO media (id, entry_id, url, mimetype, download_status, viewed, keep, length, download_date, feed_id) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, 0, ?)""", (status[1], media['url'], media['type'], 0, D_NOT_DOWNLOADED, 0, media['length'], feed_id))
								self._db_execute(self._c, u'UPDATE entries SET read=0 WHERE id=?', (status[1],))
					#self._db.commit()
				self._reindex_entry_list.append(status[1])
							
				#flag_list.append(self.get_entry_flag(status[1]))
			i+=1
		self._db.commit()
		#don't call anything old that has media...
		self._db_execute(self._c, """SELECT entry_id FROM media WHERE download_status>0 AND feed_id=?""",(feed_id,))
		for id in self._c.fetchall():
			self._db_execute(self._c, """UPDATE entries SET old=0 WHERE id=?""",(id[0],))
		self._db.commit()
		#anything not set above as new, mod, or exists is no longer in
		#the xml and therefore should be deleted
		
		self._db_execute(self._c, """SELECT count(*) FROM entries WHERE feed_id=?""",(feed_id,))
		all_entries = self._c.fetchone()[0]
		self._db_execute(self._c, """SELECT count(*) FROM entries WHERE old=1 AND feed_id=?""",(feed_id,))
		old_entries = self._c.fetchone()[0]
		if old_entries>0:
			new_entries = all_entries - old_entries
			if MAX_ARTICLES > 0: #zero means never delete
				if new_entries >= MAX_ARTICLES:
					#deleting all old because we got more than enough new
					self._db_execute(self._c, """DELETE FROM entries WHERE old=1 AND feed_id=?""",(feed_id,))
				elif new_entries+old_entries > MAX_ARTICLES:
					old_articles_to_keep = MAX_ARTICLES-new_entries
					if old_articles_to_keep > 0:
						old_articles_to_ditch = old_entries - old_articles_to_keep
						self._db_execute(self._c, """SELECT id,title FROM entries WHERE old=1 AND feed_id=? ORDER BY fakedate LIMIT ?""",(feed_id,old_articles_to_ditch))
						ditchables = self._c.fetchall()
						for e in ditchables:
							self._db_execute(self._c, """DELETE FROM entries WHERE id=?""",(e[0],))
		self._db_execute(self._c, "DELETE FROM entries WHERE fakedate=0 AND feed_id=?",(feed_id,))
		#self.update_entry_flags(feed_id,db)
		#self.update_feed_flag(feed_id,db)
		self._db.commit()
		if arguments & A_AUTOTUNE == A_AUTOTUNE:
			self._set_new_update_freq(feed_id, new_items)
		if arguments & A_DO_REINDEX:
			if new_items > 0:
				self.reindex()
		return new_items
		
	def _set_new_update_freq(self, feed_id, new_items):
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
		
		self._db_execute(self._c, u'SELECT lastpoll, newatlast, pollfreq FROM feeds WHERE id=?',(feed_id,))
		last_time,newatlast,old_poll_freq = self._c.fetchone()
		cur_time = time.time()
		#this could suck if the program was just started, so only do it if the poll_freq seems correct
		#however still update the db with the poll time
		self._db_execute(self._c, u'UPDATE feeds SET lastpoll=?, newatlast=? WHERE id=?',(cur_time,new_items,feed_id))
		self._db.commit()
		if cur_time - last_time < old_poll_freq/2:  #too soon to get a good reading.
			return
		
		#normalize dif:
		new_items = round(new_items *  old_poll_freq / (cur_time-last_time))
		
		if new_items==0:
			#figure out the average time between article postings
			#this algorithm seems to be the most accurate based on my own personal judgment
			self._db_execute(self._c, 'SELECT date FROM entries WHERE feed_id=?',(feed_id,))
			datelist = self._c.fetchall()
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
	
		self._db_execute(self._c, 'UPDATE feeds SET pollfreq=? WHERE id=?',(poll_freq,feed_id))
		self._db.commit()
		
	def _get_status(self, item, existing_entries):
		"""returns status, the entry_id of the matching entry (if any), and the media list if unmodified"""
		ID=0
		GUID=1
		LINK=2
		TITLE=3
		BODY=4

		entry_id=-1
		
		t_item = {'guid': item['guid'],
				'body': item['body'],
				'link': item['link'],
				'title': item['title']}
				
		
		for entry_item in existing_entries:
			if str(t_item['guid'])!='0':
				if str(entry_item[GUID]) == str(t_item['guid']):# and entry_item[TITLE] == t_item['title']:
					entry_id = entry_item[ID]
					old_hash = self._ascii(entry_item[GUID])+self._ascii(entry_item[BODY])
					new_hash = self._ascii(t_item['guid'])+self._ascii(t_item['body'])
					break
			elif t_item['link']!='':
				if entry_item[LINK] == t_item['link'] and entry_item[TITLE] == t_item['title']:
					entry_id = entry_item[ID]
					old_hash = self._ascii(entry_item[LINK])+self._ascii(entry_item[BODY])
					new_hash = self._ascii(t_item['link'])+self._ascii(t_item['body'])
					break
			elif entry_item[TITLE] == t_item['title']:
				entry_id = entry_item[ID]
				old_hash = self._ascii(entry_item[TITLE])+self._ascii(entry_item[BODY])
				new_hash = self._ascii(t_item['title'])+self._ascii(t_item['body'])
				break

		if entry_id == -1:
			return (NEW, -1, [])

		if new_hash == old_hash:
			#now check enclosures
			old_media = self.get_entry_media(entry_id)
			if old_media is None:
				old_media = []
			
			#if they are both zero, return
			if len(old_media) == 0 and item.has_key('enclosures') == False: 
				return (EXISTS,entry_id, [])
			
			if item.has_key('enclosures'):
				#if lengths are different, return
				if len(old_media) != len(item['enclosures']): 
					return (MODIFIED,entry_id, [])
			else:
				#if we had some, and now don't, return
				if len(old_media)>0: 
					return (MODIFIED,entry_id, [])
			
			#we have two lists of the same, non-zero length
			#only now do we do the loops and sorts -- we need to test individual items
			
			existing_media = old_media
			
			old_media = [medium['url'] for medium in old_media]
			new_media = [m['url'] for m in item['enclosures']]
			
			old_media = utils.uniquer(old_media)
			old_media.sort()
			new_media = utils.uniquer(new_media)
			new_media.sort()

			if old_media != new_media:
				return (MODIFIED,entry_id,[])
			return (EXISTS,entry_id, existing_media)
		else:
			return (MODIFIED,entry_id, [])
			
	def get_entry_media(self, entry_id):
		self._db_execute(self._c, """SELECT id,entry_id,url,file,download_status,viewed,length,mimetype FROM media WHERE entry_id = ?""",(entry_id,))
		dataList=self._c.fetchall()
		
		if dataList is None:
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
		
	def get_entry_media_block(self, entry_list):
		if len(entry_list) == 0:
			return
		qmarks = "?,"*(len(entry_list)-1)+"?"
		
		self._db_execute(self._c, """SELECT id,entry_id,url,file,download_status,viewed,length,mimetype FROM media WHERE entry_id in ("""+qmarks+')',tuple(entry_list))
		result = self._c.fetchall()
		if result is None:
			return []
		media_dict = {}
		for datum in result:
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
			
			if not media_dict.has_key(medium['entry_id']):
				media_dict[medium['entry_id']] = [medium]
			else:
				media_dict[medium['entry_id']].append(medium)				
		
		return media_dict
		
	def get_media(self, media_id):
		self._db_execute(self._c, u'SELECT url, download_status, length, file, entry_id, viewed, mimetype FROM media WHERE id=?',(media_id,))
		datum=self._c.fetchone()
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
		
	def get_feed_media_count(self, feed_id):
		self._db_execute(self._c, u'SELECT count(*) FROM media WHERE feed_id=?',(feed_id,))
		return self._c.fetchone()[0]
	
	def get_entry(self, entry_id):
		self._db_execute(self._c, """SELECT title, creator, link, description, feed_id, date, read FROM entries WHERE id=? LIMIT 1""",(entry_id,))
		result = self._c.fetchone()
		
		entry_dic={}
		try:
			entry_dic['title'] = result[0]
			entry_dic['creator'] = result[1]
			entry_dic['link'] = result[2]
			entry_dic['description']=result[3]
			entry_dic['feed_id']= result[4]
			entry_dic['date'] = result[5]
			entry_dic['read'] = result[6]
			entry_dic['entry_id'] = entry_id
		except TypeError: #this error occurs when feed or item is wrong
			raise NoEntry, entry_id
		return entry_dic
		
	def get_entry_block(self, entry_list):
		if len(entry_list) == 0:
			return
		qmarks = "?,"*(len(entry_list)-1)+"?"
		self._db_execute(self._c, u'SELECT title, creator, link, description, feed_id, date, read, id FROM entries WHERE id in ('+qmarks+')', (tuple(entry_list)))
		result = self._c.fetchall()
		if result is None:
			return []
		retval = []
		for entry in result:
			entry_dic = {}
			entry_dic['title'] = entry[0]
			entry_dic['creator'] = entry[1]
			entry_dic['link'] = entry[2]
			entry_dic['description']=entry[3]
			entry_dic['feed_id']= entry[4]
			entry_dic['date'] = entry[5]
			entry_dic['read'] = entry[6]
			entry_dic['entry_id'] = entry[7]
			retval.append(entry_dic)
		return retval
		
	def get_entrylist(self, feed_index):
		self._db_execute(self._c, u'SELECT feed_pointer,description FROM feeds WHERE id=?',(feed_index,))
		result = self._c.fetchone()
		if result is None:
			return []
		if result[0] >= 0:
			pointed_feed = result[0]
			#this is where we perform a search
			s_entries =  self.search(result[1],pointed_feed)[1]
			if len(s_entries)==0:
				return []
			s_entries.sort(lambda x,y: int(y[2] - x[2]))
			entries = []
			#gonna be slow :(
			for entry_id,title, fakedate, feed_id in s_entries:
				self._db_execute(self._c, """SELECT read FROM entries WHERE id=? LIMIT 1""",(entry_id,))
				try:
					readinfo = self._c.fetchone()[0]
				except:
					print "error in search results, reindexing"
					readinfo = 0
					self.reindex()
				entries.append([entry_id, title, fakedate, readinfo, feed_id])
			self._filtered_entries[feed_index] = entries
			return entries
	
		self._db_execute(self._c, """SELECT id,title,fakedate,read,feed_id FROM entries WHERE feed_id=? ORDER BY fakedate DESC""",(feed_index,))
		result = self._c.fetchall()
		
		if result=="":
			raise NoFeed, feed_index
		return result
		
	def get_entry_count(self, feed_id):
		self._db_execute(self._c, u'SELECT count(*) FROM entries WHERE feed_id=?', (feed_id,))
		return self._c.fetchone()[0]

	def get_feedlist(self):
		self._db_execute(self._c, """SELECT id,title FROM feeds ORDER BY UPPER(title)""")
		result = self._c.fetchall()
		dataList = []
		if result: 
			dataList = [list(row) for row in result]
		else:
			result=[]
		return dataList
		
	def get_feed_title(self, feed_index):
		self._db_execute(self._c, """SELECT title FROM feeds WHERE id=?""",(feed_index,))
		try:
			result = self._c.fetchone()[0]
		except TypeError:
			raise NoFeed, feed_index	
		
		#don't return a tuple
		return result #self.decode_text(result)
		
	def get_feed_image(self, feed_id):
		self._db_execute(self._c, u'SELECT image FROM feeds WHERE id=?', (feed_id,))
		try: return self._c.fetchone()[0]
		except: return None
		
	def get_feed_info(self, feed_id):
		import urlparse
		self._db_execute(self._c, """SELECT title, description, url, link, feed_pointer, lastpoll, pollfreq FROM feeds WHERE id=?""",(feed_id,))
		try:
			result = self._c.fetchone()
			d = {'title':result[0],
				 'description':result[1],
				 'url':result[2],
				 'link':result[3],
				 'feed_pointer':result[4],
				 'lastpoll':result[5],
				 'pollfreq':result[6]}
			parts=urlparse.urlsplit(result[2])
			usernameandpassword, domain=urllib.splituser(parts[1])
			#username, password=urllib.splitpasswd(usernameandpassword)
			if usernameandpassword is None:
				d['auth_feed'] = False
			else:
				d['auth_feed'] = True
				d['auth_userpass'] = usernameandpassword
				d['auth_domain'] = domain
			return d
		except TypeError:
			raise NoFeed, feed_id	
		return result
		
	def set_feed_name(self, feed_id, name):
		name = self._encode_text(name)
		
		if name is not None:
			self._db_execute(self._c, u'UPDATE feeds SET title=? WHERE id=?',(name,feed_id))
			self._db.commit()
		else:
			self._db_execute(self._c, """SELECT url FROM feeds WHERE id=?""",(feed_id,))
			url=self._c.fetchone()[0]
			
			try:
				import feedparser
				feedparser.disableWellFormedCheck=1
				data = feedparser.parse(url)
			except:
				return
			channel=data['feed']
			if channel.has_key('title') == 0:
				if channel['description'] != "":
					channel['title']=channel['description']
				else:
					channel['title']=url
			channel['title'] = self._encode_text(channel['title'])
			
			self._db_execute(self._c, u'UPDATE feeds SET title=? WHERE id=?',(channel['title'],feed_id))
			self._db.commit()
		self._reindex_feed_list.append(feed_id)
		self.reindex()
		
	def set_feed_url(self, feed_id, url):
		try:
			self._db_execute(self._c, u'UPDATE feeds SET url=? WHERE id=?',(url,feed_id))
			self._db.commit()
		except sqlite.IntegrityError:
			raise FeedAlreadyExists,feed_id			
		
	def set_feed_link(self, feed_id, link):
		self._db_execute(self._c, u'UPDATE feeds SET link=? WHERE id=?',(link,feed_id))
		self._db.commit()
				
	def set_media_download_status(self, media_id, status):
		if status == D_DOWNLOADED:
			self._db_execute(self._c, u'UPDATE media SET download_status=?, download_date=? WHERE id=?', (status,time.time(),media_id,))
			self._db.commit()
		else:
			self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE id=?', (status,media_id,))
			self._db.commit()
		self._db_execute(self._c, u'SELECT entry_id FROM media WHERE id=?',(media_id,))
		entry_id = self._c.fetchone()[0]
		if self.entry_flag_cache.has_key(entry_id):
			del self.entry_flag_cache[entry_id]
		
	def set_media_filename(self, media_id, filename):
		self._db_execute(self._c, u'UPDATE media SET file=? WHERE id=?', (filename,media_id))
		self._db.commit()
		
	def set_media_viewed(self, media_id, viewed):
		self._db_execute(self._c, u'UPDATE media SET viewed=? WHERE id=?',(int(viewed),media_id))
		self._db.commit()
		self._db_execute(self._c, u'SELECT entry_id FROM media WHERE id=?',(media_id,))
		entry_id = self._c.fetchone()[0]
		
		if self.entry_flag_cache.has_key(entry_id): del self.entry_flag_cache[entry_id]
	
		if viewed==1:#check to see if this makes the whole entry viewed
			self._db_execute(self._c, u'SELECT viewed FROM media WHERE entry_id=?',(entry_id,))
			list = self._c.fetchall()
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
		self._db_execute(self._c, u'SELECT length FROM media WHERE id=?',(media_id,))
		return self._c.fetchone()[0]
	
	def set_media_size(self, media_id, size):
		self._db_execute(self._c, u'UPDATE media SET length=? WHERE id=?',(int(size),media_id))
		self._db.commit()
	
	def set_entry_read(self, entry_id, read):
		self._db_execute(self._c, u'UPDATE entries SET read=? WHERE id=?',(int(read),entry_id))
		self._db_execute(self._c, u'UPDATE media SET viewed=? WHERE entry_id=?',(int(read),entry_id))
		self._db.commit()
		if self.entry_flag_cache.has_key(entry_id): del self.entry_flag_cache[entry_id]
		
	def set_entrylist_read(self, entrylist, read):
		if len(entrylist) == 0:
			return
		l = [str(e) for e in entrylist]
		qmarks = "?,"*(len(l)-1)+"?"
		self._db_execute(self._c, u'UPDATE entries SET read=? WHERE id IN ('+qmarks+')', (int(read),)+tuple(l))
		self._db_execute(self._c, u'UPDATE media SET viewed=? WHERE entry_id IN ('+qmarks+')',(int(read),)+tuple(l))
		self._db.commit()
		for e in entrylist:
			if self.entry_flag_cache.has_key(e): del self.entry_flag_cache[e]
		
	def get_entry_read(self, entry_id):
		self._db_execute(self._c, u'SELECT read FROM entries WHERE id=? LIMIT 1',(entry_id,))
		retval = self._c.fetchone()[0]
		return int(retval)
		
	def clean_media_status(self):
		self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE download_status<1',(D_NOT_DOWNLOADED,))
		self._db.commit()
		self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE download_status=1',(D_RESUMABLE,))
		self._db.commit()
		
	def get_entryid_for_media(self, media_id):
		self._db_execute(self._c, u'SELECT entry_id FROM media WHERE id=? LIMIT 1',(media_id,))
		ret = self._c.fetchone()
		return ret[0]
		
	def get_media_for_download(self, resume_paused = True):
		if resume_paused:
			self._db_execute(self._c, u'SELECT id, length, entry_id, feed_id FROM media WHERE (download_status=? OR download_status==?) AND viewed=0',(D_NOT_DOWNLOADED,D_RESUMABLE))
		else:
			self._db_execute(self._c, u'SELECT id, length, entry_id, feed_id FROM media WHERE download_status=? AND viewed=0',(D_NOT_DOWNLOADED,))
		list=self._c.fetchall()
		self._db_execute(self._c, u'SELECT id, length, entry_id, feed_id FROM media WHERE download_status=?',(D_ERROR,))
		list=list+self._c.fetchall()
		newlist=[]
		for item in list:
			try:
				size = int(item[1])
			except ValueError:
				#try _this_!
				try:
					size = int(''.join([b for b in item[1] if b.isdigit()]))
				except:
					size = 0
			new_item = (item[0],size,item[2], item[3])
			newlist.append(new_item)
			if self.entry_flag_cache.has_key(item[2]): del self.entry_flag_cache[item[2]]
			
		#build a list of feeds that do not include the noautodownload tag
		feeds = [l[3] for l in newlist]
		feeds = utils.uniquer(feeds)
		good_feeds = [f for f in feeds if NOAUTODOWNLOAD not in self.get_tags_for_feed(f)]
		newlist = [l for l in newlist if l[3] in good_feeds]
		return newlist 
		
	def get_deletable_media(self):
		no_expire = self.get_feeds_for_tag(NOAUTOEXPIRE)
		if len(no_expire) > 0:
			qmarks = "?,"*(len(no_expire)-1)+"?"
			self._db_execute(self._c, u'SELECT id, entry_id, feed_id, file, download_date FROM media WHERE download_status=2 AND feed_id not in ('+qmarks+') ORDER BY viewed DESC, download_date', tuple(no_expire))
		else:
			self._db_execute(self._c, u'SELECT id, entry_id, feed_id, file, download_date FROM media WHERE download_status=2 ORDER BY viewed DESC, download_date')
		
		result = self._c.fetchall()
		if result:
			return [[r[0],r[1],r[2],r[3],long(r[4])] for r in result]
		return []
		
	def get_resumable_media(self):
		self._db_execute(self._c, u'SELECT id, file, entry_id, feed_id  FROM media WHERE download_status=?',(D_RESUMABLE,))
		list = self._c.fetchall()
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
		if self._filtered_entries.has_key(feed_id):
			list = []
			for entry in self._filtered_entries[feed_id]:
				self._db_execute(self._c, u'UPDATE entries SET read=1 WHERE id=? AND read=0',(entry[0],))
				self._db_execute(self._c, u'SELECT id, download_status FROM media WHERE entry_id=?',(entry[0],))
				list = list+self._c.fetchall()
			feed_id = self._resolve_pointed_feed(feed_id)
		else:
			#feed_id = self._resolve_pointed_feed(feed_id)
			self._db_execute(self._c, u'UPDATE entries SET read=1 WHERE feed_id=? AND read=0',(feed_id,))
			self._db_execute(self._c, u'SELECT id, download_status FROM media WHERE feed_id = ?',(feed_id,))
			list = self._c.fetchall()
		for item in list:
			self._db_execute(self._c, u'UPDATE media SET viewed=? WHERE id=? AND viewed=0',(1,item[0]))
			if item[1] == D_ERROR:
				self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE id=?', (D_NOT_DOWNLOADED,item[0]))
		self._db.commit()
		self._db_execute(self._c, u'SELECT id,read FROM entries WHERE feed_id=?',(feed_id,))
		list = self._c.fetchall()
		for item in list:
			if self.entry_flag_cache.has_key(item[0]): 
				del self.entry_flag_cache[item[0]]
	
	def media_exists(self, filename):
		self._db_execute(self._c, u'SELECT count(*) FROM media WHERE media.file=?',(filename,))
		count = self._c.fetchone()[0]
		if count>1:
			print "WARNING: multiple entries in db for one filename"
		if count==0:
			return False
		return True
		
	def get_unplayed_media(self, set_viewed=False):
		"""media_id, entry_id, feed_id, file, entry_title, feed_title
		    0          1         2       3        4            5"""
		self._db_execute(self._c, u'SELECT media.id, media.entry_id, media.feed_id, media.file, entries.title FROM media INNER JOIN entries ON media.entry_id = entries.id WHERE media.download_status=? AND media.viewed=0',(D_DOWNLOADED,))
		list=self._c.fetchall()
		playlist=[]
		if set_viewed:
			for item in list:
				self._db_execute(self._c, u'UPDATE media SET viewed=1 WHERE id=?',(item[0],))
				self._db_execute(self._c, u'UPDATE entries SET read=1 WHERE id=?',(item[1],))	
				if self.entry_flag_cache.has_key(item[1]): del self.entry_flag_cache[item[1]]				
				playlist.append(item)
			self._db.commit()
		else:
			playlist = list
			
		retval = []
		for row in playlist:
			feed_title = self.get_feed_title(row[2])
			retval.append(row+(feed_title,))
			
		return retval
		
	def pause_all_downloads(self):
		self._db_execute(self._c, u'SELECT entry_id FROM media WHERE download_status=?',(D_DOWNLOADING,))
		list = self._c.fetchall()
		list = utils.uniquer(list)
		if list:
			for e in list:
				if self.entry_flag_cache.has_key(e[0]): del self.entry_flag_cache[e[0]]
			self._db_execute(self._c, u'UPDATE media SET viewed = 0 WHERE download_status=?',(D_DOWNLOADING,))
			self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE download_status=?',(D_RESUMABLE,D_DOWNLOADING))
			self._db.commit()
		
	def get_entry_download_status(self, entry_id):
		self._db_execute(self._c, u'SELECT download_status, viewed FROM media WHERE download_status!=0 AND entry_id=?',(entry_id,))
		result = self._c.fetchall()
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
		
	def get_feed_poll_fail(self, feed_id):
		feed_id = self._resolve_pointed_feed(feed_id)
	
		self._db_execute(self._c, u'SELECT pollfail FROM feeds WHERE id=?',(feed_id,))
		result = self._c.fetchone()[0]
		if result==0:
			return False
		return True

	def get_feed_download_status(self, feed_id):
		#feed_id = self._resolve_pointed_feed(feed_id)
			
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
			flaglist = self.get_entry_flags(feed_id)
			feed_info['important_flag'] = self.get_feed_flag(feed_id, flaglist)  #not much speeding up this	
			feed_info['entry_count'] = len(flaglist)
			feed_info['unread_count'] = len([f for f in flaglist if f & F_UNVIEWED])
		else:
			self._db_execute(self._c, u'SELECT flag_cache, unread_count_cache, entry_count_cache FROM feeds WHERE id=?',(feed_id,))
			cached_info = self._c.fetchone()
			feed_info['important_flag'] = cached_info[0]
			feed_info['unread_count'] = cached_info[1]
			feed_info['entry_count'] = cached_info[2]
		
		self._db_execute(self._c, u'SELECT pollfail FROM feeds WHERE id=?',(feed_id,))
		result = self._c.fetchone()[0]
		if result==0:
			feed_info['poll_fail'] = False
		else:
			feed_info['poll_fail'] = True
		return feed_info
	
	def get_entry_flag(self, entry_id, medialist=None, read=None):
		if self.entry_flag_cache.has_key(entry_id):
			return self.entry_flag_cache[entry_id]

		importance=0
		
		if read is None:
			self._db_execute(self._c, u'SELECT read FROM entries WHERE id=?',(entry_id,))
			read = self._c.fetchone()[0]
		
		if medialist is None:
			medialist = self.get_entry_media(entry_id)
		
		status = D_NOT_DOWNLOADED
		if medialist:
			for medium in medialist:
				if medium['download_status'] == D_DOWNLOADING:
					status = D_DOWNLOADING
					break
				if medium['download_status'] == D_ERROR:
					status = D_ERROR
					break
				if medium['download_status'] == D_RESUMABLE:
					status = D_RESUMABLE
					break
				if medium['download_status'] == D_DOWNLOADED:
					status = D_DOWNLOADED
					break
		
		if status==D_ERROR:
			importance=importance+F_ERROR
		if status==D_DOWNLOADING:
			importance=importance+F_DOWNLOADING		
			
		if medialist:	
			importance=importance+F_MEDIA
			if status==D_DOWNLOADED:
				importance=importance+F_DOWNLOADED
			elif status==D_RESUMABLE:
				importance=importance+F_PAUSED
			for medium in medialist:
				if medium['viewed']==0:
					importance=importance+F_UNVIEWED
					break
		else:
			if int(read)==0:
				importance=importance+F_UNVIEWED
		
		if USING_FLAG_CACHE:
			self.entry_flag_cache[entry_id] = importance
		return importance		
		
	def get_unread_count(self, feed_id):
		if self._filtered_entries.has_key(feed_id):
			entries = self._filtered_entries[feed_id]
			list = []
			for entry in entries:
				self._db_execute(self._c, u'SELECT read FROM entries WHERE id=?',(entry[0],))
				try:
					list.append(self._c.fetchone())
				except:
					pass
			unread=0
			for item in list:
				if item[0]==0:
					unread=unread+1
		else:
			feed_id = self._resolve_pointed_feed(feed_id)		
			self._db_execute(self._c, u'SELECT count(*) FROM entries WHERE feed_id=? and read=0', (feed_id,))
			unread = self._c.fetchone()[0]
		
		return unread
		
	def correct_unread_count(self, feed_id): #FIXME: we shouldn't need this one day
		""" Set the entry_read flag to the correct value based on all its enclosures.
			This is necessary because there are some bugs with regard to when this
			value gets set. """
		if self._filtered_entries.has_key(feed_id):
			return #just don't do anything
		#feed_id = self._resolve_pointed_feed(feed_id)
			
		entrylist = self.get_entrylist(feed_id)
		if entrylist:
			for entry in entrylist:
				flag = self.get_entry_flag(entry[0])
				if flag & F_UNVIEWED:
					self.set_entry_read(entry[0],False)
				else:
					self.set_entry_read(entry[0],True)
					
	def get_entry_flags(self, feed_id):
		medialist=None
		flaglist = []
		if self._filtered_entries.has_key(feed_id):
			entrylist = [e[0] for e in self._filtered_entries[feed_id]]
			for entry in entrylist:
				flaglist.append(self.get_entry_flag(entry))
		else:
			self._db_execute(self._c, u'SELECT id, read FROM entries WHERE feed_id=?',(feed_id,))
			entrylist = self._c.fetchall()
			if self.get_feed_media_count(feed_id) == 0:
				medialist = []
			for entry,read in entrylist:
				flaglist.append(self.get_entry_flag(entry,read=read, medialist=medialist))
		return flaglist
	
	def get_feed_flag(self, feed_id, flaglist = None):
		""" Based on a feed, what flag best represents the overall status of the feed at top-level?
			This is based on the numeric value of the flag, which is why flags are enumed the way they are."""
			
		feed_has_media=0
		if flaglist is None:
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
		self._db_execute(self._c, u'SELECT DISTINCT feeds.id FROM feeds INNER JOIN tags ON tags.feed_id=feeds.id WHERE tag=?',(tag,))
		result = self._c.fetchall()
		return [r[0] for r in result]
			
	def get_tags_for_feed(self, feed_id):
		self._db_execute(self._c, u'SELECT tag FROM tags WHERE feed_id=? ORDER BY tag',(feed_id,))
		result = self._c.fetchall()
		dataList = []
		if result: 
			dataList = [row[0] for row in result]
		else:
			return []
		return dataList
		
	def get_search_tag(self, tag):
		self._db_execute(self._c, u'SELECT query FROM tags WHERE tag=?',(tag,))
		result = self._c.fetchone()
		if result: 
			return result[0]
		return []
		
	def get_search_tags(self):
		self._db_execute(self._c, u'SELECT tag,query FROM tags WHERE type=? ORDER BY tag',(T_SEARCH,))
		result = self._c.fetchall()
		if result:
			return result
		return []
	
	def add_tag_for_feed(self, feed_id, tag):
		current_tags = self.get_tags_for_feed(feed_id)
		if current_tags:
			if tag not in current_tags and len(tag)>0:
				self._db_execute(self._c, u'SELECT favorite FROM tags WHERE tag=? LIMIT 1',(tag,))
				favorite = self._c.fetchone()
				try: favorite = favorite[0]
				except: favorite = 0
				self._db_execute(self._c, u'INSERT INTO tags (tag, feed_id, type, favorite) VALUES (?,?,?,?)',(tag,feed_id, T_TAG, favorite))
				self._db.commit()
		else:
			self._db_execute(self._c, u'INSERT INTO tags (tag, feed_id, type, favorite) VALUES (?,?,?,0)',(tag,feed_id, T_TAG))
			self._db.commit()
		if tag == NOSEARCH:
			self._blacklist = self.get_tags_for_feed(NOSEARCH)
			
	def fix_tags(self):
		self._db_execute(self._c, u'DELETE FROM tags WHERE tag=""')
		self._db.commit()
			
	def add_search_tag(self, query, tag, favorite=False):
		current_tags = [t[0] for t in self.get_all_tags(T_ALL)] #exclude favorite stuff
		if current_tags:
			if tag not in current_tags:
				self._db_execute(self._c, u'INSERT INTO tags (tag, feed_id, query, type, favorite) VALUES (?,?,?,?,?)',(tag,0,query,T_SEARCH,favorite))
				self._db.commit()
			else:
				raise TagAlreadyExists,"The tag name "+str(tag)+" is already being used"
		else:
			self._db_execute(self._c, u'INSERT INTO tags (tag, feed_id, query, type) VALUES (?,?,?,?,?)',(tag,0,query,T_SEARCH,favorite))
			self._db.commit()	
	
	def change_query_for_tag(self, tag, query):
		try:
			self._db_execute(self._c, u'UPDATE tags SET query=? WHERE tag=?',(query,tag))
			self._db.commit()
		except:
			print "error updating tag"
			
	def set_tag_favorite(self, tag, favorite=False):
		try:
			self._db_execute(self._c, u'UPDATE tags SET favorite=? WHERE tag=?',(favorite,tag))
			self._db.commit()
		except:
			print "error updating tag favorite"

	def rename_tag(self, old_tag, new_tag):
		self._db_execute(self._c, u'UPDATE tags SET tag=? WHERE tag=?',(new_tag,old_tag))
		self._db.commit()
		if new_tag == NOSEARCH or old_tag == NOSEARCH:
			self._blacklist=self.get_tags_for_feed(NOSEARCH)

	def remove_tag_from_feed(self, feed_id, tag):
		self._db_execute(self._c, u'DELETE FROM tags WHERE tag=? AND feed_id=?',(tag,feed_id))
		self._db.commit()
		if tag == NOSEARCH:
			self._blacklist=self.get_tags_for_feed(NOSEARCH)
		
	def remove_tag(self, tag):
		self._db_execute(self._c, u'DELETE FROM tags WHERE tag=?',(tag,))
		self._db.commit()
		if tag == NOSEARCH:
			self._blacklist=self.get_tags_for_feed(NOSEARCH)
		
	def get_all_tags(self, type=T_TAG):
		if type==T_ALL:
			self._db_execute(self._c, u'SELECT DISTINCT tag,favorite FROM tags')
		elif type==T_TAG:
			self._db_execute(self._c, u'SELECT DISTINCT tag,favorite FROM tags WHERE type=?',(T_TAG,))
		elif type==T_SEARCH:
			self._db_execute(self._c, u'SELECT DISTINCT tag,favorite FROM tags WHERE type=?',(T_SEARCH,))
		result = self._c.fetchall()
		def alpha_sorter(x,y):
			if x[0].upper()>y[0].upper():
				return 1
			if x[0].upper()==y[0].upper():
				return 0
			return -1
		result.sort(alpha_sorter)
		#sometimes a tag has two different favorite settings due to a bug.
		#just work around it and get rid of the extras
		result = utils.uniquer(result, lambda x: x[0])
		return result
	
	def get_count_for_tag(self, tag):
		self._db_execute(self._c, u'SELECT count(*) FROM tags WHERE tag=?',(tag,))
		result = self._c.fetchone()[0]
		return result
		
	def export_OPML(self,stream):
		if not utils.HAS_PYXML:
			return
		self._db_execute(self._c, u'SELECT title, description, url FROM feeds ORDER BY UPPER(title)')
		result = self._c.fetchall()
		dataList = []
		if result: 
			dataList = [list(row) for row in result]
		else:
			return
		
		o = OPML.OPML()
		o['title']='All'
		for feed in result:
			item = OPML.Outline()
			item['title']=self._ascii(feed[0])
			item['text']=self._ascii(feed[0])
			item['description']=self._ascii(feed[1])
			item['xmlUrl']=feed[2]
			o.outlines.append(item)
		o.output(stream)
		stream.close()
		
	def import_subscriptions(self, stream, opml = True):
		"""A generator which first yields the number of feeds, and then the feedids as they
		are inserted, and finally -1 on completion"""
		if not utils.HAS_PYXML and opml == True:
			yield (-1,0)
			yield (1,0)
			yield (-1,0)
			return
		if opml:
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
					if o.has_key('categories'):
					    for tag in o['categories'].split(','):
					        tag = tag.strip()
					        self.add_tag_for_feed(feed_id, tag)
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
		else: #just a list in a file
			url_list = []
			count = 0
			for url in stream.readlines():
				count+=1
				url_list.append(url)
			stream.close()
			yield (1,len(url_list))
			for url in url_list:
				try:
					feed_id=self.insertURL(url)
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
			yield (-1,0)
				
	def search(self, query, filter_feed=None, blacklist=None, since=0):
		if not utils.HAS_LUCENE:
			return ([],[])
		if blacklist is None:
			blacklist = self._blacklist
		if filter_feed: #no blacklist on filter feeds (doesn't make sense)
			return self.searcher.Search("entry_feed_id:"+str(filter_feed)+" AND "+query, since=since)
		return self.searcher.Search(query,blacklist, since=since)
		
	def doindex(self, callback=None):
		if utils.HAS_LUCENE:
			self.searcher.Do_Index_Threaded(callback)
		
	def reindex(self, feed_list=[], entry_list=[], threaded=True):
		"""reindex self._reindex_feed_list and self._reindex_entry_list as well as anything specified"""
		if not utils.HAS_LUCENE:
			return
		self._reindex_feed_list += feed_list
		self._reindex_entry_list += entry_list
		try:
			if threaded:
				self.searcher.Re_Index_Threaded(self._reindex_feed_list, self._reindex_entry_list)
			else:
				self.searcher.Re_Index(self._reindex_feed_list, self._reindex_entry_list)
		except:
			print "reindex failure.  wait til next time I guess"
		self._reindex_feed_list = []
		self._reindex_entry_list = []
		
	def _resolve_pointed_feed(self, feed_id):
		self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE id=?',(feed_id,))
		result = self._c.fetchone()[0]
		if result >= 0:
			return result
		return feed_id
		
	def is_feed_filter(self, feed_id):
		self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE id=?',(feed_id,))
		result = self._c.fetchone()[0]
		if result >= 0:
			return True
		return False
		
	def get_pointer_feeds(self, feed_id):
		self._db_execute(self._c, u'SELECT id FROM feeds WHERE feed_pointer=?',(feed_id,))
		results = self._c.fetchall()
		if results is None:
			return []
		return [f[0] for f in results]
		
	#############convenience Functions####################3
		
	def _encode_text(self,text):
		try:
			return text.encode('utf8')
		except:
			return u''
	
	def _ascii(self, text):
		try:
			return text.encode('ascii','replace')
		except UnicodeDecodeError:
			return u''

	def DEBUG_get_full_feedlist(self):
		self._db_execute(self._c, """SELECT id,title,url FROM feeds ORDER BY id""")
		result = self._c.fetchall()
		return result
					
	def DEBUG_reset_freqs(self):
		self._db_execute(self._c, 'UPDATE feeds SET pollfreq=1800')
		self._db.commit()	
	
	def DEBUG_get_freqs(self):
		self._db_execute(self._c, 'SELECT title, pollfreq, lastpoll, id  FROM feeds ORDER BY title')
		a = self._c.fetchall()
		max_len = 0
		for item in a:
			if len(item[0]) > max_len:
				max_len = len(item[0])
		for item in a:
			try:
			#item2=(str(item[0]),item[1]/(60),time.asctime(time.localtime(item[2])))
				print self._ascii(item[0])+" "*(max_len-len(str(item[0])))+" "+str(item[1]/60)+"       "+time.asctime(time.localtime(item[2]))+" "+str(item[3])
			except:
				print "whoops: "+ self._ascii(item[0]) 

			#print item2
		print "-"*80
		self._db_execute(self._c, 'SELECT title, pollfreq, lastpoll, id FROM feeds ORDER BY lastpoll')
		a = self._c.fetchall()
		max_len = 0
		for item in a:
			if len(item[0]) > max_len:
				max_len = len(item[0])
		for item in a:
			try:
			#item2=(str(item[0]),item[1]/(60),time.asctime(time.localtime(item[2])))
				print self._ascii(item[0])+" "*(max_len-len(str(item[0])))+" "+str(item[1]/60)+"       "+time.asctime(time.localtime(item[2]))+" "+ str(item[3])
			except:
				print "whoops: "+ self._ascii(item[0])
			#print item2
			
		print "-"*80
		self._db_execute(self._c, 'SELECT title, pollfreq, lastpoll, id FROM feeds ORDER BY pollfreq')
		a = self._c.fetchall()
		a.reverse()
		max_len = 0
		for item in a:
			if len(item[0]) > max_len:
				max_len = len(item[0])
		for item in a:
			try:
			#item2=(str(item[0]),item[1]/(60),time.asctime(time.localtime(item[2])))
				print self._ascii(item[0])+" "*(max_len-len(self._ascii(item[0])))+" "+str(item[1]/60)+"       "+time.asctime(time.localtime(item[2]))+" "+ str(item[3])
			except:
				print "whoops: "+ self._ascii(item[0])
			#print item2
			
	def DEBUG_delete_all_media(self):		
		self._db_execute(self._c, u'UPDATE media SET download_status=?',(D_NOT_DOWNLOADED,))
		self._db.commit()
		
	def DEBUG_correct_feed(self, feed_id):
		self._db_execute(self._c, u'SELECT media.download_status, media.viewed, media.entry_id, media.id FROM media,entries WHERE media.entry_id=entries.id AND media.download_status!=? AND entries.feed_id=?',(D_NOT_DOWNLOADED,feed_id))
		media = self._c.fetchall()
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
