# Copyright 2012 OpenStack, LLC
# Copyright 2015 Mirantis, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import logging
import os
import time

import fuel_health.common.utils.data_utils as data_utils

LOG = logging.getLogger(__name__)

# Default client libs
try:
    import heatclient.v1.client
except Exception:
    LOG.exception()
    LOG.warning('Heatclient could not be imported.')
try:
    import muranoclient.v1.client
except Exception:
    LOG.exception()
    LOG.warning('Muranoclient could not be imported.')
try:
    import saharaclient.client
except Exception:
    LOG.exception()
    LOG.warning('Sahara client could not be imported.')
try:
    import ceilometerclient.v2.client
except Exception:
    LOG.exception()
    LOG.warning('Ceilometer client could not be imported.')
try:
    import neutronclient.neutron.client
except Exception:
    LOG.exception()
    LOG.warning('Neutron client could not be imported.')
try:
    import glanceclient
except Exception:
    LOG.exception()
    LOG.warning('Glance client could not be imported')
try:
    import ironicclient
except Exception:
    LOG.exception()
    LOG.warning('Ironic client could not be imported')
try:
    import muranoclient.glance.client as art_client
except Exception:
    LOG.exception()
    LOG.warning('Artifacts client could not be imported')

import aodhclient.client
import cinderclient.client
import glanceclient.client
import keystoneclient
import novaclient.client
import novaclient.exceptions as nova_exc

from fuel_health.common import ssh as f_ssh
from fuel_health.common.utils.data_utils import rand_int_id
from fuel_health.common.utils.data_utils import rand_name
from fuel_health import exceptions
import fuel_health.manager
import fuel_health.test
import keystoneauth1.identity
import keystoneauth1.session


