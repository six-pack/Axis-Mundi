import threading
import Queue
import time
from datetime import datetime, timedelta
#import paho.mqtt.client as mqtt
#from paho.mqtt.client import MQTT_ERR_SUCCESS, mqtt_cs_connected
from mqtt_client import MQTT_ERR_SUCCESS, mqtt_cs_connected
from mqtt_client import Client as mqtt
from storage import Storage
import gnupg
from messaging import Message, Messaging, Contact
from utilities import queue_task, current_time, got_pgpkey,parse_user_name, full_name, Listing
import json
import socks
import socket
from calendar import timegm
from time import gmtime
import random
import re
from collections import defaultdict
from pprint import pprint
import string

MSG_STATE_NEEDS_KEY = 0
MSG_STATE_KEY_REQUESTED = 1
MSG_STATE_READY_TO_PROCESS = 2
MSG_STATE_DONE = 3
MSG_STATE_QUEUED = 4

KEY_LOOKUP_STATE_INITIAL = 0
KEY_LOOKUP_STATE_REQUESTED = 1
KEY_LOOKUP_STATE_FOUND = 2
KEY_LOOKUP_STATE_NOTFOUND = 3

class messaging_loop(threading.Thread):
# Authentication shall set the password to a PGP clear-signed message containing the follow data only
# broker-hostname:pgpkeyid:UTCdatetime
# The date time shall not contain seconds and will be chekced on the server to be no more than +/- 5 minutes fromcurrent server time

    def __init__ (self, pgpkeyid, pgppassphrase, dbpassphrase, database, homedir, appdir, q, q_res, workoffline=False):
        self.targetbroker = None
        self.mypgpkeyid = pgpkeyid
        self.q = q # queue for client (incoming queue_task requests)
        self.q_res = q_res  # results queue for client (outgoing)
        self.database = database
        self.homedir = homedir
        self.pgpdir = homedir + '/.gnupg'
        self.appdir = appdir
        self.test_mode = False
        self.dbsecretkey = dbpassphrase
        self.onion_brokers = []
        self.i2p_brokers = []
        self.clearnet_brokers = []
        self.gpg = gnupg.GPG(gnupghome=self.homedir + '/.gnupg',options={'--primary-keyring="' + self.appdir + '/pubkeys.gpg"'})
        self.pgp_passphrase = pgppassphrase
        self.profile_text = ''
        self.display_name = None
        self.myMessaging = Messaging(self.mypgpkeyid,self.pgp_passphrase,self.pgpdir,appdir)
        self.sub_inbox = str("user/" + self.mypgpkeyid + "/inbox")
        self.pub_profile = str("user/" + self.mypgpkeyid + "/profile")
        self.pub_key = str("user/" + self.mypgpkeyid + "/key")
        self.pub_items = str("user/" + self.mypgpkeyid + "/items")
        self.storageDB = Storage
        self.connected = False
        self.workoffline = workoffline
        self.shutdown = False
        self.message_retention = 30 # default 30 day retention of messages before auto-purge
        self.allow_unsigned = True # allow unsigned PMs by default
        self.task_state_messages=defaultdict(defaultdict)  # This will hold the state of any outstanding message tasks
        self.task_state_pgpkeys=defaultdict(defaultdict)  # This will hold the state of any outstanding key retrieval tasks
        threading.Thread.__init__ (self)

    def on_connect(self, client, userdata, flags, rc):  # TODO: Check that these parameters are right, had to add "flags" which may break "rc"
        print "Connected"
        self.connected = True
        flash_msg = queue_task(0,'flash_status','On-line')
        self.q_res.put(flash_msg)
        flash_msg = queue_task(0,'flash_message','Connected to broker ' + self.targetbroker)
        self.q_res.put(flash_msg)
        self.setup_message_queues(client)
        # TODO: Call function to process any queued outbound messages(pm & transaction) - github issue #5

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        flash_msg = queue_task(0,'flash_status','Off-line')
        self.q_res.put(flash_msg)
        if self.shutdown:
            flash_msg = queue_task(0,'flash_message','Disconnected from ' + self.targetbroker)
        else:
            flash_msg = queue_task(0,'flash_message','Broker was disconnected, attempting to reconnect to ' + self.targetbroker)
            try:
                client.reconnect()
            except:
                print "Reconnection failure"
        self.q_res.put(flash_msg)

    # TODO - make use of onpublish and onsubscribe callbacks instead of checking status of call to publish or subscribe
    def on_publish(self, client, userdata, mid):
        print "On publish for " + str(mid)

    def on_subscribe(self, client, userdata, mid, granted_qos):
        print "On subscribe for " + str(mid)

    def on_message(self, client, userdata, msg):
        if msg.topic == self.sub_inbox:
            message = self.myMessaging.GetMessage(msg.payload,allow_unsigned=self.allow_unsigned)
            if message == False:  print "Message was invalid"
            elif message.type == 'Private Message':
                # Calculate purge date for this message
                purgedate = datetime.now()+timedelta(days=self.message_retention)
                flash_msg = queue_task(0,'flash_message','Private message received from ' + message.sender)
                self.q_res.put(flash_msg)
                session = self.storageDB.DBSession()
                new_db_message = self.storageDB.PrivateMessaging(
                                                                    sender_key=message.sender,
                                                                    recipient_key=message.recipient,
                                                                    message_id=message.id,
                                                                    message_purge_date=purgedate,
                                                                    message_date=datetime.strptime(current_time(),"%Y-%m-%d %H:%M:%S"),
                                                                    subject=message.subject,
                                                                    body=message.body,
                                                                    message_sent=False,
                                                                    message_read=False,
                                                                    message_direction="In"
                                                                 )
                session.add(new_db_message)
                session.commit()
            elif message.type == 'Transaction':
                flash_msg = queue_task(0,'flash_message','Transaction message received from ' + message.sender)
                self.q_res.put(flash_msg)
