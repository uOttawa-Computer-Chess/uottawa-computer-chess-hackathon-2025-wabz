"""
Some example classes for people who want to create a homemade bot.

With these classes, bot makers will not have to implement the UCI or XBoard interfaces themselves.
"""
import chess
from chess.engine import PlayResult, Limit
import random
from lib.engine_wrapper import MinimalEngine
from lib.lichess_types import MOVE, HOMEMADE_ARGS_TYPE
import logging


# Use this logger variable to print messages to the console or log files.
# logger.info("message") will always print "message" to the console or log file.
# logger.debug("message") will only print "message" if verbose logging is enabled.
logger = logging.getLogger(__name__)


class ExampleEngine(MinimalEngine):
    """An example engine that all homemade engines inherit."""


# Bot names and ideas from tom7's excellent eloWorld video

class RandomMove(ExampleEngine):
    """Get a random move."""

    def search(self, board: chess.Board, *args: HOMEMADE_ARGS_TYPE) -> PlayResult:  # noqa: ARG002
        """Choose a random move."""
        return PlayResult(random.choice(list(board.legal_moves)), None)


class Alphabetical(ExampleEngine):
    """Get the first move when sorted by san representation."""

    def search(self, board: chess.Board, *args: HOMEMADE_ARGS_TYPE) -> PlayResult:  # noqa: ARG002
        """Choose the first move alphabetically."""
        moves = list(board.legal_moves)
        moves.sort(key=board.san)
        return PlayResult(moves[0], None)


class FirstMove(ExampleEngine):
    """Get the first move when sorted by uci representation."""

    def search(self, board: chess.Board, *args: HOMEMADE_ARGS_TYPE) -> PlayResult:  # noqa: ARG002
        """Choose the first move alphabetically in uci representation."""
        moves = list(board.legal_moves)
        moves.sort(key=str)
        return PlayResult(moves[0], None)


class ComboEngine(ExampleEngine):
    """
    Get a move using multiple different methods.

    This engine demonstrates how one can use `time_limit`, `draw_offered`, and `root_moves`.
    """

    def search(self,
               board: chess.Board,
               time_limit: Limit,
               ponder: bool,  # noqa: ARG002
               draw_offered: bool,
               root_moves: MOVE) -> PlayResult:
        """
        Choose a move using multiple different methods.

        :param board: The current position.
        :param time_limit: Conditions for how long the engine can search (e.g. we have 10 seconds and search up to depth 10).
        :param ponder: Whether the engine can ponder after playing a move.
        :param draw_offered: Whether the bot was offered a draw.
        :param root_moves: If it is a list, the engine should only play a move that is in `root_moves`.
        :return: The move to play.
        """
        if isinstance(time_limit.time, int):
            my_time = time_limit.time
            my_inc = 0
        elif board.turn == chess.WHITE:
            my_time = time_limit.white_clock if isinstance(time_limit.white_clock, int) else 0
            my_inc = time_limit.white_inc if isinstance(time_limit.white_inc, int) else 0
        else:
            my_time = time_limit.black_clock if isinstance(time_limit.black_clock, int) else 0
            my_inc = time_limit.black_inc if isinstance(time_limit.black_inc, int) else 0

        possible_moves = root_moves if isinstance(root_moves, list) else list(board.legal_moves)

        if my_time / 60 + my_inc > 10:
            # Choose a random move.
            move = random.choice(possible_moves)
        else:
            # Choose the first move alphabetically in uci representation.
            possible_moves.sort(key=str)
            move = possible_moves[0]
        return PlayResult(move, None, draw_offered=draw_offered)

    
