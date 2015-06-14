#!/usr/bin/env python

from flask import Flask, render_template, request, redirect, url_for, abort, session, flash, g, make_response
from flask_login import LoginManager,UserMixin,login_user,current_user,logout_user,login_required
import gnupg
from os.path import expanduser, isfile, isdir, dirname
from os import makedirs
import string
import random
from storage import Storage, SqlalchemyOrmPage
from client_backend import messaging_loop
import Queue
from utilities import queue_task,encode_image
from defaults import create_defaults
from time import sleep
import base64
from platform import system as get_os

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024 # (8Mb maximum upload to local webserver) - make sure we dont need to use the disk
messageQueue = Queue.Queue()    # work Queue for mqtt client thread
messageQueue_res = Queue.Queue()    # Results Queue for mqtt client thread
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)
pager_items = 12 # default of 12 items per page when paginating

class User(UserMixin):
    def __init__(self, id):
        self.id = id
    @classmethod
    def get(self_class, id):
        try:
            return self_class(id)
        except:
            return None # This should not happen

@login_manager.user_loader
def load_user(userid):
    return User.get(userid)

########## CSRF protection ###############################
@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.pop('_csrf_token', None)
        if not token or token != request.form.get('_csrf_token'):
            flash('Invalid CSRF token, please try again.',category="error")
            redirect(request.endpoint,302) # FIXME: This is not doing what it should

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(16))
    return session['_csrf_token']

######## STATUS, PAGE GLOBALS AND UPDATES ##########################################
@app.before_request
def get_connection_status():
    checkEvents()
    g.connection_status = app.connection_status

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
def orders(view_type='buying',page=1):
  checkEvents()
  session = app.roStorageDB.DBSession()
  page_results=None
  if view_type == 'buying':
      orders_buying = session.query(app.roStorageDB.Orders).filter_by(buyer_key=app.pgp_keyid).order_by(
                      app.roStorageDB.Orders.order_date.asc())
      page_results = SqlalchemyOrmPage(orders_buying, page=page, items_per_page=pager_items)
  elif view_type == 'selling':
      orders_selling = session.query(app.roStorageDB.Orders).filter_by(seller_key=app.pgp_keyid).order_by(
                      app.roStorageDB.Orders.order_date.asc())
      page_results = SqlalchemyOrmPage(orders_selling, page=page, items_per_page=pager_items)
  return render_template('orders.html',orders=page_results, view=view_type)


@app.route('/listings/view/<string:keyid>')
@app.route('/listings/view/<string:keyid>/<int:page>')
def xlistings(keyid=None,page=1):
    if keyid is None:
        return redirect('/listings')
    # View anther users listings
    session = app.roStorageDB.DBSession()
    listings = session.query(app.roStorageDB.cacheListings).filter_by(key_id=keyid).first()
    if not listings:
        key={"keyid":keyid}
        task = queue_task(1,'get_listings',key)
        messageQueue.put(task)
        # now, we wait...
        timer = 0
        listings = session.query(app.roStorageDB.cacheListings).filter_by(key_id=keyid).first()
        while (not listings) and (timer < 20): # 20 second timeout for listings lookups
            sleep (1)
            profile = session.query(app.roStorageDB.cacheListings).filter_by(key_id=keyid).first()
            timer = timer + 1
        if not listings:
            resp = make_response("Listings not found", 404) # TODO - pretty this up
            return resp
    else: # we have returned an existing setof listings from the cache
        print "Existing entry found in listings cache..." # Todo : deal with updating listings by sending background get_listings
    return render_template('listings.html',listings=listings)


@app.route('/listings')
@app.route('/listings/<int:page>')
@login_required
def listings(page=1):
  checkEvents()
  session = app.roStorageDB.DBSession()
  listings = session.query(app.roStorageDB.Listings)
  page_results = SqlalchemyOrmPage(listings, page=page, items_per_page=pager_items)
  return render_template('mylistings.html', listings=page_results)

@app.route('/profile/')
@app.route('/profile/<string:keyid>')
@login_required
def profile(keyid=None):
    checkEvents()
    # TODO:Implement caching for (previously viewed) profiles in the local database
    # TODO:Check to see if this user is in our contacts list
    # TODO:Message to client_backend to SUB target user profile and target user listings
    if keyid is None:
      keyid = app.pgp_keyid # if no key specified by user then look up our own profile
