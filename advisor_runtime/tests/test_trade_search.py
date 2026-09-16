'''Regression tests for bounded trade discovery.'''

import unittest
from unittest import mock

from advisor_runtime import trade_search
from advisor_runtime.tests.test_advisor_v2 import fixture_snapshot


class TradeDiscoveryTests(unittest.TestCase):
    def snapshot(self, opponent_ids=('breece', 'tee')):
        snapshot = fixture_snapshot()
        mine = next(row for row in snapshot['rosters'] if row['roster_id'] == 9)
        other = next(row for row in snapshot['rosters'] if row['roster_id'] == 4)
        mine['player_ids'] = ['jayden']
        other['player_ids'] = list(opponent_ids)
        snapshot['rosters'] = [mine, other]
        return snapshot

    def discover(self, snapshot, mode='ours', roster_average=(9.0, [])):
        original_combinations = trade_search.combinations
        get_ids = {
            snapshot['players'][player_id]['name']: player_id
            for player_id in snapshot['rosters'][1]['player_ids']
        }

        def resolve(_snapshot, give_names, get_names):
            return {
                'terms_explicit': True,
                'give': give_names,
                'get': get_names,
                'give_ids': ['jayden'],
                'get_ids': [get_ids[get_names[0]]],
                'other_rid': 4,
            }

        def evaluate(_snapshot, terms, source_checks=True):
            theirs = -1.0 if terms['get'] == ['Breece Hall'] else 1.0
            return {
                'give': terms['give'],
                'get': terms['get'],
                'perspective_delta_pg': 1.0,
                'counterparty_delta_pg': theirs,
                'perspective_after_pg': 10.0,
                'counterparty_after_pg': 10.0,
                'perspective_forced_drops': [],
                'counterparty_forced_drops': [],
                'slots_compared': [],
                'weeks': [1],
            }

        def singles(items, count):
            return original_combinations(items, count) if count == 1 else iter(())

        with (
            mock.patch.object(trade_search, 'combinations', side_effect=singles),
            mock.patch.object(trade_search.a, 'resolve_explicit_trade', side_effect=resolve),
            mock.patch.object(trade_search.a, 'trade_horizon', return_value={}),
            mock.patch.object(trade_search.a, 'evaluate_trade', side_effect=evaluate),
            mock.patch.object(trade_search.a, '_roster_average', return_value=roster_average),
        ):
            return trade_search.discover(snapshot, limit=2, max_candidates=2, mode=mode)

    def test_ours_ties_ignore_counterparty_delta(self):
        result = self.discover(self.snapshot(), mode='ours')

        self.assertEqual(
            [row['get'][0] for row in result['shortlist']],
            ['Breece Hall', 'Tee Higgins'],
        )
        self.assertIn('insufficient_reeve_gain_below_0.5ppg', result['excluded'])
        self.assertNotIn('insufficient_gain_or_counterparty_loss', result['excluded'])
        self.assertEqual(len(result['warnings']), 4)
        self.assertIn('never excludes or demotes', result['warnings'][2])

    def test_mutual_still_excludes_counterparty_loss(self):
        result = self.discover(self.snapshot(), mode='mutual')

        self.assertEqual([row['get'][0] for row in result['shortlist']], ['Tee Higgins'])
        self.assertEqual(result['excluded']['insufficient_gain_or_counterparty_loss'], 1)
        self.assertNotIn('insufficient_reeve_gain_below_0.5ppg', result['excluded'])
        self.assertEqual(len(result['warnings']), 4)
        self.assertIn('excluded before ranking', result['warnings'][2])

    def test_unknown_asset_contribution_is_not_accepted(self):
        snapshot = self.snapshot(('tee',))
        result = self.discover(snapshot, roster_average=(None, []))

        self.assertEqual(result['shortlist'], [])
        self.assertEqual(result['excluded']['forced_drop_or_noncontributing_padding'], 1)


if __name__ == '__main__':
    unittest.main()
