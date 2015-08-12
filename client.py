#!/usr/bin/env python

from flask import Flask, render_template, request, redirect, url_for, abort, session, flash, g, make_response
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user, login_required
from functools import wraps, update_wrapper
import gnupg
from os.path import expanduser, isfile, isdir, dirname
from os import makedirs, sys, unsetenv, putenv, sep
import string
import random
from storage import Storage, SqlalchemyOrmPage
from client_backend import messaging_loop
import Queue
from utilities import queue_task, encode_image, generate_seed, current_time, get_age, resource_path
from defaults import create_defaults
from time import sleep
import base64
from platform import system as get_os
import pybitcointools as btc
from collections import defaultdict
import json
from constants import *
from multiprocessing import Process, freeze_support
import multiprocessing.forking
import webbrowser
import trayicon_gui
import wx
import os

# /////////// patch socket module to attempt to fix bug #12 -  "socket.error: [Errno 98] Address already in use"
# This fixes re-use error but results in multiple cliet.py instances which is very undesirable
# TODO : Fix by ensuring that client.py Flask threads exit when we want them to
import socket
socket.socket._bind = socket.socket.bind


def my_socket_bind(self, *args, **kwargs):
    self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    return socket.socket._bind(self, *args, **kwargs)
#socket.socket.bind = my_socket_bind
# //////////// end socket patch

app = Flask(__name__)
# (8Mb maximum upload to local webserver) - make sure we dont need to use the disk
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
messageQueue = Queue.Queue()    # work Queue for mqtt client thread
messageQueue_res = Queue.Queue()    # Results Queue for mqtt client thread
# Profile and Listing Results Queue for mqtt client thread
messageQueue_data = Queue.Queue()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)
pager_items = 12  # default of 12 items per page when paginating


class User(UserMixin):

    def __init__(self, id):
        self.id = id

    @classmethod
    def get(self_class, id):
        try:
            return self_class(id)
        except:
            return None  # This should not happen


@login_manager.user_loader
def load_user(userid):
    return User.get(userid)

########## CSRF protection ###############################


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.pop('_csrf_token', None)
        if not token or token != request.form.get('_csrf_token'):
            flash('Invalid CSRF token, please try again.', category="error")
            # FIXME: This is not doing what it should
            redirect(request.endpoint, 302)


def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = ''.join(random.SystemRandom().choice(
            string.ascii_uppercase + string.digits) for _ in range(16))
    return session['_csrf_token']

######## STATUS, PAGE GLOBALS AND UPDATES ################################


@app.before_request
def get_connection_status():
    checkEvents()
    g.connection_status = app.connection_status