#    task = queue_task(1,'get_profile',keyid)
#    messageQueue.put(task)
    # TODO: show the cached page so the user doesn't have to wait for the response
    # for now wait for the response for up to [timeout] seconds
    session = app.roStorageDB.DBSession()
    profile = session.query(app.roStorageDB.cacheProfiles).filter_by(key_id=keyid).first()
    if not profile:
        key={"keyid":keyid}
        task = queue_task(1,'get_profile',key)
        messageQueue.put(task)
        # now, we wait...
        timer = 0
        profile = session.query(app.roStorageDB.cacheProfiles).filter_by(key_id=keyid).first()
        while (not profile) and (timer < 20): # 20 second timeout for profile lookups
            sleep (1)
            profile = session.query(app.roStorageDB.cacheProfiles).filter_by(key_id=keyid).first()
            timer = timer + 1
        if not profile:
            resp = make_response("Profile not found", 404) # TODO - pretty this up
            return resp
    else: # we have returned an existing profile from the cache
        print "Existing entry found in profile cache..." # Todo : deal with updating profile by sending background get_profile
    return render_template('profile.html',profile=profile)

@app.route('/contacts')
@app.route('/contacts/<int:page>')
@login_required
def contacts(page=1):
  checkEvents()
  session = app.roStorageDB.DBSession()
  contacts = session.query(app.roStorageDB.Contacts)
  page_results = SqlalchemyOrmPage(contacts, page=page, items_per_page=pager_items)
  return render_template('contacts.html', contacts=page_results)

@app.route('/contacts/new/',methods=["GET","POST"])
@login_required
def new_contact(contact_pgpkey=""):
    checkEvents()
    if request.method == "POST":
        # TODO: Validate these inputs
        # TODO: Don't store pgpkeyblock in contact, just store id and store keyblock in the pgpkeycache table
        name = request.form['name']
        pgpkey = request.form['pgpkey_block']
        contact_pgpkey =request.form['pgpkey_id']
        if contact_pgpkey: # We are adding by pgp key id
            contact={"displayname":"" + name + "","pgpkeyid":"" + contact_pgpkey + "","pgpkey":""} # TODO: add flags
            print contact
        else:           # We are adding by pgp key block
            contact={"displayname":"" + name + "","pgpkey":"" + pgpkey + "","pgpkeyid":""} # TODO: add flags
        task = queue_task(1,'new_contact',contact)
        messageQueue.put(task)
        sleep(0.1)  # it's better for the user to get a flashed message now rather than on the next page load so
                    # we will wait for 0.1 seconds here because usually this is long enough to get the queue response back
        checkEvents()
        return redirect(url_for('contacts'))
    else:
        session = app.roStorageDB.DBSession()
        contacts = session.query(app.roStorageDB.Contacts).all()
        return render_template('contact-new.html',contacts=contacts, contact_pgpkey=contact_pgpkey)

@app.route('/messages')
@app.route('/messages/<int:page>')
@login_required
def messages(page=1):
  checkEvents()
  session = app.roStorageDB.DBSession()
#  inbox_messages = session.query(app.roStorageDB.PrivateMessaging).filter_by(recipient_key=app.pgp_keyid,message_direction="In").order_by(
#                  app.roStorageDB.PrivateMessaging.message_date.asc())
  inbox_messages = session.query(app.roStorageDB.PrivateMessaging).filter_by(recipient_key=app.pgp_keyid,message_direction="In").order_by(
                  app.roStorageDB.PrivateMessaging.message_date.asc())
  page_results = SqlalchemyOrmPage(inbox_messages, page=page, items_per_page=pager_items)
  return render_template('messages.html', inbox_messages=page_results) #inbox_messages)

@app.route('/messages/sent')
@app.route('/messages/sent/<int:page>')
@login_required
def messages_sent(page=1):
  checkEvents()
  session = app.roStorageDB.DBSession()
  sent_messages = session.query(app.roStorageDB.PrivateMessaging).filter_by(sender_key=app.pgp_keyid,message_direction="Out").order_by(
                  app.roStorageDB.PrivateMessaging.message_date.asc())
  page_results = SqlalchemyOrmPage(sent_messages, page=page, items_per_page=pager_items)
  return render_template('messages-sent.html', sent_messages=page_results)