#                session = self.storageDB.DBSession()
#                new_db_message = self.storageDB.PrivateMessaging(
#                                                                    sender_key=message.sender,
#                                                                    recipient_key=message.recipient,
#                                                                    message_id=message.id,
#                                                                    message_purge_date=datetime.strptime(current_time(),"%Y-%m-%d %H:%M:%S"),
#                                                                    message_date=datetime.strptime(current_time(),"%Y-%m-%d %H:%M:%S"),
#                                                                    subject=message.subject,
#                                                                    body=message.body,
#                                                                    message_sent=False,
#                                                                    message_read=False,
#                                                                    message_direction="In"
#                                                                 )
#                session.add(new_db_message)
#                session.commit()
        elif re.match('user\/[A-F0-9]{16}\/key',msg.topic):
            # Here is a key, store it and unsubscribe
            print "Key Retrieved"
            client.unsubscribe(msg.topic)
            #TODO: Check we have really been sent a PGP key block and check if it really is the same as the topic key
            keyid = msg.topic[msg.topic.index('/')+1:msg.topic.rindex('/')]
            try:
                state=self.task_state_pgpkeys[keyid]['state']
            except KeyError:
                state=None
            if state == KEY_LOOKUP_STATE_REQUESTED:
                session = self.storageDB.DBSession()
                cachedkey = self.storageDB.cachePGPKeys(key_id=keyid,
                                                        updated=datetime.strptime(current_time(),"%Y-%m-%d %H:%M:%S"),
                                                        keyblock=msg.payload )
                session.add(cachedkey)
                session.commit()
                self.task_state_pgpkeys[keyid]['state'] = KEY_LOOKUP_STATE_FOUND
                print "Retrieved key committed"
            else:
                print "Dropping unexpected pgp key received for keyid: " + keyid
