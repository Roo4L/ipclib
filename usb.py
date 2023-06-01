from utils import ipc, t, debug, usleep
from mem import phys
import logging


GET_DESCRIPTOR_TRIES = 3


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


class InterfaceDescriptor(Data):
    F1 = 0
    F2 = 32
    F3 = 64

    def __init__(self, data=0):
        Data.__init__(self, 72, data)

class InterfaceDescriptorBits:
    bLength = [InterfaceDescriptor.F1, 0, 8]
    bDescriptorType = [InterfaceDescriptor.F1, 8, 8]
    bInterfaceNumber = [InterfaceDescriptor.F1, 16, 8]
    bAlternateSetting = [InterfaceDescriptor.F1, 24, 8]
    bNumEndpoints = [InterfaceDescriptor.F2, 0, 8]
    bInterfaceClass = [InterfaceDescriptor.F2, 8, 8]
    bInterfaceSubClass = [InterfaceDescriptor.F2, 16, 8]
    bInterfaceProtocol = [InterfaceDescriptor.F2, 24, 8]
    iInterface = [InterfaceDescriptor.F3, 0, 8]

class EndpointDescriptor(Data):
    F1 = 0
    F2 = 32

    def __init__(self, data=0):
        Data.__init__(self, 56, data)

class EndpointDescriptorBits:
    bLength = [EndpointDescriptor.F1, 0, 8]
    bDescriptorType = [EndpointDescriptor.F1, 8, 8]
    bEndpointAddress = [EndpointDescriptor.F1, 16, 8]
    bmAttributes = [EndpointDescriptor.F1, 24, 8]
    wMaxPacketSize = [EndpointDescriptor.F2, 0, 16]
    bInterval = [EndpointDescriptor.F2, 16, 8]


class DeviceClass:
    audio_device      = 0x01
    comm_device       = 0x02
    hid_device        = 0x03
    physical_device   = 0x05
    imaging_device    = 0x06
    printer_device    = 0x07
    msc_device        = 0x08
    hub_device        = 0x09
    cdc_device        = 0x0a
    ccid_device       = 0x0b
    security_device   = 0x0d
    video_device      = 0x0e
    healthcare_device = 0x0f
    diagnostic_device = 0xdc
    wireless_device   = 0xe0
    misc_device       = 0xef

class Direction:
    SETUP = 0
    IN = 1
    OUT = 2

    @staticmethod
    def name(value):
        types = Direction.__dict__
        for key in types.keys():
            if key.startswith("__"):
                continue
            if types[key] == value:
                return key
        return "UNKNOWN"


class EndpointType:
    CONTROL = 0
    ISOCHRONOUS = 1
    BULK = 2
    INTERRUPT = 3

    @staticmethod
    def name(value):
        types = EndpointType.__dict__
        for key in types.keys():
            if key.startswith("__"):
                continue
            if types[key] == value:
                return key
        return "UNKNOWN"


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
    
    def __repr__(self):
        return ("Endpoint: {}\n"
                "dir: {}\n"
                "type: {}\n"
                "mps: {}\n"
                .format(self.endpoint,
                        Direction.name(self.direction),
                        EndpointType.name(self.eptype),
                        self.maxpacketsize))
        
