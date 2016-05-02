from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, DateTime
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

#import pycountry
from os.path import isfile
import paginate
from platform import system as get_os
from utilities import current_time
from datetime import datetime

class memory_cache(): # In-memory cache db to hold a potentially large user directory comprising both the AM user directory and supplementary lists from notaries and other UPLs

    Base = declarative_base()

    def __init__(self,main_db,my_key,my_display_name):
        self.main_db = main_db # This will be set to the main local RO database in the front end client
        self.my_key = my_key
        self.my_display_name = my_display_name
        self.engine = create_engine('sqlite://',connect_args={'check_same_thread': False},poolclass=StaticPool) # simple in-memory db
        self.Base.metadata.create_all(self.engine)
        self.Base.metadata.bind = self.engine
        self.DBSession = sessionmaker(bind=self.engine)
        self.rebuild()

    class cacheFullDirectory(Base): # This table  contains the aggregate of all user publihed lists and notary lists subscribed to
        __tablename__ = 'cachefulldirectory'
        key_id = Column(String(16), primary_key=True, nullable=False)
        updated = Column(DateTime, nullable=False, index=True)
        display_name = Column(String(), index=True)
        is_active_user = Column(Boolean)
        is_seller = Column(Boolean)
        is_notary = Column(Boolean)
        is_arbiter = Column(Boolean)
        is_upl = Column(Boolean)
        is_contact = Column(Boolean)
        is_looking_glass = Column(Boolean)
        aggregate_transactions = Column(Integer)
        aggregate_feedback = Column(String(4))

    def update(self,update_data):
        session = self.DBSession()
        target_key = session.query(self.cacheFullDirectory).filter_by(key_id = update_data['key_id']).first() #
        if target_key:
            # This user is already present in the directory so we need to update
            target_key.display_name = update_data['display_name']
            target_key.is_seller = update_data['is_seller']
            target_key.is_notary = update_data['is_notary']
            target_key.is_arbiter = update_data['is_arbiter']
            target_key.is_looking_glass = update_data['is_looking_glass']
            target_key.is_upl = update_data['is_upl']
        else:
            # New user for the directory
            cache_dir_entry = self.cacheFullDirectory(key_id=update_data['key_id'],
                                                updated=update_data['updated'],
                                                display_name=update_data['display_name'],
                                                is_active_user = True, # Since this is from a directory_update it must be an active user
                                                is_seller = update_data['is_seller'],
                                                is_upl = update_data['is_upl'],
                                                is_notary = update_data['is_notary'],
                                                is_arbiter = update_data['is_arbiter'],
                                                is_looking_glass = update_data['is_looking_glass'])
            session.add(cache_dir_entry)
        session.commit()
#        print "Updated front-end directory cache for user " + update_data['display_name']  + "("+update_data['key_id']+")"

    def rebuild(self):
        print "Rebuilding front end in-memory cache db"
        session = self.DBSession()
        session.query(self.cacheFullDirectory).delete() # full rebuild so clear the table
        session.commit()
        main_session = self.main_db.DBSession()
        # 1st copy over the current cacheDirectory as is
        cache_dir_res = main_session.query(self.main_db.cacheDirectory).all()
        for row in cache_dir_res:
            cache_dir_entry = self.cacheFullDirectory(key_id=row.key_id,
                                                updated=row.updated,
                                                display_name=row.display_name,
                                                is_active_user = True, # Since this is from the directory it must be an active user
                                                is_seller = row.is_seller,
                                                is_upl = row.is_upl,
                                                is_notary = row.is_notary,
                                                is_arbiter = row.is_arbiter,
                                                is_looking_glass = row.is_looking_glass)
                                                # aggregate_transactions = # TODO caclulate based on available cached UPL's
                                                # aggregate_feedback = # TODO caclulate based on available cached UPL's
            session.add(cache_dir_entry)
        session.commit()
        # our own key should go in now if it hasn't already come from the directory (this is usually only needed for the very first run following installation)
        my_entry = session.query(self.cacheFullDirectory).filter_by(key_id=self.my_key).first()
        if my_entry:
            pass # our key is already present
        else:
            my_dir_entry = self.cacheFullDirectory(key_id=self.my_key,
                                                   updated=datetime.strptime(current_time(), "%Y-%m-%d %H:%M:%S"),
                                                   is_contact=True,
                                                   is_active_user=True,
                                                   display_name = self.my_display_name)
            session.add(my_dir_entry)
            session.commit()
        # Now read in keyids from the users contacts, add these and update where necessary (usually the contact will also be in teh directory but not always)
        contacts_res = main_session.query(self.main_db.Contacts).all()
        for row in contacts_res:
            qry_res = session.query(self.cacheFullDirectory).filter_by(key_id=row.contact_key).first()
            if qry_res:
                qry_res.is_contact = True
            else:
                contact = self.cacheFullDirectory(key_id=row.contact_key, updated=datetime.strptime(current_time(), "%Y-%m-%d %H:%M:%S"),is_contact = True, display_name = row.display_name)
                session.add(contact)
        session.commit()
        # Now read in keyids from UPLs including notary lists, add these and update where necessary
        pass