#            imp_res = self.gpg.import_keys(msg.payload) # we could import it here but we use the local keyserver
        elif re.match('user\/[A-F0-9]{16}\/profile',msg.topic):
            # Here is a profile, store it and unsubscribe
            client.unsubscribe(msg.topic)
            keyid = msg.topic[msg.topic.index('/')+1:msg.topic.rindex('/')]
            #TODO: Check we have really been sent a valid profile message for the key indicated
            #print msg.payload
            profile_message = self.myMessaging.GetMessage(msg.payload,allow_unsigned=False) # Never allow unsigned profiles
            if profile_message:
                if not keyid==profile_message.sender:
                    print "Profile was signed by a different key - discarding..."
                else:
                    profile_text = profile_message.sub_messages['profile']
                    session = self.storageDB.DBSession()
                    if 'display_name' in profile_message.sub_messages and 'profile' in profile_message.sub_messages and 'avatar_image' in profile_message.sub_messages:
                        cachedprofile = self.storageDB.cacheProfiles(key_id=keyid,
                                                            updated=datetime.strptime(current_time(),"%Y-%m-%d %H:%M:%S"),
                                                            display_name=profile_message.sub_messages['display_name'],
                                                            profile_text=profile_message.sub_messages['profile'],
                                                            avatar_base64=profile_message.sub_messages['avatar_image'])
                        session.add(cachedprofile)
                        session.commit()
                    else:
                        print "Profile message did not contain mandatory fields"
        #            imp_res = self.gpg.import_keys(msg.payload) # we could import it here but we use the local keyserver
            else:
                print "No profile message found in profile returned from " + keyid
        else:
            flash_msg = queue_task(0,'flash_error','Message received for non-inbox topic - ' + msg.topic)
            self.q_res.put(flash_msg)
            print "Non PM message recv: " + msg.payload

    def setup_message_queues(self,client):
        client.subscribe(self.sub_inbox,1)                      # Our generic incoming queue, qos=1
        client.publish(self.pub_key,self.gpg.export_keys(self.mypgpkeyid,False,minimal=True),1,True)      # Our published pgp key block, qos=1, durable
        # build and send profile message
        profile_message = Message()
        profile_message.type = 'Profile Message'
        profile_message.sender = self.mypgpkeyid
        profile_dict = {}
        profile_dict['display_name'] = self.display_name
        profile_dict['profile'] = self.profile_text
        profile_dict['avatar_image'] = self.avatar_image
        profile_message.sub_messages = profile_dict # todo: use .append to add a submessage instead
        profile_out_message = Messaging.PrepareMessage(self.myMessaging,profile_message)
        client.publish(self.pub_profile,profile_out_message,1,True)      # Our published profile queue, qos=1, durable
        # TODO: build items message
        client.publish(self.pub_items,"User is not publishing any items",1,True)      # Our published items queue, qos=1, durable

    def sendMessage(self,client,message):
        message.recipient = parse_user_name(message.recipient).pgpkey_id
        # do we have this key?
        if not got_pgpkey(self.storageDB, message.recipient):
            # need to get the recipients public key
            self.task_state_messages[message.id]['state']= MSG_STATE_NEEDS_KEY
            self.task_state_messages[message.id]['message']= message
