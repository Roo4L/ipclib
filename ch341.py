from xhci import *
from usb import *
from serial import *
import math

DEFAULT_BAUD_RATE = 9600

CH341_LCR_ENABLE_PAR = 0x08
CH341_LCR_PAR_EVEN = 0x10
CH341_LCR_MARK_SPACE = 0x20

CH341_LCR_ENABLE_RX = 0x80
CH341_LCR_ENABLE_TX = 0x40

CH341_LCR_CS5 = 0x00
CH341_LCR_CS6 = 0x01
CH341_LCR_CS7 = 0x02
CH341_LCR_CS8 = 0x03
CH341_LCR_STOP_BITS_2 = 0x04

CH341_REQ_READ_VERSION = 0x5F
CH341_REQ_READ_REG = 0x95
CH341_REQ_WRITE_REG = 0x9A
CH341_REQ_SERIAL_INIT = 0xA1
CH341_REQ_MODEM_CTRL = 0xA4

CH341_REG_BREAK = 0x05
CH341_REG_PRESCALER = 0x12
CH341_REG_DIVISOR = 0x13

CH341_REG_LCR = 0x18
CH341_REG_LCR2 = 0x25

CH341_BIT_DTR = (1 << 5)
CH341_BIT_RTS = (1 << 6)

CH341_QUIRK_LIMITED_PRESCALER = 0x01
CH341_QUIRK_SIMULATE_BREAK = 0x02

CH341_BITS_MODEM_STAT = 0x0F

CH341_CLKRATE = 48000000

def ch341_clk_div(ps, fact):
    return (1 << (12 - 3 * (ps) - (fact)))

def ch341_min_rate(ps):
    return (CH341_CLKRATE / (ch341_clk_div((ps), 1) * 512))

def div_round_up(n, d):
    return math.floor(((n) + (d) - 1) / (d))

CH341_MIN_BPS = div_round_up(CH341_CLKRATE, ch341_clk_div(0, 0) * 256)
CH341_MAX_BPS = (CH341_CLKRATE / (ch341_clk_div(3, 0) * 2))

