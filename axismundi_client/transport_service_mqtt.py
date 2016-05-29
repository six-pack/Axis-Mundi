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

        self.mqtt_queue_task_map = dict()

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

        self.in_queue = in_queue            # For receiving messages from messaging sub-system
        self.out_queue = out_queue          # For sending messages to messaging sub-system

        self.tor_socks_enabled = bool(self.tor_socks_host and self.tor_socks_port)
        self.i2p_socks_enabled = bool(self.i2p_socks_host and self.i2p_socks_port)

        self.transport = mqtt(self.pgp_key_id, False, proxy=None, proxy_port=None)

        self.transport.on_connect = self.on_connect
        self.transport.on_message = self.on_message
        self.transport.on_disconnect = self.on_disconnect
        self.transport.on_publish = self.on_publish
        self.transport.on_subscribe = self.on_subscribe
#        self.transport.message_callback_add('key/+', self.on_pgpkey) # TODO
        self.broker_connected = False

        if not (isinstance(self.in_queue,Queue.Queue) and isinstance(self.out_queue,Queue.Queue)):
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
        logger.info('Message received %s using %s', self.current_broker, self.current_network)


    def on_disconnect(self, client, userdata, rc):
        if rc == 0:
            # This appears to be a graceful disconnect
            logger.info('Disconnected from broker %s using %s', self.current_broker, self.current_network)
        else:
            # This appears to be an unexpected disconnect
            logger.warning('Unexpectedly disconnected from broker %s using %s', self.current_broker, self.current_network)
        self.broker_connected = False


    def on_publish(self, client, userdata, mid):
        logger.info('Message published sucessfuly on %s using %s', self.current_broker, self.current_network)
        try:
            queue_msg_id = self.mqtt_queue_task_map[mid]
        except KeyError:
            logger.error('Could not associate outbound MQTT message ID with a queue task id')
            return
        # Delivered
        queue_reply_msg = queue_task(queue_msg_id,
                                     command=None,
                                     data=None,
                                     rc=queue_task.OK,
                                     msg_type=queue_task.REPLY)
        self.out_queue.put(queue_reply_msg)


    def on_subscribe(self, client, userdata, mid, granted_qos):
        logger.info('Topic Subscription on broker %s using %s', self.current_broker, self.current_network)



    def on_pgpkey(self, client, userdata, msg):
        logger.info('PGP key received %s using %s', self.current_broker, self.current_network)


    def mqtt_publish_message (self, msg=None, mqtt_topic=None, qos=1, queue_task_id=None, publish=False):

        rc,mid = self.transport.publish(topic=mqtt_topic,payload=msg,qos=1,retain=publish)

        if not rc == MQTT_ERR_SUCCESS:
            # Not delivered
            queue_reply_msg = queue_task(id=queue_task_id,
                                         command=None,
                                         data=None,
                                         rc=queue_task.NOT_OK,
                                         msg_type=queue_task.REPLY)
            self.out_queue.put(queue_reply_msg)
            logger.warning('Could not deliver MQTT message to to %s',mqtt_topic)
        else:
            self.mqtt_queue_task_map[mid]=queue_task_id  # Store the returned MID and associate it with the queue message id


    def check_queues(self):

        while not self.in_queue.empty():

            queue_msg = self.in_queue.get()
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
                mqtt_topic = 'mesh/local/user/' + queue_msg.data['location']    # location = ( key | direcory | profile | items )
                msg = queue_msg.data['content']
                self.mqtt_publish_message (msg=msg, mqtt_topic=mqtt_topic, qos=1, queue_task_id=queue_msg.id, publish=True)

            elif queue_msg.command == 'publish_msg':
                pass


    def process_queued_task_reply(self,queue_msg):
        # The only replies the message transport service gets are authentication messages which are prepared by the messaging system for us
        if queue_msg.command == 'make_mqtt_pgp_auth' and queue_msg.rc == queue_task.OK:
            self.broker_password = queue_msg.data


    def request_auth_ticket(self,broker):
        # Request an authentication ticket from the main messaging system
        self.broker_password = None
        logger.info('Requesting authentication ticket from messaging service for broker %s', self.current_broker)
        auth_req_task = queue_task(id='mts_mqtt:1',command='make_mqtt_pgp_auth',data=broker,msg_type=queue_task.REQUEST)
        self.out_queue.put (auth_req_task)


    def run(self):

        connect_time = 0

        while self.running:
            if not self.broker_connected:

                if time.time() - connect_time > 5: # If more than X seconds since last connection attempt then we try another broker
                    connect_time = time.time()
                    self.transport.loop_stop(force=True)
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
                    self.transport.connect_async(self.current_broker,1883,keepalive=60)
                    self.transport.loop_start()

            # Check queue for new tasks
            self.check_queues()
            sleep(0.01)

        logger.info('Stopping Message Transport Service (MQTT)')
        self.transport.loop_stop()
        self.transport.loop(timeout=1)
        logger.info('Message Transport Service (MQTT) exiting')