#            return False # Message processing is deferred pending a key, added message to task_state_messages todo remove line to saveto db even if no key is present
        else:
            outMessage = self.myMessaging.PrepareMessage(message)
            if not outMessage:
                flash_msg = queue_task(0,'flash_error','Error: Message could not be prepared')
                self.q_res.put(flash_msg)
                return False
            res = client.publish("user/" + message.recipient + "/inbox", outMessage, 1, False)
            if res[0] == MQTT_ERR_SUCCESS:
                flash_msg = queue_task(0,'flash_message','Message sent to ' + message.recipient)
                message.sent = True
                self.q_res.put(flash_msg)
            else:
                flash_msg = queue_task(0,'flash_message','Message queued for ' + message.recipient)
                self.q_res.put(flash_msg)
                self.task_state_messages[message.id]['state']= MSG_STATE_QUEUED
                self.task_state_messages[message.id]['message']= message
        # Calculate purge date for this message
        purgedate = datetime.now()+timedelta(days=self.message_retention)
        if message.datetime_sent:
            formatted_msg_sent_date = datetime.strptime(message.datetime_sent,"%Y-%m-%d %H:%M:%S")
        else:
            formatted_msg_sent_date = None
        # Write the message to the database as long as we havent already - check to see if message id already exists first
        session = self.storageDB.DBSession()
        if message.type == "Txn Message": # This is a transaction message
            new_db_message = self.storageDB.PrivateMessaging(
                                                                sender_key=message.sender,
                                                                sender_name=message.sender_name,
                                                                recipient_key=message.recipient,
                                                                recipient_name=message.recipient_name,
                                                                message_id=message.id,
                                                                message_purge_date = purgedate, # this will not be used directly (no purge for txn msgs)
                                                                message_date=formatted_msg_sent_date,
                                                                subject=message.subject,
                                                                body=message.body,
                                                                message_sent=message.sent,
                                                                message_read=message.read,
                                                                message_direction="Out"
                                                             )
            session.add(new_db_message)

        elif message.type == "Private Message":
            if session.query(self.storageDB.PrivateMessaging).filter(self.storageDB.PrivateMessaging.message_id == message.id).count() > 0: # If it already exists then update
                # Message ID already esists in db. in theory all we could be doing now is updating sent status and sent date
                message_to_update = session.query(self.storageDB.PrivateMessaging).filter(self.storageDB.PrivateMessaging.message_id == message.id).update({
                                                                self.storageDB.PrivateMessaging.message_date:formatted_msg_sent_date,
                                                                self.storageDB.PrivateMessaging.message_sent:message.sent
                                                            })
            else:
                new_db_message = self.storageDB.PrivateMessaging(
                                                                    sender_key=message.sender,
                                                                    sender_name=message.sender_name,
                                                                    recipient_key=message.recipient,
                                                                    recipient_name=message.recipient_name,
                                                                    message_id=message.id,
                                                                    message_purge_date = purgedate,
                                                                    message_date=formatted_msg_sent_date,
                                                                    subject=message.subject,
                                                                    body=message.body,
                                                                    message_sent=message.sent,
                                                                    message_read=message.read,
                                                                    message_direction="Out"
                                                                )
                session.add(new_db_message)
        session.commit()

    def delete_pm(self,id):
        flash_msg = queue_task(0,'flash_message','Deleted private message ')
        self.q_res.put(flash_msg)
        # Write the message to the database
        session = self.storageDB.DBSession()
        session.query(self.storageDB.PrivateMessaging).filter_by(id=id).delete()
        session.commit()

    def make_pgp_auth(self):
        password_message = {}
        password_message['time']=str(timegm(gmtime())/60)
        password_message['broker']=self.targetbroker
        password_message['key']=self.gpg.export_keys(self.mypgpkeyid,False,minimal=False)
        password = str(self.gpg.sign(json.dumps(password_message),keyid=self.mypgpkeyid,passphrase=self.pgp_passphrase))
        return password


    def select_random_broker(self):
        transports=[]
        if self.i2p_proxy_enabled and len(self.i2p_brokers) > 0:
            transports.append('i2p')
        if self.proxy_enabled and len(self.onion_brokers) > 0:
            transports.append('tor')
        transport = random.choice(transports)
        if transport == 'i2p':
            self.targetbroker = random.choice(self.i2p_brokers)
        elif transport == 'tor':
            self.targetbroker = random.choice(self.onion_brokers)

    def new_contact(self, contact):
        if contact.pgpkey != "":
            importedkey = self.gpg.import_keys(contact.pgpkey)
            contact.pgpkeyid = str(importedkey.fingerprints[0][-16:])
            if not importedkey.count == 1 and contact.pgpkeyid:
                flash_msg = queue_task(0,'flash_error','Contact not added: unable to extract PGP key ID for ' + contact.displayname)
                self.q_res.put(flash_msg)
                return False
        elif not contact.pgpkeyid:
            return False
        flash_msg = queue_task(0,'flash_message','Added contact ' + contact.displayname + '(' + contact.pgpkeyid + ')')
        self.q_res.put(flash_msg)
        session = self.storageDB.DBSession()
        new_db_contact = self.storageDB.Contacts(
                                                    contact_name=contact.displayname,
                                                    contact_key=contact.pgpkeyid,
                                                    #
                                                 )
        session.add(new_db_contact)
        cachedkey = self.storageDB.cachePGPKeys(key_id=contact.pgpkeyid,
                                                        updated=datetime.strptime(current_time(),"%Y-%m-%d %H:%M:%S"),
                                                        keyblock=contact.pgpkey )
        session.add(cachedkey)
        session.commit()

    def new_listing(self, listing):
        if listing.title != "":
            pass
        else:
            return False
        flash_msg = queue_task(0,'flash_message','Added listing ' + listing.title)
        self.q_res.put(flash_msg)
        session = self.storageDB.DBSession()
        new_listing = self.storageDB.Listings(
                                                    id=listing.id,
                                                    title=listing.title,
                                                    description=listing.description,
                                                    price=listing.unitprice,
                                                    currency_code = listing.currency_code
                                                    # TODO: Add other fields
                                                 )
        session.add(new_listing)
        session.commit()

    def read_configuration(self):
        # read configuration from database
        session = self.storageDB.DBSession()
        try:
            socks_proxy_enabled = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "socks_enabled").first()
            i2p_socks_proxy_enabled = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "i2p_socks_enabled").first()
            socks_proxy = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "proxy").first()
            socks_proxy_port = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "proxy_port").first()
            i2p_socks_proxy = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "i2p_proxy").first()
            i2p_socks_proxy_port = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "i2p_proxy_port").first()
            brokers = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "hubnodes").all()
            display_name = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "displayname").first()
            publish_identity = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "publish_identity").first()
            profile_text = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "profile").first()
            avatar_image = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "avatar_image").first()
            message_retention = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "message_retention").first()
            allow_unsigned = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "accept_unsigned").first()
        except:
            return False
        # Tor SOCKS proxy
        self.proxy = socks_proxy.value
        self.proxy_port = socks_proxy_port.value
        if socks_proxy.value and socks_proxy_port.value and (socks_proxy_enabled.value == 'True'):
            self.proxy_enabled = bool(socks_proxy_enabled)
        else:
            self.proxy_enabled = False
        # i2p SOCKS proxy
        self.i2p_proxy = i2p_socks_proxy.value
        self.i2p_proxy_port = i2p_socks_proxy_port.value
        if i2p_socks_proxy.value and i2p_socks_proxy_port.value and (i2p_socks_proxy_enabled.value == 'True'):
            self.i2p_proxy_enabled = bool(i2p_socks_proxy_enabled)
        else:
            self.i2p_proxy_enabled = False
        self.brokers = brokers
        self.display_name = display_name.value
        if profile_text:
            self.profile_text = profile_text.value
        else:
            self.profile_text =''
        if avatar_image:
            self.avatar_image = avatar_image.value
        else:
            self.avatar_image =''
        self.retention_period = message_retention
        self.allow_unsigned = bool(allow_unsigned)
        # TODO: Read and assign all config options
        return True

    def run(self):
        # TODO: Clean up this flow
        # make db connection

        self.storageDB = Storage(self.dbsecretkey,"storage.db",self.appdir)
        if not self.storageDB.Start():
            print "Error: Unable to start storage database"
            flash_msg = queue_task(0,'flash_error','Unable to start storage database ' + 'storage.db') #' self.targetbroker)
            self.q_res.put(flash_msg)
            self.shutdown = True
        # read configuration from config table
        if not self.read_configuration():
            flash_msg = queue_task(0,'flash_error','Unable to read configuration from database ' + 'storage.db') #' self.targetbroker)
            self.q_res.put(flash_msg)
            self.shutdown = True
        # TODO: Execute database weeding functions here to include:
        # 1 - purge all PM's older than the configured retention period (unless message has been marked for retention)
        # 2 - purge addresses (buyer & seller side) for address information related to finalized transactions
        # -------------------------
        # COnfirm proxy settings

        # sort the broker list into Tor, i2p and clearnet
        for broker in self.brokers:
            broker = broker[0]
            if str(broker).endswith('.onion'):
                self.onion_brokers.append(broker)
            elif str(broker).endswith('.b32.i2p'):
                self.i2p_brokers.append(broker)
            else:   # There is a broker than appears to be neither Tor or i2p - we will not process these further for now unless test mode is enabled
                # TODO: check for test mode and permit clearnet RFC1918 addresses only if it is enabled - right now these will be ignored
                self.clearnet_brokers.append(broker)
        if (not self.proxy_enabled) and (not self.i2p_proxy_enabled):
                flash_msg = queue_task(0,'flash_error','WARNING: No Tor or i2p proxy specified. Setting off-line mode for your safety')
                self.q_res.put(flash_msg)
                self.workoffline = True
        # self.targetbroker = random.choice(self.brokers).value
        if not self.workoffline:
            # Select a random broker from our list of entry points and make mqtt connection
            self.select_random_broker()
            if self.targetbroker.endswith('.onion'):
                client = mqtt(self.mypgpkeyid,False,proxy=self.proxy,proxy_port=int(self.proxy_port))
                print self.proxy
                print self.proxy_port
                flash_msg = queue_task(0,'flash_message','Connecting to Tor hidden service ' + self.targetbroker)
                self.q_res.put(flash_msg)
            elif self.targetbroker.endswith('.b32.i2p'):
                client = mqtt(self.mypgpkeyid,False,proxy=self.i2p_proxy,proxy_port=int(self.i2p_proxy_port))
                print self.i2p_proxy
                print self.i2p_proxy_port
                flash_msg = queue_task(0,'flash_message','Connecting to i2p hidden service ' + self.targetbroker)
                self.q_res.put(flash_msg)
            else: # TODO: Only if in test mode
                if self.test_mode == True:
                    client = mqtt(self.mypgpkeyid,False,proxy=None,proxy_port=None)
                flash_msg = queue_task(0,'flash_error','WARNING: On-line mode enabled and target broker does not appear to be a Tor or i2p hidden service')
                self.q_res.put(flash_msg)
            # client = mqtt.Client(self.mypgpkeyid,False) # before custom mqtt client # original paho-mqtt
            client.on_connect= self.on_connect
            client.on_message = self.on_message
            client.on_disconnect = self.on_disconnect
            client.on_publish = self.on_publish
            client.on_subscribe = self.on_subscribe
            # create broker authentication request
            password=self.make_pgp_auth()
            # print password
            client.username_pw_set(self.mypgpkeyid,password)
            flash_msg = queue_task(0,'flash_status','Connecting...')
            self.q_res.put(flash_msg)
            try:
                self.connected = False
                #client.connect_async(self.targetbroker, 1883, 60)  # This is now async
                client.connect(self.targetbroker, 1883, 60)  # This is now async
