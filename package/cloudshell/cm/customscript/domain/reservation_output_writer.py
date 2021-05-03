import re


class ReservationOutputWriter(object):
    def __init__(self, session, command_context):
        """
        :type session: CloudShellAPISession
        :type command_context: ResourceCommandContext
        """
        self.session = session
        self.resevation_id = command_context.reservation.reservation_id

    def write(self, msg):
        if msg:
            msg = self._remove_illegal_chars(msg)
            self.session.WriteMessageToReservationOutput(self.resevation_id, msg)

    def write_warning(self, msg):
        self.session.WriteMessageToReservationOutput(self.resevation_id, '<font color="#f48342">WARNING: %s</font>'%msg)

    def _remove_illegal_chars(self, str):
        rx = re.compile('\x00')
        str = str if not getattr(str, "decode", False) else str.decode()  # can be a bytes-like object
        return rx.sub('', str)