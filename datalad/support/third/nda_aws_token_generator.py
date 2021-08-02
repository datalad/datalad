## NDA AWS Token Generator
## Author: NIMH Data Archives
##         http://ndar.nih.gov
## License: MIT
##          https://opensource.org/licenses/MIT

import binascii
import hashlib
import logging
import xml.etree.ElementTree as etree

import sys

if sys.version_info[0] == 2:
    import urllib2 as urllib_request
else:
    from urllib import request as urllib_request

class NDATokenGenerator(object):
    __schemas = {
        'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
        'data': 'http://gov/nih/ndar/ws/datamanager/server/bean/jaxb'
    }

    def __init__(self, url):
        assert url is not None
        self.url = url
        logging.debug('constructed with url %s', url)

    def generate_token(self, username, password):
        logging.info('request to generate AWS token')
        encoded_password = self.__encode_password(password)
        request_xml = self.__construct_request_xml(username, encoded_password)
        return self.__make_request(request_xml)

    def __encode_password(self, password):
        logging.debug('encoding password')
        hasher = hashlib.sha1()
        hasher.update(password.encode('utf-8'))
        digest_bytes = hasher.digest()
        byte_string = binascii.hexlify(digest_bytes)
        output = byte_string.decode('utf-8')
        logging.debug('encoded password hash: %s', output)
        return output

    def __construct_request_xml(self, username, encoded_password):
        logging.debug('constructing request with %s - %s', username, encoded_password)
        soap_schema = self.__schemas['soap']
        datamanager_schema = self.__schemas['data']

        element = etree.Element('{%s}Envelope' % soap_schema)
        body = etree.SubElement(element, '{%s}Body' % soap_schema)
        userelement = etree.SubElement(body, '{%s}UserElement' % datamanager_schema)

        user = etree.SubElement(userelement, "user")
        uid = etree.SubElement(user, "id")
        uid.text = '0'

        uid = etree.SubElement(user, "name")
        uid.text = username

        uid = etree.SubElement(user, "password")
        uid.text = encoded_password

        uid = etree.SubElement(user, "threshold")
        uid.text = '0'

        logging.debug(etree.tostring(element))
        return etree.tostring(element)

    def __make_request(self, request_message):
        logging.debug('making post request to %s', self.url)

        headers = {
            'SOAPAction': '"generateToken"',
            'Content-Type': 'text/xml; charset=utf-8'
        }

        request = urllib_request.Request(self.url, data=request_message, headers=headers)
        logging.debug(request)
        response = urllib_request.urlopen(request)
        return self.__parse_response(response.read())

    def __parse_response(self, response):
        logging.debug('parsing response')
        tree = etree.fromstring(response)

        error = tree.find('.//errorMessage')
        if error is not None:
            error_msg = error.text
            logging.error('response had error message: %s', error_msg)
            raise Exception(error_msg)
        generated_token = tree[0][0]
        token_elements = [e.text for e in generated_token[0:4]]
        token = Token(*token_elements)
        return token


class Token:
    def __init__(self, access_key, secret_key, session, expiration):
        logging.debug('constructing token')
        self._access_key = access_key
        self._secret_key = secret_key
        self._session = session
        self._expiration = expiration

    @property
    def access_key(self):
        return self._access_key

    @property
    def secret_key(self):
        return self._secret_key

    @property
    def session(self):
        return self._session

    @property
    def expiration(self):
        return self._expiration