class OfficialClientManager(fuel_health.manager.Manager):
    """Manager that provides access to the official python clients for
    calling various OpenStack APIs.
    """

    NOVACLIENT_VERSION = '2'
    CINDERCLIENT_VERSION = '2'

    def __init__(self):
        super(OfficialClientManager, self).__init__()
        self.clients_initialized = False
        self.traceback = ''
        self.keystone_error_message = None
        self.compute_client = self._get_compute_client()
        try:
            self.identity_client = self._get_identity_client()
            self.identity_v3_client = self._get_identity_client(version=3)
            self.clients_initialized = True
        except (keystoneclient.exceptions.AuthorizationFailure,
                keystoneclient.exceptions.Unauthorized):
            self.keystone_error_message = \
                exceptions.InvalidCredentials.message
        except Exception as e:
            LOG.error(
                "Unexpected error durring intialize keystoneclient: {0}"
                .format(e)
            )
            LOG.exception("Unexpected error durring intialize keystoneclient")

        if self.clients_initialized:
            self.glance_client = self._get_glance_client()
            self.volume_client = self._get_volume_client()
            self.heat_client = self._get_heat_client()
            self.murano_client = self._get_murano_client()
            self.sahara_client = self._get_sahara_client()
            self.ceilometer_client = self._get_ceilometer_client()
            self.neutron_client = self._get_neutron_client()
            self.glance_client_v1 = self._get_glance_client(version=1)
            self.ironic_client = self._get_ironic_client()
            self.aodh_client = self._get_aodh_client()
            self.artifacts_client = self._get_artifacts_client()
            self.murano_art_client = self._get_murano_client(artifacts=True)
            self.client_attr_names = [
                'compute_client',
                'identity_client',
                'identity_v3_client',
                'glance_client',
                'glance_client_v1',
                'volume_client',
                'heat_client',
                'murano_client',
                'sahara_client',
                'ceilometer_client',
                'neutron_client',
                'ironic_client',
                'aodh_client',
                'artifacts_client',
                'murano_art_client'
            ]

    def _get_compute_client(self, username=None, password=None,
                            tenant_name=None):
        if not username:
            username = self.config.identity.admin_username
        if not password:
            password = self.config.identity.admin_password
        if not tenant_name:
            tenant_name = self.config.identity.admin_tenant_name

        if None in (username, password, tenant_name):
            msg = ("Missing required credentials for identity client. "
                   "username: {username}, password: {password}, "
                   "tenant_name: {tenant_name}").format(
                       username=username,
                       password=password,
                       tenant_name=tenant_name, )
            raise exceptions.InvalidConfiguration(msg)

        auth_url = self.config.identity.uri

        client_args = (username, password, tenant_name, auth_url)

        # Create our default Nova client to use in testing
        service_type = self.config.compute.catalog_type
        return novaclient.client.Client(self.NOVACLIENT_VERSION,
                                        *client_args,
                                        service_type=service_type,
                                        no_cache=True,
                                        insecure=True,
                                        endpoint_type='publicURL')

    def _get_glance_client(self, version=2, username=None, password=None,
                           tenant_name=None):
        if not username:
            username = self.config.identity.admin_username
        if not password:
            password = self.config.identity.admin_password
        if not tenant_name:
            tenant_name = self.config.identity.admin_tenant_name

        keystone = self._get_identity_client(username, password, tenant_name)
        try:
            endpoint = keystone.service_catalog.url_for(
                service_type='image',
                endpoint_type='publicURL')
        except keystoneclient.exceptions.EndpointNotFound:
            LOG.warning('Can not initialize glance client')
            return None
        return glanceclient.client.Client(version, endpoint=endpoint,
                                          token=keystone.auth_token,
                                          insecure=True)

    def _get_volume_client(self, username=None, password=None,
                           tenant_name=None):
        if not username:
            username = self.config.identity.admin_username
        if not password:
            password = self.config.identity.admin_password
        if not tenant_name:
            tenant_name = self.config.identity.admin_tenant_name

        auth_url = self.config.identity.uri
        return cinderclient.client.Client(self.CINDERCLIENT_VERSION,
                                          username,
                                          password,
                                          tenant_name,
                                          auth_url,
                                          insecure=True,
                                          endpoint_type='publicURL')

    def _get_identity_client(self, username=None, password=None,
                             tenant_name=None, version=None):
        if not username:
            username = self.config.identity.admin_username
        if not password:
            password = self.config.identity.admin_password
        if not tenant_name:
            tenant_name = self.config.identity.admin_tenant_name

        if None in (username, password, tenant_name):
            msg = ("Missing required credentials for identity client. "
                   "username: {username}, password: {password}, "
                   "tenant_name: {tenant_name}").format(
                       username=username,
                       password=password,
                       tenant_name=tenant_name, )
            raise exceptions.InvalidConfiguration(msg)

        auth_url = self.config.identity.uri

        if not version or version == 2:
            return keystoneclient.v2_0.client.Client(username=username,
                                                     password=password,
                                                     tenant_name=tenant_name,
                                                     auth_url=auth_url,
                                                     insecure=True)
        elif version == 3:
            helper_list = auth_url.rstrip("/").split("/")
            helper_list[-1] = "v3/"
            auth_url = "/".join(helper_list)

            return keystoneclient.v3.client.Client(username=username,
                                                   password=password,
                                                   project_name=tenant_name,
                                                   auth_url=auth_url,
                                                   insecure=True)
        else:
            LOG.warning("Version:{0} for keystoneclient is not "
                        "supported with OSTF".format(version))

    def _get_heat_client(self, username=None, password=None,
                         tenant_name=None):
        if not username:
            username = self.config.identity.admin_username
        if not password:
            password = self.config.identity.admin_password
        if not tenant_name:
            tenant_name = self.config.identity.admin_tenant_name
        keystone = self._get_identity_client(username, password, tenant_name)
        token = keystone.auth_token
        try:
            endpoint = keystone.service_catalog.url_for(
                service_type='orchestration',
                endpoint_type='publicURL')
        except keystoneclient.exceptions.EndpointNotFound:
            LOG.warning('Can not initialize heat client, endpoint not found')
            return None
        else:
            return heatclient.v1.client.Client(endpoint=endpoint,
                                               token=token,
                                               insecure=True)

    def _get_murano_client(self, artifacts=False):
        """This method returns Murano API client
        """
        keystone = self._get_identity_client(
            self.config.identity.admin_username,
            self.config.identity.admin_password,
            self.config.identity.admin_tenant_name)
        # Get xAuth token from Keystone
        self.token_id = keystone.auth_token

        try:
            endpoint = keystone.service_catalog.url_for(
                service_type='application-catalog',
                endpoint_type='publicURL')
        except keystoneclient.exceptions.EndpointNotFound:
            LOG.warning('Endpoint for Murano service '
                        'not found. Murano client cannot be initialized.')
            return

        if artifacts:
            return muranoclient.v1.client.Client(
                endpoint,
                token=self.token_id,
                insecure=True, artifacts_client=self.artifacts_client)
        else:
            return muranoclient.v1.client.Client(
                endpoint,
                token=self.token_id,
                insecure=True)

    def _get_sahara_client(self):
        sahara_api_version = self.config.sahara.api_version

        keystone = self._get_identity_client()
        try:
            sahara_url = keystone.service_catalog.url_for(
                service_type='data-processing', endpoint_type='publicURL')
        except keystoneclient.exceptions.EndpointNotFound:
            LOG.warning('Endpoint for Sahara service '
                        'not found. Sahara client cannot be initialized.')
            return None
        auth_token = keystone.auth_token

        return saharaclient.client.Client(sahara_api_version,
                                          sahara_url=sahara_url,
                                          input_auth_token=auth_token,
                                          insecure=True)

    def _get_ceilometer_client(self):
        keystone = self._get_identity_client()
        try:
            endpoint = keystone.service_catalog.url_for(
                service_type='metering',
                endpoint_type='publicURL')
        except keystoneclient.exceptions.EndpointNotFound:
            LOG.warning('Can not initialize ceilometer client')
            return None

        return ceilometerclient.v2.Client(endpoint=endpoint, insecure=True,
                                          verify=False,
                                          token=lambda: keystone.auth_token)

    def _get_neutron_client(self, version='2.0'):
        keystone = self._get_identity_client()

        try:
            endpoint = keystone.service_catalog.url_for(
                service_type='network',
                endpoint_type='publicURL')
        except keystoneclient.exceptions.EndpointNotFound:
            LOG.warning('Can not initialize neutron client')
            return None

        return neutronclient.neutron.client.Client(version,
                                                   token=keystone.auth_token,
                                                   endpoint_url=endpoint,
                                                   insecure=True)

    def _get_ironic_client(self, version='1'):
        keystone = self._get_identity_client()
        try:
            endpoint = keystone.service_catalog.url_for(
                service_type='baremetal',
                endpoint_type='publicURL')
        except keystoneclient.exceptions.EndpointNotFound:
            LOG.warning('Can not initialize ironic client')
            return None

        return ironicclient.client.get_client(
            version,
            os_auth_token=keystone.auth_token,
            ironic_url=endpoint, insecure=True)

    def _get_artifacts_client(self, version='1'):
        keystone = self._get_identity_client()
        try:
            endpoint = keystone.service_catalog.url_for(
                service_type='artifact',
                endpoint_type='publicURL')
        except keystoneclient.exceptions.EndpointNotFound:
            LOG.warning('Can not initialize artifacts client')
            return None
        return art_client.Client(endpoint=endpoint,
                                 type_name='murano',
                                 type_version=version,
                                 token=keystone.auth_token,
                                 insecure=True)

    def _get_aodh_client(self, version='2'):
        username = self.config.identity.admin_username
        password = self.config.identity.admin_password
        tenant = self.config.identity.admin_tenant_name
        auth_url = self.config.identity.uri
        auth = keystoneauth1.identity.v2.Password(
            auth_url=auth_url, username=username,
            password=password, tenant_name=tenant)
        sess = keystoneauth1.session.Session(auth=auth, verify=False)
        return aodhclient.client.Client(version, sess)


