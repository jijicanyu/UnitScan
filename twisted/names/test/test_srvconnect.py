# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.names.srvconnect}.
"""

from twisted.internet import defer, protocol
from twisted.names import client, dns, srvconnect
from twisted.names.common import ResolverBase
from twisted.names.error import DNSNameError
from twisted.internet.error import DNSLookupError
from twisted.trial import unittest
from twisted.test.proto_helpers import MemoryReactor


class FakeResolver(ResolverBase):
    """
    Resolver that only gives out one given result.

    Either L{results} or L{failure} must be set and will be used for
    the return value of L{_lookup}

    @ivar results: List of L{dns.RRHeader} for the desired result.
    @type results: C{list}
    @ivar failure: Failure with an exception from L{twisted.names.error}.
    @type failure: L{Failure<twisted.python.failure.Failure>}
    """

    def __init__(self, results=None, failure=None):
        self.results = results
        self.failure = failure

    def _lookup(self, name, cls, qtype, timeout):
        """
        Return the result or failure on lookup.
        """
        if self.results is not None:
            return defer.succeed((self.results, [], []))
        else:
            return defer.fail(self.failure)



class DummyFactory(protocol.ClientFactory):
    """
    Dummy client factory that stores the reason of connection failure.
    """
    def __init__(self):
        self.reason = None

    def clientConnectionFailed(self, connector, reason):
        self.reason = reason

class SRVConnectorTest(unittest.TestCase):

    def setUp(self):
        self.patch(client, 'theResolver', FakeResolver())
        self.reactor = MemoryReactor()
        self.factory = DummyFactory()
        self.connector = srvconnect.SRVConnector(self.reactor, 'xmpp-server',
                                                 'example.org', self.factory)


    def test_SRVPresent(self):
        """
        Test connectTCP gets called with the address from the SRV record.
        """
        payload = dns.Record_SRV(port=6269, target='host.example.org', ttl=60)
        client.theResolver.results = [dns.RRHeader(name='example.org',
                                                   type=dns.SRV,
                                                   cls=dns.IN, ttl=60,
                                                   payload=payload)]
        self.connector.connect()

        self.assertIdentical(None, self.factory.reason)
        self.assertEqual(
            self.reactor.tcpClients.pop()[:2], ('host.example.org', 6269))


    def test_SRVNotPresent(self):
        """
        Test connectTCP gets called with fallback parameters on NXDOMAIN.
        """
        client.theResolver.failure = DNSNameError('example.org')
        self.connector.connect()

        self.assertIdentical(None, self.factory.reason)
        self.assertEqual(
            self.reactor.tcpClients.pop()[:2], ('example.org', 'xmpp-server'))


    def test_SRVNoResult(self):
        """
        Test connectTCP gets called with fallback parameters on empty result.
        """
        client.theResolver.results = []
        self.connector.connect()

        self.assertIdentical(None, self.factory.reason)
        self.assertEqual(
            self.reactor.tcpClients.pop()[:2], ('example.org', 'xmpp-server'))


    def test_SRVBadResult(self):
        """
        Test connectTCP gets called with fallback parameters on bad result.
        """
        client.theResolver.results = [dns.RRHeader(name='example.org',
                                                   type=dns.CNAME,
                                                   cls=dns.IN, ttl=60,
                                                   payload=None)]
        self.connector.connect()

        self.assertIdentical(None, self.factory.reason)
        self.assertEqual(
            self.reactor.tcpClients.pop()[:2], ('example.org', 'xmpp-server'))


    def test_SRVNoService(self):
        """
        Test that connecting fails when no service is present.
        """
        payload = dns.Record_SRV(port=5269, target='.', ttl=60)
        client.theResolver.results = [dns.RRHeader(name='example.org',
                                                   type=dns.SRV,
                                                   cls=dns.IN, ttl=60,
                                                   payload=payload)]
        self.connector.connect()

        self.assertNotIdentical(None, self.factory.reason)
        self.factory.reason.trap(DNSLookupError)
        self.assertEqual(self.reactor.tcpClients, [])
