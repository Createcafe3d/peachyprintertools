import unittest
import os
import sys
import time
import logging
from mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from peachyprinter.infrastructure.layer_control import *
from peachyprinter.domain.commands import *
from peachyprinter.infrastructure.machine import MachineStatus
from peachyprinter.infrastructure.controller import *
from peachyprinter.infrastructure.layer_generators import StubLayerGenerator
from peachyprinter.infrastructure.communicator import MissingPrinterException

@patch('infrastructure.layer_control.LayerWriter')
@patch('infrastructure.layer_control.LayerProcessing')
@patch('domain.layer_generator.LayerGenerator')
class ControllerTests(unittest.TestCase):
    controller = None

    def wait_for_controller(self): 
        while self.controller.is_alive():
            time.sleep(0.01)

    def tearDown(self):
        if self.controller and self.controller.is_alive():
            self.controller.close()

    def test_close_should_close_all_processes_cleanly(self, mock_LayerGenerator, mock_LayerWriter, mock_LayerProcessing):
        mock_layer_writer = mock_LayerWriter.return_value
        mock_layer_processing = mock_LayerProcessing.return_value
        mock_layer_generator = mock_LayerGenerator.return_value
        mock_layer_generator.next.return_value = Layer(0.0, [LateralDraw([0.0, 0.0], [2.0, 2.0], 2.0)])
        self.controller = Controller(mock_layer_writer, mock_layer_processing, mock_layer_generator, MachineStatus())
        self.controller.start()

        time.sleep(0.1)

        self.controller.close()

        time.sleep(0.1)

        mock_layer_writer.terminate.assert_called_with()
        mock_layer_processing.terminate.assert_called_with()

    def test_run_should_update_machine_status_on_complete(self, mock_LayerGenerator, mock_LayerWriter, mock_LayerProcessing):
        mock_layer_writer = mock_LayerWriter.return_value
        mock_layer_processing = mock_LayerProcessing.return_value
        test_layer1 = Layer(1.0, [LateralDraw([0.0, 0.0], [2.0, 2.0], 2.0)])
        stub_layer_generator = StubLayerGenerator([test_layer1])

        self.controller = Controller(mock_layer_writer, mock_layer_processing, stub_layer_generator, MachineStatus(), True)
        self.controller.start()

        self.wait_for_controller()

        self.assertEquals("Complete", self.controller.get_status()['status'])

    def test_run_should_record_errors_and_abort(self, mock_LayerGenerator, mock_LayerWriter, mock_LayerProcessing):
        mock_layer_writer = mock_LayerWriter.return_value
        mock_layer_processing = mock_LayerProcessing.return_value
        mock_layer_generator = mock_LayerGenerator.return_value
        mock_layer_generator.next.return_value = Layer(1.0, [LateralDraw([0.0, 0.0], [2.0, 2.0], 2.0)])
        mock_layer_processing.process.side_effect = Exception("Something Broke")

        self.controller = Controller(mock_layer_writer, mock_layer_processing, mock_layer_generator, MachineStatus(), True)
        self.controller.start()

        self.wait_for_controller()

        self.assertTrue(1 <= len(self.controller.get_status()['errors']))
        self.assertEquals("Something Broke", self.controller.get_status()['errors'][0]['message'])
        mock_layer_writer.terminate.assert_called_with()
        mock_layer_processing.terminate.assert_called_with()
        self.assertEquals("Cancelled", self.controller.get_status()['status'])

    def test_run_should_record_errors_and_fail(self, mock_LayerGenerator, mock_LayerWriter, mock_LayerProcessing):
        mock_layer_writer = mock_LayerWriter.return_value
        mock_layer_processing = mock_LayerProcessing.return_value
        mock_layer_generator = mock_LayerGenerator.return_value
        mock_layer_generator.next.return_value = Layer(1.0, [LateralDraw([0.0, 0.0], [2.0, 2.0], 2.0)])
        mock_layer_processing.process.side_effect = MissingPrinterException("Something Broke")

        self.controller = Controller(mock_layer_writer, mock_layer_processing, mock_layer_generator, MachineStatus(), True)
        self.controller.start()

        self.wait_for_controller()

        self.assertTrue(1 <= len(self.controller.get_status()['errors']))
        self.assertEquals("Something Broke", self.controller.get_status()['errors'][0]['message'])
        mock_layer_writer.terminate.assert_called_with()
        mock_layer_processing.terminate.assert_called_with()
        self.assertEquals("Failed", self.controller.get_status()['status'])

    def test_run_should_record_errors_and_continue_when_abort_on_error_is_false(self, mock_LayerGenerator, mock_LayerWriter, mock_LayerProcessing):
        mock_layer_writer = mock_LayerWriter.return_value
        mock_layer_processing = mock_LayerProcessing.return_value
        test_layer1 = Layer(0.0, [LateralDraw([0.0, 0.0], [2.0, 2.0], 100.0)])
        test_layer2 = Layer(0.1, [LateralDraw([0.0, 0.0], [2.0, 2.0], 100.0)])
        stub_layer_generator = StubLayerGenerator([test_layer1, test_layer2])
        mock_layer_processing.process.side_effect = Exception("Something Broke")

        self.controller = Controller(mock_layer_writer, mock_layer_processing, stub_layer_generator, MachineStatus(), False)
        self.controller.start()

        self.wait_for_controller()

        self.assertEquals(2, len(self.controller.get_status()['errors']), self.controller.get_status()['errors'])
        mock_layer_processing.process.assert_called_with(test_layer2)
        mock_layer_writer.terminate.assert_not_called()
        mock_layer_processing.terminate.assert_not_called()

    def test_run_should_record_errors_and_abort_when_printer_is_detached(self, mock_LayerGenerator, mock_LayerWriter, mock_LayerProcessing):
        mock_layer_writer = mock_LayerWriter.return_value
        mock_layer_processing = mock_LayerProcessing.return_value
        test_layer1 = Layer(0.0, [LateralDraw([0.0, 0.0], [2.0, 2.0], 100.0)])
        stub_layer_generator = StubLayerGenerator([test_layer1])
        mock_layer_processing.process.side_effect = MissingPrinterException("Something Broke")

        self.controller = Controller(mock_layer_writer, mock_layer_processing, stub_layer_generator, MachineStatus(), False)
        self.controller.start()

        self.wait_for_controller()

        self.assertEquals(1, len(self.controller.get_status()['errors']), self.controller.get_status()['errors'])
        mock_layer_processing.process.assert_called_with(test_layer1)
        mock_layer_writer.terminate.assert_called()
        mock_layer_processing.terminate.assert_called()

    def test_change_generator_should_change_layer_generator(self, mock_LayerGenerator, mock_LayerWriter, mock_LayerProcessing):
        mock_layer_writer = mock_LayerWriter.return_value
        mock_layer_processing = mock_LayerProcessing.return_value

        test_layer1 = Layer(0.0, [LateralDraw([0.0, 0.0], [2.0, 2.0], 100.0)])
        test_layer2 = Layer(0.1, [LateralDraw([0.0, 0.0], [2.0, 2.0], 100.0)])
        stub_layer_generator1 = StubLayerGenerator([test_layer1], repeat=True)
        stub_layer_generator2 = StubLayerGenerator([test_layer2], repeat=True)

        self.controller = Controller(mock_layer_writer, mock_layer_processing, stub_layer_generator1, MachineStatus(), False)
        self.controller.start()
        time.sleep(0.5)
        pre_switch = mock_layer_processing.process.call_args
        self.controller.change_generator(stub_layer_generator2)
        time.sleep(0.5)
        post_switch = mock_layer_processing.process.call_args
        self.controller.close()
        self.wait_for_controller()

        self.assertEquals(test_layer1, pre_switch[0][0])
        self.assertEquals(test_layer2, post_switch[0][0])

    def test_change_generator_should_stop_working_on_current_commands(self, mock_LayerGenerator, mock_LayerWriter, mock_LayerProcessing):
        mock_layer_writer = mock_LayerWriter.return_value
        mock_layer_processing = mock_LayerProcessing.return_value
        test_layer1 = Layer(1.0, [LateralDraw([2.0, 2.0], [0.0, 0.0], 2.0) for x in range(0, 32768)])
        test_layer2 = Layer(1.0, [LateralDraw([0.0, 0.0], [0.0, 0.0], 2.0)])
        stub_layer_generator1 = StubLayerGenerator([test_layer1], repeat=True)
        stub_layer_generator2 = StubLayerGenerator([test_layer2], repeat=True)
        self.controller = Controller(mock_layer_writer, mock_layer_processing, stub_layer_generator1, MachineStatus(),)
        self.controller.start()
        time.sleep(0.1)

        self.controller.change_generator(stub_layer_generator2)
        time.sleep(0.1)
        self.controller.close()
        self.wait_for_controller()

        mock_layer_processing.abort_current_command.assert_called_with()


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level='DEBUG')
    unittest.main()
