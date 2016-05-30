# Axis Mundi, Message Service

# This class defines the Axis Mundi Message Service,
# The Message Service create one or more Message Transport Services for underlying network communications
# The Message Service also creates the PGP Service for all signing/verification/encryptiona and decryption of inbound and outbound messages

# The message transport service runs in a thread and interacts with the calling thread using queues

import sys
import Queue
import threading
import logging
from time import sleep
from collections import defaultdict

from calendar import timegm
from time import gmtime
import time
import json

from utilities import queue_task
from transport_service_mqtt import Transport_Service_MQTT
import gnupg


logging.basicConfig(level=logging.INFO,format='[%(levelname)-7s] (%(module)s:%(threadName)s:%(funcName)s) -- %(message)s')
logger = logging.getLogger(__name__)


# TODO - Create signing and decrypt only gpg service (maybe a threadpool)
# TODO - Then create general purpose encryption and verification instance (that instance will need local keyserver configure to fetch new keys)

class Message_Service (threading.Thread):

    def __init__ (self, pgp_key_id=None, passphrase=None,
                  work_offline=False,
                  in_queue = None, out_queue = None):

        self.running = True

        self.pgp_key_id = pgp_key_id
        self.passphrase = passphrase

        self.in_queue = in_queue            # For receiving messages from main sub-system
        self.out_queue = out_queue          # For sending messages to main sub-system

        self.mts = None

        if not (isinstance(self.in_queue,Queue.Queue) and isinstance(self.out_queue,Queue.Queue)):
            logger.error('No valid queues defined. Disabling message service')
            raise ValueError('No queues defined')

        threading.Thread.__init__(self)


    def set_mts(self, mts,
                brokers,
                 tor_socks_host=None, tor_socks_port=0,
                 i2p_socks_host=None, i2p_socks_port=0,
                 mts_in_queue = None, mts_out_queue = None):

        self.mts_in_queue = mts_in_queue
        self.mts_out_queue = mts_out_queue

        if not self.mts_in_queue:
            self.mts_in_queue = Queue.Queue()

        if not self.mts_out_queue:
            self.mts_out_queue = Queue.Queue()

        if mts == 'Transport_Service_MQTT':
            logger.info('Enabling %s', mts)
            self.mts = Transport_Service_MQTT(brokers, pgp_key_id=self.pgp_key_id,
                                              tor_socks_host=tor_socks_host,tor_socks_port=tor_socks_port,
                                              i2p_socks_host=i2p_socks_host,i2p_socks_port=i2p_socks_port,
                                              in_queue=self.mts_in_queue, out_queue=self.mts_out_queue)

    def make_pgp_auth(self,broker):
        # Temporary method for creating mqtt pgp auth ticker
        gpg = gnupg.GPG()
        mykey = self.pgp_key_id
        password_message = {}
        password_message['time'] = str(timegm(gmtime()) / 60)
        password_message['version'] = '1.0'
        password_message['broker'] = broker
        password_message['key'] = gpg.export_keys(
            mykey, False, minimal=False)
        password = str(gpg.sign(json.dumps(password_message),
                                     keyid=mykey, passphrase=self.passphrase))
        return password


    def process_queued_task_request(self,queue_msg,queue):
        if queue_msg.command == 'make_mqtt_pgp_auth':
            logger.info('Received authentication ticket request from messaging transport service for broker %s', queue_msg.data)
            password = self.make_pgp_auth(queue_msg.data)
            queue_msg_pgp_reply = queue_task(id=queue_msg.id,command=queue_msg.command,msg_type=queue_task.REPLY,rc=queue_task.OK, data=password)
            self.mts_in_queue.put(queue_msg_pgp_reply)


    def process_queued_task_update(self,queue_msg,queue):
        if queue_msg.command == 'inbound_message':
            logger.info('Received inbound message from messaging transport service for broker %s', queue_msg.data)
            #password = self.make_pgp_auth(queue_msg.data)
            #queue_msg_pgp_reply = queue_task(id=queue_msg.id,command=queue_msg.command,msg_type=queue_task.REPLY,rc=queue_task.OK, data=password)
            #self.mts_in_queue.put(queue_msg_pgp_reply)


    def process_queued_task_reply(self,queue_msg,queue):
       logger.info('Received a reply from the MTS %s', queue_msg.id)


    def run(self):

        if self.mts:
            self.mts.start()

        while self.running:

            # Check queue for new tasks
            while not self.in_queue.empty():

                queue_msg = self.in_queue.get()
                if isinstance(queue_msg,queue_task):
                    print "Message Service got a task"

            while self.mts and not self.mts_out_queue.empty():

                queue_msg = self.mts_out_queue.get()
                if isinstance(queue_msg,queue_task):
                    logger.info('Incoming task message %s(%s) ID: %s ', queue_msg.command,queue_msg.msg_type,queue_msg.id)

                    if queue_msg.msg_type == queue_task.REQUEST:
                        self.process_queued_task_request(queue_msg,self.mts_out_queue)
                    elif queue_msg.msg_type == queue_task.REPLY:
                        self.process_queued_task_reply(queue_msg,self.mts_out_queue)
                    elif queue_msg.msg_type == queue_task.UPDATE:
                        self.process_queued_task_update(queue_msg,self.mts_out_queue)
                else:
                    logger.warning('Found something strange on my input queue, dropping it. %s', queue_msg)

            sleep(0.01)

        logger.info('Stopping Message Service')

        logger.info('Message Service exiting')



