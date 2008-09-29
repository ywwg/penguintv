#!/bin/sh

#eventually this will be different

EMBEDDED_ICON="./share/pixmaps/26x26/penguintvicon.png"
GPE_MAJOR_VERSION="2"
GPE_MINOR_VERSION="19"
GPE_MICRO_VERSION="1"

if [ "$1"x == "x" ] ; then
	echo "Need a GPG key to sign with (with 0x) (try gpg --list-keys, use the 8 digit hex num)"
	exit 1
fi

GPG_KEY="$1"

echo "Building gtkmozembed first"
if [ ! -d ./deb-build/gtkmozembed ] ; then
	mkdir -p deb-build/gtkmozembed
fi

BUILD_MOZEMBED=1
echo "testing gtkmozembed..."
python2.5 -c "from penguintv.ptvmozembed import gtkmozembed"
if [ $? -ne 0 ] ; then
	echo "there was an error using the gtkmozembed module"
else
	BUILD_MOZEMBED=0
fi

if [ $BUILD_MOZEMBED == "1" ] ; then
	cd gtkmozembed
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
	if [ $? -ne 0 ] ; then
		echo "error autoconfing python gnome extras"
		exit 1
	fi

	PYTHON=python2.5 ./configure --prefix=`pwd`/../../deb-build/gtkmozembed --with-gtkmozembed=gtkembedmoz --disable-eggtray
	if [ $? -ne 0 ] ; then
		echo "error configuring python gnome extras"
		exit 1
	fi

	PYTHON=python2.5 make
	if [ $? -ne 0 ] ; then
		echo "error building python gnome extras"
		exit 1
	fi

	PYTHON=python2.5 make install
	if [ $? -ne 0 ] ; then
		echo "error installing python gnome extras locally"
		exit 1
	fi

	cd ../..
	cp deb-build/gtkmozembed/lib/python2.5/site-packages/gtk-2.0/gtkmozembed.* penguintv/ptvmozembed/

	echo "testing gtkmozembed again..."
	python2.5 -c "from penguintv.ptvmozembed import gtkmozembed"
	if [ $? -ne 0 ] ; then
		echo "there was an error using the gtkmozembed module"
		exit 1
	fi
fi

echo "gtkmozembed works"

./packaging/setup-py2deb.py
if [ $? -ne 0 ] ; then
	echo "There was an error with the py2deb process, stopping"
	exit 1
fi

cd deb-build
for d in `find ./ -maxdepth 1 -type d | sort` ; do
	builddir=$d
done
cd $builddir

# Set up icon which will appear in application manager
iconfile=`tempfile`
if [ ! -f $EMBEDDED_ICON ] ; then
	echo "can't find icon"
	exit 1 
fi

#need to apt-get install sharutils for this stepp
uuencode -m $EMBEDDED_ICON /dev/stdout > $iconfile
length=`cat $iconfile | wc -l`

echo -e \\n"XB-Maemo-Icon-26:" >> debian/control
#cut the first and last lines from the file, then add a leading space
cat $iconfile | sed -n '1d; $d; p' | sed 's/^/ /' >> debian/control

#build the final package
dpkg-buildpackage -rfakeroot -sa
cd ..
debsign -k$GPG_KEY *.changes

if [ "$?" == "0" ] ; then
	echo ""
	echo "build complete, ready to upload to extras assistant.  Files are in deb-build/"
fi