class bRequestCodes:
	GET_STATUS = 0
	CLEAR_FEATURE = 1
	SET_FEATURE = 3
	SET_ADDRESS = 5
	GET_DESCRIPTOR = 6
	SET_DESCRIPTOR = 7
	GET_CONFIGURATION = 8
	SET_CONFIGURATION = 9
	GET_INTERFACE = 10
	SET_INTERFACE = 11
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
    wLength = [DeviceRequest.F2, 16, 16]


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

    def get_descriptor(self, rtype, desc_type, desc_idx, data, data_len):
        transfered = 0
        dr = DeviceRequest()
        failed_tries = 0
        while (failed_tries <  GET_DESCRIPTOR_TRIES):
            dr.set(DeviceRequestBits.bmRequestType, rtype)
            dr.set(DeviceRequestBits.bRequest, bRequestCodes.GET_DESCRIPTOR)
            dr.set(DeviceRequestBits.wValue, desc_type << 8 | desc_idx)
            dr.set(DeviceRequestBits.wIndex, 0)
            dr.set(DeviceRequestBits.wLength, data_len)
            data, transfered = self.controller.control(self, Direction.IN, dr, data_len, data)
            if transfered == data_len:
                break
            usleep(10)
        return data, transfered


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

    def init_device_entry(self, dev, i):
        if self.devices[i] != None:
            logging.warning("device %d reassigned?\n" % i)
        self.devices[i] = dev

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

    def submit_urb(self, urb):
        # type: ('URB') -> None
        self.urb_enqueue(urb)


