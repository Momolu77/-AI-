"""
State Recognition Test Script

Test feature extraction, PME computation, and intervention logic using mock data
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.state_recognizer import extract_features, compute_metacog_state
from app.services.intervention import InterventionStateMachine


def load_mock_session(filename: str) -> dict:
    """Load mock session data"""
    filepath = Path(__file__).parent / "mock_data" / filename
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def print_section(title: str):
    """Print section divider"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def test_feature_extraction(session_data: dict):
    """Test feature extraction"""
    print_section("Feature Extraction Test")

    events = session_data['events']
    print(f"Total events: {len(events)}")
    print(f"Event type distribution:")

    type_counts = {}
    for e in events:
        t = e['event_type']
        type_counts[t] = type_counts.get(t, 0) + 1

    for t, count in sorted(type_counts.items()):
        print(f"  {t:15} : {count}")

    features = extract_features(events)

    print("\nExtracted features:")
    for key, value in sorted(features.items()):
        if key.endswith('_status'):
            continue
        status_key = key.rsplit('_', 1)[0] + '_status'
        if '_' not in key.rsplit('_', 1)[0]:
            status_key = key + '_status'
        status = features.get(status_key, 'N/A')
        if value is None:
            print(f"  {key:25} : None (status: {status})")
        elif isinstance(value, float):
            print(f"  {key:25} : {value:.3f} (status: {status})")
        else:
            print(f"  {key:25} : {value} (status: {status})")

    return features


def test_intervention(state: dict, session_id: str):
    """Test intervention triggering"""
    print_section("Intervention Trigger Test")

    sm = InterventionStateMachine(session_id)

    for i in range(5):
        intervention = sm.on_event(state)

        if intervention:
            print(f"\nUpdate {i+1}: [TRIGGERED]")
            print(f"  Type: {intervention['type']}")
            print(f"  Reason: {intervention['trigger_reason']}")
            print(f"  Content preview: {intervention['content'][:60]}...")
        else:
            print(f"Update {i+1}: [NO INTERVENTION]")

    print(f"\nIntervention history: {len(sm.intervention_history)} times")


def run_full_test(scenario_name: str, filename: str):
    """Full test workflow"""
    print("\n" + "="*60)
    print(f"  TEST SCENARIO: {scenario_name.upper()}")
    print("="*60)

    session_data = load_mock_session(filename)
    print(f"\nSession ID: {session_data['session_id']}")
    print(f"Task: {session_data['task_description']}")

    features = test_feature_extraction(session_data)
    state = compute_metacog_state(features)

    print_section("PME State Computation Result")

    for dim in ['planning', 'monitoring', 'evaluation']:
        score = state[dim]
        conf = state['confidence'][dim]
        status = state['status'][dim]

        if score is not None:
            bar_len = int(score * 20)
            bar = '#' * bar_len + '-' * (20 - bar_len)
            print(f"  {dim.capitalize():12} : {bar} {score:.3f} (conf: {conf:.2f}, {status})")
        else:
            print(f"  {dim.capitalize():12} : {'-' * 20} None (conf: {conf:.2f}, {status})")

    print(f"\n  Coverage     : {state['feature_coverage']:.2%}")

    test_intervention(state, session_data['session_id'])

    return state


def main():
    """Main test function"""
    print("\n" + "="*60)
    print("  Metacognitive State Recognition - Mock Data Test")
    print("="*60)

    scenarios = [
        ("High Metacog", "high_metacog_session.json"),
        ("Low Metacog", "low_metacog_session.json"),
        ("Mixed Metacog", "mixed_metacog_session.json"),
        ("Planning Weak", "planning_weak_session.json")
    ]

    results = {}

    for name, filename in scenarios:
        try:
            state = run_full_test(name, filename)
            results[name] = state
        except Exception as e:
            print(f"\n[ERROR] Test failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*60)
    print("  TEST RESULTS SUMMARY")
    print("="*60 + "\n")

    print(f"{'Scenario':<20} {'Planning':>12} {'Monitoring':>12} {'Evaluation':>12} {'Coverage':>10}")
    print("-" * 70)

    for name, state in results.items():
        p = f"{state['planning']:.3f}" if state['planning'] else "N/A"
        m = f"{state['monitoring']:.3f}" if state['monitoring'] else "N/A"
        e = f"{state['evaluation']:.3f}" if state['evaluation'] else "N/A"
        cov = f"{state['feature_coverage']:.1%}"

        print(f"{name:<20} {p:>12} {m:>12} {e:>12} {cov:>10}")

    print("\nExpected validation:")
    print("  [OK] High Metacog: P/M/E all > 0.7")
    print("  [OK] Low Metacog: P/M/E all < 0.4")
    print("  [OK] Mixed Metacog: P/E ~0.5-0.6, M ~0.4")
    print("  [OK] Planning Weak: P < 0.4 with Planning intervention, M/E > 0.6")


if __name__ == "__main__":
    main()