class OfficialClientTest(fuel_health.test.TestCase):
    manager_class = OfficialClientManager

    @classmethod
    def find_micro_flavor(cls):
        return [flavor for flavor in cls.compute_client.flavors.list()
                if flavor.name == 'm1.micro']

    def _create_volume(self, client, expected_state=None, **kwargs):
        kwargs.setdefault('name', rand_name('ostf-test-volume'))
        kwargs.setdefault('size', 1)
        volume = client.volumes.create(**kwargs)
        self.set_resource(kwargs['name'], volume)
        if expected_state:
            def await_state():
                if client.volumes.get(volume.id).status == expected_state:
                    return True

            fuel_health.test.call_until_true(await_state, 50, 1)

        return volume

    def _create_snapshot(self, client, volume_id, expected_state=None,
                         **kwargs):
        kwargs.setdefault('name', rand_name('ostf-test-volume'))
        snapshot = client.volume_snapshots.create(volume_id, **kwargs)
        self.set_resource(kwargs['name'], snapshot)
        if expected_state:
            def await_state():
                if client.volume_snapshots.get(
                        snapshot.id).status == expected_state:
                    return True
            fuel_health.test.call_until_true(await_state, 50, 1)

        return snapshot

    def get_image_from_name(self, img_name=None):
        if img_name:
            image_name = img_name
        else:
            image_name = self.manager.config.compute.image_name
        images = [i for i in self.compute_client.images.list()
                  if i.status.lower() == 'active']
        image_id = ''
        LOG.debug(images)
        if images:
            for im in images:
                LOG.debug(im.name)
                if (im.name and
                        im.name.strip().lower() ==
                        image_name.strip().lower()):
                    image_id = im.id
        if not image_id:
            raise exceptions.ImageFault
        return image_id

    def _delete_server(self, server):
        LOG.debug("Deleting server.")
        self.compute_client.servers.delete(server)

        def is_deletion_complete():
            try:
                server.get()
            except Exception as exc:
                if exc.__class__.__name__ == 'NotFound':
                    return True
                LOG.exception(exc)
                return False

        fuel_health.test.call_until_true(
            is_deletion_complete, 20, 10)

    def retry_command(self, retries, timeout, method, *args, **kwargs):
        for i in range(retries):
            try:
                result = method(*args, **kwargs)
                LOG.debug("Command execution successful. "
                          "Result {0}".format(result))
                if 'False' in result:
                    raise exceptions.SSHExecCommandFailed(
                        'Command {0} finishes with False'.format(
                            kwargs.get('command')))
                else:
                    return result
            except Exception as exc:
                LOG.debug("%s. Another effort needed." % exc)
                time.sleep(timeout)
        if 'ping' not in kwargs.get('command'):
            self.fail('Execution command on Instance fails '
                      'with unexpected result. ')
        self.fail("Instance is not reachable by IP.")

    def get_availability_zone(self, image_id=None):
        disk = self.glance_client_v1.images.get(image_id).disk_format
        if disk == 'vmdk':
            az_name = 'vcenter'
        else:
            az_name = 'nova'
        return az_name

    def check_clients_state(self):
        if not self.manager.clients_initialized:
            LOG.debug("Unable to initialize Keystone client: {trace}".format(
                trace=self.manager.traceback))
            if self.manager.keystone_error_message:
                self.fail(self.manager.keystone_error_message)
            else:
                self.fail("Keystone client is not available. Please, refer"
                          " to OpenStack logs to fix this problem")

    def check_image_exists(self):
        try:
            self.get_image_from_name()
        except exceptions.ImageFault as exc:
            LOG.debug(exc)
            self.fail("{image} image not found. Please, download "
                      "http://download.cirros-cloud.net/0.3.1/"
                      "cirros-0.3.1-x86_64-disk.img image and "
                      "register it in Glance with name '{image}' as "
                      "'admin' tenant."
                      .format(image=self.manager.config.compute.image_name)
                      )
        except nova_exc.ClientException:
            LOG.exception()
            self.fail("Image can not be retrieved. "
                      "Please refer to OpenStack logs for more details")

    @classmethod
    def _clean_flavors(cls):
        if cls.flavors:
            for flavor in cls.flavors:
                try:
                    cls.compute_client.flavors.delete(flavor)
                except Exception as exc:
                    cls.error_msg.append(exc)
                    LOG.exception(exc)

    @classmethod
    def _clean_images(cls):
        if cls.images:
            for image_id in cls.images:
                try:
                    cls.glance_client.images.delete(image_id)
                except Exception as exc:
                    cls.error_msg.append(exc)
                    LOG.exception(exc)

    @classmethod
    def tearDownClass(cls):
        cls.error_msg = []
        while cls.os_resources:
            thing = cls.os_resources.pop()
            LOG.debug("Deleting %r from shared resources of %s" %
                      (thing, cls.__name__))

            try:
                # OpenStack resources are assumed to have a delete()
                # method which destroys the resource...
                thing.delete()
            except Exception as exc:
                # If the resource is already missing, mission accomplished.
                if exc.__class__.__name__ == 'NotFound':
                    continue
                cls.error_msg.append(exc)
                LOG.exception(exc)

            def is_deletion_complete():
                # Deletion testing is only required for objects whose
                # existence cannot be checked via retrieval.
                if isinstance(thing, dict):
                    return True
                try:
                    thing.get()
                except Exception as exc:
                    # Clients are expected to return an exception
                    # called 'NotFound' if retrieval fails.
                    if exc.__class__.__name__ == 'NotFound':
                        return True
                    cls.error_msg.append(exc)
                    LOG.exception(exc)
                return False

            # Block until resource deletion has completed or timed-out
            fuel_health.test.call_until_true(is_deletion_complete, 20, 10)


