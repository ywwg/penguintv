#!/usr/bin/python

import os
import sys
import tarfile

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
tarball_name = '%s-%d.tar.gz' % (bundle.get_name(), bundle.get_activity_version())
bundle_tar_gz = tarfile.open(tarball_name, "w:gz")

for filename in manifest_generator():
	arcname = os.path.join(get_bundle_dir(), filename)
	info = bundle_tar_gz.gettarinfo(filename, arcname)
	bundle_tar_gz.addfile(info, open(filename, 'rb'))
	
bundle_tar_gz.close()
	
os.chdir(orig_path)
