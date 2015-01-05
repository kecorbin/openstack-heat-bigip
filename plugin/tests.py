import yaml
import ltm_plugin

blah = 'foo'
plugin = ltm_plugin.LTM(blah,blah,blah)

# define program-wide variables
plugin.BIGIP_ADDRESS = 'opk-float9.cisco.com'
plugin.BIGIP_USER = 'admin'
plugin.BIGIP_PASS = 'admin'

SLEEP_TIME = 20

plugin.VS_NAME = 'virtual-server'
plugin.VS_ADDRESS = '7.7.1.23'
plugin.VS_PORT = 'any'

plugin.POOL_NAME = 'pool'
plugin.POOL_LB_METHOD = 'least-connections-member'
plugin.POOL_MEMBERS = [ '192.168.123.3:0' ]



plugin.handle_create()