#                time.sleep(0.5) # TODO: Find a better way to prevent the disconnect/reconnection loop following a connect

            except: # TODO: Async connect now means this error code will need to go elsewhere
                flash_msg = queue_task(0,'flash_error','Unable to connect to broker ' + self.targetbroker + ', retrying...')
                self.q_res.put(flash_msg)
                pass
        while not self.shutdown:
            if not self.workoffline:
                    client.loop(0.05) # deal with mqtt events
            time.sleep(0.05)
#            if not self.connected and not self.workoffline and 1==0: # TODO - sort this!!
#                try:
#                    # create broker authentication request
#                    flash_msg = queue_task(0,'flash_status','Connecting...')
#                    self.q_res.put(flash_msg)
#                    password=self.make_pgp_auth()
#                    client.username_pw_set(self.mypgpkeyid,password)
#                    client.connect(self.targetbroker, 1883, 60) # todo: make this connect_async
#                    time.sleep(0.5) # TODO: Find a better way to prevent the disconnect/reconnection loop following a connect
#                    self.connected = True
#                except:
#                    # print "Could not connect to broker, will retry (main loop)"
#                    print "reconnect failed"
#                    pass

            for pending_message in self.task_state_messages.keys():   # check any messages queued for whatever reason
                if self.task_state_messages[pending_message]['message'].sender == self.mypgpkeyid:
                    outbound=True
                    pending_key=self.task_state_messages[pending_message]['message'].recipient
                else:
                    outbound=False
                    pending_key=self.task_state_messages[pending_message]['message'].sender
                pending_message_state = self.task_state_messages[pending_message]['state']
                # check pending message state
                if pending_message_state == MSG_STATE_NEEDS_KEY:
                    print "Need to request key " + pending_key
                    self.task_state_pgpkeys[pending_key]['state']=KEY_LOOKUP_STATE_INITIAL # create task request for a lookup
                    self.task_state_messages[pending_message]['state']=MSG_STATE_KEY_REQUESTED
                elif pending_message_state == MSG_STATE_KEY_REQUESTED:
