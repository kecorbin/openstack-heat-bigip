#!/usr/bin/env python
# Version 1.0

from heat.engine import resource
from heat.openstack.common.gettextutils import _
from heat.openstack.common import log as logging
import requests
import json
import iniparse
logger = logging.getLogger(__name__)


class LTM(resource.Resource):

    properties_schema = {
        'Hostname': {
            'Type': 'String',
            'Default': '',
            'Description': _('Hostname of the APIC Controller')
        },
        'User': {
            'Type': 'String',
            'Default': '',
            'Description': _('Username')
        },
        'Password': {
            'Type': 'String',
            'Default': '',
            'Description': _('APIC Password')
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
        'Name': _('Name'),
        'Response': _('LTM Response'),
        'VSStatus': _('LTM VS Response'),
        'PoolStatus:': _('LTM Pool Response')

    }

    def _resolve_attribute(self, name):
        if name == 'Name':
            return self.physical_resource_name()
        elif name == 'Response':
            return self.resource_id
        elif name == 'VSStatus':
            return self.ltm_attributes['VSStatus']
        elif name == 'PoolStatus':
            return self.ltm_attributes['PoolStatus']
        else:
            raise ValueError('No Valid Attribute %s' % name)

    def __init__(self, *args, **kwargs):
        super(LTM, self).__init__(*args, **kwargs)

        ## integrate acitoolkit
        self.ltm_attributes = {}
        self.cfg = iniparse.INIConfig(open('/etc/heat/plugins.ini'))
        host = self.cfg.ltm.ltm_host
        username = self.cfg.ltm.ltm_username
        password = self.cfg.apic.ltm_password
        self.BIGIP_ADDRESS = host
        self.bigip = requests.session()
        self.bigip.auth = (username, password)
        self.bigip.verify = False
        self.bigip.headers.update({'Content-Type': 'application/json'})
        self.BIGIP_URL_BASE = 'https://%s/mgmt/tm' % self.BIGIP_ADDRESS

        self.VS_NAME = self.properties['vs_name']
        self.VS_ADDRESS = self.properties['vs_address']
        self.VS_PORT = self.properties['vs_port']

        self.POOL_NAME = self.properties['pool_name']
        self.POOL_LB_METHOD = 'least-connections-member'

    def create_pool(self):
        pool = dict()
        self.POOL_MEMBERS = [self.properties['pool_member']]
        # convert member format
        members = [
            {'kind': 'ltm:pool:members', 'partition': 'ServiceNet', 'name': member + ':0'} for member in self.POOL_MEMBERS
        ]
        # define test pool
        #TODO: change static parition / add monitoring options
        pool['partition'] = 'ServiceNet'
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
        #self.ltm_attributes['PoolStatus'] = self.bigip.status_code

    def create_virtual(self):
        payload = dict()

        # define test virtual
        payload['partition'] = 'ServiceNet'
        payload['kind'] = 'tm:ltm:virtual:virtualstate'
        payload['name'] = self.VS_NAME
        payload['description'] = 'A Python REST client test virtual server'
        payload['destination'] = '%s:%s' % (self.VS_ADDRESS, self.VS_PORT)
        payload['mask'] = '255.255.255.255'
        payload['ipProtocol'] = 'tcp'
        payload['sourceAddressTranslation'] = {'type': 'automap'}
        payload['pool'] = self.POOL_NAME
        # log POST
        logger.info('POST: %s/ltm/virtual PAYLOAD: %s' % (self.BIGIP_URL_BASE, json.dumps(payload)))
        a = self.bigip.post('%s/ltm/virtual' % self.BIGIP_URL_BASE, data=json.dumps(payload))
        logger.info('RESPONSE %s' % a)
        logger.info(a.text)

    def delete_virtual(self):
        logger.info('DELETE: %s/ltm/virtual/~ServiceNet~%s' % (self.BIGIP_URL_BASE, self.VS_NAME))
        #TODO: need to pass parition name from HOT template
        resp = self.bigip.delete('%s/ltm/virtual/~ServiceNet~%s' % (self.BIGIP_URL_BASE, self.VS_NAME))
        logger.info(resp)

    def delete_pool(self):
        logger.info('DELETE: %s/ltm/virtual/~ServiceNet~%s' % (self.BIGIP_URL_BASE, self.POOL_NAME))
        #TODO: need to pass parition name from HOT template
        resp = self.bigip.delete('%s/ltm/pool/~ServiceNet~%s' % (self.BIGIP_URL_BASE, self.POOL_NAME))
        logger.info(resp)

    def handle_create(self):
        self.create_pool()
        self.create_virtual()

    def handle_delete(self):
        self.delete_virtual()
        self.delete_pool()

    def handle_suspend(self):
        pass


def resource_mapping():
    return {
        'OS::Heat::BigIP': LTM
    }