class MyBot(ExampleEngine):
    """Template code for hackathon participants to modify.

    This is intentionally a very small, simple, and weak example engine
    meant for learning and quick prototyping only.

    Key limitations:
    - Fixed-depth search with only a very naive time-to-depth mapping (no true time management).
    - Plain minimax: no alpha-beta pruning, so the search is much slower than it
      could be for the same depth.
    - No iterative deepening: the engine does not progressively deepen and use PV-based ordering.
    - No move ordering or capture heuristics: moves are searched in arbitrary order.
    - No transposition table or caching: repeated positions are re-searched.
    - Evaluation is material-only and very simplistic; positional factors are ignored.

    Use this as a starting point: replace minimax with alpha-beta, add
    iterative deepening, quiescence search, move ordering (MVV/LVA, history),
    transposition table, and a richer evaluator to make it competitive.
    """

    def search(self, board: chess.Board, *args: HOMEMADE_ARGS_TYPE) -> PlayResult:
        # NOTE: The sections below are intentionally simple to keep the example short.
        # They demonstrate the structure of a search but also highlight the engine's
        # weaknesses (fixed depth, naive time handling, no pruning, no quiescence, etc.).

        # --- very simple time-based depth selection (naive) ---
        # Expect args to be (time_limit: Limit, ponder: bool, draw_offered: bool, root_moves: MOVE)
        time_limit = args[0] if (args and isinstance(args[0], Limit)) else None
        my_time = my_inc = None
        if time_limit is not None:
            if isinstance(time_limit.time, (int, float)):
                my_time = time_limit.time
                my_inc = 0
            elif board.turn == chess.WHITE:
                my_time = time_limit.white_clock if isinstance(time_limit.white_clock, (int, float)) else 0
                my_inc = time_limit.white_inc if isinstance(time_limit.white_inc, (int, float)) else 0
            else:
                my_time = time_limit.black_clock if isinstance(time_limit.black_clock, (int, float)) else 0
                my_inc = time_limit.black_inc if isinstance(time_limit.black_inc, (int, float)) else 0

        # Map a rough time budget to a coarse fixed depth.
        # Examples:
        # - >= 60s: depth 4
        # - >= 20s: depth 3
        # - >= 5s:  depth 2
        # - else:   depth 1
        remaining = my_time if isinstance(my_time, (int, float)) else None
        inc = my_inc if isinstance(my_inc, (int, float)) else 0
        budget = (remaining or 0) + 2 * inc  # crude increment bonus
        if remaining is None:
            total_depth = 5
        elif budget >= 60:
            total_depth = 5
        elif budget >= 20:
            total_depth = 4
        elif budget >= 5:
            total_depth = 3
        else:
            total_depth = 2
        total_depth = max(1, int(total_depth))

        values = {
                chess.PAWN: 100,
                chess.KNIGHT: 320,
                chess.BISHOP: 330,
                chess.ROOK: 500,
                chess.QUEEN: 900,
                chess.KING: 0,  # king material ignored (checkmates handled above)
            }

        # --- simple material evaluator (White-positive score) ---
        def evaluate(b: chess.Board) -> int:
            # Large score for terminal outcomes
            if b.is_game_over():
                outcome = b.outcome()
                if outcome is None or outcome.winner is None:
                    return 0  # draw
                return 10_000_000 if outcome.winner is chess.WHITE else -10_000_000

            values = {
                chess.PAWN: 100,
                chess.KNIGHT: 320,
                chess.BISHOP: 330,
                chess.ROOK: 500,
                chess.QUEEN: 900,
                chess.KING: 0,  # king material ignored (checkmates handled above)
            }
            score = 0
            for pt, v in values.items():
                score += v * (len(b.pieces(pt, chess.WHITE)) - len(b.pieces(pt, chess.BLACK)))
            return score
        
        def evaluate_anti_draw(b: chess.Board) -> int:
            base_eval = evaluate(b)

            if b.is_repetition(2):
                our_perspective_eval = base_eval if b.turn == chess.WHITE else -base_eval
                
                # Count total material to determine game phase
                total_material = sum(len(b.pieces(pt, c)) * values[pt] 
                                for pt in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]
                                for c in [chess.WHITE, chess.BLACK])
                
                # Adaptive threshold based on game phase
                if total_material > 6000:  # Opening/middlegame (lots of pieces)
                    threshold = 150  # Need bigger advantage (1.5 pawns) to avoid repetition
                elif total_material > 3000:  # Middlegame transitioning to endgame
                    threshold = 75   # Medium advantage needed (0.75 pawns)
                else:  # Endgame (few pieces left)
                    threshold = 25   # Even small advantage matters (0.25 pawns)
                
                if our_perspective_eval > threshold:
                    # Scale penalty with advantage
                    penalty = min(abs(our_perspective_eval) * 0.8, 500)
                    base_eval = base_eval - penalty if b.turn == chess.WHITE else base_eval + penalty
            
            return base_eval

        # --- MVV-LVA move ordering ---
        def order_moves(b: chess.Board, moves: list[chess.Move]) -> list[chess.Move]:
            """Order moves using MVV-LVA (Most Valuable Victim - Least Valuable Attacker).
            
            This heuristic scores captures by:
            1. Value of the captured piece (higher is better)
            2. Value of the attacking piece (lower is better)
            
            Uses the same piece values as the evaluation function for consistency.
            Non-captures get lower scores. Moves are sorted in descending order by score.
            
            :param b: The current board position
            :param moves: List of legal moves to order
            :return: Sorted list of moves (best moves first)
            """
            def move_score(move: chess.Move) -> int:
                score = 0
                
                # Check if this is a capture
                if b.is_capture(move):
                    # Get the piece being captured (victim)
                    victim_square = move.to_square
                    victim_piece = b.piece_at(victim_square)
                    
                    # Get the piece doing the capturing (attacker)
                    attacker_piece = b.piece_at(move.from_square)
                    
                    if victim_piece and attacker_piece:
                        victim_value = values.get(victim_piece.piece_type, 0)
                        attacker_value = values.get(attacker_piece.piece_type, 0)
                        
                        # MVV-LVA: High victim value + low attacker value = good
                        # Use same values as evaluation (100-900 range)
                        # Multiply victim by 10 to prioritize it over attacker penalty
                        score = victim_value * 10 - attacker_value
                
                # Promotions are also valuable (roughly gaining 800 material: Q-P)
                if move.promotion:
                    promotion_value = values.get(move.promotion, 0)
                    # Score based on actual promotion gain (promoted piece - pawn)
                    score += (promotion_value - values[chess.PAWN]) * 10
                
                return score
            
            # Sort moves by score in descending order (highest score first)
            return sorted(moves, key=move_score, reverse=True)

        # --- plain minimax (no alpha-beta) ---
        def minimax(b: chess.Board, depth: int, maximizing: bool) -> int:
            if depth == 0 or b.is_game_over():
                return evaluate_anti_draw(b)

            if maximizing:
                best = -10**12
                for m in b.legal_moves:
                    b.push(m)
                    val = minimax(b, depth - 1, False)
                    b.pop()
                    if val > best:
                        best = val
                return best
            else:
                best = 10**12
                for m in b.legal_moves:
                    b.push(m)
                    val = minimax(b, depth - 1, True)
                    b.pop()
                    if val < best:
                        best = val
                return best

        # --- alpha-beta pruning (recursive, efficient) ---
        def alphabeta(b: chess.Board, depth: int, alpha: float, beta: float, maximizing: bool) -> int:
            """Alpha-beta pruning: minimax with cutoffs.

            Alpha is the best value the maximizer can guarantee (lower bound).
            Beta is the best value the minimizer can guarantee (upper bound).
            When alpha >= beta, we can prune (stop searching) this branch.
            """
            if depth == 0 or b.is_game_over():
                return evaluate_anti_draw(b)

            # Order moves for better pruning
            ordered_moves = order_moves(b, list(b.legal_moves))

            if maximizing:
                max_eval = -10**12
                for m in ordered_moves:
                    b.push(m)
                    val = alphabeta(b, depth - 1, alpha, beta, False)
                    b.pop()
                    if val > max_eval:
                        max_eval = val
                    if max_eval > alpha:
                        alpha = max_eval
                    if alpha >= beta:
                        break  # Beta cutoff: opponent won't allow this line
                return max_eval
            else:
                min_eval = 10**12
                for m in ordered_moves:
                    b.push(m)
                    val = alphabeta(b, depth - 1, alpha, beta, True)
                    b.pop()
                    if val < min_eval:
                        min_eval = val
                    if min_eval < beta:
                        beta = min_eval
                    if alpha >= beta:
                        break  # Alpha cutoff: we won't allow this line
                return min_eval

        # --- root move selection with alpha-beta ---
        legal = list(board.legal_moves)
        if not legal:
            # Should not happen during normal play; fall back defensively
            return PlayResult(random.choice(list(board.legal_moves)), None)

        # Order moves at root for better search efficiency
        ordered_legal = order_moves(board, legal)

        maximizing = board.turn == chess.WHITE
        best_move = None
        best_eval = -10**12 if maximizing else 10**12
        
        # Initialize alpha-beta bounds at root
        alpha = -10**12
        beta = 10**12

        # Lookahead depth chosen by the simple time heuristic; subtract one for the root move
        for m in ordered_legal:
            board.push(m)
            val = alphabeta(board, total_depth - 1, alpha, beta, not maximizing)
            board.pop()

            if maximizing:
                if val > best_eval:
                    best_eval, best_move = val, m
                if val > alpha:
                    alpha = val
            else:
                if val < best_eval:
                    best_eval, best_move = val, m
                if val < beta:
                    beta = val

        # Fallback in rare cases (shouldn't trigger)
        if best_move is None:
            best_move = legal[0]

        return PlayResult(best_move, None)