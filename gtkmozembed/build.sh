#!/bin/sh

GPE_MAJOR_VERSION="2"
GPE_MINOR_VERSION="19"
GPE_MICRO_VERSION="1"

if [ ! -f gnome-python-extras-"$GPE_MAJOR_VERSION"."$GPE_MINOR_VERSION"."$GPE_MICRO_VERSION".tar.bz2 ] ; then
	wget ftp://ftp.gnome.org/pub/gnome/sources/gnome-python-extras/"$GPE_MAJOR_VERSION"."$GPE_MINOR_VERSION"/gnome-python-extras-"$GPE_MAJOR_VERSION"."$GPE_MINOR_VERSION"."$GPE_MICRO_VERSION".tar.bz2
	if [ $? -ne 0 ] ; then
		echo "error downloading python gnome extras:"
		echo wget ftp://ftp.gnome.org/pub/gnome/sources/gnome-python-extras/"$GPE_MAJOR_VERSION"."$GPE_MINOR_VERSION"/gnome-python-extras-"$GPE_MAJOR_VERSION"."$GPE_MINOR_VERSION"."$GPE_MICRO_VERSION".tar.bz2
		exit 1
	fi
fi

tar xfvj gnome-python-extras-"$GPE_MAJOR_VERSION"."$GPE_MINOR_VERSION"."$GPE_MICRO_VERSION".tar.bz2
if [ $? -ne 0 ] ; then
	echo "error uncompressing python gnome extras"
	exit 1
fi

cd gnome-python-extras-"$GPE_MAJOR_VERSION"."$GPE_MINOR_VERSION"."$GPE_MICRO_VERSION"
cat ../gnome-python-extras.diff | patch -p 0
if [ $? -ne 0 ] ; then
	echo "error patching python gnome extras"
	exit 1
fi

autoconf

PYTHON=/usr/bin/python2.5 ./configure    \
		--prefix=`pwd`/../tmp-gtkmozembed \
		--with-gtkmozembed=gtkembedmoz
		
if [ $? -ne 0 ] ; then
	echo "error configuring python gnome extras"
	exit 1
fi
		
PYTHON=/usr/bin/python2.5 make && PYTHON=/usr/bin/python2.5 make install

if [ $? -ne 0 ] ; then
	echo "error building python gnome extras"
	exit 1
fi

cd ..
cp tmp-gtkmozembed/lib/python2.5/site-packages/gtk-2.0/gtkmozembed.so ../penguintv/ptvmozembed

if [ $? -ne 0 ] ; then
	echo "error installing python gnome extras"
	exit 1
fi

echo "gtkmozembed built"