class NovaNetworkScenarioTest(OfficialClientTest):
    """Base class for nova network scenario tests."""

    @classmethod
    def setUpClass(cls):
        super(NovaNetworkScenarioTest, cls).setUpClass()
        if cls.manager.clients_initialized:
            cls.host = cls.config.compute.online_controllers
            cls.usr = cls.config.compute.controller_node_ssh_user
            cls.pwd = cls.config.compute.controller_node_ssh_password
            cls.key = cls.config.compute.path_to_private_key
            cls.timeout = cls.config.compute.ssh_timeout
            cls.tenant_id = cls.manager._get_identity_client(
                cls.config.identity.admin_username,
                cls.config.identity.admin_password,
                cls.config.identity.admin_tenant_name).tenant_id
            cls.network = []
            cls.floating_ips = []
            cls.error_msg = []
            cls.flavors = []
            cls.images = []
            cls.ports = []
            cls.private_net = cls.config.network.private_net

    def setUp(self):
        super(NovaNetworkScenarioTest, self).setUp()
        self.check_clients_state()

    def _run_ssh_cmd(self, cmd):
        """Open SSH session with Controller and execute command."""
        if not self.host:
            self.fail('Wrong test configuration: '
                      '"online_controllers" parameter is empty.')

        try:
            sshclient = f_ssh.Client(self.host[0], self.usr, self.pwd,
                                     key_filename=self.key,
                                     timeout=self.timeout)
            return sshclient.exec_longrun_command(cmd)
        except Exception:
            LOG.exception()
            self.fail("%s command failed." % cmd)

    def _create_keypair(self, client, namestart='ost1_test-keypair-smoke-'):
        kp_name = rand_name(namestart)
        keypair = client.keypairs.create(kp_name)
        self.set_resource(kp_name, keypair)
        self.verify_response_body_content(keypair.id,
                                          kp_name,
                                          'Keypair creation failed')
        return keypair

    def _create_security_group(
            self, client, namestart='ost1_test-secgroup-smoke-netw'):
        # Create security group
        sg_name = rand_name(namestart)
        sg_desc = sg_name + " description"
        secgroup = client.security_groups.create(sg_name, sg_desc)
        self.verify_response_body_content(secgroup.name,
                                          sg_name,
                                          "Security group creation failed")
        self.verify_response_body_content(secgroup.description,
                                          sg_desc,
                                          "Security group creation failed")

        # Add rules to the security group

        # These rules are intended to permit inbound ssh and icmp
        # traffic from all sources, so no group_id is provided.
        # Setting a group_id would only permit traffic from ports
        # belonging to the same security group.
        rulesets = [
            {
                # ssh
                'ip_protocol': 'tcp',
                'from_port': 22,
                'to_port': 22,
                'cidr': '0.0.0.0/0',
            },
            {
                # ping
                'ip_protocol': 'icmp',
                'from_port': -1,
                'to_port': -1,
                'cidr': '0.0.0.0/0',
            }
        ]
        for ruleset in rulesets:
            try:
                client.security_group_rules.create(secgroup.id, **ruleset)
            except Exception:
                LOG.exception()
                self.fail("Failed to create rule in security group.")

        return secgroup

    def _create_network(self, label='ost1_test-network-smoke-'):
        n_label = rand_name(label)
        cidr = self.config.network.tenant_network_cidr
        networks = self.compute_client.networks.create(
            label=n_label, cidr=cidr)
        self.set_resource(n_label, networks)
        self.network.append(networks)
        self.verify_response_body_content(networks.label,
                                          n_label,
                                          "Network creation failed")
        return networks

    def _create_port(self, net_id, vnic_type, label='ost1_test-port-'):
        n_label = rand_name(label)
        port_data = {
            'name': n_label,
            'binding:vnic_type': vnic_type,
            'network_id': net_id,
        }
        port = self.neutron_client.create_port({'port': port_data})
        self.set_resource(n_label, port)
        self.ports.append(port)
        LOG.debug(port)
        self.verify_response_body_content(port['port']['name'],
                                          n_label,
                                          "Port creation failed")
        return port

    @classmethod
    def _clear_networks(cls):
        try:
            for net in cls.network:
                cls.compute_client.networks.delete(net)
        except Exception as exc:
            cls.error_msg.append(exc)
            LOG.exception(exc)

    @classmethod
    def _clear_security_groups(cls):
        try:
            sec_groups = cls.compute_client.security_groups.list()
            [cls.compute_client.security_groups.delete(group)
             for group in sec_groups
             if 'ost1_test-' in group.name]
        except Exception as exc:
            cls.error_msg.append(exc)
            LOG.exception(exc)

    def _list_networks(self):
        nets = self.compute_client.networks.list()
        return nets

    def _create_server(self, client, name, security_groups=None,
                       flavor_id=None, net_id=None, img_name=None,
                       data_file=None, az_name=None, port=None):
        create_kwargs = {}

        if img_name:
            base_image_id = self.get_image_from_name(img_name=img_name)
        else:
            base_image_id = self.get_image_from_name()

        if not az_name:
            az_name = self.get_availability_zone(image_id=base_image_id)

        if not flavor_id:
            if not self.find_micro_flavor():
                self.fail("Flavor for tests was not created. Seems that "
                          "something is wrong with nova services.")
            else:
                flavor = self.find_micro_flavor()[0]

            flavor_id = flavor.id
        if not security_groups:
            security_groups = [self._create_security_group(
                self.compute_client).name]
        if 'neutron' in self.config.network.network_provider:
            create_kwargs['nics'] = []
            if net_id:
                network = [net_id]
            else:
                network = [net.id for net in
                           self.compute_client.networks.list()
                           if net.label == self.private_net]

            if port:
                create_kwargs['nics'].append({'port-id': port['port']['id']})
            else:
                if network:
                    create_kwargs['nics'].append({'net-id': network[0]})
                else:
                    self.fail("Default private network '{0}' isn't present. "
                              "Please verify it is properly created.".
                              format(self.private_net))

        create_kwargs['security_groups'] = security_groups

        server = client.servers.create(name, base_image_id,
                                       flavor_id, files=data_file,
                                       availability_zone=az_name,
                                       **create_kwargs)
        self.verify_response_body_content(server.name,
                                          name,
                                          "Instance creation failed")
        self.set_resource(name, server)
        self.status_timeout(client.servers, server.id, 'ACTIVE')
        # The instance retrieved on creation is missing network
        # details, necessitating retrieval after it becomes active to
        # ensure correct details.
        server = client.servers.get(server.id)
        self.set_resource(name, server)
        return server

    def _load_file(self, file_name):
        path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "etc", file_name)
        with open(path) as f:
            return f.read()

    def _create_floating_ip(self):
        floating_ips_pool = self.compute_client.floating_ip_pools.list()

        if floating_ips_pool:
            floating_ip = self.compute_client.floating_ips.create(
                pool=floating_ips_pool[0].name)
            return floating_ip
        else:
            self.fail('No available floating IP found')

    def _assign_floating_ip_to_instance(self, client, server, floating_ip):
        try:
            client.servers.add_floating_ip(server, floating_ip)
        except Exception:
            LOG.exception()
            self.fail('Can not assign floating ip to instance')

    @classmethod
    def _clean_floating_ips(cls):
        if cls.floating_ips:
            for ip in cls.floating_ips:
                LOG.info('Floating_ip_for_deletion{0}'.format(
                    cls.floating_ips))
                try:
                    cls.compute_client.floating_ips.delete(ip)
                except Exception as exc:
                    cls.error_msg.append(exc)
                    LOG.exception(exc)

    def _ping_ip_address(self, ip_address, timeout, retries):
        def ping():
            cmd = "ping -q -c1 -w10 %s" % ip_address

            if self.host:
                try:
                    ssh = f_ssh.Client(self.host[0],
                                       self.usr, self.pwd,
                                       key_filename=self.key,
                                       timeout=timeout)
                except Exception:
                    LOG.exception()

                return self.retry_command(retries=retries[0],
                                          timeout=retries[1],
                                          method=ssh.exec_command,
                                          command=cmd)

            else:
                self.fail('Wrong tests configurations, one from the next '
                          'parameters are empty controller_node_name or '
                          'controller_node_ip ')

        # TODO(???) Allow configuration of execution and sleep duration.
        return fuel_health.test.call_until_true(ping, 40, 1)

    def _ping_ip_address_from_instance(self, ip_address, timeout,
                                       retries, viaHost=None):
        def ping():
            if not (self.host or viaHost):
                self.fail('Wrong tests configurations, one from the next '
                          'parameters are empty controller_node_name or '
                          'controller_node_ip ')
            try:
                host = viaHost or self.host[0]
                LOG.debug('Get ssh to instance')
                ssh = f_ssh.Client(host,
                                   self.usr, self.pwd,
                                   key_filename=self.key,
                                   timeout=timeout)

            except Exception:
                LOG.exception()

            command = "ping -q -c1 -w10 8.8.8.8"

            return self.retry_command(retries[0], retries[1],
                                      ssh.exec_command_on_vm,
                                      command=command,
                                      user='cirros',
                                      password='cubswin:)',
                                      vm=ip_address)

        # TODO(???) Allow configuration of execution and sleep duration.
        return fuel_health.test.call_until_true(ping, 40, 1)

    def _run_command_on_instance(self, ip_address, timeout, retries, cmd,
                                 viaHost=None):
        def run_cmd():
            if not (self.host or viaHost):
                self.fail('Wrong tests configurations, one from the next '
                          'parameters are empty controller_node_name or '
                          'controller_node_ip ')
            try:
                host = viaHost or self.host[0]
                LOG.debug('Get ssh to instance')
                ssh = f_ssh.Client(host,
                                   self.usr, self.pwd,
                                   key_filename=self.key,
                                   timeout=timeout)
                LOG.debug('Host is {0}'.format(host))

            except Exception:
                LOG.exception()

            return self.retry_command(retries[0], retries[1],
                                      ssh.exec_command_on_vm,
                                      command=cmd,
                                      user='cirros',
                                      password='cubswin:)',
                                      vm=ip_address)

        # TODO(???) Allow configuration of execution and sleep duration.

        return fuel_health.test.call_until_true(run_cmd, 40, 1)

    def _check_vm_connectivity(self, ip_address, timeout, retries):
        self.assertTrue(self._ping_ip_address(ip_address, timeout, retries),
                        "Timed out waiting for %s to become "
                        "reachable. Please, check Network "
                        "configuration" % ip_address)

    def _check_connectivity_from_vm(self, ip_address,
                                    timeout, retries,
                                    viaHost=None):
        self.assertTrue(self._ping_ip_address_from_instance(ip_address,
                                                            timeout, retries,
                                                            viaHost=viaHost),
                        "Timed out waiting for %s to become "
                        "reachable. Please, check Network "
                        "configuration" % ip_address)

    def _run_command_from_vm(self, ip_address,
                             timeout, retries, cmd, viaHost=None):
        self.assertTrue(
            self._run_command_on_instance(
                ip_address, timeout, retries, cmd, viaHost=viaHost),
            "Timed out waiting for %s to become reachable. "
            "Please, check Network configuration" % ip_address)

    def get_compute_hostname(self):
        return self.compute_client.hypervisors.list()

    def get_instance_details(self, instance):
        return self.compute_client.servers.get(instance)

    def get_instance_host(self, instance):
        return getattr(self.get_instance_details(instance),
                       "OS-EXT-SRV-ATTR:host")

    def get_free_host(self, instance):
        current_host = self.get_instance_host(instance)
        LOG.debug('Current host is {0}'.format(current_host))
        available_hosts = self.get_compute_hostname()
        for host in available_hosts:
            hostname = host.service.get('host')
            if host.hypervisor_type != 'VMware vCenter Server' and \
               hostname != current_host:
                return hostname

    def migrate_instance(self, instance, host_to):
        instance.live_migrate(host_to)
        self.status_timeout(self.compute_client.servers,
                            instance.id, 'ACTIVE')
        return instance

    @classmethod
    def tearDownClass(cls):
        super(NovaNetworkScenarioTest, cls).tearDownClass()
        if cls.manager.clients_initialized:
            cls._clean_floating_ips()
            cls._clear_security_groups()
            cls._clear_networks()


