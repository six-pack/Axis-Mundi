# Axis Mundi, Message Transport Service - MQTT

# This class defines an Axis Mundi Message Transport Service, in this case the transport is MQTT over Tor or i2p
# Axis Mundi uses a standardized pgp/json message format but is independent of the underlying transport

# The message transport service runs in a thread and interacts with the calling thread using queues

import sys
import Queue
import threading
import logging
from time import sleep
from collections import defaultdict
import random
import re
import time
import hashlib

from mqtt_client import MQTT_ERR_SUCCESS, mqtt_cs_connected, MQTTMessage
from mqtt_client import Client as mqtt
from utilities import queue_task


logging.basicConfig(level=logging.INFO,format='[%(levelname)-7s] (%(module)s:%(threadName)s:%(funcName)s) -- %(message)s')
logger = logging.getLogger(__name__)


class Transport_Service_MQTT (threading.Thread):

    def __init__ (self, brokers,
                 tor_socks_host=None, tor_socks_port=0,
                 i2p_socks_host=None, i2p_socks_port=0,
                 pgp_key_id=None,
                 in_queue = None, out_queue = None):

        self.running = True

        self.mqtt_mid_queue_task_map = dict()           # Dict holding mapping of MQTT MID to Task Queue ID
        self.mqtt_sub_topic_queue_task_map = dict()     # Dict holding mapping of subscribed topics to task Queue ID, used for tracking subscribe/unsubscribing for transient subs such as key requests, profile requests etc
        self.inbound_msg_hashes = set()                 # Set holding SHA1 hashes of messages received in this session - used only for naive de-duplication before passing message for verification and further processing

        self.tor_socks_host = tor_socks_host
        self.tor_socks_port = int(tor_socks_port)
        self.i2p_socks_host = i2p_socks_host
        self.i2p_socks_port = int(i2p_socks_port)
        self.tor_brokers = []
        self.i2p_brokers = []
        self.clearnet_brokers = []
        self.current_broker = None
        self.current_network = None         # ('tor' or 'i2p' at present)
        self.broker_password = None
        self.pgp_key_id = pgp_key_id

        self.queue_to_message_transport_service = in_queue            # For receiving messages from messaging sub-system
        self.queue_from_message_transport_service = out_queue          # For sending messages to messaging sub-system

        self.tor_socks_enabled = bool(self.tor_socks_host and self.tor_socks_port)
        self.i2p_socks_enabled = bool(self.i2p_socks_host and self.i2p_socks_port)

        self.transport = mqtt(self.pgp_key_id, False, proxy=None, proxy_port=None)

        self.transport.on_connect = self.on_connect
        self.transport.on_message = self.on_message
        self.transport.on_disconnect = self.on_disconnect
        self.transport.on_publish = self.on_publish
        self.transport.on_subscribe = self.on_subscribe
        self.transport.on_unsubscribe = self.on_unsubscribe
