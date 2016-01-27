# -*- coding: utf-8 -*-

# Copyright 2015 LIP - Lisbon
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
import webob
import json
import logging

from driver import utils
from driver import parsers

FORMAT = '%(asctime)-15s %(clientip)s %(user)-8s %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger('tcpserver')


def exception_from_response(response):
    """
    # Copyright 2014 CSIC
    Convert an OpenStack V2 Fault into a webob exception.

    Since we are calling the OpenStack API we should process the Faults
    produced by them. Extract the Fault information according to [1] and
    convert it back to a webob exception.

    [1] http://docs.openstack.org/developer/nova/v2/faults.html

    :param response: a webob.Response containing an exception
    :returns: a webob.exc.exception object
    """
    exceptions = {
        400: webob.exc.HTTPBadRequest,
        401: webob.exc.HTTPUnauthorized,
        403: webob.exc.HTTPForbidden,
        404: webob.exc.HTTPNotFound,
        405: webob.exc.HTTPMethodNotAllowed,
        406: webob.exc.HTTPNotAcceptable,
        409: webob.exc.HTTPConflict,
        413: webob.exc.HTTPRequestEntityTooLarge,
        415: webob.exc.HTTPUnsupportedMediaType,
        429: webob.exc.HTTPTooManyRequests,
        500: webob.exc.HTTPInternalServerError,
        501: webob.exc.HTTPNotImplemented,
        503: webob.exc.HTTPServiceUnavailable,
    }
    code = response.status_int
    try:
        message = response.json_body.popitem()[1].get("message")
    except Exception:
        code = 500
        message = "Unknown error happenened processing response %s" % response
    logger.warning('Response exception. HTTP response: %s', code)
    exc = exceptions.get(code, webob.exc.HTTPInternalServerError)
    return exc(explanation=message)