class Storage(): # Main, persistent, encrypted local database

    def __init__(self, passphrase, database, appdir):
        self.database = database
        self.appdir = appdir
        self.passphrase = passphrase
        self.DBSession = sessionmaker

    Base = declarative_base()

    class Config(Base):
        __tablename__ = 'config'
        id = Column(Integer, primary_key=True)
        name = Column(String(250), nullable=False, index=True)
        value = Column(String(2048), nullable=False)
        displayname = Column(String(250), nullable=False)

    class PrivateMessaging(Base):
        __tablename__ = 'privatemessaging'
        id = Column(Integer, primary_key=True)
        message_id = Column(String(32), nullable=False, index=True)
        sender_key = Column(String(16), nullable=False, index=True)
        sender_name = Column(String(64))
        recipient_key = Column(String(16), nullable=False, index=True)
        recipient_name = Column(String(64))
        message_date = Column(DateTime)
        # Make sure we enforce a purge date
        message_purge_date = Column(DateTime, nullable=False)
        subject = Column(String(250))
        body = Column(String(32768))         # 32KB limit for PM message body
        parent_message_id = Column(String(32))
        message_read = Column(Boolean)
        message_sent = Column(Boolean)
        message_direction = Column(String(5))

    class Contacts(Base):
        __tablename__ = 'contacts'
        id = Column(Integer, primary_key=True)
        contact_key = Column(String(16), nullable=False)
        contact_name = Column(String(64))
        contact_flags = Column(String(1024))

    class UPL_lists(Base):
        __tablename__ = 'upl_lists'
        id = Column(Integer, primary_key=True)
        author_key_id = Column(String(16), nullable=False)
        name = Column(String(64))
        description = Column(String(255))
        type = Column(Integer)

    class UPL(Base):
        __tablename__ = 'upl'
        key_id = Column(String(16), nullable=False, primary_key=True)
        upl_list = Column(Integer, ForeignKey('upl_lists.id'),primary_key=True)
        json_data = Column(String(4096))        # 4kb limit for UPL data

    class Listings(Base):
        __tablename__ = 'listings'
        id = Column(Integer, primary_key=True, index=True)
        title = Column(String(80), nullable=False)
        category = Column(String(255), nullable=False)
        description = Column(String(4096), nullable=False)
        public = Column(Boolean)
        qty_available = Column(Integer)
        order_max_qty = Column(Integer)
        # Column(DECIMAL(8), nullable=False) # sqlalchemy/sqlite doesn't do
        # decimal
        price = Column(String(20), nullable=False)
        currency_code = Column(String, ForeignKey('currencies.code'))
    #    country_id = Column(Integer, ForeignKey('countries.id'))
    #    ships_from = relationship(country_id)
    #    ships_to = relationship(country_id)
        # will hold json list of shipping options
        shipping_options = Column(String())
        image_base64 = Column(String())

    class Orders(Base):
        __tablename__ = 'orders'
        id = Column(Integer, primary_key=True)
        orderid = Column(String(32), nullable=False, index=True)
        seller_key = Column(String(16), nullable=False, index=True)
        buyer_key = Column(String(16), nullable=False, index=True)
        notary_key = Column(String(16))
        order_date = Column(DateTime, nullable=False)
        order_status = Column(String(64), nullable=False)
        delivery_address = Column(String())
        order_note = Column(String())
        order_type = Column(String(16), nullable=False)
        buyer_ephemeral_btc_seed = Column(String(256))
        buyer_btc_pub_key = Column(String(256))
        payment_btc_address = Column(String(80), index=True)
        payment_status = Column(String(64), index=True)
        payment_btc_balance_confirmed = Column(String(20))
        payment_btc_balance_unconfirmed = Column(String(20))
        seller_btc_stealth = Column(String(80))
        item_id = Column(String(16), nullable=False)
        title = Column(String(80), nullable=False)
        price = Column(String(20), nullable=False)
        currency_code = Column(String, ForeignKey('currencies.code'))
        # will hold json list of shipping options
        shipping_options = Column(String())
        image_base64 = Column(String())
        publish_date = Column(DateTime, nullable=False)
        raw_item = Column(String())  # raw signed item message text of current message chain with signing
        raw_seed = Column(String(), nullable=False)  # raw signed item message text for seed contract
        quantity = Column(Integer)
        shipping = Column(String())
        line_total_price = Column(String(20), nullable=False)
        line_total_btc_price = Column(String(20), nullable=False)
        feedback_left = Column(String())
        feedback_received = Column(String())
        auxillary = Column(String()) # bucket for future use
        session_id = Column(String(32)) # needed to support looking glass mode
        is_synced = Column(Boolean)

    class Countries(Base):
        __tablename__ = 'countries'
        id = Column(Integer, primary_key=True)
        country = Column(String(80), nullable=False)

    class currencies(Base):
        __tablename__ = 'currencies'
        code = Column(String(4), primary_key=True, nullable=False, index=True)
        name = Column(String(40), nullable=False)
        exchange_rate = Column(String(10), nullable=False)
        last_update = Column(DateTime) # if blank means never

    class Cart(Base):
        __tablename__ = 'shopping_cart'
        id = Column(Integer, primary_key=True)
        seller_key_id = Column(String(16), nullable=False, index=True)
        item_id = Column(String(16), nullable=False, index=True)
        title = Column(String(80), nullable=False)
        qty_available = Column(Integer)
        order_max_qty = Column(Integer)
        price = Column(String(20), nullable=False)
        currency_code = Column(String, ForeignKey('currencies.code'))
        # will hold json list of shipping options
        shipping_options = Column(String())
        image_base64 = Column(String())
        publish_date = Column(DateTime, nullable=False)
        seller_btc_stealth = Column(String(80))
        raw_item = Column(String())  # raw signed item message text
        quantity = Column(Integer)
        shipping = Column(String())
        line_total_price = Column(String(20), nullable=False)
        order_type = Column(String(32))
        session_id = Column(String(32)) # needed to support looking glass mode

    class cachePGPKeys(Base):
        __tablename__ = 'cachepgpkeys'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False, index=True)
        updated = Column(DateTime, nullable=False)
        keyblock = Column(String(8192))

    class cacheDirectory(Base):
        __tablename__ = 'cachedirectory'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False, index=True)
        updated = Column(DateTime, nullable=False)
        display_name = Column(String())
        is_seller = Column(Boolean)
        is_notary = Column(Boolean)
        is_arbiter = Column(Boolean)
        is_upl = Column(Boolean)
        is_looking_glass = Column(Boolean)
        # TODO: Add other key fields but keep it light

    class cacheListings(Base):
        __tablename__ = 'cachelistings'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False)
        updated = Column(DateTime, nullable=False)
        listings_block = Column(String())

    class cacheItems(Base):
        __tablename__ = 'cacheitems'
        t_id = Column(Integer, primary_key=True)
        id = Column(Integer, nullable=False, index=True) # Item id
        key_id = Column(String(16), nullable=False, index=True)
        updated = Column(DateTime, nullable=False)
        listings_block = Column(String())
        title = Column(String(80), nullable=False)
        category = Column(String(255), nullable=False)
        description = Column(String(4096), nullable=False)
        qty_available = Column(Integer)
        order_max_qty = Column(Integer)
        price = Column(String(20), nullable=False)
        currency_code = Column(String, ForeignKey('currencies.code'))
        # will hold json list of shipping options
        shipping_options = Column(String())
        image_base64 = Column(String())
        seller_btc_stealth = Column(String(80))
        publish_date = Column(DateTime, nullable=False)

    class cacheProfiles(Base):
        __tablename__ = 'cacheprofiles'
        id = Column(Integer, primary_key=True)
        key_id = Column(String(16), nullable=False, index=True)
        updated = Column(DateTime, nullable=False, index=True)
        display_name = Column(String(80))
        profile_text = Column(String(4096))
        avatar_base64 = Column(String())  # this does not seem efficient

    def InitDB(self, passphrase, dbfilepath):
        #engine = create_engine('sqlite+pysqlcipher://:PASSPHRASE@/storage.db?cipher=aes-256-cfb&kdf_iter=64000')
        # This next one works although a numeric passphrase must be given
        #        self.engine = create_engine('sqlite+pysqlcipher://:' + passphrase + '/' + dbfilepath)
        print dbfilepath
        # DATABASE ENCRYPTION CAN BE DISABLED/ENABLED HERE
        if get_os() == 'Windows':
            self.engine = create_engine(
                r'sqlite+pysqlcipher://:'+passphrase+'@/' + dbfilepath, connect_args={'check_same_thread': False}) # Encrypted database
                # TESTING ONLY - THIS CREATES A CLEAR-TEXT STORAGE DATABASE!
