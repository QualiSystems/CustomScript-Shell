import re


class ReservationOutputWriter(object):
    def __init__(self, session, command_context):
        """
        :type session: CloudShellAPISession
        :type command_context: ResourceCommandContext
        """
        self.session = session
        reservation = command_context.reservation if hasattr(command_context, 'reservation') \
            else command_context.remote_reservation
        self.reservation_id = reservation.reservation_id

    def write(self, msg):
        if msg:
            msg = self._remove_illegal_chars(msg)
            self.session.WriteMessageToReservationOutput(self.reservation_id, msg)

    def write_warning(self, msg):
        self.session.WriteMessageToReservationOutput(self.reservation_id, '<font color="#f48342">WARNING: %s</font>' % msg)

    def _remove_illegal_chars(self, str):
        rx = re.compile(u'\x00')
        return rx.sub('', str)