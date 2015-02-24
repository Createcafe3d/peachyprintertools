import logging
from peachyprinter.infrastructure.audio import AudioWriter
from peachyprinter.infrastructure.audiofiler import PathToAudio
from peachyprinter.infrastructure.controller import Controller
from peachyprinter.infrastructure.communicator import SerialCommunicator
from peachyprinter.domain.laser_control import LaserControl
from peachyprinter.infrastructure.audio_disseminator import AudioDisseminator
from peachyprinter.infrastructure.micro_disseminator import MicroDisseminator
from peachyprinter.infrastructure.transformer import TuningTransformer, HomogenousTransformer
from peachyprinter.infrastructure.layer_generators import *
from peachyprinter.infrastructure.machine import *
from peachyprinter.infrastructure.layer_control import LayerWriter, LayerProcessing


'''The calibration API proivides the tools required to setup a Peacy Printer'''


class CalibrationAPI(object):
    def __init__(self, configuration_manager, printer):
        logging.info("Calibartion API Startup")
        self._configuration_manager = configuration_manager
        self._printer = printer
        self._configuration = self._configuration_manager.load(self._printer)

        self._point_generator = SinglePointGenerator()
        self._blink_generator = BlinkGenerator()
        self._alignment_generator = CalibrationLineGenerator()
        self._scale_generator = SquareGenerator(speed=1, radius=1)

        self._test_patterns = {
            'Hilbert Space Filling Curve': HilbertGenerator(),
            'Square': SquareGenerator(),
            'Circle': CircleGenerator(),
            'Spiral': SpiralGenerator(),
            'Memory Hourglass': MemoryHourglassGenerator(),
            'Damping Test': DampingTestGenerator(),
            'NESW': NESWGenerator(),
            'Twitch': TwitchGenerator(),
            }

        self._current_generator = self._point_generator

        self._laser_control = LaserControl()
        transformer = TuningTransformer(scale=self._configuration.calibration.max_deflection)

        self._audio_writer = None
        self._controller = None
        logging.debug("Setting up audiowriter")

        self._current_generator = self._point_generator

        self._state = MachineState()
        self._status = MachineStatus()

        if self._configuration.circut.circut_type == 'Digital':
            self._communicator = SerialCommunicator(
                self._configuration.micro_com.port,
                self._configuration.micro_com.header,
                self._configuration.micro_com.footer,
                self._configuration.micro_com.escape,
                )
            self._communicator.start()
            self._disseminator = MicroDisseminator(
                self._laser_control,
                self._communicator,
                self._configuration.micro_com.rate
                )
        else:
            self._audio_writer = AudioWriter(
                self._configuration.audio.output.sample_rate,
                self._configuration.audio.output.bit_depth,
            )
            self._disseminator = AudioDisseminator(
                self._laser_control,
                self._audio_writer,
                self._configuration.audio.output.sample_rate,
                self._configuration.audio.output.modulation_on_frequency,
                self._configuration.audio.output.modulation_off_frequency,
                self._configuration.options.laser_offset
                )

        self._path_to_audio = PathToAudio(
            self._disseminator.samples_per_second,
            transformer,
            self._configuration.options.laser_thickness_mm
            )

        post_fire_delay_speed = None
        slew_delay_speed = None
        if self._configuration.options.post_fire_delay:
            post_fire_delay_speed = self._configuration.options.laser_thickness_mm / (float(self._configuration.options.post_fire_delay) / 1000.0)
        if self._configuration.options.slew_delay:
            slew_delay_speed = self._configuration.options.laser_thickness_mm / (float(self._configuration.options.slew_delay) / 1000.0)

        self._writer = LayerWriter(
            self._disseminator,
            self._path_to_audio,
            self._laser_control,
            self._state,
            post_fire_delay_speed=post_fire_delay_speed,
            slew_delay_speed=slew_delay_speed
            )

        self._layer_processing = LayerProcessing(
            self._writer,
            self._state,
            self._status,
            )

        self._controller = Controller(
            self._writer,
            self._layer_processing,
            self._current_generator,
            self._status,
            abort_on_error=False,
            )

        self.make_pattern_fit()
        self._controller.start()

    '''Used to show a single point with no calibration applied'''
    def show_point(self, xyz=[0.5, 0.5, 0.5]):
        logging.info('Showing point')
        x, y, z = xyz
        self._point_generator.xy = [x, y]
        if (self._current_generator != self._point_generator):
            self._unapply_calibration()
            self._update_generator(self._point_generator)

    '''Used to show a blinking point with no calibration applied used for aligning on and off laser posisition'''
    def show_blink(self, xyz=[0.5, 0.5, 0.0]):
        logging.info('Showing blink')
        x, y, z = xyz
        self._blink_generator.xy = [x, y]
        if (self._current_generator != self._blink_generator):
            self._unapply_calibration()
            self._update_generator(self._blink_generator)

    '''Used to show a single line on one axis used to line up calibration grid'''
    def show_line(self):
        logging.info('Showing line')
        self._unapply_calibration()
        self._update_generator(self._alignment_generator)

    '''Used to show a test pattern with calibration applied'''
    def show_test_pattern(self, pattern):
        logging.info('Showing test pattern %s' % pattern)
        if pattern in self._test_patterns.keys():
            self._apply_calibration()
            self._update_generator(self._test_patterns[pattern])
        else:
            logging.error('Pattern: %s does not exist' % pattern)
            raise Exception('Pattern: %s does not exist' % pattern)

    '''Shows the scale square'''
    def show_scale(self):
        logging.info('Showing scale')
        self._unapply_calibration()
        self._update_generator(self._scale_generator)

    def get_max_deflection(self):
        return self._configuration.calibration.max_deflection

    def set_max_deflection(self, deflection):
        self._configuration.calibration.max_deflection = deflection
        self._unapply_calibration()
        self._save()

    '''Allows user so force the laser on'''
    def set_laser_off_override(self, state):
        self._controller.laser_off_override = state

    '''Gets the currently configured offset for laser on and off'''
    def get_laser_offset(self):
        return self._configuration.options.laser_offset

    '''Sets the currently configured offset for laser on and off'''
    def set_laser_offset(self, laser_offset):
        self._configuration.options.laser_offset = laser_offset
        self._disseminator.set_offset(laser_offset)
        self._save()

    '''Changes the speed at which the test pattern is drawn in mm/sec'''
    def set_test_pattern_speed(self, speed):
        [pattern.set_speed(speed) for pattern in self._test_patterns.values()]

    '''returns a list of test patterns'''
    def get_test_patterns(self):
        return self._test_patterns.keys()

    '''Returns the current calibration for the printer'''
    def current_calibration(self):
        return self._configuration.calibration

    '''Saves the suppliled calibration'''
    def save_points(self, height, lower_points, upper_points):
        self._configuration.calibration.height = height
        self._configuration.calibration.lower_points = lower_points
        self._configuration.calibration.upper_points = upper_points
        self._save()

    def _save(self):
        self._configuration_manager.save(self._configuration)
        self.make_pattern_fit()

    # deprecated
    def make_pattern_fit(self):
        for pattern in self._test_patterns.values():
            pattern.set_radius(self.get_largest_object_radius())

    '''Must be called before shutting down applications'''
    def close(self):
        self._controller.close()

    def _update_generator(self, generator):
        self._current_generator = generator
        self._controller.change_generator(self._current_generator)

    def _apply_calibration(self):
        self._path_to_audio.set_transformer(
            HomogenousTransformer(
                self._configuration.calibration.max_deflection,
                self._configuration.calibration.height,
                self._configuration.calibration.lower_points,
                self._configuration.calibration.upper_points
                )
            )

    def _unapply_calibration(self):
        self._path_to_audio.set_transformer(
            TuningTransformer(scale=self._configuration.calibration.max_deflection))

    def _validate_points(self, points):
        if (len(points) != 4):
            return False
        return True

    '''Based on current calibrations_gets_maximum_size_of_object at the base layer'''
    def get_largest_object_radius(self):
        lowest = None
        for (x, y) in self._configuration.calibration.lower_points.values():
            if not lowest or abs(x) < lowest:
                lowest = abs(x)
            if abs(y) < lowest:
                lowest = abs(y)
        logging.info("Calulated max radius of object as: %s mm" % lowest)
        return lowest

    def stop(self):
            self._controller.stop()