class PlatformServicesBaseClass(NovaNetworkScenarioTest):

    def get_max_free_compute_node_ram(self, min_required_ram_mb):
        max_free_ram_mb = 0
        for hypervisor in self.compute_client.hypervisors.list():
            if hypervisor.free_ram_mb >= min_required_ram_mb:
                return hypervisor.free_ram_mb
            else:
                if hypervisor.free_ram_mb > max_free_ram_mb:
                    max_free_ram_mb = hypervisor.free_ram_mb

        return max_free_ram_mb

    # Methods for creating network resources.
    def create_network_resources(self):
        """This method creates network resources.

        It creates a network, an internal subnet on the network, a router and
        links the network to the router. All resources created by this method
        will be automatically deleted.
        """

        private_net_id = None
        floating_ip_pool = None

        if self.config.network.network_provider == 'neutron':
            ext_net = self.find_external_network()
            net_name = data_utils.rand_name('ostf-platform-service-net-')
            net = self._create_net(net_name)
            subnet = self._create_internal_subnet(net)
            router_name = data_utils.rand_name('ostf-platform-service-router-')
            router = self._create_router(router_name, ext_net)
            self.neutron_client.add_interface_router(
                router['id'], {'subnet_id': subnet['id']})
            self.addCleanup(self.neutron_client.remove_interface_router,
                            router['id'], {'subnet_id': subnet['id']})
            self.addCleanup(
                self.neutron_client.remove_gateway_router, router['id'])

            private_net_id = net['id']
            floating_ip_pool = ext_net['id']
        else:
            if not self.config.compute.auto_assign_floating_ip:
                fl_ip_pools = self.compute_client.floating_ip_pools.list()
                floating_ip_pool = next(fl_ip_pool.name
                                        for fl_ip_pool in fl_ip_pools
                                        if fl_ip_pool.is_loaded())

        return private_net_id, floating_ip_pool

    def find_external_network(self):
        """This method finds the external network."""

        LOG.debug('Finding external network...')
        for net in self.neutron_client.list_networks()['networks']:
            if net['router:external']:
                LOG.debug('External network found. Ext net: {0}'.format(net))
                return net

        self.fail('Cannot find the external network.')

    def _create_net(self, name):
        """This method creates a network.

        All resources created by this method will be automatically deleted.
        """

        LOG.debug('Creating network with name "{0}"...'.format(name))
        net_body = {
            'network': {
                'name': name,
                'tenant_id': self.tenant_id
            }
        }
        net = self.neutron_client.create_network(net_body)['network']
        self.addCleanup(self.neutron_client.delete_network, net['id'])
        LOG.debug('Network "{0}" has been created. Net: {1}'.format(name, net))

        return net

    def _create_internal_subnet(self, net):
        """This method creates an internal subnet on the network.

        All resources created by this method will be automatically deleted.
        """

        LOG.debug('Creating subnet...')
        subnet_body = {
            'subnet': {
                'network_id': net['id'],
                'ip_version': 4,
                'cidr': '10.1.7.0/24',
                'tenant_id': self.tenant_id
            }
        }
        subnet = self.neutron_client.create_subnet(subnet_body)['subnet']
        self.addCleanup(self.neutron_client.delete_subnet, subnet['id'])
        LOG.debug('Subnet has been created. Subnet: {0}'.format(subnet))

        return subnet

    def _create_router(self, name, ext_net):
        """This method creates a router.

        All resources created by this method will be automatically deleted.
        """

        LOG.debug('Creating router with name "{0}"...'.format(name))
        router_body = {
            'router': {
                'name': name,
                'external_gateway_info': {
                    'network_id': ext_net['id']
                },
                'tenant_id': self.tenant_id
            }
        }
        router = self.neutron_client.create_router(router_body)['router']
        self.addCleanup(self.neutron_client.delete_router, router['id'])
        LOG.debug('Router "{0}" has been created. '
                  'Router: {1}'.format(name, router))

        return router

    def get_info_about_available_resources(self, min_ram, min_hdd, min_vcpus):
        """This function allows to get the information about resources.

        We need to collect the information about available RAM, HDD and vCPUs
        on all compute nodes for cases when we will create more than 1 VM.

        This function returns the count of VMs with required parameters which
        we can successfully run on existing cloud.
        """
        vms_count = 0
        for hypervisor in self.compute_client.hypervisors.list():
            if hypervisor.free_ram_mb >= min_ram:
                if hypervisor.free_disk_gb >= min_hdd:
                    if hypervisor.vcpus - hypervisor.vcpus_used >= min_vcpus:
                        # We need to determine how many VMs we can run
                        # on this hypervisor
                        free_cpu = hypervisor.vcpus - hypervisor.vcpus_used
                        k1 = int(hypervisor.free_ram_mb / min_ram)
                        k2 = int(hypervisor.free_disk_gb / min_hdd)
                        k3 = int(free_cpu / min_vcpus)
                        vms_count += min(k1, k2, k3)
        return vms_count

    # Methods for finding and checking Sahara images.
    def find_and_check_image(self, tag_plugin, tag_version):
        """This method finds a correctly registered Sahara image.

        It finds a Sahara image by specific tags and checks whether the image
        is correctly registered or not.
        """

        LOG.debug('Finding and checking image for Sahara...')
        image = self._find_image_by_tags(tag_plugin, tag_version)
        if image is not None:
            self.ssh_username = image.metadata.get('_sahara_username', None)
            msg = 'Image "{0}" is registered for Sahara with username "{1}".'

            if self.ssh_username is not None:
                LOG.debug(msg.format(image.name, self.ssh_username))
                return image.id

        LOG.debug('Image is not correctly registered or it is not '
                  'registered at all. Correct image for Sahara not found.')

    def _find_image_by_tags(self, tag_plugin, tag_version):
        """This method finds a Sahara image by specific tags."""

        tag_plug = '_sahara_tag_' + tag_plugin
        tag_ver = '_sahara_tag_' + tag_version
        msg = 'Image with tags "{0}" and "{1}" found. Image name is "{2}".'

        for image in self.compute_client.images.list():
            if image.status.lower() == 'active':
                if tag_plug in image.metadata and tag_ver in image.metadata:
                    LOG.debug(msg.format(tag_plugin, tag_version, image.name))
                    return image
        LOG.debug('Image with tags "{0}" and "{1}" '
                  'not found.'.format(tag_plugin, tag_version))

    # Method for checking whether or not resource is deleted.
    def is_resource_deleted(self, get_method):
        """This method checks whether or not the resource is deleted.

        The API request is wrapped in the try/except block to correctly handle
        the "404 Not Found" exception. If the resource doesn't exist, this
        method will return True. Otherwise it will return False.
        """

        try:
            get_method()
        except Exception as exc:
            exc_msg = exc.message.lower()
            if ('not found' in exc_msg) or ('could not be found' in exc_msg):
                return True
            self.fail(exc.message)

        return False

    # Methods for deleting resources.
    def delete_resource(self, delete_method, get_method=None, timeout=300,
                        sleep=5):
        """This method deletes the resource by its ID and checks whether
        the resource is really deleted or not.
        """

        try:
            delete_method()
        except Exception as exc:
            LOG.warning(exc.message)
            return
        if get_method:
            self._wait_for_deletion(get_method, timeout, sleep)

    def _wait_for_deletion(self, get_method, timeout, sleep):
        """This method waits for the resource deletion."""

        start = time.time()
        while time.time() - start < timeout:
            if self.is_resource_deleted(get_method):
                return
            time.sleep(sleep)

        self.fail('Request timed out. '
                  'Timed out while waiting for one of the test resources '
                  'to delete within {0} seconds.'.format(timeout))


