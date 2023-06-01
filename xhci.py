from mmio import *
from utils import *
from segments import *
from proc import *
from asm import *
import time
from usb import *
from xhci_rh import XHCIRootHub
import logging


NUM_EPS=32

TIMEOUT = -65

URB_ZERO_PACKET = 0x0040

        
class TRB(Data):
    PTR_LOW = 0
    PTR_HIGH = 32
    STATUS = 64
    CONTROL = 96
    
    def __init__(self, data=0):
        Data.__init__(self, 128, data)

    def __repr__(self):
        return "TRB : {}\n" \
            "  PTR Low : {}\n" \
            "  PTR High: {}\n" \
            "  Status: {}\n" \
            "  Control: {}\n" \
            .format(self.data,
                    self.get(self.PTR_LOW),
                    self.get(self.PTR_HIGH),
                    self.get(self.STATUS),
                    self.get(self.CONTROL))

        
class TRBPtrBits:
    PTR = [TRB.PTR_LOW, 0, 64]
    PORT = [TRB.PTR_LOW, 24, 8]

class TRBStatusBits:
    TL = [TRB.STATUS, 0, 17] # TL - Transfer Length 
    EVTL = [TRB.STATUS, 0, 24] #  EVTL - (Event TRB) Transfer Length 
    TDS = [TRB.STATUS, 17, 5] # TDS - TD Size 
    CC = [TRB.STATUS, 24, 8] # CC - Completion Code

class TRBControlBits:
    C = [TRB.CONTROL, 0, 1] # C - Cycle Bit
    TC = [TRB.CONTROL, 1, 1] # TC - Toggle Cycle
    ENT = [TRB.CONTROL, 1, 1] # ENT - Evaluate Next TRB
    ISP = [TRB.CONTROL, 2, 1] # ISP - Interrupt-on Short Packet
    CH = [TRB.CONTROL, 4, 1] # CH - Chain Bit
    IOC = [TRB.CONTROL, 5, 1] # IOC - Interrupt On Completion
    IDT = [TRB.CONTROL, 6, 1] # IDT - Immediate Data
    DC = [TRB.CONTROL, 9, 1] # DC - Deconfigure
    TT = [TRB.CONTROL, 10, 6] # TT - TRB Type
    TRT = [TRB.CONTROL, 16, 2] # TRT - Transfer Type
    DIR = [TRB.CONTROL, 16, 1] # DIR - Direction
    EP = [TRB.CONTROL, 16, 5] # EP - Endpoint ID
    ID = [TRB.CONTROL, 24, 8] # ID - Slot ID

class TRBDataDirection:
    NO_DATA = 0
    OUT_DATA = 2
    IN_DATA = 3

class TRBDirection:
    OUT = 0
    IN = 1

class TRBEnum:
    @staticmethod
    def name(value):
        types = TRBType.__dict__
        for key in types.keys():
            if key.startswith("__"):
                continue
            if types[key] == value:
                return key
        return "UNKNOWN"
    
class TRBType(TRBEnum):
    NORMAL = 1
    SETUP_STAGE = 2
    DATA_STAGE = 3
    STATUS_STAGE = 4
    LINK = 6
    EVENT_DATA = 7
    CMD_ENABLE_SLOT = 9
    CMD_DISABLE_SLOT = 10
    CMD_ADDRESS_DEV = 11
    CMD_CONFIGURE_EP = 12
    CMD_EVAL_CTX = 13
    CMD_RESET_EP = 14
    CMD_STOP_EP = 15
    CMD_SET_TR_DQ = 16
    CMD_NOOP = 23
    EV_TRANSFER = 32
    EV_CMD_CMPL = 33
    EV_PORTSC = 34
    EV_HOST = 37


class TRBCompletionCode:
    SUCCESS = 1
    TRB_ERROR = 5
    STALL_ERROR = 6
    RESOURCE_ERROR = 7
    BANDWIDTH_ERROR = 8
    NO_SLOTS_AVAILABLE = 9
    SLOT_NOT_ENABLED_ERROR = 11
    SHORT_PACKET = 13
    EVENT_RING_FULL_ERROR = 21
    COMMAND_RING_STOPPED = 24
    COMMAND_ABORTED = 25
    STOPPED = 26
    STOPPED_LENGTH_INVALID = 27

    @staticmethod
    def name(value):
        types = TRBCompletionCode.__dict__
        for key in types.keys():
            if key.startswith("__"):
                continue
            if types[key] == value:
                return key
        return "UNKNOWN"
    
class XHCICycleRing:
    def __init__(self, size):
        self.ring = dma_align(64, size * 0x10)
        self.size = size
        self.init()
    
    def __len__(self):
        return self.size
    def __getitem__(self, idx):
        if int(idx) > self.size:
            raise IndexError()
        return self.ring + int(idx) * 0x10

    def init(self):
        memset(self.ring, 0, self.size * 0x10)
        self.current = self.ring
        self.pcs = 1
    
    def enqueue_trb(self):
        trb = self.TRB()
        trb.set(TRBControlBits.C, self.pcs)
        trb.write(self.current)
        logging.debug("Enqued TRB:\n%s" % trb)
        self.current += 0x10
        trb = self.TRB()
        if trb.get(TRBControlBits.TT) == TRBType.LINK:
            raise Exception("TRB Link encountered.")    

    def enqueue_td(self, ep, mps, data_len, data, dt_dir):
        trb = None
        cur_start = data
        length = data_len
        packets = (data_len + mps - 1) / mps
        residue = 0
        trb_count = 0

        while (length or not trb_count):
            cur_end = (cur_start + 0x10000) & ~0xffff
            cur_length = cur_end - cur_start
            if length < cur_length:
                cur_length = length
                packets = 0
                length = 0
            else:
                packets -= (residue + cur_length) / mps
                residue = (residue + cur_length) % mps
                length -= cur_length

            trb = self.TRB()
            self.clear_trb(trb)
            trb.set(TRB.PTR_LOW, cur_start)
            trb.set(TRBStatusBits.TL, cur_length)
            trb.set(TRBStatusBits.TDS, min(0x1F, packets))
            trb.set(TRBControlBits.CH, 1)

            if (not trb_count) and ep ==1:
                trb.set(TRBControlBits.DIR, dt_dir)
                trb.set(TRBControlBits.TT, TRBType.DATA_STAGE)
            else:
                trb.set(TRBControlBits.TT, TRBType.NORMAL)
            
            if not length:
                trb.set(TRBControlBits.ENT, 1)
            
            trb.write(self.current)
            self.enqueue_trb()

            cur_start += cur_length
            trb_count += 1
        
        trb = self.TRB()
        self.clear_trb(trb)
        trb.set(TRB.PTR_LOW, self.current)
        trb.set(TRBControlBits.TT, TRBType.EVENT_DATA)
        trb.set(TRBControlBits.IOC, 1)

        trb.write(self.current)
        self.enqueue_trb()

    def clear_trb(self, trb):
        trb.set(TRB.PTR_LOW, 0)
        trb.set(TRB.PTR_HIGH, 0)
        trb.set(TRB.STATUS, 0)
        trb.set(TRB.CONTROL, 0)
        trb.set(TRBControlBits.C, not self.pcs)

    def TRB(self):
        trb = TRB()
        trb.read(self.current)
        return trb

