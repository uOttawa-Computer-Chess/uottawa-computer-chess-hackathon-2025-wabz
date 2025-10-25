"""
Some example classes for people who want to create a homemade bot.

With these classes, bot makers will not have to implement the UCI or XBoard interfaces themselves.
"""
import chess

from chess.engine import PlayResult, Limit

import random
import time
from lib.engine_wrapper import MinimalEngine
from lib.lichess_types import MOVE, HOMEMADE_ARGS_TYPE
import logging


# Use this logger variable to print messages to the console or log files.
# logger.info("message") will always print "message" to the console or log file.
# logger.debug("message") will only print "message" if verbose logging is enabled.
logger = logging.getLogger(__name__)

class ExampleEngine(MinimalEngine):
    """An example engine that all homemade engines inherit."""


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
    """Defensive chess engine with smart time management.

    Key Features:
    - Iterative deepening (searches depth 1, 2, 3... until time runs out)
    - Alpha-beta pruning with move ordering
    - Quiescence search with depth limit (prevents infinite loops)
    - Defensive evaluation (detects threats, values king safety)
    - Endgame detection based on piece count
    - Timeout protection (max 15 seconds per move)
    - Smart time allocation using opponent's thinking time
    - Pondering: reuses analysis from opponent's thinking time
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Transposition table: THE KEY TO SPEED
        # When we search to depth 5, we evaluate thousands of positions.
        # If opponent makes a move we already analyzed, we can reuse that work!
        # 
        # Example: We search our move at depth 5, analyzing opponent responses.
        #   - We store position after "opponent plays Nf6" at depth 4
        #   - Opponent actually plays Nf6
        #   - We now search from depth 5 again, and when we reach "Nf6" subtree,
        #     we instantly retrieve the depth 4 evaluation instead of re-computing!
        #   - This can save THOUSANDS of node evaluations per move
        #
        # Key: simplified FEN (position only, no move counters)
        # Value: (depth_searched, evaluation, best_move_found)
        self.transposition_table = {}
        
        # Track time usage for adaptive time management
        self.last_move_time = None
        self.opponent_last_move_time = None
        self.last_search_start = None
        self.last_position_fen = None
        
        # Opponent strength estimation
        self.opponent_move_times = []  # Track opponent's thinking times
        self.position_evaluations = []  # Track how eval changes after opponent moves
        self.opponent_strength_estimate = 0.5  # 0=weak, 1=very strong (Stockfish level)
    
    def estimate_opponent_strength(self, our_eval_before: float, our_eval_after: float, opponent_time: float):
        """Estimate opponent strength based on move quality and speed.
        
        Strong opponents (like Stockfish):
        - Make moves that improve their position (eval swings against us)
        - Think consistently fast (optimized engine)
        
        Weak opponents:
        - Make moves that don't improve position much
        - Variable thinking times
        """
        # Eval change from opponent's perspective
        # If eval went from +2 (we're winning) to -1 (they're winning), that's a +3 swing for them
        eval_swing = -(our_eval_after - our_eval_before)
        
        # Strong move indicator: opponent improved their position
        # Normalize to 0-1 scale (500 centipawns = very strong move)
        move_quality = max(0, min(1, (eval_swing + 100) / 600))
        
        # Fast consistent play indicator (engines are fast and consistent)
        # If opponent consistently plays in <1 second, likely an engine
        if opponent_time < 1.0:
            speed_indicator = 1.0
        elif opponent_time < 3.0:
            speed_indicator = 0.7
        else:
            speed_indicator = 0.3
        
        # Combined strength estimate (weighted toward move quality)
        strength_signal = 0.7 * move_quality + 0.3 * speed_indicator
        
        # Update rolling average (smooth out noise)
        self.opponent_strength_estimate = 0.8 * self.opponent_strength_estimate + 0.2 * strength_signal
        
        logger.debug(f"Opponent strength estimate: {self.opponent_strength_estimate:.2f} (move_quality={move_quality:.2f}, speed={speed_indicator:.2f})")
    
    def calculate_time_for_move(self, remaining_time: float | None, position_complexity: int) -> tuple[float, float]:
        """Calculate time budget for this move based on game state and opponent strength.
        
        Returns: (time_for_move, hard_deadline)
        """
        # Base maximum time per move
        BASE_MAX_TIME = 15.0
        
        # If we have no time info, use base max
        if remaining_time is None:
            return BASE_MAX_TIME, BASE_MAX_TIME
        
        # --- Adaptive maximum based on opponent strength ---
        # Against strong opponents (Stockfish), we need MORE time to find good moves
        # The stronger they play, the more time we should invest
        if self.opponent_strength_estimate > 0.7:
            # Strong opponent detected (likely Stockfish level 3+)
            # Increase max time significantly
            adaptive_max = BASE_MAX_TIME * (1 + self.opponent_strength_estimate)  # Up to 30s
            logger.debug(f"Strong opponent detected ({self.opponent_strength_estimate:.2f}), increasing max time to {adaptive_max:.1f}s")
        elif self.opponent_strength_estimate > 0.5:
            # Moderate opponent
            adaptive_max = BASE_MAX_TIME * 1.3  # Up to ~20s
        else:
            # Weak opponent
            adaptive_max = BASE_MAX_TIME
        
        # --- Consider opponent's last move time ---
        # If opponent took >15s and we have plenty of time, we can take longer too
        if self.opponent_last_move_time and self.opponent_last_move_time > BASE_MAX_TIME:
            if remaining_time > 60:  # Only if we're not in time trouble
                opponent_time_bonus = min(self.opponent_last_move_time, 30.0)
                adaptive_max = max(adaptive_max, opponent_time_bonus)
                logger.debug(f"Opponent took {self.opponent_last_move_time:.1f}s, matching their time")
        
        # --- Base time allocation (conservative % of remaining time) ---
        if remaining_time > 120:
            # Plenty of time: use ~3% per move (expecting 30+ moves)
            base_time = remaining_time / 30
        elif remaining_time > 60:
            # Moderate time: use ~4% per move
            base_time = remaining_time / 25
        elif remaining_time > 20:
            # Low time: use ~5% per move
            base_time = remaining_time / 20
        else:
            # Critical time: use ~10% per move, but move faster
            base_time = remaining_time / 10
        
        # --- Adjust for position complexity ---
        # More pieces on board = more complex = need more time
        if position_complexity > 25:
            complexity_multiplier = 1.3
        elif position_complexity > 20:
            complexity_multiplier = 1.1
        elif position_complexity < 10:
            complexity_multiplier = 0.8  # Endgame, faster
        else:
            complexity_multiplier = 1.0
        
        base_time *= complexity_multiplier
        
        # --- Adjust based on our previous move time ---
        if self.last_move_time is not None:
            if self.last_move_time > base_time * 1.5:
                # We overspent last move, compensate
                base_time *= 0.8
            elif self.last_move_time < base_time * 0.5:
                # We were very fast last move, can afford more now
                base_time *= 1.2
        
        # Final time allocation: use base time but cap at adaptive max
        time_for_move = min(adaptive_max, max(0.5, base_time))
        
        # Hard deadline: never exceed this (safety margin)
        hard_deadline = min(adaptive_max, remaining_time * 0.9 if remaining_time else adaptive_max)
        
        return time_for_move, hard_deadline

    def search(self, board: chess.Board, *args: HOMEMADE_ARGS_TYPE) -> PlayResult:
        """Search for the best move with iterative deepening and timeout protection."""
        
        # --- Transposition Table Cleanup ---
        current_fen = board.fen()
        if self.last_position_fen is not None and self.last_position_fen != current_fen:
            if len(self.transposition_table) > 50000:
                keys_to_remove = list(self.transposition_table.keys())[:-20000]
                for key in keys_to_remove:
                    del self.transposition_table[key]
                logger.debug(f"Cleaned transposition table: {len(self.transposition_table)} entries remain")
        
        # Store eval before opponent's move (for strength estimation)
        eval_before_opponent_move = None
        if self.last_position_fen is not None:
            # We can estimate from transposition table or do a quick eval
            pos_key = ' '.join(self.last_position_fen.split()[:4])
            if pos_key in self.transposition_table:
                _, eval_before_opponent_move, _ = self.transposition_table[pos_key]
        
        self.last_position_fen = current_fen
        
        # Track opponent's move timing
        current_time = time.time()
        if self.last_search_start is not None:
            self.opponent_last_move_time = current_time - self.last_search_start
            self.opponent_move_times.append(self.opponent_last_move_time)
            # Keep only last 10 moves
            if len(self.opponent_move_times) > 10:
                self.opponent_move_times.pop(0)
        
        # --- Time Management ---
        time_limit = args[0] if (args and isinstance(args[0], Limit)) else None
        
        remaining = None
        if time_limit is not None:
            if isinstance(time_limit.time, (int, float)):
                remaining = time_limit.time
            elif board.turn == chess.WHITE:
                remaining = time_limit.white_clock if isinstance(time_limit.white_clock, (int, float)) else None
            else:
                remaining = time_limit.black_clock if isinstance(time_limit.black_clock, (int, float)) else None
        
        # Calculate position complexity (number of pieces)
        position_complexity = len(board.piece_map())
        
        # Use sophisticated time management function
        time_for_move, hard_deadline_time = self.calculate_time_for_move(remaining, position_complexity)
        
        logger.debug(f"Time allocated: {time_for_move:.2f}s (remaining: {remaining}, complexity: {position_complexity}, opponent strength: {self.opponent_strength_estimate:.2f})")
        
        # Start the clock
        start_time = time.time()
        deadline = start_time + hard_deadline_time

        # Piece values
        values = {
            chess.PAWN: 100,
            chess.KNIGHT: 320,
            chess.BISHOP: 330,
            chess.ROOK: 500,
            chess.QUEEN: 900,
            chess.KING: 0,  # king material ignored (checkmates handled separately)
        }

        # --- Piece-Square Tables (positional bonuses) ---
        # Tables are from White's perspective (higher values = better for White)
        # Black's pieces use the same table flipped vertically
        # VALUES SCALED DOWN: Piece-square tables are now SUBTLE hints (2-5 points max)
        # This prevents sacrificing pieces just to reach "good" squares
        
        PAWN_TABLE = [
            0,  0,  0,  0,  0,  0,  0,  0,
            5,  5,  5,  5,  5,  5,  5,  5,
            1,  1,  2,  3,  3,  2,  1,  1,
            0,  0,  1,  2,  2,  1,  0,  0,
            0,  0,  0,  2,  2,  0,  0,  0,
            0, -1, -1,  0,  0, -1, -1,  0,
            0,  1,  1, -2, -2,  1,  1,  0,
            0,  0,  0,  0,  0,  0,  0,  0
        ]
        
        KNIGHT_TABLE = [
            -5, -4, -3, -3, -3, -3, -4, -5,
            -4, -2,  0,  0,  0,  0, -2, -4,
            -3,  0,  1,  2,  2,  1,  0, -3,
            -3,  0,  2,  3,  3,  2,  0, -3,
            -3,  0,  2,  3,  3,  2,  0, -3,
            -3,  0,  1,  2,  2,  1,  0, -3,
            -4, -2,  0,  0,  0,  0, -2, -4,
            -5, -4, -3, -3, -3, -3, -4, -5
        ]
        
        BISHOP_TABLE = [
            -2, -1, -1, -1, -1, -1, -1, -2,
            -1,  0,  0,  0,  0,  0,  0, -1,
            -1,  0,  1,  1,  1,  1,  0, -1,
            -1,  0,  1,  2,  2,  1,  0, -1,
            -1,  0,  1,  2,  2,  1,  0, -1,
            -1,  0,  1,  1,  1,  1,  0, -1,
            -1,  0,  0,  0,  0,  0,  0, -1,
            -2, -1, -1, -1, -1, -1, -1, -2
        ]
        
        ROOK_TABLE = [
            0,  0,  0,  0,  0,  0,  0,  0,
            1,  2,  2,  2,  2,  2,  2,  1,
            -1,  0,  0,  0,  0,  0,  0, -1,
            -1,  0,  0,  0,  0,  0,  0, -1,
            -1,  0,  0,  0,  0,  0,  0, -1,
            -1,  0,  0,  0,  0,  0,  0, -1,
            -1,  0,  0,  0,  0,  0,  0, -1,
            0,  0,  0,  1,  1,  0,  0,  0
        ]
        
        QUEEN_TABLE = [
            -2, -1, -1,  0,  0, -1, -1, -2,
            -1,  0,  0,  0,  0,  0,  0, -1,
            -1,  0,  1,  1,  1,  1,  0, -1,
            -1,  0,  1,  1,  1,  1,  0, -1,
            -1,  0,  1,  1,  1,  1,  0, -1,
            -1,  0,  1,  1,  1,  1,  0, -1,
            -1,  0,  0,  0,  0,  0,  0, -1,
            -2, -1, -1,  0,  0, -1, -1, -2
        ]
        
        KING_MIDDLEGAME_TABLE = [
            -3, -4, -4, -5, -5, -4, -4, -3,
            -3, -4, -4, -5, -5, -4, -4, -3,
            -3, -4, -4, -5, -5, -4, -4, -3,
            -3, -4, -4, -5, -5, -4, -4, -3,
            -2, -3, -3, -4, -4, -3, -3, -2,
            -1, -2, -2, -2, -2, -2, -2, -1,
            2,  2,  0,  0,  0,  0,  2,  2,
            2,  3,  1,  0,  0,  1,  3,  2
        ]
        
        KING_ENDGAME_TABLE = [
            -5, -4, -3, -2, -2, -3, -4, -5,
            -3, -2, -1,  0,  0, -1, -2, -3,
            -3, -1,  2,  3,  3,  2, -1, -3,
            -3, -1,  3,  4,  4,  3, -1, -3,
            -3, -1,  3,  4,  4,  3, -1, -3,
            -3, -1,  2,  3,  3,  2, -1, -3,
            -3, -3,  0,  0,  0,  0, -3, -3,
            -5, -3, -3, -3, -3, -3, -3, -5
        ]
        
        piece_square_tables = {
            chess.PAWN: PAWN_TABLE,
            chess.KNIGHT: KNIGHT_TABLE,
            chess.BISHOP: BISHOP_TABLE,
            chess.ROOK: ROOK_TABLE,
            chess.QUEEN: QUEEN_TABLE,
            chess.KING: KING_MIDDLEGAME_TABLE  # Will switch to endgame dynamically
        }

        # --- Enhanced evaluation with piece-square tables ---
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
            
            # Material score
            score = 0
            for pt, v in values.items():
                score += v * (len(b.pieces(pt, chess.WHITE)) - len(b.pieces(pt, chess.BLACK)))
            
            # Determine game phase based on the side with FEWER pieces
            # This ensures endgame detection works even if one side has more pieces
            white_pieces = len([1 for p in b.piece_map().values() if p.color == chess.WHITE])
            black_pieces = len([1 for p in b.piece_map().values() if p.color == chess.BLACK])
            min_pieces = min(white_pieces, black_pieces)
            
            # Endgame: when the side with fewer pieces has <= 5 pieces (including king)
            is_endgame = min_pieces <= 5
            
            # Positional score from piece-square tables
            for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]:
                # Select appropriate king table
                if piece_type == chess.KING:
                    table = KING_ENDGAME_TABLE if is_endgame else KING_MIDDLEGAME_TABLE
                else:
                    table = piece_square_tables[piece_type]
                
                # White pieces (use table as-is)
                for square in b.pieces(piece_type, chess.WHITE):
                    score += table[square]
                
                # Black pieces (flip table vertically: rank 7 becomes rank 0, etc.)
                for square in b.pieces(piece_type, chess.BLACK):
                    flipped_square = square ^ 56  # XOR with 56 flips the rank
                    score -= table[flipped_square]
            
            # --- Defensive enhancements ---
            # SIMPLIFIED: Just check if pieces are hanging (undefended or under-defended)
            hanging_penalty = 0
            
            for piece_type in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]:
                piece_value = values[piece_type]
                
                # Check white pieces
                for square in b.pieces(piece_type, chess.WHITE):
                    black_attackers = list(b.attackers(chess.BLACK, square))
                    if black_attackers:
                        white_defenders = list(b.attackers(chess.WHITE, square))
                        
                        # Simple check: if more attackers than defenders, piece is hanging
                        if len(black_attackers) > len(white_defenders):
                            hanging_penalty += piece_value * 0.7
                        elif len(black_attackers) > 0 and len(white_defenders) > 0:
                            # Check if lowest attacker is cheaper than our piece
                            min_attacker_value = min(values.get(b.piece_at(sq).piece_type, 0) 
                                                     for sq in black_attackers if b.piece_at(sq))
                            if piece_value > min_attacker_value + 150:
                                # Bad trade possible (e.g., Queen vs Bishop)
                                hanging_penalty += (piece_value - min_attacker_value) * 0.4
                
                # Check black pieces (symmetric)
                for square in b.pieces(piece_type, chess.BLACK):
                    white_attackers = list(b.attackers(chess.WHITE, square))
                    if white_attackers:
                        black_defenders = list(b.attackers(chess.BLACK, square))
                        
                        if len(white_attackers) > len(black_defenders):
                            hanging_penalty -= piece_value * 0.7  # Good for us
                        elif len(white_attackers) > 0 and len(black_defenders) > 0:
                            min_attacker_value = min(values.get(b.piece_at(sq).piece_type, 0)
                                                     for sq in white_attackers if b.piece_at(sq))
                            if piece_value > min_attacker_value + 150:
                                hanging_penalty -= (piece_value - min_attacker_value) * 0.4
            
            score -= hanging_penalty
            
            # Check king safety: count attackers near our king
            if not is_endgame:
                for color in (chess.WHITE, chess.BLACK):
                    king_square = b.king(color)
                    if king_square is None:
                        continue
                    opponent_color = not color
                    king_danger = 0
                    for sq in chess.SQUARES:
                        if chess.square_distance(sq, king_square) <= 2:
                            attackers = b.attackers(opponent_color, sq)
                            king_danger += len(attackers) * 5
                    if color == chess.WHITE:
                        score -= king_danger
                    else:
                        score += king_danger
            
            # Bonus for controlling center (only in middlegame)
            if not is_endgame:
                center_squares = [chess.E4, chess.D4, chess.E5, chess.D5]
                for sq in center_squares:
                    white_control = len(b.attackers(chess.WHITE, sq))
                    black_control = len(b.attackers(chess.BLACK, sq))
                    score += (white_control - black_control) * 3
            
            return score
        
        # --- Simplified move ordering with safety checks ---
        def order_moves(b: chess.Board, moves: list[chess.Move]) -> list[chess.Move]:
            """Order moves: good captures first, avoid hanging pieces, then quiet moves."""
            
            def move_score(move: chess.Move) -> int:
                score = 0
                
                moving_piece = b.piece_at(move.from_square)
                if not moving_piece:
                    return 0
                
                moving_value = values.get(moving_piece.piece_type, 0)
                
                # Captures: MVV-LVA (Most Valuable Victim - Least Valuable Attacker)
                if b.is_capture(move):
                    victim_piece = b.piece_at(move.to_square)
                    if victim_piece:
                        victim_value = values.get(victim_piece.piece_type, 0)
                        
                        # Only do the capture if it's a good trade
                        if victim_value >= moving_value - 100:
                            # Good capture: equal or winning material
                            score = victim_value * 10 - moving_value
                        else:
                            # Bad capture: losing material (e.g., Queen takes Pawn)
                            # Check if piece would be safe after capture
                            b.push(move)
                            to_square = move.to_square
                            opponent_attackers = list(b.attackers(b.turn, to_square))  # turn switched
                            our_defenders = list(b.attackers(not b.turn, to_square))
                            b.pop()
                            
                            if len(opponent_attackers) > len(our_defenders):
                                # We'd lose the piece after capturing
                                score = victim_value * 10 - moving_value * 25  # Heavy penalty
                            else:
                                # Piece is defended, capture is okay
                                score = victim_value * 10 - moving_value
                
                # Promotions
                if move.promotion:
                    promotion_value = values.get(move.promotion, 0)
                    score += (promotion_value - values[chess.PAWN]) * 10
                
                # Check bonus - but ONLY if the piece is safe!
                b.push(move)
                gives_check = b.is_check()
                b.pop()
                
                if gives_check:
                    # Check if the checking piece is safe
                    b.push(move)
                    to_square = move.to_square
                    opponent_attackers = list(b.attackers(b.turn, to_square))
                    our_defenders = list(b.attackers(not b.turn, to_square))
                    b.pop()
                    
                    if not opponent_attackers:
                        # Safe check - small bonus
                        score += 50
                    elif len(our_defenders) >= len(opponent_attackers):
                        # Defended check - tiny bonus (only if cheap piece)
                        if moving_value <= 320:
                            score += 20
                    # else: no bonus for unsafe checks
                
                # Quiet moves: check if destination is safe
                if not b.is_capture(move) and not move.promotion:
                    b.push(move)
                    to_square = move.to_square
                    opponent_attackers = list(b.attackers(b.turn, to_square))
                    
                    if opponent_attackers:
                        our_defenders = list(b.attackers(not b.turn, to_square))
                        
                        if len(opponent_attackers) > len(our_defenders):
                            # Piece would hang after this move!
                            score -= moving_value * 50  # MASSIVE penalty
                        elif len(opponent_attackers) > 0:
                            # Check if it's a bad trade
                            min_attacker_value = min(values.get(b.piece_at(sq).piece_type, 0)
                                                     for sq in opponent_attackers if b.piece_at(sq))
                            if moving_value > min_attacker_value + 150:
                                # Would lose material in trade
                                score -= (moving_value - min_attacker_value) * 10
                    
                    b.pop()
                
                return score
            
            return sorted(moves, key=move_score, reverse=True)

        # --- quiescence search with depth limit (prevents infinite loops) ---
        def quiescence(b: chess.Board, alpha: float, beta: float, qs_depth: int = 0) -> int:
            """Search only tactical moves (captures/checks) until position is quiet.
            
            CRITICAL: qs_depth parameter prevents infinite loops in quiescence.
            We limit quiescence to MAX_QS_DEPTH to avoid endless capture chains.
            """
            MAX_QS_DEPTH = 10  # Safety limit to prevent infinite recursion
            
            # Check timeout
            if time.time() >= deadline:
                return evaluate(b)
            
            # Depth limit check (prevents infinite loops!)
            if qs_depth >= MAX_QS_DEPTH:
                return evaluate(b)
            
            # Stand pat: evaluate current position without any moves
            stand_pat = evaluate(b)
            
            # Check if we're in a terminal position
            if b.is_game_over():
                return stand_pat
            
            # Determine who's to move
            maximizing = b.turn == chess.WHITE
            
            if maximizing:
                # Beta cutoff: position is already too good for opponent
                if stand_pat >= beta:
                    return beta
                # Update alpha if standing pat is better
                if stand_pat > alpha:
                    alpha = stand_pat
            else:
                # Alpha cutoff: position is already too bad for us
                if stand_pat <= alpha:
                    return alpha
                # Update beta if standing pat is better
                if stand_pat < beta:
                    beta = stand_pat
            
            # Generate only tactical moves (captures and SAFE checks)
            tactical_moves = []
            for m in b.legal_moves:
                if b.is_capture(m):
                    # Always include captures
                    tactical_moves.append(m)
                elif b.gives_check(m):
                    # Only include check if piece is safe afterwards
                    moving_piece = b.piece_at(m.from_square)
                    if moving_piece:
                        moving_value = values.get(moving_piece.piece_type, 0)
                        
                        # Simulate the check
                        b.push(m)
                        to_square = m.to_square
                        opponent_attackers = list(b.attackers(b.turn, to_square))
                        our_defenders = list(b.attackers(not b.turn, to_square))
                        b.pop()
                        
                        # Only include check if:
                        # 1. Piece is not attacked, OR
                        # 2. Piece is defended and it's a low-value piece (pawn/knight)
                        if not opponent_attackers:
                            tactical_moves.append(m)  # Safe check
                        elif len(our_defenders) >= len(opponent_attackers) and moving_value <= 320:
                            tactical_moves.append(m)  # Defended check with cheap piece
            
            # Sort tactical moves (MVV-LVA ordering helps quiescence too!)
            ordered_tactical = order_moves(b, tactical_moves)
            
            # Search tactical moves
            for m in ordered_tactical:
                b.push(m)
                score = quiescence(b, alpha, beta, qs_depth + 1)  # Increment depth!
                b.pop()
                
                if maximizing:
                    if score >= beta:
                        return beta  # Beta cutoff
                    if score > alpha:
                        alpha = score
                else:
                    if score <= alpha:
                        return alpha  # Alpha cutoff
                    if score < beta:
                        beta = score
            
            # Return the best score we found
            return alpha if maximizing else beta

        # --- Alpha-beta with timeout check and transposition table ---
        def alphabeta(b: chess.Board, depth: int, alpha: float, beta: float, maximizing: bool, ply: int = 0) -> tuple[int, chess.Move | None]:
            """Alpha-beta pruning with quiescence search, timeout protection, and transposition table.
            
            Returns: (evaluation, best_move)
            """

            # Timeout check at every node
            if time.time() >= deadline:
                return evaluate(b), None
            
            # Check transposition table
            # Use a simpler position key (FEN without move counters for better cache hits)
            pos_key = ' '.join(b.fen().split()[:4])  # Position, color, castling, en passant (no move counters)
            
            # Try to retrieve from transposition table
            if pos_key in self.transposition_table:
                cached_depth, cached_eval, cached_move = self.transposition_table[pos_key]
                # Only use cached result if it was searched to equal or greater depth
                if cached_depth >= depth:
                    # HUGE SPEEDUP: We already analyzed this position deeply enough!
                    # This is where we save time from previous searches
                    return cached_eval, cached_move
            
            # At leaf nodes, enter quiescence search
            if depth == 0:
                return quiescence(b, alpha, beta, qs_depth=0), None
            
            if b.is_game_over():
                outcome = b.outcome()
                if outcome is None or outcome.winner is None:
                    # Draw - evaluate based on material balance
                    eval_score = evaluate(b)
                    # If we're losing, prefer the draw
                    if (b.turn == chess.WHITE and eval_score < -200) or \
                       (b.turn == chess.BLACK and eval_score > 200):
                        return 0, None  # Draw is acceptable when losing
                    return eval_score, None  # Otherwise use material evaluation
                # Checkmate: return huge score adjusted by ply (prefer faster mates)
                if outcome.winner == chess.WHITE:
                    return 10_000_000 - ply, None
                else:
                    return -10_000_000 + ply, None

            # Order moves: try cached move first (from previous search), then captures
            legal_moves = list(b.legal_moves)
            
            # CRITICAL OPTIMIZATION: Try the cached best move first
            # This move was best in a previous search, so it's likely still good
            # This dramatically improves alpha-beta pruning efficiency
            cached_move_to_try = None
            if pos_key in self.transposition_table:
                _, _, cached_move = self.transposition_table[pos_key]
                if cached_move and cached_move in legal_moves:
                    cached_move_to_try = cached_move
                    legal_moves.remove(cached_move)
            
            # Order remaining moves by MVV-LVA (captures first)
            ordered_moves = order_moves(b, legal_moves)
            
            # Put cached move at the front
            if cached_move_to_try:
                ordered_moves.insert(0, cached_move_to_try)
            
            best_move_found = None

            if maximizing:
                max_eval = -10**12
                fully_searched = True
                for m in ordered_moves:
                    b.push(m)
                    val, _ = alphabeta(b, depth - 1, alpha, beta, False, ply + 1)
                    b.pop()
                    if val > max_eval:
                        max_eval = val
                        best_move_found = m
                    if max_eval > alpha:
                        alpha = max_eval
                    if alpha >= beta:
                        fully_searched = False
                        break  # Beta cutoff
                
                if fully_searched and best_move_found is not None and time.time() < deadline:
                    self.transposition_table[pos_key] = (depth, max_eval, best_move_found)
                return max_eval, best_move_found
            else:
                min_eval = 10**12
                fully_searched = True
                for m in ordered_moves:
                    b.push(m)
                    val, _ = alphabeta(b, depth - 1, alpha, beta, True, ply + 1)
                    b.pop()
                    if val < min_eval:
                        min_eval = val
                        best_move_found = m
                    if min_eval < beta:
                        beta = min_eval
                    if alpha >= beta:
                        fully_searched = False
                        break  # Alpha cutoff
                
                if fully_searched and best_move_found is not None and time.time() < deadline:
                    self.transposition_table[pos_key] = (depth, min_eval, best_move_found)
                return min_eval, best_move_found

        # --- Iterative deepening search ---
        def iterative_deepening_search(legal_moves: list[chess.Move]) -> tuple[chess.Move, int, int]:
            """Search with iterative deepening: depth 1, 2, 3... until time runs out.

            Benefits:
            - Natural time control (can stop anytime with best move so far)
            - Better move ordering in deeper iterations
            - Guaranteed to have at least depth 1 result

            Returns: (best_move, best_eval, deepest_completed_depth)
            """
            ordered = order_moves(board, legal_moves)

            best_move: chess.Move | None = None
            best_eval = 0
            last_completed_depth = 0

            import math
            if time_for_move < 0.3:
                max_depth_target = 2  # Emergency
            else:
                max_depth_target = round(math.log(3 * time_for_move) / math.log(3)) + 3
                max_depth_target = max(2, min(8, max_depth_target))

            depth = 1

            while depth <= max_depth_target:
                elapsed = time.time() - start_time
                if elapsed >= time_for_move * 0.85:
                    break

                alpha = -10**12
                beta = 10**12
                current_best_move = best_move
                current_best_eval = -10**12 if board.turn == chess.WHITE else 10**12

                iteration_complete = True
                for m in ordered:
                    if time.time() >= deadline:
                        iteration_complete = False
                        break

                    board.push(m)
                    val, _ = alphabeta(board, depth - 1, alpha, beta, board.turn == chess.WHITE, ply=1)
                    board.pop()

                    if board.turn == chess.WHITE:
                        if val > current_best_eval:
                            current_best_eval = val
                            current_best_move = m
                        if val > alpha:
                            alpha = val
                    else:
                        if val < current_best_eval:
                            current_best_eval = val
                            current_best_move = m
                        if val < beta:
                            beta = val

                if iteration_complete:
                    best_move = current_best_move
                    best_eval = current_best_eval
                    last_completed_depth = depth
                    logger.debug(f"Depth {depth} completed: {best_move} with eval {best_eval}")

                    if abs(best_eval) > 9_000_000:
                        logger.debug(f"Checkmate found at depth {depth}")
                        break

                    depth += 1
                else:
                    logger.debug(f"Depth {depth} interrupted by timeout")
                    break

            if best_move is None and ordered:
                best_move = ordered[0]
                board.push(best_move)
                best_eval = evaluate(board)
                board.pop()

            return best_move, best_eval, last_completed_depth

        # --- Root move selection ---
        legal = list(board.legal_moves)
        if not legal:
            # Should not happen during normal play
            return PlayResult(random.choice(list(board.legal_moves)), None)

        # Use iterative deepening for smart time management
        best_move, best_eval, completed_depth = iterative_deepening_search(legal)

        # Fallback in rare cases (shouldn't trigger)
        if best_move is None:
            best_move = legal[0]

        # --- Opponent Strength Estimation ---
        # After we search, we know the current position's evaluation
        # Next time (after opponent moves), we can see how much the eval changed
        if eval_before_opponent_move is not None and self.opponent_last_move_time is not None:
            # Estimate opponent strength based on their previous move
            self.estimate_opponent_strength(eval_before_opponent_move, best_eval, self.opponent_last_move_time)

        elapsed = time.time() - start_time
        self.last_move_time = elapsed  # Track for adaptive time management
        self.last_search_start = time.time()  # Track when we finished (opponent starts thinking)
        
        logger.info(f"Move: {best_move} | Time: {elapsed:.2f}s | Eval: {best_eval} | Depth: {completed_depth} | Opponent strength: {self.opponent_strength_estimate:.2f}")

        return PlayResult(best_move, None)