class SanityChecksTest(OfficialClientTest):
    """Base class for openstack sanity tests."""

    _enabled = True

    @classmethod
    def check_preconditions(cls):
        cls._enabled = True
        if cls.config.network.neutron_available:
            cls._enabled = False
        else:
            cls._enabled = True
            # ensure the config says true
            try:
                cls.compute_client.networks.list()
            except exceptions.EndpointNotFound:
                cls._enabled = False

    def setUp(self):
        super(SanityChecksTest, self).setUp()
        self.check_clients_state()
        if not self._enabled:
            self.skipTest('Nova Networking is not available')

    @classmethod
    def setUpClass(cls):
        super(SanityChecksTest, cls).setUpClass()
        if cls.manager.clients_initialized:
            cls.tenant_id = cls.manager._get_identity_client(
                cls.config.identity.admin_username,
                cls.config.identity.admin_password,
                cls.config.identity.admin_tenant_name).tenant_id
            cls.network = []
            cls.floating_ips = []

    @classmethod
    def tearDownClass(cls):
        pass

    def _list_instances(self, client):
        instances = client.servers.list()
        return instances

    def _list_images(self, client):
        images = client.images.list()
        return images

    def _list_volumes(self, client):
        volumes = client.volumes.list(detailed=False)
        return volumes

    def _list_snapshots(self, client):
        snapshots = client.volume_snapshots.list(detailed=False)
        return snapshots

    def _list_flavors(self, client):
        flavors = client.flavors.list()
        return flavors

    def _list_limits(self, client):
        limits = client.limits.get()
        return limits

    def _list_services(self, client, host=None, binary=None):
        services = client.services.list(host=host, binary=binary)
        return services

    def _list_users(self, client):
        users = client.users.list()
        return users

    def _list_networks(self, client):
        if hasattr(client, 'list_networks'):
            return client.list_networks()
        else:
            return client.networks.list()

    def _list_stacks(self, client):
        return client.stacks.list()


