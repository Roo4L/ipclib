from enum import Enum

from utils import ipc, t, debug
from mem import phys

usb_debug = debug


class Data:
    def __init__(self, size, data=0, addr=None):
        self.size = size
        self.data = ipc.BitData(size, data)
        self.addr = addr
    
    def get(self, register):
        if type(register) == int:
            offset, start, length = (register, 0, 32)
        else:
            offset, start, length = register
        if self.addr is not None:
            self.read(self.addr)
        value = self.data[offset:offset+31]
        return value[start:start+length-1]
    
    def set(self, register, value):
        if type(register) == int:
            offset, start, length = (register, 0, 32)
        else:
            offset, start, length = register
        value = ipc.BitData(length, value)
        if self.addr is not None:
            self.read(self.addr)
        self.data[offset+start:offset+start+length-1] = value
        if self.addr is not None:
            self.write(self.addr)

    def read(self, addr):
        self.data = t.memblock(phys(addr), self.size / 8, 1)
    def write(self, addr):
         t.memblock(phys(addr), self.size / 8, 1, self.data.ToRawBytes())

class DeviceDescriptor(Data):
    F1 = 0
    F2 = 32
    F3 = 64
    F4 = 96
    F5 = 128
    
    def __init__(self, data=0):
        Data.__init__(self, 144, data)

class DeviceDescriptorBits:
    bLength = [DeviceDescriptor.F1, 0, 8]
    bDescriptorType = [DeviceDescriptor.F1, 8, 8]
    bcdUSB = [DeviceDescriptor.F1, 16, 16]
    bDeviceClass = [DeviceDescriptor.F2, 0, 8]
    bDeviceSubClass = [DeviceDescriptor.F2, 8, 8]
    bDeviceProtocol = [DeviceDescriptor.F2, 16, 8]
    bMaxPacketSize0 = [DeviceDescriptor.F2, 24, 8]
    idVendor = [DeviceDescriptor.F3, 0, 16]
    idProduct = [DeviceDescriptor.F3, 16, 16]
    bcdDevice = [DeviceDescriptor.F4, 0, 16]
    iManufacturer = [DeviceDescriptor.F4, 16, 8]
    iProduct = [DeviceDescriptor.F4, 24, 8]
    iSerialNumber = [DeviceDescriptor.F5, 0, 8]
    bNumConfigurations = [DeviceDescriptor.F5, 8, 8]


class ConfigurationDescriptor(Data):
    F1 = 0
    F2 = 32
    F3 = 64
        
    def __init__(self, data=0):
        Data.__init__(self, 72, data)
    
class ConfigurationDescriptorBits:
    bLength = [ConfigurationDescriptor.F1, 0, 8]
    bDescriptorType = [ConfigurationDescriptor.F1, 8, 8]
    wTotalLength = [ConfigurationDescriptor.F1, 16, 16]
    bNumInterfaces = [ConfigurationDescriptor.F2, 0, 8]
    bConfigurationValue = [ConfigurationDescriptor.F2, 8, 8]
    iConfiguration = [ConfigurationDescriptor.F2, 16, 8]
    bmAttributes = [ConfigurationDescriptor.F2, 24, 8]
    bMaxPower = [ConfigurationDescriptor.F3, 0, 8]


class Direction(Enum):
    SETUP = 0
    IN = 1
    OUT = 2


class EndpointType(Enum):
    CONTROL = 0
    ISOCHRONOUS = 1
    BULK = 2
    INTERRUPT = 3


class Endpoint:
    dev = None # type: 'USBDevice'
    endpoint = None # type: int
    toggle = None # type: int
    direction = None # type: 'Direction'
    maxpacketsize = None # type: int
    eptype = None # type: 'EndpointType'

    # expressed as binary logarithm of the number
	# of microframes (i.e. t = 125us * 2^interval)
    interval = None # type: int

    def __init__(self, dev, endpoint, toggle, direction, eptype):
        self.dev = dev
        self.endpoint  = endpoint
        self.toggle = toggle
        self.direction = direction
        self.eptype = eptype


class bRequestCodes(Enum):
	GET_STATUS = 0,
	CLEAR_FEATURE = 1,
	SET_FEATURE = 3,
	SET_ADDRESS = 5,
	GET_DESCRIPTOR = 6,
	SET_DESCRIPTOR = 7,
	GET_CONFIGURATION = 8,
	SET_CONFIGURATION = 9,
	GET_INTERFACE = 10,
	SET_INTERFACE = 11,
	SYNCH_FRAME = 12


class DeviceRequest(Data):
    """
    SETUP Data, the Parameter Component of Setup Stage TRB
    For payload format details refer to Figure 4-14 of xHCI
    specification.
    """
    F1 = 0
    F2 = 32    
    def __init__(self, data=0):
        Data.__init__(self, 64, data)

class DeviceRequestBits:
    bmRequestType = [DeviceRequest.F1, 0, 8]
    RequestRecipient = [DeviceRequest.F1, 0, 5]
    RequestType = [DeviceRequest.F1, 5, 2]
    DataDir = [DeviceRequest.F1, 7, 1]

    bRequest = [DeviceRequest.F1, 8, 8]
    wValue = [DeviceRequest.F1, 16, 16]
    wIndex = [DeviceRequest.F2, 0, 16]
    wILength = [DeviceRequest.F2, 16, 16]


class USBDevice:
    controller = None
    endpoints = [None] * 32
    num_endp = None
    address = None
    hub = None
    port = None
    speed = None
    quirks = None
    # data = None : there is no need in data field as it is used for simulating inheritance
    descriptor = None
    configuration = None

    def __init__(self, controller, address, hub, port):
        self.controller = controller
        self.address = address
        self.hub = hub
        self.port = port

    def init(self):
        pass

    def destroy(self):
        pass

    def poll(self):
        pass


class HCI:
    """
    abstract interface for any Host Controller (EHCI, OHCI, XHCI, etc.)
    """
    next = None  # type: 'HCI'
    reg_base = None  # type: int
    pcidev = None  # type: int
    hctype = None  # type: str
    latest_address = None  # type: int
    devices = [None] * 128  # type: List['USBDevice']

    instance = None  # type: Any

    def start(self):
        # type: () -> None
        pass

    def stop(self):
        # type: () -> None
        pass

    def reset(self):
        # type: () -> None
        pass

    def init(self):
        # type: () -> None
        pass

    def shutdown(self):
        # type: () -> None
        pass

    def bulk(self, ep, size, data, finalize):
        # type: (Any, int, bytearray, int) -> int
        pass

    def control(self, dev, pid, dr_length, devreq, data_length, data):
        # type: (Any, str, int, Any, int, bytearray) -> int
        pass

    def create_intr_queue(self, ep, reqsize, reqcount, reqtiming):
        # type: (Any, int, int, int) -> Any
        pass

    def destroy_intr_queue(self, ep, queue):
        # type: (Any, Any) -> None
        pass

    def poll_intr_queue(self, queue):
        # type: (Any) -> bytearray
        pass

    def set_address(self, speed, hubport, hubaddr):
        # type: (str, int, int) -> Any
        pass

    def finish_device_config(self, dev):
        # type: (Any) -> int
        pass

    def destroy_device(self, devaddr):
        # type: (int) -> None
        pass


def usb_set_address(controller, speed, hubport, hubaddr):
    controller.set_address(hubport)