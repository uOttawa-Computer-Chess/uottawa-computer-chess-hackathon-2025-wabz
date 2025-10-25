"""Quick test to verify alpha-beta implementation works correctly."""
import chess
from homemade import MyBot

def test_alphabeta():
    """Test that MyBot with alpha-beta can find simple tactics."""
    bot = MyBot()
    
    # Test 1: Starting position - should return a legal move
    board = chess.Board()
    result = bot.search(board)
    assert result.move in board.legal_moves, "Should return a legal move"
    print(f"✓ Test 1 passed: Starting position, chose {result.move}")
    
    # Test 2: Mate in 1 - should find the checkmate
    # Position: White to move, can mate with Qh7#
    board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 0 1")
    result = bot.search(board)
    # Qxf7 is mate
    expected_mate = chess.Move.from_uci("h5f7")
    assert result.move == expected_mate, f"Should find mate in 1, got {result.move}"
    print(f"✓ Test 2 passed: Found mate in 1 with {result.move}")
    
    # Test 3: Free piece - should capture the hanging queen
    # Black queen on d4 is hanging, white can capture
    board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/3qP3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 1")
    result = bot.search(board)
    # Should capture the queen on d4
    assert result.move.to_square == chess.D4, f"Should capture hanging queen, got {result.move}"
    print(f"✓ Test 3 passed: Captured hanging piece with {result.move}")
    
    print("\n✅ All tests passed! Alpha-beta is working correctly.")

if __name__ == "__main__":
    test_alphabeta()
