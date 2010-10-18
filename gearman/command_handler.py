import logging
from gearman.errors import UnknownCommandError
from gearman.protocol import get_command_name

gearman_logger = logging.getLogger(__name__)

class GearmanCommandHandler(object):
    """A command handler manages the state which we should be in given a certain stream of commands

    GearmanCommandHandler does no I/O and only understands sending/receiving commands
    """
    def __init__(self):
        self._connection = None
        self._connection_manager = None

        self._data_encoder = None

        # Takes cmd_type and **cmd_args
        self._gearman_command_callback_map = {}

    #### Interaction with GearmanConnectionManager
    def set_connection_manager(self, gearman_connection_manager):
        self._connection_manager = gearman_connection_manager
        self.set_data_encoder(self._connection_manager.data_encoder)

    def set_data_encoder(self, data_encoder):
        self._data_encoder = data_encoder

    def decode_data(self, data):
        """Convenience function :: handle binary string -> object unpacking"""
        return self._data_encoder.decode(data)

    def encode_data(self, data):
        """Convenience function :: handle object -> binary string packing"""
        return self._data_encoder.encode(data)

    #### Interaction with GearmanConnection ####
    def set_connection(self, gearman_connection):
        self._connection = gearman_connection

    def on_connect(self):
        pass

    def on_disconnect(self):
        pass

    def send_command(self, cmd_type, **cmd_args):
        """Hand off I/O to the connection mananger"""
        self._connection.send_command(cmd_type, cmd_args)

    def recv_command(self, cmd_type, cmd_args):
        """Maps any command to a recv_* callback function"""
        completed_work = None

        # Cache our callback code so we can get improved QPS
        cmd_callback = self._gearman_command_callback_map.get(cmd_type)
        if cmd_callback is None:
            cmd_callback = self._locate_command_callback(cmd_type, cmd_args)
            self._gearman_command_callback_map[cmd_type] = cmd_callback

        # Expand the arguments as passed by the protocol
        # This must match the parameter names as defined in the command handler
        completed_work = cmd_callback(**cmd_args)
        return completed_work

    def _locate_command_callback(self, cmd_type, cmd_args):
        gearman_command_name = get_command_name(cmd_type)
        if bool(gearman_command_name == cmd_type) or not gearman_command_name.startswith('GEARMAN_COMMAND_'):
            unknown_command_msg = 'Could not handle command: %r - %r' % (gearman_command_name, cmd_args)
            gearman_logger.error(unknown_command_msg)
            raise ValueError(unknown_command_msg)

        recv_command_function_name = gearman_command_name.lower().replace('gearman_command_', 'recv_')

        cmd_callback = getattr(self, recv_command_function_name, None)
        if not cmd_callback:
            missing_callback_msg = 'Could not handle command: %r - %r' % (get_command_name(cmd_type), cmd_args)
            gearman_logger.error(missing_callback_msg)
            raise UnknownCommandError(missing_callback_msg)

        return cmd_callback

    def recv_error(self, error_code, error_text):
        """When we receive an error from the server, notify the connection manager that we have a gearman error"""
        gearman_logger.error('Received error from server: %s: %s' % (error_code, error_text))
        self._connection_manager.on_gearman_error(self)