#                    print "Message is waiting on a key " + self.task_state_messages[pending_message]['message'].recipient
                    if self.task_state_pgpkeys[pending_key]['state']==KEY_LOOKUP_STATE_FOUND:
                        self.task_state_messages[pending_message]['state']=MSG_STATE_READY_TO_PROCESS
                        del self.task_state_pgpkeys[pending_key]
                elif pending_message_state == MSG_STATE_QUEUED:
                    print "Can we send queued message for " + self.task_state_messages[pending_message]['message'].recipient
                    if self.connected:
                        if outbound: # this should always be true as incoming messages should never be set to MSG_STATE_QUEUED
                            self.sendMessage(client,self.task_state_messages[pending_message]['message'])
                            self.task_state_messages[pending_message]['state']=MSG_STATE_DONE
                elif pending_message_state == MSG_STATE_READY_TO_PROCESS:
                    print "Deferred message now ready - send the message now"
                    if outbound:
                        self.sendMessage(client,self.task_state_messages[pending_message]['message'])
                        self.task_state_messages[pending_message]['state']=MSG_STATE_DONE
                elif pending_message_state == MSG_STATE_DONE:
                    del self.task_state_messages[pending_message]

            for pgp_key in self.task_state_pgpkeys.keys():   # initiate & monitor pgp key requests
                try:
                    state = self.task_state_pgpkeys[pgp_key]['state']
                except KeyError:
                    state = None
                if state == KEY_LOOKUP_STATE_INITIAL:
                    key_topic = 'user/' + pgp_key + '/key'
                    res = client.subscribe(str(key_topic),1)
                    if res[0] == MQTT_ERR_SUCCESS:
                        self.task_state_pgpkeys[pgp_key]['state'] = KEY_LOOKUP_STATE_REQUESTED