@app.after_request
def add_header(response):
    #response.cache_control.max_age = 0
    response.headers[
        'Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    return response

########## Flask Routes ##################################


@app.route('/')
@login_required
def home():
    checkEvents()
    return render_template('home.html')


@app.route('/orders')
@app.route('/orders/<int:page>')
@app.route('/orders/<string:view_type>')
@app.route('/orders/<string:view_type>/<int:page>')
@login_required
def orders(view_type='buying', page=1):
    checkEvents()
    session = app.roStorageDB.DBSession()
    page_results = None
    if view_type == 'buying':
        orders_buying = session.query(app.roStorageDB.Orders).filter_by(buyer_key=app.pgp_keyid).order_by(
            app.roStorageDB.Orders.order_date.asc())
        page_results = SqlalchemyOrmPage(
            orders_buying, page=page, items_per_page=pager_items)
    elif view_type == 'selling':
        orders_selling = session.query(app.roStorageDB.Orders).filter_by(seller_key=app.pgp_keyid).order_by(
            app.roStorageDB.Orders.order_date.asc())
        page_results = SqlalchemyOrmPage(
            orders_selling, page=page, items_per_page=pager_items)
    return render_template('orders.html', orders=page_results, view=view_type)


@app.route
@app.route('/listings/publish')
@login_required
def publish_listings():
    if app.workoffline:
        return redirect(url_for('listings'))
    task = queue_task(1, 'publish_listings', app.pgp_keyid)
    messageQueue.put(task)
    return redirect(url_for('listings'))


@app.route
@app.route('/listings/export')
@login_required
def export_listings():
    task = queue_task(1, 'export_listings', app.pgp_keyid)
    messageQueue.put(task)
    return redirect(url_for('listings'))


@app.route('/listings/view/<string:keyid>')
@app.route('/listings/view/<string:keyid>/<string:id>')
@login_required
def external_listings(keyid='none', id='none'):
    if keyid == 'none':
        return redirect('/listings')
    # View another users listings
    with messageQueue_data.mutex:
        messageQueue_data.queue.clear()  # flush the queue incase there is residual crap
    cmd_data = {"keyid": keyid, "id": id}
    task = queue_task(1, 'get_listings', cmd_data)
    messageQueue.put(task)
    # now, we wait...
    timer = 0
    while timer < 20:  # todo: this chunk of code is deeply crap - rewrite.
        listings_data = checkDataQ()
        if listings_data == 'none':
            listings_data = None  # an empty listing message has arrived, break and process it
            break
        elif listings_data:
            break  # a listing message has arrived, break and process it
        sleep(0.25)
        timer = timer + 0.25
    if not listings_data:
        return render_template('no_listing.html')
    if not id == 'none':
        # This is a specific listing response
        return render_template('listing.html', listing=listings_data, pgp_key=keyid)
    else:
        # This is a full listings response
        return render_template('listings.html', listings=listings_data, pgp_key=keyid)


@app.route('/cart', methods=["GET", "POST"])
@login_required
def cart(action=''):
    # todo calculate price here based on current exchange rates
    shopping_cart = defaultdict(defaultdict)  # lol...
    session = app.roStorageDB.DBSession()
    cart_items = session.query(app.roStorageDB.Cart).order_by(
        app.roStorageDB.Cart.seller_key_id.asc())
    if request.method == 'POST':
        action = request.form['action']
        if action == 'add':
            # New item in cart - add it to database along with default quantity & shipping options unless
            # quantuty and shipping were selected on the listings page TODO add
            # qty and shipping to listing page
            seller_key = request.form['pgpkey_id']
            item_id = request.form['listing_id']
            new_item = {"key_id": seller_key, "item_id": item_id}
            task = queue_task(1, 'add_to_cart', new_item)
            # todo - do this from bakend so that item naem can be included
            flash("Item added to cart", category="message")
        elif action == 'remove':
            # delete sellers items from cart - remove them from database
            print "Front end requesting to delete sellers items from cart"
            seller_key = request.form['pgpkey_id']
            del_seller = {"key_id": seller_key}
            task = queue_task(1, 'remove_from_cart', del_seller)
        elif action == 'update':
            # User is updating something in the cart - find out what and then update db
            # possible changes are Quantity or shipping
            # TODO: Each quanity and shipping form field must have a unique
            # name that can be tied to the orderid to deal with multiple items
            # from same seller
            seller_key = request.form['pgpkey_id']
            item_id = request.form['listing_id']
            quantity = request.form['quantity']
            shipping_option = request.form['shipping']
            cart_updates = {"key_id": seller_key, "item_id": item_id,
                            "quantity": quantity, "shipping": shipping_option}
            task = queue_task(1, 'update_cart', cart_updates)
        elif action == "checkout":
            # user is checking out their cart from a single seller
            seller_key = request.form['pgpkey_id']
            cart_checkout = {"key_id": seller_key}
            task = queue_task(1, 'checkout', cart_checkout)
            sleep(0.25)
            # return redirect(url_for('checkout'))
            render_template('not_yet.html')
        # Now send the relevant cart_update message to backend and await
        # response - then return page
        messageQueue.put(task)
        sleep(0.25)
        return redirect(url_for('cart'))
    # convert the results into a format usable by the cart page
    for cart_item in cart_items:
        cart_item.__dict__['item'] = json.loads(cart_item.__dict__['item'])
        shopping_cart[cart_item.seller_key_id][
            cart_item.id] = cart_item.__dict__
    checkEvents()
    return render_template('cart.html', shopping_cart=shopping_cart)

@app.route('/not_yet')
@login_required
def not_yet():
    return render_template('not_yet.html')

@app.route('/directory')
@app.route('/directory/<int:page>')
@login_required
def directory(page=1):
    checkEvents()
    session = app.roStorageDB.DBSession()
    directory = session.query(app.roStorageDB.cacheDirectory).order_by(
        app.roStorageDB.cacheDirectory.display_name.asc())
    page_results = SqlalchemyOrmPage(
        directory, page=page, items_per_page=pager_items * 2)
    return render_template('directory.html', directory=page_results)


@app.route('/listings')
@app.route('/listings/<int:page>')
@login_required
def listings(page=1):
    checkEvents()
    session = app.roStorageDB.DBSession()
    listings = session.query(app.roStorageDB.Listings)
    page_results = SqlalchemyOrmPage(
        listings, page=page, items_per_page=pager_items)
    return render_template('mylistings.html', listings=page_results)


@app.route('/profile/')
@app.route('/profile/<string:keyid>')
@login_required
def profile(keyid=None):
    checkEvents()
    # TODO:Check to see if this user is in our contacts list
    # TODO:Message to client_backend to SUB target user profile and target
    # user listings
    if keyid is None:
        keyid = app.pgp_keyid  # if no key specified by user then look up our own profile
#    task = queue_task(1,'get_profile',keyid)
#    messageQueue.put(task)
    # for now wait for the response for up to [timeout] seconds
    session = app.roStorageDB.DBSession()
    profile = session.query(app.roStorageDB.cacheProfiles).filter_by(
        key_id=keyid).first()
    if not profile:  # no existing profile found in cache, request it
        key = {"keyid": keyid}
        task = queue_task(1, 'get_profile', key)
        messageQueue.put(task)
        # now, we wait...
        timer = 0
        profile = session.query(app.roStorageDB.cacheProfiles).filter_by(
            key_id=keyid).first()
        while (not profile) and (timer < 20):  # 20 second timeout for profile lookups
            sleep(1)
            profile = session.query(app.roStorageDB.cacheProfiles).filter_by(
                key_id=keyid).first()
            timer = timer + 1
        if not profile:
            # TODO - pretty this up
            resp = make_response("Profile not found", 404)
            return resp
    else:  # we have returned an existing profile from the cache
        print "Existing entry found in profile cache..."
        # how old is the cached data
        age = get_age(profile.updated)
        if age > CACHE_EXPIRY_LIMIT:
            print 'Cached profile is too old, requesting latest copy'
            key = {"keyid": keyid}
            task = queue_task(1, 'get_profile', key)
            messageQueue.put(task)
            flash("Cached profile has expired, the latest profile has been requested in the background. Refresh the page.", category="message")

    return render_template('profile.html', profile=profile)


@app.route('/contacts')
@app.route('/contacts/<int:page>')
@login_required
def contacts(page=1):
    checkEvents()
    session = app.roStorageDB.DBSession()
    contacts = session.query(app.roStorageDB.Contacts)
    page_results = SqlalchemyOrmPage(
        contacts, page=page, items_per_page=pager_items)
    return render_template('contacts.html', contacts=page_results)


@app.route('/contacts/new/', methods=["GET", "POST"])
@login_required
def new_contact(contact_pgpkey=""):
    checkEvents()
    if request.method == "POST":
        # TODO: Validate these inputs
        # TODO: Don't store pgpkeyblock in contact, just store id and store
        # keyblock in the pgpkeycache table
        name = request.form['name']
        pgpkey = request.form['pgpkey_block']
        contact_pgpkey = request.form['pgpkey_id']
        if contact_pgpkey:  # We are adding by pgp key id
            contact = {"displayname": "" + name + "", "pgpkeyid": "" +
                       contact_pgpkey + "", "pgpkey": ""}  # TODO: add flags
            print contact
        else:           # We are adding by pgp key block
            contact = {"displayname": "" + name + "", "pgpkey": "" +
                       pgpkey + "", "pgpkeyid": ""}  # TODO: add flags
        task = queue_task(1, 'new_contact', contact)
        messageQueue.put(task)
        # it's better for the user to get a flashed message now rather than on
        # the next page load so
        sleep(0.1)
        # we will wait for 0.1 seconds here because usually this is long enough
        # to get the queue response back
        checkEvents()
        return redirect(url_for('contacts'))
    else:
        session = app.roStorageDB.DBSession()
        contacts = session.query(app.roStorageDB.Contacts).all()
        return render_template('contact-new.html', contacts=contacts, contact_pgpkey=contact_pgpkey)


@app.route('/messages')
@app.route('/messages/<int:page>')
@login_required
def messages(page=1):
    checkEvents()
    session = app.roStorageDB.DBSession()
#  inbox_messages = session.query(app.roStorageDB.PrivateMessaging).filter_by(recipient_key=app.pgp_keyid,message_direction="In").order_by(
#                  app.roStorageDB.PrivateMessaging.message_date.asc())
    inbox_messages = session.query(app.roStorageDB.PrivateMessaging).filter_by(recipient_key=app.pgp_keyid, message_direction="In").order_by(
        app.roStorageDB.PrivateMessaging.message_date.asc())
    page_results = SqlalchemyOrmPage(
        inbox_messages, page=page, items_per_page=pager_items)
    # inbox_messages)
    return render_template('messages.html', inbox_messages=page_results)


@app.route('/messages/sent')
@app.route('/messages/sent/<int:page>')
@login_required
def messages_sent(page=1):
    checkEvents()
    session = app.roStorageDB.DBSession()
    sent_messages = session.query(app.roStorageDB.PrivateMessaging).filter_by(sender_key=app.pgp_keyid, message_direction="Out").order_by(
        app.roStorageDB.PrivateMessaging.message_date.asc())
    page_results = SqlalchemyOrmPage(
        sent_messages, page=page, items_per_page=pager_items)
    return render_template('messages-sent.html', sent_messages=page_results)


@app.route('/messages/view/<string:id>/',)
@login_required
def view_message(id):
    session = app.roStorageDB.DBSession()
    message = session.query(
        app.roStorageDB.PrivateMessaging).filter_by(id=id).one()
    return render_template('message.html', message=message)


@app.route('/messages/reply/<string:id>/', methods=["GET", "POST"])
@login_required
def reply_message(id):
    checkEvents()
    if request.method == "POST":
        # TODO: Validate these inputs
        recipient = request.form['recipient']
        subject = request.form['subject']
        body = request.form['body']
        sign_msg = request.form['sign-message']
        message = {"recipient": recipient, "subject": subject, "body": body}
        task = queue_task(1, 'send_pm', message)
        messageQueue.put(task)
        # it's better for the user to get a flashed message now rather than on
        # the next page load so
        sleep(0.1)
        # we will wait for 0.1 seconds here because usually this is long enough
        # to get the queue response back
        checkEvents()
        return redirect(url_for('messages'))
    else:
        session = app.roStorageDB.DBSession()
        message = session.query(
            app.roStorageDB.PrivateMessaging).filter_by(id=id).one()
        return render_template('message-reply.html', message=message)


@app.route('/listings/new/', methods=["GET", "POST"])
@login_required
def new_listing(id=0):
    checkEvents()
    if request.method == "POST":
        # TODO: Validate these inputs
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        print category
        price = request.form['price']
        currency_code = request.form['currency']
        qty_available = request.form['quantity']
        max_order = request.form['max_order']
        if request.form.get('is_public') == 'True':
            is_public = 'True'
        else:
            is_public = 'False'
        if request.form.get('order_direct') == 'True':
            order_direct = 'True'
        else:
            order_direct = 'False'
        if request.form.get('order_escrow') == 'True':
            order_escrow = 'True'
        else:
            order_escrow = 'False'
        listing_image_file = request.files['listing_image']
        if listing_image_file and listing_image_file.filename.rsplit('.', 1)[1] in {'png', 'jpg'}:
            # TODO - maintain aspect ratio
            image = str(encode_image(listing_image_file.read(), (128, 128)))
        else:
            image = ''
        print "Checking shipping options..."
        # Now shipping options
        shipping = defaultdict()
        for x in range(1, 4):
            if request.form.get('shipping_enabled_' + str(x)) == 'True':
                s_type = request.form.get('shipping_' + str(x))
                s_cost = request.form.get('shipping_cost_' + str(x))
                if s_type and s_cost:
                    # TODO additional sanity checks on shipping options
                    shipping[x] = (s_type, s_cost)

        # crete message for backend
        message = {"category": category, "title": title, "description": description, "price": price, "currency": currency_code, "image": image, "is_public": is_public,
                   "quantity": qty_available, "max_order": max_order, "order_direct": order_direct, "order_escrow": order_escrow, "shipping_options": json.dumps(shipping)}
        print message
        task = queue_task(1, 'new_listing', message)
        messageQueue.put(task)
        # it's better for the user to get a flashed message now rather than on
        # the next page load so
        sleep(0.1)
        # we will wait for 0.1 seconds here because usually this is long enough
        # to get the queue response back
        checkEvents()
        return redirect(url_for('listings'))
    else:
        session = app.roStorageDB.DBSession()
        # session.query(app.roStorageDB.Contacts).all() # TODO: Query list of
        # categories currently known
        categories = None
        currencies = session.query(app.roStorageDB.currencies).all()
        return render_template('listing-new.html', categories=categories, currencies=currencies)


@app.route('/listings/edit/<int:id>', methods=["GET", "POST"])
@login_required
def edit_listing(id=0):
    checkEvents()
    if request.method == "POST":
        # TODO: Validate these inputs
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        print category
        price = request.form['price']
        currency_code = request.form['currency']
        qty_available = request.form['quantity']
        max_order = request.form['max_order']
        if request.form.get('is_public') == 'True':
            is_public = 'True'
        else:
            is_public = 'False'
        if request.form.get('order_direct') == 'True':
            order_direct = 'True'
        else:
            order_direct = 'False'
        if request.form.get('order_escrow') == 'True':
            order_escrow = 'True'
        else:
            order_escrow = 'False'
        listing_image_file = request.files['listing_image']
        if listing_image_file and listing_image_file.filename.rsplit('.', 1)[1] in {'png', 'jpg'}:
            # TODO - maintain aspect ratio
            image = str(encode_image(listing_image_file.read(), (128, 128)))
        else:
            image = ''

        print "Checking shipping options..."
        # Now shipping options
        shipping = defaultdict()
        for x in range(1, 4):
            if request.form.get('shipping_enabled_' + str(x)) == 'True':
                s_type = request.form.get('shipping_' + str(x))
                s_cost = request.form.get('shipping_cost_' + str(x))
                if s_type and s_cost:
                    # TODO additional sanity checks on shipping options
                    shipping[x] = (s_type, s_cost)

        message = {"id": id, "category": category, "title": title, "description": description, "price": price, "currency": currency_code, "image": image, "is_public": is_public,
                   "quantity": qty_available, "max_order": max_order, "order_direct": order_direct, "order_escrow": order_escrow, "shipping_options": json.dumps(shipping)}
        print "Update Listing message: " + message.__str__()
        task = queue_task(1, 'update_listing', message)
        messageQueue.put(task)
        # it's better for the user to get a flashed message now rather than on
        # the next page load so
        sleep(0.1)
        # we will wait for 0.1 seconds here because usually this is long enough
        # to get the queue response back
        checkEvents()
        return redirect(url_for('listings'))
    else:
        session = app.roStorageDB.DBSession()
        # session.query(app.roStorageDB.Contacts).all() # TODO: Query list of
        # categories currently known
        categories = None
        currencies = session.query(app.roStorageDB.currencies).all()
        listing_item = session.query(
            app.roStorageDB.Listings).filter_by(id=id).first()
        listing_shipping_options = json.loads(listing_item.shipping_options)
        return render_template('listing-edit.html', categories=categories, currencies=currencies, listing=listing_item, shipping_options=listing_shipping_options)


@app.route('/listings/delete/<int:id>', methods=["GET"])
@login_required
def delete_listing(id=0):
    message = {"id": str(id)}
    task = queue_task(1, 'delete_listing', message)
    messageQueue.put(task)
    # it's better for the user to get a flashed message now rather than on the
    # next page load so
    sleep(0.1)
    # we will wait for 0.1 seconds here because usually this is long enough to
    # get the queue response back
    checkEvents()
    return redirect(url_for('listings'))


@app.route('/messages/new/', methods=["GET", "POST"])
# TODO CSRF protection required
@app.route('/messages/new/<string:recipient_key>', methods=["GET", "POST"])
@login_required
def new_message(recipient_key=""):
    checkEvents()
    if request.method == "POST":
        # TODO: Validate these inputs
        recipient = request.form['recipient']
        subject = request.form['subject']
        body = request.form['body']
        sign_msg = request.form['sign-message']
        message = {"recipient": recipient, "subject": subject, "body": body}
        task = queue_task(1, 'send_pm', message)
        messageQueue.put(task)
        # it's better for the user to get a flashed message now rather than on
        # the next page load so
        sleep(0.1)
        # we will wait for 0.1 seconds here because usually this is long enough
        # to get the queue response back
        checkEvents()
        return redirect(url_for('messages'))
    else:
        session = app.roStorageDB.DBSession()
        contacts = session.query(app.roStorageDB.Contacts).all()
        return render_template('message-compose.html', contacts=contacts, recipient_key=recipient_key)


@app.route('/messages/delete/<string:id>/',)    # TODO CSRF protection required
@login_required
def delete_message(id):
    message = {"id": "" + id + ""}
    task = queue_task(1, 'delete_pm', message)
    messageQueue.put(task)
    # it's better for the user to get a flashed message now rather than on the
    # next page load so
    sleep(0.1)
    # we will wait for 0.1 seconds here because usually this is long enough to
    # get the queue response back
    checkEvents()
    return redirect(url_for('messages'))


@app.route('/load-identity', methods=['POST'])
# load existing app data from a non-default location
def loadidentity():
    if app.SetupDone:
        return redirect(url_for('home'))
    app.appdir = dirname(request.form['app_dir'])  # strip off the file-name
    print app.appdir
    if isfile(app.appdir + "/secret") and isfile(app.appdir + "/storage.db"):
        app.SetupDone = True  # TODO: A better check is needed here
    else:
        flash("Could not load application data from " +
              app.appdir, category="error")
    return redirect(url_for('login'))


@app.route('/create-identity', methods=['POST'])
def createidentity():                                               # This is a bit of a mess, TODO: clean up
    if app.SetupDone:
        return redirect(url_for('home'))
    app.pgp_keyid = request.form['keyid']
    app.display_name = request.form['displayname']
    app.pgp_passphrase = request.form['pgppassphrase']
    # Now attempt to create our application data directory if it doesn't exist
    if not isdir(app.appdir):
        try:
            makedirs(app.appdir, mode=0700)
        except:
            flash("Error creating identity - client folder not created",
                  category="error")
            return redirect(url_for('install'))
    app.dbsecretkey = ''.join(random.SystemRandom().choice(
        string.digits) for _ in range(128))
    # Now create our empty pgp keyring it it does not exist in our app data dir
    if not isfile(app.appdir + '/pubkeys.gpg'):
        try:
            file = open(app.appdir + '/pubkeys.gpg', 'w')
            file.close()
        except:
            flash("Error creating public keyring", category="error")
            return redirect(url_for('install'))
    # Now create or overwrite the secret db key file in the app data dir
    try:
        file = open(app.appdir + '/secret', 'w')
        encrypted_dbsecretkey = app.gpg.encrypt(app.dbsecretkey, app.pgp_keyid)
        file.write(str(encrypted_dbsecretkey))
        file.close()
        app.SetupDone = True
    except:
        flash("Error creating identity - secret file not created", category="error")
        return redirect(url_for('install'))
    # Now generate initial Bitcoin keys
    wordlist_path = resource_path('words.txt')
    # todo: ensure wordcount reflects size of wordlist
    wallet_seed = generate_seed(wordlist_path, words=18)
    # Our published stealth address will be derived from a child key (index 1) which will be generated on the fly
    # Now create & populate DB with initial values
    installStorageDB = Storage(app.dbsecretkey, 'storage.db', app.appdir)
    if not installStorageDB.Start():
        flash('There was a problem creating the storage database ' +
              'storage.db', category="error")
    session = installStorageDB.DBSession()
    # Now populate the config database with defaults + user specified data
    # TODO: take account of user selection when setting publish_id
    defaults = create_defaults(
        installStorageDB, session, app.pgp_keyid, app.display_name, app.publish_id, wallet_seed)
    if not defaults:
        flash('There was a problem creating the initial configuration in the storage database ' +
              'storage.db', category="error")
        # return False
    session.commit()
    sleep(1)  # TODO find cause of socks_enabled.value being None and causing failed install - for now add delay
    # Now set the proxy settings specified on the install page
    socks_proxy = session.query(app.roStorageDB.Config).filter(
        app.roStorageDB.Config.name == "proxy").first()
    socks_proxy_port = session.query(app.roStorageDB.Config).filter(
        app.roStorageDB.Config.name == "proxy_port").first()
    i2p_socks_proxy = session.query(app.roStorageDB.Config).filter(
        app.roStorageDB.Config.name == "i2p_proxy").first()
    i2p_socks_proxy_port = session.query(app.roStorageDB.Config).filter(
        app.roStorageDB.Config.name == "i2p_proxy_port").first()
    socks_enabled = session.query(app.roStorageDB.Config).filter(
        app.roStorageDB.Config.name == "socks_enabled").first()
    i2p_socks_enabled = session.query(app.roStorageDB.Config).filter(
        app.roStorageDB.Config.name == "i2p_socks_enabled").first()
    if request.form.get('enable_socks') == 'True':
        socks_enabled.value = 'True'
    else:
        socks_enabled.value = 'False'
    socks_proxy.value = request.form['proxy']
    socks_proxy_port.value = request.form['proxy_port']
    if request.form.get('i2p_enable_socks') == 'True':
        i2p_socks_enabled.value = 'True'
    else:
        i2p_socks_enabled.value = 'False'
    i2p_socks_proxy.value = request.form['i2p_proxy']
    i2p_socks_proxy_port.value = request.form['i2p_proxy_port']
    session.commit()
    session.close()
    installStorageDB.Stop()
    return redirect(url_for('setup'))


@app.route('/install')
def install():
    if app.SetupDone:
        return redirect(url_for('home'))
    private_keys = app.gpg.list_keys(True)  # True => private keys
    if not private_keys:
        # It looks like there is no private pgpkey - offer to create one for
        # user
        return render_template('new_pgp_key.html')
    return render_template('install.html', key_list=private_keys)


@app.route('/create_pgpkey', methods=["POST"])
def create_pgpkey():
    if app.SetupDone:
        return redirect(url_for('home'))
    # now try to create key
    key_type = "RSA"
    key_length = 4096
    name_real = request.form['displayname']
    name_comment = ""
    name_email = request.form['email']
    passphrase = request.form['pgppassphrase']
    passphrase2 = request.form['pgppassphrase2']
    if passphrase <> passphrase2:
        flash('Passphrases did not match, try again', 'error')
        return render_template('new_pgp_key.html')
    input_data = app.gpg.gen_key_input(key_type=key_type, key_length=key_length, name_real=name_real,
                                       name_comment=name_comment, name_email=name_email, passphrase=passphrase)
    app.gpg.gen_key(input_data)
    # if successful we can now contineu to intall
    private_keys = app.gpg.list_keys(True)  # True => private keys
    if not private_keys:
        # It looks like there is still no private pgpkey - offer to create one
        # for user
        return render_template('new_pgp_key.html')
    return render_template('install.html', key_list=private_keys)


@app.route('/setup', methods=["GET", "POST"])
@app.route('/setup/<string:page>', methods=["GET", "POST"])
@login_required
def setup(page=''):
    checkEvents()
    if request.method == "POST":
        # These are updates to the config - these should be sent to the client queue but for now allow a db update from here
        #  CHeck and apply new settings
        session = app.roStorageDB.DBSession()
        displayname = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "displayname").first()
        profile = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "profile").first()
        avatar_image = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "avatar_image").first()
        hubnodes = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "hubnodes").all()
        notaries = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "notaries").all()
        socks_proxy = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "proxy").first()
        socks_proxy_port = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "proxy_port").first()
        i2p_socks_proxy = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "i2p_proxy").first()
        i2p_socks_proxy_port = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "i2p_proxy_port").first()
        socks_enabled = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "socks_enabled").first()
        i2p_socks_enabled = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "i2p_socks_enabled").first()
        message_retention = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "message_retention").first()
        accept_unsigned = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "accept_unsigned").first()
        wallet_seed = session.query(app.roStorageDB.Config).filter(
            app.roStorageDB.Config.name == "wallet_seed").first()
        #
        if page == "identity":
            if displayname:
                displayname.value = request.form['displayname']
            avatar_image_file = request.files['avatar_image']
            if avatar_image_file and avatar_image_file.filename.rsplit('.', 1)[1] in {'png', 'jpg'}:
                if not avatar_image:
                    new_conf_item = app.roStorageDB.Config(name="avatar_image")
                    # TODO - maintain aspect ratio
                    new_conf_item.value = str(encode_image(
                        avatar_image_file.read(), (128, 128)))
                    new_conf_item.displayname = "Avatar Image"
                    session.add(new_conf_item)
                else:
                    avatar_image.value = encode_image(
                        avatar_image_file.read(), (128, 128))  # TODO - maintain aspect ratio
                    # print encode_image(avatar_image_file.read(),(128,128))
            if profile:
                profile.value = request.form['profile']
            else:
                new_conf_item = app.roStorageDB.Config(name="profile")
                new_conf_item.value = str(request.form['profile'])
                new_conf_item.displayname = "Public Profile"
                session.add(new_conf_item)
        elif page == "network":
            if request.form.get('enable_socks') == 'True':
                socks_enabled.value = 'True'
            else:
                socks_enabled.value = 'False'
            socks_proxy.value = request.form['proxy']
            socks_proxy_port.value = request.form['proxy_port']
            if request.form.get('i2p_enable_socks') == 'True':
                i2p_socks_enabled.value = 'True'
            else:
                i2p_socks_enabled.value = 'False'
            i2p_socks_proxy.value = request.form['i2p_proxy']
            i2p_socks_proxy_port.value = request.form['i2p_proxy_port']
            new_hubnodes = str(request.form['hubnodes']).splitlines()
            session.query(app.roStorageDB.Config.value).filter(
                app.roStorageDB.Config.name == "hubnodes").delete()
            for node in new_hubnodes:
                new_conf_item = app.roStorageDB.Config(name="hubnodes")
                new_conf_item.value = node
                new_conf_item.displayname = "Entry Points"
                session.add(new_conf_item)
        elif page == "security":
            message_retention.value = request.form['message_retention']
            if request.form.get('allow_unsigned') == 'True':
                accept_unsigned.value = 'True'
            else:
                accept_unsigned.value = 'False'
        elif page == "bitcoin":
            wallet_seed = request.form['seed']
            new_stratum_servers = str(
                request.form['stratum_servers']).splitlines()
            session.query(app.roStorageDB.Config.value).filter(
                app.roStorageDB.Config.name == "stratum_servers").delete()
            for node in new_stratum_servers:
                new_conf_item = app.roStorageDB.Config(name="stratum_servers")
                new_conf_item.value = node
                new_conf_item.displayname = "Stratum Servers"
                session.add(new_conf_item)
        try:
            session.commit()
        except:
            session.rollback()
            flash(
                "There was a problem saving the updated configuration. Nothing has been saved", category="error")
            return redirect(url_for('setup'))
        finally:
            session.close()
            flash("Configuration updated", category="message")
            return redirect(url_for('setup'))
    else:
        # First read config from the database
        session = app.roStorageDB.DBSession()
        pgpkeyid = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "pgpkeyid").first()
        displayname = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "displayname").first()
        profile = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "profile").first()
        avatar = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "avatar_image").first()
        hubnodes = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "hubnodes").all()
        notaries = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "notaries").all()
        socks_proxy = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "proxy").first()
        socks_proxy_port = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "proxy_port").first()
        i2p_socks_proxy = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "i2p_proxy").first()
        i2p_socks_proxy_port = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "i2p_proxy_port").first()
        socks_enabled = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "socks_enabled").first()
        i2p_socks_enabled = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "i2p_socks_enabled").first()
        message_retention = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "message_retention").first()
        accept_unsigned = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "accept_unsigned").first()
        wallet_seed = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "wallet_seed").first()
        stratum_servers = session.query(app.roStorageDB.Config.value).filter(
            app.roStorageDB.Config.name == "stratum_servers").all()
        session.close()
        if page == '':
            return render_template('setup.html', displayname=displayname, pgpkeyid=pgpkeyid, hubnodes=hubnodes, notaries=notaries)
        elif page == 'identity':
            return render_template('setup-identity.html', displayname=displayname, pgpkeyid=pgpkeyid, profile=profile, avatar=avatar)
        elif page == 'network':
            return render_template('setup-network.html', proxy=socks_proxy, proxy_port=socks_proxy_port, i2p_proxy=i2p_socks_proxy, i2p_proxy_port=i2p_socks_proxy_port, hubnodes=hubnodes, socks_enabled=socks_enabled, i2p_socks_enabled=i2p_socks_enabled)
        elif page == 'security':
            return render_template('setup-security.html', message_retention=message_retention, accept_unsigned=accept_unsigned.value)
        elif page == 'trading':
            return render_template('setup-trading.html', notaries=notaries)
        elif page == 'bitcoin':
            return render_template('setup-bitcoin.html', wallet_seed=wallet_seed, stratum_servers=stratum_servers)