class XHCICommandRing(XHCICycleRing):

    def init(self):
        XHCICycleRing.init(self)
        trb = TRB()
        trb.read(self[self.size - 1])
        # Set TRB Type to LINK
        trb.set(TRBControlBits.TT, TRBType.LINK)
        # Enable Toggle Cycle
        trb.set(TRBControlBits.TC, 1)
        trb.set(TRB.PTR_LOW, self.ring)
        trb.write(self[self.size - 1])
        
    def advance_enqueue_pointer(self):
        trb = TRB()
        self.current = self.current + 0x10
        trb.read(self.current)
        # Check for LINK Type
        while trb.get(TRBControlBits.TT) == TRBType.LINK:
            tc = trb.get(TRBControlBits.TC)
            trb.set(TRBControlBits.C, self.pcs)
            trb.write(self.current)
            self.current = trb.get(TRB.PTR_LOW)
            trb.read(self.current)
            if tc:
                self.pcs ^= 1
                
    def next_command_trb(self, cmd=0):
        trb = TRB()
        trb.set(TRBControlBits.C, not self.pcs)
        # Set TRB Type
        trb.set(TRBControlBits.TT, cmd)
        trb.write(self.current)
        return trb

    def post_command(self):
        trb = self.TRB()
        logging.debug("Posting command %s" % TRBType.name(trb.get(TRBControlBits.TT)))
        # Set Cycle bit
        trb.set(TRBControlBits.C, self.pcs)
        trb.write(self.current)

        # Ring the doorbell
        xhci.bar_write32(0x3000, 0)

        self.advance_enqueue_pointer()

    def wait_for_command(self, addr, clear_event):
        logging.debug("wait_for_command: addr = %x" % addr)
        cc = xhci.er.wait_for_command_done(addr, clear_event)
        if cc is not None:
            return cc
        
        xhci.bar_write32(0x98, xhci.bar_read32(0x98) | 0x6) # CS | CA
        xhci.bar_write32(0x9c, 0)

        cc = xhci.er.wait_for_command_aborted(addr)
        if xhci.bar_read32(0x98) & 8:
            logging.error("**FATAL**: xhci_wait_for_command: Command ring still running")
        return cc

    def noop(self):
        self.next_command_trb(TRBType.CMD_NOOP)
        cmd = self.current
        self.post_command()
        return self.wait_for_command(cmd, True)
    
    def enable_slot(self):
        slot_id = None
        self.next_command_trb(TRBType.CMD_ENABLE_SLOT)
        cmd = self.current
        self.post_command()
        cc = self.wait_for_command(cmd, False)
        if cc == TRBCompletionCode.SUCCESS:
            trb = xhci.er.TRB()
            slot_id = trb.get(TRBControlBits.ID)
            if slot_id > xhci.max_slots:
                raise Exception("Controller error")
            xhci.er.advance_dequeue_pointer()
            xhci.er.handle_events()
        return cc, slot_id
            
    def address_device(self, slot_id, ic):
        logging.debug("address_device: slot_id = %d" % slot_id)
        trb = self.next_command_trb(TRBType.CMD_ADDRESS_DEV)
        trb.set(TRBControlBits.ID, slot_id)
        trb.set(TRB.PTR_LOW, ic)
        # trb.set([96, 9, 1], 1) # Set BSR
        trb.write(self.current)
        cmd = self.current
        self.post_command()
        trb.read(cmd)
        logging.debug("Waiting for command: %s\n"
            "%s" % (hex(cmd), trb))
        return self.wait_for_command(cmd, True)

    def configure_endpoint(self, slot_id, config_id, ic):
        trb = self.next_command_trb(TRBType.CMD_CONFIGURE_EP)
        trb.set(TRBControlBits.ID, slot_id)
        trb.set(TRB.PTR_LOW, ic.ctx)
        if config_id == 0:
            trb.set(TRBControlBits.DC, 1)
        trb.write(self.current)
        cmd = self.current
        self.post_command()
        trb.read(cmd)
        logging.debug("Waiting for command: %s\n"
            "%s" % (hex(cmd), trb))
        return self.wait_for_command(cmd, True)


