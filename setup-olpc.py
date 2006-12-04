#!/usr/bin/python

import os
import sys
import zipfile

try:
	from sugar.activity.bundle import Bundle
	HAS_SUGAR = True
except:
	HAS_SUGAR = False

BUNDLE_NAME="ptv"

def manifest_generator():
	f = open('./MANIFEST-OLPC')
	for line in f.readlines():
		yield line[:-1]
		
def get_source_path():
	return os.path.dirname(os.path.abspath(__file__))
	
def get_bundle_dir():
	return BUNDLE_NAME + '.activity' 
		
orig_path = os.getcwd()
os.chdir(get_source_path())

if HAS_SUGAR:
	bundle = Bundle(get_source_path())
	zipfile_name = '%s-%d.xo' % (bundle.get_name(), bundle.get_activity_version())
else:
	zipfile_name = 'bundle.xo'
bundle_zip = zipfile.ZipFile(zipfile_name, "w", zipfile.ZIP_DEFLATED)

for filename in manifest_generator():
	arcname = os.path.join(get_bundle_dir(), filename)
	bundle_zip.write(filename, arcname)
	
bundle_zip.close()
	
os.chdir(orig_path)
