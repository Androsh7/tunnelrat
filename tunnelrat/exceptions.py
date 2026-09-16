"""Defines tunnelrat exceptions"""


class TunnelratBackendAbortError(Exception):
    """Raise when a step fails and the script run has to be abandoned"""
