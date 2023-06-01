
from generic_hub import GenericHub
from usb import USBDevice, USBSpeed, usb_set_address
from utils import usleep
import logging


class XHCIRootHub(GenericHub, USBDevice):

    def __init__(self, controller):
        num_ports = controller.max_ports
        GenericHub.__init__(self, controller, 0, -1, -1, num_ports)

    def enable_port(self, port):
        """
        Might be needed to implement, but don't know what this quirk for right now

        Source code:

            static int
            xhci_rh_enable_port(usbdev_t *const dev, int port)
            {
                if (CONFIG(LP_USB_XHCI_MTK_QUIRK)) {
                    xhci_t *const xhci = XHCI_INST(dev->controller);
                    volatile u32 *const portsc =
                        &xhci->opreg->prs[port - 1].portsc;

                    /*
                    * Before sending commands to a port, the Port Power in
                    * PORTSC register should be enabled on MTK's xHCI.
                    */
                    *portsc = (*portsc & PORTSC_RW_MASK) | PORTSC_PP;
                }
                return 0;
            }
        """
        pass

    def port_connected(self, port):
        portsc = self.controller.bar_read32(0x480 + 0x10 * (port-1))
        return portsc & 1

    def port_enabled(self, port):
        portsc = self.controller.bar_read32(0x480 + 0x10 * (port-1))
        return bool(portsc & (1 << 1))

    def port_speed(self, port):
        portsc = self.controller.bar_read32(0x480 + 0x10 * (port-1))
        if bool(portsc & (1 << 1)):
            return ((portsc & (((1 << (4)) - 1) << (10))) >> 10) - 1
        else:
            return USBSpeed.UNKNOWN_SPEED

    def port_status_changed(self, port):
        portsc = self.controller.bar_read32(0x480 + 0x10 * (port-1))
        changed = bool(portsc & ((1 << 17) | (1 << 21)))
        # always clear all the status change bits
        new_portsc = (portsc & ((1 << 4) | (((1 << (4)) - 1) << (5)) | (1 << 9) | (((1 << (2)) - 1) << (14)) | (1 << 16)
                                | (1 << 25) | (1 << 26) | (1 << 27))) | 0x00fe0000
        self.controller.bar_write32(0x480 + 0x10 * (port-1), new_portsc)
        return changed

    def port_in_reset(self, port):
        portsc = self.controller.bar_read32(0x480 + 0x10 * (port-1))
        return bool(portsc & (1 << 4))

    # def reset_port(self, port):
    #     portsc = self.controller.bar_read32(0x480 + 0x10 * (port-1))
    #     pls = portsc[5:7]
    #     if pls == 0:
    #         # USB3 port, already reset
    #         logging.debug("USB3 Port")
    #     elif pls == 7:
    #         # Initiate reset
    #         portsc[4] = 1
    #         self.controller.bar_write32(0x480 + 0x10 *(port-1), portsc)
    #     else:
    #         logging.debug("Unknown port state %s" % pls)

    #     timeout = 100
    #     while True:
    #         portsc = self.controller.bar_read32(0x480 + 0x10 * (port-1))
    #         if portsc[0] == 0:
    #             logging.debug("Disconnected while resetting")
    #             return -1
    #         if portsc[1] == 1:
    #             break
    #         timeout -= 1
    #         if timeout == 0:
    #             logging.debug("Timeout on reset")
    #             return -1
    #         usleep(1)
    #     # speed = portsc[10:12]
    #     # XHCI_PORT_SPEEDS = {
    #     #     0: " - ",
    #     #     1: "Full",
    #     #     2: "Low",
    #     #     3: "High",
    #     #     4: "Super"
    #     # }
    #     # logging.debug("Port %d reset. SC=%s - %s Speed" % (port, portsc, XHCI_PORT_SPEEDS.get(int(speed), "Super")))
    #     logging.debug("Port %d reset. SC=%s" % (port, portsc))
    #     return 0

    def reset_port(self, port):
        portsc = self.controller.bar_read32(0x480 + 0x10 * (port-1))

        portsc = (portsc & ((1 << 4) | (((1 << (4)) - 1) << (5)) | (1 << 9) | (((1 << (2)) - 1) << (14)) | (1 << 16)
                            | (1 << 25) | (1 << 26) | (1 << 27))) | (1 << 4)
        self.controller.bar_write32(0x480 + 0x10 * (port-1), portsc)

        if not self.wait_for_port_in_reset(port, False, 150, 1000):
            logging.info("xhci_rh: Reset timed out at port %d" % port)
        else:
            logging.info("Port %d reset." % (port))
            portsc = self.controller.bar_read32(0x480 + 0x10 * (port-1))
            portsc = (portsc & ((1 << 4) | (((1 << (4)) - 1) << (5)) | (1 << 9) | (((1 << (2)) - 1) << (14)) | (1 << 16)
                                | (1 << 25) | (1 << 26) | (1 << 27)) | (1 << 21) | (1 << 19))
            self.controller.bar_write32(0x480 + 0x10 * (port-1), portsc)

    def check_ports(self):
        for i in range(self.num_ports):
            if self.port_connected(i):
                logging.info("Port %d has a connected device" % (i + 1))
                speed = self.reset_port(i)
                if speed > 0:
                    usb_set_address(self.controller, speed, i, self.address)