@app.route('/messages/view/<string:id>/',)
@login_required
def view_message(id):
    session = app.roStorageDB.DBSession()
    message = session.query(app.roStorageDB.PrivateMessaging).filter_by(id=id).one()
    return render_template('message.html',message=message)

@app.route('/messages/reply/<string:id>/',methods=["GET","POST"])
@login_required
def reply_message(id):
    checkEvents()
    if request.method == "POST":
        # TODO: Validate these inputs
        recipient = request.form['recipient']
        subject = request.form['subject']
        body = request.form['body']
        sign_msg = request.form['sign-message']
        message={"recipient":recipient,"subject":subject,"body":body}
        task = queue_task(1,'send_pm',message)
        messageQueue.put(task)
        sleep(0.1)  # it's better for the user to get a flashed message now rather than on the next page load so
                    # we will wait for 0.1 seconds here because usually this is long enough to get the queue response back
        checkEvents()
        return redirect(url_for('messages'))
    else:
        session = app.roStorageDB.DBSession()
        message = session.query(app.roStorageDB.PrivateMessaging).filter_by(id=id).one()
        return render_template('message-reply.html',message=message)


@app.route('/listings/new/',methods=["GET","POST"])
@login_required
def new_listing():
    checkEvents()
    if request.method == "POST":
        # TODO: Validate these inputs
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        currency_code = request.form['currency']
        qty_available = request.form['quantity']
        order_max_qty = request.form['max_order']
        listing_image_file = request.files['listing_image']
        if listing_image_file and listing_image_file.filename.rsplit('.', 1)[1] in {'png','jpg'}:
            image = str(encode_image(listing_image_file.read(),(128,128))) # TODO - maintain aspect ratio
        else:
            image = ''
        message={"title":title,"description":description,"price":price,"currency":currency_code,"image": image}
        task = queue_task(1,'new_listing',message)
        messageQueue.put(task)
        sleep(0.1)  # it's better for the user to get a flashed message now rather than on the next page load so
                    # we will wait for 0.1 seconds here because usually this is long enough to get the queue response back
        checkEvents()
        return redirect(url_for('listings'))
    else:
        session = app.roStorageDB.DBSession()
        categories = None # session.query(app.roStorageDB.Contacts).all() # TODO: Query list of categories currently known
        currencies = session.query(app.roStorageDB.currencies).all()
        return render_template('listing-new.html',categories=categories, currencies=currencies)



@app.route('/messages/new/',methods=["GET","POST"])
@app.route('/messages/new/<string:recipient_key>',methods=["GET","POST"]) # TODO CSRF protection required
@login_required
def new_message(recipient_key=""):
    checkEvents()
    if request.method == "POST":
        # TODO: Validate these inputs
        recipient = request.form['recipient']
        subject = request.form['subject']
        body = request.form['body']
        sign_msg = request.form['sign-message']
        message={"recipient":recipient,"subject":subject,"body":body}
        task = queue_task(1,'send_pm',message)
        messageQueue.put(task)
        sleep(0.1)  # it's better for the user to get a flashed message now rather than on the next page load so
                    # we will wait for 0.1 seconds here because usually this is long enough to get the queue response back
        checkEvents()
        return redirect(url_for('messages'))
    else:
        session = app.roStorageDB.DBSession()
        contacts = session.query(app.roStorageDB.Contacts).all()
        return render_template('message-compose.html',contacts=contacts, recipient_key=recipient_key)

@app.route('/messages/delete/<string:id>/',)    # TODO CSRF protection required
@login_required
def delete_message(id):
    message={"id":"" + id + ""}
    task = queue_task(1,'delete_pm',message)
    messageQueue.put(task)
    sleep(0.1)  # it's better for the user to get a flashed message now rather than on the next page load so
                # we will wait for 0.1 seconds here because usually this is long enough to get the queue response back
    checkEvents()
    return redirect(url_for('messages'))


@app.route('/load-identity', methods=['POST'])
def loadidentity():                                               # load existing app data from a non-default location
  if app.SetupDone : return redirect(url_for('home'))
  app.appdir = dirname(request.form['app_dir']) # strip off the file-name
  print app.appdir
  if isfile(app.appdir + "/secret") and isfile (app.appdir + "/storage.db") :
      app.SetupDone = True # TODO: A better check is needed here
  else:
      flash("Could not load application data from " + app.appdir,category="error")
  return redirect(url_for('login'))