class XHCIEventRing(XHCICycleRing):

    def reset(self):
        trb = TRB()
        for i in range(self.size):
            trb.read(self[i])
            trb.set(TRBControlBits.C, 0)
            trb.write(self[i])
        self.current = self.ring
        self.ccs = 1
        self.pcs = 1
        
    def event_ready(self, trb):
        return trb.get(TRBControlBits.C) == self.pcs
    
    def wait_for_event(self, timeout):
        trb = self.TRB()
        while not self.event_ready(trb) and timeout > 0:
            if not (timeout % (1000*1000)):
                logging.debug("Timeout time remaining: %d" % timeout)
            usleep(1000)
            timeout -= 1000
            trb.read(self.current)
        return timeout if timeout > 0 else 0
    
    def wait_for_event_type(self, tt, timeout):
        while True:
            timeout = self.wait_for_event(timeout)
            if timeout == 0:
                break
            trb = self.TRB()
            logging.debug("Received event : %s, Completion Code: %s\n%s" % (
                TRBType.name(trb.get(TRBControlBits.TT)),
                TRBCompletionCode.name(trb.get(TRBStatusBits.CC)),
                trb))
            # logging.debug("tt = {}".format(tt))
            # logging.debug("TRBControlBits.TT = {}".format(trb.get(TRBControlBits.TT)))
            if trb.get(TRBControlBits.TT) == tt:
                break
            # logging.debug("handle_event in wait_for_event_type")
            self.handle_event(trb)
        return timeout

    def update_event_dq(self):
        xhci.bar_write32(0x2038, self.current)
    
    def advance_dequeue_pointer(self):
        self.current = self.current + 0x10
        if self.current == self.ring + self.size * 0x10:
            self.current = self.ring
        xhci.bar_write32(0x2038, self.current)

    def handle_event(self, trb):
        tt = trb.get(TRBControlBits.TT)
        cc = trb.get(TRBStatusBits.CC)
        # logging.debug("Received event : %s, Completion Code: %s\n%s" % (TRBType.name(tt), TRBCompletionCode.name(cc), trb))
        logging.debug("Handling unexpected event: %s" % TRBType.name(tt))
        if tt == TRBType.EV_CMD_CMPL:
            logging.debug("Warning: Spurious command completion event")
        elif tt == TRBType.EV_PORTSC:
            logging.debug("Port Status Change Event for %d: %s\n" %
                       (trb.get(TRBPtrBits.PORT), TRBCompletionCode.name(cc)))
        elif tt == TRBType.EV_HOST:
            if cc == TRBCompletionCode.EVENT_RING_FULL_ERROR:
                logging.debug("Event ring full!")
        else:
            logging.debug("Warning: Spurious event: %s, Completion Code: %s\n" %
                       (TRBType.name(tt), TRBCompletionCode.name(cc)))
        self.advance_dequeue_pointer()
    
    def handle_transfer_event(self):
        # Skip the logic due to missing interrupt_queues logic
        # trb = self.TRB()
        # cc = trb.get(TRBStatusBits.CC)
        # slot_id = trb.get(TRBControlBits.ID)
        # ep = trb.get(TRBControlBits.EP)

        # if slot_id and slot_id <= xhci.max_slots:
        #     intrq = xhci.devs[slot_id].interrupt_queues[ep]
        #     if intrq:
        #         # It's a running interrupt endpoint
        #         intrq.ready = trb.get(TRB.PTR_LOW)
        #         ready_trb = TRB()
        #         ready_trb.read(intrq.ready)
        #         if (cc == TRBCompletionCode.SUCCESS or
        #             cc == TRBCompletionCode.SHORT_PACKET):
        #             ready_trb.set(TRBStatusBits.TL,
        #                           (intrq.size - trb.get(TRBStatusBits.EVTL)))
        #             ready_trb.write(intrq.ready)
        #         else:
        #             logging.debug("Interrupt Transfer failed: %d" % cc)
        #             ready_trb.set(TRBStatusBits.TL, 0)
        # elif (cc == TRBCompletionCode.STOPPED
        #       or cc == TRBCompletionCode.STOPPED_LENGTH_INVALID):
        #     #ignore
        #     pass
        # else:
        #     logging.debug("Warning: "
        #         "Spurious transfer event for ID %d, EP %d:\n"
        #         "  Pointer: 0x%08x%08x\n"
        #         "       TL: 0x%06x\n"
        #         "       CC: %d\n" %
        #         (slot_id, ep,
        #         trb.get(TRB.PTR_HIGH),
        #         trb.get(TRB.PTR_LOW),
        #         trb.get(TRBStatusBits.EVTL), cc))
        self.advance_dequeue_pointer()
        
    def handle_events(self):
        trb = self.TRB()
        while self.event_ready(trb):
            self.handle_event(trb)
            trb.read(self.current)
        
    def wait_for_command_done(self, addr, clear_event):
        timeout = 100 * 1000 # 100ms
        cc = None
        while True:
            timeout = self.wait_for_event_type(TRBType.EV_CMD_CMPL, timeout)
            if timeout == 0:
                logging.debug("Warning: Timed out waiting for TRB_EV_CMD_CMPL.\n")
                break
            trb = self.TRB()
            if trb.get(TRB.PTR_LOW) == addr:
                cc = trb.get(TRBStatusBits.CC)
                break
            self.handle_event(trb)
        if clear_event:
            self.advance_dequeue_pointer()
        return cc
    
    def wait_for_command_aborted(self, addr, clear_event):
        timeout = 5 * 1000 * 1000 # 5s
        cc = None
        while True:
            timeout = self.wait_for_event_type(TRBType.EV_CMD_CMPL, timeout)
            if timeout == 0:
                logging.debug("Warning: Timed out waiting for TRB_EV_CMD_CMPL.\n")
                break
            trb = self.TRB()
            if trb.get(TRB.PTR_LOW) == addr:
                cc = trb.get(TRBStatusBits.CC)
                self.advance_dequeue_pointer()
                break
            self.handle_event(trb)

            
        while True:
            timeout = self.wait_for_event_type(TRBType.EV_CMD_CMPL, timeout)
            if timeout == 0:
                logging.debug("Warning: Timed out waiting for COMMAND_RING_STOPPED.\n")
                break
            trb = self.TRB()
            if trb.get(TRBStatusBits.CC) == TRBCompletionCode.COMMAND_RING_STOPPED:
                self.current = trb.read(TRB.PTR_LOW)
                self.advance_dequeue_pointer()
                break
            self.handle_event(trb)

        return cc


class SlotContext(Data):
    F1 = 0
    F2 = 32
    F3 = 64
    F4 = 96
    RSVD = 128

    def __init__(self, addr):
        Data.__init__(self, 0x20 * 8, addr=addr)
    
    def __repr__(self):
        return "Slot : {}\n" \
            "  F1: {}\n" \
            "  F2: {}\n" \
            "  F3: {}\n" \
            "  F4: {}\n" \
            .format(self.addr,
                    self.get(self.F1),
                    self.get(self.F2),
                    self.get(self.F3),
                    self.get(self.F4))

class SlotContextBits:
    ROUTE = [SlotContext.F1, 0, 20] # ROUTE - Route String
    SPEED1 = [SlotContext.F1, 20, 4] # SPEED - Port speed plus one (compared to usb_speed enum)
    MTT = [SlotContext.F1, 25, 1] # MTT - Multi Transaction Translator
    HUB = [SlotContext.F1, 26, 1] # HUB - Is this a hub?
    CTXENT = [SlotContext.F1, 27, 5] # CTXENT - Context Entries (number of following ep contexts)
    RHPORT = [SlotContext.F2, 16, 8] # RHPORT - Root Hub Port Number
    NPORTS = [SlotContext.F2, 24, 8] # NPORTS - Number of Ports
    TTID = [SlotContext.F3, 0, 8] # TTID - TT Hub Slot ID
    TTPORT = [SlotContext.F3, 8, 8] # TTPORT - TT Port Number
    TTT = [SlotContext.F3, 16, 2] # TTT - TT Think Time
    UADDR = [SlotContext.F4, 0, 8] # UADDR - USB Device Address
    STATE = [SlotContext.F4, 27, 8] # STATE - Slot State

