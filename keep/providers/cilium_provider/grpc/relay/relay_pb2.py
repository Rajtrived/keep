# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: relay/relay.proto
# Protobuf Python Version: 5.27.2
"""Generated protocol buffer code."""
# from google.protobuf import runtime_version as _runtime_version
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

"""
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    27,
    2,
    '',
    'relay/relay.proto'
)
"""
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b"\n\x11relay/relay.proto\x12\x05relay\"^\n\x0fNodeStatusEvent\x12&\n\x0cstate_change\x18\x01 \x01(\x0e\x32\x10.relay.NodeState\x12\x12\n\nnode_names\x18\x02 \x03(\t\x12\x0f\n\x07message\x18\x03 \x01(\t*l\n\tNodeState\x12\x16\n\x12UNKNOWN_NODE_STATE\x10\x00\x12\x12\n\x0eNODE_CONNECTED\x10\x01\x12\x14\n\x10NODE_UNAVAILABLE\x10\x02\x12\r\n\tNODE_GONE\x10\x03\x12\x0e\n\nNODE_ERROR\x10\x04\x42'Z%github.com/cilium/cilium/api/v1/relayb\x06proto3"
)

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "relay.relay_pb2", _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    _globals["DESCRIPTOR"]._loaded_options = None
    _globals["DESCRIPTOR"]._serialized_options = (
        b"Z%github.com/cilium/cilium/api/v1/relay"
    )
    _globals["_NODESTATE"]._serialized_start = 124
    _globals["_NODESTATE"]._serialized_end = 232
    _globals["_NODESTATUSEVENT"]._serialized_start = 28
    _globals["_NODESTATUSEVENT"]._serialized_end = 122
# @@protoc_insertion_point(module_scope)