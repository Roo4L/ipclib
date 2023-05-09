from ch341 import *
import time

MEMDUMP_HEADER_LEN = 16 * 8

class RAMDump:

    def __init__(self):
        xhci.setup()
        xhci.roothub.poll()
        self.port = USBSerialPort(xhci.devices[1])
        self.ch341 = CH341()
        self.ch341.port_probe(self.port)
        self.ch341.open(self.port)
    
    def memdump(self, base, data_len):
        packet = ipc.BitData(MEMDUMP_HEADER_LEN + data_len * 8, 0)
        packet[0:7] = 1
        packet[32:63] = base
        packet[64:95] = data_len
        packet[96:127] = int(time.time())
        packet[128:] = t.memblock(phys(base), data_len, 1)
        usb_debug("Packet: \n"
                  "Header: {}"
                  "Memdump Header: {}"
                  "Data: {}".format(packet[0:31],
                                    packet[32:127],
                                    packet[128:]))
        self.ch341.write(self.port, packet)
