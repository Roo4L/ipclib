import os
import mmio
from utils import *

class PCIDevice(object):
    def __init__(self, bus, dev, func, thread, base_address=0xE0000000):
        self._bus = bus & 0xFF
        self._dev = dev & 0x1F
        self._func = func & 0x7
        self._thread = thread
        self._base_addr = base_address

    def getID(self):
        return (self._bus << 8) | (self._dev << 3) | self._func
    
    def getConfigAddr(self, offset=0):
        """
        Get MMIO address of device in PCI configuration space
        
        Bits:
        31 - Enable bit
        30-24   - Reserved (used for specifying base address)
        23-16   - Bus
        15-11   - Device
        10-8    - Function
        7-0     - Offset
        """
        return 0x80000000 | (self._bus << 16) | (self._dev << 11) | (self._func << 8) | (offset & 0xFF)
    
    def getLegacyIOAddress(self, offset=0):
        """
        Get MMIO address of device in PCI configuration space
        
        Bits:
        31 - Enable bit
        30-24   - Reserved (used for specifying base address)
        23-16   - Bus
        15-11   - Device
        10-8    - Function
        7-0     - Offset
        """
        return self._base_addr | (self._bus << 16) | (self._dev << 11) | (self._func << 8) | (offset & 0xFF)
    
    def getIOAddress(self, offset=0):
        """
        Get MMIO address of device in PCI extended configuration space
        
        Bits:
        31 - Enable bit
        30-28   - Reserved (used for specifying base address)
        27-20   - Bus
        19-15   - Device
        14-12    - Function
        11-0     - Offset
        """
        return self._base_addr | (self._bus << 20) | (self._dev << 15) | (self._func << 12) | (offset & 0xFFF)

    def getVID(self, addressing="mmio"):
        return self.readWord(0, addressing)
    
    def readWord(self, offset, addressing="mmio"):
        if addressing == "mmio":
            ret = self._thread.memblock(hex(self.getIOAddress(offset)).replace("L", "") + "P", 1, 4)
        elif addressing == "portio":
            self._thread.dport(0xCF8, self.getConfigAddr())
            ret = self._thread.dport(0xCFC)
        else:
            raise "Invalid addressing mode: %s" % addressing
        return ret


    
def list_pci_devices(t, base_addr=0xE0000000, alt="", bars=True, addressing="mmio"):
    pwd = os.path.join(os.getcwd(), "PCI")
    for bus in range(256):
        device_found=False
        for dev in range (32):
            for func in range (8):
                device = PCIDevice(bus, dev, func, t, base_addr)
                vid = device.getVID()
                if vid != 0xFFFFFFFF and vid != 0x0:
                    if func == 0:
                        # device is present (zero func must be always implemented)
                        device_found = True
                    print("PCI %d.%d.%d : %s" % (bus, dev, func, vid.ToHex()))
                    mmio.save_mmios(t, pwd, [(device.getIOAddress(), 0x1000)], "PCI_" + alt + "%d.%d.%d_" % (bus, dev, func) )
                    if bars:
                        for offset in range(0x10, 0x28, 4):
                            bar = device.readWord(offset)
                            if bar != 0:
                                bar[0:7] = 0
                                mmio.save_mmios(t, pwd, [(bar, 0x1000)], "BAR_" + alt + "%d.%d.%d_" % (bus, dev, func))
                elif func == 0:
                    break
            if not device_found:
                # bus is empty as there is no root device, skip it
                break

def alt_list_pci_devices(t):
    list_pci_devices(t, 0xF1000000, "alt_")
