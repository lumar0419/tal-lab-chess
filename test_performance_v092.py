import unittest
from unittest.mock import patch

from board import Board, Move
from deep_analysis import _defense_consistency, _defense_need, _verify_defense
from research.pruning_trace import PruningTrace
from search import EXACT, Searcher


class PerformanceAccuracyTests(unittest.TestCase):
    def test_cached_moves_preserve_value_and_are_immutable(self):
        first = Board().legal_moves()
        second = Board().legal_moves()
        self.assertEqual(first, second)
        self.assertTrue(all(a is b for a,b in zip(first,second)))
        self.assertIn(Move(35,55),first)  # e2e4
        with self.assertRaises(AttributeError):
            first[0].to=35

    def test_draw_context_change_invalidates_scores(self):
        b=Board()
        s=Searcher()
        s.search(b,max_depth=2,on_info=None)
        # The same piece placement/hash, different halfmove clock.
        s.tt.store(123456789,10,EXACT,999,None)
        b.halfmove=12
        s.search(b,max_depth=1,on_info=None)
        self.assertIsNone(s.tt.get(123456789))

    def test_same_diagram_different_game_history_invalidates_scores(self):
        b=Board()
        s=Searcher()
        for m in ('g1f3','g8f6','f3g1','f6g8'):
            b.push_uci(m)
        s.search(b,max_depth=1,on_info=None)
        s.tt.store(123456789,10,EXACT,999,None)
        other=Board(b.fen())
        self.assertEqual(b.hash,other.hash)
        s.search(other,max_depth=1,on_info=None)
        self.assertIsNone(s.tt.get(123456789))

    def test_ordering_option_change_invalidates_selective_scores(self):
        s=Searcher()
        s.selective=True
        s.search(Board(),max_depth=2,on_info=None)
        s.tt.store(123456789,10,EXACT,999,None)
        s.pvs=False
        s.search(Board(),max_depth=1,on_info=None)
        self.assertIsNone(s.tt.get(123456789))

    def test_structured_trace_records_parent_for_reduction(self):
        b=Board();s=Searcher();t=PruningTrace(s,limit=1)
        before=b.snapshot();fen=b.fen();m=b.parse_uci('e2e4');b.make_move(m)
        s._emit_trace(t,'lmr',b,0,5,m,10,11,20,reduction=1,after_move=True)
        self.assertEqual(t.events[0]['fen'],fen)
        self.assertEqual(t.events[0]['move'],'e2e4')
        self.assertEqual((t.events[0]['alpha'],t.events[0]['beta']),(10,11))
        b.unmake_move();self.assertEqual(b.snapshot(),before)
        s._emit_trace(t,'rfp',b,0,1,None,10,11,20)
        self.assertEqual(t.dropped,1)

    def test_legacy_trace_api_remains_compatible(self):
        events=[];s=Searcher();b=Board()
        s._emit_trace(lambda *args:events.append(args),'iir',b,2,4,None,0,1,25)
        self.assertEqual(len(events[0]),5)

    def test_trace_disabled_has_no_recording_calls(self):
        s=Searcher();s.selective=True
        with patch.object(s,'_emit_trace',side_effect=AssertionError('trace overhead')):
            s.search(Board(),max_depth=4,on_info=None)

    def test_defense_comparison_uses_common_depth_and_root_extension(self):
        candidate=[dict(depth=5,score=20,pv=['e2e4','e7e5'])]
        defense=[dict(depth=3,score=20,pv=['e7e5'])]
        self.assertEqual(_defense_consistency(candidate,defense)['status'],'insufficient_common_depth')
        defense[0]['depth']=4
        self.assertEqual(_defense_consistency(candidate,defense)['status'],'agrees')
        self.assertEqual(_defense_consistency(candidate,defense,True)['status'],'insufficient_common_depth')
        defense[0]['depth']=5
        self.assertEqual(_defense_consistency(candidate,defense,True)['status'],'agrees')
        defense[0]['score']=30
        self.assertEqual(_defense_consistency(candidate,defense,True)['status'],'disagrees')

    def test_uncertainty_budget_does_not_reward_sacrifice_labels(self):
        a=dict(iterations=[dict(depth=3,score=1,pv=['a','b']),dict(depth=4,score=300,pv=['a','c'])],comparison=None)
        b={**a,'offer':{'piece':'Q'}}
        self.assertEqual(_defense_need(a),_defense_need(b))

    def test_shallow_agreement_cannot_verify_deeper_unrestricted_root(self):
        row=dict(depth=5,score=20,pv=['e2e4','e7e5'])
        item=dict(move='e2e4',iterations=[row],defenses=[dict(depth=4,score=20,pv=['e7e5'])])
        _verify_defense(item,[{**row,'depth':7}])
        self.assertEqual(item['consistency']['status'],'agrees')
        self.assertFalse(item['deepest_defense_verified'])
        self.assertEqual(item['required_defense_depth'],6)
        _verify_defense(item,[row])
        self.assertTrue(item['deepest_defense_verified'])


if __name__=='__main__':
    unittest.main()