class EPContext(Data):
    F1 = 0
    F2 = 32
    TR_DQ_LOW = 64
    TR_DQ_HIGH = 96
    F5 = 128
    RSVD0 = 160
    RSVD1_3 = 192

    def __init__(self, addr):
        Data.__init__(self, 0x20 * 8, addr=addr)
    
    def __repr__(self):
        return "EP: {}\n" \
            "  F1: {}\n" \
            "  F2: {}\n" \
            "  TR_DQ_LOW: {}\n" \
            "  TR_DQ_HIGH: {}\n" \
            "  F5: {}\n" \
            .format(self.addr,
                    self.get(self.F1),
                    self.get(self.F2),
                    self.get(self.TR_DQ_LOW),
                    self.get(self.TR_DQ_HIGH),
                    self.get(self.F5))


class EPContextBits:
    STATE = [EPContext.F1, 0, 3] # STATE - Endpoint State
    INTVAL = [EPContext.F1, 16, 8] # INTVAL - Interval
    CERR = [EPContext.F2, 1, 2] # CERR - Error Count
    TYPE = [EPContext.F2, 3, 3] # TYPE - EP Type
    MBS = [EPContext.F2, 8, 8] # MBS - Max Burst Size
    MPS = [EPContext.F2, 16, 16] # MPS - Max Packet Size
    DCS = [EPContext.TR_DQ_LOW, 0, 1] # DCS - Dequeue Cycle State
    AVRTRB = [EPContext.F5, 0, 16] # AVRTRB - Average TRB Length
    MXESIT = [EPContext.F5, 16, 16] # MXESIT - Max ESIT Payload
    BPKTS = [EPContext.RSVD0, 0, 6] # BPKTS - packets tx in scheduled uframe
    BBM = [EPContext.RSVD0, 11, 1] # BBM - burst mode for scheduling

class Intrq:
    size = None # type: int
    count = None # type: int
    # (address to trb instead of actual TRB)
    next_trb = None # type: int
    # (address to trb instead of actual TRB)
    ready = None # type: int
    ep = None # type: 'Endpoint'
        
class XHCIDevice:
    def __init__(self, slot_id, addr=None):
        self.slot_id = slot_id
        if addr is None:
            addr = dma_align(64, NUM_EPS * 0x20, memset_value=0)
        self.ctx = addr
        self.slot = SlotContext(self.ctx)
        self.transfer_rings = [None for i in xrange(NUM_EPS)]
        self.interrupt_queues = [None for i in xrange(NUM_EPS)]
        self.ep0 = EPContext(self.ctx + 0x20)
        self.eps = []
        for i in range(0x00, 0x20 * (NUM_EPS), 0x20):
            self.eps.append(EPContext(self.ctx + i))

    def __getitem__(self, idx):
        if int(idx) > 30:
            raise IndexError()
        return self.ctx + int(idx) * 0x20
    
    def __repr__(self):
        return ("%s\n"
                "EP0: %s\n"
                "EP1 IN: %s\n"
                "EP2 OUT: %s\n"
                "EP2 IN: %s\n" % (
                    self.slot,
                    self.ep0,
                    self.eps[3],
                    self.eps[4],
                    self.eps[5])
                )

    def doorbell(self, value=0):
        logging.debug("Ringing doorbel for slot {} with DT = {}".
                  format(self.slot_id, value))
        xhci.bar_write32(0x3000 + 4 * int(self.slot_id), value)
        
class XHCIInputContext:
    def __init__(self, slot_id, add_list=[], drop_list=[]):
        self.slot_id = slot_id
        self.ctx = dma_align(64, 0x20 + NUM_EPS * 0x20, memset_value=0)
        add = ipc.BitData(32, 0)
        drop = ipc.BitData(32, 0)
        for ep in add_list:
            add[ep] = 1
        t.mem(phys(self.ctx + 4), 4, add)
        t.mem(phys(self.ctx), 4, drop)
        self.dev = XHCIDevice(slot_id, self.ctx + 0x20)
    
    def __repr__(self):
        return ("Input control: %s\n"
                "%s" % (t.memblock(phys(self.ctx), 0x20, 1), self.dev))
        
