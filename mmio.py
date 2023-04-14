import os
import time
from utils import *
from proc import *
from mem import *

# 0 = kernel space CS
# 1 = entire physical RAM range
# 2 = ?
# 3 = LDT address
# 4 = TSS
# 5 = ?
# 6 = ?
gdt_ranges = [
    (0x00000000, 0x8FE13),
    (0x00000000, 0xFFFFF),
    (0x00000000, 0x083FF),
    (0x001343B8, 0x001D0),
    (0x00096000, 0x00068),
    (0xF00C8008, 0x00008),
    (0xF5038000, 0x00088)]

# 0-53 = MMIO Ranges from BUP metadata
# 54 = BUP CS
# 55 = BUP DS
# 56 = ?
# 57 = BUP Stack
# 78 = corrupted?
# 81 = corrupted?
# 85 = corrupted?
ldt_ranges = [
    (0xF4000000, 0x26000),
    (0xF00B4000, 0x00200),
    (0xF5029000, 0x01000),
    (0xF461A000, 0x02000),
    (0xFCEE0000, 0x10000),
    (0xF4624000, 0x02000),
    (0xF6D00000, 0x10000),
    (0xF0080000, 0x06000),
    (0xF0088000, 0x06000),
    (0xF00D8000, 0x06000),
    (0xF5018000, 0x02000),
    (0xF5108000, 0x01000),
    (0xF510B000, 0x01000),
    (0xF510C000, 0x01000),
    (0xF510D000, 0x01000),
    (0xF510E000, 0x01000),
    (0xF510F000, 0x00484),
    (0xF5038000, 0x01000),
    (0xF00A8000, 0x01000),
    (0xF00A9000, 0x01000),
    (0xF00AA000, 0x01000),
    (0xF00AB000, 0x01000),
    (0xF00AC000, 0x01000),
    (0xF4400000, 0xB0000),
    (0xF00A8000, 0x05000),
    (0xF00A0000, 0x06000),
    (0xF0090000, 0x06000),
    (0xFEDFD000, 0x01000),
    (0xF3000000, 0x01000),
    (0xF00D0000, 0x06000),
    (0xDF800000, 0x00800),
    (0xF60D0000, 0x10000),
    (0xF0099000, 0x01000),
    (0xF6050000, 0x10000),
    (0xFEDFE000, 0x01000),
    (0xFEDFF000, 0x01000),
    (0xF00B1050, 0x00004),
    (0xF00B1004, 0x00004),
    (0xF5010000, 0x01000),
    (0xE00C0000, 0x01000),
    (0xF4630000, 0x10000),
    (0xF4623000, 0x01000),
    (0xF1000000, 0x01000),
    (0xF1010000, 0x01000),
    (0xE0070000, 0x01000),
    (0xE00D0000, 0x01000),
    (0xC8000000, 0x02000),
    (0xF00B0000, 0x01000),
    (0xF00B1000, 0x00004),
    (0x10000000, 0x20000),
    (0x10000000, 0x10000),
    (0xF6110000, 0x10000),
    (0xF5048000, 0x08000),
    (0xF6030000, 0x10000),
    (0x0009B000, 0x4F33A),
    (0x0009B000, 0x9922C),
    (0x000F0FFC, 0x00004),
    (0x0009B000, 0x56000),
    (0x00000023, 0x001C7),
    (0x00000000, 0x00003),
    (0xFFFF0000, 0xF01CF)]
    

def save_mmios(t, pwd, mmios, prefix="MMIO_"):
    try:
        os.makedirs(pwd)
    except:
        pass
    # Sort by size
    mmios.sort(lambda a, b: cmp(a[1], b[1]) if a[1] != b[1] else cmp(a[0], b[0]))
    for (addr, size) in mmios:
        print("Addr: %s, size: %s" % (hex(addr), hex(size)))
        path = os.path.join(pwd, prefix + hex(addr)[2:].replace("L", "") + ".bin")
        if os.path.exists(path):
            statinfo = os.stat(path)
            if statinfo.st_size >= size:
                print("Skipping. Already dumped")
                continue
            addr += statinfo.st_size
            size -= statinfo.st_size
        with open(path, "ab") as f:
            while size > 0:
                chunk = 4 * 1024
                if chunk > size:
                    chunk = size
                f.write(memtostr(t, phys(addr), chunk))
                addr += chunk
                size -= chunk


