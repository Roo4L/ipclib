import proc
import ipccli

class CSEController:
    def __init__(self, execution_thread):
        if execution_thread.name != 'CSE_C0_T0':
            raise Exception("CSEController must be created from CSE_C0_T0 thread")
        self.thread = execution_thread

    def reset(self):
        self.thread.halt()
        self.set_register("eip", self.get_proc_address("RESET_ME_CALL"))
        ebp = self.get_register("ebp")
        self.step_over(4)
        self.thread.mem(ipccli.Address(ebp-8), 4, 0xd)
        self.thread.go()
    
    def resume(self):
        self.thread.halt()
        esp = self.pop()
        self.set_register("eip", esp)
        self.thread.go()
    
    def pop(self):
        ss = self.get_register("ss")
        ret = self.thread.mem(ss.ToHex() + ":" + self.get_register("esp").ToHex(), 4)
        self.set_register("esp", self.get_register("esp") + 4)
        return ret

    def set_register(self, name, value):
        self.thread.arch_register(name, value)

    def get_register(self, name):
        return self.thread.arch_register(name)

    def get_proc_address(self, name):
         return proc.proc_addresses[name][self.thread.name]

    def step_over(self, steps=1):
        instructions = self.asm("$", steps + 1)
        self.go_until(instructions[-1].address)

    def asm(self, addr, size=1):
        # thread.asm changes the register values, so we need to save them first!
        eax = self.get_register("eax")
        ebx = self.get_register("ebx")
        ecx = self.get_register("ecx")
        edx = self.get_register("edx")
        result = self.thread.asm(addr, size)
        self.set_register("eax", eax)
        self.set_register("ebx", ebx)
        self.set_register("ecx", ecx)
        self.set_register("edx", edx)
        return result

    def go_until(self, addr):
        br = self.thread.brnew(addr)
        self.thread.go()
        while (self.thread.isrunning()):
            pass
        self.thread.brremove(br)
        self.asm("$", 5)
