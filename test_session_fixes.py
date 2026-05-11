#!/usr/bin/env python3
"""
Test script untuk validasi session persistence & context management fixes.

Usage:
    python test_session_fixes.py
"""

import json
import sys
from unittest.mock import Mock

# Test data
TEST_CASES = {
    "session_id_first_msg_only": {
        "description": "Verify session ID adalah hash dari first user message saja",
        "test": lambda: True,  # Placeholder
    },
    "history_merge_append": {
        "description": "Verify message history di-append, bukan replaced",
        "test": lambda: True,  # Placeholder  
    },
    "user_info_name_priority": {
        "description": "Verify nama user prioritize realname > firstname > name",
        "test": lambda: True,  # Placeholder
    },
}

def test_merge_logic():
    """Test fungsi _merge_conversation_history."""
    from app.main import _merge_conversation_history
    
    print("\n" + "="*60)
    print("TEST: Message History Merge Logic")
    print("="*60)
    
    # Test Case 1: Stored history + new user message
    stored = [
        {"role": "user", "content": "Pertanyaan 1"},
        {"role": "assistant", "content": "Jawaban 1"},
    ]
    incoming = [
        {"role": "user", "content": "Pertanyaan 2"},
    ]
    result = _merge_conversation_history(stored, incoming)
    
    expected_len = 3  # user1, assistant1, user2
    actual_len = len(result)
    
    if actual_len == expected_len:
        print(f"✓ PASS: Merge append | stored={len(stored)} + incoming={len(incoming)} → {len(result)}")
        return True
    else:
        print(f"✗ FAIL: Merge append | expected {expected_len}, got {actual_len}")
        print(f"  Stored: {stored}")
        print(f"  Incoming: {incoming}")
        print(f"  Result: {result}")
        return False

def test_session_id_resolution():
    """Test fungsi _resolve_session_id dengan first message only."""
    from app.main import _resolve_session_id
    from unittest.mock import Mock
    
    print("\n" + "="*60)
    print("TEST: Session ID Resolution (First Message Only)")
    print("="*60)
    
    request = Mock()
    request.headers = {}
    
    # Test Case 1: Same first message → same session ID
    messages1 = [
        {"role": "user", "content": "Nama saya siapa?"},
        {"role": "assistant", "content": "Jawaban 1"},
        {"role": "user", "content": "Aset saya apa?"},
    ]
    
    messages2 = [
        {"role": "user", "content": "Nama saya siapa?"},
        {"role": "user", "content": "Aset saya apa?"},
    ]
    
    sid1 = _resolve_session_id(request, messages1)
    sid2 = _resolve_session_id(request, messages2)
    
    if sid1 == sid2:
        print(f"✓ PASS: Session ID stable | sid1={sid1[:20]}... == sid2={sid2[:20]}...")
        return True
    else:
        print(f"✗ FAIL: Session ID not stable")
        print(f"  Messages 1 first msg: '{messages1[0]['content']}'")
        print(f"  Messages 2 first msg: '{messages2[0]['content']}'")
        print(f"  sid1: {sid1}")
        print(f"  sid2: {sid2}")
        return False

def test_user_info_name_priority():
    """Test fetch_user_info name priority logic."""
    from app.it_glpi_client import fetch_user_info
    import asyncio
    from unittest.mock import AsyncMock, patch
    
    print("\n" + "="*60)
    print("TEST: User Info Name Priority (realname > firstname > name)")
    print("="*60)
    
    async def run_test():
        # Mock GLPI API response
        glpi_response = {
            "id": 123,
            "name": "GLPI",  # Service account username
            "realname": "Ariel Admin",  # Actual real name
            "firstname": "Ariel",
            "_useremails": [{"email": "admin@company.com"}],
            "_groups_id": [{"name": "Admins"}],
        }
        
        with patch("app.it_glpi_client._get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = glpi_response
            
            user_info = await fetch_user_info(123)
            
            # Check if realname was prioritized
            if user_info and user_info["name"] == "Ariel Admin":
                print(f"✓ PASS: Name priority | got '{user_info['name']}' (not 'GLPI')")
                return True
            else:
                print(f"✗ FAIL: Name priority")
                print(f"  Expected 'Ariel Admin', got '{user_info['name'] if user_info else None}'")
                print(f"  Full response: {user_info}")
                return False
    
    try:
        return asyncio.run(run_test())
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("CHATBOT SESSION & CONTEXT FIXES - TEST SUITE")
    print("="*70)
    
    results = []
    
    # Test 1: Merge logic
    try:
        results.append(("Message History Merge", test_merge_logic()))
    except Exception as e:
        print(f"✗ ERROR in test_merge_logic: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Message History Merge", False))
    
    # Test 2: Session ID resolution
    try:
        results.append(("Session ID Resolution", test_session_id_resolution()))
    except Exception as e:
        print(f"✗ ERROR in test_session_id_resolution: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Session ID Resolution", False))
    
    # Test 3: User info name priority
    try:
        results.append(("User Info Name Priority", test_user_info_name_priority()))
    except Exception as e:
        print(f"✗ ERROR in test_user_info_name_priority: {e}")
        import traceback
        traceback.print_exc()
        results.append(("User Info Name Priority", False))
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
