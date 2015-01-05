openstack-heat-bigip
====================

Heat plugin for F5 Big-IP 

# Installation


## Environment

Required

* Python 2.7+


## Downloading

Clone the repository

     git clone https://github.com/kecorbin/openstack-heat-plugin

Copy the plugin into heat plugin_dirs (/etc/heat/heat.conf)
    
     cp plugin/ltm_plugin.py /usr/lib/heat

Restart openstack-heat-engine (RHEL example)

    systemctl restart openstack-heat-engine
    


# Usage

sample HOT template in example directory


The following section needs to be added to heat.conf

    [ltm_plugin]
    ltm_host=1.1.1.1
    ltm_username=admin
    ltm_password=password

