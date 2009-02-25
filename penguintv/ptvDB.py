# Written by Owen Williams
# see LICENSE for license information

import logging
try:
	import sqlite3 as sqlite
	logging.info("Using built-in sqlite3")
except:
	logging.info("Using external pysqlite2")
	from pysqlite2 import dbapi2 as sqlite

from math import floor,ceil
import time
import string
import urllib, urlparse
from urllib2 import URLError
from types import *
import ThreadPool
import sys, os, os.path, re
import gc
import locale
import gettext
import sets
import traceback
import pickle
import sha

import socket
socket.setdefaulttimeout(30.0)

#locale.setlocale(locale.LC_ALL, '')
gettext.install('penguintv', '/usr/share/locale')
gettext.bindtextdomain('penguintv', '/usr/share/locale')
gettext.textdomain('penguintv')
_=gettext.gettext

import utils
import IconManager
import OfflineImageCache
if utils.HAS_LUCENE:
	import Lucene
if utils.HAS_XAPIAN:
	import PTVXapian
if utils.HAS_GCONF:
	try:
		import gconf
	except:
		from gnome import gconf
if utils.RUNNING_SUGAR: # or utils.RUNNING_HILDON:
	USING_FLAG_CACHE = False
else:
	USING_FLAG_CACHE = True
#USING_FLAG_CACHE = False

LATEST_DB_VER = 7
	
NEW = 0
EXISTS = 1
MODIFIED = 2
DELETED = 3

BOOL    = 1
INT     = 2
STRING  = 3

if utils.RUNNING_SUGAR or utils.RUNNING_HILDON:
	MAX_ARTICLES = 50
else:
	MAX_ARTICLES = 1000

_common_unicode = { u'\u0093':u'"', u'\u0091': u"'", u'\u0092': u"'", u'\u0094':u'"', u'\u0085':u'...', u'\u2026':u'...'}

#Possible entry flags
F_ERROR       = 64
F_DOWNLOADING = 32   
F_UNVIEWED    = 16
F_DOWNLOADED  = 8
F_NEW         = 4
F_PAUSED      = 2
F_MEDIA       = 1

#arguments for poller
A_POOLED_POLL    = 64 # if this is set, don't do housework after each poll
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

#obsolete tag-based flags (needed for schema upgrades)
T_NOAUTODOWNLOAD="noautodownload"
T_NOSEARCH="nosearch"
T_NOAUTOEXPIRE="noautoexpire"
T_NOTIFYUPDATES="notify"

#new bit-based flags
FF_NOAUTODOWNLOAD = 1
FF_NOSEARCH       = 2
FF_NOAUTOEXPIRE   = 4
FF_NOTIFYUPDATES  = 8
FF_ADDNEWLINES    = 16
FF_MARKASREAD     = 32
FF_NOKEEPDELETED  = 64

DB_FILE="penguintv4.db"

STRIPPER_REGEX = re.compile('<.*?>')