# Sideband loading. No idea what the value is/represents, but 0x706a8 makes it
# load DCI sideband into segment 0x19f (at 0xf6110000) and 0x70684 loads the DFx
# agregator instead. So let's try to bruteforce a few of these, see if any of them
# returns anything.

class Sideband(object):
    """
    IOSF Sideband bus
    """

    # Base address register (?)
    BAR_READ_GROUP = 0x00
    BAR_WRITE_GROUP = 0x01
    # PCI Configuration space
    PCI_READ_GROUP = 0x04
    PCI_WRITE_GROUP = 0x05
    # Private Configuration space
    PRIVATE_READ_GROUP = 0x06
    PRIVATE_WRITE_GROUP = 0x07
    

    def __init__(self, t, base_address=None):
        self.__thread = t
        self.base_addr = proc_get_address(t, "SB_CHANNEL") if not base_address else base_address
        self.broken_ports = proc_get_address(t, "SB_BROKEN_PORTS")

    def __setup(self, channel, rs=1, fid=0,):
        # Can only set it if the flag 0x2 (LOCK) is not set
        #sb_mmio = proc_get_address(t, "SB_WINDOW_MMIO")
        #t.mem(phys(sb_channel_port_addr), 4, sb_mmio)
        #t.mem(phys(sb_channel_port_addr + 4), 4, (size + 0xfff) & ~0xfff)
        self.__thread.mem(phys(self.base_addr + 0x18), 4, channel)
        self.__thread.mem(phys(self.base_addr + 0x1c), 4, rs << 8 | fid)
        return (self.__thread.mem(phys(self.base_addr), 4), self.__thread.mem(phys(self.base_addr + 4), 4))
    
    def __channel_value(self, group, port):
        return (group << 8) + port

    def read(self, group, port, size, rs=1, fid=0):
        if not self.__thread.ishalted():
            raise Exception("Execution threads is not halted!")
        
        channel = self.__channel_value(group, port)
        sb_mmio, _ = self.__setup(channel, rs, fid)
        ret = self.__thread.memblock(phys(sb_mmio), size, 1)
        try:
            a = self.__thread.mem(phys(self.base_addr + 0x18), 4)
            if a != channel:
                raise "Error"
        except:
            print("SB seems to have locked")
        
        return ret

    def dump(self, channel, size=0x8000, rs=1, fid=0, pwd=None):
        if not pwd:
            memdump = self.read(channel, size, rs, fid)
            print(memdump)
        else:
            sb_mmio, _ = self.__setup(channel, rs, fid)
            save_mmios(self.__thread, pwd, [(sb_mmio, size)], "SB_" + hex(channel) + "_")
    
    
    def __value_is_interesting(self, value):
        for i in value.ReadByteArray():
            if i != 0xFF and i != 0x00:
                return True
        return False
    
    def bruteforce(self, group, pstart=0, pend=0x100, rs=1, fid=0, size=0x10):
        for port in xrange(pstart, pend):
            if port in self.broken_ports:
                continue

            port_value = self.read(group, port, size, rs, fid)
            if self.__value_is_interesting(port_value):
                print("Group: %s. Port %s. Fid: %s" % (hex(group), hex(port), hex(fid)))
                print("Value: %s" % hex(port_value))

    def bruteforce_port_pci(self, port, dstart=0, dend=32, fstart=0, fend=8, rs=1, size=0x10):
        for dev in xrange(dstart, dend, 1):
            for func in xrange(fstart, fend, 1):
                fid = ((dev << 3)+ func)
                group = (self.PCI_WRITE_GROUP << 8) + self.PCI_READ_GROUP
                value = self.read(group, port, size, rs, fid)
                if not self.__value_is_interesting(value):
                    break
                print("Device-function: %d-%d" % (dev, func))
                print("Value: %s" % hex(value))
    
    def bruteforce_with_pci(self, pstart=0x00, pend=0x100, dstart=0, dend=32, fstart=0, fend=8, rs=1, size=0x10, ignore_ffports=True):
        bar_group = (self.BAR_WRITE_GROUP << 8) + self.BAR_READ_GROUP
        for port in xrange(pstart, pend):
            if port in self.broken_ports:
                continue

            port_value = self.read(bar_group, port, size, rs, 0)
            if ignore_ffports and self.__value_is_interesting(port_value) or not ignore_ffports:
                print("Group: %s. Port %s. Fid: %s" % (hex(bar_group), hex(port), hex(0)))
                print("Value: %s" % hex(port_value))
                self.bruteforce_port_pci(port, dstart, dend, fstart, fend, rs)


