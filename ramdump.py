from ch341 import *
import time
import logging

ramdump_logger = logging.getLogger(__name__)

MEMDUMP_HEADER_LEN = 16 * 8


class RAMDump:

    def __init__(self):
        ramdump_logger.info("Setting up Host Controller")
        xhci.setup()
        ramdump_logger.info(
            "Polling roothub in search of output traffic controller")
        xhci.roothub.poll()
        ramdump_logger.info("Allocating serial port for CH341")
        self.port = USBSerialPort(xhci.devices[1])
        self.ch341 = CH341()
        ramdump_logger.info("Probing port")
        self.ch341.port_probe(self.port)
        ramdump_logger.info("Opening port")
        self.ch341.open(self.port)

    def memdump(self, base, data_len):
        packet = ipc.BitData(MEMDUMP_HEADER_LEN + data_len * 8, 0)
        packet[0:7] = 1
        packet[32:63] = base
        packet[64:95] = data_len
        packet[96:127] = int(time.time())
        packet[128:] = t.memblock(phys(base), data_len, 1)
        ramdump_logger.debug("Packet: \n"
                             "Header: {}"
                             "Memdump Header: {}"
                             "Data: {}".format(packet[0:31],
                                               packet[32:127],
                                               packet[128:]))
        ramdump_logger.info("Sending packet...")
        self.ch341.write(self.port, packet)
