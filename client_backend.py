import threading
import Queue
import time
from datetime import datetime
#import paho.mqtt.client as mqtt
#from paho.mqtt.client import MQTT_ERR_SUCCESS, mqtt_cs_connected
from mqtt_client import MQTT_ERR_SUCCESS, mqtt_cs_connected
from mqtt_client import Client as mqtt
from storage import Storage
import gnupg
from messaging import Message, Messaging, Contact
from utilities import queue_task, current_time
import json
import socks
import socket
from calendar import timegm
from time import gmtime
import random

class messaging_loop(threading.Thread):
# Authentication shall set the password to a PGP clear-signed message containing the follow data only
# broker-hostname:pgpkeyid:UTCdatetime
# The date time shall not contain seconds and will be chekced on the server to be no more than +/- 5 minutes fromcurrent server time

    def __init__ (self, pgpkeyid, pgppassphrase, dbpassphrase, database, homedir, appdir, q, q_res, workoffline=False):
        self.targetbroker = None
        self.mypgpkeyid = pgpkeyid
        self.q = q
        self.q_res = q_res
        self.database = database
        self.homedir = homedir
        self.appdir = appdir
        self.dbsecretkey = dbpassphrase
        self.gpg = gnupg.GPG(gnupghome=self.homedir + '/.gnupg',options='--primary-keyring='" + self.appdir + '/pubkeys.gpg"'')
        self.pgp_passphrase = pgppassphrase
        self.myMessaging = Messaging(self.mypgpkeyid,self.pgp_passphrase,homedir)
        self.sub_inbox = str("user/" + self.mypgpkeyid + "/inbox")
        self.pub_profile = str("user/" + self.mypgpkeyid + "/profile")
        self.pub_items = str("user/" + self.mypgpkeyid + "/items")
        self.storageDB = Storage
        self.connected = False
        self.workoffline = workoffline
        self.shutdown = False
        threading.Thread.__init__ (self)

    def on_connect(self, client, userdata, flags, rc):  # TODO: Check that these parameters are right, had to add "flags" which may break "rc"
        self.connected = True
        flash_msg = queue_task(0,'flash_status','On-line')
        self.q_res.put(flash_msg)
        flash_msg = queue_task(0,'flash_message','Connected to broker ' + self.targetbroker)
        self.q_res.put(flash_msg)
        self.setup_message_queues(client)

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        flash_msg = queue_task(0,'flash_status','Off-line')
        self.q_res.put(flash_msg)
        if self.shutdown:
            flash_msg = queue_task(0,'flash_message','Disconnected from ' + self.targetbroker)
        else:
            flash_msg = queue_task(0,'flash_message','Broker was disconnected, attempting to reconnect to ' + self.targetbroker)
        self.q_res.put(flash_msg)

    def on_message(self, client, userdata, msg):
        if msg.topic == self.sub_inbox:
            message = self.myMessaging.GetMessage(msg.payload)
            if message == False:  print "Message was invalid"
            elif message.type == 'Private Message':
                flash_msg = queue_task(0,'flash_message','Private message received from ' + message.sender)
                self.q_res.put(flash_msg)
                session = self.storageDB.DBSession()
                new_db_message = self.storageDB.PrivateMessaging(
                                                                    sender_key=message.sender,
                                                                    recipient_key=message.recipient,
                                                                    message_id=message.id,
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
#                                                                    message_date=datetime.strptime(current_time(),"%Y-%m-%d %H:%M:%S"),
#                                                                    subject=message.subject,
#                                                                    body=message.body,
#                                                                    message_sent=False,
#                                                                    message_read=False,
#                                                                    message_direction="In"
#                                                                 )
#                session.add(new_db_message)
#                session.commit()
        else:
            # todo: Check if this is for a PUB we have subscribed to temporarily
            flash_msg = queue_task(0,'flash_error','Message received for non-inbox topic - ' + msg.topic)
            self.q_res.put(flash_msg)
            print "Non PM message recv: " + msg.payload

    def setup_message_queues(self,client):
        client.subscribe(self.sub_inbox,1)                      # Our generic incoming queue, qos=1
        client.publish(self.pub_items,"User is not publishing any items",1,True)      # Our published items queue, qos=1, durable
        client.publish(self.pub_profile,"This will be the profile of " + self.mypgpkeyid,1,True)      # Our published profile queue, qos=1, durable

    def sendMessage(self,client,message):
        outMessage = self.myMessaging.PrepareMessage(message)
        if not outMessage:
            flash_msg = queue_task(0,'flash_error','Error: Message could not be prepared, check your recipient details')
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
        # Write the message to the database
        session = self.storageDB.DBSession()
        if message.type == "Txn Message": # This is a transaction message
            new_db_message = self.storageDB.PrivateMessaging(
                                                                sender_key=message.sender,
                                                                recipient_key=message.recipient,
                                                                message_id=message.id,
                                                                message_date=datetime.strptime(message.datetime_sent,"%Y-%m-%d %H:%M:%S"),
                                                                subject=message.subject,
                                                                body=message.body,
                                                                message_sent=message.sent,
                                                                message_read=message.read,
                                                                message_direction="Out"
                                                             )
        elif message.type == "Private Message":
            new_db_message = self.storageDB.PrivateMessaging(
                                                                sender_key=message.sender,
                                                                recipient_key=message.recipient,
                                                                message_id=message.id,
                                                                message_date=datetime.strptime(message.datetime_sent,"%Y-%m-%d %H:%M:%S"),
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

    def new_contact(self, contact):
        if not contact.pgpkey:
            return False
        importedkey = self.gpg.import_keys(contact.pgpkey)
        contact.pgpkeyid = str(importedkey.fingerprints[0][-16:])
        if not importedkey.count == 1 and contact.pgpkeyid:
            flash_msg = queue_task(0,'flash_error','Contact not added: unable to extract PGP key ID for ' + contact.displayname)
            self.q_res.put(flash_msg)
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
        session.commit()

    def read_configuration(self):
        # read configuration from database
        session = self.storageDB.DBSession()
        try:
            socks_proxy = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "proxy").first()
            socks_proxy_port = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "proxy_port").first()
            brokers = session.query(self.storageDB.Config.value).filter(self.storageDB.Config.name == "hubnodes").all()
        except:
            return False
        self.proxy = socks_proxy.value
        self.proxy_port = socks_proxy_port.value
        self.brokers = brokers
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
        # make mqtt connection
        client = mqtt(self.mypgpkeyid,False,proxy=self.proxy,proxy_port=int(self.proxy_port))
        # client = mqtt.Client(self.mypgpkeyid,False) # before custom mqtt client # original paho-mqtt
        client.on_connect= self.on_connect
        client.on_message = self.on_message
        client.on_disconnect = self.on_disconnect
        # Select a random broker from our list of entry points
        self.targetbroker = random.choice(self.brokers).value
        if not self.workoffline:
            # create broker authentication request
            password=self.make_pgp_auth()
            client.username_pw_set(self.mypgpkeyid,password)
            flash_msg = queue_task(0,'flash_status','Connecting...')
            self.q_res.put(flash_msg)
            try:
                self.connected = False
                client.connect(self.targetbroker, 1883, 60)
                time.sleep(0.5) # TODO: Find a better way to prevent the disconnect/reconnection loop following a connect

            except:
                flash_msg = queue_task(0,'flash_error','Unable to connect to broker ' + self.targetbroker + ', retrying...')
                self.q_res.put(flash_msg)
                pass
        while not self.shutdown:
            client.loop(0.05) # deal with mqtt events
            time.sleep(0.05)
            if not self.connected and not self.workoffline:
                try:
                    # create broker authentication request
                    flash_msg = queue_task(0,'flash_status','Connecting...')
                    self.q_res.put(flash_msg)
                    password=self.make_pgp_auth()
                    client.username_pw_set(self.mypgpkeyid,password)
                    client.connect(self.targetbroker, 1883, 60)
                    time.sleep(0.5) # TODO: Find a better way to prevent the disconnect/reconnection loop following a connect
                    self.connected = True
                except:
                    # print "Could not connect to broker, will retry (main loop)"
                    print "reconnect failed"
                    pass
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
                elif task.command == 'new_contact':
                    contact = Contact()
                    contact.displayname = task.data['displayname']
                    contact.pgpkey = task.data['pgpkey']
                    contact.pgpkeyid = task.data['pgpkeyid']
                    contact.flags = ''#task.data['flags']
                    self.new_contact(contact)
                elif task.command == 'shutdown':
                    self.shutdown = True
        client.disconnect()
        self.storageDB.DBSession.close_all()
        # Terminatedo