class SmokeChecksTest(OfficialClientTest):
    """Base class for openstack smoke tests."""

    @classmethod
    def setUpClass(cls):
        super(SmokeChecksTest, cls).setUpClass()
        if cls.manager.clients_initialized:
            cls.tenant_id = cls.manager._get_identity_client(
                cls.config.identity.admin_username,
                cls.config.identity.admin_password,
                cls.config.identity.admin_tenant_name).tenant_id
            cls.build_interval = cls.config.volume.build_interval
            cls.build_timeout = cls.config.volume.build_timeout
            cls.created_flavors = []
            cls.error_msg = []
            cls.private_net = cls.config.network.private_net
        else:
            cls.proceed = False

    def setUp(self):
        super(SmokeChecksTest, self).setUp()
        self.check_clients_state()

    def _create_flavors(self, client, ram, disk, vcpus=1, use_huge_page=False):
        name = rand_name('ost1_test-flavor-')
        flavorid = rand_int_id()
        exist_ids = [flavor.id for flavor
                     in self.compute_client.flavors.list()]

        if flavorid in exist_ids:
            flavorid = name + rand_int_id()
        flavor = client.flavors.create(name=name, ram=ram, disk=disk,
                                       vcpus=vcpus, flavorid=flavorid)
        self.created_flavors.append(flavor)

        if use_huge_page:
            # change flavor settings use hugepage
            flavor_metadata = flavor.get_keys()
            logging.debug(flavor_metadata)
            flavor_metadata['hw:mem_page_size'] = '2048'
            flavor.set_keys(flavor_metadata)

        return flavor

    def _delete_flavors(self, client, flavor):
        self.created_flavors.remove(flavor)
        client.flavors.delete(flavor)

    def _create_tenant(self, client):
        name = rand_name('ost1_test-tenant-')
        tenant = client.tenants.create(name)
        self.set_resource(name, tenant)
        return tenant

    def _create_user(self, client, tenant_id):
        password = "123456"
        email = "test@test.com"
        name = rand_name('ost1_test-user-')
        user = client.users.create(name, password, email, tenant_id)
        self.set_resource(name, user)
        return user

    def _create_role(self, client):
        name = rand_name('ost1_test-role-')
        role = client.roles.create(name)
        self.set_resource(name, role)
        return role

    def _create_boot_volume(self, client, img_name=None, **kwargs):
        name = rand_name('ost1_test-bootable-volume')

        imageRef = self.get_image_from_name(img_name=img_name)

        LOG.debug(
            'Image ref is {0} for volume {1}'.format(imageRef, name))
        return self._create_volume(
            client, name=name, imageRef=imageRef, **kwargs)

    def create_instance_from_volume(self, client, volume):
        if not self.find_micro_flavor():
            self.fail("m1.micro flavor was not created.")

        name = rand_name('ost1_test-boot-volume-instance')
        base_image_id = self.get_image_from_name()
        bd_map = {'vda': volume.id + ':::0'}
        az_name = self.get_availability_zone(image_id=base_image_id)
        if 'neutron' in self.config.network.network_provider:
            network = [net.id for net in
                       self.compute_client.networks.list()
                       if net.label == self.private_net]
            if network:
                create_kwargs = {'block_device_mapping': bd_map,
                                 'nics': [{'net-id': network[0]}]}
            else:
                self.fail("Default private network '{0}' isn't present. "
                          "Please verify it is properly created.".
                          format(self.private_net))
            server = client.servers.create(
                name, base_image_id, self.find_micro_flavor()[0].id,
                availability_zone=az_name,
                **create_kwargs)
        else:
            create_kwargs = {'block_device_mapping': bd_map}
            server = client.servers.create(name, base_image_id,
                                           self.find_micro_flavor()[0].id,
                                           availability_zone=az_name,
                                           **create_kwargs)

        self.verify_response_body_content(server.name,
                                          name,
                                          "Instance creation failed")
        # The instance retrieved on creation is missing network
        # details, necessitating retrieval after it becomes active to
        # ensure correct details.
        server = self._wait_server_param(client, server, 'addresses', 5, 1)
        self.set_resource(name, server)
        return server

    def _create_server(self, client, img_name=None):
        if not self.find_micro_flavor():
            self.fail("m1.micro flavor was not created.")

        name = rand_name('ost1_test-volume-instance')

        base_image_id = self.get_image_from_name(img_name=img_name)
        az_name = self.get_availability_zone(image_id=base_image_id)

        if 'neutron' in self.config.network.network_provider:
            network = [net.id for net in
                       self.compute_client.networks.list()
                       if net.label == self.private_net]
            if network:
                create_kwargs = {'nics': [{'net-id': network[0]}]}
            else:
                self.fail("Default private network '{0}' isn't present. "
                          "Please verify it is properly created.".
                          format(self.private_net))
            server = client.servers.create(
                name, base_image_id, self.find_micro_flavor()[0].id,
                availability_zone=az_name,
                **create_kwargs)
        else:
            server = client.servers.create(name, base_image_id,
                                           self.micro_flavors[0].id,
                                           availability_zone=az_name)

        self.verify_response_body_content(server.name,
                                          name,
                                          "Instance creation failed")
        # The instance retrieved on creation is missing network
        # details, necessitating retrieval after it becomes active to
        # ensure correct details.
        server = self._wait_server_param(client, server, 'addresses', 5, 1)
        self.set_resource(name, server)
        return server

    def _wait_server_param(self, client, server, param_name,
                           tries=1, timeout=1, expected_value=None):
        while tries:
            val = getattr(server, param_name, None)
            if val:
                if (not expected_value) or (expected_value == val):
                    return server
            time.sleep(timeout)
            server = client.servers.get(server.id)
            tries -= 1
        return server

    def _attach_volume_to_instance(self, volume, instance):
        device = '/dev/vdb'
        attached_volume = self.compute_client.volumes.create_server_volume(
            volume_id=volume.id, server_id=instance, device=device)
        return attached_volume

    def _detach_volume(self, server, volume):
        volume = self.compute_client.volumes.delete_server_volume(
            server_id=server, attachment_id=volume)
        return volume

    def verify_volume_deletion(self, volume):

        def is_volume_deleted():
            try:
                self.compute_client.volumes.get(volume.id)
            except Exception as e:
                if e.__class__.__name__ == 'NotFound':
                    return True
                return False

        fuel_health.test.call_until_true(is_volume_deleted, 20, 10)

    @classmethod
    def tearDownClass(cls):
        super(SmokeChecksTest, cls).tearDownClass()
        if cls.manager.clients_initialized:
            if cls.created_flavors:
                try:
                    cls.compute_client.flavors.delete(cls.created_flavors)
                except Exception:
                    LOG.exception("OSTF test flavor cannot be deleted.")