#        self.transport.message_callback_add('key/+', self.on_pgpkey) # TODO
        self.broker_connected = False

        if not (isinstance(self.queue_to_message_transport_service, Queue.Queue) and isinstance(self.queue_from_message_transport_service, Queue.Queue)):
            logger.error('No valid queues defined. Disabling message transport service')
            raise ValueError('No queues defined')

        for broker in brokers:
            if str(broker).endswith('.onion'):
                self.tor_brokers.append(broker)
            elif str(broker).endswith('.b32.i2p'):
                self.i2p_brokers.append(broker)
            else:   # There is a broker than appears to be neither Tor or i2p - we will not process these further for now unless test mode is enabled and they are RFC1918 ip addresses
                # TODO: check for test mode allow use of RFC1918 brokers
                if re.match('^(?:10|127|172\.(?:1[6-9]|2[0-9]|3[01])|192\.168)\..*',broker):
                    self.clearnet_brokers.append(broker)
                else:
                   logger.warning('Broker specification is a public address, dropping %s', broker)

        if len(self.tor_brokers) == 0:
            self.tor_socks_enabled  = False

        if len(self.i2p_brokers) == 0:
            self.i2p_socks_enabled  = False

        if not (self.tor_socks_enabled or self.i2p_socks_enabled):
            logger.error('No suitable brokers and/or proxies defined. Disabling message transport service')
            raise ValueError('No brokers and/or proxies defined')

        logger.info('Tor enabled: %s', self.tor_socks_enabled)
        logger.info('I2p enabled: %s', self.i2p_socks_enabled)

        threading.Thread.__init__(self)


    def select_random_broker(self):

        transports = []

        if self.i2p_socks_enabled:
            transports.append('i2p')
        if self.tor_socks_enabled:
            transports.append('tor')

        self.current_network = random.choice(transports)

        if self.current_network == 'i2p':
            self.current_broker = random.choice(self.i2p_brokers)
            self.transport._proxy=self.i2p_socks_host
            self.transport._proxy_port=self.i2p_socks_port
        elif self.current_network == 'tor':
            self.current_broker = random.choice(self.tor_brokers)
            self.transport._proxy=self.tor_socks_host
            self.transport._proxy_port=self.tor_socks_port


    def on_connect(self, client, userdata, flags, rc):
        self.broker_connected = True
        logger.info('Connected to broker %s using %s', self.current_broker, self.current_network)


    def on_message(self, client, userdata, msg):
        logger.info('Message received on %s using %s', msg.topic, self.current_broker)
        # Send incoming message to messaging system
        hash = hashlib.sha1(msg.payload)
        if hash.hexdigest() in self.inbound_msg_hashes:
            logger.warning('Duplicate message on %s dropped', msg.topic)
            return
        else:
            self.inbound_msg_hashes.add(hash.hexdigest())

        queue_update_msg = queue_task(id='mts_mqtt:0',
                                     command='inbound_message',
                                     data={'payload':msg.payload,'location':msg.topic},
                                     msg_type=queue_task.UPDATE)
        self.queue_from_message_transport_service.put(queue_update_msg)


    def on_disconnect(self, client, userdata, rc):
        self.broker_connected = False
        if rc == 0:
            # This appears to be a graceful disconnect
            logger.info('Disconnected from broker %s using %s', self.current_broker, self.current_network)
        else:
            # This appears to be an unexpected disconnect
            logger.warning('Unexpectedly disconnected from broker %s using %s', self.current_broker, self.current_network)
        # Flush any items in the queue task dicts, marking as NOT_OK and postingback REPLY messages
        self.flush_unfinished_mqtt_operations()




    def on_publish(self, client, userdata, mid):
        logger.info('Message published sucessfuly on %s using %s', self.current_broker, self.current_network)
        try:
            queue_msg_id = self.mqtt_mid_queue_task_map[mid]
            self.mqtt_mid_queue_task_map.__delitem__(mid)
        except KeyError:
            logger.error('Could not associate outbound MQTT message ID with a queue task ID')
            return
        # Delivered
        queue_reply_msg = queue_task(queue_msg_id,
                                     command=None,
                                     data=None,
                                     rc=queue_task.OK,
                                     msg_type=queue_task.REPLY)
        self.queue_from_message_transport_service.put(queue_reply_msg)


    def on_subscribe(self, client, userdata, mid, granted_qos):
        logger.info('Topic subscribed on broker %s using %s', self.current_broker, self.current_network)
        try:
            queue_msg_id = self.mqtt_mid_queue_task_map[mid]
            subscribed_topic = self.mqtt_sub_topic_queue_task_map[queue_msg_id]
            #logger.info('Now unsubscribing from %s',subscribed_topic)
            u_rc,u_mid = self.transport.unsubscribe (subscribed_topic)
            self.mqtt_mid_queue_task_map[u_mid] = queue_msg_id  # create a new mqtt MID <> queue mapping for the unsubscribe
            self.mqtt_mid_queue_task_map.__delitem__(mid) # and delete the original queue mapping for the subscribe

        except KeyError:
            logger.info('Persistent subscription created')

    def on_unsubscribe(self, client, userdata, mid):
        logger.info('Topic unsubscribed on broker %s using %s', self.current_broker, self.current_network)
        try:
            queue_msg_id = self.mqtt_mid_queue_task_map[mid]
            subscribed_topic = self.mqtt_sub_topic_queue_task_map[queue_msg_id]
            logger.info('Now unsubscribed from %s (originally requested for %s)',subscribed_topic,queue_msg_id)
            # TODO - if no message was received for this subscription by now then it is now safe to assume that no message exists - deal with that here or in messaging?
            self.mqtt_mid_queue_task_map.__delitem__(mid)
            self.mqtt_sub_topic_queue_task_map.__delitem__(queue_msg_id)
            # get_message has completed sucessfully in any case
            queue_reply_msg = queue_task(id=queue_msg_id,
                                         command=None,
                                         data=None,
                                         rc=queue_task.OK,
                                         msg_type=queue_task.REPLY)
            self.queue_from_message_transport_service.put(queue_reply_msg)
        except KeyError:
            logger.info('Unsubscribed from persistent connection (probably)')


    def on_pgpkey(self, client, userdata, msg):
        logger.info('PGP key received %s using %s', self.current_broker, self.current_network)


    def mqtt_publish_message (self, msg=None, mqtt_topic=None, qos=1, queue_task_id=None, publish=False):

        rc,mid = self.transport.publish(topic=mqtt_topic,payload=msg,qos=1,retain=publish)
        if not rc == MQTT_ERR_SUCCESS:
            # Not delivered
            queue_reply_msg = queue_task(id=queue_task_id,
                                         rc=queue_task.NOT_OK,
                                         msg_type=queue_task.REPLY)
            self.queue_from_message_transport_service.put(queue_reply_msg)
            logger.warning('Could not deliver MQTT message to %s requested by task queue ID %s',mqtt_topic,queue_task_id)
        else:
            self.mqtt_mid_queue_task_map[mid]=queue_task_id  # Store the returned MID and associate it with the queue message id



    def mqtt_subscribe_message (self, mqtt_topic=None, qos=0, queue_task_id=None, persistent=False):

        rc,mid = self.transport.subscribe(topic=mqtt_topic,qos=qos)

        if not rc == MQTT_ERR_SUCCESS:
            # Could not subscribe to get message
            queue_reply_msg = queue_task(id=queue_task_id,
                                         rc=queue_task.NOT_OK,
                                         msg_type=queue_task.REPLY)
            self.queue_from_message_transport_service.put(queue_reply_msg)
            logger.warning('Could not subscribe to MQTT topic %s requested by task queue ID %s',mqtt_topic,queue_task_id)
        else:
            if not persistent:
                # Only store the mid if the request is for a single retained message - if a mid is present during on_subscribe() then we will unsubscribe
                self.mqtt_mid_queue_task_map[mid] = queue_task_id               # Store the returned MID and associate it with the queue message id
                self.mqtt_sub_topic_queue_task_map[queue_task_id] = mqtt_topic      # Store the desired topic associted withe the queue_task_id



    def check_queues(self):

        while not self.queue_to_message_transport_service.empty():

            queue_msg = self.queue_to_message_transport_service.get()
            if isinstance(queue_msg,queue_task):
                logger.info('Incoming queue message %s(%s) ID: %s ', queue_msg.command,queue_msg.msg_type,queue_msg.id)
                if queue_msg.msg_type == queue_task.REQUEST:
                    self.process_queued_task_request(queue_msg)
                elif queue_msg.msg_type == queue_task.REPLY:
                    self.process_queued_task_reply(queue_msg)
            else:
                logger.warning('Found something strange on my input queue, dropping it. %s', queue_msg)



    def process_queued_task_request(self,queue_msg):
            logger.info ("Task ID %s received from Messaging system : %s %s ",  queue_msg.id, queue_msg.command, queue_msg.data)

            if queue_msg.command == 'shutdown':
                logger.debug('Message Transport Service (MQTT) shutdown requested')
                self.running = False

            elif queue_msg.command == 'send_directed_msg':
                mqtt_topic = 'mesh/local/user/' + queue_msg.data['recipient'] + '/inbox'
                msg = queue_msg.data['content']
                self.mqtt_publish_message (msg=msg, mqtt_topic=mqtt_topic, qos=1, queue_task_id=queue_msg.id)

            elif queue_msg.command == 'publish_msg':
                mqtt_topic = 'mesh/local/user/' + self.pgp_key_id + '/' + queue_msg.data['location']    # location = ( key | direcory | profile | items )
                msg = queue_msg.data['content']
                self.mqtt_publish_message (msg=msg, mqtt_topic=mqtt_topic, qos=1, queue_task_id=queue_msg.id, publish=True)

            elif queue_msg.command == 'get_published_msg':
                mqtt_topic = 'mesh/+/user/' + queue_msg.data['location']    # location = ( key | direcory | profile | items )
                self.mqtt_subscribe_message(mqtt_topic=mqtt_topic,qos=0,queue_task_id=queue_msg.id)


    def process_queued_task_reply(self,queue_msg):
        # The only replies the message transport service gets are authentication messages which are prepared by the messaging system for us
        if queue_msg.command == 'make_mqtt_pgp_auth' and queue_msg.rc == queue_task.OK:
            logger.info('Received authentication ticket from messaging service for broker %s', self.current_broker)
            self.broker_password = queue_msg.data


    def request_auth_ticket(self,broker):
        # Request an authentication ticket from the main messaging system
        self.broker_password = None
        logger.info('Requesting authentication ticket from messaging service for broker %s', self.current_broker)
        auth_req_task = queue_task(id='mts_mqtt:1',command='make_mqtt_pgp_auth',data=broker,msg_type=queue_task.REQUEST)
        self.queue_from_message_transport_service.put (auth_req_task)


    def flush_unfinished_mqtt_operations(self):
        logger.info('Checking for incomplete MQTT tasks')
        for mid,task_id in self.mqtt_mid_queue_task_map.items():
            queue_reply_msg = queue_task(task_id,
                             command=None,
                             data=None,
                             rc=queue_task.NOT_OK,
                             msg_type=queue_task.REPLY)
            self.queue_from_message_transport_service.put(queue_reply_msg)
            logger.warning('Failing and purging incomplete MQTT task %s',task_id)
        self.mqtt_mid_queue_task_map.clear()
        self.mqtt_sub_topic_queue_task_map.clear()
        self.inbound_msg_hashes.clear()

    def run(self):

        connect_time = 0

        while self.running:
            if not self.broker_connected:

                if time.time() - connect_time > 10: # If more than X seconds since last connection attempt then we try another broker

                    if not connect_time == 0:
                        self.transport.loop_stop(force=True)
                        self.flush_unfinished_mqtt_operations()

                    connect_time = time.time()
                    self.select_random_broker()

                    logger.info('Attempting connection to broker %s using %s', self.current_broker, self.current_network)
                    self.request_auth_ticket(self.current_broker)

                    while not self.broker_password:
                        self.check_queues()
                        sleep(0.1)
                        if time.time() - connect_time > 5:
                            logger.error('Message transport service could not get authentication ticket for MQTT broker %s (TIMEOUT)', self.current_broker)
                            break

                    self.transport.username_pw_set(self.pgp_key_id, self.broker_password)
                    connect_time = time.time()
                    self.transport.connect_async(self.current_broker,1883,keepalive=30)
                    self.transport.loop_start()

            # Check queue for new tasks
            self.check_queues()
            sleep(0.01)

        logger.info('Stopping Message Transport Service (MQTT)')
        self.transport._send_disconnect()   # This seems necessary but feels nasty - TODO - investigate
        self.transport.loop_stop(force=True)
        self.transport.loop(timeout=1)
        self.flush_unfinished_mqtt_operations()
        logger.info('Message Transport Service (MQTT) exiting')

