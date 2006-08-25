import PyLucene
import os
import utils
from pysqlite2 import dbapi2 as sqlite
from threading import Lock

"""
This class does the searching for PenguinTV.  It has full access to its own database object.
"""

ENTRY_LIMIT=100

class Lucene:
	def __init__(self):
		try:
			self.home=os.getenv('HOME')
			os.stat(self.home+"/.penguintv")
		except:
			try:
				os.mkdir(self.home+"/.penguintv")
			except:
				raise DBError, "error creating directories: "+self.home+"/.penguintv"
		self.storeDir = self.home+"/.penguintv/search_store"
		self.needs_index = False
		if not os.path.exists(self.storeDir):
			os.mkdir(self.storeDir)
			self.needs_index = True
			
		self.index_lock = Lock()
		#self.db = self._get_db()
		#self.c = self.db.cursor()
			
#	def finish(self):
#		self.c.close()
#		self.db.close()
		
	def _get_db(self):
		try:	
			if os.path.isfile(self.home+"/.penguintv/penguintv3.db") == False:
				raise DBError,"database file missing"
			db=sqlite.connect(self.home+"/.penguintv/penguintv3.db", timeout=10	)
			db.isolation_level="DEFERRED"
			return db
		except:
			raise DBError, "Error connecting to database in Lucene module"
		
	def Do_Index_Threaded(self):
		PyLucene.PythonThread(target=self.Do_Index).start()
		
	def Do_Index(self,get_new_db=False):
		"""loop through all feeds and entries and feed them to the beast"""
		self.index_lock.acquire()
		db = self._get_db()
		c = db.cursor()
		
		analyzer = PyLucene.StandardAnalyzer()
		store = PyLucene.FSDirectory.getDirectory(self.storeDir, True)
		writer = PyLucene.IndexWriter(store, analyzer, True)
				
		c.execute(u"""SELECT id, title, description FROM feeds""")
		feeds = c.fetchall()
		c.execute(u"""SELECT id, feed_id, title, description,fakedate FROM entries""")
		entries = c.fetchall()
		c.close()
		db.close()
		
		print "indexing feeds"
		for feed_id, title, description in feeds:
			try:
				doc = PyLucene.Document()
				doc.add(PyLucene.Field("id", "feed "+str(feed_id), 
											   PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.UN_TOKENIZED))
				doc.add(PyLucene.Field("title", title,
	                                           PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.TOKENIZED))   
				doc.add(PyLucene.Field("description", description,
	                                           PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.TOKENIZED))       
				writer.addDocument(doc)  
			except Exception, e:
				print "Failed in indexDocs:", e                      
		
		print  "indexing entries"
		
		for entry_id, feed_id, title, description, fakedate in entries:
			try:
				doc = PyLucene.Document()
				doc.add(PyLucene.Field("id", "entry "+str(entry_id), 
											   PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.UN_TOKENIZED))
				doc.add(PyLucene.Field("feed_id", str(feed_id), 
											   PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.UN_TOKENIZED))	                                           
				doc.add(PyLucene.Field("fakedate", str(fakedate), 
											   PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.UN_TOKENIZED))	                                           
				doc.add(PyLucene.Field("title",title,
	                                           PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.TOKENIZED))   
				doc.add(PyLucene.Field("description", description,
	                                           PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.TOKENIZED))       
				writer.addDocument(doc)  
			except Exception, e:
				print "Failed in indexDocs:", e    
				
		print "optimizing"
		writer.optimize()
		writer.close()
		print "done indexing"
		self.index_lock.release()
		
	def Re_Index_Threaded(self,feedlist=[], entrylist=[]):
		PyLucene.PythonThread(target=self.Re_Index, args=(feedlist,entrylist)).start()
		
	def Re_Index(self, feedlist=[], entrylist=[]):
		if len(feedlist)==0 and len(entrylist)==0:
			#print "nothing to reindex"
			return
		self.index_lock.acquire()
		db = self._get_db()
		c = db.cursor()
					
		#print "reindexing "+str(len(feedlist))+" feeds and "+str(len(entrylist))+" entries"
		analyzer = PyLucene.StandardAnalyzer()
		indexModifier = PyLucene.IndexModifier(self.storeDir, analyzer, False)
		
		feed_addition = []
		entry_addition = []
	
		feeds = c.execute(u"""SELECT id FROM feeds""")
		
		for feed_id in feedlist:
			try:
				#print "checking feed "+str(feed_id)
				c.execute(u"""SELECT title, description FROM feeds WHERE id=?""",(feed_id,))
				title, description = c.fetchone()
				feed_addition.append((feed_id, title, description))
			except TypeError:
				pass #it won't be readded.  Assumption is we have deleted this feed

		for entry_id in entrylist:
			try:
				#print "checking entry "+str(entry_id)
				c.execute(u"""SELECT feed_id, title, description, fakedate FROM entries WHERE id=?""",(entry_id,))
				feed_id, title, description, fakedate = c.fetchone()
				entry_addition.append((entry_id, feed_id, title, description, fakedate))
			except TypeError:
				pass
				
		c.close()
		db.close()
				
		#first delete anything deleted or changed
		for feed_id in feedlist:
			try:
				#print "deleting feed "+str(feed_id)
				indexModifier.deleteDocuments(PyLucene.Term("id","feed "+str(feed_id)))
			except Exception, e:
				print "Failed deleting feed:", e
				
		for entry_id in entrylist:
			try:
				#print "deleting entry "+str(entry_id)
				indexModifier.deleteDocuments(PyLucene.Term("id","entry "+str(entry_id)))
			except Exception, e:
				print "Failed deleting entry:", e
			
		#now add back the changes
		for feed_id, title, description in feed_addition:
			try:
				#print "adding feed "+str(feed_id)
				doc = PyLucene.Document()
				doc.add(PyLucene.Field("id", "feed "+str(feed_id), 
											   PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.UN_TOKENIZED))
				doc.add(PyLucene.Field("title",title,
	                                           PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.TOKENIZED))   
				doc.add(PyLucene.Field("description", description,
	                                           PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.TOKENIZED))
				indexModifier.addDocument(doc)
			except Exception, e:
				print "Failed adding feed:", e
		
		for entry_id, feed_id, title, description, fakedate in entry_addition:
			try:
				#print "adding entry "+str(entry_id)
				doc = PyLucene.Document()
				doc.add(PyLucene.Field("id", "entry "+str(entry_id), 
											   PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.UN_TOKENIZED))
				doc.add(PyLucene.Field("feed_id", str(feed_id), 
											   PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.UN_TOKENIZED))	
				doc.add(PyLucene.Field("fakedate", str(fakedate), 
											   PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.UN_TOKENIZED))	
				doc.add(PyLucene.Field("title",title,
	                                           PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.TOKENIZED))   
				doc.add(PyLucene.Field("description", description,
	                                           PyLucene.Field.Store.YES,
	                                           PyLucene.Field.Index.TOKENIZED))
				indexModifier.addDocument(doc)
			except Exception, e:
				print "Failed adding entry:", e
				
		indexModifier.flush()
		indexModifier.close()
		#print "done reindexing"
		self.index_lock.release()
						
	def Search(self, command, filter_feed=None):
		"""returns two lists, one of search results in feeds, and one for results in entries.  It
		is sorted so that title results are first, description results are second"""
		#print "performing search"
		analyzer = PyLucene.StandardAnalyzer()
		directory = PyLucene.FSDirectory.getDirectory(self.storeDir, False)
		searcher = PyLucene.IndexSearcher(directory)
		
		feed_results=[]
		entry_results=[]
		
		#MultiFiendQuery has a bug in 2.0.0... for now don't use
		#queryparser = PyLucene.MultiFieldQueryParser(['title','description'], self.analyzer)
		#query = PyLucene.MultiFiendQueryParser.parse(command, ['title','description'], self.analyzer)

		#query TITLES
		queryparser = PyLucene.QueryParser("title", analyzer)
		query = PyLucene.QueryParser.parse(queryparser, command)
		hits = searcher.search(query)
		#print "%s total matching document titles." % hits.length()
		for i, doc in hits:
			#print 'id:', doc.get("id"), 'title:', doc.get("title")#, 'desc:', doc.get("description")
			id    = doc.get("id")
			title = doc.get("title")
			desc  = doc.get("description")
			if id[:4] == "feed":
				feed_results.append(int(id[5:]))
			else: # == "entry"
				feed_id = int(doc.get("feed_id"))
				fakedate = float(doc.get("fakedate"))
				if filter_feed is not None:
					if feed_id == filter_feed:
						entry_results.append((int(id[6:]),title, fakedate, feed_id))
				else:
					if len(entry_results) < ENTRY_LIMIT:
						entry_results.append((int(id[6:]),title, fakedate, feed_id))
				
		for entry in entry_results: #also add feed results so that they show up in the feed list too
			feed_results.append(entry[1])
			
		#query DESCRIPTIONS		
		queryparser = PyLucene.QueryParser("description", analyzer)
		query = PyLucene.QueryParser.parse(queryparser, command)
		hits = searcher.search(query)
		#print "%s total matching document descriptions." % hits.length()
		for i, doc in hits:
			#print 'id:', doc.get("id"), 'title:', doc.get("title")#, 'desc:', doc.get("description")
			id    = doc.get("id")
			title = doc.get("title")
			desc  = doc.get("description")
			if id[:4] == "feed":
				feed_results.append(int(id[5:]))
			else: # == "entry"
				feed_id = int(doc.get("feed_id"))
				fakedate = float(doc.get("fakedate"))
				if filter_feed is not None:
					if feed_id == filter_feed:
						entry_results.append((int(id[6:]),title, fakedate, feed_id))
				else:
					if len(entry_results) < ENTRY_LIMIT:
						entry_results.append((int(id[6:]),title, fakedate, feed_id))
		
		for entry in entry_results:
			feed_results.append(entry[3]) #this redoes the stuff at the top, but I 
											#don't care because we are going to pare down the list
		feed_results = utils.uniquer(feed_results)
		entry_results = utils.uniquer(entry_results)	
		searcher.close()           				
		#print "search done"					
		return (feed_results, entry_results)
		
class DBError(Exception):
	def __init__(self,error):
		self.error = error
	def __str__(self):
		return self.error		
