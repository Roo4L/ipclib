
from generic_hub import GenericHub
from usb import USBDevice, usb_set_address, usb_debug
from utils import usleep

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
        portsc = self.controller.bar_read32(0x480 + 0x10 * port)
        return portsc & 1
    
    def reset_port(self, port):
        portsc = self.controller.bar_read32(0x480 + 0x10 * port)
        pls = portsc[5:7]
        if pls == 0:
            # USB3 port, already reset
            usb_debug("USB3 Port")
        elif pls == 7:
            # Initiate reset
            portsc[4] = 1
            self.controller.bar_write32(0x480 + 0x10 *port, portsc)
        else:
            usb_debug("Unknown port state %s" % pls)
        
        timeout = 100    
        while True:
            portsc = self.controller.bar_read32(0x480 + 0x10 * port)
            if portsc[0] == 0:
                usb_debug("Disconnected while resetting")
                return -1
            if portsc[1] == 1:
                break
            timeout -= 1
            if timeout == 0:
                usb_debug("Timeout on reset")
                return -1
            usleep(1)
        speed = portsc[10:12]
        XHCI_PORT_SPEEDS = {
            0: " - ",
            1: "Full",
            2: "Low",
            3: "High",
            4: "Super"
        }
        usb_debug("Port %d reset. SC=%s - %s Speed" % (port + 1, portsc, XHCI_PORT_SPEEDS.get(int(speed), "Super")))
        return speed


    def check_ports(self):
        for i in range(self.num_ports):
            if self.port_connected(i):
                usb_debug("Port %d has a connected device" % (i + 1))
                speed = self.reset_port(i)
                if speed > 0:
                    usb_set_address(self.controller, speed, i, self.address)
        