class OpenStackDriver(object):
    """Class to interact with the OS API."""

    def __init__(self, endpoint, port, version, token):
        self.endpoint = endpoint
        self.version = version
        self.port = port
        self.token = token

    @staticmethod
    def get_from_response(response, element, default):
        if response.status_int in [200, 201, 202]:
            logger.debug('HTTP response: %s', response.status_int)
            return response.json_body #.get(element, default)
        else:
            raise exception_from_response(response)

    def _get_req(self, path, method,
                 content_type="application/json",
                 body=None,
                 query_string=""):
        """Return a new Request object to interact with OpenStack.

        This method will create a new request starting with the same WSGI
        environment as the original request, prepared to interact with
        OpenStack. Namely, it will override the script name to match the
        OpenStack version. It will also override the path, content_type and
        body of the request, if any of those keyword arguments are passed.

        :param path: new path for the request
        :param content_type: new content type for the request, defaults to
                             "application/json" if not specified
        :param body: new body for the request
        :param query_string: query string for the request, defaults to an empty
                             query if not specified
        :returns: a Request object
        """
        server = self.endpoint
        port = self.port
        base_url = "/%s" % self.version
        kwargs = {"http_version": "HTTP/1.1", "server_name": server, "server_port": port}
        environ = {"HTTP_X-Auth-Token": self.token}

        new_req = webob.Request.blank(path=path, environ=environ,  base_url=base_url, **kwargs)
        #new_req.script_name = base_url
        new_req.query_string = query_string
        new_req.method = method
        if path is not None:
            new_req.path_info = path
        if content_type is not None:
            new_req.content_type = content_type
        if body is not None:
            new_req.body = utils.utf8(body)


        return new_req

    def _make_get_request(self, path, parameters=None):
        """Create GET request
        This method create a GET Request instance
        :param path: path resource
        :param parameters: parameters to filter results
        """
        query_string = parsers.get_query_string(parameters)
        return self._get_req(path, query_string=query_string, method="GET")

    def _make_create_request(self, path, resource, parameters):#TODO(jorgesece): Create unittest for it
        """Create CREATE request
        This method create a CREATE Request instance
        :param path: path resource
        :param parameters: parameters with values
        """
        body = parsers.make_body(resource, parameters)
        return self._get_req(path, content_type="application/json", body=json.dumps(body), method="POST")

    def _make_delete_request(self, req, path, parameters):
        """Create DELETE request
        This method create a DELETE Request instance
        :param req: the incoming request
        :param path: element location
        """
        param = parsers.translate_parameters(self.translation["network"], parameters)
        id = param["network_id"]
        path = "%s/%s" % (path, id)
        return self._get_req(path, method="DELETE")

    def index(self, path, parameters=None):
        """Get a list of networks.
        This method retrieve a list of network to which the tenant has access.
        :param req: the incoming request
        :param parameters: parameters to filter results
        """
        resource = utils.get_resource_from_path(path, False)
        os_req = self._make_get_request(path, parameters)
        response = os_req.get_response(None)
        json_response = self.get_from_response(response, resource, {})
        return json_response

    def create(self, path, parameters):
        """Create a server.
        :param req: the incoming request
        :param parameters: parameters with values for the new network
        """
        resource = utils.get_resource_from_path(path, True)
        req = self._make_create_request(path, resource, parameters)
        response = req.get_response(None)
        json_response = self.get_from_response(response, resource, {})

        return json_response
    #
    # def get_network(self, req, id):
    #     """Get info from a network. It returns json code from the server
    #     :param req: the incoming network
    #     :param id: net identification
    #     """
    #     path = "/networks/%s" % id
    #     req = self._make_get_request(req, path)
    #     response = req.get_response(self.app)
    #     net = self.get_from_response(response, "network", {})
    #     # subnet
    #     if net["subnets"]:
    #         path = "/subnets/%s" % net["subnets"][0]
    #         req_subnet = self._make_get_request(req, path)
    #         response_subnet = req_subnet.get_response(self.app)
    #         net["subnet_info"] = self.get_from_response(response_subnet, "subnet", {})
    #
    #     net["status"] = parsers.network_status(net["status"]);
    #     return net
    #
    # def get_subnet(self, req, id):
    #     """Get information from a subnet.
    #     :param req: the incoming request
    #     :param id: subnet identification
    #     """
    #     path = "/subnets/%s" % id
    #     req = self._make_get_request(req, path)
    #     response = req.get_response(self.app)
    #
    #     return self.get_from_response(response, "subnet", {})
    #
    # def create_network(self, req, parameters):
    #     """Create a server.
    #     :param req: the incoming request
    #     :param parameters: parameters with values for the new network
    #     """
    #     req = self._make_create_request(req, "network", parameters)
    #     response = req.get_response(self.app)
    #     json_response = self.get_from_response(response, "network", {})
    #     #subnetattributes
    #     if "occi.networkinterface.address" in parameters:#TODO(jorgesece): Create unittest for it
    #         parameters["network_id"] = json_response["id"]
    #         req_subnet= self._make_create_request(req, "subnet", parameters)
    #         response_subnet = req_subnet.get_response(self.app)
    #         json_response["subnet_info"] = self.get_from_response(response_subnet, "subnet", {})
    #
    #     return json_response
    #
    # def delete_network(self, req, parameters):
    #     """Delete network. It returns empty array
    #     :param req: the incoming network
    #     :param parameters:
    #     """
    #     path = "/networks"
    #     req = self._make_delete_request(req, path, parameters)
    #     response = req.get_response(self.app)
    #     return response
    #
    # def run_action(self, req, action, id):
    #     """Run an action on a network.
    #     :param req: the incoming request
    #     :param action: the action to run
    #     :param server_id: server id to delete
    #     """
    #     os_req = self._make_action_reques(req, action, id)
    #     response = os_req.get_response(self.app)
    #     if response.status_int != 202:
    #         raise helpers.exception_from_response(response)
