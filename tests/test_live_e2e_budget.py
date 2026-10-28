import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from scripts import live_e2e_server


class LiveBudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = patch.object(live_e2e_server, 'PRIVATE', Path(self.directory.name))
        self.path.start()
        self.addCleanup(self.path.stop)
        self.budget = live_e2e_server.Budget(Decimal('4.50'))

    def test_inflight_requests_share_one_soft_limit(self):
        self.budget.reserve(Decimal('3'), 'llm')
        self.budget.reserve(Decimal('1'), '2gis')
        with self.assertRaises(ValueError):
            self.budget.reserve(Decimal('0.51'), 'tavily')
        self.assertEqual(sum(self.budget.pending.values()), Decimal('4'))
        self.assertEqual(len(self.budget.rows), 2)

    def test_usage_releases_only_unused_reservation(self):
        ident = self.budget.reserve(Decimal('1'), 'llm')
        self.budget.settle(ident, Decimal('0.01'), prompt_tokens=12, completion_tokens=4)
        self.budget.reserve(Decimal('4.49'), 'llm')
        self.assertEqual(self.budget.spent + sum(self.budget.pending.values()), Decimal('4.50'))
        with self.assertRaises(ValueError):
            self.budget.reserve(Decimal('0.000001'), 'llm')

    def test_missing_billing_and_timeout_charge_entire_reserve(self):
        ident = self.budget.reserve(Decimal('4.50'), 'llm')
        self.budget.settle(ident, None)
        self.assertEqual(self.budget.spent, Decimal('4.50'))
        with self.assertRaises(ValueError):
            self.budget.reserve(Decimal('0.01'), 'tavily')

    def test_cannot_configure_above_soft_limit(self):
        for limit in ('0', '-1', '4.51', '5'):
            with self.assertRaises(ValueError):
                live_e2e_server.Budget(Decimal(limit))

    def test_safe_parameters_exclude_credentials_and_personal_data(self):
        self.assertEqual(live_e2e_server.safe_params({'query': 'Сочи', 'adults': 2,
            'apiKey': 'secret', 'Authorization': 'secret', 'email': 'person@example.invalid',
            'passengers_data': [{'name': 'Person'}]}), {'query': 'Сочи', 'adults': 2})