@app.route('/about')
@login_required
def about():
    checkEvents()
    return render_template('about.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    # disconnect network
    # flush pgp passphrase
    app.pgp_passphrase = ""
    app.pgp_keyid = ""
    # Disconnect database
    app.roStorageDB.Stop()
    task = queue_task(1, 'shutdown', None)
    messageQueue.put(task)
    # any other cleanup (touch files?)
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if not app.SetupDone:
        return redirect(url_for('install'))
    private_keys = app.gpg.list_keys(True)  # True => private keys
    if request.method == "POST":
        # check that secret can be decrypted
        try:
            stream = open(app.appdir + "/secret", "rb")
        except:
            flash('There was a problem opening the secret file', category="error")
            return render_template('login.html', key_list=private_keys)
        app.pgp_keyid = request.form['keyid']
        app.pgp_passphrase = request.form['pgppassphrase']
        if request.form.get('offline') == 'yes':
            app.workoffline = True
        else:
            app.workoffline = False
        decrypted_data = app.gpg.decrypt_file(
            stream, False, app.pgp_passphrase)
        if not str(decrypted_data):
            flash('Your passphrase or PGP key is not correct', category="error")
            return render_template('login.html', key_list=private_keys)
        app.dbsecretkey = str(decrypted_data)
        app.roStorageDB = Storage(app.dbsecretkey, "storage.db", app.appdir)
        if not app.roStorageDB.Start():
            flash(
                'You were authenticated however there is a problem with the storage database', category="error")
            return render_template('login.html', key_list=private_keys)
        user = User.get(app.pgp_keyid)
        login_user(user)
        if app.connection_status == "Off-line":
            messageThread = messaging_loop(app.pgp_keyid, app.pgp_passphrase, app.dbsecretkey, "storage.db", app.homedir,
                                           app.appdir, messageQueue, messageQueue_res, messageQueue_data, workoffline=app.workoffline)
            messageThread.start()
            # it's better for the user to get a flashed message now rather than
            # on the next page load so
            sleep(0.1)
            checkEvents()
        return render_template('home.html')
    else:
        return render_template('login.html', key_list=private_keys)

# Minimalist PGP keyserver implementation (no auth required)
# TODO: Move this whole function to client_backend and run as a small
# thread with a listener on a dedicated port


@app.route('/pks/lookup')
def pks_lookup():
    if not app.pgp_keyid:
        resp = make_response("Key server not available", 404)
        resp.headers.extend({'X-HKP-Results-Count': '0'})
        return resp
    search_key = request.args.get('search', '')
    if not search_key:
        resp = make_response("Key ID not provided", 404)
        resp.headers.extend({'X-HKP-Results-Count': '0'})
        return resp
    # if the provided keyid starts with 0x
    search_key_split = search_key.split('x')
    if len(search_key_split) == 2:
        search_key = search_key_split[1]  # strip 0x
    # Query local key cache database for the key - we will request from the
    # broker if we don't have it
    print "PKS Lookup for " + search_key
    session = app.roStorageDB.DBSession()
    key_block = session.query(app.roStorageDB.cachePGPKeys).filter_by(
        key_id=search_key).first()
    if not key_block:
        key = {"keyid": "" + search_key + ""}
        print "Keyblock not found in db, sending query key msg"
        task = queue_task(1, 'get_key', key)
        messageQueue.put(task)
        print "Sent message requesting key..."
        # now, we wait...
        sleep(0.1)
        timer = 0
        key_block = session.query(app.roStorageDB.cachePGPKeys).filter_by(
            key_id=search_key).first()
        while (not key_block) and (timer < 20):  # 20 second timeout for key lookups
            sleep(1)
            checkEvents()
            key_block = session.query(app.roStorageDB.cachePGPKeys).filter_by(
                key_id=search_key).first()
            timer = timer + 1
        if not key_block:
            resp = make_response("Key not found", 404)
            resp.headers.extend({'X-HKP-Results-Count': '0'})
            return resp
    resp = make_response(key_block.keyblock, 200)  # for now return our key
    # we will only ever return a single key
    resp.headers.extend({'X-HKP-Results-Count': '1'})
    return resp


def checkEvents():
    if messageQueue_res.empty():
        return(False)
    while not messageQueue_res.empty():
        results = messageQueue_res.get()
        # TODO: check results is set to a valid queue_task object here
        if not type(results) == queue_task:
            flash("Unknown data received from client thread results queue",
                  category="error")
            return(True)
        if results.command == 'flash_message':
            flash(results.data, category="message")
        elif results.command == 'flash_error':
            flash(results.data, category="error")
        elif results.command == 'flash_status':
            app.connection_status = results.data
        elif results.command == 'resolved_key':
            print "Backend resolved a key for front end " + results.data['keyid']
            app.pgpkeycache[results.data['keyid']] = results.data[
                'key_block']  # add this key to the keycache
        else:
            flash(
                "Unknown command received from client thread results queue", category="error")
    return(True)


def checkDataQ():
    if messageQueue_data.empty():
        return(False)
    while not messageQueue_data.empty():
        results = messageQueue_data.get()
        # TODO: check results is set to a valid queue_task object here
        return results


def client_shutdown(sender, **extra):
    print "Client_Shutdown called....exiting"


def run():
    app.storageThreadID = ""
    app.pgpkeycache = {}
    app.dbsecretkey = ""
    app.workoffline = False
    app.secret_key = ''.join(random.SystemRandom().choice(
        string.ascii_uppercase + string.digits) for _ in range(16))
    app.jinja_env.globals['csrf_token'] = generate_csrf_token
    print 'Translate paths for Flask if running from binary (onefile)'
    print 'before:' + app.template_folder
    app.template_folder = resource_path('templates')
    app.static_folder = resource_path('static')
    print 'after:' + app.template_folder
    app.SetupDone = False
    app.pgp_keyid = ""
    # path of the module/executable - should work for both source and binary
    app.bin_path = dirname(sys.argv[0])
    app.publish_id = True
    app.roStorageDB = Storage
    app.display_name = ""
    app.pgp_passphrase = ""
    app.homedir = expanduser("~")
    if get_os() == 'Windows':
        # This is the default appdir location
        app.appdir = app.homedir + '\\application data\\.dnmng'
        app.gpg = gnupg.GPG(gnupghome=app.homedir + '/application data/gnupg', options={
                            '--throw-keyids', '--no-emit-version', '--trust-model=always'})  # we want to encrypt the secret with throw keys
    else:
        app.appdir = app.homedir + '/.dnmng'  # This is the default appdir location
        # we want to encrypt the secret with throw keys
        app.gpg = gnupg.GPG(gnupghome=app.homedir + '/.gnupg', options={
                            '--throw-keyids', '--no-emit-version', '--trust-model=always'})
    app.connection_status = "Off-line"
    app.current_broker = None
    app.current_broker_users = None
    if isfile(app.appdir + "/secret") and isfile(app.appdir + "/storage.db"):
        app.SetupDone = True  # TODO: A better check is needed here
    # TODO: turn off threading - either move PKS lookup handler to backend
    # thread or inject retreived keys directly into keyring
    app.run(debug=True, threaded=True, use_reloader=False)
 # use_reloader added to prevent initialization running twice when in flask
 # debug mode


# Windows doess not support fork so we need to extend Multiprocessing on
# Windows

class _Popen(multiprocessing.forking.Popen):

    def __init__(self, *args, **kw):
        if hasattr(sys, 'frozen'):
            # We have to set original _MEIPASS2 value from sys._MEIPASS
            # to get --onefile mode working.
            # Last character is stripped in C-loader. We have to add
            # '/' or '\\' at the end.
            os.putenv('_MEIPASS2', sys._MEIPASS + sep)
        try:
            super(_Popen, self).__init__(*args, **kw)
        finally:
            if hasattr(sys, 'frozen'):
                # On some platforms (e.g. AIX) 'os.unsetenv()' is not
                # available. In those cases we cannot delete the variable
                # but only set it to the empty string. The bootloader
                # can handle this case.
                if hasattr(os, 'unsetenv'):
                    unsetenv('_MEIPASS2')
                else:
                    putenv('_MEIPASS2', '')


class Process(multiprocessing.Process):
    _Popen = _Popen


class SendeventProcess(Process):

    def __init__(self, resultQueue):
        self.resultQueue = resultQueue

        multiprocessing.Process.__init__(self)
        self.start()

    def run(self):
        print 'SendeventProcess'
        self.resultQueue.put((1, 2))
        print 'SendeventProcess'


if __name__ == '__main__':
    if get_os() == 'Windows':
        freeze_support()

    print """
 AA  X   X III  SSS   M   M U   U N   N DDD  III
A  A  X X   I  S      MM MM U   U NN  N D  D  I
AAAA   X    I   SSS   M M M U   U N N N D  D  I
A  A  X X   I      S  M   M U   U N  NN D  D  I
A  A X   X III SSSS   M   M  UUU  N   N DDD  III
    """
    print "Version " + VERSION + " starting up..."

    running = True
    option_nogui = False
    option_nobrowser = False
    # By default try to start the status gui in the system tray
    if not option_nogui:
        try:
            gui = wx.App()
            frame = wx.Frame(None)  # empty frame
            trayicon_gui.TaskBarIcon()
        except:  # If that fails assume nogui mode
            print "No display detected, disabling status gui"
            option_nogui = True
            option_nobrowser = True
    # Start the front end thread of the client
    front_end = Process(target=run)
    front_end.start()
    print "Axis Mundi local web-server now accessible on http://127.0.0.1:5000"
    if not option_nobrowser:
        webbrowser.open_new_tab('http://127.0.0.1:5000/')
    # main loop
    while running:
        try:
            if option_nogui:
                sleep(0.5)
            else:
                gui.MainLoop()
                running = False
        except KeyboardInterrupt:
            break
    print "Axis Mundi shutting down..."
    # TODO : give frontend and backend (if running) a chance to close down
    # gracefully
    front_end.terminate()
    front_end.join()
    if not option_nogui:
        gui.Exit()
    # TODO - overwrite and then delete temp pubkeyring if used
    print "Axis Mundi exiting..."
