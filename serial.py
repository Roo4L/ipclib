# USB Interfaces implementation
#
# This implementation is mostly a translation linux kernel. If it is of any
# interest, one may refer to origin C implementation
# at https://elixir.bootlin.com/linux/latest/source/drivers/usb/serial/ch341.c

from usb import *

USB_SERIAL_WRITE_BUSY = 0
USB_SERIAL_THROTTLED = 1


class USBSerialPort:
    serial = None  # type: 'USBSerial'
    # flags = None # type: 'ipc.BitData'
    # interrupt_in_urb = None # type: 'URB'
    write_urb = None  # type: 'URB'

    def __init__(self, dev):
        # type: ('USBSerial') -> None
        self.serial = USBSerial(dev)
        self.init_urbs()

    def init_urbs(self):
        dev = self.serial.dev

        for ep in [ep for ep in dev.endpoints if ep is not None]:
            if ep.eptype == EndpointType.INTERRUPT:
                self.interrupt_in_urb = URB(ep)
            elif (ep.eptype == EndpointType.BULK and
                  ep.direction == Direction.OUT):
                self.write_urb = URB(ep)


class USBSerial:
    dev = None  # type: 'USBDevice'

    def __init__(self, dev):
        # type: ('USBDevice') -> None
        self.dev = dev


class USBSerialGeneric:

    def open(self, port):
        # type: ('USBSerialPort') -> None
        # port.flags[USB_SERIAL_THROTTLED] = 0
        #     if port.bulk_in_size:
        #         self.submit_read_urbs(port, GFP_KERNEL)
        pass

    # def submit_read_urbs(self, port, mem_flags):
    #     for i in xrange(0, len(port.read_urbs)):
    #         self.submit_read_urb(port, i, mem_flags)

    # def submit_read_urb(self, port, index, mem_flags):

    def write(self, port, data):
        # type: ('USBSerialPort', 'ipc.BitData') -> None
        # if not port.bulk_out_size:
        #     raise Exception("Error: invalid out write size")
        self.write_start(port, data)

    def write_start(self, port, data):
        # type: ('USBSerialPort', 'ipc.BitData') -> None
        # port.flags[USB_SERIAL_WRITE_BUSY] = 1

        urb = port.write_urb
        # urb.transfer_buffer = self.prepare_write_buffer(port.bulk_out_size)
        urb.transfer_buffer = data
        # port.tx_bytes += len(urb.transfer_buffer) / 8
        urb.submit()

    # def prepare_write_buffer(self, port, size):
    #     data = port.write_fifo.get(size)
    #     return data