@app.route('/create-identity', methods=['POST'])
def createidentity():                                               # This is a bit of a mess, TODO: clean up
  if app.SetupDone : return redirect(url_for('home'))
  app.pgp_keyid = request.form['keyid']
  app.display_name = request.form['displayname']
  app.pgp_passphrase = request.form['pgppassphrase']
  # Now attempt to create our application data directory if it doesn't exist
  if not isdir(app.appdir):
      try:
        makedirs(app.appdir,mode=0700)
      except:
        flash("Error creating identity - client folder not created",category="error")
        return redirect(url_for('install'))
  app.dbsecretkey = ''.join(random.SystemRandom().choice(string.digits) for _ in range(128))
  # Now create our empty pgp keyring it it does not exist in our app data dir
  if not isfile(app.appdir + '/pubkeys.gpg'):
      try:
         file = open(app.appdir+'/pubkeys.gpg', 'w')
         file.close()
      except:
         flash("Error creating public keyring",category="error")
         return redirect(url_for('install'))
  # Now create or overwrite the secret db key file in the app data dir
  try:
     file = open(app.appdir+'/secret', 'w')
     encrypted_dbsecretkey = gpg.encrypt(app.dbsecretkey, app.pgp_keyid)
     file.write(str(encrypted_dbsecretkey))
     file.close()
     app.SetupDone = True
  except:
     flash("Error creating identity - secret file not created",category="error")
     return redirect(url_for('install'))
  ## Now create & populate DB with initial values
  installStorageDB = Storage(app.dbsecretkey,'storage.db',app.appdir)
  if not installStorageDB.Start():
     flash('There was a problem creating the storage database '+ 'storage.db',category="error")
  session = installStorageDB.DBSession()
  # Now populate the config database with defaults + user specified data
  defaults = create_defaults(installStorageDB,session,app.pgp_keyid,app.display_name,app.publish_id)
  if not defaults:
    flash('There was a problem creating the initial configuration in the storage database '+ 'storage.db',category="error")
    #return False
  # Now set the proxy settings specified on the install page
  socks_proxy = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "proxy").first()
  socks_proxy_port = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "proxy_port").first()
  i2p_socks_proxy = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "i2p_proxy").first()
  i2p_socks_proxy_port = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "i2p_proxy_port").first()
  socks_enabled = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "socks_enabled").first()
  i2p_socks_enabled = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "i2p_socks_enabled").first()
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
  if app.SetupDone : return redirect(url_for('home'))
  private_keys = gpg.list_keys(True) # True => private keys
  return render_template('install.html',key_list=private_keys)

