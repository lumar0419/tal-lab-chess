"""Opt-in Tal Lab configurations for paired tactical research."""

CHECKS = {'qsearch_quiet_checks': True}
CONTINUATION = CHECKS | {'check_continuation': True}
PROFILES = {
    'baseline': {},
    'candidate': {},
    'quiet': CHECKS,
    'continuation': CONTINUATION,
    'bridge': CONTINUATION | {'qsearch_capture_bridge': True},
    'forcing': CONTINUATION | {'qsearch_forcing_replies': 2},
    'forcing_bridge': CONTINUATION | {'qsearch_forcing_replies': 2, 'qsearch_capture_bridge': True},
    'unextended': {'check_extension_limit': 0},
    'bounded': {'check_extension_limit': 2},
    'null': {'null_move_pruning': True},
    'threat': {'null_threat_extension': True},
    'combined': {'check_extension_limit': 2, 'null_move_pruning': True, 'null_threat_extension': True},
    # v0.8.8: 선택적 탐색 묶음 (가지치기·축소 + 정적 탐색 조용한 체크 + 희생 뒤 수순 보호)
    'selective': {'selective': True},
    # v0.9.3: 선택적 탐색 + 전술 연장 (Searcher.set_tactical과 같은 값)
    'tactical': dict(__import__('search').TACTICAL_PROFILE),
    'selective_plain': {'selective': True, 'sel_sac_ply': 0, 'sel_qchecks': False},
}
