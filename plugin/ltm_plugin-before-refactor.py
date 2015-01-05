#!/usr/bin/env python
# Version 1.0

from heat.engine import resource
from heat.openstack.common.gettextutils import _
from heat.openstack.common import log as logging
import requests
import json
import iniparse
import MySQLdb
logger = logging.getLogger(__name__)


class LTM(resource.Resource):
    #TODO - cleanup extra properties
    properties_schema = {
        'partition':  {
            'Type': 'String',
            'Default': '',
            'Description': _('Partition')
        },
        'vs_name':  {
            'Type': 'String',
            'Default': '',
            'Description': _('Vitrual Server Name')
        },
        'vs_address':  {
            'Type': 'String',
            'Default': '',
            'Description': _('Virtual Server Address')
        },
        'vs_port':  {
            'Type': 'String',
            'Default': 'any',
            'Description': _('Virtual Server Address')
        },
        'pool_name': {
            'Type': 'String',
            'Default': 'any',
            'Description': _('Pool Name')
        },
        'pool_member': {
            'Type': 'String',
            'Default': 'any',
            'Description': _('IP Address of Pool Member')
        }
    }

    attributes_schema = {
        'name': _('Name of the Resource'),
        'fqdn': _('FQDN of the VIP'),
        'pool': _('Pool Name'),
        'vs': _('Virtual Server Name'),
    }

    def _resolve_attribute(self, name):
        if name in self.attributes:
            return str(self.attributes[name])
        else:
            return "Unknown Attribute"
            #raise ValueError('No Valid Attribute %s' % name)

    def __init__(self, *args, **kwargs):
        super(LTM, self).__init__(*args, **kwargs)
        try:
            self.cfg = iniparse.INIConfig(open('/etc/heat/plugins.ini'))
        except:
            raise ValueError("Plugin configuration file not found")
        # BIGIP Session Information
        host = self.cfg.ltm.ltm_host
        username = self.cfg.ltm.ltm_username
        password = self.cfg.ltm.ltm_password
        self.BIGIP_ADDRESS = host
        self.bigip = requests.session()
        self.bigip.auth = (username, password)
        self.bigip.verify = False
        self.bigip.headers.update({'Content-Type': 'application/json'})
        self.BIGIP_URL_BASE = 'https://%s/mgmt/tm' % self.BIGIP_ADDRESS
        # Initialize MySQL connection
        dbhost = self.cfg.ltm.ltm_db_host
        dbuser = self.cfg.ltm.ltm_db_user
        dbname = self.cfg.ltm.ltm_db_name
        dbpass = self.cfg.ltm.ltm_db_passwd
        self.dbtable = 'vips'
        self.db = MySQLdb.connect(dbhost, dbuser, dbpass, dbname)
        self.vip_dict = dict()
        #self.fqdn = ''
        # Initialize stack specific items
        self.VS_PORT = self.properties['vs_port']
        self.POOL_LB_METHOD = 'least-connections-member'
        #self.PARTITION = ''
        #self.VS_NAME = ''
        #self.VS_ADDRESS = ''
        #self.POOL_NAME = ''
        # Initialize Attributes Dictionary
        self.attributes = dict()

    def reserve_vip(self):
        logger.info("Contacting Database for available VIP")
        cursor = self.db.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM vips where ACTIVE = 0 LIMIT 1")
        response = cursor.fetchall()
        if len(response) < 1:
            raise ValueError("Could not get VIP from Database")
        else:
            self.vip_dict = response[0]
            self.VS_NAME = self.vip_dict['fqdn']
            self.VS_ADDRESS = self.vip_dict['vip_address']
            self.POOL_NAME = self.vip_dict['pool_name']
            self.PARTITION = self.vip_dict['partition_name']
            self.attributes['fqdn'] = self.vip_dict['fqdn']
            self.attributes['dbid'] = self.vip_dict['id']
            cursor.execute("UPDATE vips SET active = 1 where id = %s" % self.attributes['dbid'])
            self.db.commit()
            logger.info("Reserved %s - %s" % (self.VS_NAME, self.VS_ADDRESS))

    def db_update(self, table, column, value, dbid):
            cursor = self.db.cursor(MySQLdb.cursors.DictCursor)
            logger.info("SQL CALL: UPDATE %s SET %s = %s where id = %s" %
                           (table, column, value, dbid))
            cursor.execute("UPDATE %s SET %s = '%s' where id = %s" %
                           (table, column, value, dbid))
            self.db.commit()

    def add_pool_member(self):
        payload = dict()
        pool_members = [self.properties['pool_member']]
        payload['partition'] = self.PARTITION
        response = self.bigip.get('%s/ltm/pool/~%s~%s/members' % (self.BIGIP_URL_BASE, self.PARTITION, self.POOL_NAME))
        jsondict = json.loads(response.text)
        existing_member_list = jsondict['items']
        for d in existing_member_list:
            bad_keys = ['state', 'ephemeral', 'session']
            for k in bad_keys:
                d.pop(k)
        members = existing_member_list
        for member in pool_members:
            members.append({'kind': 'ltm:pool:members', 'partition': '%s' % self.PARTITION, 'name': member})
        payload['members'] = members
        logger.info(self.bigip.put('%s/ltm/pool/~%s~%s'
                                   % (self.BIGIP_URL_BASE, self.PARTITION, self.POOL_NAME),
                                   data=json.dumps(payload)))

    def create_pool(self):
        pool = dict()
        pool_members = [self.properties['pool_member']]
        # convert member format
        members = [
            {'kind': 'ltm:pool:members',
             'partition': 'ServiceNet',
             'name': member + ':0'} for member in pool_members
        ]
        pool['partition'] = self.PARTITION
        pool['kind'] = 'tm:ltm:pool:poolstate'
        pool['name'] = self.POOL_NAME
        pool['description'] = 'A Python REST client test pool'
        pool['loadBalancingMode'] = self.POOL_LB_METHOD
        pool['monitor'] = 'gateway_icmp'
        pool['members'] = members
        # log the post
        logger.info('POST: %s/ltm/pool PAYLOAD: %s' % (self.BIGIP_URL_BASE, json.dumps(pool)))
        a = self.bigip.post('%s/ltm/pool' % self.BIGIP_URL_BASE, data=json.dumps(pool))
        logger.info('RESPONSE: %s' % a)
        logger.info(a.text)
        self.attributes['pool'] = a.url
        self.db_update(self.dbtable, 'pool_url', a.url, self.attributes['dbid'])

    def create_virtual(self):
        payload = dict()
        payload['partition'] = self.PARTITION
        payload['kind'] = 'tm:ltm:virtual:virtualstate'
        payload['name'] = self.VS_NAME
        payload['description'] = 'A Python REST client test virtual server'
        payload['destination'] = '%s:%s' % (self.VS_ADDRESS, self.VS_PORT)
        payload['mask'] = '255.255.255.255'
        payload['ipProtocol'] = 'tcp'
        payload['sourceAddressTranslation'] = {'type': 'automap'}
        payload['pool'] = self.POOL_NAME
        # Create the VS
        a = self.bigip.post('%s/ltm/virtual' % self.BIGIP_URL_BASE, data=json.dumps(payload))
        # log results
        logger.info('POST: %s/ltm/virtual PAYLOAD: %s' % (self.BIGIP_URL_BASE, json.dumps(payload)))
        logger.info('RESPONSE %s' % a)
        logger.info(a.text)
        self.attributes['fqdn'] = self.VS_NAME
        logger.info('VIP: %s' % self.VS_NAME)
        self.attributes['vs'] = a.url
        self.resource_id_set(self.VS_NAME)
        self.db_update(self.dbtable, 'vs_url', a.url, self.attributes['dbid'])

    def delete_virtual(self):
        logger.info('DELETE: %s/ltm/virtual/~%s~%s' % (self.BIGIP_URL_BASE, self.PARTITION, self.VS_NAME))
        resp = self.bigip.delete('%s/ltm/virtual/~%s~%s' % (self.BIGIP_URL_BASE, self.PARTITION, self.VS_NAME))
        logger.info(resp)
        #TODO: need some database work here

    def delete_pool(self):
        logger.info('DELETE: %s/ltm/virtual/~%s~%s' % (self.BIGIP_URL_BASE, self.PARTITION, self.POOL_NAME))
        resp = self.bigip.delete('%s/ltm/pool/~%s~%s' % (self.BIGIP_URL_BASE, self.PARTITION, self.POOL_NAME))
        logger.info(resp)

    def handle_create(self):
        # check if pool already exists
        response = self.bigip.get('%s/ltm/pool/~%s~%s/members' % (self.BIGIP_URL_BASE, self.PARTITION, self.POOL_NAME))
        if response.status_code == 200:
            logger.info('Pool Already exists - adding member to existing pool')
            self.add_pool_member()
        else:
            logger.info('Pool does not exist - creating')
            self.reserve_vip()
            self.create_pool()
            self.create_virtual()
            #TODO: finish db work
            #self.db_update()

    def handle_delete(self):
        self.delete_virtual()
        self.delete_pool()

    def handle_suspend(self):
        pass


def resource_mapping():
    return {
        'OS::Heat::BigIP': LTM
    }