def usb_set_address(controller, speed, hubport, hubaddr):
    # type: ('HCI', 'USBSpeed', int, int) -> int
    dev = controller.set_address(speed, hubport, hubaddr)
    if not dev:
        logging.info("set_address failed")
        return -1
    
    logging.info("set address succeed\n"
              "dev:\n"
              "  hubport: {}\n"
              "  hubaddr: {}\n"
              "  address: {}\n"
              "  speed: {}\n"
              "  EP0: {}\n"
              .format(dev.port,
                      dev.hub,
                      dev.address,
                      dev.speed,
                      dev.endpoints[0]))

    dev.descriptor = DeviceDescriptor()
    # data, transfered = dev.get_descriptor(DR_DESC(), DT.DEV, 0, dev.descriptor, 144/8)
    # if transfered != 144:
    #     logging.debug("get_descriptor(DT_DEV) failed")
    #     # usb_detach_device(controller, dev.address)
    #     return -1
    # dev.descriptor.data = data
    # Hardcoded for arduino nano device
    dev.descriptor.set(DeviceDescriptorBits.bLength, 18)
    dev.descriptor.set(DeviceDescriptorBits.bDescriptorType, 1)
    dev.descriptor.set(DeviceDescriptorBits.bcdUSB, 0x0110)
    dev.descriptor.set(DeviceDescriptorBits.bDeviceClass, 255)
    dev.descriptor.set(DeviceDescriptorBits.bMaxPacketSize0, 8)
    dev.descriptor.set(DeviceDescriptorBits.idVendor, 0x1a86)
    dev.descriptor.set(DeviceDescriptorBits.idProduct, 0x7523)
    dev.descriptor.set(DeviceDescriptorBits.bcdDevice, 0x0254)
    dev.descriptor.set(DeviceDescriptorBits.iProduct, 2)
    dev.descriptor.set(DeviceDescriptorBits.bNumConfigurations, 1)

    logging.info("* found device (0x%04x:0x%04x, USB %x.%x, MPS0: %d)" % (
              dev.descriptor.get(DeviceDescriptorBits.idVendor),
              dev.descriptor.get(DeviceDescriptorBits.idProduct),
              dev.descriptor.get(DeviceDescriptorBits.bcdUSB) >> 8,
              dev.descriptor.get(DeviceDescriptorBits.bcdUSB) & 0xFF,
              dev.endpoints[0].maxpacketsize))

    # dev->quirks = usb_quirk_check(dev->descriptor->idVendor,
    #                     dev->descriptor->idProduct);

    bNumConfigurations = dev.descriptor.get(DeviceDescriptorBits.bNumConfigurations)
    logging.info("device has %d configurations" % bNumConfigurations)
    if bNumConfigurations == 0:
        logging.info("... no usable configuration!")
        # usb_detach_device(controller, device.address)
        return -1
    
    # buf = ipc.BitData(32, 0)
    # buf, transfered = dev.get_descriptor(DR_DESC, DT.CFG, 0, buf, 32 / 8)
    # if transfered != 32 / 8:
    #     logging.debug("first get_descriptor(DT_CFG) failed")
    #     # usb_detach_device(controller, device.address)
    #     return -1
    
    # usleep(1 * 1000)
    
    # configuration_len = buf.ReadByteArray()[1]
    configuration_len = 0x027
    dev.configuration = ConfigurationDescriptor()
    # dev.configuration, transfered = dev.get_descriptor(DR_DESC, DT.CFG, 0,
    #                                                    dev.configuration, configuration_len)
    # if transfered != configuration_len:
    #     logging.debug("get_descriptor(DT_CFG) failed")
    #     # usb_detach_device(controller, device.address)
    #     return -1

    dev.configuration.set(ConfigurationDescriptorBits.bLength, 9)
    dev.configuration.set(ConfigurationDescriptorBits.bDescriptorType, 2)
    dev.configuration.set(ConfigurationDescriptorBits.wTotalLength, 0x0027)
    dev.configuration.set(ConfigurationDescriptorBits.bNumInterfaces, 1)
    dev.configuration.set(ConfigurationDescriptorBits.bConfigurationValue, 1)
    dev.configuration.set(ConfigurationDescriptorBits.bmAttributes, 0x80)
    dev.configuration.set(ConfigurationDescriptorBits.bMaxPower, 48)

    # cd = ConfigurationDescriptor()
    # cd.data = dev.configuration

    cd = dev.configuration

    if cd.get(ConfigurationDescriptorBits.wTotalLength) != configuration_len:
        logging.info("configuration descriptor size changed, aborting")
        # usb_detach_device(controller, dev.address)
        return -1;

    bNumInterfaces = cd.get(ConfigurationDescriptorBits.bNumInterfaces)
    logging.info("device has %x interfaces" % bNumInterfaces)
    ifnum = usb_interface_check(dev.descriptor.get(DeviceDescriptorBits.idVendor),
                                dev.descriptor.get(DeviceDescriptorBits.idProduct))
    if bNumInterfaces > 1 and ifnum < 0:
            logging.warning("NOTICE: Your device has multiple interfaces and\n"
            "this driver will only use the first one. That may\n"
            "be the wrong choice and cause the device to not\n"
            "work correctly. Please report this case\n"
            "(including the above debugging output) to\n"
            "coreboot@coreboot.org to have the device added to\n"
            "the list of well-known quirks.");

    # config_array = dev.configuration.ReadByteArray()
    # end = cd.get(ConfigurationDescriptorBits.wTotalLength)
    # intf = InterfaceDescriptor()
    # ptr = len(cd)
    # while True:
    #     if (ptr + 2 > end or not config_array[ptr]
    #         or (ptr + config_array[ptr]) > end):
    #         logging.debug("Couldn't find usable DT_INTF")
    #         # usb_detach_device(controller, dev.address)
    #         return -1

    #     if config_array[ptr + 1] != DT.INTF:
    #         ptr += config_array[ptr]
    #         continue

    #     intf.data = dev.configuration[ptr*8:ptr*8+72]
    #     if intf.get(InterfaceDescriptorBits.bLength) != 72 / 8:
    #         logging.debug("Skipping broken DT_INTF")
    #         ptr += config_array[ptr]
    #         continue

    #     if ifnum >= 0 and intf.get(InterfaceDescriptorBits.bInterfaceNumber != ifnum):
    #         ptr += config_array[ptr]
    #         continue

    #     logging.debug("Interface %d: class 0x%x, sub 0x%x. proto 0x%x" % (
	# 		intf.get(InterfaceDescriptorBits.bInterfaceNumber),
    #         intf.get(InterfaceDescriptorBits.bInterfaceClass),
    #         intf.get(InterfaceDescriptorBits.bInterfaceSubClass),
    #         intf.get(InterfaceDescriptorBits.bInterfaceProtocol)))
    #     ptr += 72/8
    #     break

    dev.num_endp = 4

    # while ((ptr + 2 <= end) and config_array[ptr]
    #        and (ptr + config_array[ptr] <= end)):
    #     if (config_array[ptr + 1] == DT.INTF
    #         or config_array[ptr + 1] == DT.CFG
    #         or dev.num_endp >= len(dev.endpoints)):
    #         break;

    #     if (config_array[ptr + 1] != DT.ENDP):
    #         ptr += config_array[ptr]
    #         continue

    #     desc = EndpointDescriptor()
    #     desc.data = dev.configuration[ptr*8:ptr*8+len(desc.data)]
    #     transfertypes = [ "control", "isochronous", "bulk", "interrupt"]
    #     logging.debug(" #Endpoint %d (%s), max packet size %x, type %s" % (
    #         desc.get(EndpointDescriptorBits.EnbEndpointAddress) & 0x7f,
    #         "in" if (desc.get(EndpointDescriptorBits.bEndpointAddress) & 0x80) else "out",
    #         desc.get(EndpointDescriptorBits.wMaxPacketSize),
    #         transfertypes[desc.get(EndpointDescriptorBits.bmAttributes) & 0x3]))
        
    #     ep = Endpoint(dev,
    #                   desc.get(EndpointDescriptorBits.bEndpointAddress),
    #                   0,
    #                   Direction.IN if (desc.get(EndpointDescriptorBits.bEndpointAddress) & 0x80) else Direction.OUT,
    #                   desc.get(EndpointDescriptorBits.bmAttributes) & 0x3
    #                   )
    #     ep.maxpacketsize = desc.get(EndpointDescriptorBits.wMaxPacketSize)
    #     ep.interval = usb_decode_interval(dev.speed, ep.type,
    #                         desc.get(EndpointDescriptorBits.bInterval))
    #     dev.endpoints[dev.num_endp] = ep
    #     dev.num_endp += 1
    #     ptr += config_array[ptr]

    ep1 = Endpoint(dev,
                  0x82,
                  0,
                  Direction.IN,
                  2)
    ep1.maxpacketsize = 0x20
    ep1.interval = 0
    dev.endpoints[1] = ep1

    ep2 = Endpoint(dev,
                  0x02,
                  0,
                  Direction.OUT,
                  2)
    ep2.maxpacketsize = 0x20
    ep2.interval = 0
    dev.endpoints[2] = ep2

    ep3 = Endpoint(dev,
                  0x81,
                  0,
                  Direction.IN,
                  3)
    ep3.maxpacketsize = 0x8
    ep3.interval = 1
    dev.endpoints[3] = ep3
    
    if controller.finish_device_config(dev) or set_configuration(dev) < 0:
        raise Exception("Could not finalize device configuration")
        # usb_detach_device(controller, dev.address)
        return -1
    
    class_id = dev.descriptor.get(DeviceDescriptorBits.bDeviceClass)
    # if class_id == 0:
    #     class_id = intf.get(InterfaceDescriptorBits.bInterfaceClass)
    
    logging.info("Class: %d" % class_id)
    return dev.address