#                r'sqlite:///' + dbfilepath, connect_args={'check_same_thread': False}) # Cleartext database (testing)
            #  poolclass=StaticPool
        else:

            self.engine = create_engine(
                'sqlite+pysqlcipher://:'+passphrase+'@//' + dbfilepath, connect_args={'check_same_thread': False}) # Encrypted database
                # TESTING ONLY - THIS CREATES A CLEAR-TEXT STORAGE DATABASE!
#                'sqlite:////' + dbfilepath, connect_args={'check_same_thread': False}) # Cleartext database (testing)
            #  poolclass=StaticPool
        try:
            self.Base.metadata.create_all(self.engine)
        except:
            print "Error creating database"
            return False
        self.Base.metadata.bind = self.engine
        self.DBSession = sessionmaker(bind=self.engine)
        return True
        # Populate initial data

    def Start(self):
        newstoragedb = True
        if isfile(self.appdir + '/' + self.database):
            newstoragedb = False

        if get_os() == 'Windows':
            if self.InitDB(self.passphrase, self.appdir + '\\' + self.database):
                return True
            else:
                if newstoragedb:
                    print "Error creating storage database"
                else:
                    print "Error accessing storage database"
                return False
        else:
            if self.InitDB(self.passphrase, self.appdir + '/' + self.database):
                return True
            else:
                if newstoragedb:
                    print "Error creating storage database"
                else:
                    print "Error accessing storage database"
                return False

    def Stop(self):
        try:
            #            self.engine.close()
            self.engine.remove()
            # TODO - compress database on exit using: self.engine.execute("VACUUM")
        except:
            print "Error removing DB session"

