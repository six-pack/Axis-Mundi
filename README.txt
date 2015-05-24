Installation
============

1) If you do not have PIP installed then do that first from a terminal
    $ sudo apt-get install python-pip
2) Download client files from https://github.com/six-pack/client/archive/master.zip
3) Extract to your chosen location
4) Open a terminal and change directory to the location you extracted the client to
4) If you have not already installed the pre-requisite python dependencies (you only have to do this once) then
do so now using the commands:

    $ sudo pip install -r requirements.txt

Running for First Time
======================

Make  sure you have generated a PGP key in your gpg keyring before running the client (you can use an existing one).

1) Execute client.py
2) Use a web browser to access the client using address http://127.0.0.1:5000/
3) The first time the client is run you must select a PGP key to use as your identity,
[This initial set-up creates an encrypted database file (by default in the same directory as the
application) and a PGP encrypted file called secret which will go into ~/.dnmg/secret]
4) Login by selecting your PGP key in the drop-down box and supplying your PGP passphrase (you may want to use offline
mode for the first login if your SOCKS proxy is not tunning on 127.0.0.1:9050)

====================================

DO NOT LOSE THE 'secret' file OR YOUR PGP KEY. ANYTHING IN YOUR LOCAL DATABASE WILL BE LOST FOREVER.


Six Pack 2015


lose keyserver.(probably)
get alt keyring working properly

INCOMING MESSAGES
when we get an onmessage for a directed message (pm or txn) -
  - decompress if compressed
  - decrypt if encrypted
  - if signed - use gpg.verify to see if we get a valid fingerprint (we need the key already)
  - if verify OK (we must hvae the key) then append to message dict and show as ready_to_process
    else if we get no fingerprint but do get a keyid then append to key dict the keyid, append to the message dict and show key_needed
    - send SUB to target key then update the message (and/or key) dict to show key requested
  - exit onmessage and return to main loop

when onmessage comes in for a pgp key then
  - update key dict with (state = retreived) for the keyid in question
  - exit onmessage and return to mainloop

mainloop
 - enumerate message dict, for each message in dict
   - is the message ready_to_process - if so then process it
   - is the message key_requested if so we got to keep wating
   - is the

OUTGOING MESSAGES
Wehen we get a send message
 - if we need to encrypt, do we have the recipients key? (check keyring and/or check pgpcache)
    - if we do then preparemessage
    - if we dont have the key then append to the message dict to show key_needed and append to the key dict the key_id
         - send SUB to target key then update the message (and/or key) dict to show key requested
 - else this is an unencrypted broadcast message