class ptvDB:
	entry_flag_cache = {}
	
	def __init__(self, polling_callback=None, change_setting_cb=None):
		self._exiting = False
		self.searcher = None
		self.home = utils.get_home()
		
		try:
			os.stat(self.home)
		except:
			try:
				os.mkdir(self.home)
			except:
				raise DBError, "error creating directories: "+self.home
		if not os.access(self.home, os.R_OK | os.W_OK | os.X_OK):
			raise DBError, "Insufficient access to "+self.home
		self._initializing_db = False
		try:	
			#also check db connection in _process_feed
			if os.path.isfile(os.path.join(self.home,"penguintv4.db")) == False:
				import shutil
				self._initializing_db = True
				if os.path.isfile(os.path.join(self.home,"penguintv3.db")):
					try: 
						shutil.copyfile(os.path.join(self.home,"penguintv3.db"), os.path.join(self.home,"penguintv4.db"))
					except:
						raise DBError,"couldn't create new database file"
				elif os.path.isfile(os.path.join(self.home,"penguintv2.db")):
					try: 
						shutil.copyfile(os.path.join(self.home,"penguintv2.db"), os.path.join(self.home,"penguintv4.db"))
					except:
						raise DBError,"couldn't create new database file"
				elif os.path.isfile(os.path.join(self.home,"penguintv.db")):
					try: 
						shutil.copyfile(os.path.join(self.home,"penguintv.db"), os.path.join(self.home,"penguintv4.db"))
					except:
						raise DBError,"couldn't create new database file"
			self._db=sqlite.connect(os.path.join(self.home,"penguintv4.db"), timeout=30.0, isolation_level="IMMEDIATE")
		except:
			raise DBError,"error connecting to database"
			
		self._c = self._db.cursor()
		
		db_ver = self.get_version_info()[0]
		if db_ver == -1:
			logging.info("database will need init")
			self._initializing_db = True
			
		self._cancel_poll_multiple = False
		
		self._c.execute('PRAGMA synchronous="NORMAL"')
		if not utils.RUNNING_SUGAR and not utils.RUNNING_HILDON:
			self._c.execute('PRAGMA cache_size=6000')
		self.cache_dirty = True
		try:
			if not self._initializing_db:
				self.cache_dirty = self.get_setting(BOOL, "feed_cache_dirty", True)
		except:
			pass
			
		if polling_callback is None:
			self.polling_callback=self._polling_callback
		else:
			self.polling_callback = polling_callback		
			
		self._change_setting_cb = change_setting_cb
			
		self._blacklist = []
		if utils.HAS_SEARCH:
			if utils.HAS_LUCENE:
				self.searcher = Lucene.Lucene()
			if utils.HAS_XAPIAN:
				self.searcher = PTVXapian.PTVXapian()
			else:
				logging.error("Have search, but no search engine?  Programming error!")
				assert False
			if not self._initializing_db:
				try:
					self._blacklist = self.get_feeds_for_flag(FF_NOSEARCH)
				except:
					logging.error("possible old database version")
			
		if utils.HAS_GCONF:
			self._conf = gconf.client_get_default()
			
		self._icon_manager = IconManager.IconManager(self.home)
		
		self._image_cache = None
		cache_images = self.get_setting(BOOL, "/apps/penguintv/cache_images_locally", False)
		if cache_images:
			store_location = self.get_setting(STRING, '/apps/penguintv/media_storage_location', os.path.join(utils.get_home(), "media"))
			if store_location != "":
				self._image_cache = OfflineImageCache.OfflineImageCache(os.path.join(store_location, "images"))
		
		self._reindex_entry_list = []
		self._reindex_feed_list = []
		self._image_cache_list = []
		self._image_uncache_list = []
		self._filtered_entries = {}
		self._parse_list = []
		
	def _db_execute(self, c, command, args=()):
		#if "FROM FEEDS" in command.upper(): 
		#traceback.print_stack()
		#if "UPDATE" in command.upper():
		#	print command, args
		#	traceback.print_stack()
		try:
			return c.execute(command, args)
		except Exception, e:
			#traceback.print_stack()
			logging.error("Database error:" + str(command) + " " + str(args))
			raise e
				
	#def __del__(self):
	#	self.finish()
		
	def finish(self, vacuumok=True, majorsearchwait=False, correctthread=True):
		#allow multiple finishes
		if self._exiting:
			return
		self._exiting=True
		self._cancel_poll_multiple = True
		if utils.HAS_SEARCH and self.searcher is not None:
			if not majorsearchwait and self.searcher.is_indexing(only_this_thread=True):
				logging.debug("not waiting for reindex")
				self.searcher.finish(False)
			else:
				if len(self._reindex_entry_list) > 0 or len(self._reindex_feed_list) > 0:
					logging.info("have leftover things to reindex, reindexing")
					#don't do it threadedly or else we will interrupt it on the next line
					self.reindex(threaded=False) #it's usually not much...
				self.searcher.finish(True)
				
		self.cache_images()
				
		if self._image_cache is not None:
			self._image_cache.finish()
				
		#FIXME: lame, but I'm being lazy
		#if randint(1,100) == 1:
		#	print "cleaning up unreferenced media"
		#	self.clean_file_media()
		if correctthread:
			import random
			if random.randint(1,80) == 1 and vacuumok:
				logging.info("compacting database")
				self._c.execute('VACUUM')
			self._c.close()
			self._db.close()
			
	def get_version_info(self):
		try:
			self._db_execute(self._c, u'SELECT rowid FROM feeds LIMIT 1')
		except Exception, e:
			logging.debug("db except: %s" % str(e))
			return (-1, LATEST_DB_VER)
		self._db_execute(self._c, u'SELECT value FROM settings WHERE data="db_ver"')
		db_ver = self._c.fetchone()
		if db_ver is None:
			db_ver = 0
		else:
			db_ver = int(db_ver[0])
		return (db_ver, LATEST_DB_VER)

	def maybe_initialize_db(self):
		"""returns true if new database"""
		db_ver = self.get_version_info()[0]
		if db_ver == -1:
			logging.info("initializing database")
			self._initializing_db = True
			self._init_database()
			return True	

		try:
			#logging.debug("current database version is " + str(db_ver))
			if db_ver == 0:
				self._migrate_database_one_two()
			if db_ver < 2:
				self._migrate_database_one_two()
			if db_ver < 3:
				self._migrate_database_two_three()
			if db_ver < 4:
				self._migrate_database_three_four()
			if db_ver < 5:
				self._migrate_database_four_five()
			if db_ver < 6:
				self._migrate_database_five_six()
			if db_ver < 7:
				self._migrate_database_six_seven()
				self.clean_database_media()
			if db_ver > LATEST_DB_VER:
				logging.warning("This database comes from a later version of PenguinTV and may not work with this version")
				raise DBError, "db_ver is "+str(db_ver)+" instead of "+str(LATEST_DB_VER)
		except Exception, e:
			logging.error("exception:" + str(e))
			
		#if self.searcher.needs_index:
		#	print "indexing for the first time"
		#	self.searcher.Do_Index_Threaded()
		
		if not utils.RUNNING_HILDON:
			self._check_settings_location()
			self.fix_tags()
			self._fix_indexes()
		return False
		
	def done_initializing(self):
		self._initializing_db = False
			
	def _migrate_database_one_two(self):
		#add table settings
		logging.info("upgrading to database schema 2")
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
				logging.warning(str(e)) #else pass
			#change db_ver (last thing)
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN pollfreq INT')
		self._db_execute(self._c, u'UPDATE feeds SET pollfreq=1800')
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN lastpoll DATE')
		self._db_execute(self._c, u'UPDATE feeds SET lastpoll=?',(int(time.time())-(30*60),))
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
		logging.info("upgrading to database schema 3")
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN flag_cache INT')
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN entry_count_cache INT')
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN unread_count_cache INT')
		
		self._db_execute(self._c, u'UPDATE settings SET value=3 WHERE data="db_ver"')
		self._db_execute(self._c, u'INSERT INTO settings (data, value) VALUES ("feed_cache_dirty",1)')
		self._db.commit()
		
	def _migrate_database_three_four(self):
		"""version 4 adds fulltext table"""
		logging.info("upgrading to database schema 4")
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
		
		logging.info("building new column, please wait...")
		self._db_execute(self._c, u'SELECT id FROM feeds')
		for feed_id, in self._c.fetchall():
			self._db_execute(self._c, u'SELECT media.id FROM entries INNER JOIN media ON media.entry_id = entries.id WHERE entries.feed_id=?', (feed_id,))
			media = self._c.fetchall()
			media = [m[0] for m in media]
			if len(media) > 0:
				qmarks = "?,"*(len(media)-1)+"?"
				self._db_execute(self._c, u'UPDATE media SET feed_id=? WHERE id IN ('+qmarks+')', tuple([feed_id] + media))

		self._db.commit()
		
	def _migrate_database_four_five(self):
		"""version five gets rid of 'id' column, 'new' column, adds option_flags column"""
		logging.info("upgrading to database schema 5, please wait...")
		
		self.__remove_columns("settings","""data TEXT NOT NULL,
											 value TEXT""", 
											 "data, value")
		
		self.__remove_columns("feeds", """id INTEGER PRIMARY KEY,
								url TEXT NOT NULL,
							    polled INT NOT NULL,
							    pollfail BOOL NOT NULL,
							    title TEXT,
							    description TEXT,
							    link TEXT, 
							    modified INT UNSIGNED NOT NULL,
							    etag TEXT,
							    pollfreq INT NOT NULL,
							    lastpoll DATE,
							    newatlast INT,
							    flag_cache INT,
							    entry_count_cache INT,
							    unread_count_cache INT,
							    feed_pointer INT,
							    image TEXT,
							    UNIQUE(url)""",
						"""id, url, polled, pollfail, title, description, link, 
						   modified, etag,  pollfreq, lastpoll, newatlast, 
						   flag_cache, entry_count_cache, unread_count_cache, 
						   feed_pointer, image""")
						   
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN flags INTEGER NOT NULL DEFAULT 0')
		
		self.__update_flags(T_NOAUTODOWNLOAD, FF_NOAUTODOWNLOAD)
		self.__update_flags(T_NOSEARCH, FF_NOSEARCH)
		self.__update_flags(T_NOAUTOEXPIRE, FF_NOAUTOEXPIRE)
		self.__update_flags(T_NOTIFYUPDATES, FF_NOTIFYUPDATES)

		self.__remove_columns("entries", """id INTEGER PRIMARY KEY,
									 	feed_id INTEGER UNSIGNED NOT NULL,
							        	title TEXT,
							        	creator TEXT,
							        	description TEXT,
							        	fakedate DATE,
							        	date DATE,
							        	guid TEXT,
							        	link TEXT,
										read INTEGER NOT NULL,
							        	old INTEGER NOT NULL""",
							  "id, feed_id, title, creator, description, fakedate, date, guid, link, read, old")
							  
		self.__remove_columns("media", """id INTEGER PRIMARY KEY,
								entry_id INTEGER UNSIGNED NOT NULL,
								feed_id INTEGER UNSIGNED NOT NULL,
								url TEXT NOT NULL,
								file TEXT,
								mimetype TEXT,
								download_status INTEGER NOT NULL,
								viewed BOOL NOT NULL,
								keep BOOL NOT NULL,
								length INTEGER,
								download_date DATE, 
								thumbnail TEXT""",
								"id, entry_id, feed_id, url, file, mimetype, download_status, viewed, keep, length, download_date, thumbnail")
								
		self.__remove_columns("tags", """tag TEXT,
							feed_id INT UNSIGNED NOT NULL,
							query TEXT,
							favorite INT,
							type""",
							"tag, feed_id, query, favorite, type")
							
		self._db_execute(self._c, u'UPDATE settings SET value=5 WHERE data="db_ver"')
		self._db.commit()
		
	def _migrate_database_five_six(self):
		logging.info("upgrading to database schema 6, please wait...")
		self._db_execute(self._c, u'ALTER TABLE entries ADD COLUMN keep BOOL')
		self._db_execute(self._c, u'UPDATE entries SET keep=0') 
		self.__remove_columns("feeds", """id INTEGER PRIMARY KEY,
							    url TEXT NOT NULL,
							    pollfail BOOL NOT NULL,
							    title TEXT,
							    description TEXT,
							    link TEXT, 
							    modified INT UNSIGNED NOT NULL,
							    etag TEXT,
							    pollfreq INT NOT NULL,
							    lastpoll DATE,
							    newatlast INT,
							    flags INTEGER NOT NULL DEFAULT 0,
							    flag_cache INT,
							    entry_count_cache INT,
							    unread_count_cache INT,
							    feed_pointer INT,
							    image TEXT,
							    UNIQUE(url)""",
						"""id, url, pollfail, title, description, link, 
						   modified, etag,  pollfreq, lastpoll, newatlast, flags,
						   flag_cache, entry_count_cache, unread_count_cache, 
						   feed_pointer, image""")
		self._db_execute(self._c, u'ALTER TABLE feeds ADD COLUMN first_entry_cache TEXT')
		self._db_execute(self._c, u'UPDATE feeds SET first_entry_cache=""')
		self._db_execute(self._c, u'UPDATE settings SET value=6 WHERE data="db_ver"')
		
		self._db_execute(self._c, u"""CREATE INDEX pollindex ON entries (fakedate DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX feedindex ON feeds (title DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX e_feedindex ON entries (feed_id DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX m_feedindex ON media (feed_id DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX m_entryindex ON media (entry_id DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX t_feedindex ON tags (feed_id DESC);""")

		self._db.commit()
		
	def _migrate_database_six_seven(self):
		logging.info("upgrading to database schema 7, please wait...")
		self.__remove_columns("feeds", """id INTEGER PRIMARY KEY,
							    url TEXT NOT NULL,
							    pollfail BOOL NOT NULL,
							    title TEXT,
							    description TEXT,
							    link TEXT, 
							    etag TEXT,
							    pollfreq INT NOT NULL,
							    lastpoll DATE,
							    newatlast INT,
							    flags INTEGER NOT NULL DEFAULT 0,
							    feed_pointer INT,
							    image TEXT,
							    UNIQUE(url)""",
						"""id, url, pollfail, title, description, link, 
						   etag, pollfreq, lastpoll, newatlast,
						   flags, feed_pointer, image""")
						   
		self.__remove_columns("entries", """id INTEGER PRIMARY KEY,
						    	feed_id INTEGER UNSIGNED NOT NULL,
					        	title TEXT,
					        	creator TEXT,
					        	description TEXT,
					        	fakedate DATE,
					        	date DATE,
					        	guid TEXT,
					        	link TEXT,
					        	keep INTEGER,
								read INTEGER NOT NULL""",
						"""id, feed_id, title, creator, description,
					        	fakedate, date, guid, link, keep,
								read""")
		
		self._db_execute(self._c, u'ALTER TABLE entries ADD COLUMN hash TEXT')
		
		logging.info("Creating entry hashes")
		self._db_execute(self._c, u'SELECT rowid, description, title, guid FROM entries')
		entries = self._c.fetchall()
		hashes = []
		for entry_id, description, title, guid in entries:
			entry_hash = self._get_hash(guid, title, description)
			self._db_execute(self._c, u'UPDATE entries SET hash=? WHERE rowid=?', \
				(entry_hash, entry_id))
		
		self._db.commit()
		
		self._db_execute(self._c, u'UPDATE settings SET value=7 WHERE data="db_ver"')
		self._db.commit()
		
		
	def __remove_columns(self, table, new_schema, new_columns):
		"""dangerous internal function without injection checking.
		   (only called by migration function and with no user-programmable
		   arguments)"""
		   
		logging.info("updating %s ..." % table)
		
		self._c.execute(u"CREATE TEMPORARY TABLE t_backup(" + new_schema + ")")
		self._c.execute(u"INSERT INTO t_backup SELECT "+new_columns+" FROM " + table)
		self._c.execute(u"DROP TABLE "+ table)
		self._c.execute(u"CREATE TABLE " + table + " ("+ new_schema +")")
		self._c.execute(u"INSERT INTO " + table + " SELECT " + new_columns + " FROM t_backup")
		self._c.execute(u"DROP TABLE t_backup")
		
		self._db.commit()
		
	def __update_flags(self, tag_flag, int_flag):
		"""for migration.  take all feeds with tag tag_flag and add int_flag
		to its flag value.  Then delete the tag_flag"""

		flagged_feeds = self.get_feeds_for_tag(tag_flag)
		
		if len(flagged_feeds) > 0:
			qmarks = "?,"*(len(flagged_feeds)-1)+"?"
			#print u'UPDATE feeds SET flags = flags + ? WHERE feeds.rowid in ('+qmarks+')'
			#print (int_flag,) + tuple(flagged_feeds)
			self._db_execute(self._c, u'UPDATE feeds SET flags = flags + ? WHERE feeds.rowid in ('+qmarks+')', 
							 (int_flag,) + tuple(flagged_feeds))
		
		self.remove_tag(tag_flag)
		
	def _init_database(self):
		self._db_execute(self._c, u"""CREATE TABLE settings
							(
								data TEXT NOT NULL,
								value TEXT
								);""")

		#for pointer / pointed filter feeds, feed_pointer is feed_id, and description is query
		self._db_execute(self._c, u"""CREATE TABLE  feeds
							(
								id INTEGER PRIMARY KEY,
							    url TEXT NOT NULL,
							    pollfail BOOL NOT NULL,
							    title TEXT,
							    description TEXT,
							    link TEXT, 
							    etag TEXT,
							    pollfreq INT NOT NULL,
							    lastpoll DATE,
							    newatlast INT,
							    flags INTEGER NOT NULL DEFAULT 0,
							    feed_pointer INT,
							    image TEXT,
							    UNIQUE(url)
							);""")
							
		self._db_execute(self._c, u"""CREATE TABLE entries
							(
								id INTEGER PRIMARY KEY,
						    	feed_id INTEGER UNSIGNED NOT NULL,
					        	title TEXT,
					        	creator TEXT,
					        	description TEXT,
					        	fakedate DATE,
					        	date DATE,
					        	guid TEXT,
					        	link TEXT,
					        	keep INTEGER,
								read INTEGER NOT NULL,
								hash TEXT
							);""")
		self._db_execute(self._c, u"""CREATE TABLE media
							(
								id INTEGER PRIMARY KEY,
								entry_id INTEGER UNSIGNED NOT NULL,
								feed_id INTEGER UNSIGNED NOT NULL,
								url TEXT NOT NULL,
								file TEXT,
								mimetype TEXT,
								download_status INTEGER NOT NULL,
								viewed BOOL NOT NULL,
								keep BOOL NOT NULL,
								length INTEGER,
								download_date DATE, 
								thumbnail TEXT
							);
							""")
		self._db_execute(self._c, u"""CREATE TABLE tags
							(
							tag TEXT,
							feed_id INT UNSIGNED NOT NULL,
							query TEXT,
							favorite INT,
							type INT);""")
							
		self._db_execute(self._c, u"""CREATE INDEX pollindex ON entries (fakedate DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX feedindex ON feeds (title DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX e_feedindex ON entries (feed_id DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX m_feedindex ON media (feed_id DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX m_entryindex ON media (entry_id DESC);""")
		self._db_execute(self._c, u"""CREATE INDEX t_feedindex ON tags (feed_id DESC);""")
		self._db_execute(self._c, u'UPDATE entries SET keep=0') 
							
		self._db.commit()
		
		self._db_execute(self._c, u"""INSERT INTO settings (data, value) VALUES ("db_ver", 7)""")
		self._db_execute(self._c, u'INSERT INTO settings (data, value) VALUES ("frequency_table_update",0)')
		self._db.commit()
		
	def _get_hash(self, guid, title, description):
		s = sha.new()
		text = STRIPPER_REGEX.sub('', ' '.join((guid, title, description)))
		s.update(text)
		return s.hexdigest()
		
	def _fix_indexes(self):
		try:
			self._db_execute(self._c, 'SELECT sql FROM sqlite_master WHERE name="pollindex"')
			result = self._c.fetchone()[0]
		except:
			result = ""

		if "fakedate" not in result:
			logging.info("Rebuilding indexes")
			#this means the user was using svn before I fixed the indexes
			self._db_execute(self._c, 'SELECT name FROM sqlite_master WHERE type="index"')
			result = self._c.fetchall()
			for index in result:
				if 'autoindex' not in index[0]:
					self._db_execute(self._c, 'DROP INDEX %s' % index)
			self._db.commit()
			
			self._db_execute(self._c, u"""CREATE INDEX pollindex ON entries (fakedate DESC);""")
			self._db_execute(self._c, u"""CREATE INDEX feedindex ON feeds (title DESC);""")
			self._db_execute(self._c, u"""CREATE INDEX e_feedindex ON entries (feed_id DESC);""")
			self._db_execute(self._c, u"""CREATE INDEX m_feedindex ON media (feed_id DESC);""")
			self._db_execute(self._c, u"""CREATE INDEX m_entryindex ON media (entry_id DESC);""")
			self._db_execute(self._c, u"""CREATE INDEX t_feedindex ON tags (feed_id DESC);""")
			logging.info("Indexes rebuilt")
		
	def clean_database_media(self):
		self._db_execute(self._c, "SELECT rowid,file,entry_id FROM media")
		result = self._c.fetchall()
		for item in result:
			self._db_execute(self._c, "SELECT title FROM entries WHERE rowid=?",(item[2],))
			title = self._c.fetchone()
			if title is None: #this entry doesn't exist anymore
				self._db_execute(self._c, "DELETE FROM media WHERE rowid=?",(item[0],))
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
						self._db_execute(self._c, u"SELECT rowid FROM media WHERE file=?",(os.path.join(root, file),))
						result = self._c.fetchone()
						if result is None:
							logging.info("deleting "+os.path.join(root,file))
							os.remove(os.path.join(root,file))
		d = os.walk(media_dir)
		for root,dirs,files in d:
			if root!=media_dir:
				if len(files) == 1:
					if files[0] == "playlist.m3u":
						logging.info("deleting "+root)
						utils.deltree(root)
				elif len(files) == 0:
					logging.info("deleting "+root)
					utils.deltree(root)
					
	def relocate_media(self, old_dir, new_dir):
		"""rewrite db so that media files point to a new place.  Lots of
		checking involved"""
		
		if old_dir[-1] == '/' or old_dir[-1] == '\\':
			old_dir = old_dir[:-1]
			
		assert os.access(new_dir, os.F_OK & os.R_OK & os.W_OK & os.X_OK)
		assert os.access(old_dir, os.F_OK & os.R_OK & os.W_OK & os.X_OK)
	
		self._db_execute(self._c, u'SELECT rowid, file FROM media WHERE file IS NOT NULL')
		rows = self._c.fetchall()
		for rowid, filename in rows:
			assert filename.startswith(old_dir)
			
		for rowid, filename in rows:
			new_filename = os.path.join(new_dir, filename[len(old_dir) + 1:])
			self._db_execute(self._c, u'UPDATE media SET file=? WHERE rowid=?', (new_filename, rowid))
		self._db.commit()
		
	def _check_settings_location(self):
		"""Do we suddenly have gconf, where before we were using the db?
		   If so, migrate from db to gconf"""
		   
		settings_in_db = self.get_setting(BOOL, "settings_in_db", utils.HAS_GCONF, force_db=True)
		settings_now_in_db = settings_in_db
		if settings_in_db:
			if utils.HAS_GCONF:
				self._db_execute(self._c, u'SELECT data, value FROM settings')
				settings = self._c.fetchall()
				for data, value in settings:
					if data.startswith('/'):
						val = self._conf.get_default_from_schema(data)
						if val is None:
							#not in schema, let it be replaced with a default
							continue
						if val.type == gconf.VALUE_BOOL:
							self._conf.set_bool(data, bool(value))
						elif val.type == gconf.VALUE_INT:
							self._conf.set_int(data, int(value))
						elif val.type == gconf.VALUE_STRING:
							self._conf.set_string(data, value)
				settings_now_in_db = False
		else:
			if not utils.HAS_GCONF:
				logging.error("Setting used to be in gconf, but gconf is now missing.  Loading defaults")
				settings_now_in_db = True
		self.set_setting(BOOL, 'settings_in_db', settings_now_in_db, force_db=True)
					
	def get_setting(self, type, datum, default=None, force_db=False):
		if utils.HAS_GCONF and self._initializing_db:
			logging.debug("we are initing db, returning and setting default: %s %s" % (datum, str(default)))
			return default #always return default, gconf LIES
		if utils.HAS_GCONF and datum[0] == '/' and not force_db:
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
				if type == BOOL:
					return bool(int(retval[0]))
				elif type == INT:
					return int(retval[0])
				elif type == STRING:
					return str(retval[0])
				return retval[0]
			return default
				
	def set_setting(self, type, datum, value, force_db=False):
		if utils.HAS_GCONF and datum[0] == '/' and not force_db:
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
		if self._change_setting_cb is not None:
			self._change_setting_cb(type, datum, value)
			
	def set_feed_cache(self, cachelist):
		"""Cachelist format:
		   rowid, flag, unread, total"""
		try:
			fd = open(os.path.join(self.home, 'feed_cache.pickle'), 'w')
			pickle.dump(cachelist, fd)
		except:
			logging.warning("Couldn't create feed_cache.pickle.")
			return
					   
			#self._db_execute(self._c, u'UPDATE feeds SET flag_cache=?, unread_count_cache=?, entry_count_cache=?, first_entry_cache=? WHERE rowid=?',\
							#(cache[1], cache[2], cache[3], cache[4], cache[0]))
			#self._db_execute(self._c, u'UPDATE feeds SET unread_count_cache=? WHERE rowid=?',(cache[2],cache[0]))
			#self._db_execute(self._c, u'UPDATE feeds SET entry_count_cache=? WHERE rowid=?',(cache[3],cache[0]))
		#self._db.commit()
		#and only then...
		self.set_setting(BOOL, "feed_cache_dirty", False)
		self.cache_dirty = False
		
	def get_feed_cache(self):
		if self.cache_dirty:
			logging.debug("Feed cache is dirty, returning empty set")
			return None
		
		try:
			fd = open(os.path.join(self.home, 'feed_cache.pickle'), 'r')
			cache = pickle.load(fd)
		except:
			logging.warning("error loading feed_cache.pickle ")
			return None
			
		
		#self._db_execute(self._c, u'SELECT rowid, flag_cache, unread_count_cache, entry_count_cache, pollfail, first_entry_cache FROM feeds ORDER BY UPPER(TITLE)')
		#cache = self._c.fetchall()
		self.set_setting(BOOL, "feed_cache_dirty", True)
		self.cache_dirty=True
		return cache
		
	def insertURL(self, url, title=None):
		#if a feed with that url doesn't already exists, add it

		self._db_execute(self._c, """SELECT url FROM feeds WHERE url=?""",(url,))
		#on success, fetch will return the url itself
		if self._c.fetchone() != (url,):
			if title is not None:
				self._db_execute(self._c, u"""INSERT INTO feeds (title,url,pollfail,pollfreq,lastpoll,newatlast,flags,feed_pointer,image) VALUES (?, ?,0, 1800,0,0,0,-1,"")""", (title,url)) #default 30 minute polling
			else:
				self._db_execute(self._c, u"""INSERT INTO feeds (title,url,pollfail,pollfreq,lastpoll,newatlast,flags,feed_pointer,image) VALUES (?, ?,0, 1800,0,0,0,-1,"")""", (url,url)) #default 30 minute polling
			self._db.commit()
			#self._db_execute(self._c, u"""SELECT rowid,url FROM feeds WHERE url=?""",(url,))
			self._db_execute(self._c,  "SELECT last_insert_rowid()")
			feed_id = self._c.fetchone()[0]
			d={ 'title':_("Waiting for first poll"),
				'description':_("This feed has not yet been polled successfully.  There might be an error with this feed.<br>"+str(title)),
			  }
			self._db_execute(self._c, u'INSERT INTO entries (feed_id, title, creator, description, read, fakedate, date, guid, link, keep) VALUES (?, ?, NULL, ?, ?, 0, ?, ?, "http://", 0)',(feed_id,d['title'],d['description'],'0', int(time.time()), int(time.time())))
			self._db.commit()
		else:
			self._db_execute(self._c, """SELECT rowid FROM feeds WHERE url=?""",(url,))
			feed_id = self._c.fetchone()
			feed_id = feed_id[0]
			logging.info("db: feed already exists")
			raise FeedAlreadyExists(feed_id)
			
		return feed_id
	
	def add_feed_filter(self, pointed_feed_id, filter_name, query):
		self._db_execute(self._c, u'SELECT rowid,feed_pointer,description FROM feeds WHERE feed_pointer=? AND description=?',(pointed_feed_id,query))
		result = self._c.fetchone()
		if result is None:
			s = sha.new()
			#this is lame I know.  We shouldn't ever get a collision here though!
			s.update(filter_name+query)
			self._db_execute(self._c, u'INSERT INTO feeds (title,url,feed_pointer,description,pollfail,pollfreq,lastpoll,newatlast,flags) VALUES (?, ?,?,?, 0,21600,0,0,0)', (filter_name,s.hexdigest(),pointed_feed_id,query))
			self._db.commit()
			#self._db_execute(self._c, u'SELECT rowid FROM feeds WHERE feed_pointer=? AND description=?',(pointed_feed_id,query))
			self._db_execute(self._c,  "SELECT last_insert_rowid()")
			return self._c.fetchone()[0]
		else:
			raise FeedAlreadyExists, result[0]
			
	def set_feed_filter(self, pointer_feed_id, filter_name, query):
		self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE rowid=?',(pointer_feed_id,))
		pointed_id = self._c.fetchone()
		if pointed_id is None:
			raise NoFeed, pointer_feed_id
		pointed_id = pointed_id[0]
		self._db_execute(self._c, u'SELECT rowid FROM feeds WHERE feed_pointer=? AND description=?',(pointed_id,query))
		result = self._c.fetchone()
		if result is None:
			self._db_execute(self._c, u'UPDATE feeds SET title=?, description=? WHERE rowid=?',(filter_name, query, pointer_feed_id))
			self._db.commit()
		else:
			raise FeedAlreadyExists, result[0]
				
	def delete_feed(self, feed_id):
		#check for valid entry		
		self._db_execute(self._c, """SELECT rowid FROM feeds WHERE rowid=?""",(feed_id,))
		result = self._c.fetchone()[0]

		if result != feed_id:			
			raise NoFeed,feed_id
		
		#delete the feed, its entries, and its media (this does not delete files)
		self._db_execute(self._c, """DELETE FROM feeds WHERE rowid=?""",(feed_id,))
		self._reindex_feed_list.append(feed_id)
		self._db_execute(self._c, u'DELETE FROM tags WHERE feed_id=?',(feed_id,))
		self._db.commit()
		#result = self._c.fetchone()
		#print(result)
		
		self._icon_manager.remove_icon(feed_id)
		
		self._db_execute(self._c, 'SELECT rowid FROM entries WHERE feed_id=?',(feed_id,))
		data=self._c.fetchall()
		if data: 
			dataList = [list(row) for row in data]
			for datum in dataList:
				if self._image_cache is not None:
					self._image_cache.remove_cache(datum[0])
				self._db_execute(self._c, 'SELECT rowid FROM media WHERE entry_id=?',(datum[0],))
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
			logging.error("Error deleting: "+str(detail))
		#but keep going in case the dirs are empty now
		try:
			#now check to see if we should get rid of the dated dir
			import glob
			globlist = glob.glob(os.path.split(media['file'])[0]+"/*")
			if len(globlist)==1 and os.path.split(globlist[0])[1]=="playlist.m3u": #if only the playlist is left, we're done
				utils.deltree(os.path.split(media['file'])[0])
			if len(globlist)==0: #similarly, if dir is empty, we're done.
				utils.deltree(os.path.split(media['file'])[0])
		except os.error, detail:
			logging.error("Error deleting dirs: "+str(detail))
		#if everything worked, set status
		self.set_media_download_status(media_id,D_NOT_DOWNLOADED)			
		
	def delete_bad(self):	
		self._db_execute(self._c, """DELETE FROM feeds WHERE title IS NULL""")
		self._db.commit()
		
	def poll_multiple(self, arguments=0, feeds=None):
		"""Polls multiple feeds multithreadedly"""
		successes=[]
		cur_time = int(time.time())
		self._cancel_poll_multiple = False
		
		if feeds is None:
			if arguments & A_AUTOTUNE and arguments & A_ALL_FEEDS == 0:
				self._db_execute(self._c, 'SELECT rowid FROM feeds WHERE (? - lastpoll) >= pollfreq ORDER BY pollfreq', (cur_time,))
			elif arguments & A_ERROR_FEEDS:
				self._db_execute(self._c, 'SELECT rowid FROM feeds WHERE pollfail=1 ORDER BY pollfreq')
			else: #polling all
				self._db_execute(self._c, 'SELECT rowid FROM feeds ORDER BY pollfreq')
				
			data=self._c.fetchall()
			if data: 
				feeds = [row[0] for row in data]
			else:
				self.polling_callback((-1, [], 0), False)
				return 0
		
		#don't renice on hildon because we can't renice
		#back down to zero again
		#if not utils.RUNNING_HILDON:
		#	os.nice(2)
				
		threadcount = 5
		if utils.RUNNING_HILDON or utils.RUNNING_SUGAR:
			threadcount = 2
		pool = ThreadPool.ThreadPool(threadcount,"ptvDB", lucene_compat = utils.HAS_LUCENE)
		self._parse_list = []
		for feed in feeds:
			if self._cancel_poll_multiple or self._exiting:
				break
			self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE rowid=?',(feed,))
			result = self._c.fetchone()[0]
			if result >= 0:
				self._parse_list.append((feed, arguments, len(feeds), -2)) 
				continue
				
			self._db_execute(self._c, """SELECT url,etag FROM feeds WHERE rowid=?""",(feed,))
			data = self._c.fetchone()
			pool.queueTask(self._pool_poll_feed,(feed,arguments,len(feeds), data),self._poll_mult_cb)
			
		polled = 0
		total = 0
		#grow the cache while we do this operation
		#self._db_execute(self._c, 'PRAGMA cache_size=6000')
		while polled < len(feeds):
			if self._cancel_poll_multiple or self._exiting:
				break
			if len(self._parse_list) > 0:
				polled+=1
				feed_id, args, total, parsed = self._parse_list.pop(0)
				self.polling_callback(self._process_feed(feed_id, args, total, parsed))
				gc.collect()
			time.sleep(.1)
		#self._db_execute(self._c, 'PRAGMA cache_size=2000')
		
		if self._cancel_poll_multiple:
			self._parse_list = []
			#pass dummy poll result, send cancel signal
			self.polling_callback((-1, [], total), True)
		else: # no need for manual join
			while pool.getTaskCount()>0: #manual joinAll so we can check for exit
				if self._exiting:
					pool.joinAll(False, True)
					del pool
					self._c.close()
					self._db.close()
					#if not utils.RUNNING_HILDON:
					#	os.nice(-2)
					return total
				time.sleep(.5)
		pool.joinAll(False,True) #just to make sure I guess
		del pool
		self.reindex()
		if not self._exiting:
			self.cache_images()
		self._cancel_poll_multiple = False
		gc.collect()
		#if not utils.RUNNING_HILDON:
		#	os.nice(-2)
		return total
		
	def interrupt_poll_multiple(self):
		self._cancel_poll_multiple = True
		
	def _poll_mult_cb(self, args):
		feed_id, args, total, parsed = args
		self._parse_list.append((feed_id, args, total, parsed))
		
	def _pool_poll_feed(self, args):
		feed_id, arguments, total, data = args
		url,etag=data
		
		#save ram by not piling up polled data
		if utils.RUNNING_SUGAR or utils.RUNNING_HILDON:
			parse_list_limit = 10
		else:
			parse_list_limit = 50
		
		while len(self._parse_list) > parse_list_limit and not self._exiting:
			time.sleep(1)
			
		if self._exiting:
			return (feed_id, arguments, total, -1)
		
		try:
			import feedparser
			#feedparser.disableWellFormedCheck=1  #do we still need this?  it used to cause crashes
			#speed up feedparser
			#must sanitize because some feeds have POPUPS!
			if utils.RUNNING_SUGAR:
				#feedparser._sanitizeHTML = lambda a, b: a
				feedparser._resolveRelativeURIs = lambda a, b, c: a
			if arguments & A_IGNORE_ETAG == A_IGNORE_ETAG:
				data = feedparser.parse(url)
			else:
				data = feedparser.parse(url,etag)
			return (feed_id, arguments, total, data)
		except Exception, e:
			logging.error(str(e))
			return (feed_id, arguments, total, -1)

	def _process_feed(self,feed_id, args, total, data, recurse=0):
		"""a wrapper function that returns the index along with the result
		so we can sort.  Each poller needs its own db connection for locking reasons"""
		
		self._db_execute(self._c, u'SELECT lastpoll FROM feeds WHERE rowid=?', (feed_id,))
		last_poll_time = self._c.fetchone()[0]
		
		poll_arguments = 0
		result = 0
		try:
			#poll_arguments = args[1]
			if self._exiting:
				return (feed_id,{'ioerror':None, 'pollfail':False}, total)
			
			result, new_entryids = self.poll_feed(feed_id, args | A_POOLED_POLL, preparsed=data)

			if self._exiting:
				return (feed_id,{'ioerror':None, 'pollfail':False}, total)
		except sqlite.OperationalError, e:
			logging.warning("Database warning..." + str(e))
			if recurse < 2:
				time.sleep(5)
				logging.warning("trying again...")
				self._db.close()
				self._db=sqlite.connect(os.path.join(self.home,"penguintv4.db"), timeout=30, isolation_level="IMMEDIATE")
				self._c = self._db.cursor()
				return self._process_feed(feed_id, args, total, data, recurse+1) #and reconnect
			logging.warning("can't get lock, giving up")
			return (feed_id,{'pollfail':True}, total)
		except FeedPollError,e:
			#print "feed poll error",
			logging.warning(str(e))
			return (feed_id,{'pollfail':True}, total)
		except IOError, e:
			#print "io error",
			logging.warning(str(e))
			#we got an ioerror, but we won't take it out on the feed
			return (feed_id,{'ioerror':e, 'pollfail':False}, total)
		except:
			logging.warning("other error polling feed:" + str(feed_id))
			exc_type, exc_value, exc_traceback = sys.exc_info()
			error_msg = ""
			for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
				error_msg += s
			logging.error(error_msg)
			return (feed_id,{'pollfail':True}, total)
			
		#assemble our handy dictionary while we're in a thread
		update_data={}
		
		if result > 0:
			update_data['first_poll'] = last_poll_time == 0
			update_data['new_entries'] = result
			update_data['new_entryids'] = new_entryids
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
					logging.info("have pointers, reindexing now")
					self.reindex()
					
				update_data['flag_list']=flag_list
				update_data['pollfail']=False
			update_data['no_changes'] = False
		elif result == 0:
			flag_list = self.get_entry_flags(feed_id)
			update_data['flag_list']=flag_list
			update_data['pollfail'] = False
			update_data['no_changes'] = True
			update_data['first_poll'] = False
				
		return (feed_id, update_data, total)
			
	def poll_feed_trap_errors(self, feed_id, callback):
		try:
			feed={}
			self._db_execute(self._c, "SELECT title,url FROM feeds WHERE rowid=?",(feed_id,))
			result = self._c.fetchone()
			feed['feed_id']=feed_id
			feed['url']=result[1]
			feed['new_entries'], feed['new_entryids'] = \
				self.poll_feed(feed_id, A_IGNORE_ETAG+A_DO_REINDEX)
			callback(feed, True)
		except Exception, e:#FeedPollError,e:
			logging.warning(str(e))
			logging.warning("error polling feed:")
			exc_type, exc_value, exc_traceback = sys.exc_info()
			error_msg = ""
			for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
				error_msg += s
			logging.warning(error_msg)
			self.reindex()
			callback(feed, False)

	def _polling_callback(self, data):
		print "look a callback"
		print data
		
	def poll_feed(self, feed_id, arguments=0, preparsed=None):
		"""polls a feed and returns the number of new articles and a flag list.  Optionally, one can pass
			a feedparser dictionary in the preparsed argument and avoid network operations"""
		
		def perform_feed_updates(updates, f_id):
			if not updates.has_key('pollfail'):
				updates['pollfail'] = 0
			#logging.debug("setting pollfail to %i for %i" % (updates['pollfail'], f_id))
			updated_fields = ", ".join(["%s=?" % k for k in updates.keys()])
			updated_values = tuple([updates[k] for k in updates.keys()])
			self._db_execute(self._c, u"""UPDATE feeds SET %s WHERE rowid=?""" % updated_fields, updated_values + (feed_id,))
			self._db.commit()

		self._db_execute(self._c, u'SELECT feed_pointer, url, etag, image, title, link, flags, lastpoll, newatlast, pollfreq FROM feeds WHERE rowid=?', (feed_id,))
		result = self._c.fetchone()
		feed = {}
		feed['feed_id'] = feed_id
		feed['feed_pointer'] = result[0]
		feed['url'] = result[1]
		feed['etag'] = result[2]
		feed['image'] = result[3]
		feed['title'] = result[4]
		feed['link'] = result[5]
		feed['flags'] = result[6]
		feed['last_time'] = result[7]
		feed['netatlast'] = result[8]
		feed['old_poll_freq'] = result[9]
		

		if preparsed is None:
			#feed_id = self._resolve_pointed_feed(feed_id)
			#self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE rowid=?',(feed_id,))
			#result =self._c.fetchone()
			#if result:
			if feed['feed_pointer'] >= 0:
				return 0, []
				
			#self._db_execute(self._c, """SELECT url,etag FROM feeds WHERE rowid=?""",(feed_id,))
			#data = self._c.fetchone()
			try:
				import feedparser
				#feedparser.disableWellFormedCheck=1  #do we still need this?  it used to cause crashes
				
				#speed up feedparser
				if utils.RUNNING_SUGAR or utils.RUNNING_HILDON:
					#feedparser._sanitizeHTML = lambda a, b: a
					feedparser._resolveRelativeURIs = lambda a, b, c: a
				
				if arguments & A_IGNORE_ETAG == A_IGNORE_ETAG:
					data = feedparser.parse(feed['url'])
				else:
					data = feedparser.parse(feed['url'], feed['etag'])
			except Exception, e:
				feed_updates = {}
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					feed_updates = self._set_new_update_freq(feed, 0)
				logging.warning("feedparser exception: %s" % str(e))
				feed_updates['pollfail'] = 1
				#self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE rowid=?""",(feed_id,))
				#self._db.commit()
				perform_feed_updates(feed_updates, feed_id)
				logging.warning(str(e))
				raise FeedPollError,(feed_id,"feedparser blew a gasket")
		else:
			if preparsed == -1:
				feed_updates = {}
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					feed_updates = self._set_new_update_freq(feed, 0)
				logging.warning("bad preparsed")
				feed_updates['pollfail'] = 1
				#self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE rowid=?""",(feed_id,))
				#self._db.commit()
				perform_feed_updates(feed_updates, feed_id)
				raise FeedPollError,(feed_id,"feedparser blew a gasket")
			elif preparsed == -2:
				#print "pointer feed, returning 0"
				return 0, []
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
				feed_updates = {}
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					feed_updates = self._set_new_update_freq(feed, 0)
				#feed_updates['pollfail'] = 1
				#self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE rowid=?""",(feed_id,))
				#self._db.commit()
				perform_feed_updates(feed_updates, feed_id)
				return 0, []
			if data['status'] == 404: #whoops
				feed_updates = {}
				if arguments & A_AUTOTUNE == A_AUTOTUNE:
					feed_updates = self._set_new_update_freq(feed, 0)
				feed_updates['pollfail'] = 1
				#self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE rowid=?""",(feed_id,))
				#self._db.commit()
				perform_feed_updates(feed_updates, feed_id)
				raise FeedPollError,(feed_id,"404 not found: "+str(url))

		if len(data['feed']) == 0 or len(data['items']) == 0:
			#print data
			if data.has_key('bozo_exception'):
				if isinstance(data['bozo_exception'], URLError):
					e = data['bozo_exception'][0]
					#logging.debug(str(e))
					errno = e[0]
					if errno in (#-2, # Name or service not known 
								-3, #failure in name resolution   
								101, #Network is unreachable
								114, #Operation already in progress
								11):  #Resource temporarily unavailable
						raise IOError(e)
					elif errno == -2: #could be no site, could be no internet
						try:
							#this really should work, right?
							#fixme: let's find a real way to test internet, hm?
							u = urllib.urlretrieve("http://www.google.com")
						except IOError, e2:
							raise IOError(e)
			feed_updates = {}
			if arguments & A_AUTOTUNE == A_AUTOTUNE:
				feed_updates = self._set_new_update_freq(feed, 0)
			feed_updates['pollfail'] = 1
			#self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE rowid=?""",(feed_id,))
			#self._db.commit()
			perform_feed_updates(feed_updates, feed_id)
			#logging.debug("empty: %s"  % str(data))
			raise FeedPollError,(feed_id,"empty feed")
			
		#else...
		
		feed_updates = {}
		
		#see if we need to get an image
		if not self._icon_manager.icon_exists(feed_id):
			href = self._icon_manager.download_icon(feed_id, data)
			if href is not None:
				#self._db_execute(self._c, u"""UPDATE feeds SET image=? WHERE rowid=?""",(href,feed_id))
				feed_updates['image'] = href
		else:
			#self._db_execute(self._c, u"""SELECT image FROM feeds WHERE rowid=?""",(feed_id,))
			#try: old_href = self._c.fetchone()[0]
			#except: old_href = ""
			
			if not self._icon_manager.is_icon_up_to_date(feed_id, feed['image'], data):
				self._icon_manager.remove_icon(feed_id)
				href = self._icon_manager.download_icon(feed_id, data)
				if href is not None:
					#self._db_execute(self._c, u"""UPDATE feeds SET image=? WHERE rowid=?""",(href,feed_id))
					feed_updates['image'] = href		
		
		if arguments & A_DELETE_ENTRIES == A_DELETE_ENTRIES:
			logging.info("deleting existing entries"  + str(feed_id) + str(arguments))
			self._db_execute(self._c, """DELETE FROM entries WHERE feed_id=?""",(feed_id,))
			#self._db.commit()
		#to discover the old entries, first we mark everything as old
		#later, we well unset this flag for everything that is NEW,
		#MODIFIED, and EXISTS. anything still flagged should be deleted  
		#self._db_execute(self._c, """UPDATE entries SET old=1 WHERE feed_id=?""",(feed_id,))
		feed_updates['pollfail'] = 0
		#self._db_execute(self._c, """UPDATE feeds SET pollfail=0 WHERE rowid=?""",(feed_id,))
	
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
		#if not data.has_key('modified'):
		#	modified='0'
		#else:
		#	modified = int(time.mktime(data['modified']))

		try:
			#self._db_execute(self._c, u'SELECT title FROM feeds WHERE rowid=?',(feed_id,))
			#exists=self._c.fetchone()
			
			if len(feed['title'])>4:
				#self._db_execute(self._c, """UPDATE feeds SET description=?, modified=?, etag=? WHERE rowid=?""", (channel['description'], modified,data['etag'],feed_id))
				if feed['title'][0:4] == "http": #hack to detect when the title hasn't been set yet because of first poll
					feed_updates['title'] = channel['title']
					#self._db_execute(self._c, """UPDATE feeds SET title=?, description=?, modified=?, etag=? WHERE rowid=?""", (channel['title'],channel['description'], modified,data['etag'],feed_id))
			elif len(feed['title'])>0: #don't change title
				#self._db_execute(self._c, """UPDATE feeds SET description=?, modified=?, etag=? WHERE rowid=?""", (channel['description'], modified,data['etag'],feed_id))
				if feed['title'] is None:
					feed_updates['title'] = channel['title']
					#self._db_execute(self._c, """UPDATE feeds SET title=?, description=?, modified=?, etag=? WHERE rowid=?""", (channel['title'],channel['description'], modified,data['etag'],feed_id))
			else:
				feed_updates['title'] = channel['title']
				feed_updates['description'] = channel['description']
				feed_updates['etag'] = data['etag']
				#self._db_execute(self._c, """UPDATE feeds SET title=?, description=?, etag=? WHERE rowid=?""", (channel['title'],channel['description'], data['etag'],feed_id))
			self._reindex_feed_list.append(feed_id)
			
			feed_updates['description'] = channel['description']
			feed_updates['etag'] = data['etag']
		except Exception, e:
			logging.warning(str(e))
			feed_updates['pollfail'] = 1
			#self._db_execute(self._c, """UPDATE feeds SET pollfail=1 WHERE rowid=?""",(feed_id,))
			perform_feed_updates(feed_updates, feed_id)
			raise FeedPollError,(feed_id,"error updating title and description of feed")
			
		#self._db_execute(self._c, u'SELECT link FROM feeds WHERE rowid=?',(feed_id,))
		#link = self._c.fetchone()
		#if link is not None:
		#		link = link[0]
		#if there was no result, or result is None, it's blank
		
		if feed['link'] is None:
			feed['link'] = ""
		if feed['link'] == "" and data['feed'].has_key('link'):
			feed_updates['link'] = data['feed']['link']
			#self._db_execute(self._c, u'UPDATE feeds SET link=? WHERE rowid=?',(data['feed']['link'],feed_id))
		#self._db.commit()
		
		#populate the entries
		#only look as far back as 1000% for existing entries
		#existing_limit = int(len(data['items']) * 10)
		#print "only checking", existing_limit
		self._db_execute(self._c, 
			#"""SELECT rowid,guid,link,title,description FROM entries WHERE feed_id=? ORDER BY fakedate DESC LIMIT %i""" % existing_limit,
			"""SELECT rowid,guid,link,title,description,hash FROM entries WHERE feed_id=? ORDER BY fakedate DESC""",
			(feed_id,)) 
		existing_entries = self._c.fetchall()
		#logging.debug("existing entries: %i" % len(existing_entries))
		#print "got", len(existing_entries)
		
		#only use GUID if there are no dupes -- thanks peter's feed >-(
		guid_quality = 0.0
		if len(existing_entries) > 0:
			guids = [e[1] for e in existing_entries]
			guids.sort()	
			if len(guids[0]) > 2: #too short to be valuable
				prev_g = guids[0]
				dupe_count = 0.0
				for g in guids[1:50]: #up to first 50 is fine
					if g == prev_g:
						dupe_count += 1.0
					prev_g = g
				guid_quality = 1 - (dupe_count / len(existing_entries))
		
		#we can't trust the dates inside the items for timing data.
		#Bad formats, no dates at all, and timezones screw things up
		#so I introduce a fake date which works for determining read and
		#unread article counts, and keeps the articles in order
		fake_time = int(time.time())
		i=0
		
		new_items = 0
		
		flag_list = []
		no_delete = []
		new_entryids = []
		
		default_read = int(feed['flags'] & FF_MARKASREAD == FF_MARKASREAD)
		
		self._db_execute(self._c, u"""SELECT entry_id FROM media WHERE feed_id=?""", (feed_id,))
		media_entries = self._c.fetchall()
		if media_entries is None:
			media_entries = []
		else:
			media_entries = [r[0] for r in media_entries]
	
		#logging.debug("feed has %i items" % len(data['items']))
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
					#p = utils.StrippingParser()
					#p.feed(item['description'])
					##p.cleanup()
					#p.close()
					#item['title']=p.result[0:35]
					item['title'] = STRIPPER_REGEX.sub('', item['description'])[:35]
			elif item['title']=="":
				item['title']=item['description'][0:35]
				html_begin = string.find(item['title'],'<')
				if html_begin >= 0 and html_begin < 5: #in case it _begins_ with html, and the html is really early
					#p = utils.StrippingParser()
					#p.feed(item['description'])
					##p.cleanup()
					#p.close()
					#item['title']=p.result[0:35]
					item['title'] = STRIPPER_REGEX.sub('', item['description'])[:35]
			
				elif html_begin > 5: #in case there's html within 35 chars...
					item['title']=item['title'][0:html_begin-1] #strip
					#things mess up if a title ends in a space, so strip trailing spaces
				#doublecheck
				if len(item['title'])==0:
					item['title']='untitled'
				else:
					item['title'] = item['title'].strip()
			
			try:
				#p = utils.StrippingParser()
				#p.feed(item['title'])
				##p.cleanup()
				#p.close()
				#item['title'] = p.result	
				item['title'] = STRIPPER_REGEX.sub('', item['title'])			
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
			for uni in _common_unicode.keys():
				item['title'] = item['title'].replace(uni, _common_unicode[uni])
		
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
				item['date_parsed']=time.localtime()
				
			entry_hash = self._get_hash(item['guid'], item['title'], item['body'])
			status = self._get_status(item, entry_hash, existing_entries, guid_quality, media_entries)
			
			if status[0]==NEW:
				new_items = new_items+1
				self._db_execute(self._c, u'INSERT INTO entries (feed_id, title, creator, description, read, fakedate, date, guid, link, keep, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)',
						(feed_id,item['title'],item['creator'],item['body'],
						default_read,fake_time-i, 
						int(time.mktime(item['date_parsed'])),
						item['guid'],item['link'], entry_hash))
				self._db_execute(self._c,  "SELECT last_insert_rowid()")
				entry_id = self._c.fetchone()[0]
				if item.has_key('enclosures'):
					for media in item['enclosures']:
						media.setdefault('length', 0)
						media.setdefault('type', 'application/octet-stream')
						self._db_execute(self._c, u"""INSERT INTO media (entry_id, url, mimetype, download_status, viewed, keep, length, feed_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (entry_id, media['url'], media['type'], D_NOT_DOWNLOADED, default_read, 0, media['length'], feed_id))
						
				self._reindex_entry_list.append(entry_id)
				self._image_cache_list.append(entry_id)
				no_delete.append(entry_id)
				new_entryids.append(entry_id)
			elif status[0]==EXISTS:
				entry_id = status[1]
				no_delete.append(entry_id)
			elif status[0]==MODIFIED:
				entry_id = status[1]
				self._db_execute(self._c, u'UPDATE entries SET title=?, creator=?, description=?, date=?, guid=?, link=?, hash=? WHERE rowid=?',
								 (item['title'],item['creator'],item['body'], 
								 int(time.mktime(item['date_parsed'])),item['guid'],
								 item['link'], entry_hash, entry_id))
				if self.entry_flag_cache.has_key(entry_id): del self.entry_flag_cache[entry_id]
				if item.has_key('enclosures'):
					#self._db_execute(self._c, u'SELECT url FROM media WHERE entry_id=? AND (download_status=? OR download_status=?)',
					#				(entry_id,D_NOT_DOWNLOADED,D_ERROR))
					self._db_execute(self._c, u'SELECT url FROM media WHERE entry_id=?', (entry_id,))
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
						for media in item['enclosures']: #add the rest
							if media['url'] in added:
								#if dburl[0] != media['url']: #only add if that url doesn't exist
								media.setdefault('length', 0)
								media.setdefault('type', 'application/octet-stream')
								self._db_execute(self._c, u"""INSERT INTO media (entry_id, url, mimetype, download_status, viewed, keep, length, download_date, feed_id) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""", (entry_id, media['url'], media['type'], D_NOT_DOWNLOADED, default_read, 0, media['length'], feed_id))
								self._db_execute(self._c, u'UPDATE entries SET read=0 WHERE rowid=?', (entry_id,))
				
				self._reindex_entry_list.append(entry_id)
				self._image_cache_list.append(entry_id)
				no_delete.append(entry_id)
			i+=1

		#don't call anything old that has media...
		self._db_execute(self._c, """SELECT entry_id FROM media WHERE download_status>0 AND feed_id=?""",(feed_id,))
		result = self._c.fetchall()
		if result:
			#combine with EXISTing entries
			no_delete += [r[0] for r in result]
		
		# anything not set above as new, mod, or exists is no longer in
		# the xml and therefore could be deleted if we have more articles than 
		# the limit
		
		self._db_execute(self._c, """SELECT count(*) FROM entries WHERE feed_id=?""",(feed_id,))
		all_entries = self._c.fetchone()[0]
		
		nokeepdeleted = int(feed['flags'] & FF_NOKEEPDELETED == FF_NOKEEPDELETED)
		if nokeepdeleted:
			if len(no_delete) > 0:
				qmarks = "?,"*(len(no_delete)-1)+"?"
				self._db_execute(self._c, 
					"""DELETE FROM entries WHERE rowid NOT IN (%s) AND keep=0 AND feed_id=?""" % qmarks,
					tuple(no_delete) + (feed_id,))
				ditchables = self._c.fetchall()
			else:
				self._db_execute(self._c, 
					"""DELETE FROM entries WHERE keep=0 AND feed_id=?""",
					(feed_id,))
				ditchables = self._c.fetchall()
		elif MAX_ARTICLES > 0:
			if all_entries > MAX_ARTICLES:
				if len(no_delete) > 0:
					qmarks = "?,"*(len(no_delete)-1)+"?"
					self._db_execute(self._c, """SELECT rowid FROM entries WHERE rowid NOT IN (%s) AND keep=0 AND feed_id=? ORDER BY fakedate LIMIT ?""" % qmarks,
						tuple(no_delete) + (feed_id, all_entries - MAX_ARTICLES))
					ditchables = self._c.fetchall()
				else:
					self._db_execute(self._c, """SELECT rowid FROM entries WHERE keep=0 AND feed_id=? ORDER BY fakedate LIMIT ?""",
						(feed_id, all_entries - MAX_ARTICLES))
					ditchables = self._c.fetchall()
					
				if ditchables is not None:
					if len(ditchables) > 0:
						ditchables = tuple([r[0] for r in ditchables])
						qmarks = "?,"*(len(ditchables)-1)+"?"
						self._db_execute(self._c, """DELETE FROM entries WHERE rowid IN (%s)""" % qmarks, ditchables)
						for e_id in ditchables:
							self._image_uncache_list.append(e_id)
			
		#delete pre-poll entry
		if feed['last_time'] == 0:
			self._db_execute(self._c, "DELETE FROM entries WHERE fakedate=0 AND feed_id=?",(feed_id,))

		if arguments & A_AUTOTUNE == A_AUTOTUNE:
			result = self._set_new_update_freq(feed, new_items)
			feed_updates.update(result)
		else:
			cur_time = int(time.time())
			feed_updates['lastpoll'] = cur_time
			#self._db_execute(self._c, u'UPDATE feeds SET lastpoll=? WHERE rowid=?',(cur_time,feed_id))

		perform_feed_updates(feed_updates, feed_id)
		
		if arguments & A_POOLED_POLL == 0:
			if arguments & A_DO_REINDEX:
				if new_items > 0:
					self.reindex()
			self.cache_images()
		return (new_items, new_entryids)
		
	def _set_new_update_freq(self, feed, new_items):
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
		
		feed_updates = {}
		
		#should never be called on a filtered feed
		
		cur_time = int(time.time())
		#this could suck if the program was just started, so only do it if the poll_freq seems correct
		#however still update the db with the poll time
		feed_updates['lastpoll'] = cur_time
		feed_updates['newatlast'] = new_items
		if cur_time - feed['last_time'] < feed['old_poll_freq']/2:  #too soon to get a good reading.
			return feed_updates
		
		#normalize dif:
		new_items = round(new_items *  feed['old_poll_freq'] / (cur_time- feed['last_time']))
		
		if new_items==0:
			#figure out the average time between article postings
			#this algorithm seems to be the most accurate based on my own personal judgment
			self._db_execute(self._c, 'SELECT date FROM entries WHERE feed_id=?',(feed['feed_id'],))
			datelist = self._c.fetchall()
			datelist.append((int(time.time()),)) #helps in some cases to pretend we found one now
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
			modifier = avg / feed['old_poll_freq']
			poll_freq = round(feed['old_poll_freq'] + modifier*60)
		elif new_items>1:
			poll_freq = floor((cur_time - feed['last_time']) / new_items)
		else:
			return feed_updates
			
		if poll_freq > 21600: #four hours
			poll_freq = 21600
		if poll_freq < 1800: #30 mins
			poll_freq = 1800
	
		feed_updates['pollfreq'] = poll_freq
		return feed_updates
		
	def _get_status(self, item, new_hash, existing_entries, guid_quality, media_entries):
		"""returns status, the entry_id of the matching entry (if any), and the media list if unmodified"""
		ID=0
		GUID=1
		LINK=2
		TITLE=3
		BODY=4
		HASH=5

		entry_id=-1
		
		t_item = {'guid': item['guid'],
				'body': item['body'],
				'link': item['link'],
				'title': item['title']}
				
		#debug_i = 0
		for entry_item in existing_entries:
			if guid_quality > 0.7: 
				if str(entry_item[GUID]) == str(t_item['guid']):
					entry_id = entry_item[ID]
					old_hash = entry_item[HASH]
					#logging.debug("found match at %i (%f)" % (debug_i, debug_i / float(len(existing_entries))))
					break
			elif guid_quality > 0.1:
				if str(entry_item[GUID]) == str(t_item['guid']):
					if entry_item[TITLE] == t_item['title']:
						entry_id = entry_item[ID]
						old_hash = entry_item[HASH]
						#logging.debug("found match at %i (%f)" % (debug_i, debug_i / float(len(existing_entries))))
						break
			elif t_item['link'] != '':
				if entry_item[LINK] == t_item['link']:
					if entry_item[TITLE] == t_item['title']:
						entry_id = entry_item[ID]
						old_hash = entry_item[HASH]
						#logging.debug("found match at %i (%f)" % (debug_i, debug_i / float(len(existing_entries))))
						break
					elif entry_item[BODY] == t_item['body']:
						entry_id = entry_item[ID]
						old_hash = entry_item[HASH]
						#logging.debug("found match at %i (%f)" % (debug_i, debug_i / float(len(existing_entries))))
						break
			elif entry_item[TITLE] == t_item['title']:
				entry_id = entry_item[ID]
				old_hash = entry_item[HASH]
				#logging.debug("found match at %i (%f)" % (debug_i, debug_i / float(len(existing_entries))))
				break
			elif entry_item[BODY] == t_item['body']:
				entry_id = entry_item[ID]
				old_hash = entry_item[HASH]
				#logging.debug("found match at %i (%f)" % (debug_i, debug_i / float(len(existing_entries))))
				break
			#debug_i += 1

		if entry_id == -1:
			return (NEW, -1, [])

		if new_hash == old_hash:
			#now check enclosures
			if entry_id not in media_entries:
				old_media = []
			else:
				old_media = self.get_entry_media(entry_id)

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
			
			old_media = [urlparse.urlparse(medium['url'])[:3] for medium in old_media]
			new_media = [urlparse.urlparse(m['url'])[:3] for m in item['enclosures']]
			
			old_media = utils.uniquer(old_media)
			old_media.sort()
			new_media = utils.uniquer(new_media)
			new_media.sort()
			
			if old_media != new_media:
				return (MODIFIED,entry_id,[])
			return (EXISTS,entry_id, existing_media)
		else:
			#logging.debug("entry is modified")
			return (MODIFIED,entry_id, [])
			
	def get_entry_media(self, entry_id):
		self._db_execute(self._c, """SELECT rowid,entry_id,url,file,download_status,viewed,length,mimetype FROM media WHERE entry_id = ? ORDER BY entry_id DESC""",(entry_id,))
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
		
		self._db_execute(self._c, """SELECT rowid,entry_id,url,file,download_status,viewed,length,mimetype FROM media WHERE entry_id in ("""+qmarks+')',tuple(entry_list))
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
		self._db_execute(self._c, u'SELECT url, download_status, length, file, entry_id, viewed, mimetype, feed_id FROM media WHERE rowid=?',(media_id,))
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
		medium['feed_id']=datum[7] #MAGIC
		return medium
		
	def get_feed_media_count(self, feed_id):
		self._db_execute(self._c, u'SELECT count(*) FROM media WHERE feed_id=?',(feed_id,))
		return self._c.fetchone()[0]
	
	def get_entry(self, entry_id, ajax_url=None):
		self._db_execute(self._c, """SELECT title, creator, link, description, feed_id, date, read, keep, guid, hash FROM entries WHERE rowid=? LIMIT 1""",(entry_id,))
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
			entry_dic['keep'] = result[7]
			entry_dic['guid'] = result[8]
			entry_dic['hash'] = result[9]
			entry_dic['entry_id'] = entry_id
		except TypeError: #this error occurs when feed or item is wrong
			raise NoEntry, entry_id
		
		if self._image_cache is not None:
			entry_dic['description'] = self._image_cache.rewrite_html(str(entry_id), entry_dic['description'], ajax_url)
			
		return entry_dic
		
	def get_entry_block(self, entry_list, ajax_url=None):
		if len(entry_list) == 0:
			return []
		qmarks = "?,"*(len(entry_list)-1)+"?"
		self._db_execute(self._c, u'SELECT title, creator, link, description, feed_id, date, read, rowid, keep, guid, hash FROM entries WHERE rowid in ('+qmarks+')', (tuple(entry_list)))
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
			entry_dic['keep'] = entry[8]
			entry_dic['guid'] = entry[9]
			entry_dic['hash'] = entry[10]
			
			if self._image_cache is not None:
				entry_dic['description'] = self._image_cache.rewrite_html(str(entry_dic['entry_id']), entry_dic['description'], ajax_url)

			retval.append(entry_dic)
		return retval
		
	def get_entries_since(self, timestamp):
		self._db_execute(self._c, u'SELECT feed_id, rowid, hash, read FROM entries WHERE fakedate > ?', (timestamp,))
		result = self._c.fetchall()
		if result is None:
			return []
		else:
			return result
			
	def get_kept_entries(self, feed_id):
		self._db_execute(self._c, u'SELECT rowid FROM entries WHERE keep=1 AND feed_id=?', (feed_id,))
		result = self._c.fetchall()
		if result is None:
			return []
		else:
			return [r[0] for r in result]
			
	def get_filtered_entries(self, feed_index):
		"""Assumes this is a feed pointer"""
		self._db_execute(self._c, u'SELECT feed_pointer,description FROM feeds WHERE rowid=?',(feed_index,))
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
				self._db_execute(self._c, """SELECT read FROM entries WHERE rowid=? LIMIT 1""",(entry_id,))
				try:
					readinfo = self._c.fetchone()[0]
				except:
					logging.info("error in search results, reindexing")
					readinfo = 0
					self.reindex()
				entries.append([entry_id, title, fakedate, readinfo, feed_id])
			self._filtered_entries[feed_index] = entries
			return entries
		else:
			logging.error("programming error: tried to get filter information from non-filter feed")
			assert False
		
	def get_entrylist(self, feed_index):
		if self.is_feed_filter(feed_index):
			return self.get_filtered_entries(feed_index)
		
		self._db_execute(self._c, """SELECT rowid,title,fakedate,read,feed_id FROM entries WHERE feed_id=? ORDER BY fakedate DESC""",(feed_index,))
		result = self._c.fetchall()
		
		if result=="":
			raise NoFeed, feed_index
		return result
		
	def get_first_entry_title(self, feed_id, strip_newlines=False):
		self._db_execute(self._c, u'SELECT feed_pointer,description FROM feeds WHERE rowid=?',(feed_id,))
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
			entry_id,title, fakedate, feed_id = s_entries[0]
			return title
	
		self._db_execute(self._c, """SELECT title FROM entries WHERE feed_id=? ORDER BY fakedate DESC LIMIT 1""",(feed_id,))
		result = self._c.fetchone()

		if result=="":
			raise NoFeed, feed_id
			
		if strip_newlines:
			return result[0].replace("\n"," ")
		return result[0]
		
	def get_entry_count(self, feed_id):
		self._db_execute(self._c, u'SELECT count(*) FROM entries WHERE feed_id=?', (feed_id,))
		return self._c.fetchone()[0]

	def get_feedlist(self):
		self._db_execute(self._c, """SELECT rowid,title,url FROM feeds ORDER BY UPPER(title)""")
		result = self._c.fetchall()
		dataList = []
		if result: 
			dataList = [list(row) for row in result]
		else:
			result=[]
		return dataList
		
	def get_feed_id_by_url(self, url):
		self._db_execute(self._c, """SELECT rowid FROM feeds WHERE url=?""",(url,))
		try:
			result = self._c.fetchone()[0]
		except TypeError:
			return -1	
		
		return result
		
	def get_feed_title(self, feed_index):
		self._db_execute(self._c, """SELECT title FROM feeds WHERE rowid=?""",(feed_index,))
		try:
			result = self._c.fetchone()[0]
		except TypeError:
			raise NoFeed, feed_index	
		
		#don't return a tuple
		return result #self.decode_text(result)
		
	def get_feed_image(self, feed_id):
		self._db_execute(self._c, u'SELECT image FROM feeds WHERE rowid=?', (feed_id,))
		try: return self._c.fetchone()[0]
		except: return None
		
	def get_feed_info(self, feed_id):
		self._db_execute(self._c, """SELECT title, description, url, link, feed_pointer, lastpoll, pollfreq FROM feeds WHERE rowid=?""",(feed_id,))
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
			self._db_execute(self._c, u'UPDATE feeds SET title=? WHERE rowid=?',(name,feed_id))
			self._db.commit()
		else:
			self._db_execute(self._c, """SELECT url FROM feeds WHERE rowid=?""",(feed_id,))
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
			
			self._db_execute(self._c, u'UPDATE feeds SET title=? WHERE rowid=?',(channel['title'],feed_id))
			self._db.commit()
		self._reindex_feed_list.append(feed_id)
		self.reindex()
		
	def set_feed_url(self, feed_id, url):
		try:
			self._db_execute(self._c, u'UPDATE feeds SET url=? WHERE rowid=?',(url,feed_id))
			self._db.commit()
		except sqlite.IntegrityError:
			raise FeedAlreadyExists,feed_id			
		
	def set_feed_link(self, feed_id, link):
		self._db_execute(self._c, u'UPDATE feeds SET link=? WHERE rowid=?',(link,feed_id))
		self._db.commit()
		
	def set_media(self, media_id, status=None, filename=None, size=None):
		assert media_id is not None
		
		update_str = u'UPDATE media SET '
		update_data = ()
		
		if status is not None:
			update_str += u'download_status=?, download_date=?, '
			update_data += (status, int(time.time()))
		
		if filename is not None:
			update_str += u'file=?, '
			update_data += (filename,)
			
		if size is not None:
			update_str += u'length=?, '
			update_data += (int(size),)
			
		assert len(update_data) > 0
		
		update_str = update_str[:-2] + u'WHERE rowid=?'
		update_data += (media_id,)
		
		self._db_execute(self._c, update_str, update_data)
		self._db.commit()
				
	def set_media_download_status(self, media_id, status):
		if status == D_DOWNLOADED:
			self._db_execute(self._c, u'UPDATE media SET download_status=?, download_date=? WHERE rowid=?', (status, int(time.time()),media_id,))
			self._db.commit()
		else:
			self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE rowid=?', (status,media_id,))
			self._db.commit()
		self._db_execute(self._c, u'SELECT entry_id FROM media WHERE rowid=?',(media_id,))
		entry_id = self._c.fetchone()[0]
		if self.entry_flag_cache.has_key(entry_id):
			del self.entry_flag_cache[entry_id]
		
	def set_media_filename(self, media_id, filename):
		self._db_execute(self._c, u'UPDATE media SET file=? WHERE rowid=?', (filename,media_id))
		self._db.commit()
		
	def set_media_viewed(self, media_id, viewed, entry_id=None):
		self._db_execute(self._c, u'UPDATE media SET viewed=? WHERE rowid=?',(int(viewed),media_id))
		self._db.commit()
		if entry_id is None:
			self._db_execute(self._c, u'SELECT entry_id FROM media WHERE rowid=?',(media_id,))
			entry_id = self._c.fetchone()[0]
		
		if self.entry_flag_cache.has_key(entry_id): del self.entry_flag_cache[entry_id]
	
		if viewed==1:#check to see if this makes the whole entry viewed
			if self.get_entry_keep(entry_id):
				return
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
		self._db_execute(self._c, u'SELECT length FROM media WHERE rowid=?',(media_id,))
		return self._c.fetchone()[0]
	
	def set_media_size(self, media_id, size):
		self._db_execute(self._c, u'UPDATE media SET length=? WHERE rowid=?',(int(size),media_id))
		self._db.commit()
	
	def set_entry_read(self, entry_id, read):
		self._db_execute(self._c, u'UPDATE entries SET read=? WHERE rowid=?',(int(read),entry_id))
		self._db_execute(self._c, u'UPDATE media SET viewed=? WHERE entry_id=?',(int(read),entry_id))
		self._db.commit()
		if self.entry_flag_cache.has_key(entry_id): del self.entry_flag_cache[entry_id]
		
	def set_entry_keep(self, entry_id, keep):
		self._db_execute(self._c, u'UPDATE entries SET keep=? WHERE rowid=?',(int(keep),entry_id))
		if keep:
			self._db_execute(self._c, u'UPDATE entries SET read=0 WHERE rowid=?',(entry_id,))
			self._db_execute(self._c, u'UPDATE media SET viewed=0 WHERE entry_id=?',(entry_id,))
		self._db.commit()
		if self.entry_flag_cache.has_key(entry_id): del self.entry_flag_cache[entry_id]
		
	def get_entry_keep(self, entry_id):
		self._db_execute(self._c, u'SELECT keep FROM entries WHERE rowid=? LIMIT 1',(entry_id,))
		retval = self._c.fetchone()[0]
		return int(retval)
		
	def set_entrylist_read(self, entrylist, read):
		if len(entrylist) == 0:
			return
		l = [str(e) for e in entrylist]
		subset = []
		while len(l) > 0:
			subset = l[:900]
			qmarks = "?,"*(len(subset)-1)+"?"
			self._db_execute(self._c, u'UPDATE entries SET read=? WHERE rowid IN ('+qmarks+')', (int(read),)+tuple(subset))
			self._db_execute(self._c, u'UPDATE media SET viewed=? WHERE entry_id IN ('+qmarks+')',(int(read),)+tuple(subset))
			self._db.commit()
			l = l[900:]
		for e in entrylist:
			if self.entry_flag_cache.has_key(e): del self.entry_flag_cache[e]
		
	def get_entry_read(self, entry_id):
		self._db_execute(self._c, u'SELECT read FROM entries WHERE rowid=? LIMIT 1',(entry_id,))
		retval = self._c.fetchone()[0]
		return int(retval)
		
	def clean_media_status(self):
		self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE download_status<1',(D_NOT_DOWNLOADED,))
		self._db.commit()
		self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE download_status=1',(D_RESUMABLE,))
		self._db.commit()
		self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE download_status=? AND file is NULL',(D_NOT_DOWNLOADED, D_DOWNLOADED))
		self._db.commit()
		
	def get_entryid_for_media(self, media_id):
		self._db_execute(self._c, u'SELECT entry_id FROM media WHERE rowid=? LIMIT 1',(media_id,))
		ret = self._c.fetchone()
		return ret[0]
		
	def get_media_for_download(self, resume_paused = True):
		if resume_paused:
			self._db_execute(self._c, u'SELECT rowid, length, entry_id, feed_id FROM media WHERE (download_status=? OR download_status==?) AND viewed=0',(D_NOT_DOWNLOADED,D_RESUMABLE))
		else:
			self._db_execute(self._c, u'SELECT rowid, length, entry_id, feed_id FROM media WHERE download_status=? AND viewed=0',(D_NOT_DOWNLOADED,))
		list=self._c.fetchall()
		self._db_execute(self._c, u'SELECT rowid, length, entry_id, feed_id FROM media WHERE download_status=?',(D_ERROR,))
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
			
		#build a list of feeds that do not include the noautodownload flag
		feeds = [l[3] for l in newlist]
		feeds = utils.uniquer(feeds)
		good_feeds = [f for f in feeds if self.get_flags_for_feed(f) & FF_NOAUTODOWNLOAD == 0]
		newlist = [l for l in newlist if l[3] in good_feeds]
		return newlist 
		
	def get_deletable_media(self):
		no_expire = self.get_feeds_for_flag(FF_NOAUTOEXPIRE)
		if len(no_expire) > 0: 
			qmarks = "?,"*(len(no_expire)-1)+"?"
			self._db_execute(self._c, u'SELECT media.rowid, media.entry_id, media.feed_id, media.file, media.download_date FROM media INNER JOIN entries ON media.entry_id = entries.rowid WHERE entries.keep=0 AND media.download_status=2 AND media.feed_id not in ('+qmarks+') ORDER BY media.viewed DESC, media.download_date', tuple(no_expire))
		else:
			self._db_execute(self._c, u'SELECT media.rowid, media.entry_id, media.feed_id, media.file, media.download_date FROM media INNER JOIN entries ON media.entry_id = entries.rowid WHERE entries.keep=0 AND media.download_status=2 ORDER BY media.viewed DESC, media.download_date')
		
		result = self._c.fetchall()
		if result:
			return [[r[0],r[1],r[2],r[3],long(r[4])] for r in result]
		return []
		
	def get_resumable_media(self):
		self._db_execute(self._c, u'SELECT rowid, file, entry_id, feed_id  FROM media WHERE download_status=?',(D_RESUMABLE,))
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
		if self.is_feed_filter(feed_id):
			if not self._filtered_entries.has_key(feed_id):
				self.get_filtered_entries(feed_id)
			changed_list = []
			list = []
			for entry in self._filtered_entries[feed_id]:
				self._db_execute(self._c, u'UPDATE entries SET read=1 WHERE rowid=? AND read=0 AND keep=0',(entry[0],))
				self._db_execute(self._c, u'SELECT rowid, download_status FROM media WHERE entry_id=?',(entry[0],))
				list = list+self._c.fetchall()
			feed_id = self._resolve_pointed_feed(feed_id)
		else:
			#feed_id = self._resolve_pointed_feed(feed_id)
			self._db_execute(self._c, u'SELECT rowid FROM entries WHERE feed_id=? AND read=0 AND keep=0',(feed_id,))
			changed_list = self._c.fetchall()
			self._db_execute(self._c, u'UPDATE entries SET read=1 WHERE feed_id=? AND read=0 AND keep=0',(feed_id,))
			self._db_execute(self._c, u'SELECT media.rowid, media.download_status FROM media INNER JOIN entries ON media.entry_id = entries.rowid WHERE entries.keep=0 AND media.feed_id = ?',(feed_id,))
			list = self._c.fetchall()
		
		if len(list) > 0:
			qmarks = "?,"*(len(list)-1)+"?"
			idlist = [l[0] for l in list]
			self._db_execute(self._c, u'UPDATE media SET viewed=1 WHERE rowid IN ('+qmarks+')', tuple(idlist))
		#for item in list:
		#	self._db_execute(self._c, u'UPDATE media SET viewed=? WHERE rowid=? AND viewed=0',(1,item[0]))
		#	if item[1] == D_ERROR:
		#		self._db_execute(self._c, u'UPDATE media SET download_status=? WHERE rowid=?', (D_NOT_DOWNLOADED,item[0]))
		self._db.commit()
		
		changed_list = [r[0] for r in changed_list]
		
		for item in changed_list:
			if self.entry_flag_cache.has_key(item): 
				del self.entry_flag_cache[item]
				
		return changed_list
		
	
	def media_exists(self, filename):
		self._db_execute(self._c, u'SELECT count(*) FROM media WHERE media.file=?',(filename,))
		count = self._c.fetchone()[0]
		if count>1:
			logging.warning("multiple entries in db for one filename")
		if count==0:
			return False
		return True
		
	def get_unplayed_media(self, set_viewed=False):
		"""media_id, entry_id, feed_id, file, entry_title, feed_title
		    0          1         2       3        4            5"""
		self._db_execute(self._c, u'SELECT media.rowid, media.entry_id, media.feed_id, media.file, entries.title FROM media INNER JOIN entries ON media.entry_id = entries.rowid WHERE media.download_status=? AND media.viewed=0',(D_DOWNLOADED,))
		list=self._c.fetchall()
		playlist=[]
		if set_viewed:
			for item in list:
				self._db_execute(self._c, u'UPDATE media SET viewed=1 WHERE rowid=?',(item[0],))
				self._db_execute(self._c, u'UPDATE entries SET read=1 WHERE rowid=?',(item[1],))	
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
	
		self._db_execute(self._c, u'SELECT pollfail FROM feeds WHERE rowid=?',(feed_id,))
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
		
		#is_filter = False
		#if utils.HAS_SEARCH:
		#	is_filter = self.is_feed_filter(feed_id) 
		
		#if is_filter or self.cache_dirty:
		flaglist = self.get_entry_flags(feed_id)
		feed_info['important_flag'] = self.get_feed_flag(feed_id, flaglist)  #not much speeding up this	
		feed_info['entry_count'] = len(flaglist)
		feed_info['unread_count'] = len([f for f in flaglist if f & F_UNVIEWED])
		#else:
		#	self._db_execute(self._c, u'SELECT flag_cache, unread_count_cache, entry_count_cache FROM feeds WHERE rowid=?',(feed_id,))
		#	cached_info = self._c.fetchone()
		#	feed_info['important_flag'] = cached_info[0]
		#	feed_info['unread_count'] = cached_info[1]
		#	sfeed_info['entry_count'] = cached_info[2]
		
		self._db_execute(self._c, u'SELECT pollfail FROM feeds WHERE rowid=?',(feed_id,))
		result = self._c.fetchone()[0]
		if result==0:
			feed_info['poll_fail'] = False
		else:
			feed_info['poll_fail'] = True
		return feed_info
	
	def get_entry_flag(self, entry_id, medialist=None, read=None, media_entries=None):
		if self.entry_flag_cache.has_key(entry_id):
			return self.entry_flag_cache[entry_id]

		importance=0
		
		if read is None:
			self._db_execute(self._c, u'SELECT read FROM entries WHERE rowid=?',(entry_id,))
			read = self._c.fetchone()[0]
		
		if medialist is None:
			if media_entries is not None:
				if entry_id not in media_entries:
					medialist = []
				else:
					medialist = self.get_entry_media(entry_id)
			else:
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
		
		if status == D_ERROR:
			importance = importance + F_ERROR
		if status == D_DOWNLOADING:
			importance = importance + F_DOWNLOADING		
			
		if medialist:	
			importance = importance + F_MEDIA
			if status == D_DOWNLOADED:
				importance = importance + F_DOWNLOADED
			elif status == D_RESUMABLE:
				importance = importance + F_PAUSED
			for medium in medialist:
				if medium['viewed'] == 0:
					importance = importance + F_UNVIEWED
					break
		else:
			if int(read) == 0:
				importance = importance + F_UNVIEWED
		
		if USING_FLAG_CACHE:
			self.entry_flag_cache[entry_id] = importance
		return importance
		
	def get_entry_for_hash(self, e_hash):
		self._db_execute(self._c, u'SELECT feed_id, rowid FROM entries WHERE hash=?', (e_hash,))
		retval = self._c.fetchone()
		if retval is None:
			return None, None
		return retval
		
	def get_entries_for_hashes(self, hashlist, read=None):
		if len(hashlist) == 0:
			return []
			
		retval = []
		subset = []
		while len(hashlist) > 0:
			subset = hashlist[:900]
			qmarks = "?,"*(len(subset)-1)+"?"
			condition = ''
			if read is not None:
				if read:
					condition = ' AND read=1'
				else:
					condition = ' AND read=0'
			self._db_execute(self._c, u'SELECT feed_id, rowid, read FROM entries WHERE hash IN ('+qmarks+')'+condition, tuple(subset))
			r = self._c.fetchall()
			if r is not None:
				retval += r
			hashlist = hashlist[900:]
		return retval
		
	def get_hashes_for_entries(self, entrylist):
		if len(entrylist) == 0:
			return []
			
		retval = []
		subset = []
		while len(entrylist) > 0:
			subset = entrylist[:900]
			qmarks = "?,"*(len(subset)-1)+"?"
			self._db_execute(self._c, u'SELECT hash FROM entries WHERE rowid IN ('+qmarks+')', tuple(subset))
			r = self._c.fetchall()
			if r is not None:
				retval += r
			entrylist = entrylist[900:]
		return [r[0] for r in retval]
		
	def get_unread_hashes(self):
		self._db_execute(self._c, u'SELECT hash FROM entries WHERE read=0')
		retval = self._c.fetchall()
		if retval is None:
			return []
		return [r[0] for r in retval]
	
	def get_unread_entries(self, feed_id):
		if self.is_feed_filter(feed_id):
			if not self._filtered_entries.has_key(feed_id):
				self.get_filtered_entries(feed_id)
				
			return [r[0] for r in self.get_entrylist(feed_id) if r[3] == 0]
			
		self._db_execute(self._c, u'SELECT rowid FROM entries WHERE feed_id=? AND read=0', (feed_id,))
		retval = self._c.fetchall()
		if retval is None:
			return []
		return [r[0] for r in retval]
		
	def get_unread_count(self, feed_id):
		if self.is_feed_filter(feed_id):
			if not self._filtered_entries.has_key(feed_id):
				self.get_filtered_entries(feed_id)
			entries = self._filtered_entries[feed_id]
			list = []
			for entry in entries:
				self._db_execute(self._c, u'SELECT read FROM entries WHERE rowid=?',(entry[0],))
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
		if self.is_feed_filter(feed_id):
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
		if self.is_feed_filter(feed_id):
			if not self._filtered_entries.has_key(feed_id):
				self.get_filtered_entries(feed_id)
			entrylist = [e[0] for e in self._filtered_entries[feed_id]]
			for entry in entrylist:
				flaglist.append(self.get_entry_flag(entry))
		else:
			self._db_execute(self._c, u'SELECT rowid, read FROM entries WHERE feed_id=?',(feed_id,))
			entrylist = self._c.fetchall()
			if self.get_feed_media_count(feed_id) == 0:
				medialist = []
				media_entries = []
			else:
				self._db_execute(self._c, u"""SELECT entry_id FROM media WHERE feed_id=?""", (feed_id,))
				media_entries = self._c.fetchall()
				if media_entries is None:
					media_entries = []
				else:
					media_entries = [r[0] for r in media_entries]
			for entry,read in entrylist:
				flaglist.append(self.get_entry_flag(entry, read=read, medialist=medialist, media_entries=media_entries))
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
		self._db_execute(self._c, u'SELECT DISTINCT feeds.rowid FROM feeds INNER JOIN tags ON tags.feed_id=feeds.rowid WHERE tag=?',(tag,))
		result = self._c.fetchall()
		if result is None:
			return []
		return [r[0] for r in result]
		
	def get_feeds_for_flag(self, tag):
		self._db_execute(self._c, u'SELECT DISTINCT feeds.rowid FROM feeds WHERE flags & ? == ?',(tag,tag))
		result = self._c.fetchall()
		if result is None:
			return []
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
		
	def get_flags_for_feed(self, feed_id):
		self._db_execute(self._c, u'SELECT flags FROM feeds WHERE rowid=?',(feed_id,))
		result = self._c.fetchone()
		if result:
			return result[0]
		return 0
		
	def set_flags_for_feed(self, feed_id, flags):
		self._db_execute(self._c, u'UPDATE feeds SET flags=? WHERE rowid=?',(flags, feed_id))
		self._db.commit()
		
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
		self._db_execute(self._c, u'SELECT favorite FROM tags WHERE tag=? LIMIT 1',(tag,))
		favorite = self._c.fetchone()
		try: favorite = favorite[0]
		except: favorite = 0
		if current_tags:
			if tag not in current_tags and len(tag)>0:
				self._db_execute(self._c, u'INSERT INTO tags (tag, feed_id, type, favorite) VALUES (?,?,?,?)',(tag,feed_id, T_TAG, favorite))
				self._db.commit()
		else:
			self._db_execute(self._c, u'INSERT INTO tags (tag, feed_id, type, favorite) VALUES (?,?,?,?)',(tag,feed_id, T_TAG, favorite))
			self._db.commit()
			
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
			logging.error("error updating tag")
			
	def set_tag_favorite(self, tag, favorite=False):
		try:
			self._db_execute(self._c, u'UPDATE tags SET favorite=? WHERE tag=?',(favorite,tag))
			self._db.commit()
		except:
			logging.error("error updating tag favorite")

	def rename_tag(self, old_tag, new_tag):
		self._db_execute(self._c, u'UPDATE tags SET tag=? WHERE tag=?',(new_tag,old_tag))
		self._db.commit()

	def remove_tag_from_feed(self, feed_id, tag):
		self._db_execute(self._c, u'DELETE FROM tags WHERE tag=? AND feed_id=?',(tag,feed_id))
		self._db.commit()
		
	def remove_tag(self, tag):
		self._db_execute(self._c, u'DELETE FROM tags WHERE tag=?',(tag,))
		self._db.commit()
		
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
		import OPML
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
			if feed[1] is None: 
				item['description'] = ""
			else:
				item['description'] = self._ascii(feed[1])
			item['xmlUrl']=feed[2]
			o.outlines.append(item)
		o.output(stream)
		stream.close()
		
	def import_subscriptions(self, stream, opml = True):
		"""A generator which first yields the number of feeds, and then the feedids as they
		are inserted, and finally -1 on completion"""
		if not utils.HAS_PYXML and opml == True:
			logging.warning("Trying to import an OPML, but we don't have pyxml.  Aborting import")
			yield (-1,0)
			yield (1,0)
			yield (-1,0)
			return
		if opml:
			import OPML
			try:
				p = OPML.parse(stream)
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				error_msg = ""
				for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
					error_msg += s
				logging.warning(error_msg)
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
					logging.warning(error_msg)
					yield (-1,0)
			stream.close()
			#return added_feeds
			yield (-1,0)
		else: #just a list in a file
			url_list = []
			count = 0
			for line in stream.readlines():
				line = line.strip()
				if len(line) == 0: continue
				space_at = line.find(' ')
				if space_at >= 0:
					url = line[:space_at]
					title = line[space_at+1:]
				else:
					url = line
					title = None
				count+=1
				url_list.append((url, title))
			stream.close()
			yield (1,len(url_list))
			for url, title in url_list:
				try:
					feed_id=self.insertURL(url, title)
					yield (1,feed_id)
				except FeedAlreadyExists, f:
					yield (0,f.feed)
				except:
					exc_type, exc_value, exc_traceback = sys.exc_info()
					error_msg = ""
					for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
						error_msg += s
					logging.warning(error_msg)
					yield (-1,0)
			yield (-1,0)
				
	def search(self, query, filter_feed=None, blacklist=None, since=0):
		if not utils.HAS_SEARCH:
			return ([],[])
		if blacklist is None:
			blacklist = self._blacklist
		if filter_feed: #no blacklist on filter feeds (doesn't make sense)
			result = [l for l in self.searcher.Search(query, since=since)[1] if l[3] == filter_feed]
			if len(result) > 0:
				return ([filter_feed], result)
			return ([],[])
		return self.searcher.Search(query,blacklist, since=since)
		
	def doindex(self, callback=None):
		if utils.HAS_SEARCH:
			self.searcher.Do_Index_Threaded(callback)
		
	def reindex(self, feed_list=[], entry_list=[], threaded=True):
		"""reindex self._reindex_feed_list and self._reindex_entry_list as well as anything specified"""
		if not utils.HAS_SEARCH:
			return
		self._reindex_feed_list += feed_list
		self._reindex_entry_list += entry_list
		try:
			if threaded:
				self.searcher.Re_Index_Threaded(self._reindex_feed_list, self._reindex_entry_list)
			else:
				self.searcher.Re_Index(self._reindex_feed_list, self._reindex_entry_list)
		except Exception, e:
			logging.warning("reindex failure.  wait til next time I guess: %s" % str(e))
		self._reindex_feed_list = []
		self._reindex_entry_list = []
		
	def cache_images(self):
		"""goes through _image_cache_list and caches everything"""

		if self._image_cache is not None:
			while len(self._image_cache_list) > 0:
				entry_id = self._image_cache_list.pop(0)
				body = self.get_entry(entry_id)['description']
				self._image_cache.cache_html(str(entry_id), body)
				
			while len(self._image_uncache_list) > 0:
				entry_id = self._image_uncache_list.pop(0)
				self._image_cache.remove_cache(entry_id)
		
	def _resolve_pointed_feed(self, feed_id):
		if not utils.HAS_SEARCH:
			return feed_id
		self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE rowid=?',(feed_id,))
		result = self._c.fetchone()
		if result is None:
			return feed_id
		if result[0] >= 0:
			return result
		return feed_id
		
	def is_feed_filter(self, feed_id):
		if not utils.HAS_SEARCH:
			return False
		self._db_execute(self._c, u'SELECT feed_pointer FROM feeds WHERE rowid=?',(feed_id,))
		result = self._c.fetchone()
		if result is None:
			return False
		if result[0] >= 0:
			return True
		return False
		
	def get_pointer_feeds(self, feed_id):
		if not utils.HAS_SEARCH:
			return []
		self._db_execute(self._c, u'SELECT rowid FROM feeds WHERE feed_pointer=?',(feed_id,))
		results = self._c.fetchall()
		if results is None:
			return []
		return [f[0] for f in results]
		
	def get_associated_feeds(self, feed_id):
		if not utils.HAS_SEARCH:
			return [feed_id]
		feed_list = [feed_id]
		pointer = self._resolve_pointed_feed(feed_id)
		if pointer != feed_id:
			feed_list.append(feed_id)
		
		feed_list += self.get_pointer_feeds(feed_id)
		print feed_list
		return feed_list
		
	def set_cache_images(self, cache):
		if self._image_cache is not None:
			if not cache:
				self._image_cache.finish()
				self._image_cache = None
		else:
			if cache:
				store_location = self.get_setting(STRING, '/apps/penguintv/media_storage_location', os.path.join(utils.get_home(), "media"))
				if store_location != "":
					self._image_cache = OfflineImageCache.OfflineImageCache(os.path.join(store_location, "images"))
				else:
					logging.error("could not start image cache, no storage location")
		
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
		self._db_execute(self._c, """SELECT rowid,title,url FROM feeds ORDER BY rowid""")
		result = self._c.fetchall()
		return result
					
	def DEBUG_reset_freqs(self):
		self._db_execute(self._c, 'UPDATE feeds SET pollfreq=1800')
		self._db.commit()	
	
	def DEBUG_get_freqs(self):
		self._db_execute(self._c, 'SELECT title, pollfreq, lastpoll, rowid  FROM feeds ORDER BY title')
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
		self._db_execute(self._c, 'SELECT title, pollfreq, lastpoll, rowid FROM feeds ORDER BY lastpoll')
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
		self._db_execute(self._c, 'SELECT title, pollfreq, lastpoll, rowid FROM feeds ORDER BY pollfreq')
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
		self._db_execute(self._c, u'SELECT media.download_status, media.viewed, media.entry_id, media.rowid FROM media,entries WHERE media.entry_id=entries.rowid AND media.download_status!=? AND entries.feed_id=?',(D_NOT_DOWNLOADED,feed_id))
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