"""Enhances the paginate.Page class to work with SQLAlchemy objects"""


class SqlalchemyOrmWrapper(object):
    """Wrapper class to access elements of an SQLAlchemy ORM query result."""

    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, range):
        if not isinstance(range, slice):
            raise Exception("__getitem__ without slicing not supported")
        return self.obj[range]

    def __len__(self):
        return self.obj.count()


class SqlalchemyOrmPage(paginate.Page):

    def __init__(self, *args, **kwargs):
        super(SqlalchemyOrmPage, self).__init__(
            *args, wrapper_class=SqlalchemyOrmWrapper, **kwargs)


class SqlalchemySelectWrapper(object):
    """Wrapper class to access elements of an SQLAlchemy SELECT query."""

    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, range):
        if not isinstance(range, slice):
            raise Exception("__getitem__ without slicing not supported")
        # value for offset
        offset_v = range.start
        limit = range.stop - range.start
        result = self.obj.sqlalchemy_session.execute(selection).fetchall()
        select = result.offset(offset_v).limit(limit)
        return self.sqlalchemy_session.execute(select).fetchall()

    def __len__(self):
        return self.obj.scalar()


class SqlalchemySelectPage(paginate.Page):

    def __init__(self, *args, **kwargs):
        """sqlalchemy_connection: SQLAlchemy connection object"""
        super(SqlalchemySelectPage, self).__init__(*args, wrapper_class=SqlalchemySelectWrapper,
                                                   **kwargs)