class DevReqDir:
    host_to_device = 0
    device_to_host = 1

class DevReqType:
    standard_type = 0
    class_type = 1
    vendor_type = 2
    reserved_type = 3

class DevReqRecp:
    dev_recp = 0
    iface_recp = 1
    endp_recp = 2
    other_recp = 3

def gen_bmRequestType(dir, rtype, recp):
    # type: ('DevReqDir', 'DevReqType', 'DevReqRecp') -> int
    return (dir << 7) | (rtype << 5) | recp

def DR_DESC():
    return gen_bmRequestType(DevReqDir.device_to_host,
                             DevReqType.standard_type,
                             DevReqRecp.dev_recp)

class DT:
    DEV = 1
    CFG = 2
    STR = 3
    INTF = 4
    ENDP = 5


class USBSpeed:
    UNKNOWN_SPEED = -1
    FULL_SPEED = 0
    LOW_SPEED = 1
    HIGH_SPEED = 2
    SUPER_SPEED = 3
    SUPER_SPEED_PLUS = 4

    @staticmethod
    def name(value):
        types = USBSpeed.__dict__
        for key in types.keys():
            if key.startswith("__"):
                continue
            if types[key] == value:
                return key
        return "UNKNOWN"


def usb_decode_mps0(speed, mps0):
    if speed == USBSpeed.FULL_SPEED:
        if mps0 in [8, 16, 32, 64]:
            return mps0
        else:
            logging.warning("Invalid MPS0: %d" % mps0)
            return 8
    elif speed == USBSpeed.HIGH_SPEED:
        if mps0 != 64:
            logging.warning("Invalid MPS0: %d" % mps0)
        return 64
    elif (speed == USBSpeed.SUPER_SPEED or
          speed == USBSpeed.SUPER_SPEED_PLUS):
        if (mps0 != 9):
            logging.warning("Invalid MPS0: %d" % mps0)
        return 1 << mps0
    else:
        logging.warning("Unexpected usb speed")
        return 8