@app.route('/setup', methods=["GET","POST"])
@app.route('/setup/<string:page>', methods=["GET","POST"])
@login_required
def setup(page=''):
  checkEvents()
  if request.method == "POST":
      # These are updates to the config - these should be sent to the client queue but for now allow a db update from here
      #  CHeck and apply new settings
      session = app.roStorageDB.DBSession()
      displayname = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "displayname").first()
      profile =  session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "profile").first()
      avatar_image =  session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "avatar_image").first()
      hubnodes = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "hubnodes").all()
      notaries = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "notaries").all()
      socks_proxy = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "proxy").first()
      socks_proxy_port = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "proxy_port").first()
      i2p_socks_proxy = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "i2p_proxy").first()
      i2p_socks_proxy_port = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "i2p_proxy_port").first()
      socks_enabled = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "socks_enabled").first()
      i2p_socks_enabled = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "i2p_socks_enabled").first()
      message_retention = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "message_retention").first()
      accept_unsigned = session.query(app.roStorageDB.Config).filter(app.roStorageDB.Config.name == "accept_unsigned").first()
      #
      if page == "identity":
            if displayname:
                displayname.value = request.form['displayname']
            avatar_image_file = request.files['avatar_image']
            if avatar_image_file and avatar_image_file.filename.rsplit('.', 1)[1] in {'png','jpg'}:
                if not avatar_image:
                    new_conf_item = app.roStorageDB.Config(name="avatar_image")
                    new_conf_item.value = str(encode_image(avatar_image_file.read(),(128,128))) # TODO - maintain aspect ratio
                    new_conf_item.displayname = "Avatar Image"
                    session.add(new_conf_item)
                else:
                    avatar_image.value = encode_image(avatar_image_file.read(),(128,128)) # TODO - maintain aspect ratio
                    #print encode_image(avatar_image_file.read(),(128,128))
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
          session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "hubnodes").delete()
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
      try:
         session.commit()
      except:
         session.rollback()
         flash("There was a problem saving the updated configuration. Nothing has been saved",category="error")
         return redirect(url_for('setup'))
      finally:
         session.close()
         flash("Configuration updated",category="message")
         return redirect(url_for('setup'))
  else:
      # First read config from the database
      session = app.roStorageDB.DBSession()
      pgpkeyid = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "pgpkeyid").first()
      displayname = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "displayname").first()
      profile =  session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "profile").first()
      avatar =  session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "avatar_image").first()
      hubnodes = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "hubnodes").all()
      notaries = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "notaries").all()
      socks_proxy = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "proxy").first()
      socks_proxy_port = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "proxy_port").first()
      i2p_socks_proxy = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "i2p_proxy").first()
      i2p_socks_proxy_port = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "i2p_proxy_port").first()
      socks_enabled = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "socks_enabled").first()
      i2p_socks_enabled = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "i2p_socks_enabled").first()
      message_retention = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "message_retention").first()
      accept_unsigned = session.query(app.roStorageDB.Config.value).filter(app.roStorageDB.Config.name == "accept_unsigned").first()
      session.close()
      if page == '':
        return render_template('setup.html',displayname=displayname,pgpkeyid=pgpkeyid,hubnodes=hubnodes,notaries=notaries)
      elif page == 'identity':
        return render_template('setup-identity.html',displayname=displayname,pgpkeyid=pgpkeyid,profile=profile,avatar=avatar)
      elif page == 'network':
        return render_template('setup-network.html',proxy=socks_proxy,proxy_port=socks_proxy_port,i2p_proxy=i2p_socks_proxy,i2p_proxy_port=i2p_socks_proxy_port,hubnodes=hubnodes,socks_enabled=socks_enabled, i2p_socks_enabled=i2p_socks_enabled)
      elif page == 'security':
        return render_template('setup-security.html',message_retention=message_retention,accept_unsigned=accept_unsigned.value)
      elif page == 'trading':
        return render_template('setup-trading.html',notaries=notaries)

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
    app.pgp_passphrase=""
    app.pgp_keyid=""
    # Disconnect database
    app.roStorageDB.Stop()
    task = queue_task(1,'shutdown',None)
    messageQueue.put(task)
    # any other cleanup (touch files?)
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
  if not app.SetupDone : return redirect(url_for('install'))
  private_keys = gpg.list_keys(True) # True => private keys
  if request.method == "POST":
    # check that secret can be decrypted
    try:
        stream = open(app.appdir+"/secret", "rb")
    except:
        flash('There was a problem opening the secret file',category="error")
        return render_template('login.html',key_list=private_keys)
    app.pgp_keyid = request.form['keyid']
    app.pgp_passphrase = request.form['pgppassphrase']
    if request.form.get('offline') == 'yes':
        app.workoffline = True
    else:
        app.workoffline = False
    decrypted_data = gpg.decrypt_file(stream,False,app.pgp_passphrase)
    if not str(decrypted_data):
        flash('Your passphrase or PGP key is not correct',category="error")
        return render_template('login.html',key_list=private_keys)
    app.dbsecretkey = str(decrypted_data)
    app.roStorageDB = Storage(app.dbsecretkey,"storage.db",app.appdir)
    if not app.roStorageDB.Start():
        flash('You were authenticated however there is a problem with the storage database',category="error")
        return render_template('login.html',key_list=private_keys)
    user = User.get(app.pgp_keyid)
    login_user(user)
    if app.connection_status=="Off-line":
        messageThread = messaging_loop( app.pgp_keyid, app.pgp_passphrase, app.dbsecretkey,"storage.db",app.homedir, app.appdir, messageQueue, messageQueue_res, workoffline=app.workoffline)
        messageThread.start()
        sleep(0.1)  # it's better for the user to get a flashed message now rather than on the next page load so
        checkEvents()
    return render_template('home.html')
  else:
    return render_template('login.html',key_list=private_keys)

