#!/usr/bin/python

import os
import sys
import zipfile

from sugar.activity.bundle import Bundle

def manifest_generator():
	f = open('./MANIFEST-OLPC')
	for line in f.readlines():
		yield line[:-1]
		
def get_source_path():
	return os.path.dirname(os.path.abspath(__file__))
	
def get_bundle_dir():
	#bundle_name = os.path.basename(get_source_path())
	bundle_name = "ptv"
	return bundle_name + '.activity' 
		
orig_path = os.getcwd()
os.chdir(get_source_path())

bundle = Bundle(get_source_path())
zipname = '%s-%d.zip' % (bundle.get_name(), bundle.get_activity_version())
bundle_zip = zipfile.ZipFile(zipname, 'w')

for filename in manifest_generator():
	arcname = os.path.join(get_bundle_dir(), filename)
	try:
		bundle_zip.write(filename, arcname)
	except IOError, e:
		print filename,"is a directory, skipping"
		if e.errno != 21:
			raise e
	
bundle_zip.close()
os.chdir(orig_path)
