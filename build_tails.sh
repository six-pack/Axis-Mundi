#!/bin/sh
echo "############################################################################################################"
echo "Axis Mundi Executable Builder (Tails)"
echo "############################################################################################################"
echo "Preparing Operating System requirements"
sudo apt-get update
sudo apt-get -y install build-essential python-wxtools python-pip python-dev libjpeg-dev zlib1g-dev libssl-dev python-appindicator
sudo pip uninstall -y PIL
echo "############################################################################################################"
echo "Getting PyInstaller 2.1"
sudo torsocks pip install PyInstaller==2.1
echo "############################################################################################################"
echo "Getting Axis Mundi source code"
git clone https://github.com/six-pack/axis-mundi
cd axis-mundi
echo "############################################################################################################"
echo "Installing Axis Mundi Python requirements"
sudo torsocks pip install -r requirements.txt
echo "############################################################################################################"
echo "Setting Python library permissions"
sudo chmod -R o+r,o+X /usr/local/lib/python2.7/dist-packages
echo "############################################################################################################"
echo "Building Axis Mundi executable file"
pyinstaller axismundi_pyinst.spec
echo "############################################################################################################"
echo "Copying Axis Mundi executable to your Persistence folder"
cp dist/axismundi ~/Persistent
echo "############################################################################################################"
echo "Axis Mundi has been built and copied into your Persistence Folder"
