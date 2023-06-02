# IPCLib

A set of high-level interfaces to interract with a devices under OpenIPC.
It is meant to be used with OpenIPC's `ipccli` in order to access a device via DCI.

## Repository structure

Repository contains two branches:

`master` branch contains the code which provides general interfaces to interact with devices connected through DCI. There are a lot fo gadjets to inspect Intel SoC and Chipsets architecture.

`xhci`branch contains an implementation of USB stack. This branch was used to organize a leak channel on Intel SoC through USB connection.

## Usage

1. import ipclib: `from ipclib import *`. Import issues `ipccli.baseaccess()` call which would take a few seconds to establish DCI connection with available devices. It access succeds, one should see the list of available TAP points. For example:
```
Indx DID         Alias                                    Type                                    Step Idcode      P/D/ C/T  Enabled
--------------------------------------------------------------------------------------------------------------------------------------------
0    0x00003000  BXTP_CLTAPC0                             BXTP_CLTAPC                             B2   0x00A89013   0/-/ -/-  Yes
1    0x00004000  NORTHPEAK_TAP0                           NORTHPEAK_TAP                           B2   0x00100023   0/-/ -/-  Yes
2    0x00004001  RDU_SE_TAP0                              RDU_SE_TAP                              B2   0x0210002D   0/-/ -/-  Yes
3    0x00004002  CDU_SATAPCIE_TAP0                        CDU_SATAPCIE_TAP                        B2   0x02101613   0/-/ -/-  Yes
4    0x00004003  CDU_SATAPCIE_SCAN_TAP0                   CDU_SATAPCIE_SCAN_TAP                   B2   0x00100915   0/-/ -/-  Yes
5    0x00004004  CDU_SATAPCIE_RETIME_TAP0                 CDU_SATAPCIE_RETIME_TAP                 B2   0x00100905   0/-/ -/-  Yes
6    0x00004005  CDU_PCIE_TAP0                            CDU_PCIE_TAP                            B2   0x0210162B   0/-/ -/-  Yes
7    ...
```

If the connection have not been established, try reopening python console and import `ipclib` once again. Try to mix with the order in which you power on target device and import ipclib.

2. After establishing the connection, one can access library interfaces and global variables. The following global variables are available:
    a. `t` - the variable containing the first thread of the device.
    b. `ipc` - the ipc object itself.
    c. `xhci` - XHCI controller object.

Please look at the code itself to figure out which functions are available and what they do. There is no guarantee that none of them are broken.

The XHCI Controller code was heavily inspired by coreboot and the seabios implementation. The CH341 driver was inspired by the linux kernel impleme

## License

This code is licensed under the GPL v3 license.