class XHCI(HCI):
    # Sideband and PCI addressing
    port = None
    fid = None

    # Host controller Parameters
    page_size = None
    max_slots = None
    max_ports = None
    max_sp_bufs = None

    # DMA buffer for data structures allocation
    dma_buffer = None

    # XHCI Data structures
    dcbaa = None
    sp_ptrs = None
    cr = None
    er = None
    ev_ring_table = None
    devs = None # type: List[XHCIDevice]
    transfer_rings = None

    def __init__(self, thread):
        self.port = proc_get_address(thread, "XHCI_PORTID")
        self.fid = proc_get_address(thread, "XHCI_PCI_DEVICE")

        self.page_size = self.bar_read16(0x88).ToUInt32() << 12
        self.max_slots = self.bar_read32(0x4).ToUInt32() & 0xff
        self.max_ports = (self.bar_read32(0x4).ToUInt32() & 0xff000000) >> 24
        self.devs = [None for i in xrange(self.max_slots + 1)]
        logging.info("caplen:  %s" % hex(self.bar_read16(0)))
        logging.info("rtsoff:  %s" % hex(self.bar_read32(0x18)))
        logging.info("dboff:   %s" % hex(self.bar_read32(0x14)))
        logging.info("hciversion: %d.%d" % (self.bar_read8(0x3), self.bar_read8(0x2)))
        logging.info("Max Slots:   %d" % self.max_slots)
        logging.info("Max Ports:   %d" % self.max_ports)
        logging.info("Page Size:   %d" % self.page_size)

        
        # Allocate resources
        self.dcbaa = dma_align(64, (self.max_slots + 1 ) * 8, memset_value=0)
        max_sp_hi = (self.bar_read32(0x8) & 0x03E00000) >> 21
        max_sp_lo = (self.bar_read32(0x8) & 0xF8000000) >> 27
        self.max_sp_bufs = max_sp_hi << 5 | max_sp_lo
        logging.info("Max Scratch Pad Buffers:   %d" % self.max_sp_bufs)
        if self.max_sp_bufs:
            self.sp_ptrs = dma_align(64, self.max_sp_bufs * 8, memset_value=0)
            for i in range(self.max_sp_bufs):
                page = dma_align(self.page_size, self.page_size)
                self.set(self.sp_ptrs + i*8, page)
            self.set(self.dcbaa, self.sp_ptrs)
        self.dma_buffer = dma_align(64 * 1024, 64 * 1024)
        self.cr = XHCICommandRing(4)
        logging.debug("command ring %s" % hex(self.cr.ring))
        self.er = XHCIEventRing(64)
        logging.debug("event ring %s" % hex(self.er.ring))
        self.ev_ring_table = dma_align(64, 0x10, memset_value=0)
        logging.debug("event ring table %s" % hex(self.ev_ring_table))

    def dump_pci_config(self):
        sb_mmio, _ = setup_sideband_channel(0x050400 | self.port, 0, self.fid << 3)
        t.memdump(phys(sb_mmio), 0x100, 1)
        save_mmios(pwd, [(sb_mmio, 0x1000)], "PCI_" + str(self.fid) + ".0_")
    
    def check_pci_from_ME(self):
        sb_mmio, _ = setup_sideband_channel(0x050400 | self.port, 0, self.fid << 3)
        base = t.arch_register("ldtbas")
        selector = 0
        for idx in range(128):
            segment = t.memblock(str(base.ToUInt32() + 8 * idx) + "L", 8, 1)
            entry = GDTEntry(segment)
            if entry.base_addr == sb_mmio:
                selector = idx << 3 | 0xf
                break

        execute_asm(t,
                    "mov edx, fs",
                    "mov eax, 0x%X" % selector,
                    "mov fs, eax",
                    "mov eax, 0",
                    "mov eax, fs:[eax]",
                    "mov fs, edx")
        wait_until_infinite_loop(t)
        print "Read from XHCI USB Using ME processor : %s" % reg("eax")

    def sb_read(self, rw_opcode, fid, size, offset):
        sb_channel = 1 << 28 | (rw_opcode | 1) << 16 | (rw_opcode & ~1) << 8 | self.port
        sb_mmio, _ = setup_sideband_channel(sb_channel, 0, fid << 3)
        return t.mem(phys(sb_mmio + offset), size)
    def sb_write(self, rw_opcode, fid, size, offset, value):
        sb_channel = 1 << 28 | (rw_opcode | 1) << 16 | (rw_opcode & ~1) << 8 | self.port
        sb_mmio, _ = setup_sideband_channel(sb_channel, 0, fid << 3)
        t.mem(phys(sb_mmio + offset), size, value)

    def pci_read(self, size, offset):
        return self.sb_read(4, self.fid, size, offset)
    def pci_write(self, size, offset, value):
        return self.sb_write(4, self.fid, size, offset, value)

    def pci_read32(self, offset):
        return self.pci_read(4, offset)
    def pci_read16(self, offset):
        return self.pci_read(2, offset)
    def pci_read8(self, offset):
        return self.pci_read(1, offset)
    def pci_write32(self, offset, value):
        self.pci_write(4, offset, value)
    def pci_write16(self, offset, value):
        self.pci_write(2, offset, value)   
    def pci_write8(self, offset, value):
        self.pci_write(1, offset, value)

    def bar_read(self, size, offset):
        return self.sb_read(0, self.fid, size, offset)
    def bar_write(self, size, offset, value):
        return self.sb_write(0, self.fid, size, offset, value) 

    def bar_read32(self, offset):
        return self.bar_read(4, offset)
    def bar_read16(self, offset):
        return self.bar_read(2, offset)
    def bar_read8(self, offset):
        return self.bar_read(1, offset)
    def bar_write32(self, offset, value):
        self.bar_write(4, offset, value)
    def bar_write16(self, offset, value):
        self.bar_write(2, offset, value)   
    def bar_write8(self, offset, value):
        self.bar_write(1, offset, value)
    def get(self, addr):
        return t.mem(phys(addr), 4)
    def set(self, addr, value):
        t.mem(phys(addr), 4, value)

    def status(self):
        return self.bar_read32(0x84)

    def print_status(self):
        sts = self.status()
        logging.debug("XHCI Status : \n" \
                   "  Host Controller Error : %s\n" \
                   "  Controller Not Ready : %s\n" \
                   "  Save/Restore Error : %s\n" \
                   "  Restore State Status : %s\n" \
                   "  Save State Status : %s\n" \
                   "  Port Change Detect : %s\n" \
                   "  Event Interrupt : %s\n" \
                   "  Host System Error : %s\n" \
                   "  Host Controller Halted : %s\n" \
                   % (sts[12], sts[11], sts[10], sts[9], sts[8],
                      sts[4], sts[3], sts[2], sts[0]))

    def handshake(self, reg, mask, value, timeout=100000):
        while ((self.bar_read32(reg) & mask) != value and timeout > 0):
            usleep(1)
            timeout -= 1
        if timeout == 0:
            logging.info("Timeout waiting for 0x%X & 0x%X to reach 0x%X!" % (reg, mask, value))
        return timeout

    def wait_ready(self):
        logging.debug("Waiting for controller to be ready...")
        if self.handshake(0x84, 1 << 11, 0) == 0:
            logging.debug("Timeout!")
            return -1
        logging.debug("OK")
        return 0

    def command(self, command, set=True):
        cmd = self.bar_read32(0x80)
        if set:
            cmd |= command
        else:
            cmd &= ~command
        self.bar_write32(0x80, cmd)

    def start(self):
        # Set Running Command
        self.command(1)
        # Check Halted Status
        if self.handshake(0x84, 1, 0):
            logging.info("XHCI Controller started")
    def stop(self):
        self.command(1, False)
        if self.handshake(0x84, 1, 1):
            logging.info("XHCI Controller stopped")
    def reset(self):
        if self.bar_read32(0x80) & 1:
            self.stop()
        try:
            self.command(2)
        except:
            # It is a normal reaction for XHCI reset under linux
            pass
        logging.info("Resetting controller...")
        time.sleep(2)
        # Check Command cleared
        if self.handshake(0x80, 2, 0):
            logging.debug("OK")
        # Check Not Ready status
        if self.handshake(0x84, 1<<11, 0):
            logging.debug("OK")

    def ring_doorbell(self, ep):
        # type: ('Endpoint') -> None
        value = ((ep.endpoint & 0x7F) * 2) + (ep.direction != Direction.OUT)
        self.devs[ep.dev.address].doorbell(value)
        
    def setup(self):
        # Enable COMMAND MEMORY and BUS MASTER 
        self.pci_write16(4, 6)
        self.reset()
        self.init()

    def init(self):
        # Setup hardware
        self.wait_ready()
        self.bar_write8(0xb8, self.max_slots)
        self.bar_write32(0xb0, self.dcbaa)
        self.bar_write32(0xb4, 0)

        self.bar_write32(0x98, self.cr.ring | 0x1)
        self.bar_write32(0x9c, 0)

        self.er.reset()
        
        self.set(self.ev_ring_table, self.er.ring)
        self.set(self.ev_ring_table + 8, 64)
        
        self.bar_write32(0x2028, 1) # Size of evet ring table
        self.bar_write32(0x2030, self.ev_ring_table)
        self.bar_write32(0x2034, 0)
        self.bar_write32(0x2038, self.er.current)

        self.start()

        # Wait 20ms to stabilize
        usleep(20 * 1000)

        cc = self.cr.noop()
        running = self.bar_read32(0x98) & 8
        logging.debug("NOOP result : %s" % TRBCompletionCode.name(cc))
        logging.info("Command ring is %s" % ("running" if running else "not running"))

        self.devs = [None]* self.max_ports

        self.roothub = XHCIRootHub(self)
        self.init_device_entry(self.roothub, 0)

    def gen_route(self, port, hubaddr):
        if not hubaddr:
            return 0
        route_string = self.devs[hubaddr].ctx.slot.get(SlotContextBits.ROUTE)
        for i in xrange(20):
            if not (route_string & (0xf << i)):
                route_string |= (port & 0x0f) << i
                break
        return route_string
    
    def get_tt(self, speed, port, hubaddr):
        if not hubaddr:
            return None, None
        slot = self.devs[hubaddr].ctx.slot
        tt = slot.get(SlotContextBits.TTID)
        if tt:
            tt_port = slot.get(SlotContextBits.TTPORT)
        elif (speed < USBSpeed.HIGH_SPEED
              and slot.get(SlotContextBits.SPEED1)-1 == USBSpeed.HIGH_SPEED):
            tt = hubaddr
            tt_port = port
        return tt, tt_port
    

    def gen_rh_port(self, port, hubaddr):
        if not hubaddr:
            return port
        return self.devs[hubaddr].ctx.slot.get(SlotContextBits.RHPORT)
    
    def set_address(self, speed, port, hubaddr):
        # type: ('USBSpeed', int, int) -> USBDevice
        cc, slot_id = self.cr.enable_slot()
        if cc != TRBCompletionCode.SUCCESS:
            raise Exception("Slot Enable command failed. CC = %s" % TRBCompletionCode.name(cc))
        
        slot_id = int(slot_id)
        
        ic = XHCIInputContext(slot_id, add_list=[0, 1])
        tr = XHCICycleRing(32)
        
        # Set Slot Context
        ic.dev.slot.set(SlotContextBits.ROUTE, self.gen_route(port, hubaddr))
        ic.dev.slot.set(SlotContextBits.SPEED1, speed+1)
        ic.dev.slot.set(SlotContextBits.CTXENT, 1)
        ic.dev.slot.set(SlotContextBits.RHPORT, self.gen_rh_port(port, hubaddr))

        tt, tt_port = self.get_tt(speed, port, hubaddr)
        if tt is not None:
            logging.debug("TT for %d: %d[%d]" % (slot_id, tt, tt_port))
            ic.dev.slot.set(SlotContextBits.MTT,
                            self.devs[tt].ctx.slot.get(SlotContextBits.MTT))
            ic.dev.slot.set(SlotContextBits.TTID, tt)
            ic.dev.slot.set(SlotContextBits.TTPORT, tt_port)
        

        # Set EP Context
        ic.dev.ep0.set(EPContext.TR_DQ_LOW, tr.ring)
        
        ic.dev.ep0.set(EPContext.TR_DQ_HIGH, 0)
        ic.dev.ep0.set(EPContextBits.TYPE, 4) # EP_CONTROL
        ic.dev.ep0.set(EPContextBits.AVRTRB, 8)
        # ic.dev.ep0.set(EPContextBits.MPS, speed_to_default_mps(speed))
        # hardcoded for full speed device
        ic.dev.ep0.set(EPContextBits.MPS, 8)
        ic.dev.ep0.set(EPContextBits.CERR, 3)
        ic.dev.ep0.set(EPContextBits.DCS, 1)

        self.devs[slot_id] = XHCIDevice(slot_id)
        self.devs[slot_id].transfer_rings[1] = tr
        dcbaa_new = t.memblock(phys(self.dcbaa), (slot_id+1)*8, 1)
        dcbaa_new[slot_id*8*8:(slot_id+1)*8*8-1] = self.devs[slot_id].ctx
        logging.debug("dcbaa_new: %s" % dcbaa_new)
        t.memblock(phys(self.dcbaa), (slot_id+1)*8, 1, dcbaa_new.ToRawBytes())
        # self.set(self.dcbaa + slot_id * 8, self.devs[slot_id].ctx)
        # logging.debug("dcbaa = %s" % hex(self.dcbaa))
        # logging.debug("dcbaa: %s" % t.memblock(phys(self.dcbaa), (slot_id+1)*8, 1))
        # logging.debug("dcbaa[%d] = %s" % 
        #           (slot_id, t.memblock(phys(self.dcbaa + slot_id * 8), 1, 4)))
        #  logging.debug("Input Context:%s\n%s" % (hex(ic.ctx), ic))
        # logging.debug("xhci.devs[%d]:\n%s" % (slot_id, self.devs[slot_id]))
        # logging.debug("before address_device:\n"
        #           "xhci.devs[%d]: %s\n%s" % 
        #     (slot_id, 
        #     hex(self.devs[slot_id].ctx),
        #     self.devs[slot_id]))
        cc = self.cr.address_device(slot_id, ic.ctx)
        if cc != 1:
            raise Exception("Address device failed: %d" % cc)
        usleep(6*1000)

        logging.debug("Address device succeed")

        # logging.debug("after address_device:\n"
        #           "xhci.devs[%d]: %s\n%s" % 
        #     (slot_id, 
        #     hex(self.devs[slot_id].ctx),
        #     self.devs[slot_id]))
        # logging.debug("dcbaa[%d] = %s" %
        #           (slot_id, hex(t.memblock(phys(self.dcbaa + slot_id*8), 4, 1))))
        newdev = USBDevice(self, int(slot_id), hubaddr, port)
        newdev.speed = speed
        newdev.endpoints[0] = Endpoint(newdev, 0, 0, Direction.SETUP, EndpointType.CONTROL)
        # TODO: initialize device remaining fields
        self.init_device_entry(newdev, slot_id)
        # buf = ipc.BitData(8*8, 0)
        # buf, transfered = newdev.get_descriptor(gen_bmRequestType(
        #                             DevReqDir.device_to_host,
        #                             DevReqType.standard_type,
        #                             DevReqRecp.dev_recp),
        #                        DT.DEV, 0, buf, len(buf)/8
        #                     )
        # if transfered != len(buf)/8:
        #     raise Exception("first get_descriptor(DT_DEV) failed")
        
        # newdev.endpoints[0].maxpacketsize = usb_decode_mps0(speed, buf[56:])
        newdev.endpoints[0].maxpacketsize = 8

        # if newdev.endpoints[0].maxpacketsize != speed_to_default_mps(speed):
        #     raise Exception("Set specific MPS")
        return newdev

    def control(self, dev, dir, devreq, data_len, src):
        # type: (USBDevice, Direction, DeviceRequest, int, ipc.BitData) -> Tuple[ipc.BitData, int]
        data = src
        logging.debug("xhci.devs[%d]: %s\n%s" % 
                  (dev.address, 
                   hex(self.devs[dev.address].ctx),
                   self.devs[dev.address]))
        epctx = self.devs[dev.address].ep0
        tr = self.devs[dev.address].transfer_rings[1]

        # logging.debug("Transfer ring: {}".format(hex(tr.ring)))

        # const size_t off = (size_t)data & 0xffff;
	    # if ((off + dalen) > ((TRANSFER_RING_SIZE - 4) << 16)) {
		#     xhci_debug("Unsupported transfer size\n");
		#     return -1;
	    # }

        ep_state = epctx.get(EPContextBits.STATE)
        if ep_state > 1:
            logging.debug("Reset endpoint cause it's not running")
            self.reset_endpoint(dev, None)
        
        if data_len:
            data = self.dma_buffer
            if dir == Direction.OUT:
                memcpy(data, src, data_len)

        setup = tr.TRB()
        tr.clear_trb(setup)
        setup.set(TRB.PTR_LOW, devreq.get(DeviceRequest.F1))
        setup.set(TRB.PTR_HIGH, devreq.get(DeviceRequest.F2))
        setup.set(TRBStatusBits.TL, 8)
        trt = TRBDataDirection.NO_DATA
        if data_len:
            trt = TRBDataDirection.OUT_DATA if dir == Direction.OUT else TRBDataDirection.IN_DATA
        setup.set(TRBControlBits.TRT, trt)
        setup.set(TRBControlBits.TT, TRBType.SETUP_STAGE)
        setup.set(TRBControlBits.IDT, 1)
        setup.set(TRBControlBits.IOC, 1)
        setup.write(tr.current)
        tr.enqueue_trb()

        if data_len:
            # logging.debug("dcbaa: = %s" %
            #         (dev.address, hex(t.memblock(phys(self.dcbaa + dev.address*8), 4, 1))))
            dcbaa = t.memblock(phys(self.dcbaa), (dev.address+1)*8, 1)
            logging.debug("dcbaa: %s" % dcbaa)
            mps = epctx.get(EPContextBits.MPS)
            if not mps:
                # A workaround for the case when get_descriptor request is issued
                # first time for FS device
                logging.debug("xhci::control: epctx.MPS is not set. Setting MPS to 8 by default")
                mps = 8
            dt_dir = TRBDirection.OUT if dir == Direction.OUT else TRBDirection.IN
            tr.enqueue_td(1, mps, data_len, data, dt_dir)
        
        # Fill Status TRB
        status = tr.TRB()
        tr.clear_trb(status)
        status.set(TRBControlBits.DIR,
                   TRBDirection.IN if dir == Direction.OUT else TRBDirection.OUT)
        status.set(TRBControlBits.TT, TRBType.STATUS_STAGE)
        status.set(TRBControlBits.IOC, 1)
        status.write(tr.current)
        tr.enqueue_trb()

        self.ring_doorbell(dev.endpoints[0])

        # Wait for transfered events
        transferred = 0
        n_stages = 2 + (1 if data_len else 0)
        for i in xrange(0,n_stages):
            ret = self.wait_for_transfer(dev.address, 1)
            transferred += ret
            if (ret < 0):
                raise Exception("Stage %d/%d failed: %d\n" % (i, n_stages, ret))
                # if ret == TIMEOUT:
                #     logging.debug("Stopping ID %d EP 1\n" % dev.address)
                #     self.cmd_stop_endpoint(dev.address, 1)
                # return ret
        
        if data_len and dir == Direction.IN:
            src = t.memblock(phys(data), transferred, 1)
        return src, transferred
    
    def wait_for_transfer(self, slot_id, ep_id):
        # Type: (int, int) -> int
        logging.debug("Waiting for transfer on ID %d EP %d" % (slot_id, ep_id))
        timeout_us = 5 * 1000 * 1000
        ret = TIMEOUT
        while True:
            timeout_us = self.er.wait_for_event_type(TRBType.EV_TRANSFER, timeout_us)
            if not timeout_us:
                break
            trb = self.er.TRB()
            if (trb.get(TRBControlBits.ID) == slot_id and
                trb.get(TRBControlBits.EP) == ep_id):
                logging.debug("received transfere event for ID %d EP %d" % (slot_id, ep_id))
                ret = -int(trb.get(TRBStatusBits.CC))
                if (ret == -int(TRBCompletionCode.SUCCESS)
                    or ret == -int(TRBCompletionCode.SHORT_PACKET)):
                    ret = int(trb.get(TRBStatusBits.EVTL))
                logging.debug("wait_for_transfer::ret = %d" % ret)
                self.er.advance_dequeue_pointer()
                break
            logging.debug("handle_event in wait_for_transfer")
            self.er.handle_event(trb)
        if (not timeout_us):
            logging.debug("Warning: Timed out waiting for TRB_EV_TRANSFER.")
        self.er.update_event_dq()
        return ret

    def bound_interval(self, ep):
        # Hardcoded for FS device
        if ep.eptype == EndpointType.INTERRUPT:
            if ep.interval < 3:
                return 3
            elif ep.interval > 11:
                return 11
            else:
                ep.interval
        else:
            if ep.interval < 0:
                return 0
            elif ep.interval > 15:
                return 15
            else:
                ep.interval


    def finish_ep_config(self, ep, ic):
        ep_id = eval_ep_id(ep)
        logging.debug("ep_id: {}".format(ep_id))

        if (ep_id <=1 or ep_id >= 32):
            raise Exception("ep_id out of bounds")
        
        tr = XHCICycleRing(32)
        self.devs[ep.dev.address].transfer_rings[ep_id] = tr
        # set add list
        add = t.mem(phys(ic.ctx + 4), 4)
        add |= (1 << ep_id)
        t.mem(phys(ic.ctx + 4), 4, add)

        if ic.dev.slot.get(SlotContextBits.CTXENT) < ep_id:
            ic.dev.slot.set(SlotContextBits.CTXENT, ep_id)
        
        ic.dev.eps[ep_id].set(EPContext.TR_DQ_LOW, tr.ring)
        ic.dev.eps[ep_id].set(EPContext.TR_DQ_HIGH, 0)
        ic.dev.eps[ep_id].set(EPContextBits.INTVAL, self.bound_interval(ep))
        ic.dev.eps[ep_id].set(EPContextBits.CERR, 3)
        ic.dev.eps[ep_id].set(EPContextBits.TYPE, ep.eptype | ((ep.direction != Direction.OUT) << 2))
        ic.dev.eps[ep_id].set(EPContextBits.MPS, ep.maxpacketsize)
        ic.dev.eps[ep_id].set(EPContextBits.DCS, 1)

        if (ep.eptype == EndpointType.BULK or
            ep.eptype == EndpointType.ISOCHRONOUS):
            avrtrb = 3 * 1024
        elif ep.eptype == EndpointType.INTERRUPT:
            avrtrb = 1024
        else:
            avrtrb = 8
        
        ic.dev.eps[ep_id].set(EPContextBits.AVRTRB, avrtrb)
        ic.dev.eps[ep_id].set(EPContextBits.MXESIT,
                              ic.dev.eps[ep_id].get(EPContextBits.MPS) * ic.dev.eps[ep_id].get(EPContextBits.MBS))
        return ic


    def finish_device_config(self, dev):
        slot_id = dev.address
        di = self.devs[slot_id]

        ic = XHCIInputContext(slot_id, [0])
        ic.dev.slot.set(SlotContext.F1, di.slot.get(SlotContext.F1))
        ic.dev.slot.set(SlotContext.F2, di.slot.get(SlotContext.F2))
        ic.dev.slot.set(SlotContext.F3, di.slot.get(SlotContext.F3))
        for i in xrange(1, dev.num_endp):
            ic = self.finish_ep_config(dev.endpoints[i], ic)

        config_id = dev.configuration.get(ConfigurationDescriptorBits.bConfigurationValue)
        logging.debug("config_id: {}".format(int(config_id)))
        cc = self.cr.configure_endpoint(slot_id, config_id, ic)
        if (cc != TRBCompletionCode.SUCCESS):
            raise Exception("configure endpoint failed")

        logging.debug("Endpoints configured")
    
    def bulk(self, ep, size, src):
        # type: ('Endpoint', int, ipc.BitData) -> None
        slot_id = ep.dev.address
        ep_id = eval_ep_id(ep)
        epctx = self.devs[slot_id].eps[ep_id]
        tr = self.devs[slot_id].transfer_rings[ep_id]

        if size:
            data = self.dma_buffer
            if ep.direction == Direction.OUT:
                memcpy(data, src, size)
        
        ep_state = epctx.get(EPContextBits.STATE)
        if ep_state > 1:
            raise Exception("Endpoint %d not running" % ep_id)
        
        mps = int(epctx.get(EPContextBits.MPS))
        dir = TRBDirection.OUT if ep.direction == Direction.OUT else TRBDirection.IN
        tr.enqueue_td(ep_id, mps, size, data, dir)
        self.ring_doorbell(ep)

        # Wait for transfered events    
        transferred = self.wait_for_transfer(ep.dev.address, ep_id)
        if (transferred < 0):
            raise Exception("Bulk transfere failed")
            # if ret == TIMEOUT:
            #     logging.debug("Stopping ID %d EP 1\n" % dev.address)
            #     self.cmd_stop_endpoint(dev.address, 1)
            # return ret
        
        if size and ep.direction == Direction.IN:
            src = t.memblock(data, transferred, 1);
        return src, transferred
        

    def urb_enqueue(self, urb):
        # type: ('URB') -> None
        # slot_id = urb.dev.address
        # ep_index = eval_ep_id(urb.ep)
        # ep_state = int(self.devs[slot_id].eps[ep_index].get(EPContextBits.STATE))
        # if urb.ep.eptype == EndpointType.ISOCHRONOUS:
        #     raise Exception("ISOC eps are not supported")
        # elif (urb.ep.eptype == EndpointType.BULK and
        #       urb.ep.direction == Direction.OUT and
        #       urb.transfer_flags & URB_ZERO_PACKET and
        #       len(urb.transfer_buffer) > 0 and
        #       not (len(urb.transfer_buffer) % urb.ep.maxpacketsize)):
        #     num_tds = 2
        # else:
        #     num_tds = 1
        
        # urb.num_tds = num_tds
        # urb.num_tds_done = 0

        # trace_xhci_urb_enqueue(urb)

        if urb.ep.eptype == EndpointType.BULK:
            self.bulk(urb.ep, len(urb.transfer_buffer)/8, urb.transfer_buffer)
        # elif urb.ep.eptype == EndpointType.INTERRUPT:
        #     self.interrupt(urb.ep, len(urb.transfer_buffer), urb.transfer_buffer)
        else:
            raise Exception("Unsupported urb endpoint type")  


def eval_ep_id(ep):
    # type: ('Endpoint') -> int
    return int((ep.endpoint & 0x7F) * 2) + (ep.direction != Direction.OUT)

if t.isrunning():
    t.halt()    
xhci = XHCI(t)

