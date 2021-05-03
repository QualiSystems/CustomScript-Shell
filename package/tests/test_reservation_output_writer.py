from unittest import TestCase

from mock import Mock

from cloudshell.cm.customscript.domain.reservation_output_writer import ReservationOutputWriter


class TestReservationOutputWriter(TestCase):

    def test_write(self):
        session = Mock()
        context = Mock()
        context.reservation.reservation_id = '1234'
        writer = ReservationOutputWriter(session, context)
        writer.write('some msg')
        session.WriteMessageToReservationOutput.assert_called_once_with('1234','some msg')

    def test_write_with_bytes(self):
        session = Mock()
        context = Mock()
        context.reservation.reservation_id = '1234'
        writer = ReservationOutputWriter(session, context)
        writer.write(b'some msg')
        session.WriteMessageToReservationOutput.assert_called_once_with('1234','some msg')