def speed_to_default_mps(speed):
    if (speed == USBSpeed.FULL_SPEED or
        speed == USBSpeed.HIGH_SPEED):
        return 64
    elif (speed == USBSpeed.SUPER_SPEED or
          speed == USBSpeed.SUPER_SPEED_PLUS):
        return 512   
    else:
        logging.warning("Unexpected usb speed: %d" % speed)
        return 512

def usb_attach_device(controller, hubaddress, port, speed):
    speeds = ["full", "low", "high", "super", "ultra"]
    logging.info("%s speed device" % speeds[speed]if (speed < len(speeds) and speed >=0) else "invalid value - no")
    newdev = usb_set_address(controller, speed, port, hubaddress)
    if newdev == -1:
        return -1
    newdev_t = controller.devices[newdev]
    # newdev_t.init()
    return newdev if controller.devices[newdev] else -1

def usb_interface_check(vendor, device):
    # skip this as we don't think my device has any quirks
    return -1

def usb_decode_interval(speed, eptype, bInterval):
    def countZeros(x):
        # Keep shifting x by one until
        # leftmost bit does not become 1.
        total_bits = 32
        res = 0
        while ((x & (1 << (total_bits - 1))) == 0):
            x = (x << 1)
            res += 1
    
        return res

    def LOG2(a):
        return  ((4 << 3) - countZeros(a) - 1)
        

    if speed == USBSpeed.HIGH_SPEED:
        if eptype == EndpointType.ISOCHRONOUS or eptype == EndpointType.INTERRUPT:
            return bInterval-1
        else:
            return LOG2(bInterval)
    elif speed == USBSpeed.SUPER_SPEED or speed == USBSpeed.SUPER_SPEED_PLUS:
        if eptype == EndpointType.ISOCHRONOUS or eptype == EndpointType.INTERRUPT:
            return bInterval-1
        else:
            return 0
    else:
        raise Exception("Unexpected device speed: %d" % speed)

def set_configuration(dev):
    dr = DeviceRequest()
    dr.set(DeviceRequestBits.bmRequestType, 0)
    dr.set(DeviceRequestBits.bRequest, bRequestCodes.SET_CONFIGURATION)
    dr.set(DeviceRequestBits.wValue,
           dev.configuration.get(ConfigurationDescriptorBits.bConfigurationValue))
    dr.set(DeviceRequestBits.wIndex, 0)
    dr.set(DeviceRequestBits.wLength, 0)

    _, transfered = dev.controller.control(dev, Direction.OUT, dr, 0, 0)
    return transfered


class URB:

    dev = None # type: 'USBDevice'
    ep = None # type: 'Endpoint'
    transfer_buffer = None

    def __init__(self, ep):
        # type: ('Endpoint') -> None
        self.dev = ep.dev
        self.ep = ep

    def submit(self):
        self.dev.controller.submit_urb(self)
        

