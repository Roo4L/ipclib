from usb import USBDevice, HCI, usb_attach_device
from utils import usleep
import logging

class GenericHub(USBDevice):
    
    num_ports = None
    ports = None

    def __init__(self, controller, address, hub, port, num_ports):
        # type: ('HCI', int, int, int, int) -> None
        USBDevice.__init__(self, controller, address, hub, port)
        self.num_ports = num_ports
        self.ports = [-1 for i in xrange(num_ports + 1)]
        for i in xrange(num_ports):
            self.enable_port(i)
    
    def enable_port(self, port):
        logging.error("hub's enable_port not implemented")
        pass

    def port_status_changed(self, port):
        logging.error("hub's port_status_has_changed not implemented")
        pass

    def port_connected(self, port):
        logging.error("hub's port_connected not implemented")
        pass

    def port_enabled(self, port):
        logging.error("hub's port_enabled not implemented")
        pass

    def port_speed(self, port):
        logging.error("hub's port_speed not implemented")
        pass

    def wait_for_port_enabled(self, port, wait_for, timeout_steps, step_us):
        while timeout_steps:
            state = self.port_enabled(port)
            if bool(state) == wait_for:
                return timeout_steps
            usleep(step_us)
            timeout_steps -= 1
        return 0

    def wait_for_port_in_reset(self, port, wait_for, timeout_steps, step_us):
        while timeout_steps:
            state = self.port_in_reset(port)
            if bool(state) == wait_for:
                return timeout_steps
            usleep(step_us)
            timeout_steps -= 1
        return 0
    
    def debounce(self, port):
        step_ms = 1
        at_least_ms = 100
        timeout_ms = 1500

        total_ms = 0
        stable_ms = 0
        while stable_ms < at_least_ms and total_ms < timeout_ms:
            usleep(step_ms * 1000)
            changed = self.port_status_changed(port)
            connected = self.port_connected(port)

            # if (changed < 0 || connected < 0)
            #   return -1;
            if not changed and connected:
                stable_ms += step_ms
            else:
                logging.info("generic_hub: Unstable connection at %d" % port);
                stable_ms = 0
            
            total_ms += step_ms
        if total_ms >= timeout_ms:
            logging.info("generic_hub: Debouncing timed out at %d" % port)
        return 0

    def attach_dev(self, port):
        if self.debounce(port):
            raise Exception("")
                    # if (changed < 0 || connected < 0)
            # return -1;
        self.reset_port(port)
        if not self.port_connected(port):
            logging.info(
                "generic_hub: Port %d disconnected after "
                "reset. Possibly upgraded, rescan required.\n" % port)
            return
        ret = self.wait_for_port_enabled(port, True, 1000, 10)
        if ret < 0:
            raise Exception("")
        elif not ret:
            logging.info("generic_hub: Port %d still "
                    "disabled after 10ms" % port)
        
        speed = self.port_speed(port)
        if (speed >= 0):
            logging.info("generic_hub: Success at port %d" % port)
            # Reset recovery time (usb20 spec 7.1.7.5)
            usleep(10 * 1000)
            self.ports[port] = usb_attach_device(self.controller, self.address, port, speed)

    def scanport(self, port):
        if self.ports[port] >= 0:
            logging.info("generic_hub: Detachment at port %d" % port)
            # self.detach_dev(port)
        
        if self.port_connected(port):
            logging.info("generic_hub: Attachment at port %d" % port)
            self.attach_dev(port)

    def poll(self):
        # if (!(dev->quirks & USB_QUIRK_HUB_NO_USBSTS_PCD) &&
        #     hub->ops->hub_status_changed &&
        #     hub->ops->hub_status_changed(dev) != 1) {
        #     return;
        # }
        # for port in xrange(1, self.num_ports + 1):
        port = 1 # Poll only first port to scan for arduino
        if self.port_status_changed(port):
            logging.info("generic_hub: Port change at %d" % port)
            self.scanport(port)