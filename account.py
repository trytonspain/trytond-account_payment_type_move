#This file is part of account_payment_type_move module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
from itertools import izip
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

__all__ = ['PaymentType', 'Move', 'Invoice']
__metaclass__ = PoolMeta


class PaymentType:
    __name__ = 'account.payment.type'
    account = fields.Many2One('account.account', 'Account', help='If set, once '
        'a move with this payment type will be confirmed, a new move will be '
        'created that will move the balance from the payable/receivable to the '
        'account supplied here.')


class Move:
    __name__ = 'account.move'

    def auto_move_line_defaults(self):
        return {
            'move': self.id,
            'tax_lines': [],
            'payment_type': None,
            }

    def auto_move_counterpart_defaults(self):
        return {
            'move': self.id,
            'tax_lines': [],
            }

    @classmethod
    def create_payment_auto_move(cls, moves):
        Line = Pool().get('account.move.line')
        for move in moves:
            to_reconcile = []
            for line in move.lines:
                if (not line.payment_type
                        or line.account.kind not in ('receivable', 'payable')
                        ):
                    continue
                account = line.payment_type.account
                if not account or account == line.account:
                    continue
                to_reconcile.append(line)
            if not to_reconcile:
                continue
            new_move = cls()
            new_move.date = move.date
            new_move.period = move.period
            new_move.journal = move.journal
            new_move.origin = move.origin
            new_move.description = move.description
            new_move.save()
            new_lines = Line.copy(to_reconcile,
                new_move.auto_move_line_defaults())
            counterparts = Line.copy(to_reconcile,
                new_move.auto_move_counterpart_defaults())
            to_reconcile2 = []
            for line, new_line, counterpart in izip(to_reconcile, new_lines,
                    counterparts):
                new_line.debit = line.credit
                new_line.credit = line.debit
                new_line.save()
                counterpart.account = line.payment_type.account
                counterpart.save()
                to_reconcile2.append((line, new_line))

            cls.post([new_move])
            for l1, l2 in to_reconcile2:
                Line.reconcile([l1, l2])

    @classmethod
    @ModelView.button
    def post(cls, moves):
        super(Move, cls).post(moves)
        # Avoid infinite recursion by setting and checking for a
        # 'payment_type_move' in context
        if Transaction().context.get('payment_type_move', True):
            with Transaction().set_context(payment_type_move=False):
                cls.create_payment_auto_move(moves)


class Invoice:
    __name__ = 'account.invoice'

    def get_lines_to_pay(self, name):
        Line = Pool().get('account.move.line')
        if self.type in ('out_invoice', 'out_credit_note'):
            kind = 'receivable'
        else:
            kind = 'payable'
        lines = Line.search([
                ('origin', '=', ('account.invoice', self.id)),
                ('account.kind', '=', kind),
                ('maturity_date', '=', None),
                ])
        return [x.id for x in lines]