class CH341(USBSerialGeneric):

    lcr = None  
    baud_rate = None
    version = None
    quirks = 0
    mcr = 0

    def __init__(self):
        self.min_rates = [ch341_min_rate(i) for i in xrange(4)]

    def port_probe(self, port):
        # type: ('USBSerialPort') -> None
        self.baud_rate = DEFAULT_BAUD_RATE
        self.lcr = CH341_LCR_ENABLE_RX | CH341_LCR_ENABLE_TX | CH341_LCR_CS8

        self.configure(port.serial.dev)
        # usb_set_serial_port_data(port)
        self.detect_quirks(port)

    def configure(self, dev):
        buffer = ipc.BitData(2*8, 0)
        size = 2

        buffer = self.control_in(dev, CH341_REQ_READ_VERSION, 0, 0, buffer, size)

        self.version = int(buffer[0:7])
        usb_debug("Chip version: %x" % self.version)

        self.control_out(dev, CH341_REQ_SERIAL_INIT, 0, 0)
        
        self.set_baudrate_lcr(dev, self.baud_rate, self.lcr)
        self.set_handshake(dev, self.mcr)
    
    def detect_quirks(self, port):
        udev = port.serial.dev
        buffer = ipc.BitData(2*8, 0)
        size = 2

        # dr = DeviceRequest()
        # dr.set(DeviceRequestBits.bmRequestType, gen_bmRequestType(
        #     DevReqDir.device_to_host,
        #     DevReqType.vendor_type,
        #     DevReqRecp.dev_recp
        # ))
        # dr.set(DeviceRequestBits.bRequest, CH341_REQ_READ_REG)
        # dr.set(DeviceRequestBits.wValue, CH341_REG_BREAK)
        # dr.set(DeviceRequestBits.wIndex, 0)
        # dr.set(DeviceRequestBits.wLength, size)

        # buffer, transfered = udev.controller.control(udev, Direction.IN, dr, size, buffer)
        # if transfered != size:
        #     raise Exception("control_in CH341_REQ_READ_REG:CH341_REG_BREAK request failed\n"
        #                     "Perhaps break control is not supported")

        quirks = CH341_QUIRK_LIMITED_PRESCALER | CH341_QUIRK_SIMULATE_BREAK

        if quirks:
            usb_debug("enabling quirk flags: 0x%02lx\n" % quirks)
            self.quirks |= quirks

    def control_in(self, dev, request, value, index, buf, bufsize):
        # type: ('USBDevice', int, int, int, ipc.BitData, int) -> ipc.BitData
        
        dr = DeviceRequest()
        dr.set(DeviceRequestBits.bmRequestType, gen_bmRequestType(
            DevReqDir.device_to_host,
            DevReqType.vendor_type,
            DevReqRecp.dev_recp
        ))
        dr.set(DeviceRequestBits.bRequest, request)
        dr.set(DeviceRequestBits.wValue, value)
        dr.set(DeviceRequestBits.wIndex, index)
        dr.set(DeviceRequestBits.wLength, bufsize)


        buf, transfered = dev.controller.control(dev, Direction.IN, dr, bufsize, buf)

        if transfered != bufsize:
            raise Exception("control_in %x failed" % request)
        return buf
    
    def control_out(self, dev, request, value, index):
        dr = DeviceRequest()
        dr.set(DeviceRequestBits.bmRequestType, gen_bmRequestType(
            DevReqDir.host_to_device,
            DevReqType.vendor_type,
            DevReqRecp.dev_recp
        ))
        dr.set(DeviceRequestBits.bRequest, request)
        dr.set(DeviceRequestBits.wValue, value)
        dr.set(DeviceRequestBits.wIndex, index)
        dr.set(DeviceRequestBits.wLength, 0)

        _, transfered = dev.controller.control(dev, Direction.OUT,
                                                 dr, 0, None)
        
        if transfered != 0:
            raise Exception("control_out %x failed" % request)

    def get_divisor(self, speed):
        force_fact0 = False
        speed = clamp_val(speed, CH341_MIN_BPS, CH341_MAX_BPS)

        ps = -1
        fact = 1
        for i in xrange(3, -1, -1):
            if speed > self.min_rates[i]:
                ps = i
                break
        
        if ps < 0:
            raise Exception("Invalid speed")

        clk_div = ch341_clk_div(ps, fact)
        div = CH341_CLKRATE / (clk_div * speed)
        
        # Some devices require a lower base clock if ps < 3.
        if (ps < 3 and (self.quirks & CH341_QUIRK_LIMITED_PRESCALER)):
            force_fact0 = True

        # Halve base clock (fact = 0) if required.
        if (div < 9 or div > 255 or force_fact0):
            div /= 2
            clk_div *= 2
            fact = 0
        
        if div < 2:
            raise Exception("Invalid divisor")

        if (16 * CH341_CLKRATE / (clk_div * div) - 16 * speed >=
            16 * speed - 16 * CH341_CLKRATE / (clk_div * (div + 1))):
            div += 1

        if (fact == 1 and div % 2 == 0):
            div /= 2
            fact = 0
        
        return (0x100 - div) << 8 | fact << 2 | ps

    def set_baudrate_lcr(self, dev, baudrate, lcr):
        if baudrate is None or self.baud_rate is None:
            raise Exception("Invalid baudrate")
        val = self.get_divisor(baudrate)
        
        if self.version > 0x27:
            val |= (1 << 7)
        
        self.control_out(dev, CH341_REQ_WRITE_REG,
                         (CH341_REG_DIVISOR << 8) | CH341_REG_PRESCALER,
                         val)
        if self.version < 0x30:
            return
        
        self.control_out(dev, CH341_REQ_WRITE_REG,
                         CH341_REG_LCR2 << 8 | CH341_REG_LCR,
                         lcr)
    
    def set_handshake(self, dev, control):
        self.control_out(dev, CH341_REQ_MODEM_CTRL, ~control, 0)
    
    def open(self, port):
        # type: ('USBSerialPort') -> None
        # if tty:
        #     self.set_termios(tty, port, None)
        
        # usb_debug("submitting interrupt urb")
        # port.interrupt_in_urb.submit()
        # if r:
        #     raise Exception("failed to submit interrupt urb: %d" % r)
        self.get_status(port.serial.dev)
        
        USBSerialGeneric.open(self, port)
    
    # def set_termios(self, tty, port , old_termios):
    #     # /* redundant changes may cause the chip to lose bytes */
    #     # if (old_termios && !tty_termios_hw_change(&tty->termios, old_termios))
    #     #     return;

    #     baud_rate = tty.get_baud_rate()
    #     lcr = CH341_LCR_ENABLE_RX | CH341_LCR_ENABLE_TX

    #     csize = tty.termios.c_cflag & 0000060
    #     if csize == 0000000:
    #         lcr |= CH341_LCR_CS5
    #     elif csize == 0000020:
    #         lcr |= CH341_LCR_CS6
    #     elif csize == 0x0000040:
    #         lcr |= CH341_LCR_CS7
    #     elif csize == 0000060:
    #         lcr |= CH341_LCR_CS8
        
    #     parenb = tty.termios.c_cflag & 0000400
    #     if parenb:
    #         lcr |= CH341_LCR_ENABLE_PAR
    #         if tty.termios.c_cflag & 0001000:
    #             lcr |= CH341_LCR_PAR_EVEN
    #         if tty.termios.c_cflag & 010000000000:
    #             lcr |= CH341_LCR_MARK_SPACE
        
    #     if tty.termios.c_cflags & 0000100:
    #         lcr |= CH341_LCR_STOP_BITS_2
        
    #     if baud_rate:
    #         self.baud_rate = baud_rate
    #         r = self.set_baudrate_lcr(port.serial.dev, baud_rate, lcr)
    #         if r < 0 and old_termios:
    #             raise Exception("old_termios not None")
    #         elif r == 0:
    #             self.lcr = lcr
        
    #     if tty.termios.c_cflags & 000000010017 == 000000000000:
    #         self.mcr &= ~(CH341_BIT_DTR | CH341_BIT_RTS)
        
    #     self.set_handshake(port.serial.dev, self.mcr)


    def get_status(self, dev):
        # type: ('USBDevice') -> None
        buffer = ipc.BitData(2*8, 0)
        size = 2

        buffer = self.control_in(dev, CH341_REQ_READ_REG, 0x0706, 0, 
                                 buffer, size)
        self.msr = (~buffer) & CH341_BITS_MODEM_STAT


def clamp_val(val, lo, hi):
    return hi if val > hi else lo if val < lo else val