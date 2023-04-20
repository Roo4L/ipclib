from usb import USBDevice, HCI

class GenericHub(USBDevice):
    
    num_ports = None
    ports = None

    def __init__(self, controller, address, hub, port, num_ports):
        # type: ('HCI', int, int, int, int) -> None
        USBDevice.__init__(self, controller, address, hub, port)
        self.num_ports = num_ports
        self.ports = [-1 for i in xrange(num_ports)]
        for i in xrange(num_ports):
            self.enable_port(i)
    
    def enable_port(self, port):
        pass

    def init():
        pass

    def poll():
        pass