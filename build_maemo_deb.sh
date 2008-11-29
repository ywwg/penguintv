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

echo "Preparing gtkmozembed first"
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
make distclean
cd ../..

cp PenguinTV.in bin/PenguinTV

#running py2deb gets most of it out of the way, but more work needs to be done
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


#copy gnome-python-extras source which we extracted and patched above
#also include the patch so people can see what I've done
echo "copying gnome-python-extras source"
mkdir gtkmozembed
cp -a ../../gtkmozembed/gnome-python-extras-"$GPE_MAJOR_VERSION"."$GPE_MINOR_VERSION"."$GPE_MICRO_VERSION"/* gtkmozembed/
cp ../../gtkmozembed/gnome-python-extras.diff gtkmozembed/
cd debian
cat ../../../packaging/rules.diff | patch -p 0
cd ..

# Set up icon which will appear in application manager
iconfile=`tempfile`
if [ ! -f $EMBEDDED_ICON ] ; then
	echo "can't find icon"
	exit 1 
fi

#need to apt-get install sharutils for this stepp
uuencode -m $EMBEDDED_ICON /dev/stdout > $iconfile
if [ $? -ne 0 ] ; then
	echo "error running uuencode.  Need sharutils?"
	exit 1
fi
length=`cat $iconfile | wc -l`

echo -e \\n"XB-Maemo-Icon-26:" >> debian/control
#cut the first and last lines from the file, then add a leading space
cat $iconfile | sed -n '1d; $d; p' | sed 's/^/ /' >> debian/control

#build the final package
dpkg-buildpackage -rfakeroot -sa
cd ..
for file in *.changes ; do
	debsign -k$GPG_KEY $file
done

if [ "$?" == "0" ] ; then
	echo ""
	echo "build complete, ready to upload to extras assistant.  Files are in deb-build/"
else
	echo "there was an error signing the package"
	exit 1
fi