#                elif state == KEY_LOOKUP_STATE_REQUESTED:
#                    print "Waiting for key..."
#                elif state == KEY_LOOKUP_STATE_FOUND:
#                    print "Got key."
                elif state == KEY_LOOKUP_STATE_NOTFOUND:
                    print "Could not find a key OR unable to retrieve key"

            if not self.q.empty():
                task = self.q.get()
                if task.command == 'send_pm':
                    message = Message()
                    message.type = 'Private Message'
                    message.sender = self.mypgpkeyid
                    message.recipient = task.data['recipient']
                    message.subject = task.data['subject']
                    message.body = task.data['body']
                    message.sent = False
                    self.sendMessage(client,message)
                elif task.command == 'delete_pm':
                    message_to_del = task.data['id']
                    self.delete_pm(message_to_del)
                elif task.command == 'get_key': # fetch a key from a user
                    print "Requesting key"
                    key_topic = 'user/' + task.data['keyid'] + '/key'
                    client.subscribe(str(key_topic),1)
                    self.task_state_pgpkeys[task.data['keyid']]['state']=KEY_LOOKUP_STATE_INITIAL # create task request for a lookup
                elif task.command == 'get_profile':
                    key_topic = 'user/' + task.data['keyid'] + '/profile'
                    client.subscribe(str(key_topic),1)
                    print "Requesting profile"
                elif task.command == 'new_contact':
                    contact = Contact()
                    contact.displayname = task.data['displayname']
                    contact.pgpkey = task.data['pgpkey']
                    contact.pgpkeyid = task.data['pgpkeyid']
                    contact.flags = ''#task.data['flags']
                    self.new_contact(contact)
                elif task.command == 'new_listing':
                    print "New listing: " + task.data['title']
                    listing = Listing()
                    listing.title=task.data['title']
                    listing.description=task.data['description']
                    listing.unitprice=task.data['price']
                    listing.currency_code=task.data['currency']
                    #TODO: add other listing fields
                    self.new_listing(listing)
                elif task.command == 'shutdown':
                    self.shutdown = True
        try:
            client
        except NameError:
            pass
        else:
            if client._state == mqtt_cs_connected:
                client.disconnect()
        self.storageDB.DBSession.close_all()
        print "client-backend exits"
        # Terminated

