import logging
import os
import sys
import re
import time
from glob import glob
import threading
import firmware as firmware_manager_factory

from peachyprinter.infrastructure.communicator import UsbPacketCommunicator
from peachyprinter.infrastructure.messages import EnterBootloaderMessage

logger = logging.getLogger('peachy')

class FirmwareAPI(object):
    '''Allows for checking and upgrading device firmware
    Simple usage:

    is_complete = false

    def complete_callback(result):
        if result:
            is_complete = true
        else:
            exit()

    firmware_api = FirmwareAPI()

    if not firmware_api.is_firmware_valid(configuration_api.get_info_firmware_version_number()):
        firmware_api.make_ready()
        update_firmware(complete_callback)
        while not is_complete:
            time.sleep(1)
    '''

    version_regex = '''.*-([0-9]*[.][0-9]*[.][0-9]*).(bin|dfu)'''

    def __init__(self):
        self.firmware_manager = firmware_manager_factory.get_firmware_updater()
        self._required_version = None
        self._firmware_update = FirmwareUpdate(self._bin_file(), self.firmware_manager)

    @property
    def required_version(self):
        '''The version of firmware required by this version of the api'''

        if self._required_version is None:
            bin_file = self._bin_file()
            self._required_version = re.match(self.version_regex, bin_file).group(1)
        return self._required_version

    def is_firmware_valid(self, current_firmware):
        '''Returns a boolean true if the version of the software matches the required version'''

        return self.required_version == current_firmware

    def _bin_file(self):
        if getattr(sys, 'frozen', False):
            path = sys._MEIPASS
        else:
            path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dependancies', 'firmware'))
        print('PLATFORM: {}'.format(sys.platform))
        if sys.platform.startswith('win') or sys.platform.startswith('cygwin'):
            bin_file = glob(os.path.join(path, 'peachyprinter-firmware-*.dfu'))
        else:
            bin_file = glob(os.path.join(path, 'peachyprinter-firmware-*.bin'))
        if not bin_file:
            logger.error("Package missing required firmware at path: {}".format(path))
            raise Exception("Package missing required firmware")
        if len(bin_file) > 1:
            logger.error("Unexpected firmware files")
            raise Exception("Unexpected firmware files")
        return bin_file[0]

    def make_ready(self):
        '''Forces the printer into bootloader mode so it can recieve an update'''

        self._firmware_update.prepare()

    def is_ready(self):
        '''Checks if the printer is in bootloader mode so it can recieve an update'''

        return self.firmware_manager.check_ready()

    def update_firmware(self, complete_call_back=None):
        '''Starts an a-syncronous firmware update a callback for completion of this process may be specified'''

        if self.is_ready():
            logger.info("Starting external update")
            self._firmware_update.start(complete_call_back)
        else:
            logger.error("Peachy Printer not ready for update")
            raise Exception("Peachy Printer not ready for update")


class FirmwareUpdate(threading.Thread):
    def __init__(self, file, firmware_updater, complete_call_back=None):
        threading.Thread.__init__(self)
        self.file = file
        self.firmware_manager = firmware_updater

    def start(self, complete_call_back):
        self.complete_call_back = complete_call_back
        threading.Thread.start(self)

    def run(self):
        logger.info("Starting firmware update")
        result = self.firmware_manager.update(self.file)
        self.complete_call_back(result)
        logger.info("Firmware update {}".format("succeeded" if result else "failed"))

    def prepare(self):
        usb_communicator = UsbPacketCommunicator(50)
        usb_communicator.start()
        usb_communicator.send(EnterBootloaderMessage())
        time.sleep(0.1)  #need to wait for usb
        usb_communicator.close()