# Minimalist PGP keyserver implementation (no auth required)
# TODO: Move this whole function to client_backend and run as a small thread with a listener on a dedicated port
@app.route('/pks/lookup')
def pks_lookup():
    if not app.pgp_keyid:
        resp = make_response("Key server not available", 404)
        resp.headers.extend({'X-HKP-Results-Count': '0'})
        return resp
    search_key = request.args.get('search','')
    if not search_key:
        resp = make_response("Key ID not provided", 404)
        resp.headers.extend({'X-HKP-Results-Count': '0'})
        return resp
    # if the provided keyid starts with 0x
    search_key_split = search_key.split('x')
    if len(search_key_split)==2:
        search_key=search_key_split[1] # strip 0x
    # Query local key cache database for the key - we will request from the broker if we don't have it
    print "PKS Lookup for " + search_key
    session = app.roStorageDB.DBSession()
    key_block = session.query(app.roStorageDB.cachePGPKeys).filter_by(key_id=search_key).first()
    if not key_block:
        key={"keyid":"" + search_key + ""}
        print "Keyblock not found in db, sending query key msg"
        task = queue_task(1,'get_key',key)
        messageQueue.put(task)
        print "Sent message requesting key..."
        # now, we wait...
        sleep(0.01)
        timer = 0
        key_block = session.query(app.roStorageDB.cachePGPKeys).filter_by(key_id=search_key).first()
        while (not key_block) and (timer < 20): # 20 second timeout for key lookups
            sleep (1)
            key_block = session.query(app.roStorageDB.cachePGPKeys).filter_by(key_id=search_key).first()
            timer = timer + 1
        if not key_block:
            resp = make_response("Key not found", 404)
            resp.headers.extend({'X-HKP-Results-Count': '0'})
            return resp
    resp = make_response(key_block.keyblock, 200) # for now return our key
    resp.headers.extend({'X-HKP-Results-Count': '1'}) # we will only ever return a single key
    return resp

def checkEvents():
    if messageQueue_res.empty(): return(False)
    while not messageQueue_res.empty():
        results = messageQueue_res.get()
        # TODO: check results is set to a valid queue_task object here
        if not type(results) == queue_task:
            flash("Unknown data received from client thread results queue", category="error")
            return(True)
        if results.command == 'flash_message':
            flash(results.data, category="message")
        elif results.command == 'flash_error':
            flash(results.data, category="error")
        elif results.command == 'flash_status':
            app.connection_status = results.data
        elif results.command == 'resolved_key':
            app.pgpkeycache[results.data['keyid']] = results.data['key_block'] # add this key to the keycache
        else:
            flash("Unknown command received from client thread results queue", category="error")
    return(True)

if __name__ == '__main__':
  app.storageThreadID = ""
  app.pgpkeycache = {}
  app.dbsecretkey = ""
  app.workoffline = False
  app.secret_key = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(16))
  app.jinja_env.globals['csrf_token'] = generate_csrf_token
  app.SetupDone = False
  app.pgp_keyid = ""
  app.publish_id = True
  app.roStorageDB = Storage
  app.display_name = ""
  app.pgp_passphrase = ""
  app.homedir = expanduser("~")
  if get_os() == 'Windows':
    app.appdir = app.homedir + '\\application data\\.dnmng' # This is the default appdir location
    gpg = gnupg.GPG(gnupghome=app.homedir + '/application data/gnupg',options={'--throw-keyids','--no-emit-version','--trust-model=always'}) # we want to encrypt the secret with throw keys
  else:
    app.appdir = app.homedir + '/.dnmng' # This is the default appdir location
    gpg = gnupg.GPG(gnupghome=app.homedir + '/.gnupg',options={'--throw-keyids','--no-emit-version','--trust-model=always'}) # we want to encrypt the secret with throw keys
  print app.homedir
  app.connection_status = "Off-line"
  app.current_broker = None
  app.current_broker_users = None
  if isfile(app.appdir + "/secret") and isfile (app.appdir + "/storage.db") :   app.SetupDone = True # TODO: A better check is needed here
  app.run(debug=True,threaded=True) # Enable threading, primarily for pks keyserver support until the keyserver is moved to client_backend