def bruteforce_sideband(t, pwd, group=0, start=0, end=0x100, size=0x8000, rs=1, fid=0):
    for i in xrange(start, end):
        # if i in cse_broken_ports:
        #     print("Skipping Port Id %d: it is known to be broken." % i)
        #     continue
        channel = (group << 8) + i
        print("Dumping Sideband : %s" % hex(channel))
        dump_sideband_channel(t, pwd, channel, size=size, rs=rs, fid=fid)
        # time.sleep(5)

def bruteforce_sideband_port(t, pwd, port, start=0, end=0x100, size=0x1000):
    for i in xrange(start, end, 2):
        bruteforce_sideband(t, pwd, group=i, start=port, end=port+1, size=size)

def bruteforce_sideband_port_pci(t, pwd, port, dstart=0, dend=32, fstart=0, fend=1, size=0x1000):
    for dev in xrange(dstart, dend, 1):
        for func in xrange(fstart, fend, 1):
            fid = ((dev << 3)+ func)
            print("Device-function: %d-%d" % (dev, func))
            bruteforce_sideband(t, pwd, group=0x0504, start=port, end=port+1,
                                size=size, fid=fid)
        

def setup_sideband_channel(t, channel, rs=1, fid=0, base_address=None):
    if base_address:
        sb_channel_port_addr = base_address
    else:
        sb_channel_port_addr = proc_get_address(t, "SB_CHANNEL")
    # Can only set it if the flag 0x2 (LOCK) is not set
    #sb_mmio = proc_get_address(t, "SB_WINDOW_MMIO")
    #t.mem(phys(sb_channel_port_addr), 4, sb_mmio)
    #t.mem(phys(sb_channel_port_addr + 4), 4, (size + 0xfff) & ~0xfff)
    t.mem(phys(sb_channel_port_addr + 0x18), 4, channel)
    t.mem(phys(sb_channel_port_addr + 0x1c), 4, rs << 8 | fid)
    return (t.mem(phys(sb_channel_port_addr), 4), t.mem(phys(sb_channel_port_addr + 4), 4))

def dump_sideband_channel(t, pwd, channel, size=0x8000, rs=1, fid=0):
    try:
        t.halt()
    except:
        # It could timeout for no good reason
        pass
    sb_channel_port_addr = proc_get_address(t, "SB_CHANNEL")
    sb_mmio, _ = setup_sideband_channel(t, channel, rs, fid)
    t.memdump(phys(sb_mmio), 0x10, 1)
    # save_mmios(t, pwd, [(sb_mmio, size)], "SB_" + hex(channel) + "_")

    try:
        a = t.mem(phys(sb_channel_port_addr + 0x18), 4)
        if a != channel:
            raise "Error"
    except:
        print("SB seems to have locked")
        ipc.resettarget()

def dump_sideband_channel_via_sbreg(t, pwd, channel, offset=0, size=0x8000, rs=1, fid=0, bar=0, opcode=0):
    tpsbs = [i for i in dir(ipc.stateport) if "tpsb" in i]
    if len(tpsbs) == 0:
        print("Can't find Tap2IOSF device")
        return
    tpsb = getattr(ipc.stateport, tpsbs[0])

    data = ipc.BitData(0, 0)
    force = False
    limit = offset + size
    for i in xrange(offset, limit, 4):
        try:
            data.Append(tpsb.sbreg(bar, fid, i, channel, rs, 4, opcode)[0:31])
            if ((i + 4) % 0x10) == 0:
                force = True
        except:
            force = True
            offset = i - (data.BitSize / 8)
        if force or i + 4 >= limit:
            if data.BitSize > 0:
                print "0x%08X: %s%s" % (offset, " ".join(map(lambda b: "%02X" % b, data.ToRawBytes())), "" if data.BitSize == 0x80 else "   ***")
                data = ipc.BitData(0, 0)
            offset = i + 4
        force = False
        
            
def clear_psf():
    dump_sideband_channel(pwd, 0x0706ba, 0x10)
    memset(0xf5048000, 0, 0x4000)
    dump_sideband_channel(pwd, 0x0706bb, 0x10)
    memset(0xf5048000, 0, 0x4000)
    dump_sideband_channel(pwd, 0x0706bc, 0x10)
    memset(0xf5048000, 0, 0x4000)
    dump_sideband_channel(pwd, 0x0706bd, 0x10)
    memset(0xf5048000, 0, 0x4000)